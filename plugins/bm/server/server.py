#!/usr/bin/env python3
"""bm bookmarklet daemon.

Pure-stdlib HTTP server on 127.0.0.1:9876. Accepts URL captures from the
browser bookmarklet and writes inbox files into the bookmark vault.
Also serves the v5 web UI for browsing/visualizing the vault.

Endpoints:
  POST /add             — JSON body {url, title?}. Writes inbox file.
  GET  /add             — ?url=&title=. CSP-fallback path; returns auto-closing HTML.
  GET  /health          — {ok, vault, inbox_count}.
  GET  /                — Web UI shell (server/ui/index.html).
  GET  /static/<name>   — Whitelisted UI assets (app.js, style.css).
  GET  /bookmarks.json  — Full vault data: bookmarks + collections + tag/host aggregates.

Vault discovery: BM_VAULT env var first, then ~/Documents/obsidian/whiskers,
~/Documents/whiskers, ~/whiskers. First match where AGENTS.md first line
contains "Bookmarks Vault" wins. Resolved once at startup.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 9876
UI_DIR = Path(__file__).resolve().parent / "ui"
UI_ASSETS = {  # whitelist of /static/<name> → content-type
    "app.js": "application/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
}
URL_RE = re.compile(r"^https?://[^\s]+$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)
LLM_MARKER = "<!-- /llm-managed -->"
VAULT_CANDIDATES = [
    os.environ.get("BM_VAULT") or "",
    str(Path.home() / "Documents" / "obsidian" / "whiskers"),
    str(Path.home() / "Documents" / "whiskers"),
    str(Path.home() / "whiskers"),
]


def find_vault() -> Path:
    for candidate in VAULT_CANDIDATES:
        if not candidate:
            continue
        p = Path(candidate)
        agents = p / "AGENTS.md"
        if not agents.is_file():
            continue
        try:
            first = agents.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        except OSError:
            continue
        if first and "Bookmarks Vault" in first[0]:
            return p
    print(
        "bm-server: no bookmarks vault found. Set BM_VAULT or place vault at "
        "~/Documents/obsidian/whiskers",
        file=sys.stderr,
    )
    sys.exit(1)


VAULT = find_vault()
INBOX = VAULT / "_inbox"
INBOX.mkdir(exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{ts}] {msg}", flush=True)


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sixid(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:6]


def dedup_hit(url: str) -> str | None:
    """Return path of existing file containing `url: <url>` line, or None.

    Uses ripgrep for speed; falls back to a Python scan if rg isn't installed.
    """
    needle = f"url: {url}"
    rg = subprocess.run(
        ["rg", "-Fx", "-l", needle, str(VAULT), "--type", "md"],
        capture_output=True,
        text=True,
    )
    if rg.returncode == 0 and rg.stdout.strip():
        return rg.stdout.splitlines()[0]
    if rg.returncode in (0, 1):
        return None
    # rg not installed or errored — fall back
    for p in VAULT.rglob("*.md"):
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if line == needle:
                    return str(p)
        except OSError:
            continue
    return None


def write_inbox(url: str, title: str | None) -> tuple[str, Path]:
    """Write an inbox file. Returns ("saved"|"duplicate", path)."""
    hit = dedup_hit(url)
    if hit:
        return ("duplicate", Path(hit))
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = INBOX / f"{ts}-{sixid(url)}.md"
    lines = ["---", f"url: {url}"]
    if title:
        # YAML-quote double quotes, drop newlines / control chars.
        clean = " ".join(title.split())
        clean = clean.replace('"', '\\"')
        lines.append(f'title: "{clean}"')
    lines.append(f"captured: {iso_now()}")
    lines.append("source: bookmarklet")
    lines.append("---")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return ("saved", path)


def _parse_frontmatter_block(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Frontmatter parsed via tiny line scanner
    (good enough for the bm schema — keeps the daemon stdlib-only)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, ""
    block, body = m.group(1), m.group(2)
    fm: dict = {}
    for line in block.splitlines():
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        # Skip indented continuation lines (e.g. nested proposed_collection.name)
        if line.startswith((" ", "\t")):
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        # Flow-style list: tags: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                fm[key] = []
            else:
                fm[key] = [_strip_yaml_scalar(part.strip()) for part in inner.split(",")]
            continue
        # Empty value (nested block following — we skip nested for our purposes)
        if not val:
            continue
        fm[key] = _strip_yaml_scalar(val)
    return fm, body


def _strip_yaml_scalar(s: str) -> str:
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def _extract_blurb(body: str) -> str:
    """v1.3+ schema: blurb sits above the `<!-- /llm-managed -->` marker."""
    if LLM_MARKER in body:
        return body.partition(LLM_MARKER)[0].strip()
    return body.strip()


def _collect_vault_data(vault: Path) -> dict:
    """Walk the vault, return the JSON shape consumed by the UI.

    Includes filed bookmarks (user collections + `_unsorted/` + `_broken/`)
    with normalized frontmatter; aggregates for tags, hosts, and per-collection
    counts. Sorted: collections by count desc with system dirs at the end;
    tags and hosts by count desc.
    """
    user_collections: list[Path] = []
    system_collections: list[Path] = []
    for child in sorted(vault.iterdir()):
        if not child.is_dir():
            continue
        if child.name == "outputs":
            continue
        if child.name in ("_unsorted", "_broken"):
            system_collections.append(child)
            continue
        if child.name.startswith("_"):
            continue
        if not (child / "README.md").exists():
            continue
        user_collections.append(child)

    bookmarks: list[dict] = []
    coll_counts: dict[str, int] = {}
    tag_counter: Counter = Counter()
    host_counter: Counter = Counter()

    for coll in user_collections + system_collections:
        count = 0
        for p in sorted(coll.glob("*.md")):
            if p.name == "README.md":
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm, body = _parse_frontmatter_block(text)
            if not fm:
                continue
            blurb = _extract_blurb(body) or fm.get("blurb") or ""
            tags_raw = fm.get("tags") or []
            tags = [str(t) for t in tags_raw if t]
            url = fm.get("url") or ""
            host = ""
            try:
                host = urllib.parse.urlparse(url).hostname or ""
                if host.startswith("www."):
                    host = host[4:]
            except ValueError:
                host = ""
            bookmarks.append({
                "url": url,
                "title": fm.get("title") or "",
                "blurb": blurb,
                "tags": tags,
                "collection": coll.name,
                "captured": fm.get("captured") or "",
                "enriched": fm.get("enriched") or "",
                "status": fm.get("status") or "active",
                "host": host,
                "needs_review": str(fm.get("needs_review", "")).lower() == "true",
                "path": str(p.relative_to(vault)),
            })
            count += 1
            tag_counter.update(tags)
            if host:
                host_counter[host] += 1
        coll_counts[coll.name] = count

    collections_out = [
        {"name": c.name, "count": coll_counts.get(c.name, 0), "kind": "user"}
        for c in user_collections
    ]
    collections_out.sort(key=lambda r: (-r["count"], r["name"]))
    collections_out.extend(
        {"name": c.name, "count": coll_counts.get(c.name, 0), "kind": "system"}
        for c in system_collections
    )

    return {
        "vault": str(vault),
        "generated_at": iso_now(),
        "totals": {
            "bookmarks": len(bookmarks),
            "collections": len(user_collections),
            "tags": len(tag_counter),
            "hosts": len(host_counter),
        },
        "collections": collections_out,
        "tags": [
            {"name": t, "count": n} for t, n in tag_counter.most_common()
        ],
        "hosts": [
            {"host": h, "count": n} for h, n in host_counter.most_common()
        ],
        "bookmarks": bookmarks,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "bm-server/0.4"

    def log_message(self, fmt: str, *args) -> None:  # silence default access log
        return

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html(self, code: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/health":
            inbox_count = sum(
                1 for _ in INBOX.glob("*.md") if _.name != ".gitkeep"
            )
            return self._json(200, {"ok": True, "vault": str(VAULT), "inbox_count": inbox_count})
        if path == "/add":
            q = urllib.parse.parse_qs(parsed.query)
            url = (q.get("url", [""])[0] or "").strip()
            title = (q.get("title", [""])[0] or "").strip() or None
            return self._handle_add(url, title, html_response=True)
        if path == "/":
            return self._serve_static_file(UI_DIR / "index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            ctype = UI_ASSETS.get(name)
            if not ctype:
                return self._json(404, {"error": "not found"})
            return self._serve_static_file(UI_DIR / name, ctype)
        if path == "/bookmarks.json":
            return self._serve_bookmarks_json()
        return self._json(404, {"error": "not found"})

    def _serve_static_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            return self._json(404, {"error": f"asset missing: {path.name}"})
        except OSError as e:
            return self._json(500, {"error": str(e)})
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _serve_bookmarks_json(self) -> None:
        try:
            data = _collect_vault_data(VAULT)
        except OSError as e:
            return self._json(500, {"error": str(e)})
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # No-cache so the UI's refresh button always sees fresh data
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if urllib.parse.urlparse(self.path).path != "/add":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._json(400, {"error": "invalid json body"})
        url = (payload.get("url") or "").strip()
        title = (payload.get("title") or "").strip() or None
        return self._handle_add(url, title, html_response=False)

    def _handle_add(self, url: str, title: str | None, *, html_response: bool) -> None:
        if not URL_RE.match(url):
            log(f"POST /add 400 invalid-url {url!r}")
            if html_response:
                return self._html(400, _html_done("Invalid URL", url, ok=False))
            return self._json(400, {"error": "invalid url", "url": url})
        try:
            status, path = write_inbox(url, title)
        except OSError as e:
            log(f"POST /add 500 write-error {url} ({e})")
            if html_response:
                return self._html(500, _html_done(f"Error: {e}", url, ok=False))
            return self._json(500, {"error": str(e)})
        log(f"POST /add 200 {status} {url}")
        if html_response:
            return self._html(200, _html_done("Saved" if status == "saved" else "Duplicate", url, ok=True))
        return self._json(200, {"status": status, "path": str(path)})


def _html_done(msg: str, url: str, *, ok: bool) -> str:
    color = "#10b981" if ok else "#ef4444"
    safe_msg = msg.replace("<", "&lt;").replace(">", "&gt;")
    safe_url = url.replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<!doctype html><meta charset=utf-8>"
        f"<title>bm</title>"
        f"<body style=\"font:13px/1.4 system-ui;margin:12px;color:#222\">"
        f"<div style=\"color:{color};font-weight:600\">{safe_msg}</div>"
        f"<div style=\"opacity:.6;margin-top:4px;word-break:break-all\">{safe_url}</div>"
        f"<script>setTimeout(()=>window.close(),700)</script>"
        f"</body>"
    )


def shutdown(srv: ThreadingHTTPServer) -> None:
    def handler(signum, frame):  # noqa: ARG001
        log(f"signal {signum} received, shutting down")
        srv.shutdown()
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main() -> int:
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    shutdown(srv)
    log(f"bm-server listening on http://{HOST}:{PORT}  vault={VAULT}")
    try:
        srv.serve_forever()
    finally:
        srv.server_close()
        log("bm-server stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

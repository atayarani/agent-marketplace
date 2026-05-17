#!/usr/bin/env python3
"""bm bookmarklet daemon.

Pure-stdlib HTTP server on 127.0.0.1:9876. Accepts URL captures from the
browser bookmarklet and writes inbox files into the bookmark vault.

Endpoints:
  POST /add     — JSON body {url, title?}. Writes inbox file.
  GET  /add     — ?url=&title=. CSP-fallback path; returns auto-closing HTML.
  GET  /health  — {ok, vault, inbox_count}.

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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 9876
URL_RE = re.compile(r"^https?://[^\s]+$")
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


class Handler(BaseHTTPRequestHandler):
    server_version = "bm-server/0.3"

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
        if parsed.path == "/health":
            inbox_count = sum(
                1 for _ in INBOX.glob("*.md") if _.name != ".gitkeep"
            )
            return self._json(200, {"ok": True, "vault": str(VAULT), "inbox_count": inbox_count})
        if parsed.path == "/add":
            q = urllib.parse.parse_qs(parsed.query)
            url = (q.get("url", [""])[0] or "").strip()
            title = (q.get("title", [""])[0] or "").strip() or None
            return self._handle_add(url, title, html_response=True)
        return self._json(404, {"error": "not found"})

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

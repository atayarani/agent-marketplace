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
FRONTMATTER_RE = re.compile(r"^(---\n)(.*?\n)(---\n?)(.*)", re.DOTALL)
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
    block, body = m.group(2), m.group(4)
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


def _host_from_url(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _collect_vault_data(vault: Path) -> dict:
    """Walk the vault, return the JSON shape consumed by the UI.

    Includes filed bookmarks (user collections + `_unsorted/` + `_broken/`)
    and inbox files (`_inbox/`). Each bookmark carries `kind: "filed"` or
    `kind: "inbox"`. Inbox files have empty `blurb`/`enriched`/`status` and
    fall back to `imported_tags` for tags, URL path for title when missing.

    Aggregates:
      - `tags`: canonical vocabulary (filed bookmarks only).
      - `hosts`: all bookmarks (filed + inbox).
      - `collections`: user dirs + `_unsorted` + `_broken` + `_inbox` (system).
    """
    # User collections: any directory containing a README.md, at any depth,
    # under a top-level segment that isn't `_`-prefixed or `outputs`. Nesting
    # is bm 1.6+ — pre-1.6 vaults are fully flat and still walk correctly.
    user_collections: list[Path] = []
    for readme in sorted(vault.rglob("README.md")):
        coll = readme.parent
        rel = coll.relative_to(vault)
        parts = rel.parts
        if not parts:
            continue  # vault-root README.md is not a collection
        top = parts[0]
        if top.startswith("_") or top == "outputs":
            continue
        user_collections.append(coll)
    # System pseudo-collections (flat sinks; not nested).
    system_collections: list[Path] = []
    for special in ("_unsorted", "_broken"):
        d = vault / special
        if d.is_dir():
            system_collections.append(d)

    bookmarks: list[dict] = []
    coll_counts: dict[str, int] = {}
    tag_counter: Counter = Counter()       # canonical tags (filed only)
    host_counter: Counter = Counter()      # all bookmarks

    def append_filed(p: Path, coll_name: str) -> bool:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        fm, body = _parse_frontmatter_block(text)
        if not fm:
            return False
        url = fm.get("url") or ""
        host = _host_from_url(url)
        tags = [str(t) for t in (fm.get("tags") or []) if t]
        bookmarks.append({
            "kind": "filed",
            "url": url,
            "title": fm.get("title") or "",
            "blurb": _extract_blurb(body) or fm.get("blurb") or "",
            "tags": tags,
            "collection": coll_name,
            "captured": fm.get("captured") or "",
            "enriched": fm.get("enriched") or "",
            "status": fm.get("status") or "active",
            "source": fm.get("source") or "",
            "host": host,
            "og_image": fm.get("og_image") or "",
            "needs_review": str(fm.get("needs_review", "")).lower() == "true",
            "path": str(p.relative_to(vault)),
        })
        tag_counter.update(tags)
        if host:
            host_counter[host] += 1
        return True

    def append_inbox(p: Path) -> bool:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        fm, _ = _parse_frontmatter_block(text)
        if not fm:
            return False
        url = fm.get("url") or ""
        if not url:
            return False
        host = _host_from_url(url)
        # Inbox has imported_tags (from Raindrop) but no canonical tags yet.
        imported_tags = [str(t) for t in (fm.get("imported_tags") or []) if t]
        bookmarks.append({
            "kind": "inbox",
            "url": url,
            "title": fm.get("title") or "",  # bookmarklet captures may have one; imports won't
            "blurb": "",
            "tags": imported_tags,            # surface imported_tags as the tag list for filtering
            "collection": "_inbox",
            "captured": fm.get("captured") or "",
            "enriched": "",
            "status": "pending",
            "source": fm.get("source") or "",
            "host": host,
            "og_image": "",                   # inbox hasn't been through extract.py yet
            "needs_review": False,
            "imported_collection": fm.get("imported_collection") or "",
            "path": str(p.relative_to(vault)),
        })
        if host:
            host_counter[host] += 1
        return True

    for coll in user_collections + system_collections:
        # Collection identifier: vault-relative posix path. Flat collections
        # render as a single segment (`flat-coll`); nested as a slash-path
        # (`parent-coll/child-a`). System sinks (_unsorted, _broken) stay flat.
        coll_id = coll.relative_to(vault).as_posix()
        count = 0
        for p in sorted(coll.glob("*.md")):
            if p.name == "README.md":
                continue
            if append_filed(p, coll_id):
                count += 1
        coll_counts[coll_id] = count

    inbox_dir = vault / "_inbox"
    inbox_count = 0
    if inbox_dir.is_dir():
        for p in sorted(inbox_dir.glob("*.md")):
            if p.name == ".gitkeep":
                continue
            if append_inbox(p):
                inbox_count += 1

    # _trash/ — surfaced as a system collection with kind="trash" per bookmark.
    # NOT counted in totals.bookmarks; NOT included in tag/host aggregates.
    trash_count = 0
    trash_dir = vault / "_trash"
    if trash_dir.is_dir():
        for p in sorted(trash_dir.glob("*.md")):
            if p.name == ".gitkeep":
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm, body = _parse_frontmatter_block(text)
            if not fm:
                continue
            url = fm.get("url") or ""
            host = _host_from_url(url)
            tags = [str(t) for t in (fm.get("tags") or []) if t]
            bookmarks.append({
                "kind": "trash",
                "url": url,
                "title": fm.get("title") or "",
                "blurb": _extract_blurb(body) or fm.get("blurb") or "",
                "tags": tags,
                "collection": "_trash",
                "captured": fm.get("captured") or "",
                "enriched": fm.get("enriched") or "",
                "status": "trashed",
                "source": fm.get("source") or "",
                "host": host,
                "og_image": fm.get("og_image") or "",
                "needs_review": False,
                "trashed_from": fm.get("trashed_from") or "",
                "trashed_at": fm.get("trashed_at") or "",
                "path": str(p.relative_to(vault)),
            })
            trash_count += 1

    # Collection identifier == vault-relative posix path (flat: single segment;
    # nested: slash-path). System sinks (_unsorted, _broken) are always flat.
    def _cid(c: Path) -> str:
        return c.relative_to(vault).as_posix()
    collections_out = [
        {"name": _cid(c), "count": coll_counts.get(_cid(c), 0), "kind": "user"}
        for c in user_collections
    ]
    collections_out.sort(key=lambda r: (-r["count"], r["name"]))
    collections_out.extend(
        {"name": _cid(c), "count": coll_counts.get(_cid(c), 0), "kind": "system"}
        for c in system_collections
    )
    collections_out.append({"name": "_inbox", "count": inbox_count, "kind": "system"})
    collections_out.append({"name": "_trash", "count": trash_count, "kind": "system"})

    # totals.bookmarks counts active items only (filed + inbox); trash is separate.
    active = len(bookmarks) - trash_count
    return {
        "vault": str(vault),
        "generated_at": iso_now(),
        "totals": {
            "bookmarks": active,
            "filed": active - inbox_count,
            "inbox": inbox_count,
            "trashed": trash_count,
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


def _inject_frontmatter_fields(path: Path, fields: dict[str, str]) -> None:
    """Insert `key: "value"` lines just before the closing `---` of the
    frontmatter. Values are double-quoted to survive YAML colons / spaces.
    """
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return
    open_marker, fm_inner, close_marker, body = m.group(1), m.group(2), m.group(3), m.group(4)
    if not fm_inner.endswith("\n"):
        fm_inner += "\n"
    extras_lines = []
    for k, v in fields.items():
        escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
        extras_lines.append(f'{k}: "{escaped}"\n')
    path.write_text(open_marker + fm_inner + "".join(extras_lines) + close_marker + body, encoding="utf-8")


def _strip_frontmatter_fields(path: Path, keys: tuple[str, ...]) -> None:
    """Remove top-level `key: ...` lines (not indented) from the frontmatter."""
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return
    open_marker = m.group(1)
    fm_inner = m.group(2)
    close_marker = m.group(3)
    body = m.group(4)
    kept = []
    drop_set = set(keys)
    for line in fm_inner.splitlines():
        # Match top-level (non-indented) lines like `key: ...`
        if line and not line.startswith((" ", "\t")) and ":" in line:
            key = line.split(":", 1)[0].strip()
            if key in drop_set:
                continue
        kept.append(line)
    new_inner = "\n".join(kept)
    if not new_inner.endswith("\n"):
        new_inner += "\n"
    path.write_text(open_marker + new_inner + close_marker + body, encoding="utf-8")


def _git_mv(src: Path, dst: Path) -> bool:
    """git mv with Path.rename fallback. Returns True on success."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        src_rel = src.relative_to(VAULT)
        dst_rel = dst.relative_to(VAULT)
        subprocess.run(
            ["git", "-C", str(VAULT), "mv", str(src_rel), str(dst_rel)],
            check=True, capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        try:
            src.rename(dst)
            return True
        except OSError:
            return False


class Handler(BaseHTTPRequestHandler):
    server_version = "bm-server/0.5"

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
        route = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._json(400, {"error": "invalid json body"})
        if route == "/add":
            url = (payload.get("url") or "").strip()
            title = (payload.get("title") or "").strip() or None
            return self._handle_add(url, title, html_response=False)
        if route == "/delete":
            return self._handle_delete(payload)
        if route == "/restore":
            return self._handle_restore(payload)
        if route == "/empty-trash":
            return self._handle_empty_trash(payload)
        return self._json(404, {"error": "not found"})

    def _handle_delete(self, payload: dict) -> None:
        """Soft-delete a bookmark by moving its file to `_trash/`.

        Body: {"path": "<vault-relative path>"}. Path must resolve inside the
        vault, be an existing .md file, and not already be under `_trash/`.
        Adds `trashed_from: <collection>` and `trashed_at: <ISO>` to
        frontmatter before the move so `/restore` knows where to put it back.
        Uses `git mv` when the vault is a git repo, falls back to rename.
        Collisions in `_trash/` get a timestamp suffix.
        """
        rel = (payload.get("path") or "").strip()
        if not rel:
            return self._json(400, {"error": "missing path"})
        try:
            src = (VAULT / rel).resolve()
            src.relative_to(VAULT)
        except (ValueError, OSError):
            return self._json(400, {"error": "path escapes vault"})
        if not src.exists():
            return self._json(404, {"error": "file not found"})
        if not src.is_file() or src.suffix != ".md":
            return self._json(400, {"error": "not a markdown file"})
        rel_parts = src.relative_to(VAULT).parts
        if rel_parts and rel_parts[0] == "_trash":
            return self._json(400, {"error": "already in _trash"})
        original_collection = rel_parts[0] if rel_parts else ""
        # Inject trashed_from / trashed_at into frontmatter before moving
        try:
            _inject_frontmatter_fields(src, {
                "trashed_from": original_collection,
                "trashed_at": iso_now(),
            })
        except OSError as e:
            log(f"POST /delete 500 frontmatter-write {rel} ({e})")
            return self._json(500, {"error": str(e)})
        # Compute destination (with timestamp suffix on collision)
        trash = VAULT / "_trash"
        trash.mkdir(exist_ok=True)
        dst = trash / src.name
        if dst.exists():
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            dst = trash / f"{src.stem}-{ts}{src.suffix}"
            n = 1
            while dst.exists():
                n += 1
                dst = trash / f"{src.stem}-{ts}-{n}{src.suffix}"
        if not _git_mv(src, dst):
            log(f"POST /delete 500 {rel} (rename failed)")
            return self._json(500, {"error": "could not move file"})
        new_rel = str(dst.relative_to(VAULT))
        log(f"POST /delete 200 {rel} -> {new_rel}")
        return self._json(200, {"ok": True, "new_path": new_rel})

    def _handle_restore(self, payload: dict) -> None:
        """Restore a `_trash/` file to its original collection (or `_unsorted/`).

        Body: {"path": "_trash/foo.md"}. Reads `trashed_from:` from frontmatter
        to pick the destination; falls back to `_unsorted/` if missing, empty,
        or the target dir no longer exists. Strips `trashed_from:` and
        `trashed_at:` from frontmatter on the way out.
        """
        rel = (payload.get("path") or "").strip()
        if not rel:
            return self._json(400, {"error": "missing path"})
        try:
            src = (VAULT / rel).resolve()
            src.relative_to(VAULT)
        except (ValueError, OSError):
            return self._json(400, {"error": "path escapes vault"})
        if not src.exists() or not src.is_file() or src.suffix != ".md":
            return self._json(404, {"error": "file not found"})
        rel_parts = src.relative_to(VAULT).parts
        if not rel_parts or rel_parts[0] != "_trash":
            return self._json(400, {"error": "not in _trash"})
        # Read trashed_from from frontmatter; default to _unsorted if missing
        try:
            text = src.read_text(encoding="utf-8")
        except OSError as e:
            return self._json(500, {"error": str(e)})
        fm, _ = _parse_frontmatter_block(text)
        trashed_from = (fm or {}).get("trashed_from") or "_unsorted"
        target_dir = VAULT / trashed_from
        if trashed_from == "_trash" or not target_dir.is_dir():
            target_dir = VAULT / "_unsorted"
            target_dir.mkdir(exist_ok=True)
        # Strip trashed_from / trashed_at from frontmatter before moving back
        try:
            _strip_frontmatter_fields(src, ("trashed_from", "trashed_at"))
        except OSError as e:
            log(f"POST /restore 500 frontmatter-strip {rel} ({e})")
            return self._json(500, {"error": str(e)})
        # Destination with collision handling
        dst = target_dir / src.name
        if dst.exists():
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            dst = target_dir / f"{src.stem}-{ts}{src.suffix}"
            n = 1
            while dst.exists():
                n += 1
                dst = target_dir / f"{src.stem}-{ts}-{n}{src.suffix}"
        if not _git_mv(src, dst):
            log(f"POST /restore 500 {rel} (rename failed)")
            return self._json(500, {"error": "could not move file"})
        new_rel = str(dst.relative_to(VAULT))
        log(f"POST /restore 200 {rel} -> {new_rel}")
        return self._json(200, {"ok": True, "new_path": new_rel})

    def _handle_empty_trash(self, payload: dict) -> None:
        """Permanently delete every `.md` file in `_trash/`.

        Uses `git rm` when the file is tracked, falls back to plain `unlink`.
        Either way, the working-tree file is gone. Git history still preserves
        the content for any previously-committed file; the user can `git add -u
        && git commit` if they want the deletion reflected in vault history.

        Body: {} (no payload). Returns {ok, deleted, errors}.
        """
        trash = VAULT / "_trash"
        if not trash.is_dir():
            return self._json(200, {"ok": True, "deleted": 0, "errors": []})
        deleted = 0
        errors: list[dict] = []
        for p in sorted(trash.glob("*.md")):
            rel = str(p.relative_to(VAULT))
            try:
                # Try git rm first (stages the deletion). Fall back to unlink.
                try:
                    subprocess.run(
                        ["git", "-C", str(VAULT), "rm", "--quiet", "--force", rel],
                        check=True, capture_output=True,
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    p.unlink()
                deleted += 1
            except OSError as e:
                errors.append({"path": rel, "error": str(e)})
        log(f"POST /empty-trash 200 deleted={deleted} errors={len(errors)}")
        return self._json(200, {"ok": True, "deleted": deleted, "errors": errors})

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

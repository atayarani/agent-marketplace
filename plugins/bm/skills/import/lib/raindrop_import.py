#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "beautifulsoup4>=4.12",
# ]
# ///
"""Parse a Raindrop HTML export into the bm vault's _inbox/.

For each <A HREF=... ADD_DATE=... TAGS=...> in the Netscape Bookmark File,
write one inbox markdown file:

  $vault/_inbox/<YYYYMMDD-HHMMSS-from-captured>-<6id>.md

Frontmatter:
  url: <raw HREF>
  captured: <ISO 8601 with local TZ from ADD_DATE>
  source: import
  imported_tags: ["t1", "t2", ...]
  imported_collection: "<innermost H3 ancestor folder>"

Dedupe: a single rg pass builds a set of every existing `url:` value under
$vault/**/*.md before the write loop starts; URLs already present anywhere
in the vault (collection, inbox, failed, trash) are skipped.

Usage: raindrop_import.py <export.html> --vault <vault-path>

Output:
  stdout: imported: N, skipped: M (deduplicated)
  stderr: skip: <url> (already in vault)   — one line per skipped URL
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Generator

from bs4 import BeautifulSoup, Tag


def parse_tags_attr(tags_attr: str) -> list[str]:
    if not tags_attr:
        return []
    return [t.strip() for t in tags_attr.split(",") if t.strip()]


def captured_from_add_date(add_date: str | None) -> tuple[str, str]:
    """Return (filename_ts, iso_with_tz). Falls back to now() if missing/invalid.

    filename_ts is YYYYMMDD-HHMMSS for use in the inbox filename.
    iso_with_tz is the ISO 8601 string for the `captured:` frontmatter field.
    """
    try:
        ts = int(add_date or "")
    except ValueError:
        ts = int(datetime.now().timestamp())
    dt = datetime.fromtimestamp(ts).astimezone()
    return dt.strftime("%Y%m%d-%H%M%S"), dt.isoformat(timespec="seconds")


def build_url_set(vault: Path) -> set[str]:
    """Single rg pass: return the set of all existing `url:` values."""
    try:
        result = subprocess.run(
            ["rg", "-INo", r"^url: .+$", str(vault), "--type", "md"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    urls: set[str] = set()
    for line in result.stdout.splitlines():
        if line.startswith("url: "):
            urls.add(line[len("url: "):].strip())
    return urls


def walk_bookmarks(root: Tag) -> Generator[tuple[Tag, str], None, None]:
    """Walk the DOM in document order, yielding (anchor_tag, current_collection).

    Netscape Bookmark Format: each <H3> is followed by a sibling <DL> that
    contains the folder's contents. The algorithm: remember the most recent
    H3 text as `pending_h3`; when we enter the next <DL>, push that text
    onto the stack (and clear `pending_h3`); when that <DL> exits, pop.
    The collection of each <A> is the top of the stack at the time we
    encounter it (or "" if the stack is empty — root-level bookmark).
    """
    pending_h3: str | None = None
    stack: list[str] = []

    def walk(elem):
        nonlocal pending_h3
        if not isinstance(elem, Tag):
            return
        name = (elem.name or "").lower()
        if name == "h3":
            pending_h3 = elem.get_text(strip=True)
            return
        if name == "dl":
            pushed = pending_h3 is not None
            if pushed:
                stack.append(pending_h3)
                pending_h3 = None
            for child in elem.children:
                yield from walk(child)
            if pushed:
                stack.pop()
            return
        if name == "a":
            yield (elem, stack[-1] if stack else "")
            return
        for child in elem.children:
            yield from walk(child)

    yield from walk(root)


def yaml_dq(s: str) -> str:
    """Escape a string for inclusion in a double-quoted YAML scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_inbox(
    vault: Path,
    url: str,
    captured_iso: str,
    captured_ts: str,
    imported_tags: list[str],
    imported_collection: str,
) -> Path:
    six_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:6]
    target = vault / "_inbox" / f"{captured_ts}-{six_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    # If filename collides (same captured second + same 6id is extremely rare;
    # would require the same URL imported twice in the same second), append
    # a counter to disambiguate.
    n = 1
    while target.exists():
        target = vault / "_inbox" / f"{captured_ts}-{six_id}-{n}.md"
        n += 1

    tags_yaml = "[" + ", ".join(f'"{yaml_dq(t)}"' for t in imported_tags) + "]"
    content = (
        f"---\n"
        f"url: {url}\n"
        f"captured: {captured_iso}\n"
        f"source: import\n"
        f"imported_tags: {tags_yaml}\n"
        f'imported_collection: "{yaml_dq(imported_collection)}"\n'
        f"---\n"
    )
    target.write_text(content, encoding="utf-8")
    return target


def main() -> int:
    p = argparse.ArgumentParser(
        description="Parse a Raindrop HTML export into the bm vault's _inbox/.",
    )
    p.add_argument("export_path", help="path to the Raindrop HTML export")
    p.add_argument("--vault", required=True, help="path to the bm vault root")
    args = p.parse_args()

    export_path = Path(args.export_path)
    vault = Path(args.vault)

    if not export_path.is_file():
        print(f"error: file not found: {export_path}", file=sys.stderr)
        return 1
    if not vault.is_dir():
        print(f"error: vault not a directory: {vault}", file=sys.stderr)
        return 1

    existing_urls = build_url_set(vault)

    try:
        html = export_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html = export_path.read_bytes().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")

    imported = 0
    skipped = 0
    seen_this_run: set[str] = set()

    for anchor, collection in walk_bookmarks(soup):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        if href in existing_urls or href in seen_this_run:
            print(f"skip: {href} (already in vault)", file=sys.stderr)
            skipped += 1
            seen_this_run.add(href)
            continue
        add_date = anchor.get("add_date")
        tags_attr = anchor.get("tags") or ""
        captured_ts, captured_iso = captured_from_add_date(add_date)
        imported_tags = parse_tags_attr(tags_attr)
        write_inbox(
            vault, href, captured_iso, captured_ts, imported_tags, collection
        )
        seen_this_run.add(href)
        imported += 1

    print(f"imported: {imported}, skipped: {skipped} (deduplicated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

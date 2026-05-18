#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
#   "ruamel.yaml>=0.18",
# ]
# ///
"""One-off migration: move `blurb:` from frontmatter to body.

For each filed bookmark in the vault (collections + `_unsorted/` + `_broken/`):
  - If `blurb:` is present in frontmatter, extract it
  - Remove `blurb:` from frontmatter
  - Write the blurb into the body, above the `<!-- /llm-managed -->` marker
  - Preserve anything that was already in the body (treated as user notes)

Idempotent: files without `blurb:` in frontmatter are left untouched.

Usage:  migrate_blurb_to_body.py <vault> [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML


MARKER = "<!-- /llm-managed -->"
FRONTMATTER_RE = re.compile(r"^(---\n)(.*?\n)(---\n)(.*)", re.DOTALL)


def collect_bookmarks(vault: Path) -> list[Path]:
    """Filed bookmarks: every *.md file directly inside a user collection
    dir (any nesting depth), plus `_unsorted/` and `_broken/` flat sinks."""
    out: list[Path] = []
    for special in ("_unsorted", "_broken"):
        d = vault / special
        if d.is_dir():
            for p in d.glob("*.md"):
                if p.name != "README.md":
                    out.append(p)
    for readme in sorted(vault.rglob("README.md")):
        coll = readme.parent
        rel = coll.relative_to(vault)
        parts = rel.parts
        if not parts:
            continue
        top = parts[0]
        if top.startswith("_") or top == "outputs":
            continue
        for p in coll.glob("*.md"):
            if p.name != "README.md":
                out.append(p)
    return sorted(set(out))


def migrate_one(text: str) -> tuple[str | None, str]:
    """Return (new_text, status). status is one of: migrated, no-blurb, no-frontmatter, malformed."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, "no-frontmatter"

    open_marker, fm_block, close_marker, body = m.groups()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 9999  # don't wrap long quoted scalars
    yaml.indent(mapping=2, sequence=4, offset=2)
    try:
        fm = yaml.load(fm_block) or {}
    except Exception:
        return None, "malformed"

    if "blurb" not in fm:
        return None, "no-blurb"

    blurb = str(fm.pop("blurb") or "").strip()

    # Determine existing user notes in body
    existing_user_notes = ""
    if MARKER in body:
        _, _, after = body.partition(MARKER)
        existing_user_notes = after.lstrip("\n").rstrip()
    else:
        existing_user_notes = body.strip()

    # Re-emit frontmatter
    buf = io.StringIO()
    yaml.dump(fm, buf)
    new_fm = buf.getvalue()
    if not new_fm.endswith("\n"):
        new_fm += "\n"

    # Build new body
    body_parts = [blurb, MARKER]
    new_body = "\n\n".join(body_parts) + "\n"
    if existing_user_notes:
        new_body += "\n" + existing_user_notes + "\n"

    new_text = open_marker + new_fm + close_marker + "\n" + new_body
    return new_text, "migrated"


def main() -> int:
    p = argparse.ArgumentParser(prog="migrate_blurb_to_body.py")
    p.add_argument("vault")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1

    bookmarks = collect_bookmarks(vault)
    counts = {"migrated": 0, "no-blurb": 0, "no-frontmatter": 0, "malformed": 0}
    samples: dict[str, list[str]] = {k: [] for k in counts}

    for bm in bookmarks:
        try:
            text = bm.read_text(encoding="utf-8")
        except OSError as e:
            print(f"warning: could not read {bm}: {e}", file=sys.stderr)
            continue
        new_text, status = migrate_one(text)
        counts[status] += 1
        if len(samples[status]) < 3:
            samples[status].append(str(bm.relative_to(vault)))
        if status == "migrated" and new_text is not None:
            if args.dry_run:
                continue
            bm.write_text(new_text, encoding="utf-8")

    print(f"migrate_blurb_to_body: {len(bookmarks)} bookmarks scanned"
          + (" [DRY-RUN]" if args.dry_run else ""))
    for k in ("migrated", "no-blurb", "no-frontmatter", "malformed"):
        line = f"  {k:<16} {counts[k]}"
        if samples[k]:
            line += "   e.g. " + ", ".join(samples[k])
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

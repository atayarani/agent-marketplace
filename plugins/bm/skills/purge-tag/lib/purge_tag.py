#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "ruamel.yaml>=0.18",
# ]
# ///
"""Remove a tag from the bm vault — from every bookmark and from tags.yaml.

Scope:
  - filed bookmarks under user collections, `_unsorted/`, `_broken/`
      (rewrites `tags:` and `proposed_tags:`)
  - inbox files under `_inbox/`
      (rewrites `imported_tags:`)
  - `tags.yaml`
      (deletes the entry if `<tag>` is a `name:`; also drops `<tag>` from any
       OTHER entry's `aliases:` list so the alias doesn't redirect to a tag
       that no longer exists in bookmarks)

A bookmark that ends up with `tags: []` is left as-is — purging a tag isn't
a re-classification.

Usage:  purge_tag.py <vault> <tag> [--dry-run]
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML


FRONTMATTER_RE = re.compile(r"^(---\n)(.*?\n)(---\n)(.*)", re.DOTALL)


def yaml_rt() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 9999  # avoid wrapping long quoted scalars
    y.indent(mapping=2, sequence=4, offset=2)  # `  - name:` style for tags.yaml
    return y


def collect_filed_bookmarks(vault: Path) -> list[Path]:
    """Filed bookmarks: every *.md file directly inside a user collection
    dir (any depth, nested collections supported), plus `_unsorted/` and
    `_broken/` (flat staging sinks)."""
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


def collect_inbox(vault: Path) -> list[Path]:
    inbox = vault / "_inbox"
    if not inbox.is_dir():
        return []
    return [p for p in inbox.glob("*.md") if p.name != ".gitkeep"]


def mutate_bookmark(path: Path, tag: str, fields: tuple[str, ...]) -> bool:
    """Remove `tag` from each of `fields` (e.g. ('tags', 'proposed_tags')).
    Returns True if anything changed.
    """
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return False
    open_marker, fm_block, close_marker, body = m.groups()

    yaml = yaml_rt()
    try:
        fm = yaml.load(fm_block)
    except Exception:
        return False
    if fm is None:
        return False

    touched = False
    for field in fields:
        cur = fm.get(field)
        if not isinstance(cur, list):
            continue
        new = [t for t in cur if t != tag]
        if new != list(cur):
            # Mutate in place to preserve flow style
            cur.clear()
            cur.extend(new)
            touched = True

    if not touched:
        return False

    buf = io.StringIO()
    yaml.dump(fm, buf)
    path.write_text(open_marker + buf.getvalue() + close_marker + body, encoding="utf-8")
    return True


def update_tags_yaml(vault: Path, tag: str) -> tuple[bool, list[str]]:
    """Delete the `<tag>` entry; also drop `<tag>` from other entries' aliases.
    Returns (changed, notes).
    """
    path = vault / "tags.yaml"
    if not path.exists():
        return False, ["tags.yaml not found"]

    yaml = yaml_rt()
    try:
        doc = yaml.load(path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, [f"tags.yaml load error: {e}"]
    if not doc or "tags" not in doc or not isinstance(doc["tags"], list):
        return False, ["tags.yaml has no `tags:` list"]

    notes: list[str] = []
    changed = False

    # Step 1: delete the entry with name == tag
    keep = []
    deleted_entry = None
    for entry in doc["tags"]:
        if isinstance(entry, dict) and entry.get("name") == tag:
            deleted_entry = entry
            continue
        keep.append(entry)
    if deleted_entry is not None:
        doc["tags"].clear()
        doc["tags"].extend(keep)
        changed = True
        aliases = deleted_entry.get("aliases") or []
        if aliases:
            notes.append(f"deleted `{tag}` (with {len(aliases)} alias(es): {', '.join(aliases)})")
        else:
            notes.append(f"deleted `{tag}` from tags.yaml")

    # Step 2: drop `<tag>` from other entries' aliases
    alias_drops: list[str] = []
    for entry in doc["tags"]:
        if not isinstance(entry, dict):
            continue
        aliases = entry.get("aliases")
        if not isinstance(aliases, list):
            continue
        if tag in aliases:
            new_aliases = [a for a in aliases if a != tag]
            aliases.clear()
            aliases.extend(new_aliases)
            alias_drops.append(entry.get("name") or "?")
            changed = True
    if alias_drops:
        notes.append(f"removed `{tag}` from aliases of: {', '.join(alias_drops)}")

    if changed:
        buf = io.StringIO()
        yaml.dump(doc, buf)
        path.write_text(buf.getvalue(), encoding="utf-8")
    return changed, notes


def main() -> int:
    p = argparse.ArgumentParser(prog="purge_tag.py")
    p.add_argument("vault")
    p.add_argument("tag")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1
    tag = args.tag

    filed = collect_filed_bookmarks(vault)
    inbox = collect_inbox(vault)

    # First pass: find affected files without mutating
    affected_filed: list[Path] = []
    affected_inbox: list[Path] = []

    def has_tag(path: Path, fields: tuple[str, ...]) -> bool:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        m = FRONTMATTER_RE.match(text)
        if not m:
            return False
        # Lightweight check: regex the field lines. False positives are OK
        # since the actual mutation re-checks via YAML parsing.
        fm = m.group(2)
        for field in fields:
            # match flow list contents containing the tag
            for line in fm.splitlines():
                if line.startswith(f"{field}:"):
                    if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(tag)}(?![A-Za-z0-9_-])", line):
                        return True
        return False

    for p in filed:
        if has_tag(p, ("tags", "proposed_tags")):
            affected_filed.append(p)
    for p in inbox:
        if has_tag(p, ("imported_tags",)):
            affected_inbox.append(p)

    # tags.yaml planned changes (preview by re-parsing without writing)
    yaml_changes_preview: list[str] = []
    tags_yaml_path = vault / "tags.yaml"
    if tags_yaml_path.exists():
        try:
            doc = yaml_rt().load(tags_yaml_path.read_text(encoding="utf-8"))
            if doc and isinstance(doc.get("tags"), list):
                for entry in doc["tags"]:
                    if isinstance(entry, dict) and entry.get("name") == tag:
                        yaml_changes_preview.append(f"delete tags.yaml entry `{tag}`")
                        break
                for entry in doc["tags"]:
                    if isinstance(entry, dict) and isinstance(entry.get("aliases"), list):
                        if tag in entry["aliases"] and entry.get("name") != tag:
                            yaml_changes_preview.append(
                                f"drop `{tag}` from aliases of `{entry.get('name')}`"
                            )
        except Exception:
            pass

    total = len(affected_filed) + len(affected_inbox)
    print(f"# bm:purge-tag `{tag}`")
    print()
    print(f"Vault: `{vault}`")
    print()
    print(f"- Filed bookmarks affected:  **{len(affected_filed)}**")
    print(f"- Inbox files affected:      **{len(affected_inbox)}**")
    print(f"- tags.yaml changes:         **{len(yaml_changes_preview)}**")
    print()

    if total == 0 and not yaml_changes_preview:
        print(f"_No occurrences of `{tag}` found; nothing to do._")
        return 0

    def preview(label: str, paths: list[Path]) -> None:
        if not paths:
            return
        print(f"## {label}")
        print()
        for p in paths[:10]:
            print(f"- `{p.relative_to(vault)}`")
        if len(paths) > 10:
            print(f"- _(+{len(paths) - 10} more)_")
        print()

    preview("Filed bookmarks", affected_filed)
    preview("Inbox files", affected_inbox)
    if yaml_changes_preview:
        print("## `tags.yaml` changes")
        print()
        for c in yaml_changes_preview:
            print(f"- {c}")
        print()

    if args.dry_run:
        print("_(--dry-run: no changes written)_")
        return 0

    # Apply
    written_filed = 0
    for p in affected_filed:
        if mutate_bookmark(p, tag, ("tags", "proposed_tags")):
            written_filed += 1
    written_inbox = 0
    for p in affected_inbox:
        if mutate_bookmark(p, tag, ("imported_tags",)):
            written_inbox += 1

    yaml_changed, yaml_notes = update_tags_yaml(vault, tag)

    print("## Applied")
    print()
    print(f"- Filed bookmarks rewritten: **{written_filed}**")
    print(f"- Inbox files rewritten:     **{written_inbox}**")
    if yaml_changed:
        for n in yaml_notes:
            print(f"- {n}")
    elif yaml_notes:
        for n in yaml_notes:
            print(f"- _(skipped)_ {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

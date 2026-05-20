#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "ruamel.yaml>=0.18",
# ]
# ///
"""Rename a tag across the entire bm vault.

Scope:
  - filed bookmarks under user collections, `_unsorted/`, `_broken/`
      (rewrites `tags:` and `proposed_tags:`)
  - inbox files under `_inbox/`
      (rewrites `imported_tags:`)
  - `tags.yaml`
      (renames `<from>`'s `name:` if `<to>` doesn't yet exist; otherwise
       deletes `<from>`'s entry and appends `<from>` (plus its previous
       aliases) to `<to>`'s `aliases:` list — preserves discoverability
       across re-imports)

After rewriting a bookmark's tag list, duplicates are collapsed (preserving
order) so a bookmark that already had both `<from>` and `<to>` ends up with
just `<to>` once.

Usage:  rename_tag.py <vault> <from> <to> [--dry-run]
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
    y.width = 9999
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def collect_filed_bookmarks(vault: Path) -> list[Path]:
    """Every filed bookmark across user collections (any nesting depth) plus
    `_unsorted/` and `_broken/` flat sinks."""
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


def mutate_bookmark(path: Path, from_tag: str, to_tag: str, fields: tuple[str, ...]) -> bool:
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
        original = list(cur)
        # Rename + dedup (preserve first occurrence order)
        seen: set[str] = set()
        new = []
        for t in cur:
            mapped = to_tag if t == from_tag else t
            if mapped in seen:
                continue
            seen.add(mapped)
            new.append(mapped)
        if new != original:
            cur.clear()
            cur.extend(new)
            touched = True

    if not touched:
        return False

    buf = io.StringIO()
    yaml.dump(fm, buf)
    path.write_text(open_marker + buf.getvalue() + close_marker + body, encoding="utf-8")
    return True


def update_tags_yaml(vault: Path, from_tag: str, to_tag: str) -> tuple[bool, list[str]]:
    """Return (changed, notes)."""
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

    from_entry = None
    to_entry = None
    for entry in doc["tags"]:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == from_tag:
            from_entry = entry
        elif entry.get("name") == to_tag:
            to_entry = entry

    if from_entry is None:
        notes.append(f"`{from_tag}` is not a `name:` in tags.yaml; only bookmark references rewritten")
        return False, notes

    if to_entry is None:
        # Pure rename
        from_entry["name"] = to_tag
        changed = True
        notes.append(f"renamed `{from_tag}` → `{to_tag}` (description and aliases preserved)")
    else:
        # Merge: delete from_entry; append from_tag + its aliases to to_entry's aliases
        old_aliases = list(from_entry.get("aliases") or [])
        absorb = [from_tag] + old_aliases
        existing_aliases = to_entry.setdefault("aliases", [])
        if not isinstance(existing_aliases, list):
            existing_aliases = []
            to_entry["aliases"] = existing_aliases
        added = []
        for a in absorb:
            if a == to_tag:
                continue  # would be a self-alias
            if a not in existing_aliases:
                existing_aliases.append(a)
                added.append(a)
        # Drop from_entry
        new_list = [e for e in doc["tags"] if not (isinstance(e, dict) and e.get("name") == from_tag)]
        doc["tags"].clear()
        doc["tags"].extend(new_list)
        changed = True
        if added:
            notes.append(
                f"merged `{from_tag}` into `{to_tag}`; added to its aliases: {', '.join(added)}"
            )
        else:
            notes.append(f"merged `{from_tag}` into `{to_tag}` (aliases already up to date)")

    if changed:
        buf = io.StringIO()
        yaml.dump(doc, buf)
        path.write_text(buf.getvalue(), encoding="utf-8")
    return changed, notes


def main() -> int:
    p = argparse.ArgumentParser(prog="rename_tag.py")
    p.add_argument("vault")
    p.add_argument("from_tag", metavar="from")
    p.add_argument("to_tag", metavar="to")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.from_tag == args.to_tag:
        print(f"error: <from> and <to> are identical: '{args.from_tag}'", file=sys.stderr)
        return 1

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1

    filed = collect_filed_bookmarks(vault)
    inbox = collect_inbox(vault)

    def has_tag(path: Path, tag: str, fields: tuple[str, ...]) -> bool:
        # YAML-parse rather than line-regex: matches flow-style
        # `tags: [a, b]` AND block-style `tags:\n  - a\n  - b` uniformly.
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        m = FRONTMATTER_RE.match(text)
        if not m:
            return False
        try:
            fm = yaml_rt().load(m.group(2))
        except Exception:
            return False
        if not isinstance(fm, dict):
            return False
        for field in fields:
            cur = fm.get(field)
            if isinstance(cur, list) and any(str(t) == tag for t in cur):
                return True
        return False

    affected_filed = [p for p in filed if has_tag(p, args.from_tag, ("tags", "proposed_tags"))]
    affected_inbox = [p for p in inbox if has_tag(p, args.from_tag, ("imported_tags",))]

    # tags.yaml preview — yaml_changes are real mutations, yaml_notes are status only
    yaml_changes: list[str] = []
    yaml_notes: list[str] = []
    tags_yaml_path = vault / "tags.yaml"
    if tags_yaml_path.exists():
        try:
            doc = yaml_rt().load(tags_yaml_path.read_text(encoding="utf-8"))
            if doc and isinstance(doc.get("tags"), list):
                from_present = any(
                    isinstance(e, dict) and e.get("name") == args.from_tag for e in doc["tags"]
                )
                to_present = any(
                    isinstance(e, dict) and e.get("name") == args.to_tag for e in doc["tags"]
                )
                if from_present and to_present:
                    yaml_changes.append(
                        f"merge `{args.from_tag}` into `{args.to_tag}` (add to aliases)"
                    )
                elif from_present:
                    yaml_changes.append(
                        f"rename `{args.from_tag}` → `{args.to_tag}` in tags.yaml"
                    )
                else:
                    yaml_notes.append(
                        f"`{args.from_tag}` is not in tags.yaml; only bookmark references rewritten"
                    )
        except Exception:
            pass

    print(f"# bm:rename-tag `{args.from_tag}` → `{args.to_tag}`")
    print()
    print(f"Vault: `{vault}`")
    print()
    print(f"- Filed bookmarks affected: **{len(affected_filed)}**")
    print(f"- Inbox files affected:     **{len(affected_inbox)}**")
    print(f"- tags.yaml changes:        **{len(yaml_changes)}**")
    if yaml_notes:
        for n in yaml_notes:
            print(f"- _Note:_ {n}")
    print()

    if not affected_filed and not affected_inbox and not yaml_changes:
        print(f"_No occurrences of `{args.from_tag}` found; nothing to do._")
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
    if yaml_changes:
        print("## `tags.yaml` change")
        print()
        for c in yaml_changes:
            print(f"- {c}")
        print()

    if args.dry_run:
        print("_(--dry-run: no changes written)_")
        return 0

    written_filed = sum(
        1 for p in affected_filed
        if mutate_bookmark(p, args.from_tag, args.to_tag, ("tags", "proposed_tags"))
    )
    written_inbox = sum(
        1 for p in affected_inbox
        if mutate_bookmark(p, args.from_tag, args.to_tag, ("imported_tags",))
    )
    _, yaml_notes = update_tags_yaml(vault, args.from_tag, args.to_tag)

    print("## Applied")
    print()
    print(f"- Filed bookmarks rewritten: **{written_filed}**")
    print(f"- Inbox files rewritten:     **{written_inbox}**")
    for n in yaml_notes:
        print(f"- {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

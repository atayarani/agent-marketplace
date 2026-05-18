#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "ruamel.yaml>=0.18",
# ]
# ///
"""Merge collection `<from>` into `<to>`.

Moves every `<from>/*.md` (except README.md) into `<to>/`. On filename
collision, the moved file is renamed `<stem>-<6-char-sha1(url)><suffix>`,
cascading to `-N` if that also collides (matches audit_links.move_to_broken).

Then:
  - rewrites `imported_collection:` in `_inbox/*.md` where the value
    canonicalizes to `<from>` (so future enrichments file into `<to>`)
  - rewrites `proposed_collection.name` in filed bookmarks where it equals
    `<from>`
  - deletes `<from>/README.md` and `rmdir <from>`

Uses `git mv` when the vault is a git repo, falls back to `Path.rename`.

Usage:  merge_collection.py <vault> <from> <to> [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import subprocess
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


def canonicalize_collection(name: str) -> str:
    """Strip leading emoji/non-alnum then kebab-case (mirrors vocab_warmup.py)."""
    if name is None:
        return ""
    stripped = re.sub(r"^[^a-zA-Z0-9]+", "", str(name)).strip()
    return re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")[:60]


def short_url_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:6]


def collect_filed_bookmarks(vault: Path) -> list[Path]:
    out: list[Path] = []
    for child in sorted(vault.iterdir()):
        if not child.is_dir():
            continue
        if child.name in ("_unsorted", "_broken"):
            for p in child.glob("*.md"):
                if p.name != "README.md":
                    out.append(p)
            continue
        if child.name.startswith("_"):
            continue
        if child.name == "outputs":
            continue
        if not (child / "README.md").exists():
            continue
        for p in child.glob("*.md"):
            if p.name != "README.md":
                out.append(p)
    return out


def collect_inbox(vault: Path) -> list[Path]:
    inbox = vault / "_inbox"
    if not inbox.is_dir():
        return []
    return [p for p in inbox.glob("*.md") if p.name != ".gitkeep"]


def get_url(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return ""
    for line in m.group(2).splitlines():
        if line.startswith("url:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def plan_target(target_dir: Path, src: Path, url: str, taken: set[Path]) -> Path:
    """Compute final target path inside target_dir, handling collisions.

    Mirrors audit_links.move_to_broken's slug cascade.
    """
    target = target_dir / src.name
    if not target.exists() and target not in taken:
        return target
    stem, suffix = src.stem, src.suffix
    candidate = target_dir / f"{stem}-{short_url_hash(url)}{suffix}"
    n = 1
    while candidate.exists() or candidate in taken:
        n += 1
        candidate = target_dir / f"{stem}-{short_url_hash(url)}-{n}{suffix}"
    return candidate


def git_mv(vault: Path, src: Path, dst: Path) -> bool:
    """Try git mv; fall back to Path.rename. Returns True on success."""
    try:
        src_rel = src.relative_to(vault)
        dst_rel = dst.relative_to(vault)
    except ValueError:
        # paths not under vault — fall back
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            return True
        except OSError:
            return False
    try:
        subprocess.run(
            ["git", "-C", str(vault), "mv", str(src_rel), str(dst_rel)],
            check=True, capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            return True
        except OSError:
            return False


def rewrite_imported_collection(path: Path, from_canon: str, to_name: str) -> bool:
    """Rewrite `imported_collection:` if it canonicalizes to from_canon."""
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
    cur = fm.get("imported_collection")
    if cur is None:
        return False
    if canonicalize_collection(cur) != from_canon:
        return False
    fm["imported_collection"] = to_name
    buf = io.StringIO()
    yaml.dump(fm, buf)
    path.write_text(open_marker + buf.getvalue() + close_marker + body, encoding="utf-8")
    return True


def rewrite_proposed_collection(path: Path, from_name: str, to_name: str) -> bool:
    """Rewrite `proposed_collection.name` if it equals from_name."""
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
    pc = fm.get("proposed_collection")
    if not isinstance(pc, dict):
        return False
    if pc.get("name") != from_name:
        return False
    pc["name"] = to_name
    buf = io.StringIO()
    yaml.dump(fm, buf)
    path.write_text(open_marker + buf.getvalue() + close_marker + body, encoding="utf-8")
    return True


def main() -> int:
    p = argparse.ArgumentParser(prog="merge_collection.py")
    p.add_argument("vault")
    p.add_argument("from_dir", metavar="from")
    p.add_argument("to_dir", metavar="to")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.from_dir == args.to_dir:
        print(f"error: <from> and <to> are identical: '{args.from_dir}'", file=sys.stderr)
        return 1

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1

    src_dir = vault / args.from_dir
    dst_dir = vault / args.to_dir

    if not src_dir.is_dir():
        print(f"error: source collection not found: {src_dir}", file=sys.stderr)
        return 1
    if not (src_dir / "README.md").exists():
        print(f"error: '{src_dir.name}/' has no README.md — not recognized as a user collection", file=sys.stderr)
        return 1
    if not dst_dir.is_dir():
        print(
            f"error: destination collection not found: {dst_dir}\n"
            f"  hint: create it first with `mkdir {dst_dir} && printf '# ...\\n' > {dst_dir}/README.md`",
            file=sys.stderr,
        )
        return 1
    if not (dst_dir / "README.md").exists():
        print(f"error: '{dst_dir.name}/' has no README.md", file=sys.stderr)
        return 1

    # Plan the moves
    to_move = [p for p in sorted(src_dir.glob("*.md")) if p.name != "README.md"]
    taken: set[Path] = set()
    moves: list[tuple[Path, Path, str]] = []  # (src, dst, "plain" | "collision")
    for src in to_move:
        url = get_url(src)
        dst = plan_target(dst_dir, src, url, taken)
        taken.add(dst)
        kind = "collision" if dst.name != src.name else "plain"
        moves.append((src, dst, kind))

    # Plan inbox rewrites
    from_canon = canonicalize_collection(args.from_dir)
    inbox_affected: list[Path] = []
    for p in collect_inbox(vault):
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        for line in m.group(2).splitlines():
            if line.startswith("imported_collection:"):
                val = line.split(":", 1)[1].strip().strip("\"'")
                if canonicalize_collection(val) == from_canon:
                    inbox_affected.append(p)
                break

    # Plan proposed_collection rewrites
    proposed_affected: list[Path] = []
    for p in collect_filed_bookmarks(vault):
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        # quick predicate: look for proposed_collection block with name: from_dir
        if re.search(
            rf"^proposed_collection:\s*\n\s+name:\s+{re.escape(args.from_dir)}(\s|$)",
            m.group(2), re.MULTILINE,
        ):
            proposed_affected.append(p)

    # Report
    print(f"# bm:merge-collection `{args.from_dir}` → `{args.to_dir}`")
    print()
    print(f"Vault: `{vault}`")
    print()
    print(f"- Bookmarks to move:           **{len(moves)}**")
    print(f"  - plain moves:               **{sum(1 for _,_,k in moves if k == 'plain')}**")
    print(f"  - collision-suffixed moves:  **{sum(1 for _,_,k in moves if k == 'collision')}**")
    print(f"- Inbox `imported_collection` rewrites: **{len(inbox_affected)}**")
    print(f"- Filed `proposed_collection` rewrites: **{len(proposed_affected)}**")
    print()

    if moves:
        print("## Moves")
        print()
        for src, dst, kind in moves[:20]:
            tag = "  _(collision)_" if kind == "collision" else ""
            print(f"- `{src.relative_to(vault)}` → `{dst.relative_to(vault)}`{tag}")
        if len(moves) > 20:
            print(f"- _(+{len(moves) - 20} more)_")
        print()

    if inbox_affected:
        print("## Inbox rewrites")
        print()
        for p in inbox_affected[:10]:
            print(f"- `{p.relative_to(vault)}`")
        if len(inbox_affected) > 10:
            print(f"- _(+{len(inbox_affected) - 10} more)_")
        print()

    if proposed_affected:
        print("## proposed_collection rewrites")
        print()
        for p in proposed_affected[:10]:
            print(f"- `{p.relative_to(vault)}`")
        if len(proposed_affected) > 10:
            print(f"- _(+{len(proposed_affected) - 10} more)_")
        print()

    if args.dry_run:
        print("_(--dry-run: no changes written)_")
        return 0

    # Apply
    moved_count = 0
    for src, dst, _ in moves:
        if git_mv(vault, src, dst):
            moved_count += 1
        else:
            print(f"warning: could not move {src}", file=sys.stderr)

    inbox_rewritten = sum(
        1 for p in inbox_affected if rewrite_imported_collection(p, from_canon, args.to_dir)
    )
    proposed_rewritten = sum(
        1 for p in proposed_affected if rewrite_proposed_collection(p, args.from_dir, args.to_dir)
    )

    # Remove source dir
    readme_removed = False
    dir_removed = False
    src_readme = src_dir / "README.md"
    if src_readme.exists():
        try:
            # Use git rm if tracked
            try:
                subprocess.run(
                    ["git", "-C", str(vault), "rm", "--quiet", str(src_readme.relative_to(vault))],
                    check=True, capture_output=True,
                )
                readme_removed = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                src_readme.unlink()
                readme_removed = True
        except OSError as e:
            print(f"warning: could not remove {src_readme}: {e}", file=sys.stderr)
    try:
        src_dir.rmdir()
        dir_removed = True
    except OSError as e:
        print(f"warning: could not rmdir {src_dir} (likely contains unexpected files): {e}", file=sys.stderr)

    print("## Applied")
    print()
    print(f"- Bookmarks moved:              **{moved_count}**")
    print(f"- Inbox rewrites:               **{inbox_rewritten}**")
    print(f"- proposed_collection rewrites: **{proposed_rewritten}**")
    if readme_removed:
        print(f"- `{src_dir.name}/README.md` removed")
    if dir_removed:
        print(f"- `{src_dir.name}/` directory removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

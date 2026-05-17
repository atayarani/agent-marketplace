#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Audit bm vault collections: sparse + bloated detection, distribution overview.

Walks every top-level user collection (dir not starting with `_`, not `outputs/`,
containing a `README.md`), counts filed bookmarks (`*.md` excluding `README.md`),
parses frontmatter to gather tag distribution, and emits a markdown report to
stdout.

Usage:  audit_collections.py <vault> [--sparse-threshold N] [--bloat-threshold N]
                                     [--nest-cluster-min N]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None


def list_user_collections(vault: Path) -> list[Path]:
    out = []
    for child in sorted(vault.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):
            continue
        if child.name == "outputs":
            continue
        if not (child / "README.md").exists():
            continue
        out.append(child)
    return out


def count_bookmarks(coll: Path) -> list[Path]:
    return [p for p in coll.glob("*.md") if p.name != "README.md"]


def gather_tags(bookmarks: list[Path]) -> tuple[Counter, list[list[str]]]:
    counter: Counter = Counter()
    per_file: list[list[str]] = []
    for bm in bookmarks:
        fm = parse_frontmatter(bm)
        tags = (fm.get("tags") if fm else None) or []
        # YAML can return scalars in odd cases; coerce to list[str]
        tags = [str(t) for t in tags if t is not None]
        per_file.append(tags)
        counter.update(tags)
    return counter, per_file


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_(none)_\n"
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        cells = [str(c).replace("|", "\\|") for c in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def histogram(sizes: dict[str, int]) -> str:
    if not sizes:
        return "_(no collections)_\n"
    max_count = max(sizes.values())
    bar_width = 40
    rows = []
    for name in sorted(sizes, key=lambda k: sizes[k], reverse=True):
        n = sizes[name]
        bar_len = int(round(n / max_count * bar_width)) if max_count else 0
        bar = "█" * bar_len
        rows.append(f"`{name:<28}` {n:>4}  {bar}")
    return "```\n" + "\n".join(rows) + "\n```\n"


def main() -> int:
    p = argparse.ArgumentParser(prog="audit_collections.py")
    p.add_argument("vault")
    p.add_argument("--sparse-threshold", type=int, default=3,
                   help="collections with fewer than N bookmarks are 'sparse' (default 3)")
    p.add_argument("--bloat-threshold", type=int, default=50,
                   help="collections with more than N bookmarks are 'bloated' (default 50)")
    p.add_argument("--nest-cluster-min", type=int, default=10,
                   help="min bookmarks sharing a tag in a bloated collection to propose nesting (default 10)")
    args = p.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1

    collections = list_user_collections(vault)

    # First pass: gather per-collection data
    coll_data: dict[str, dict] = {}
    global_tag_to_colls: dict[str, Counter] = defaultdict(Counter)
    for coll in collections:
        bookmarks = count_bookmarks(coll)
        tag_counts, _ = gather_tags(bookmarks)
        coll_data[coll.name] = {
            "count": len(bookmarks),
            "tags": tag_counts,
        }
        for tag, n in tag_counts.items():
            global_tag_to_colls[tag][coll.name] += n

    total_bookmarks = sum(d["count"] for d in coll_data.values())
    sizes = {name: d["count"] for name, d in coll_data.items()}

    # Sparse analysis: propose merge target by dominant tag
    sparse_rows = []
    for name, d in sorted(coll_data.items(), key=lambda kv: kv[1]["count"]):
        if d["count"] >= args.sparse_threshold:
            continue
        # Dominant tag = most-used tag across this collection's bookmarks
        # (skip the tag matching the collection name itself if it equals)
        candidates = [(t, n) for t, n in d["tags"].most_common() if t != name]
        if not candidates:
            sparse_rows.append([
                f"`{name}/`", d["count"], "_(no tag signal)_", "—",
            ])
            continue
        dominant_tag, _ = candidates[0]
        # Find other collections where that tag is also strongly present
        targets = []
        for other_name, other_count in global_tag_to_colls[dominant_tag].most_common():
            if other_name == name:
                continue
            other_total = coll_data[other_name]["count"]
            if other_total == 0:
                continue
            share = other_count / other_total
            if share >= 0.25 and other_count >= 2:
                targets.append(f"`{other_name}/` ({other_count}/{other_total} share tag)")
            if len(targets) >= 3:
                break
        proposed = "; ".join(targets) if targets else "_(no strong target — consider `_unsorted/` or new collection)_"
        sparse_rows.append([f"`{name}/`", d["count"], proposed, f"`{dominant_tag}`"])

    # Bloated analysis: propose nestings by within-collection tag clusters
    bloated_rows = []
    for name, d in sorted(coll_data.items(), key=lambda kv: -kv[1]["count"]):
        if d["count"] <= args.bloat_threshold:
            continue
        # Top-3 within-collection tags meeting the cluster-min threshold,
        # excluding the collection name as a self-tag.
        clusters = [
            (t, n) for t, n in d["tags"].most_common()
            if t != name and n >= args.nest_cluster_min
        ][:3]
        if clusters:
            nest_proposals = "; ".join(
                f"`{name}/{tag}/` (~{n} bookmarks)" for tag, n in clusters
            )
        else:
            nest_proposals = f"_(no tag clusters of {args.nest_cluster_min}+ — manual split needed)_"
        bloated_rows.append([f"`{name}/`", d["count"], nest_proposals])

    # Emit markdown report to stdout
    today = date.today().isoformat()
    print(f"# bm:audit collections — {today}")
    print()
    print(f"Vault: `{vault}`")
    print()
    print(f"- Collections:      **{len(collections)}**")
    print(f"- Total bookmarks:  **{total_bookmarks}**")
    print(f"- Sparse (<{args.sparse_threshold}):       **{len(sparse_rows)}**")
    print(f"- Bloated (>{args.bloat_threshold}):     **{len(bloated_rows)}**")
    print()

    print(f"## Sparse collections (<{args.sparse_threshold} bookmarks)")
    print()
    print(md_table(
        ["Collection", "Count", "Proposed merge target", "Dominant tag"],
        sparse_rows,
    ))

    print(f"## Bloated collections (>{args.bloat_threshold} bookmarks)")
    print()
    print(md_table(
        ["Collection", "Count", "Proposed nestings"],
        bloated_rows,
    ))

    print("## Distribution overview")
    print()
    print(histogram(sizes))

    return 0


if __name__ == "__main__":
    sys.exit(main())

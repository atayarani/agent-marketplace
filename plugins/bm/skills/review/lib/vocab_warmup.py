#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Scan the bookmark vault for frequency-ranked imported_tags / imported_collection
values from inbox frontmatter, filter out values already present in tags.yaml or
existing collection dirs, and emit a JSON decision list to stdout.

Usage:  vocab_warmup.py --vault PATH [--min-count N] [--top N] [--include-filed]

Output schema (always all keys; lists may be empty):
  {
    "vault":             "/abs/path",
    "scan_count":        1775,
    "min_count":         2,
    "top":               50,
    "tag_candidates": [
      {"canonical": "imdb", "count": 105, "variants": ["IMDb"],
       "sample_urls": ["https://...", ...]},
      ...
    ],
    "collection_candidates": [
      {"original_name": "\U0001F916 AI & Agents", "dir_slug": "ai-agents",
       "count": 23, "sample_urls": ["https://...", ...]},
      ...
    ],
    "deferred_below_threshold": 142
  }

Exit codes: 0 on success, 2 on invalid args / missing vault.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NoReturn

import yaml

SAMPLE_URLS_CAP = 3
VARIANTS_CAP = 5


def die(msg: str, code: int = 2) -> NoReturn:
    print(f"vocab_warmup.py: {msg}", file=sys.stderr)
    sys.exit(code)


def canonicalize_tag(tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", tag.strip().lower()).strip("-")[:80]


def canonicalize_collection(name: str) -> str:
    stripped = re.sub(r"^[^a-zA-Z0-9]+", "", name).strip()
    return re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")[:60]


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def collect_files(vault: Path, include_filed: bool) -> list[Path]:
    files: list[Path] = []
    inbox = vault / "_inbox"
    if inbox.is_dir():
        files.extend(sorted(inbox.glob("*.md")))
    if include_filed:
        for entry in sorted(vault.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("_") or entry.name == ".git":
                continue
            files.extend(sorted(entry.glob("*.md")))
    return files


def load_known_tag_tokens(vault: Path) -> set[str]:
    tags_path = vault / "tags.yaml"
    known: set[str] = set()
    if not tags_path.is_file():
        return known
    try:
        data = yaml.safe_load(tags_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return known
    if not isinstance(data, dict):
        return known
    for entry in data.get("tags") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str):
            tok = canonicalize_tag(name)
            if tok:
                known.add(tok)
        for alias in entry.get("aliases") or []:
            if isinstance(alias, str):
                tok = canonicalize_tag(alias)
                if tok:
                    known.add(tok)
    return known


def load_existing_collection_slugs(vault: Path) -> set[str]:
    slugs: set[str] = set()
    for entry in vault.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith("_") or entry.name == ".git":
            continue
        slugs.add(entry.name)
    return slugs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Frequency-rank imported_tags / imported_collection values "
        "across the bookmark vault's inbox and emit a decision list as JSON.",
    )
    parser.add_argument("--vault", required=True)
    parser.add_argument("--min-count", type=int, default=2)
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--include-filed", action="store_true")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        die(f"vault not found: {vault}")

    files = collect_files(vault, args.include_filed)

    tag_counts: dict[str, int] = defaultdict(int)
    tag_variants: dict[str, set[str]] = defaultdict(set)
    tag_samples: dict[str, list[str]] = defaultdict(list)

    coll_counts: dict[str, int] = defaultdict(int)
    coll_original: dict[str, str] = {}
    coll_samples: dict[str, list[str]] = defaultdict(list)

    scan_count = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(text)
        if fm is None:
            continue
        scan_count += 1
        url = fm.get("url")
        url_str = url if isinstance(url, str) else ""

        imported_tags = fm.get("imported_tags")
        if isinstance(imported_tags, list):
            for raw in imported_tags:
                if not isinstance(raw, str):
                    continue
                stripped = raw.strip()
                if not stripped:
                    continue
                canon = canonicalize_tag(stripped)
                if not canon:
                    continue
                tag_counts[canon] += 1
                if stripped != canon:
                    tag_variants[canon].add(stripped)
                if url_str and len(tag_samples[canon]) < SAMPLE_URLS_CAP and url_str not in tag_samples[canon]:
                    tag_samples[canon].append(url_str)

        imported_coll = fm.get("imported_collection")
        if isinstance(imported_coll, str):
            original = imported_coll.strip()
            if original:
                slug = canonicalize_collection(original)
                if slug:
                    coll_counts[slug] += 1
                    coll_original.setdefault(slug, original)
                    if url_str and len(coll_samples[slug]) < SAMPLE_URLS_CAP and url_str not in coll_samples[slug]:
                        coll_samples[slug].append(url_str)

    known_tag_tokens = load_known_tag_tokens(vault)
    existing_coll_slugs = load_existing_collection_slugs(vault)

    tag_candidates_all = []
    for canon, count in tag_counts.items():
        if canon in known_tag_tokens:
            continue
        variants = sorted(tag_variants.get(canon, set()))
        # Drop candidates whose every variant is already a known token
        # (covers the case where the canonical form differs but all source
        #  strings are existing aliases).
        if variants and all(canonicalize_tag(v) in known_tag_tokens for v in variants):
            continue
        tag_candidates_all.append({
            "canonical": canon,
            "count": count,
            "variants": variants[:VARIANTS_CAP],
            "sample_urls": tag_samples.get(canon, []),
        })

    coll_candidates_all = []
    for slug, count in coll_counts.items():
        if slug in existing_coll_slugs:
            continue
        coll_candidates_all.append({
            "original_name": coll_original[slug],
            "dir_slug": slug,
            "count": count,
            "sample_urls": coll_samples.get(slug, []),
        })

    tag_candidates_all.sort(key=lambda c: (-c["count"], c["canonical"]))
    coll_candidates_all.sort(key=lambda c: (-c["count"], c["dir_slug"]))

    tag_above = [c for c in tag_candidates_all if c["count"] >= args.min_count]
    coll_above = [c for c in coll_candidates_all if c["count"] >= args.min_count]

    deferred = (
        (len(tag_candidates_all) - len(tag_above))
        + (len(coll_candidates_all) - len(coll_above))
    )

    out = {
        "vault": str(vault),
        "scan_count": scan_count,
        "min_count": args.min_count,
        "top": args.top,
        "tag_candidates": tag_above[: args.top],
        "collection_candidates": coll_above[: args.top],
        "deferred_below_threshold": deferred,
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

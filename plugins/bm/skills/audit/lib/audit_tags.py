#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Audit bm vault tags: frequency, rare, over-broad, ghost, and synonym candidates.

Two subcommands:

  analyze <vault> [flags]
      Walk filed bookmarks, parse frontmatter, tally tag use.
      Emit a single JSON document to stdout with rare / over_broad /
      synonym_candidates / ghosts / totals sections, plus an embedded
      `vocab` block (tags.yaml entries for each candidate tag) so the
      downstream LLM verdict pass has the context it needs.

  render <analysis.json> [--verdicts <verdicts.json>]
      Take the analyze output (and optional Sonnet verdict JSON) and emit
      a markdown report to stdout.

The split lets bm:audit/SKILL.md orchestrate the LLM verdict pass between
the two phases (or skip it via --skip-llm and call `render` directly).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


# ---------- shared helpers ----------

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


def collect_filed_bookmarks(vault: Path) -> list[Path]:
    """All filed bookmarks: <collection>/<slug>.md plus _unsorted/<slug>.md.

    Excludes README.md, .gitkeep, system dirs (_inbox/_failed/_trash/_broken/_proposals),
    and outputs/.
    """
    out: list[Path] = []
    for coll in list_user_collections(vault):
        for p in coll.glob("*.md"):
            if p.name != "README.md":
                out.append(p)
    unsorted = vault / "_unsorted"
    if unsorted.is_dir():
        for p in unsorted.glob("*.md"):
            if p.name != "README.md":
                out.append(p)
    return out


def load_vocab(vault: Path) -> dict[str, dict]:
    """Read tags.yaml and return {tag_name: {description, aliases}}."""
    path = vault / "tags.yaml"
    if not path.exists():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    out: dict[str, dict] = {}
    for entry in doc.get("tags") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        out[str(name)] = {
            "description": entry.get("description") or "",
            "aliases": [str(a) for a in (entry.get("aliases") or [])],
        }
    return out


# ---------- analyze ----------

def levenshtein(a: str, b: str) -> int:
    """Iterative Levenshtein distance — single-row DP, O(len(a) * len(b))."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            ins = curr[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            curr.append(min(ins, dele, sub))
        prev = curr
    return prev[-1]


def synonym_candidates(
    counter: Counter,
    levenshtein_max: int,
    min_count_each: int = 2,
) -> list[dict]:
    """Pairwise tag comparison; emit candidates by Levenshtein or containment."""
    tags = sorted(counter.keys())
    out = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(tags):
        if counter[a] < min_count_each:
            continue
        for b in tags[i + 1:]:
            if counter[b] < min_count_each:
                continue
            key = (a, b)
            if key in seen:
                continue
            dist = levenshtein(a, b)
            reason: str | None = None
            if dist <= levenshtein_max:
                reason = "levenshtein"
            elif len(a) >= 3 and len(b) >= 3 and (
                a in b or b in a
            ):
                # Containment (e.g., `git` ⊂ `git-tools`)
                reason = "containment"
            else:
                continue
            seen.add(key)
            out.append({
                "a": a,
                "b": b,
                "dist": dist,
                "reason": reason,
                "count_a": counter[a],
                "count_b": counter[b],
            })
    # Sort: containment first (most actionable), then by combined count desc
    out.sort(key=lambda r: (r["reason"] != "containment", -(r["count_a"] + r["count_b"])))
    return out


def cmd_analyze(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 1

    bookmarks = collect_filed_bookmarks(vault)
    counter: Counter = Counter()
    tag_to_files: dict[str, list[str]] = defaultdict(list)
    co_occur: dict[str, Counter] = defaultdict(Counter)

    for bm in bookmarks:
        fm = parse_frontmatter(bm) or {}
        tags = [str(t) for t in (fm.get("tags") or []) if t is not None]
        counter.update(tags)
        rel = str(bm.relative_to(vault))
        for t in tags:
            tag_to_files[t].append(rel)
            for u in tags:
                if u != t:
                    co_occur[t][u] += 1

    total_bookmarks = len(bookmarks)
    vocab = load_vocab(vault)

    rare = [
        {"tag": t, "count": counter[t], "files": tag_to_files[t]}
        for t in sorted(counter, key=lambda k: (counter[k], k))
        if counter[t] < args.rare_threshold
    ]

    broad_min = args.broad_pct * total_bookmarks if total_bookmarks else 0
    over_broad = []
    for t in sorted(counter, key=lambda k: -counter[k]):
        if total_bookmarks == 0:
            break
        if counter[t] <= broad_min:
            continue
        top_co = co_occur[t].most_common(5)
        over_broad.append({
            "tag": t,
            "count": counter[t],
            "pct": counter[t] / total_bookmarks,
            "top_co_occurring": [{"tag": u, "count": n} for u, n in top_co],
        })

    # Ghosts: used in bookmarks but not declared in tags.yaml
    ghosts = [
        {"tag": t, "count": counter[t], "files": tag_to_files[t]}
        for t in sorted(counter)
        if t not in vocab
    ]

    candidates = synonym_candidates(counter, args.levenshtein_max)

    # Attach vocab context to each candidate so the LLM has descriptions to reason with
    candidates_with_vocab = []
    for c in candidates:
        c_out = dict(c)
        c_out["vocab_a"] = vocab.get(c["a"], {})
        c_out["vocab_b"] = vocab.get(c["b"], {})
        candidates_with_vocab.append(c_out)

    out = {
        "vault": str(vault),
        "generated_at": date.today().isoformat(),
        "thresholds": {
            "rare_threshold": args.rare_threshold,
            "broad_pct": args.broad_pct,
            "levenshtein_max": args.levenshtein_max,
        },
        "totals": {
            "bookmarks": total_bookmarks,
            "tags_used": len(counter),
            "tags_declared": len(vocab),
            "rare_count": len(rare),
            "over_broad_count": len(over_broad),
            "ghost_count": len(ghosts),
            "synonym_candidate_count": len(candidates_with_vocab),
        },
        "rare": rare,
        "over_broad": over_broad,
        "ghosts": ghosts,
        "synonym_candidates": candidates_with_vocab,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


# ---------- render ----------

def md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_(none)_\n"
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in r]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def cmd_render(args: argparse.Namespace) -> int:
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    verdicts_by_pair: dict[tuple[str, str], dict] = {}
    if args.verdicts:
        try:
            verdicts = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"warning: could not read verdicts: {e}", file=sys.stderr)
            verdicts = []
        for v in verdicts or []:
            if not isinstance(v, dict):
                continue
            a, b = v.get("a"), v.get("b")
            if a is None or b is None:
                continue
            verdicts_by_pair[(str(a), str(b))] = v

    print(f"# bm:audit tags — {analysis.get('generated_at') or date.today().isoformat()}")
    print()
    print(f"Vault: `{analysis.get('vault')}`")
    print()
    t = analysis.get("totals") or {}
    th = analysis.get("thresholds") or {}
    print(f"- Bookmarks scanned:    **{t.get('bookmarks', 0)}**")
    print(f"- Tags used in vault:   **{t.get('tags_used', 0)}**")
    print(f"- Tags declared in `tags.yaml`: **{t.get('tags_declared', 0)}**")
    print(f"- Ghost tags (used but not declared): **{t.get('ghost_count', 0)}**")
    print(f"- Rare tags (<{th.get('rare_threshold')}): **{t.get('rare_count', 0)}**")
    print(f"- Over-broad tags (>{int(th.get('broad_pct', 0) * 100)}%): **{t.get('over_broad_count', 0)}**")
    print(f"- Synonym candidates (Levenshtein ≤ {th.get('levenshtein_max')} or containment): **{t.get('synonym_candidate_count', 0)}**")
    print()

    # ----- Synonym section -----
    print("## Synonym merges proposed")
    print()
    if verdicts_by_pair:
        merges = []
        distinct = []
        related = []
        unverdicted = []
        for c in analysis.get("synonym_candidates") or []:
            key = (c["a"], c["b"])
            v = verdicts_by_pair.get(key)
            if not v:
                unverdicted.append(c)
                continue
            verdict = (v.get("verdict") or "").lower()
            if verdict == "synonym":
                merges.append((c, v))
            elif verdict == "distinct":
                distinct.append((c, v))
            else:
                related.append((c, v))

        merge_rows = []
        for c, v in merges:
            canonical = v.get("canonical") or ""
            other = c["b"] if canonical == c["a"] else c["a"]
            other_count = c["count_b"] if canonical == c["a"] else c["count_a"]
            reason = v.get("reason") or ""
            merge_rows.append([
                f"`{other}`",
                f"`{canonical}`" if canonical else "_(no canonical chosen)_",
                reason,
                other_count,
            ])
        print(md_table(["From", "To", "Reason", "Affected files"], merge_rows))

        print("## Distinct (Levenshtein matched but semantically different)")
        print()
        distinct_rows = [
            [f"`{c['a']}`", f"`{c['b']}`", v.get("reason") or ""]
            for c, v in distinct
        ]
        print(md_table(["a", "b", "Reason"], distinct_rows))

        if related:
            print("## Related (overlap but not synonymous)")
            print()
            related_rows = [
                [f"`{c['a']}`", f"`{c['b']}`", v.get("reason") or ""]
                for c, v in related
            ]
            print(md_table(["a", "b", "Reason"], related_rows))

        if unverdicted:
            print(f"## Synonym candidates without verdicts ({len(unverdicted)})")
            print()
            print("These were not classified by the LLM (truncation, parsing error, etc.). Inspect manually.")
            print()
            rows = [
                [f"`{c['a']}`", f"`{c['b']}`", c["reason"], c["dist"], c["count_a"], c["count_b"]]
                for c in unverdicted
            ]
            print(md_table(["a", "b", "Reason", "Dist", "Count a", "Count b"], rows))
    else:
        # --skip-llm path: show raw candidates for manual review
        rows = [
            [
                f"`{c['a']}`",
                f"`{c['b']}`",
                c["reason"],
                c["dist"],
                c["count_a"],
                c["count_b"],
            ]
            for c in (analysis.get("synonym_candidates") or [])
        ]
        if rows:
            print("_LLM verdicts not provided — raw candidates listed for manual review._")
            print()
        print(md_table(
            ["a", "b", "Reason", "Dist", "Count a", "Count b"],
            rows,
        ))

    # ----- Rare -----
    print("## Rare tags")
    print()
    rare_rows = []
    for r in (analysis.get("rare") or []):
        files = r.get("files") or []
        sample = ", ".join(f"`{p}`" for p in files[:3])
        more = f" (+{len(files) - 3} more)" if len(files) > 3 else ""
        rare_rows.append([f"`{r['tag']}`", r["count"], sample + more])
    print(md_table(["Tag", "Count", "Files"], rare_rows))

    # ----- Over-broad -----
    print("## Over-broad tags")
    print()
    broad_rows = []
    for r in (analysis.get("over_broad") or []):
        co = ", ".join(
            f"`{c['tag']}` ({c['count']})"
            for c in (r.get("top_co_occurring") or [])
        )
        broad_rows.append([
            f"`{r['tag']}`",
            r["count"],
            f"{r['pct'] * 100:.1f}%",
            co or "_(none)_",
        ])
    print(md_table(["Tag", "Count", "Share", "Top co-occurring"], broad_rows))

    # ----- Ghosts -----
    print("## Ghost tags (used but not in `tags.yaml`)")
    print()
    print("Action: add to `tags.yaml` (if these are legitimate new tags) or retag the affected bookmarks.")
    print()
    ghost_rows = []
    for r in (analysis.get("ghosts") or []):
        files = r.get("files") or []
        sample = ", ".join(f"`{p}`" for p in files[:3])
        more = f" (+{len(files) - 3} more)" if len(files) > 3 else ""
        ghost_rows.append([f"`{r['tag']}`", r["count"], sample + more])
    print(md_table(["Tag", "Count", "Files"], ghost_rows))

    return 0


# ---------- entry point ----------

def main() -> int:
    p = argparse.ArgumentParser(prog="audit_tags.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("analyze", help="walk vault and emit JSON analysis to stdout")
    pa.add_argument("vault")
    pa.add_argument("--rare-threshold", type=int, default=3)
    pa.add_argument("--broad-pct", type=float, default=0.20)
    pa.add_argument("--levenshtein-max", type=int, default=2)
    pa.set_defaults(func=cmd_analyze)

    pr = sub.add_parser("render", help="read analysis JSON + optional verdicts and emit markdown")
    pr.add_argument("analysis", help="path to analysis JSON (from `analyze`)")
    pr.add_argument("--verdicts", help="optional path to LLM verdicts JSON", default=None)
    pr.set_defaults(func=cmd_render)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

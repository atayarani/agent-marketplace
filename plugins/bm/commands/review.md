---
description: "Review the enrichment backlog. With --vocab: batch-promote frequent imported_tags / imported_collection from the inbox to tags.yaml and collection dirs (pre-enrich warmup). Without --vocab: per-bookmark walker for needs_review:true files (post-enrich cleanup, Phase 2.B — not yet implemented). Use when the user types /bm:review or wants to resolve enrichment proposals."
argument-hint: "[--vocab] [--min-count N] [--top N] [--include-filed]"
---

Review the enrichment backlog. Two modes:

1. **`--vocab` (pre-enrich warmup, this phase)** — scans `_inbox/*.md` for frequency-ranked `imported_tags` and `imported_collection` hints (from Raindrop import). Presents them in chunks of 5 via `AskUserQuestion`; batch-accepts promote tags into `tags.yaml` and create collection dirs with `README.md`. Best run after `/bm:import` and **before** `/bm:enrich` drains the queue — pre-populating the vocab means most subsequent enrichments produce clean filings (no `needs_review: true`).

2. **Default (post-enrich walker, Phase 2.B)** — walks `needs_review: true` bookmarks one at a time. **Not yet implemented**; running `/bm:review` without `--vocab` prints a stub message and exits 0.

Use the `review` skill's `SKILL.md` for the full runbook. Brief steps for `--vocab`:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` whose first line contains "Bookmarks Vault". Fallback: `~/Documents/whiskers/`.
2. **Run `lib/vocab_warmup.py`** — scans frontmatter, frequency-ranks `imported_tags` (case-folded to kebab-case, original casings recorded as variants) and `imported_collection` (emoji-stripped → `dir_slug`), filters out values already in `tags.yaml` or existing dirs, emits a JSON decision list to stdout.
3. **Tags phase** — chunked `AskUserQuestion` prompts (5 candidates each, options: Accept all / Reject all / Pick individually / Skip remaining tags).
4. **Collections phase** — same shape over `collection_candidates`.
5. **Apply decisions** — plain-text append to `tags.yaml` (preserves existing flow-style aliases); `mkdir + README.md` per accepted collection (H1 preserves emoji).
6. **Summary** — tally `promoted / created / skipped / deferred below threshold`.

## Flags

- `--vocab` — run the pre-enrich warmup. Required in this phase (default mode is the Phase 2.B walker stub).
- `--min-count N` — frequency threshold (default 2). Lower to `1` to surface singletons (often typos or one-offs); raise to prune more aggressively.
- `--top N` — cap on candidates per category (default 50). Prevents drowning the user.
- `--include-filed` — also scan filed bookmarks under `<collection>/*.md` in addition to `_inbox/*.md`. No-op in practice today (filed bookmarks don't carry `imported_*` fields); reserved for future use.

## Do not

- Promote singleton tags by default — they're often typos. Use `--min-count 1` only when you want them surfaced.
- Commit anything to git — the user commits manually.
- Touch already-vocab-ed tags or already-existing collections — the scanner filters them out, and the apply step has a defensive check that won't overwrite an existing `README.md`.

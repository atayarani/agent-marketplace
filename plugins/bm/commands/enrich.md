---
description: "Process the bookmarks `_inbox/` queue: fetch + extract each URL, spawn the bm:enricher subagent, file the result into a collection. Idempotent. Use when the user types /bm:enrich, says 'process the bookmark inbox', 'enrich the bookmarks', or just captured a batch."
argument-hint: "[--limit N] [--failed] [--dry-run] [--force]"
---

Process the bookmark vault's `_inbox/` queue. For each file: fetch the URL with `extract.py`, spawn the `bm:enricher` subagent, file the result into `<collection>/<slug>.md`. Always picks a best-guess collection; marks `needs_review: true` when confidence is low or new vocabulary is proposed.

Use the `enrich` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` whose first line contains "Bookmarks Vault". Fallback: `~/Documents/whiskers/`.
2. **Build queue** — `_inbox/*.md` by default; with `--failed`, also include `_failed/fetch/*.md` and `_failed/llm/*.md`. Apply `--limit N` (default 10).
3. **For each file** — run `extract.py`, spawn `bm:enricher`, parse JSON (tolerating ```` ```json ```` fences), file the bookmark.
4. **Summary** — tally filed / needs_review / fetch-failed / llm-failed / bootstrap-held.

## Flags

- `--limit N` — cap queue size (default 10). Run repeatedly to drain larger backlogs (host-LLM context grows ~500 tokens per subagent return; iteration is cheaper than one mega-run).
- `--failed` — also process files in `_failed/fetch/` and `_failed/llm/`.
- `--dry-run` — print what would be written/moved; no side effects.
- `--force` — accepted but no-op in v1 (reserved).

## Do not

- Normalize URLs (store verbatim).
- Commit anything to git — the user commits manually.
- Write to the body of a filed bookmark — that's the user's notes area.
- Skip the `needs_review` frontmatter field when the enricher returns low confidence or proposed vocabulary.

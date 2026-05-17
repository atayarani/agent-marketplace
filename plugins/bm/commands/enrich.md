---
description: "Process the bookmarks `_inbox/` queue: fetch + extract each URL, spawn the bm:enricher subagent, file the result into a collection. Prompts inline (AskUserQuestion) when the enricher proposes a brand-new collection — pass --no-prompt to skip. Idempotent. Use when the user types /bm:enrich, says 'process the bookmark inbox', 'enrich the bookmarks', or just captured a batch."
argument-hint: "[--limit N] [--failed] [--dry-run] [--no-prompt] [--force] [--commit]"
---

Process the bookmark vault's `_inbox/` queue. For each file: fetch the URL with `extract.py`, spawn the `bm:enricher` subagent, file the result into `<collection>/<slug>.md`. Always picks a best-guess collection; marks `needs_review: true` when confidence is low or new vocabulary is proposed. When the enricher proposes a *brand-new* collection, prompts the user inline (`AskUserQuestion`) before filing — unless `--no-prompt` is passed.

Use the `enrich` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` whose first line contains "Bookmarks Vault". Fallbacks (first match wins): `$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`.
2. **Build queue** — `_inbox/*.md` by default; with `--failed`, also include `_failed/fetch/*.md` and `_failed/llm/*.md`. Apply `--limit N` (default 10).
3. **For each file** — run `extract.py`, spawn `bm:enricher`, parse JSON (tolerating ```` ```json ```` fences), resolve any brand-new `proposed_collection` (auto-reroute if it exists; ask user otherwise), file the bookmark.
4. **Summary** — tally `filed / needs_review / deferred / fetch-failed / llm-failed`.

## Flags

- `--limit N` — cap queue size (default 10). Run repeatedly to drain larger backlogs (host-LLM context grows ~500 tokens per subagent return; iteration is cheaper than one mega-run).
- `--failed` — also process files in `_failed/fetch/` and `_failed/llm/`.
- `--dry-run` — print what would be written/moved; no side effects. Implies `--no-prompt`.
- `--no-prompt` — skip the interactive "create new collection?" prompt when the enricher proposes a brand-new collection. Pre-v0.3.0 behavior: file to the under-protest existing collection with `needs_review: true`. Use for batch flows (`/bm:import` from Phase 1.D) where prompts would be tedious.
- `--force` — accepted but no-op in v1 (reserved).
- `--commit` — after a successful run, auto-commit the changed files with a templated message summarizing the run (`filed`, `needs_review`, `deferred`, `fetch-failed`, `llm-failed`). Refuses to commit if the vault has pre-existing staged changes (you can stage them yourself first, run without --commit, or unstage them).

## Do not

- Normalize URLs (store verbatim).
- Commit anything to git unless `--commit` is passed.
- Write to the body of a filed bookmark — that's the user's notes area.
- Skip the `needs_review` frontmatter field when the enricher returns low confidence or proposed vocabulary.

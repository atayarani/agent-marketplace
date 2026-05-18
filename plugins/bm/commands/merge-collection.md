---
description: "Merge collection `<from>` into `<to>`. Moves every bookmark via `git mv` (collision-suffixed on duplicate filenames), rewrites `imported_collection:` in inbox and `proposed_collection.name:` in filed bookmarks, then deletes `<from>/`. Use when the user types /bm:merge-collection or wants to consolidate two collection directories."
argument-hint: "<from> <to> [--dry-run] [--commit]"
---

Merge collection `<from>` into `<to>`. Cleans up old vocabulary directories in one shot.

Use the `merge-collection` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk-up + fallbacks.
2. **Parse args** — positional `<from>` and `<to>` required. Same arg → usage error.
3. **Run `lib/merge_collection.py`** — validates both dirs exist with READMEs, plans moves with collision suffixes, prints the plan; if not `--dry-run`, applies via `git mv` and removes the source dir.
4. **Print report** — moves (with collision flags), inbox rewrites, proposed_collection rewrites; then either dry-run notice or `## Applied` summary.

## What gets moved/rewritten

| Touched | Notes |
|---|---|
| `<from>/*.md` (excluding README.md) | `git mv` to `<to>/`. Collisions get `-<6-char-sha1(url)>` suffix. |
| `_inbox/*.md` `imported_collection:` | Rewritten to `<to>` when the value canonicalizes to `<from>` (emoji strip + kebab). |
| Filed bookmarks `proposed_collection.name:` | Rewritten to `<to>` when it equals `<from>`. Description preserved. |
| `<from>/README.md` | Deleted (use `git log` to recover the old description if you want to merge it). |
| `<from>/` directory | `rmdir`'d. Fails loudly if non-README files remain. |

## Flags

- `--dry-run` — print the plan (moves with collision flags, rewrite counts) and exit without writing.
- `--commit` — after a successful real run, auto-commit with message `bm:merge-collection: <from> → <to> (N bookmarks moved)`. Refuses to commit if the vault has pre-existing staged changes.

## Examples

- `/bm:merge-collection collection-a collection-b --dry-run` — preview.
- `/bm:merge-collection entertainment imdb-career` — actually consolidate (per the audit's "23 of 24 are imdb-tagged" finding).
- `/bm:merge-collection adult-gaming gaming --commit` — apply + commit.

## Notes

- **Destination must exist.** No auto-create — that's a different operation. Error message includes the `mkdir + README.md` hint.
- **Idempotency via error.** Re-running on an already-merged pair exits 1 with "source collection not found". This is deliberate: silent no-op would mask a typo.
- **Symbolic-link safe.** Uses `git mv` if available, plain `Path.rename` otherwise.
- **Companion to `/bm:rename-tag` and `/bm:purge-tag`** — vocabulary maintenance trio.

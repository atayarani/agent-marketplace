---
description: "Remove a tag from the bm vault entirely — every `tags:` / `proposed_tags:` / `imported_tags:` reference, plus its `tags.yaml` entry (and any aliases referencing it from other entries). Use after `/bm:audit tags` flags a tag as rare or noise. Idempotent. Use when the user types /bm:purge-tag or wants to kill a bad tag everywhere."
argument-hint: "<tag> [--dry-run] [--commit]"
---

Bulk-remove a tag from the bm vault — every reference, plus the `tags.yaml` entry. Idempotent.

Use the `purge-tag` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` titled "Bookmarks Vault". Fallbacks: `$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`.
2. **Parse args** — positional `<tag>` is required.
3. **Run `lib/purge_tag.py`** — walks filed bookmarks + inbox, mutates `tags:` / `proposed_tags:` / `imported_tags:` via ruamel.yaml round-trip, deletes the `tags.yaml` entry and removes the tag from any other entry's aliases.
4. **Print report** — affected file count + first 10 paths, planned `tags.yaml` changes, then either dry-run notice or `## Applied` summary.

## Scope

| Touched | Not touched |
|---|---|
| `<collection>/*.md` (`tags:`, `proposed_tags:`) | `_trash/`, `_failed/` |
| `_unsorted/*.md` (`tags:`, `proposed_tags:`) | bookmark bodies |
| `_broken/*.md` (`tags:`, `proposed_tags:`) | |
| `_inbox/*.md` (`imported_tags:`) | |
| `tags.yaml` (entry + cross-references in aliases) | |

A bookmark that ends up with `tags: []` is left as-is — purging a tag isn't a re-classification. If you wanted that, you'd retag it.

## Flags

- `--dry-run` — print the report (affected counts + first 10 paths + planned tags.yaml changes) and exit without writing.
- `--commit` — after a successful real run, auto-commit the touched files with message `bm:purge-tag: <tag> (N files touched)`. Refuses to commit if the vault has pre-existing staged changes.

## Examples

- `/bm:purge-tag noisy-tag-xyz --dry-run` — see what would change.
- `/bm:purge-tag noisy-tag-xyz` — apply.
- `/bm:purge-tag noisy-tag-xyz --commit` — apply + commit.

## Notes

- **Idempotent.** Re-running with a tag that's already gone exits 0 with `_No occurrences of '<tag>' found; nothing to do._`.
- **Sibling to `/bm:rename-tag`.** If you want to redirect a tag rather than delete it, use rename-tag — it preserves the old name as an alias on the canonical entry.
- **Aliases of other entries.** If `<tag>` is listed as an alias under some OTHER `tags.yaml` entry, it gets pulled from that aliases list too — the alias would otherwise redirect the LLM to a tag that no longer exists in any bookmark.

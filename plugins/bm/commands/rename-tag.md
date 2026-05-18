---
description: "Rename a tag everywhere in the bm vault — `tags:` / `proposed_tags:` / `imported_tags:` references, plus the `tags.yaml` entry. If the new name already exists, merges the old name into the new entry's aliases. Idempotent. Use when the user types /bm:rename-tag or wants to consolidate a synonym."
argument-hint: "<from> <to> [--dry-run] [--commit]"
---

Rename a tag across the entire vault. Bookmark references and `tags.yaml` both updated in one pass. Idempotent.

Use the `rename-tag` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` titled "Bookmarks Vault". Fallbacks: `$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`.
2. **Parse args** — positional `<from>` and `<to>` are required. `<from> == <to>` is a usage error.
3. **Run `lib/rename_tag.py`** — walks filed bookmarks + inbox, mutates `tags:` / `proposed_tags:` / `imported_tags:` via ruamel.yaml. Updates `tags.yaml` (rename if `<to>` doesn't exist, merge into aliases if it does).
4. **Print report** — affected file count + first 10 paths, the planned tags.yaml change, then either dry-run notice or `## Applied` summary.

## Scope

| Touched | Not touched |
|---|---|
| `<collection>/*.md` (`tags:`, `proposed_tags:`) | `_trash/`, `_failed/` |
| `_unsorted/*.md` (`tags:`, `proposed_tags:`) | bookmark bodies |
| `_broken/*.md` (`tags:`, `proposed_tags:`) | |
| `_inbox/*.md` (`imported_tags:`) | |
| `tags.yaml` (rename entry OR absorb into `<to>`'s aliases) | |

A bookmark that already had both `<from>` and `<to>` gets deduplicated to a single `<to>` (preserving order).

## tags.yaml behaviour

| State | What happens |
|---|---|
| `<from>` exists, `<to>` does NOT | Rename `<from>`'s `name:` to `<to>`. Description and aliases preserved. |
| `<from>` exists, `<to>` also exists | Delete `<from>`'s entry. Append `<from>` + its previous aliases to `<to>`'s `aliases:`, dedup. Preserves Raindrop-import discoverability. |
| `<from>` not in `tags.yaml` (e.g. ghost tag) | Bookmark references still rewritten; `tags.yaml` untouched. Surfaced as a `_Note:_` line in the report. |

## Flags

- `--dry-run` — print the report and exit without writing.
- `--commit` — after a successful real run, auto-commit with message `bm:rename-tag: <from> → <to> (N files touched)`. Refuses to commit if the vault has pre-existing staged changes.

## Examples

- `/bm:rename-tag 3d-printing 3dprinting --dry-run` — preview the merge that `/bm:audit tags` proposed.
- `/bm:rename-tag 3d-printing 3dprinting --commit` — apply + commit.
- `/bm:rename-tag old-name new-name` — pure rename when `new-name` isn't in `tags.yaml`.

## Notes

- **Idempotent.** Re-running with a `<from>` that no longer exists prints `_No occurrences of '<from>' found; nothing to do._`.
- **Sibling to `/bm:purge-tag`.** If you want to remove rather than redirect, use purge-tag.
- **Bookmarks with both tags dedup.** This is the right thing to do for synonyms; if you have intentional duplicates somehow, sort that out beforehand.

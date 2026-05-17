---
description: "Import a Raindrop HTML export into the bm vault. Parses Netscape Bookmark File format, writes one inbox file per bookmark with imported_tags + imported_collection hints. Does NOT auto-enrich. Use when the user types /bm:import or wants to migrate a Raindrop backup."
argument-hint: "<path-to-raindrop-export.html>"
---

Parse a Raindrop HTML export (Netscape Bookmark File Format) and populate the bm vault's `_inbox/` with one file per `<A>` entry. Each imported bookmark carries `imported_tags` (from the bookmark's `TAGS=` attribute) and `imported_collection` (from the innermost `<H3>` ancestor folder) as carry-through hints for the downstream `/bm:enrich`.

Use the `import` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` titled "Bookmarks Vault". Fallbacks (first match wins): `$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`.
2. **Validate the export path** — file exists, `.html` or `.htm` extension.
3. **Run the parser** — `raindrop_import.py <export-path> --vault $vault`.
4. **Surface the summary** — `imported: N, skipped: M (deduplicated)`. Suggest `/bm:enrich --limit 20 --no-prompt` to start enrichment of the first batch.

## Notes

- **Raindrop HTML only**. Pocket, CSV, and JSON exports are not supported.
- **Dedup by URL** — re-running on the same export is safe; already-vaulted URLs are skipped, not duplicated.
- **No auto-enrich** — a few-thousand-bookmark import enriched in one go would block. The user batches at their own pace with `/bm:enrich --limit N --no-prompt`.

## Do not

- Auto-trigger `/bm:enrich` after import.
- Normalize URLs.
- Commit to git.

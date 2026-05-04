---
description: Backfill author + source URL + blurb on `lists/media/books/items/*.md` from public book APIs (Open Library, Wikipedia, Hardcover, Google Books). Idempotent and non-destructive.
argument-hint: "[--limit N] [--items GLOB] [--sources hardcover,openlibrary,wikipedia,googlebooks] [--status any|tbr|reading|read|...] [--reset] [--dry-run]"
---

Enrich the user's TBR (or other-status) book items with author, publication year, source URL, and a `## Blurb` description. The skill ships a script at `${CLAUDE_PLUGIN_ROOT}/skills/book-enrichment/enrich_books.py` that does the work. Use the `book-enrichment` skill's SKILL.md for full reference.

## Steps

1. **Verify prerequisites**:
   - `command -v uv` exists. If not, ask the user to install `uv` and stop.
   - The vault is initialized (`AGENTS.md` is reachable at the wiki root). If not, suggest `/wiki_keeper:init`.
   - Optional: surface whether `HARDCOVER_TOKEN` is set in the environment. If not, mention that Hardcover (the highest-quality fiction descriptions) will be skipped — and tell the user how to set it: get a token from `https://hardcover.app/account/api`, then `export HARDCOVER_TOKEN=<value>` in their shell.

2. **Run the script** at `${CLAUDE_PLUGIN_ROOT:-.}/skills/book-enrichment/enrich_books.py` with `$ARGUMENTS` passed through. The script auto-detects the vault root by walking up from `$PWD` looking for `AGENTS.md`.

3. **Surface the summary** the script prints to stdout: per-status counts (enriched-via-hardcover, enriched-via-openlibrary, enriched-via-wikipedia, enriched-via-googlebooks, ambiguous-*, skip-*).

4. **Spot-check 1–2 enriched items** with the user — read back a sample to confirm the blurb quality and check the author was assigned correctly. Books with very generic or numeric titles (`19 Minutes`, `1984`, `Zero`) and books with adaptations (graphic novels, abridgments) are the most common mis-match cases.

5. **Point at the log file** the script wrote (`<vault>/system/enrich-books-<YYYY-MM-DD>.log`). The log lists ambiguous matches the script declined to apply — those are candidates for manual lookup.

## Sensible default invocation

If `$ARGUMENTS` is empty, run with no extra flags. The script's defaults are: enrich all `tbr` items in `lists/media/books/items/`, try sources in order hardcover → openlibrary → wikipedia → googlebooks, skip items with an existing `## Blurb` section.

## Test runs

If you want to validate before a full run, suggest the user pass `--limit 10 --dry-run` first. That hits each source, logs match decisions, and writes nothing.

## Re-running

The script is idempotent — on a second run it skips items that already have a `## Blurb` section. To force re-enrichment of specific items (e.g., after adding a Hardcover token where prior runs only had Open Library + Wikipedia available), pass `--reset --items 'glob-pattern'`. **Never pass `--reset` without an `--items` filter** — that wipes blurbs across the entire TBR before re-fetching.

## Do not

- Pass any API tokens on the command line — they'd appear in the process list and shell history. Tokens are read from environment variables only.
- Edit `sources/raw/` or other immutable layers. The script writes only into `lists/media/books/items/`.
- Promote books to `wiki/entities/books/` automatically. Promotion stays on-demand per `AGENTS.md` rule 16; the user creates entity pages when a book actually warrants one.
- Bulk-overwrite existing frontmatter values. The script only fills empty fields — existing `creator`, `source_url`, `published`, etc. are preserved.

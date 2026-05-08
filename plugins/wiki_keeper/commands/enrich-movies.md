---
description: Backfill director + source URL + blurb on `lists/media/movies/items/*.md` from public movie APIs (TMDB, Wikipedia, OMDB). Idempotent and non-destructive.
argument-hint: "[--limit N] [--items GLOB] [--sources tmdb,wikipedia,omdb] [--status any|to-watch|watched|watching|abandoned] [--reset] [--dry-run]"
---

Enrich the user's to-watch (or other-status) movie items with director, release year, source URL, and a `## Blurb` description. The skill ships a script at `${CLAUDE_PLUGIN_ROOT}/skills/movie-enrichment/enrich_movies.py` that does the work. Use the `movie-enrichment` skill's SKILL.md for full reference.

## Steps

1. **Verify prerequisites**:
   - `command -v uv` exists. If not, ask the user to install `uv` and stop.
   - The vault is initialized (`AGENTS.md` is reachable at the wiki root). If not, suggest `/wiki_keeper:init`.
   - Optional: surface whether `TMDB_BEARER` / `TMDB_API_KEY` / `OMDB_API_KEY` are set in the environment. If TMDB credentials aren't set, mention that TMDB (the highest-quality contemporary coverage) will be skipped — and tell the user how to set it: get a v4 read-access token from `https://www.themoviedb.org/settings/api`, then `export TMDB_BEARER=<token>` in their shell.

2. **Run the script** at `${CLAUDE_PLUGIN_ROOT:-.}/skills/movie-enrichment/enrich_movies.py` with `$ARGUMENTS` passed through. The script auto-detects the vault root by walking up from `$PWD` looking for `AGENTS.md`.

3. **Surface the summary** the script prints to stdout: per-status counts (enriched-via-tmdb, enriched-via-wikipedia, enriched-via-omdb, ambiguous-*, skip-*).

4. **Spot-check 1–2 enriched items** with the user — read back a sample to confirm the blurb quality and check the director was assigned correctly. Films with very generic titles (*Apostle*, *Cure*, *Hunger*) and remake-heavy titles (*Frankenstein*, *The Wicker Man*) are the most common mis-match cases. **Year mismatch is the most common single error** — verify the year on a few items, especially ones without `published:` set in frontmatter.

5. **Point at the log file** the script wrote (`<vault>/system/enrich-movies-<YYYY-MM-DD>.log`). The log lists ambiguous matches the script declined to apply — those are candidates for manual lookup.

## Sensible default invocation

If `$ARGUMENTS` is empty, run with no extra flags. The script's defaults are: enrich all `to-watch` items in `lists/media/movies/items/`, try sources in order tmdb → wikipedia → omdb, skip items with an existing `## Blurb` section.

## Test runs

If you want to validate before a full run, suggest the user pass `--limit 10 --dry-run` first. That hits each source, logs match decisions, and writes nothing.

## Re-running

The script is idempotent — on a second run it skips items that already have a `## Blurb` section. To force re-enrichment of specific items (e.g., after adding a TMDB token where prior runs only had Wikipedia available), pass `--reset --items 'glob-pattern'`. **Never pass `--reset` without an `--items` filter** — that wipes blurbs across the entire to-watch list before re-fetching.

## Year-disambiguation

Films are far more remake-prone than books. The script uses the `published:` frontmatter year (when set) to narrow searches and boost matching candidates. **Pre-populating `published:` for known-year items before running enrichment substantially reduces ambiguous matches** — particularly for canonical titles with remakes (e.g., *The Wicker Man* 1973 vs. 2006, *Cape Fear* 1962 vs. 1991).

## Do not

- Pass any API tokens on the command line — they'd appear in the process list and shell history. Tokens are read from environment variables only.
- Edit `sources/raw/` or other immutable layers. The script writes only into `lists/media/movies/items/`.
- Promote movies to `wiki/entities/movies/` automatically. Promotion stays on-demand per `AGENTS.md` rule 16; the user creates entity pages when a film actually warrants one. (Note: not every wiki_keeper vault has `wiki/entities/movies/` — check the project's `system/schemas/repository-model.md` first.)
- Bulk-overwrite existing frontmatter values. The script only fills empty fields — existing `creator`, `source_url`, `published`, etc. are preserved.

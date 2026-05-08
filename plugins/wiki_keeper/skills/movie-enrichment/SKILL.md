---
name: movie-enrichment
description: Backfill missing metadata + descriptions for `lists/media/movies/items/*.md` files in a wiki_keeper-managed vault, using public movie APIs (TMDB, Wikipedia, OMDB). Idempotent and non-destructive — only fills empty frontmatter fields and appends a `## Blurb` section.
---

You can flesh out the user's to-watch (and other status) movie items with director, release year, source URL, and a short description blurb sourced from public APIs. The skill ships a Python script that's safe to re-run — items already carrying a `## Blurb` section are skipped, and existing frontmatter values are preserved.

This is the movies counterpart to the [`book-enrichment`](../book-enrichment/SKILL.md) skill — same idempotency model, same file-shape contract, same pacing and ambiguity logging.

## When to use this

- The user has a populated `lists/media/movies/items/` whose entries are mostly bare title-only stubs and they want enough metadata to triage what to watch next.
- The user has imported movies from a list (Letterboxd export, Recall import, hand-typed list) and directors / blurbs weren't captured.
- A movie item has a thin or missing `creator:` field (director) and the user wants it filled.
- The user wants to refresh blurbs after adding a new source (e.g., signing up for TMDB after the initial pass).

## Prerequisite check

`uv` must be available — the script self-bootstraps via PEP 723 inline metadata. If `command -v uv` fails, tell the user and stop.

The script will work with no API keys if the user is willing to accept Wikipedia-only coverage (which works well for famous / canonical films but thin elsewhere). For deeper coverage, two optional credentials:

- **`TMDB_BEARER`** (preferred) — v4 read-access token from [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Free signup; no per-second hard limit specified for the free tier. **Best blurbs and metadata coverage** — TMDB is the contemporary go-to film database. Set as `TMDB_BEARER` and the script uses it via Authorization header so it doesn't leak into URLs.
- **`TMDB_API_KEY`** (fallback) — v3 API key from the same TMDB account. Functionally equivalent for this script's needs but appears in URL strings. Use the bearer token where possible.
- **`OMDB_API_KEY`** — IMDB-derived database; **1000/day free tier** at [omdbapi.com/apikey.aspx](https://www.omdbapi.com/apikey.aspx). Plot summaries are concise — useful as fallback when TMDB and Wikipedia both miss.

Keys go in the user's environment, not on the command line — so they don't appear in the process list or shell history.

## How to invoke

The script lives next to this SKILL.md. From within a wiki vault:

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/skills/movie-enrichment/enrich_movies.py" \
  --vault /absolute/path/to/vault
```

If `--vault` is omitted, the script walks upward from `$PWD` looking for an `AGENTS.md` file at the wiki root.

### Common flags

- `--vault <path>` — explicit vault root. Defaults to walking up from `$PWD`.
- `--status <name>` — only enrich items with this status. Defaults to `to-watch`. Pass `any` to enrich all statuses (useful for back-filling watched/abandoned items too).
- `--limit N` — process at most N items. Useful for a small test before a big run.
- `--items <pattern>` — only process items whose filename matches this glob (e.g. `--items 'the-*'`).
- `--sources <list>` — comma-separated subset of `tmdb,wikipedia,omdb`. Default tries all sources for which credentials (if needed) are present.
- `--reset` — clear `## Blurb` sections on matching items before re-enriching. Use cautiously.
- `--dry-run` — log decisions but don't write any files.

### Exit codes

- `0` success (some items may have been logged as ambiguous; check the log file)
- `2` no vault found
- `3` no items matched the selector

## Idempotency model

The script's contract is *non-destructive enrichment*:

- An item is **skipped** if it already has a `## Blurb` section.
- Frontmatter fields (`creator`, `source_url`, `published`) are only written if currently empty. Existing values are preserved.
- The `updated:` field is bumped to today only when the script writes any change.
- The body's existing sections are preserved verbatim. A new `## Blurb` section is inserted between the H1 and the next existing section.

To force re-enrichment of an item, either delete its `## Blurb` section manually or run with `--reset` against a narrow `--items` filter.

## Source priority

When multiple sources are enabled, the script tries them in this order and stops as soon as one produces a confident match with a description ≥80 chars:

1. **TMDB** — preferred when configured. Best contemporary coverage; rich blurbs (`overview` field); director comes from a separate `/credits` call. Free tier; bearer-token auth means tokens don't leak into URLs.
2. **Wikipedia REST** — best for famous / canonical films. Searches with `(film)` / `(YYYY film)` disambiguator preference and rejects `(novel)` / `(book)` / `(album)` / `(song)` / etc. Skips disambiguation pages.
3. **OMDB** — IMDB-derived; concise plots; 1000/day cap. Useful fallback for cult / B-movies that TMDB or Wikipedia don't cover well.

If you want to compare sources or audit which film got which provenance, the script writes a per-run log to `<vault>/system/enrich-movies-<YYYY-MM-DD>.log` listing per-item status: `enriched-via-<source>`, `ambiguous-no-match`, `ambiguous-low-score`, `ambiguous-no-description`, `skip-already-enriched`, etc. The log is throwaway — fine to delete or `.gitignore`.

## Saving conventions

The script writes only into `<vault>/lists/media/movies/items/<slug>.md`. It does not create wiki entity pages — that promotion stays on-demand per `AGENTS.md` rule 16. If a film deserves a wiki page (you watched it, cite it, query it), create `wiki/entities/movies/<slug>.md` separately and link out from the list item via `wiki_page:`. (Note: the wiki entity directory for movies may not exist by default in every wiki_keeper vault — check the project's `system/schemas/repository-model.md` for the canonical entity directory list.)

Body shape after enrichment:

```markdown
# <Title>

## Blurb

<description, 1–4 paragraphs>

*Source: [<provider>](<url>)*

## Reason for interest
...
```

The `## Blurb` is always inserted as the first section after the H1. Existing sections (Reason for interest, Notes, Links, Status history) are preserved in place and order.

## Year-disambiguation

Films are far more remake-prone than books — *The Wicker Man* (1973) vs. *The Wicker Man* (2006), *The Hallow* (2015) vs. *The Hallows*, etc. The script uses three signals to pick the right year:

- **Year filter at search time** when the item's `published:` frontmatter field is set — TMDB and OMDB both support `year=` query params; Wikipedia gets it appended to the search query.
- **Year-match boost** during candidate ranking: exact year +15%, ±2 years +5%, off-by-more-than-5-years -30%.
- **Derivative-marker penalties** in titles (`(remake)`, `(reboot)`, `(short film)`, `behind the scenes`, `making of`) — these get a 50% penalty before ranking.

If the item carries no `published:` frontmatter and the title is generic (*Witchfinder General*, *Apostle*), the script will pick the highest-popularity match — usually correct but worth spot-checking ambiguous-low-score items in the log.

## Caveats

- **Title-match is fuzzy**, not exact. Generic-titled films (`Apostle`, `Hunger`, `Cure`) and adaptation-heavy titles (`Frankenstein`, where multiple decades of films exist) can mis-match. The script uses a SequenceMatcher ratio threshold of 0.7 plus the year-match boost; ambiguous matches are logged and not auto-applied.
- **TMDB returns `original_title` and `title` separately** for foreign-language films — the script matches against `title` (the English / localized title). For films like *Hagazussa* or *Valkoinen peura* the user may want to verify the result.
- **Wikipedia disambiguation pages** are detected and skipped — but only for the REST `summary` endpoint's reported `type: "disambiguation"`. Older pages without that flag may still slip through; the search-time disambiguator filters help but aren't perfect.
- **Director attribution**: TMDB returns full crew via `/credits`; OMDB returns a `Director` field that may be comma-separated for co-directed films (the script uses the first); Wikipedia REST summary doesn't reliably include director, so when Wikipedia matches, the existing `creator:` value is preserved (no overwrite).
- **OMDB plot length toggle**: the script requests `plot=full` for richer descriptions. The default `plot=short` returns 1-2 sentences; `plot=full` returns 1-2 paragraphs.
- **Tokens are never written to disk**. They're read from environment variables only; the script never logs or echoes them.
- **The `creator:` frontmatter field stores director**, not actor. If a user has manually added an actor name to a foreign / older film thinking it was the relevant credit, the script won't overwrite it — but the result will be misleading. Check ambiguous-* items in the log.

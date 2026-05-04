---
name: book-enrichment
description: Backfill missing metadata + descriptions for `lists/media/books/items/*.md` files in a wiki_keeper-managed vault, using public book APIs (Open Library, Wikipedia, Hardcover, Google Books). Idempotent and non-destructive — only fills empty frontmatter fields and appends a `## Blurb` section.
---

You can flesh out the user's TBR (and other status) book items with author, publication year, source URL, and a short description blurb sourced from public APIs. The skill ships a Python script that's safe to re-run — items already carrying a `## Blurb` section are skipped, and existing frontmatter values are preserved.

## When to use this

- The user has a populated `lists/media/books/items/` whose entries are mostly bare title-only stubs and they want enough metadata to triage what to read next.
- The user has imported books from a list (Goodreads export, hand-typed list, legacy DB) and authors / descriptions weren't captured.
- A book item has a thin or missing `creator:` field and the user wants it filled.
- The user wants to refresh blurbs after adding a new source (e.g., signing up for Hardcover after the initial pass).

## Prerequisite check

`uv` must be available — the script self-bootstraps via PEP 723 inline metadata. If `command -v uv` fails, tell the user and stop.

The script will work with no API keys (Open Library + Wikipedia only). For deeper coverage, two optional credentials:

- **`HARDCOVER_TOKEN`** — bearer token from [hardcover.app/account/api](https://hardcover.app/account/api) (free, expires yearly on January 1). Hardcover has unusually rich descriptions for fiction and is rate-limited to 60 requests/minute.
- **`GOOGLE_BOOKS_KEY`** — Google Books API key. Only needed if the unauth daily quota is exhausted; without a key the script will silently skip Google Books once the quota is hit.

Both keys go in the user's environment, not on the command line — so they don't appear in the process list or shell history.

## How to invoke

The script lives next to this SKILL.md. From within a wiki vault:

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/skills/book-enrichment/enrich_books.py" \
  --vault /absolute/path/to/vault
```

If `--vault` is omitted, the script walks upward from `$PWD` looking for an `AGENTS.md` file at the wiki root.

### Common flags

- `--vault <path>` — explicit vault root. Defaults to walking up from `$PWD`.
- `--status <name>` — only enrich items with this status. Defaults to `tbr`. Pass `any` to enrich all statuses.
- `--limit N` — process at most N items. Useful for a small test before a big run.
- `--items <pattern>` — only process items whose filename matches this glob (e.g. `--items 'a-*'`).
- `--sources <list>` — comma-separated subset of `openlibrary,wikipedia,hardcover,googlebooks`. Default uses all sources for which credentials (if needed) are present.
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

1. **Hardcover** — preferred when configured, especially for fiction. Descriptions are typically the richest available.
2. **Open Library** — primary metadata anchor (author, work key, year). Description quality varies; thin descriptions trigger fallback.
3. **Wikipedia REST** — best for famous / canonical works. Skips disambiguation pages.
4. **Google Books** — broad coverage for the long tail. Last resort because of unauth quota fragility.

If you want to compare sources or audit which book got which provenance, the script writes a per-run log to `<vault>/system/enrich-books-<YYYY-MM-DD>.log` listing per-item status: `enriched-via-<source>`, `ambiguous-no-match`, `ambiguous-low-score`, `ambiguous-no-description`, `skip-already-enriched`, etc. The log is throwaway — fine to delete or `.gitignore`.

## Saving conventions

The script writes only into `<vault>/lists/media/books/items/<slug>.md`. It does not create wiki entity pages — that promotion stays on-demand per `AGENTS.md` rule 16. If a book deserves a wiki page (you read it, cite it, query it), create `wiki/entities/books/<slug>.md` separately and link out from the list item via `wiki_page:`.

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

## Caveats

- **Title-match is fuzzy**, not exact. Generic-titled books (`19 Minutes`, `Zero`, `The Stand`) and adaptation-heavy titles (`1984`, where Open Library returns "1984 (adaptation)" first) can mis-match. The script uses a SequenceMatcher ratio threshold of 0.7 and applies derivative-marker penalties; ambiguous matches are logged and not auto-applied.
- **Hardcover authors include translators**. The script filters on `contribution_types == "Author"` to pick the primary author; check the result if the item ends up with an unexpected creator.
- **Open Library descriptions are sometimes empty**. The script will fall through to the next source rather than write nothing.
- **Wikipedia disambiguation pages** are detected and skipped — but only for the REST `summary` endpoint's reported `type: "disambiguation"`. Older pages without that flag may still slip through.
- **Rate limits**: Open Library is generally lenient, Wikipedia even more so, Hardcover is hard-capped at 60/min, Google Books unauth has a low daily quota that's easy to burn. The script's default sleep of 250–1100 ms per request keeps it under all of these.
- **Tokens are never written to disk**. They're read from environment variables only; the script never logs or echoes them.

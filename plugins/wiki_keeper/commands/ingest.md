---
description: Ingest a single source into the wiki — summarize, integrate, log
argument-hint: @path/to/source.md | https://example.com/article
---

Run the full ingest pipeline for one source. Default to one source per invocation; the user can batch later if they want.

`$ARGUMENTS` may be an `@`-mention path (Claude Code TAB-completes these against the working directory and pre-loads the file), a bare relative or absolute path, or a URL. Detect which and proceed.

## Steps

1. Load the wiki's `AGENTS.md` (or equivalent) and any schemas it points to. Stop if the vault is uninitialized — suggest `/wiki_keeper:init`.

2. Resolve the source from `$ARGUMENTS`:
   - File path inside the vault: read directly.
   - URL: ask whether to fetch and save under `sources/raw/` first, or just analyze in place.
   - Nothing: ask the user which source to process.

3. Read the source end to end. Discuss the key takeaways with the user in 3–5 bullets before writing anything. Confirm the framing.

4. Write a normalized version (if needed) to `sources/normalized/<type>/<slug>.md`. Cleaned, structured — no synthesis, no claims absent from the source.

5. Decide whether to create or update wiki pages. Apply the on-demand rule:
   - Create a wiki page only if the source produces durable synthesis, is referenced by other pages already, or the user asks for one.
   - Otherwise leave the source in `sources/normalized/` and stop after step 7.

6. If creating or updating wiki pages:
   - Identify entities, concepts, and claims worth tracking.
   - For each: create the page (using the project's template) or amend an existing one.
   - Cross-link with `[[wikilinks]]`. Preserve provenance — every nontrivial claim cites the source.
   - Update `wiki/index.md` with new entries.

7. Append a log entry to `system/log.md`:

   ```
   ## [YYYY-MM-DD] ingest | <Source title>

   - Summary: <one-paragraph what was added>
   - Files changed: <bullet list>
   - Follow-up: <gaps, contradictions, or open questions; "None" if clean>
   ```

8. Report a one-line summary plus the files touched.

## Heavy ingestion

If the source is long (book, paper, multi-hour transcript), spawn the `wiki-archivist` subagent to do the read + extraction in a clean context. Pass it the source path, the project's `AGENTS.md`, and the relevant schemas. Have it return a structured proposal (summary + entity/concept/claim updates) for you to review and apply. This keeps the ingestion bookkeeping out of the user's main session.

## Do not

- Edit `sources/raw/`.
- Bulk-create wiki pages for every entity mentioned. On-demand only.
- Skip the log entry.
- Treat existing wiki pages as evidence for new claims — they are synthesis, not source.

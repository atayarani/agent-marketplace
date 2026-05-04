---
description: Ingest a single source into the wiki — summarize, integrate, log
argument-hint: "@path/to/source.md | https://example.com/article"
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

5. **Check `notes/inbox/` for connections.** Spawn the `inbox-connection-finder` subagent with the new normalized source path, the vault root, and the keywords/concepts you extracted in step 3. It will return at most 3 candidate inbox notes that might connect to this source, with soft framing (`strong-match` / `worth-review` / `likely-coincidence`). Surface the candidates to the user. Skip this step only when the inbox is empty or the source is being analyzed in place rather than normalized. The user decides what to do with the candidates — common options:
   - **Graduate the inbox note** (move to `notes/working/`) and cross-link it from the wiki pages you're about to create or update in step 6.
   - **Link without graduating** — add a `note_refs:` entry on the new wiki page and a body mention so the inbox note is reachable, but leave it in inbox.
   - **Ignore** — the candidate is coincidence or not actionable right now.

6. Decide whether to create or update wiki pages. Apply the on-demand rule:
   - Create a wiki page only if the source produces durable synthesis, is referenced by other pages already, or the user asks for one.
   - Otherwise leave the source in `sources/normalized/` and stop after step 8.

7. If creating or updating wiki pages:
   - Identify entities, concepts, and claims worth tracking.
   - For each: create the page (using the project's template) or amend an existing one.
   - Cross-link with `[[wikilinks]]`. Preserve provenance — every nontrivial claim cites the source.
   - Update `wiki/index.md` with new entries.
   - If the user graduated or linked an inbox note in step 5, fold those connections in here.

8. Append a log entry to `system/log.md`:

   ```
   ## [YYYY-MM-DD] ingest | <Source title>

   - Summary: <one-paragraph what was added>
   - Files changed: <bullet list>
   - Follow-up: <gaps, contradictions, or open questions; "None" if clean>
   ```

9. Report a one-line summary plus the files touched.

## Heavy ingestion

If the source is long (book, paper, multi-hour transcript), spawn the `wiki-archivist` subagent to do the read + extraction in a clean context. Pass it the source path, the project's `AGENTS.md`, and the relevant schemas. Have it return a structured proposal (summary + entity/concept/claim updates) for you to review and apply. This keeps the ingestion bookkeeping out of the user's main session.

## Inbox connection-finding

Step 5 calls the `inbox-connection-finder` subagent. Two notes:

- **It runs in clean context.** It only sees the normalized source, the vault's `notes/inbox/`, and the keywords you pass it. It does not read the wiki, prior conversation, or other ingest logs. That isolation is the point — the subagent's job is to find dormant inbox material that the parent might overlook because it's invested in the new source's synthesis.
- **At most 3 candidates, with soft framing.** The subagent caps results to keep noise bounded. If it returns "no meaningful overlap," accept that and move on; do not retry with broader keywords just to surface something. Empty results are correct results.

## Do not

- Edit `sources/raw/`.
- Bulk-create wiki pages for every entity mentioned. On-demand only.
- Skip the log entry.
- Treat existing wiki pages as evidence for new claims — they are synthesis, not source.

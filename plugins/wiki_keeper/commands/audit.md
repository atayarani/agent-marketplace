---
description: Health-check the wiki — contradictions, stale claims, orphans, gaps
argument-hint: "[scope: full | concepts | claims | entities | recent]"
---

Run a maintenance audit on the wiki. Identify drift; do not fix it in the same pass.

## Steps

1. Load `AGENTS.md` and any maintenance schema. If uninitialized, suggest `/wiki_keeper:init` and stop.

2. Determine scope from `$ARGUMENTS`:
   - `full` (default): all wiki pages.
   - `concepts` / `claims` / `entities`: that subtree only.
   - `recent`: pages changed in the last 30 days (`git log --since=30.days --name-only`).

3. Spawn the `wiki-auditor` subagent with the scope. It runs in clean context, reads pages, returns findings. Do not audit yourself in this session — clean context catches drift you would rationalize away.

4. Receive the findings. Format as a single table grouped by severity:

   | severity | category | page | issue | suggested fix |

   Categories: `contradiction`, `stale-claim`, `orphan`, `missing-page`, `missing-link`, `provenance-gap`, `data-gap`.

   Severities: `blocker` (the wiki is wrong), `concern` (likely wrong or incoherent), `nit` (small inconsistency).

5. Append an audit log entry to `system/log.md`:

   ```
   ## [YYYY-MM-DD] audit | <scope>

   - Summary: <N findings: X blocker, Y concern, Z nit>
   - Files changed: system/log.md
   - Follow-up: <list of pages needing correction, or "None">
   ```

6. Ask the user which findings to act on. Apply corrections one at a time, each as a separate log entry with action `correction`. Do not bundle.

## Auditor categories — what to look for

- **contradiction**: page A asserts X, page B asserts not-X, no reconciliation.
- **stale-claim**: page asserts something a newer source contradicts; provenance points to the older source.
- **orphan**: page has no inbound wikilinks; not reachable from `index.md`.
- **missing-page**: a concept or entity is referenced by name across multiple pages but has no page of its own.
- **missing-link**: a page mentions a known wiki entity but does not wikilink to it.
- **provenance-gap**: a nontrivial claim has no citation back to a source.
- **data-gap**: an answerable question that the wiki cannot answer; flag for a future ingest or web search.

## Do not

- Apply corrections silently in the audit pass.
- Rewrite history in `system/log.md`.
- Use the audit to refactor the wiki structurally. Structural changes go through a separate decision and a `restructure` log entry.

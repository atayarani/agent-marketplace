---
description: Health-check the wiki — contradictions, stale claims, orphans, gaps
argument-hint: "[scope: full | concepts | claims | entities | recent | sources | lists | external | schema]"
---

Run a maintenance audit. Identify drift; do not fix it in the same pass.

## Steps

1. Load `AGENTS.md` and any maintenance schema. If uninitialized, suggest `/wiki_keeper:init` and stop.

2. Determine scope from `$ARGUMENTS`:
   - `full` (default): all wiki pages.
   - `concepts` / `claims` / `entities`: that subtree only.
   - `recent`: wiki pages changed in the last 30 days (`git log --since=30.days --name-only`).
   - `sources`: source files in `sources/` — frontmatter completeness, broken backpointers, synthesis creep.
   - `lists`: media list items in `lists/media/` — broken `source_refs:`, missing required fields.
   - `external`: sync between `external/` and their `sources/` processed counterparts — backpointer validity, orphaned files.
   - `schema`: schema files and scripts in `system/` — stale path references, internal contradictions, rules that contradict current vault state.

3. For wiki scopes (`full`, `concepts`, `claims`, `entities`, `recent`): spawn the `wiki-auditor` subagent with the scope. It runs in clean context, reads pages, returns findings.

   For non-wiki scopes (`sources`, `lists`, `external`, `schema`): run the appropriate checks directly (see per-scope rules below). Use a general-purpose agent if the check requires broad file scanning.

4. Receive the findings. Format as a single table grouped by severity:

   | severity | category | file | issue | suggested fix |

   Categories: `contradiction`, `stale-claim`, `orphan`, `missing-page`, `missing-link`, `provenance-gap`, `data-gap`, `broken-ref`, `missing-field`, `stale-path`.

   Severities: `blocker` (wrong or broken), `concern` (likely wrong or incoherent), `nit` (small inconsistency).

5. Append an audit log entry to `system/log.md`:

   ```
   ## [YYYY-MM-DD] audit | <scope>

   - Summary: <N findings: X blocker, Y concern, Z nit>
   - Files changed: system/log.md
   - Follow-up: <list of files needing correction, or "None">
   ```

6. Ask the user which findings to act on. Apply corrections one at a time, each as a separate log entry with action `correction`. Do not bundle.

## Wiki auditor categories (full / concepts / claims / entities / recent)

- **contradiction**: page A asserts X, page B asserts not-X, no reconciliation.
- **stale-claim**: page asserts something a newer source contradicts; provenance points to the older source.
- **orphan**: page has no inbound wikilinks; not reachable from `wiki/index.md`.
- **missing-page**: a concept or entity is referenced by name across multiple pages but has no page of its own.
- **missing-link**: a page mentions a known wiki entity but does not wikilink to it.
- **provenance-gap**: a nontrivial claim has no citation back to a source.
- **data-gap**: an answerable question the wiki cannot answer; flag for a future ingest or web search.

## Sources audit (sources scope)

Check all `.md` files in `sources/web/`, `sources/chats/`, `sources/readwise/`:

- **missing-field**: required frontmatter fields absent (`source_type`, `url` or valid backpointer field, `title`, `captured`).
- **broken-ref**: `external_ref:` / `readwise_ref:` field points to a path that does not exist in `external/`.
- **stale-path**: any wikilink inside the source body references a path that no longer exists (e.g. old `sources/normalized/` or `wiki/entities/` paths).
- **provenance-gap**: source file has no `url:` and no backpointer field — no way to trace provenance.

## Lists audit (lists scope)

Check all `.md` files in `lists/media/`:

- **broken-ref**: `source_refs:` entries point to source files that no longer exist at the referenced path.
- **missing-field**: required frontmatter fields absent (`type`, `media_type`, `status`, `title` or equivalent).
- **stale-path**: any wikilink inside the list item references a deleted path.

## External audit (external scope)

Check sync between `external/` and `sources/`:

- **broken-ref**: `sources/readwise/<Category>/<slug>.md` has a `readwise_ref:` pointing to a file that does not exist in `external/readwise/`.
- **orphan**: file exists in `external/chats/` with no corresponding processed file in `sources/chats/` (flag only URL-less files where `external/chats/` is the canonical record).
- **missing-field**: `sources/readwise/Books/*.md` is missing `lists_ref:` and the book exists in `lists/media/books/items/` (should be cross-linked).

## Schema audit (schema scope)

Check files in `system/schemas/`, `system/scripts/`, `AGENTS.md`:

- **stale-path**: any path reference inside a schema or script that no longer exists in the vault (e.g. deleted directories, renamed files).
- **contradiction**: two schema files assert conflicting rules about the same thing.
- **stale-claim**: a schema rule describes a vault behavior that has since changed (e.g. still mentions `sources/normalized/`, wiki pages being created at ingest time).

## Do not

- Apply corrections silently in the audit pass.
- Rewrite history in `system/log.md`.
- Use the audit to refactor the vault structurally. Structural changes go through a separate decision and a `restructure` log entry.

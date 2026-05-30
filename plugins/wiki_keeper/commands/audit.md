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

5.
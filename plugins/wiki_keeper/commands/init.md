---
description: Scaffold a new LLM wiki vault in the current directory
argument-hint: [optional vault name or path]
---

Initialize an LLM-maintained wiki vault. Use sensible defaults but ask before overwriting any existing files.

## Steps

1. Resolve the target directory:
   - If `$ARGUMENTS` is a path, use it (create if missing).
   - Otherwise use the current working directory.

2. Inspect the target. If it already contains an `AGENTS.md` or a populated `wiki/`, stop and report what's there. Do not overwrite — propose targeted additions instead.

3. Confirm the layout with the user before creating files. Default (mirrors the gist plus the patterns proven in atayarani's vault):

   ```
   sources/raw/                  immutable captures
   sources/normalized/           cleaned source material (no synthesis)
   notes/inbox/                  unfiled human captures
   notes/working/                active human drafts
   notes/journal/daily/          dated journal entries
   wiki/index.md                 content-oriented catalog
   wiki/entities/                pages about specific referents
     books/  articles/  videos/  podcasts/  people/  tools/
   wiki/concepts/                ideas, frameworks, comparisons
   wiki/claims/                  traceable assertions
   lists/                        workflow state (read/to-read, etc.)
   outputs/                      composed deliverables
   system/log.md                 append-only chronological log
   system/schemas/               operation-specific schemas
   system/templates/             page templates
   AGENTS.md                     vault instructions for agents
   CLAUDE.md, GEMINI.md          one-line pointers to AGENTS.md
   ```

   Offer to drop layers the user doesn't need (e.g. `notes/`, `lists/`, `outputs/`).

4. Write the files. Each schema and template should be short and pragmatic — leave room for the vault to evolve them.

   - `AGENTS.md`: short instructions naming the directory model, the immutability rule for `sources/raw/`, the on-demand wiki promotion rule, the index/log discipline, and a list of schemas to read for specific operations.
   - `wiki/index.md`: skeleton with the role headings, no entries yet.
   - `system/log.md`: file header plus a single seed entry: `## [YYYY-MM-DD] scaffold | Initialize vault`.
   - `system/schemas/repository-model.md`: directory layer purposes.
   - `system/schemas/provenance.md`: how nontrivial claims cite back to sources.
   - `system/schemas/maintenance.md`: how audit + correction cycles work.
   - `system/templates/`: minimal templates for entity, concept, claim, normalized source, output, human note. YAML frontmatter with `type`, `created`, `updated`, `provenance`.
   - `CLAUDE.md` and `GEMINI.md`: one line each, pointing at `AGENTS.md`.

5. Optionally `git init` if the directory is not already a repo. Add a `.gitignore` covering `.obsidian/themes/`, `.obsidian/plugins/*/main.js`, `.obsidian/plugins/*/styles.css`, `.obsidian/plugins/*/data.json`, `.obsidian/graph.json`, `.obsidian/appearance.json` (these are bulky/secret-prone).

6. Append a seed entry to `system/log.md` and report what was created.

## Notes

The point is to get a working vault quickly, not to anticipate every future need. Prefer fewer files. The user and the LLM co-evolve the schemas as real sources hit the pipeline.

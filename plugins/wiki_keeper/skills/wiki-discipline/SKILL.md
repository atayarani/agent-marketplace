---
name: wiki-discipline
description: Use when working in an LLM-maintained wiki vault — ingesting sources, querying the wiki, filing insights back, or auditing the wiki for drift. Encodes the three-layer architecture (raw sources, wiki, schema), the three operations (ingest, query, audit), and the rules that keep the wiki coherent over time.
---

You are working in an LLM-maintained wiki: a directory of markdown files where you do the bookkeeping that makes a knowledge base actually compound. The user curates sources and asks questions; you read, summarize, cross-reference, file, and maintain.

## Read the vault's own conventions first

Before doing anything, read the project's instruction file (`AGENTS.md` first, then `CLAUDE.md` / `GEMINI.md` as fallbacks) and any schemas it points to. The vault may extend or override the defaults below. Trust the project's rules over this skill when they conflict.

If no such file exists, the vault has not been initialized. Suggest `/wiki_keeper:init` and stop.

## Three layers

1. **Raw sources** — immutable captures (clipped articles, transcripts, PDFs, exports). Read-only. Never edit unless the user explicitly asks.
2. **Wiki** — markdown pages you write and maintain. Pages by synthesis role: entities (specific referents), concepts (ideas/frameworks), claims (traceable assertions). The vault may add layers like `notes/` (human first-party thinking), `lists/` (workflow state), `outputs/` (composed deliverables) — respect their boundaries.
3. **Schema** — `AGENTS.md` plus any files under `system/schemas/` (or equivalent). This is how the vault tells you how it's structured. You and the user co-evolve it; do not rewrite it without saying so.

## Three operations

**Ingest.** Read a single source, discuss takeaways with the user, write a summary, update relevant entity / concept / claim pages, append to the log. Wiki pages are created **on demand** (durable synthesis, repeated reference, explicit request, or audit gap) — not bulk-promoted from sources. A source can sit in `sources/` indefinitely without a wiki page.

**Query.** Search the wiki (start at `wiki/index.md`, drill into pages, fall back to sources only when the wiki is silent). Answer with citations back to sources, notes, or claim pages. **If the answer is durable insight, file it back into the wiki** — a new concept page, a comparison, a strengthened claim. Don't let synthesis disappear into chat history.

**Audit.** Health-check the wiki: contradictions between pages, stale claims newer sources have superseded, orphan pages, hub concepts mentioned but lacking their own page, missing cross-references, gaps a web search could fill.

## Rules

1. `sources/raw/` is immutable. Do not modify it.
2. `sources/normalized/` is for cleaned source material — no synthesis, no interpretation, no claims absent from the source.
3. Do not destructively rewrite human-authored notes (`notes/`) without explicit instruction.
4. Every nontrivial synthesized claim preserves provenance — link to the source, note, or claim page it rests on.
5. Prefer updating an existing wiki page over creating a new overlapping one.
6. Use Obsidian wikilinks (`[[page-name]]`) for internal references.
7. Use stable, lowercase, hyphenated filenames.
8. Mark uncertainty, caveats, and unsupported interpretation explicitly.
9. Do not treat generated wiki text as raw evidence when ingesting future sources.
10. Outputs cite or link back to sources, notes, concepts, or claims.
11. Maintain `wiki/index.md` as the content-oriented index.
12. Maintain `system/log.md` as an append-only chronological log. Append entries; do not rewrite history.
13. For substantial changes, prefer small, reviewable edits over broad rewrites.

## Index and log conventions

**`wiki/index.md`** — content-oriented. Each wiki page listed once with a one-line summary, grouped by role (Concepts / Claims / Entities / Outputs). Update on every ingest or new page. When answering a query, read the index first.

**`system/log.md`** — chronological. Append entries with a consistent header so the log is greppable:

```
## [YYYY-MM-DD] action | Title

- Summary:
- Files changed:
- Follow-up:
```

`action` is one of: `ingest`, `query`, `audit`, `correction`, `restructure`, `policy`, `cleanup`. The header format means `grep "^## \[" system/log.md | tail -10` always gives a clean recent timeline.

## Filing-back

The single most important habit: when a query produces a durable comparison, framework, or insight, **write it into the wiki** before the conversation ends. Pick the right home (concept, claim, or amend an entity), wikilink it, update the index, log it. The wiki compounds only if exploration outputs are filed.

## When in doubt

Ask the user. The vault's specifics belong to them; your job is to maintain them carefully.

---
description: Query the wiki and optionally file the answer back as a new page
argument-hint: <question> — use @page.md inside to pin a specific wiki page
---

Answer a question against the wiki, then decide whether the answer is durable enough to file back.

`$ARGUMENTS` is free-text. Users may embed `@`-mention paths inside the question to pin specific wiki pages, sources, or notes into context — Claude Code TAB-completes those against the working directory and pre-loads them. Treat any `@`-resolved files as authoritative starting points for the answer.

## Steps

1. Load `AGENTS.md` and any schemas it points to. If uninitialized, suggest `/wiki_keeper:init` and stop.

2. Read `wiki/index.md`. Identify candidate pages from titles and one-line summaries.

3. Read the candidate pages. Drill into linked pages as needed. Fall back to `sources/normalized/` only when the wiki is silent on the question. Use `sources/raw/` only as a last resort and only to read.

4. Answer the question. Cite every nontrivial claim with a wikilink to the wiki page or source it rests on. If evidence is thin, say so explicitly — do not invent synthesis.

5. Decide whether the answer should be filed back:
   - **File it** if the answer produced a new comparison, a clarified concept, a synthesized claim, or a useful framework — anything the user is likely to want to retrieve later.
   - **Do not file** if the answer was a quick lookup that didn't generate new structure.

6. If filing back:
   - Pick the right home: a new `wiki/concepts/` page for a framework or comparison; a new `wiki/claims/` page for a specific assertion; an amendment to an existing entity for biographical updates.
   - Use the project's template if one exists.
   - Cross-link from related pages so the new page is reachable.
   - Update `wiki/index.md`.
   - Append a log entry: `## [YYYY-MM-DD] query | <question topic>` with `Files changed` listing the new or amended page.

7. Return the answer to the user and (if filed) the path of the new wiki page.

## Output format options

When the user wants a non-prose answer — a comparison table, a slide deck (Marp), a chart, a canvas — produce that, and still file a markdown summary back to the wiki with a link to the artifact. The artifact is ephemeral; the synthesis is not.

## Do not

- Treat `wiki/` text as evidence for claims that aren't traceable to a source.
- Omit citations.
- File answers that are just lookups — that bloats the wiki without compounding.

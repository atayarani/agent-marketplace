---
name: highlights
description: EXPLICIT-INVOCATION-ONLY. Surface 5 wiki highlights as one-sentence bullets in chat. Run **only** when the user has typed `/wiki_keeper:highlights` (or the host's equivalent slash form) — never auto-load on natural-language phrasings about the wiki, samples, browsing, daily prompts, or rediscovery, even when those phrasings seem to fit. Read-only — never writes to a file. If this skill matches a natural-language request rather than an explicit slash invocation, refuse to run and surface the slash command form to the user instead.
---

You're surfacing 5 wiki highlights to the chat for the user to skim. **The output is 5 bullet points, one sentence each, and is never written to disk.**

## Invocation guardrail (read this first)

**This skill runs ONLY on explicit slash-command invocation** — `/wiki_keeper:highlights` on Claude Code, the equivalent on Codex / Gemini.

If you reached this skill because the user said something like *"what's in the wiki?"* / *"show me a sample"* / *"give me a browsing prompt"* / *"5 things from the vault"* — or any other natural-language phrasing that semantically matches the skill's job — **do not run it**. Instead:

1. Tell the user the slash command form: *"You can run `/wiki_keeper:highlights` for that."*
2. Stop. Don't surface bullets, don't read pages, don't pre-fetch anything.

The reason: highlights are explicit-curiosity output. The user wants to ask for them deliberately, not have them appear during other tasks. Accidental auto-invocation is exactly what the skill is designed to avoid.

The slash command body at `commands/highlights.md` is the legitimate entry point; running this SKILL.md on its own is the case to refuse.

## Interpreting "concepts"

Some `wiki_keeper` vaults have only a handful of `wiki/concepts/` pages but many entity pages with load-bearing theses, plus candidate concepts that have been documented across multiple pages but not yet promoted. **Read "concepts" broadly: any durable idea the wiki captures**, regardless of which subfolder hosts the page. Acceptable picks include:

- A `wiki/concepts/` page's central distinction.
- A `wiki/claims/` page's load-bearing assertion (when those exist).
- A `wiki/entities/<type>/` page's distinctive thesis or signature move.
- A cross-source pattern documented across multiple pages (e.g., a candidate concept tracked at N instances).

Skip: page titles by themselves, channel-cluster size facts, or housekeeping observations. The bar is "is this a *substantive idea* the user would want to be reminded of?"

## Default flow

1. **Read `wiki/index.md`** to get the lay of the land — the index is the canonical entry point for concepts, claims, and entities.
2. **Pick 5 items spanning at least 2 of the synthesis layers.** Mix concepts with entity-page theses (e.g., 1 concept + 1 cross-source pattern + 3 entity-thesis picks; or 2 concepts + 3 entity-thesis picks). Diversity matters more than the exact mix; **avoid 5-from-the-same-channel-cluster monoculture**. If the wiki has < 5 concept pages, that's fine — pull from entity-page theses to make up the count.
3. **Read the picked pages** (just the picked ones — don't try to load the whole wiki) and pull the load-bearing claim from each.
4. **Write each highlight as a single sentence** that captures the idea. Cite the source page with a wikilink so the user can navigate.
5. **Surface to chat as bullet points only.** Do not write to any file. Do not append a log entry. Do not update any wiki page.

## Output shape

```markdown
Five from across the wiki:

- **[[<page-link>|<short-title>]]**: <one sentence capturing the load-bearing idea>.
- **[[<page-link>|<short-title>]]**: <one sentence>.
- **[[<page-link>|<short-title>]]**: <one sentence>.
- **[[<page-link>|<short-title>]]**: <one sentence>.
- **[[<page-link>|<short-title>]]**: <one sentence>.
```

A short framing line above the bullets is OK ("Five from across the wiki:"). No closing summary, no analytical wrap-up. The bullets are the deliverable.

## Variation — keep it fresh

Different invocations should produce different picks. Strategies:

- Vary which synthesis layer dominates the selection (mostly-concepts one time, mostly-entity-theses another).
- Pull from less-recently-added pages when their `created:` date is visibly older than today's recent ingests.
- Surface candidate-concept patterns (e.g., "form encodes meaning at N instances") alongside named entity pages — they read as durable ideas even when not yet promoted.

If the user invokes the skill twice in the same session, the second batch should overlap minimally with the first (different layer mix; different pages).

## Do not

- **Run on natural-language requests.** This skill is explicit-invocation-only — the user must have typed the slash command. If you reached this SKILL.md from an ambient phrasing match, surface the slash command to the user and stop. (See "Invocation guardrail" at the top of this file.)
- **Write to any file.** The output is chat-only. This is the explicit constraint that makes the skill a read-only browsing prompt rather than an outputs-builder.
- **Append a log entry.** This is a read-only operation; nothing is being changed in the vault.
- **Update any wiki page**, including `wiki/index.md`. The skill is a passive surfacing pass.
- **Pad sentences past one.** Terseness is the value here — if the idea needs two sentences to land, pick a different pick.
- **Pick 5 from the same channel cluster.** Diversity across the wiki is the point; a channel-monoculture sample would be a worse-than-useless prompt.
- **Skip the wikilinks.** Each bullet should let the user click to the source page.

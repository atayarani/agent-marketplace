---
description: Surface 5 concepts from across the wiki as one-sentence bullet points. Read-only — never writes to a file.
---

Surface 5 wiki highlights to the chat as one-sentence bullet points.

Use the `highlights` skill's SKILL.md for full reference. Brief instructions:

1. **Verify the vault is initialized** (`AGENTS.md` is reachable at the wiki root). If not, suggest `/wiki_keeper:init`.

2. **Read `wiki/index.md`** for the lay of the land.

3. **Pick 5 items spanning at least 2 synthesis layers** (concepts / claims / entity-page theses / documented candidate-concept patterns). Diversity over monoculture — avoid 5-from-the-same-channel-cluster picks.

4. **Read the picked pages** and pull the load-bearing idea from each.

5. **Write each highlight as a single sentence** with a wikilink to the source page.

6. **Surface to chat only.** Do not write to any file, do not append a log entry, do not update any wiki page. The output is ephemeral by design.

## Output shape

```markdown
Five from across the wiki:

- **[[<page-link>|<short-title>]]**: <one sentence capturing the idea>.
- ...
```

## Sensible default invocation

If `$ARGUMENTS` is empty, run with the default flow: a varied mix across synthesis layers. If the user has invoked the skill earlier in the session, the second batch should overlap minimally with the first.

## Do not

- Pad bullets past one sentence.
- Pick 5 from the same channel cluster.
- Skip the wikilinks.
- Write to any file. The skill is read-only by design.

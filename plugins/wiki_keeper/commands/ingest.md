---
description: Ingest a source into the vault — captures from any URL, file, or pasted content
argument-hint: "<url | path | pasted-content>"
---

Capture a single source into the vault. One unified entry point — the source type is detected from the argument shape and dispatched to the right capture path. Under the strict on-demand discipline (AGENTS.md rule 15): ingest writes to `sources/`, `lists/`, and `external/`, and commits to git. It does **not** create or update `wiki/` pages — that's the Query operation.

## Dispatch table

Detect the source type from `$ARGUMENTS`:

| Input shape | Source type | Captures via | Saved to |
|---|---|---|---|
| `youtube.com/watch?v=…`, `youtu.be/…`, `youtube.com/shorts/…`, or 11-char video ID | YouTube transcript | `fetch_transcript.py` (yt-dlp fallback) | `sources/web/videos/<slug>.md` |
| `chatgpt.com/c/…`, `chat.openai.com/share/…` | ChatGPT chat | WebFetch + parse | `external/chats/<slug>.md` + `sources/chats/<slug>.md` |
| `claude.ai/chat/…`, `claude.ai/share/…` | Claude.ai chat | WebFetch + parse | `external/chats/<slug>.md` + `sources/chats/<slug>.md` |
| Any other `https://…` URL | Web article | WebFetch | `sources/web/articles/<slug>.md` |
| Path starting with `/`, `./`, or `@` | Existing local source | Read directly | (no new write — analyze the existing file) |
| Pasted multi-line text with `**User:**` / `## Prompt:` / `## User` shape | AI chat export | Parse content shape | `external/chats/<slug>.md` + `sources/chats/<slug>.md` |
| Empty / unrecognized | n/a | Ask the user for a URL or path | n/a |

## Steps

1. **Load AGENTS.md** and the relevant schema for the detected source type:
   - YouTube → `system/schemas/youtube-ingestion.md`
   - Chat → `system/schemas/ai-chat-ingestion.md`
   - Web article → `system/schemas/source-normalization.md`
   - Stop if the vault is uninitialized (suggest `/wiki_keeper:init`).

2. **Detect the source type** from `$ARGUMENTS` via the dispatch table.

3. **Capture** the source per the detected type (see per-type sections below).

4. **Write the source file(s)** with frontmatter per the relevant schema. The schema is the source of truth for frontmatter fields — read it; do not invent fields.

5. **Add per-source analysis** in a `## Key content` (or equivalent) section before the transcript / content body. This captures what *this source* says: thesis, key claims, structure, distinctive moves. **Not** cross-source synthesis — that's Query territory.

6. **Update `lists/` cross-references** if the source cites a book / movie / podcast / article that has an entry in `lists/media/<type>/items/`. Append the new source's wikilink to that item's `source_refs:`. This is provenance bookkeeping, not synthesis.

7. **Surface a one-line summary** of what was captured. Do not commit — let the user do that (or batch with later ingests).

## Per-type capture

### YouTube

```bash
# Metadata sidecar (chapters, duration, channel)
yt-dlp --skip-download --print "%(title)s|%(channel)s|%(upload_date)s|%(duration_string)s" "<url>"

# Transcript via the bundled fetch_transcript.py
"${CLAUDE_PLUGIN_ROOT:-.}/skills/youtube-transcript/fetch_transcript.py" "<url>" --format text > /tmp/<video-id>.transcript.txt
```

Save the resulting `sources/web/videos/<slug>.md` with frontmatter per `youtube-ingestion.md` and the transcript appended after a `## Transcript` header.

**Caption fallback**: the script handles IP-blocks via yt-dlp's `--write-auto-subs`. Manual `en-US`/`en-GB` captions are higher quality than `en` auto — try `--languages en-US en-GB en` if `--list` shows manual captions available.

### Chat (URL form — ChatGPT, Claude.ai)

For share URLs:

```bash
# Try WebFetch first
WebFetch "<url>"
```

If WebFetch returns the chat content, save as both:
- `external/chats/<slug>.md` — raw export (the verbatim chat content)
- `sources/chats/<slug>.md` — processed with frontmatter and `external_ref: "[[external/chats/<slug>]]"` backpointer

If WebFetch returns nothing useful (auth-gated, share link expired), ask the user to paste the export content instead.

### Chat (pasted content form)

When the user pastes a chat export directly:
- Detect by content shape: `**User:**`, `**Created:**`, `**Link:**` lines (ChatGPT Exporter format), or `## Prompt:` / `## Response:` headers, or `## You` / `## ChatGPT` headers
- Parse the export structure: title (H1 or `**Title:**`), URL (`**Link:**`), timestamps (`**Created:**` / `**Updated:**` / `**Exported:**`), turns
- Save the **raw export** verbatim to `external/chats/<slug>.md` (strip only obvious UI noise: browsing citation blocks may be compacted to one-line `[Web browsing: N sources]` summaries)
- Save the **processed version** to `sources/chats/<slug>.md` with frontmatter per `ai-chat-ingestion.md`, including `external_ref: "[[external/chats/<slug>]]"` and turn summaries

Slug naming for chats: topic-derived, lowercase-hyphenated, **title-only** (not date-prefixed, not provider-prefixed). See `ai-chat-ingestion.md`.

### Web article

```bash
WebFetch "<url>"
```

Save as `sources/web/articles/<slug>.md` with frontmatter per `source-normalization.md` (`source_type: article`, `title`, `url`, `author` if extractable, `captured`).

### Local file path

Read the file. If it already has proper frontmatter and lives under `sources/`, no new write — just add per-source analysis if missing. If it's outside `sources/`, ask the user where to file it.

## Per-source analysis

Under strict on-demand: per-source synthesis (what *this source* says) is acceptable in the source body. Cross-source synthesis (this source's pattern matches another source's pattern) is **not** — that's a Query operation.

What belongs in `## Key content`:
- The source's thesis or claim
- Structural breakdown (the "3 steps," the "5 tips," the "4 truths")
- Distinctive moves (worked refactors, framing devices, register signals)
- Sponsor / CTA (when notable)

What does **not** belong:
- "This is the Nth video on topic X" cross-channel density observations
- "This pairs with [other source]" — that's a query-time finding
- New entity/concept proposals — Query creates wiki pages, not ingest

## Heavy ingestion

If the source is long (book, paper, multi-hour transcript), delegate the read + extraction to the `wiki-archivist` subagent. Pass it the source path and the relevant schemas. Have it return a structured proposal for the per-source analysis section. The actual write stays in the parent session.

## lists/ cross-linking discipline

When the source mentions a book / movie / podcast / article by name:
1. Look for `lists/media/<type>/items/<slug>.md`
2. If exists: append the new source's path to its `source_refs:` array, bump `updated:`
3. If not exists AND the host frames it as a substantive recommendation: create the list item with `source_refs:` populated

This is the only structural cross-link ingest performs. See `system/schemas/youtube-ingestion.md` "TBR cross-link discipline" for full rules.

## Do not

- Create or update `wiki/` pages (entity / concept / claim / index). That's Query, not Ingest.
- Modify files in `external/` after the initial write — they're treated as service-owned.
- Bulk-create entity pages for every channel / author / book mentioned. On-demand only.
- Treat the source's claims as evidence for cross-source patterns. The source is one data point.

## Migration note (2026-05-30)

This skill replaces the prior split between `/wiki_keeper:youtube-transcript`, `/wiki_keeper:ai-chat-source`, and `/wiki_keeper:ingest`. All three are now the same entry point. The two source-type-specific skills are retained as thin redirects to this command.

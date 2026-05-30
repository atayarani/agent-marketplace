---
name: ai-chat-source
description: DEPRECATED — chat capture has been unified into /wiki_keeper:ingest as of 2026-05-30. This skill exists only as a redirect for the deprecated slash form. Do NOT auto-trigger on natural-language requests to save chat transcripts — those should route to /wiki_keeper:ingest instead.
---

# Deprecated — chat capture is now part of /wiki_keeper:ingest

**As of 2026-05-30, `/wiki_keeper:ai-chat-source` was unified into `/wiki_keeper:ingest`.** The unified ingest skill detects pasted chat content by its shape (`**User:**` / `## Prompt:` / `## You` headers, ChatGPT-Exporter `**Created:**` / `**Link:**` lines) and dispatches to the chat capture path automatically.

## If the user typed `/wiki_keeper:ai-chat-source <pasted-content>`

This is the deprecated slash form. Redirect:

1. Tell the user: *"`/wiki_keeper:ai-chat-source` was unified into `/wiki_keeper:ingest` on 2026-05-30. I'll run the ingest flow with the same content."*
2. Run the `/wiki_keeper:ingest` flow with the pasted content.

## Why the unification

Under the strict on-demand discipline (AGENTS.md rule 15), all source captures follow the same shape:
1. Detect type
2. Save to vault with proper frontmatter
3. Add per-source analysis
4. Commit

The three previous skills (`youtube-transcript`, `ai-chat-source`, and the URL branch of `ingest`) duplicated steps 2-4 with type-specific variations only in step 1. Unifying into a single dispatcher reduces drift and gives one mental model for the user.

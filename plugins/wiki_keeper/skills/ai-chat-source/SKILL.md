---
name: ai-chat-source
description: Save a pasted AI chat transcript (Claude, ChatGPT, Gemini, Cursor, etc.) as a raw source in a wiki_keeper vault. Use when the user pastes a conversation and wants it stored — e.g. "save this chat", "add this conversation to the wiki", "ingest this Claude transcript", "file this ChatGPT chat". Writes the raw file under sources/raw/, then offers to hand off to /wiki_keeper:ingest for normalization and synthesis.
---

You save pasted AI-chat transcripts into a wiki_keeper vault as raw sources. The capture + bookkeeping is your job. Synthesis, normalization, and wiki promotion happen later, inside `/wiki_keeper:ingest` — do not duplicate that work here.

## When to use this

- The user pastes an LLM conversation (Claude, ChatGPT, Gemini, Cursor, Copilot, etc.) into the chat and asks to save, file, ingest, or archive it.
- The user gives you a path to a chat export file (JSON, markdown) and asks to file it as a source.
- The user gives you a share URL for a public chat conversation.
- `/wiki_keeper:ingest` is run against pasted chat content and needs the raw written first.

## Default flow

Run these steps in order — don't stop early:

1. Confirm the vault is initialized (`AGENTS.md` exists at the vault root). If not, tell the user and stop — there's no source location to write to.
2. Read the vault's schemas. Start with `AGENTS.md` and any file under `system/schemas/` whose name suggests AI-chat ingestion (`ai-chat-ingestion.md`, `chat-ingestion.md`, etc.) or general source normalization (`source-normalization.md`). If a schema exists, follow it.
3. Gather minimum metadata from the user in **one** round (see "Metadata"). Don't drip-feed questions.
4. Save the raw chat per the schema, or per the fallback pattern below if no schema exists.
5. **Offer to hand the raw path to `/wiki_keeper:ingest`** in the same turn (see "Offer to hand off to ingest"). Mandatory whenever step 4 ran.
6. If the user declines, surface the raw path and stop.

## Reading the pasted text

Pasted chats arrive in a handful of shapes:

- **Alternating turns with labels**: `User:` / `Claude:`, `Human:` / `Assistant:`, `## You` / `## ChatGPT`. Preserve them.
- **Unlabeled bodies**: just paragraphs alternating between speakers. Ask the user to confirm which speaker started before saving — guessing produces wrong attributions.
- **Provider exports**: JSON (ChatGPT, Claude.ai exports), markdown (Cursor, Copilot Chat). Save the file as-is under the raw path; do not convert formats.
- **Share URL** (`claude.ai/share/...`, `chat.openai.com/share/...`, `gemini.google.com/share/...`): try `WebFetch` first. If the page is auth-gated or empty, ask the user to paste the content instead.

Preserve the conversation lossless: speaker order, turn boundaries, code blocks, markdown formatting. Strip only obvious UI noise (typing indicators, "Copy" / "Regenerate" buttons, "ChatGPT can make mistakes" footers). **Do not summarize, condense, or rewrite.** The raw is meant to round-trip.

## Metadata

Ask in one round and include sensible defaults the user can accept silently. Required and optional fields:

- **provider** (required) — `anthropic` | `openai` | `google` | `xai` | `cursor` | `github-copilot` | etc. Try to infer from speaker labels, model mentions, or share-URL hostname before asking.
- **model** (optional but encouraged) — full model id (`claude-opus-4-7`, `gpt-4o-2024-08-06`, `gemini-2.5-pro`). Leave blank rather than guess.
- **date** (default: today, YYYY-MM-DD) — when the conversation happened, not when you're filing it.
- **title** (required) — short topic phrase, hyphenated for the filename slug. The user's framing usually gives you this.
- **url** (optional) — share link if one exists.
- **note** (optional) — one-line context the user might want to preserve ("debugging the migration", "drafting the README", etc.).

## Saving into a wiki vault

If the vault has an AI-chat ingestion schema (e.g. `system/schemas/ai-chat-ingestion.md`), follow whatever raw path, basename rule, sidecar layout, and frontmatter shape it prescribes.

If no schema exists, fall back to this generic pattern:

- raw file under `sources/raw/ai-chats/` (check siblings first — if the vault uses a different naming for provider-rooted content like `sources/raw/conversations/` or `sources/raw/llm-chats/`, match the local convention rather than inventing a new tree)
- one file per conversation; basename `<YYYY-MM-DD>-<provider>-<slug>.md`
- prefer `.md` so Obsidian wikilinks of the form `[[<basename>]]` resolve without an extension hint, and frontmatter wraps cleanly
- frontmatter at minimum:

```yaml
---
source_type: ai-chat
provider: <anthropic|openai|google|xai|cursor|...>
model: <model-id or blank>
url: <share link or blank>
title: <short title>
captured: <YYYY-MM-DD>
note: <optional one-line context>
---
```

- body: the conversation, with speaker turns as `## User` / `## <Assistant>` headings (or whatever shape the schema dictates). Preserve fenced code blocks, inline code, and links.

Treat the written file as immutable per the vault's source rules. If a sidecar JSON export exists (ChatGPT export, Claude.ai export), pair it by basename: `<basename>.md` and `<basename>.json`.

## Offer to hand off to ingest

After the raw file is written, **offer to hand the raw path to `/wiki_keeper:ingest` in the same turn**. Don't make the user copy/paste the path into a separate invocation just to clear the next bookkeeping step. Phrase the offer as a one-word yes/no:

> "Saved raw chat to `<raw-path>`. Run `/wiki_keeper:ingest` on it now?"

This skill does **not** normalize the chat, decide on wiki promotion, or write a log entry — that's `/wiki_keeper:ingest`'s job. Two paths to the same goal would drift; one path keeps the pipeline coherent.

If the user accepts, follow the steps in `commands/ingest.md` (`/wiki_keeper:ingest`) with the raw chat path as the source argument. For long chats, ingest will route to the `wiki-archivist` subagent automatically — let it.

If the user declines, leave the raw file in place and report the path.

The offer is mandatory in every other case. Do **not** skip it because the user only said "save this chat." They don't see the wiki bookkeeping you'd otherwise leave them to do by hand.

Skip only when:

- the vault is uninitialized (no `AGENTS.md`) — there's no ingest pipeline to hand off to, and you should not have written a raw file in the first place
- you were spawned **by** `/wiki_keeper:ingest` (i.e. ingest is calling this skill to capture the raw before continuing the pipeline) — re-prompting would loop

## Caveats

- **Sensitive content.** Chats often contain code, credentials, prompts, or private context. Before writing, scan for anything that looks like a credential, API key, internal hostname, or production secret. If you find one, ask before saving — the raw file is checked into git in many vaults.
- **Provider drift.** A chat from Claude 3.5 Sonnet, GPT-4-turbo, or Gemini 1.5 may assert things a current model would correct. Provenance is the chat itself; do not treat its assertions as evidence on the same footing as primary sources during ingest.
- **Missing system prompts.** Many share-URL exports strip the system prompt. If the chat references unseen context ("you are a..."), capture what you have and note the gap in the `note:` frontmatter.
- **Length.** Long chats can exceed practical context. When handing off to ingest, pass the file path; do not paste the body back into context.
- **Format fidelity.** Speaker labels and turn boundaries matter for downstream normalization. If you stripped or reformatted anything beyond UI noise, note it in `note:`.

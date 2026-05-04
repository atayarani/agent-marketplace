---
name: youtube-transcript
description: Fetch a YouTube video transcript given a URL or video id. Use when the user wants captions/transcript text from a YouTube video — e.g. "transcript for <url>", "ingest this YouTube video into the wiki", "summarize this YouTube talk". Wraps youtube-transcript-api via a self-bootstrapping uv script (no global install needed).
---

You can pull a YouTube transcript on demand. The skill ships a script that
uses [`youtube-transcript-api`](https://pypi.org/project/youtube-transcript-api/)
and self-bootstraps via `uv` PEP 723 inline metadata, so the only host
prerequisite is `uv`.

## When to use this

- The user asks for the transcript of a YouTube URL.
- You're running `/wiki_keeper:ingest` against a YouTube URL and need the
  text before you can summarize.
- The user wants to compare a video's claims against the wiki.

## Prerequisite check

`uv` must be available. If `command -v uv` fails, tell the user and stop —
do not silently fall back to `pip install` against the global interpreter.

## How to invoke

The script lives next to this SKILL.md. Resolve its absolute path from the
skill directory and call it with the URL or 11-character video id.

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/skills/youtube-transcript/fetch_transcript.py" \
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

If `CLAUDE_PLUGIN_ROOT` isn't set in the host (Codex, Gemini), use the
absolute path to this skill's directory directly. The script handles all
common YouTube URL shapes — `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`,
`/live/` — plus a bare video id.

### Flags

- `--languages en es ja` — preferred language codes, in priority order. Defaults to `en`.
- `--format text|json|srt|vtt` — output format. Defaults to `text`.
- `--list` — print available transcripts (language code, label, manual vs auto-generated, translatability) and exit. Use this first when `--languages en` returns no transcript.

### Exit codes

- `0` success
- `2` no transcript in the requested languages (try `--list`)
- `3` transcripts disabled for the video
- `4` video unavailable
- `5` other retrieval failure

## Saving into a wiki vault

If you're inside a `wiki_keeper`-managed vault (i.e. `AGENTS.md` describes
one), the vault's own schemas decide where files land and what shape the
metadata takes. **Read those schemas before writing.** Start with the
vault's `AGENTS.md` and any file it points at under `system/schemas/` —
typically `system/schemas/youtube-ingestion.md` and
`system/schemas/source-normalization.md`. Follow whatever raw path,
basename rule, sidecar layout, and frontmatter shape they prescribe, and
treat the written files as immutable per the vault's source rules. Then
hand off to the normal ingest pipeline — synthesis goes into the wiki,
not the raw transcript file.

If the vault has no YouTube-specific schema, fall back to this generic
pattern:

- raw transcript under `sources/raw/` in whatever subdirectory the vault
  uses for video sources (look at sibling files; do not invent a new tree)
- basename is the 11-character video id, so transcript and any metadata
  sidecar pair unambiguously (e.g. `<video-id>.txt` + `<video-id>.json`)
- if you must capture metadata inline instead of in a sidecar, use
  frontmatter with at minimum: `source_type`, `url`, `video_id`, `title`,
  `channel`, `captured` (YYYY-MM-DD), `language`, `transcript_type`
  (manual / auto)

If the vault is uninitialized, just print the transcript to the user — do
not invent a directory layout.

## Offer to normalize

After the raw file is written, **offer to normalize in the same turn**.
Don't make the user copy/paste the path into a separate `/wiki_keeper:ingest`
invocation just to clear the next bookkeeping step. Phrase the offer
concretely so it's a one-word yes/no:

> "Saved raw transcript to `<raw-path>`. Want me to normalize it into
> `<normalized-path>` now?"

If the user accepts:

1. Re-read the vault's `system/schemas/source-normalization.md` and any
   YouTube-specific schema (`system/schemas/youtube-ingestion.md`) for
   the normalized path, frontmatter shape, and body structure. Follow
   them; do not invent a layout.
2. Write the normalized file. Preserve timestamps if the schema asks
   for them. Strip duplicate caption fragments only when meaning is
   preserved. Do **not** add synthesis, claims, or commentary — that
   belongs in `wiki/`, not `sources/normalized/`.
3. Link the normalized file back to the raw transcript and metadata
   files (per the vault's provenance rule).
4. Stop. Do not promote to wiki pages in the same turn unless the user
   asks. Filing-back happens during ingest/query, not here.

If the user declines, leave the raw file in place and note the path so
they can pick it up later.

Skip the offer entirely when:

- the vault is uninitialized (no `AGENTS.md`)
- the vault has no `sources/normalized/` tree
- the user originally asked only for the transcript text, not for
  ingestion (e.g. "show me the transcript of <url>" with no wiki context)

## Caveats

- Auto-generated transcripts have no punctuation and no speaker labels.
  Note this in any synthesis you produce.
- Transcripts can be long. Prefer streaming the file path to a subagent
  (e.g. `wiki-archivist`) over pasting the whole transcript into context.
- Some videos disable captions or are region-locked. Surface the exit code
  to the user rather than retrying blindly.
- The script does not download audio or video — captions only. If a video
  has no captions of any kind, this skill cannot help.

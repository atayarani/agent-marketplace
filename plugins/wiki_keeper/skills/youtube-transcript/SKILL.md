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

## Offer to hand off to ingest

After the raw file is written, **offer to hand the raw path to
`/wiki_keeper:ingest` in the same turn**. Don't make the user copy/paste
the path into a separate invocation just to clear the next bookkeeping
step. Phrase the offer as a one-word yes/no:

> "Saved raw transcript to `<raw-path>`. Run `/wiki_keeper:ingest` on it
> now?"

This skill does **not** normalize the transcript itself — that lives in
`/wiki_keeper:ingest`, which already knows how to read the vault's
schemas, write the normalized file, decide on wiki promotion, and append
a log entry. Two paths to the same goal would drift; one path keeps the
pipeline coherent.

If the user accepts, follow the steps in
`commands/ingest.md` (`/wiki_keeper:ingest`) with the raw transcript
path as the source argument. For long transcripts, ingest will route to
the `wiki-archivist` subagent automatically — let it.

If the user declines, leave the raw file in place and report the path so
they can pick it up later.

Skip the offer entirely when:

- the vault is uninitialized (no `AGENTS.md`)
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

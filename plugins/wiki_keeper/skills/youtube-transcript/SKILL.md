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
one), write the raw transcript to `sources/raw/transcripts/<slug>.md` with
frontmatter capturing the source URL, video id, channel, fetch date, and
language. Treat that file as immutable per the vault's source rules. Then
hand off to the normal ingest pipeline — synthesis goes into the wiki, not
the raw transcript file.

A reasonable frontmatter:

```yaml
---
source_type: youtube-transcript
url: https://www.youtube.com/watch?v=<id>
video_id: <id>
title: <video title>
channel: <channel>
fetched: <YYYY-MM-DD>
language: <code>
auto_generated: <true|false>
---
```

If the vault is uninitialized, just print the transcript to the user — do
not invent a directory layout.

## Caveats

- Auto-generated transcripts have no punctuation and no speaker labels.
  Note this in any synthesis you produce.
- Transcripts can be long. Prefer streaming the file path to a subagent
  (e.g. `wiki-archivist`) over pasting the whole transcript into context.
- Some videos disable captions or are region-locked. Surface the exit code
  to the user rather than retrying blindly.
- The script does not download audio or video — captions only. If a video
  has no captions of any kind, this skill cannot help.

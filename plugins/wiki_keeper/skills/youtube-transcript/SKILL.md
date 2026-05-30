---
name: youtube-transcript
description: INTERNAL HELPER ONLY — wraps fetch_transcript.py for use by /wiki_keeper:ingest and /wiki_keeper:youtube-tech-list. Not user-facing. Do NOT auto-trigger on natural-language requests to transcribe or ingest YouTube videos — those should route to /wiki_keeper:ingest instead.
---

# Internal helper — YouTube transcript fetcher

**As of 2026-05-30, this skill is no longer user-facing.** The user-facing entry point for ingesting any source (including YouTube videos) is `/wiki_keeper:ingest <url>`. This SKILL.md exists only because `fetch_transcript.py` lives next to it and is still used by two callers:

1. `/wiki_keeper:ingest` — for the YouTube dispatch branch
2. `/wiki_keeper:youtube-tech-list` — to fetch the transcript before triaging projects

## If the user typed `/wiki_keeper:youtube-transcript <url>`

This is the deprecated slash form. Redirect:

1. Tell the user: *"`/wiki_keeper:youtube-transcript` was unified into `/wiki_keeper:ingest` on 2026-05-30. I'll run the ingest flow with the same URL."*
2. Run the `/wiki_keeper:ingest` flow with the URL.

## Script location

```
${CLAUDE_PLUGIN_ROOT}/skills/youtube-transcript/fetch_transcript.py
```

Invocation (handled inside `/wiki_keeper:ingest`):

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/skills/youtube-transcript/fetch_transcript.py" "<url>" --format text
```

Flags: `--languages en es ja` (priority order), `--format text|json|srt|vtt`, `--list`, `--no-fallback`. Exit codes: 0 success / 2 no transcript / 3 disabled / 4 unavailable / 5 retrieval failure.

The script self-bootstraps via `uv` PEP 723 inline metadata. Only host prerequisite: `uv`. Falls back to `yt-dlp --write-auto-subs` on IP-block when yt-dlp is installed.

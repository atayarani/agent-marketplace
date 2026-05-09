---
description: Surface a clickable triage list of OSS / GitHub projects mentioned in a YouTube list-format video. Read-only — never writes to a file.
---

Surface a clickable list of OSS projects mentioned in a YouTube list-format video to the chat for triage.

Use the `youtube-oss-list` skill's SKILL.md for full reference. Brief instructions:

1. **Verify prerequisites**: `command -v uv` and `command -v yt-dlp` both exist. If either is missing, tell the user (`brew install uv` / `brew install yt-dlp`) and stop.

2. **Parse the URL** (`<arguments>`) to extract the 11-character video ID. Accept `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`, or a bare ID. If no URL was provided, ask the user for one.

3. **Fetch metadata + transcript into `/tmp` scratch**:

   ```bash
   yt-dlp --skip-download --write-info-json -o "/tmp/<id>.%(ext)s" "<url>"
   "${CLAUDE_PLUGIN_ROOT:-.}/skills/youtube-transcript/fetch_transcript.py" "<url>" --format text > /tmp/<id>.transcript.txt
   ```

   Both files are scratch; do not copy into the vault.

4. **Extract project URLs from the description** (in `info.json`). Filter out channel-template URLs (Patreon / sponsors / social media), affiliate links, and YouTube self-links. Keep `github.com`, `gitlab.com`, `codeberg.org`, `bitbucket.org`, `sr.ht`, `sourceforge.net`, and clear project homepages.

5. **For each candidate URL, find the matching project name in the description**, then locate its mention in the transcript and summarize the host's take in one sentence (~20-30 words).

6. **Skip half-matches.** If a project appears in the description but not the transcript (or vice versa), drop it — both anchors are required.

7. **Surface to chat only.** Output shape:

   ```markdown
   N projects from "<video title>" by <channel>:

   - **<Project Name>** — <https://github.com/owner/repo>
     <one-sentence blurb>
   - ...
   ```

   Use plain URLs (universally terminal-clickable), not Markdown links. One blurb sentence per project — this is triage, not synthesis.

8. **Do not write any vault file.** No log entry, no list items, no wiki page, no normalized source. The output is ephemeral by design.

## Sensible default invocation

Required argument: a YouTube URL or 11-character video ID. If `<arguments>` is empty, ask the user for the URL.

## Do not

- Run on natural-language requests (e.g. "what projects are in this video?"). The skill is explicit-invocation-only; surface the slash command form and stop.
- Write to any vault file.
- Surface entries that lack either a URL (description side) or a host-take blurb (transcript side).
- Pad blurbs past one sentence.
- Promote any surfaced project to `wiki/entities/tools/` or `lists/` automatically. That's a separate, explicit decision per `AGENTS.md` rule 16.

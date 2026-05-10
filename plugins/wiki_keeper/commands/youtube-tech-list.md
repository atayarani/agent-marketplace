---
description: Surface a clickable triage list of tech projects mentioned in a YouTube list-format video — auto-detects category (OSS / Android / iOS / browser extension / VS Code extension / web tool) by tallying URL hostnames; pass `--type <category>` to override. Read-only — never writes to a file.
---

Surface a clickable list of tech projects mentioned in a YouTube list-format video to the chat for triage.

Use the `youtube-tech-list` skill's SKILL.md for full reference. Brief instructions:

1. **Verify prerequisites**: `command -v uv` and `command -v yt-dlp` both exist. If either is missing, tell the user (`brew install uv` / `brew install yt-dlp`) and stop.

2. **Parse `<arguments>`** — first positional arg is a YouTube URL or 11-character video ID. Optional `--type <category>` selects one of `oss`, `android`, `ios`, `browser-extension`, `vscode-extension`, `web` and bypasses auto-detection. If no URL was provided, ask the user for one.

3. **Fetch metadata + transcript into `/tmp` scratch**:

   ```bash
   yt-dlp --skip-download --write-info-json -o "/tmp/<id>.%(ext)s" "<url>"
   "${CLAUDE_PLUGIN_ROOT:-.}/skills/youtube-transcript/fetch_transcript.py" "<url>" --format text > /tmp/<id>.transcript.txt
   ```

   Both files are scratch; do not copy into the vault.

4. **Extract project URLs from the description** (in `info.json`). Apply the global noise filter (drop Patreon / sponsors / social media / affiliate / YouTube self-links) before category detection.

5. **Auto-detect category** if `--type` was not passed: tally the surviving URLs against per-category whitelists and pick the plurality. Tie-break order: `oss` > `android` > `ios` > `browser-extension` > `vscode-extension` > `web`. Fall back to `web` if no category has at least 2 hits.

   Per-category whitelists:
   - **`oss`**: github.com, gitlab.com, codeberg.org, bitbucket.org, sr.ht, sourceforge.net (plus clear project homepages when paired)
   - **`android`**: play.google.com/store/apps/details, f-droid.org/packages
   - **`ios`**: apps.apple.com, testflight.apple.com
   - **`browser-extension`**: chrome.google.com/webstore, chromewebstore.google.com, addons.mozilla.org, microsoftedge.microsoft.com/addons
   - **`vscode-extension`**: marketplace.visualstudio.com/items, open-vsx.org
   - **`web`**: any non-noise project homepage (catch-all)

6. **For each candidate URL** in the chosen category, find the matching project name in the description, locate its mention in the transcript, and summarize the host's take in one sentence (~20-30 words).

7. **Skip half-matches.** If a project appears in the description but not the transcript (or vice versa), drop it — both anchors are required.

8. **Surface to chat only.** Output shape:

   ```markdown
   N <category> projects from "<video title>" by <channel>:

   - **<Project Name>** — <https://...>
     <one-sentence blurb>
   - ...
   ```

   Lead line names the category in human-readable form (`OSS`, `Android`, `iOS`, `browser extension`, `VS Code extension`, `web tool`) so the user can see how the auto-detection landed and can re-run with `--type <other>` if they want a different lens. Use plain URLs (universally terminal-clickable), not Markdown links. One blurb sentence per project — this is triage, not synthesis.

9. **Do not write any vault file.** No log entry, no list items, no wiki page, no normalized source. The output is ephemeral by design.

## Sensible default invocation

Required argument: a YouTube URL or 11-character video ID. If `<arguments>` is empty, ask the user for the URL.

## Do not

- Run on natural-language requests (e.g. "what apps are in this video?"). The skill is explicit-invocation-only; surface the slash command form and stop.
- Write to any vault file.
- Surface entries that lack either a URL (description side) or a host-take blurb (transcript side).
- Pad blurbs past one sentence.
- Cross category lines — if the chosen category is `oss`, surface only OSS hits, not the stray Play Store link sitting in the description. The user re-runs with `--type <other>` to get the other lens.
- Promote any surfaced project to `wiki/entities/tools/` or `lists/` automatically. That's a separate, explicit decision per `AGENTS.md` rule 16.

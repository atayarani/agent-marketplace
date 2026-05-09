---
name: youtube-oss-list
description: EXPLICIT-INVOCATION-ONLY. Surface a clickable list of OSS / GitHub projects mentioned in a YouTube video, one per project with a one-sentence host-take blurb and a terminal-clickable URL. Read-only — never writes to a vault file. Run **only** when the user has typed `/wiki_keeper:youtube-oss-list <url>` (or the host's equivalent slash form). If this skill matches a natural-language request rather than an explicit slash invocation, refuse to run and surface the slash command form to the user instead.
---

You're surfacing a triage-grade list of OSS projects featured in a YouTube video to the chat for the user to skim. **The output is a per-project bullet list with name + URL + one-sentence blurb, surfaced to chat only and never written to disk.**

## Invocation guardrail (read this first)

**This skill runs ONLY on explicit slash-command invocation** — `/wiki_keeper:youtube-oss-list <url>` on Claude Code, the equivalent on Codex / Gemini.

If you reached this skill because the user said something like *"what projects are in this video?"* / *"give me the GitHub links"* / *"summarize the tools mentioned in <url>"* — or any other natural-language phrasing that semantically matches the skill's job — **do not run it**. Instead:

1. Tell the user the slash command form: *"You can run `/wiki_keeper:youtube-oss-list <url>` for that."*
2. Stop. Don't fetch the video, don't surface bullets, don't pre-process anything.

The reason: this output is explicit-curiosity output, not background bookkeeping. The user wants to ask for it deliberately, not have it appear during other tasks. Accidental auto-invocation is exactly what the skill is designed to avoid.

The slash command body at `commands/youtube-oss-list.md` is the legitimate entry point; running this SKILL.md on its own is the case to refuse.

## When to use this

- The user has typed `/wiki_keeper:youtube-oss-list <url>` against a YouTube list-format video that showcases OSS / GitHub projects (e.g. *"10 Open Source Tools That Feel Illegal"*, *"5 GitHub Repos You Should Know"*).
- The user wants triage-level information — enough to decide which projects are worth a deeper look — without committing to ingesting the video into the vault.

This skill is **not** the right tool for:

- General video summarization (use `/wiki_keeper:youtube-transcript` + `/wiki_keeper:ingest`).
- Wiki promotion / tool-entity creation (that's a separate, explicit decision per `AGENTS.md` rule 16).
- Videos that aren't OSS-list-shaped (a single-project deep-dive, a tutorial, etc.). Refuse politely if the input video doesn't fit the format.

## Prerequisite check

`uv` must be available (the `youtube-transcript` script self-bootstraps via `uv`).
`yt-dlp` must be available — required here, not optional, because the YouTube **description and chapters** are the canonical source of project URLs (the transcript by itself is auto-captioned without URLs).

If either is missing, tell the user (`brew install uv` / `brew install yt-dlp`) and stop.

## Default flow

1. **Parse the URL** to extract the 11-character video ID. Accept `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`, or a bare ID.

2. **Fetch the video metadata** via yt-dlp into a temp file:

   ```bash
   yt-dlp --skip-download --write-info-json -o "/tmp/<video-id>.%(ext)s" "<url>"
   ```

   This produces `/tmp/<video-id>.info.json` containing `title`, `channel`, `description`, and (when present) `chapters` — the structured timestamps the host marked at upload time.

3. **Fetch the transcript** via the existing `youtube-transcript` skill's script:

   ```bash
   "${CLAUDE_PLUGIN_ROOT:-.}/skills/youtube-transcript/fetch_transcript.py" "<url>" --format text > /tmp/<video-id>.transcript.txt
   ```

   `/tmp` is fine for the transcript and info.json — those are scratch files, not vault output. Do not copy either into `sources/raw/`.

4. **Extract project URLs from the description** (see "Description parsing" below). Build a candidate list of `{name, url}` records.

5. **Match each candidate to its transcript section** for a host-take blurb (see "Transcript matching" below).

6. **Surface the list to chat** in the output shape below.

7. **Do not write any files in the vault.** Do not append to `system/log.md`. Do not update any wiki page. Temp files in `/tmp` are fine and get cleaned up by the OS.

## Description parsing

YouTube descriptions for OSS-list videos vary in format. Handle the common shapes:

- **Numbered list with timestamps + separate URL block.** Description leads with `1. ProjectName 0:42 / 2. ProjectName 1:55 / ...` and then a section like `Links: / 1. https://github.com/...`. Match by index.
- **Markdown-style list inline.** `- ProjectName: https://github.com/owner/repo` or `* ProjectName — https://...`.
- **Plain text inline.** `First up is ProjectName, you can find it at https://github.com/...`.
- **Chapter-driven.** `info.json` has a `chapters` array; each chapter title is usually the project name. Pair chapter titles to URLs found in the description body.

**URL filter — keep**:

- `github.com/<owner>/<repo>` — the canonical case.
- `gitlab.com`, `codeberg.org`, `bitbucket.org`, `sr.ht` (Sourcehut), `sourceforge.net`.
- The project's own homepage when it's clearly the project (e.g., `obsidian.md`, `neovim.io`) and a paired GitHub URL is absent.

**URL filter — drop (do not surface)**:

- `youtube.com` / `youtu.be` (the channel's own videos, related links).
- The channel's standing template URLs that appear across many of their videos — Patreon, Discord, Twitter/X, Mastodon, BlueSky, merch shops, sponsor blocks (Brilliant, Squarespace, NordVPN, etc.).
- Affiliate / referral links the host promotes for their own tools.
- Bare documentation URLs when a paired GitHub URL exists for the same project (prefer the repo).

**Sponsor block detection**: most descriptions group sponsor URLs under a header like `Sponsor:` / `Today's video is brought to you by:` / `Promo code:`. Treat anything within those blocks as channel-template noise.

## Transcript matching

For each `{name, url}` candidate from the description:

1. Search the transcript (case-insensitive, with reasonable variant tolerance) for the project name. Auto-captioned transcripts mangle proper nouns frequently — try the exact name first, then a fuzzy match on the most distinctive token.
2. Extract a 1–3 sentence window around the first substantive mention.
3. Summarize the host's take to **one sentence** capturing: what the project does + the host's distinctive angle (why they recommend it, what it solves, who it's for, what's notable).
4. Keep the blurb terse — this is triage, not synthesis. ~20-30 words is the sweet spot.

If the project name appears in the description but **does not** appear in the transcript at all, **skip it** (do not surface). Per the skill spec: link-without-a-take has no triage value. The user is opting into "I might want to read more about this," not "here's a URL I could have found in the description anyway."

If two candidates clearly refer to the same project (e.g., a GitHub URL and a homepage URL), surface only one entry — prefer the GitHub URL.

## Output shape

```markdown
N projects from "<video title>" by <channel>:

- **<Project Name>** — <https://github.com/owner/repo>
  <one-sentence blurb capturing what it does + host's take>
- **<Project Name>** — <https://github.com/owner/repo>
  <one-sentence blurb>
- ...
```

Notes on the shape:

- **Use plain URLs, not Markdown links.** `https://...` is universally clickable in modern terminals (iTerm2, Ghostty, Warp, VS Code, macOS Terminal); `[text](url)` Markdown rendering varies. The bracketed form `<https://...>` is fine — most terminals strip the brackets and linkify the URL.
- **One blurb sentence per project.** Two-sentence blurbs blow past the triage budget; users skimming this are deciding whether to click, not reading prose.
- **Bold the project name; URL on the same line.** Compact and scannable.
- **No closing summary, no analytical wrap-up.** The bullets are the deliverable.
- **Count in the lead** so the user knows how long the list is before they start scanning.

If the list is very long (>15 projects), it's still fine to surface them all — that's the user's signal to either trust the host or pick the highest-stars-in-name picks.

## Edge cases

- **Video with no extractable project URLs.** Tell the user *"I couldn't find OSS project URLs in the description for this video — it may not be a list-format OSS video, or the host puts URLs only in pinned comments."* Stop. Do not fall back to transcript-only fuzzy matching.
- **All projects mentioned in the transcript but description has no URLs.** Same as above — skip. The skill's value depends on URL anchoring.
- **Description is in a language other than English.** Project names + URLs work language-agnostically. Pull what you can; the host-take blurb may be unhelpful if the transcript is in a language you can't summarize naturally — surface a placeholder blurb (e.g., "Foreign-language transcript; project name and URL only.") rather than guessing.
- **Same project appears multiple times.** Sometimes a description has both a "1. Project — https://..." entry and a separate "More info: https://..." link. Dedupe by URL or by project name; keep the one with the clearer blurb context in the transcript.
- **Sponsor projects ambiguously mixed in.** Some channels integrate sponsors into the list (e.g., "today's sponsor is X, and project number 1 is Y"). When the host's take in the transcript reads as ad-copy ("today's sponsor," "use code SAVE10," "thanks to <sponsor> for sponsoring"), drop it.

## Caveats

- **Auto-captioned transcripts mangle proper nouns frequently.** Project names with unusual spellings (Helix, Zellij, Zed) sometimes get captioned phonetically. Fuzzy-match on the distinctive token before giving up.
- **The yt-dlp-fetched description is the upload-time description.** If the host has edited the description since (e.g., adding pinned-comment URLs as a follow-up), this won't catch the edits. That's a known limitation; surface what's in the description we have.
- **Triage, not synthesis.** This skill is the OSS-video parallel to `highlights` — disposable, scan-and-decide output. Do not promote anything to the wiki, do not save anything to the vault, do not log anything. If the user wants a project in the vault, they'll invoke `/wiki_keeper:ingest` separately.

## Do not

- **Run on natural-language requests.** This skill is explicit-invocation-only — the user must have typed the slash command. If you reached this SKILL.md from an ambient phrasing match, surface the slash command to the user and stop. (See "Invocation guardrail" at the top of this file.)
- **Write to any vault file.** No `sources/raw/`, no `sources/normalized/`, no `lists/`, no `wiki/`, no log entry. Temp scratch files in `/tmp` are fine and expected — those don't count.
- **Surface entries that have only a URL or only a transcript mention.** Both are required (URL from description + name in transcript) — the spec is to skip half-matches.
- **Pad blurbs past one sentence.** Triage output. Two sentences is too many.
- **Treat the list as wiki-promotion-worthy.** Even if the host's pitch is glowing, this skill doesn't make the wiki promotion decision. That's an explicit, separate user action.
- **Surface channel-template URLs** (Patreon, sponsor links, social media). Filter ruthlessly.
- **Use Markdown link syntax** (`[text](url)`) where plain URLs would render as clickable in the user's terminal. Plain URLs are more compatible.

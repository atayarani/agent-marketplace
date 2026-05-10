---
name: youtube-tech-list
description: EXPLICIT-INVOCATION-ONLY. Surface a clickable list of tech projects mentioned in a YouTube list-format video — auto-detects category (OSS / GitHub, Android apps, iOS apps, browser extensions, VS Code extensions, generic web tools) by tallying URL hostnames in the description; one bullet per project with a one-sentence host-take blurb and a terminal-clickable URL. Read-only — never writes to a vault file. Run **only** when the user has typed `/wiki_keeper:youtube-tech-list <url> [--type <category>]` (or the host's equivalent slash form). If this skill matches a natural-language request rather than an explicit slash invocation, refuse to run and surface the slash command form to the user instead.
---

You're surfacing a triage-grade list of tech projects featured in a YouTube video to the chat for the user to skim. **The output is a per-project bullet list with name + URL + one-sentence blurb, surfaced to chat only and never written to disk.**

This skill generalizes across tech-list video genres — OSS / GitHub repos, Android apps, iOS apps, browser extensions, VS Code extensions, generic web tools. The category is auto-detected from URL hostnames in the description; an explicit `--type <category>` override is available for edge cases.

## Invocation guardrail (read this first)

**This skill runs ONLY on explicit slash-command invocation** — `/wiki_keeper:youtube-tech-list <url> [--type <category>]` on Claude Code, the equivalent on Codex / Gemini.

If you reached this skill because the user said something like *"what projects are in this video?"* / *"give me the GitHub links"* / *"summarize the apps mentioned in <url>"* — or any other natural-language phrasing that semantically matches the skill's job — **do not run it**. Instead:

1. Tell the user the slash command form: *"You can run `/wiki_keeper:youtube-tech-list <url>` for that."*
2. Stop. Don't fetch the video, don't surface bullets, don't pre-process anything.

The reason: this output is explicit-curiosity output, not background bookkeeping. The user wants to ask for it deliberately, not have it appear during other tasks. Accidental auto-invocation is exactly what the skill is designed to avoid.

The slash command body at `commands/youtube-tech-list.md` is the legitimate entry point; running this SKILL.md on its own is the case to refuse.

## When to use this

- The user has typed `/wiki_keeper:youtube-tech-list <url>` against a YouTube list-format video that showcases tech projects of any category — *"10 Open Source Tools That Feel Illegal"*, *"Best Android Apps of 2026"*, *"15 iOS Apps Every Power User Needs"*, *"7 VS Code Extensions That Will Change Your Life"*, etc.
- The user wants triage-level information — enough to decide which projects are worth a deeper look — without committing to ingesting the video into the vault.

This skill is **not** the right tool for:

- General video summarization (use `/wiki_keeper:youtube-transcript` + `/wiki_keeper:ingest`).
- Wiki promotion / tool-entity creation (that's a separate, explicit decision per `AGENTS.md` rule 16).
- Videos that aren't tech-list-shaped (a single-project deep-dive, a tutorial, etc.). Refuse politely if the input video doesn't fit the format.

## Prerequisite check

`uv` must be available (the `youtube-transcript` script self-bootstraps via `uv`).
`yt-dlp` must be available — required here, not optional, because the YouTube **description and chapters** are the canonical source of project URLs (the transcript by itself is auto-captioned without URLs).

If either is missing, tell the user (`brew install uv` / `brew install yt-dlp`) and stop.

## Default flow

1. **Parse the URL** to extract the 11-character video ID. Accept `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`, or a bare ID.

2. **Parse `--type <category>`** if present. Valid categories: `oss`, `android`, `ios`, `browser-extension`, `vscode-extension`, `web`. If absent, auto-detect (step 5).

3. **Fetch the video metadata** via yt-dlp into a temp file:

   ```bash
   yt-dlp --skip-download --write-info-json -o "/tmp/<video-id>.%(ext)s" "<url>"
   ```

   This produces `/tmp/<video-id>.info.json` containing `title`, `channel`, `description`, and (when present) `chapters` — the structured timestamps the host marked at upload time.

4. **Fetch the transcript** via the existing `youtube-transcript` skill's script:

   ```bash
   "${CLAUDE_PLUGIN_ROOT:-.}/skills/youtube-transcript/fetch_transcript.py" "<url>" --format text > /tmp/<video-id>.transcript.txt
   ```

   `/tmp` is fine for the transcript and info.json — those are scratch files, not vault output. Do not copy either into `sources/raw/`.

5. **Extract candidate URLs from the description** and **auto-detect category** if not overridden (see "Categories and auto-detection" below). Apply the noise filter first; then tally the surviving candidate URLs by category-pattern; pick the category with the plurality of hits. If no category has a clear plurality, fall back to `web`.

6. **Apply the chosen category's URL whitelist** to filter the candidates down to in-category project URLs.

7. **Match each candidate to its transcript section** for a host-take blurb (see "Transcript matching" below).

8. **Surface the list to chat** in the output shape below. Lead with the count *and* the chosen category so the user knows how the auto-detection landed.

9. **Do not write any files in the vault.** Do not append to `system/log.md`. Do not update any wiki page. Temp files in `/tmp` are fine and get cleaned up by the OS.

## Categories and auto-detection

### Category whitelists

Each category has a URL-hostname whitelist. After the global noise filter (below), tally hostnames against these patterns and pick the category with the plurality.

| Category | Whitelisted hostnames | Notes |
|---|---|---|
| **`oss`** | `github.com`, `gitlab.com`, `codeberg.org`, `bitbucket.org`, `sr.ht`, `sourceforge.net` | The original case. Project's own homepage when it's clearly the project (e.g., `obsidian.md`, `neovim.io`) and a paired GitHub URL is absent. |
| **`android`** | `play.google.com/store/apps/details`, `f-droid.org/packages` | Direct APK-distribution sites (`apkmirror.com`, `apkpure.com`) are *not* automatically whitelisted — they're often piracy-adjacent and channel-specific; surface only if the host explicitly cites them. |
| **`ios`** | `apps.apple.com`, `testflight.apple.com` | App Store Connect URLs (`appstoreconnect.apple.com`) are developer-facing and shouldn't appear. |
| **`browser-extension`** | `chrome.google.com/webstore`, `chromewebstore.google.com`, `addons.mozilla.org`, `microsoftedge.microsoft.com/addons` | The 2024 Chrome Web Store URL change introduced `chromewebstore.google.com`; both forms appear in older and newer videos. |
| **`vscode-extension`** | `marketplace.visualstudio.com/items`, `open-vsx.org` | Both the official Microsoft marketplace and the Open VSX (used by VSCodium / Cursor / Eclipse Theia) namespace. |
| **`web`** | Any non-noise project homepage that doesn't match one of the above | Fallback category for tools that live as web apps with no canonical store / repo URL (e.g., `linear.app`, `excalidraw.com`, `notion.so`). The host-take blurb is the primary value here; the URL is just a destination. |

### Auto-detection algorithm

1. Extract all hyperlink-shaped strings from the `description` field of `info.json`.
2. Apply the **global noise filter** (next section). Drop everything matching that.
3. For each surviving URL, classify by category-pattern using the table above. URLs that match multiple categories (rare, but possible) are tallied against their most-specific match — the entry's own URL form usually disambiguates.
4. Pick the category with the highest count of in-category URLs. **Tie-breaker order**: `oss` > `android` > `ios` > `browser-extension` > `vscode-extension` > `web` (most-specific-first).
5. If the chosen category has fewer than 2 in-category URLs, fall back to `web` (the catch-all). A list video should have at least a handful of project URLs; if the description is sparse, surface what you can in `web` mode rather than refuse.
6. Surface the chosen category in the output's count line so the user can see how the detection landed and override with `--type` if it's wrong.

### `--type` override

The user can pass `--type <category>` to bypass auto-detection — useful when:

- The description has a mix (e.g., a video covering both web tools and Android apps; auto-detect picks one and you want the other).
- The auto-detect picked the wrong category because the host put many social/affiliate links in the same patterns.
- The user wants to see what surfaces under a specific lens (e.g., a generic "tech tools" video where they specifically want only the OSS-on-GitHub picks).

When `--type` is passed, skip auto-detection and apply that category's whitelist directly.

## Global noise filter (applies to all categories)

These get dropped before category detection runs:

- `youtube.com` / `youtu.be` (the channel's own videos, related links).
- The channel's standing template URLs that appear across many of their videos — Patreon, Discord, Twitter/X, Mastodon, BlueSky, merch shops, sponsor blocks (Brilliant, Squarespace, NordVPN, etc.).
- Affiliate / referral links the host promotes for their own tools (`*?ref=`, `*?aff=`, `*?utm_source=youtube`).
- Bare documentation URLs when a paired in-category URL exists for the same project (prefer the in-category one).

**Sponsor block detection**: most descriptions group sponsor URLs under a header like `Sponsor:` / `Today's video is brought to you by:` / `Promo code:`. Treat anything within those blocks as channel-template noise.

## Description parsing

YouTube descriptions for tech-list videos vary in format. Handle the common shapes — these all apply regardless of category:

- **Numbered list with timestamps + separate URL block.** Description leads with `1. ProjectName 0:42 / 2. ProjectName 1:55 / ...` and then a section like `Links: / 1. https://...`. Match by index.
- **Markdown-style list inline.** `- ProjectName: https://...` or `* ProjectName — https://...`.
- **Plain text inline.** `First up is ProjectName, you can find it at https://...`.
- **Chapter-driven.** `info.json` has a `chapters` array; each chapter title is usually the project name. Pair chapter titles to URLs found in the description body.

## Transcript matching

For each `{name, url}` candidate that survives the category whitelist:

1. Search the transcript (case-insensitive, with reasonable variant tolerance) for the project name. Auto-captioned transcripts mangle proper nouns frequently — try the exact name first, then a fuzzy match on the most distinctive token.
2. Extract a 1–3 sentence window around the first substantive mention.
3. Summarize the host's take to **one sentence** capturing: what the project does + the host's distinctive angle (why they recommend it, what it solves, who it's for, what's notable).
4. Keep the blurb terse — this is triage, not synthesis. ~20-30 words is the sweet spot.

If the project name appears in the description but **does not** appear in the transcript at all, **skip it** (do not surface). Per the skill spec: link-without-a-take has no triage value. The user is opting into "I might want to read more about this," not "here's a URL I could have found in the description anyway."

If two candidates clearly refer to the same project (e.g., a GitHub URL and a homepage URL), surface only one entry — prefer the in-category URL of whichever category you're operating in.

## Output shape

```markdown
N <category> projects from "<video title>" by <channel>:

- **<Project Name>** — <https://...>
  <one-sentence blurb capturing what it does + host's take>
- **<Project Name>** — <https://...>
  <one-sentence blurb>
- ...
```

The lead line names the category in human-readable form: `OSS`, `Android`, `iOS`, `browser extension`, `VS Code extension`, or `web tool` — so the user can see at a glance how the auto-detection landed.

Notes on the shape:

- **Use plain URLs, not Markdown links.** `https://...` is universally clickable in modern terminals (iTerm2, Ghostty, Warp, VS Code, macOS Terminal); `[text](url)` Markdown rendering varies. The bracketed form `<https://...>` is fine — most terminals strip the brackets and linkify the URL.
- **One blurb sentence per project.** Two-sentence blurbs blow past the triage budget; users skimming this are deciding whether to click, not reading prose.
- **Bold the project name; URL on the same line.** Compact and scannable.
- **No closing summary, no analytical wrap-up.** The bullets are the deliverable.
- **Count + category in the lead** so the user knows the list's length and the lens used.

If the list is very long (>15 projects), it's still fine to surface them all — that's the user's signal to either trust the host or pick the highest-stars-in-name picks.

## Edge cases

- **Video with no extractable project URLs.** Tell the user *"I couldn't find project URLs in the description for this video — it may not be a list-format tech video, or the host puts URLs only in pinned comments."* Stop. Do not fall back to transcript-only fuzzy matching.
- **All projects mentioned in the transcript but description has no URLs.** Same as above — skip. The skill's value depends on URL anchoring.
- **Mixed-category video.** Auto-detect picks the plurality; surface the other categories in a "Notable runner-up category" line at the end if the gap was close (within 25%) and there are at least 3 entries in the runner-up. Or tell the user they can re-run with `--type <other-category>` to get the other half.
- **Description is in a language other than English.** Project names + URLs work language-agnostically. Pull what you can; the host-take blurb may be unhelpful if the transcript is in a language you can't summarize naturally — surface a placeholder blurb (e.g., "Foreign-language transcript; project name and URL only.") rather than guessing.
- **Same project appears multiple times.** Sometimes a description has both a "1. Project — https://..." entry and a separate "More info: https://..." link. Dedupe by URL or by project name; keep the one with the clearer blurb context in the transcript.
- **Sponsor projects ambiguously mixed in.** Some channels integrate sponsors into the list (e.g., "today's sponsor is X, and project number 1 is Y"). When the host's take in the transcript reads as ad-copy ("today's sponsor," "use code SAVE10," "thanks to <sponsor> for sponsoring"), drop it.

## Caveats

- **Auto-captioned transcripts mangle proper nouns frequently.** Project names with unusual spellings (Helix, Zellij, Zed) sometimes get captioned phonetically. Fuzzy-match on the distinctive token before giving up.
- **The yt-dlp-fetched description is the upload-time description.** If the host has edited the description since (e.g., adding pinned-comment URLs as a follow-up), this won't catch the edits. That's a known limitation; surface what's in the description we have.
- **Triage, not synthesis.** This skill is the tech-video parallel to `highlights` — disposable, scan-and-decide output. Do not promote anything to the wiki, do not save anything to the vault, do not log anything. If the user wants a project in the vault, they'll invoke `/wiki_keeper:ingest` separately.
- **Auto-detection is hostname-pattern-based, not semantic.** A video titled "Best Android apps" whose description happens to link mostly to GitHub repos for those apps will detect as `oss`. The `--type android` override exists for this case.

## Do not

- **Run on natural-language requests.** This skill is explicit-invocation-only — the user must have typed the slash command. If you reached this SKILL.md from an ambient phrasing match, surface the slash command to the user and stop. (See "Invocation guardrail" at the top of this file.)
- **Write to any vault file.** No `sources/raw/`, no `sources/normalized/`, no `lists/`, no `wiki/`, no log entry. Temp scratch files in `/tmp` are fine and expected — those don't count.
- **Surface entries that have only a URL or only a transcript mention.** Both are required (URL from description + name in transcript) — the spec is to skip half-matches.
- **Pad blurbs past one sentence.** Triage output. Two sentences is too many.
- **Treat the list as wiki-promotion-worthy.** Even if the host's pitch is glowing, this skill doesn't make the wiki promotion decision. That's an explicit, separate user action.
- **Surface channel-template URLs** (Patreon, sponsor links, social media). Filter ruthlessly.
- **Use Markdown link syntax** (`[text](url)`) where plain URLs would render as clickable in the user's terminal. Plain URLs are more compatible.
- **Cross category lines.** If `oss` is the chosen category, surface only OSS hits — don't quietly include the one Play Store link sitting in the description. The category override is the user's tool for getting the other lens.

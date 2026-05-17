---
description: "Capture a URL to the bookmarks inbox. Reads the URL from the first arg, or from the macOS clipboard if no arg given. Use when the user types /bm:add, says 'save this URL to bookmarks', 'add to /bm', or wants to drop a link into the inbox queue."
argument-hint: "[url] [--commit]"
---

Capture a URL into the bookmark vault's `_inbox/` queue. Single-shot, idempotent.

Use the `add` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` whose first line contains "Bookmarks Vault". Fallbacks (first match wins): `$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`. Error + exit 1 if none match.
2. **Resolve the URL** — `$ARGUMENTS` if given; else `pbpaste`. Trim whitespace.
3. **Validate** — must match `^https?://[^[:space:]]+$`. Else error + exit 1.
4. **Dedup** — `rg -Fx -l "url: $url" $vault --type md`. Hit → echo `already saved: <path>` + exit 0.
5. **Write** to `$vault/_inbox/$(date +%Y%m%d-%H%M%S)-<6id>.md` with frontmatter (`url`, `captured`, `source: cli`).
6. **Echo** the new path.
7. **Optional auto-commit** — when `--commit` is passed and a new inbox file was written, stage just that file and commit with message `bm:add: <url>`. Refuses to commit if the vault has pre-existing staged changes.

## Flags

- `--commit` — after a successful run, auto-commit the changed files with a templated message. Refuses to commit if the vault has pre-existing staged changes (you can stage them yourself first, run without --commit, or unstage them).

## Do not

- Normalize the URL (lowercase, strip query strings) — store verbatim.
- Commit anything to git unless `--commit` is passed.
- Write to the file body — frontmatter only; `/bm:enrich` adds content later.

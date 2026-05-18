---
description: "Open the bm vault's web UI in your default browser. Requires the bm bookmarklet daemon (install via /bm:install). Use when the user types /bm:web, says 'show me the bookmarks', or wants to browse the vault visually."
argument-hint: "[--url] [--health]"
---

Open the bm web UI at `http://localhost:9876/` in the default browser. The UI is served by the existing bookmarklet daemon — same port, same launchd process, no new daemon.

Use the `web` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Parse args** — `--url` prints the URL only; `--health` prints daemon health JSON only; no flags = open the browser.
2. **Health-check** — `curl http://127.0.0.1:9876/health`. If unreachable, error with hint to `/bm:install`.
3. **Open** — `open` (macOS) or `xdg-open` (Linux) on `http://localhost:9876/`. Also prints the URL so you can copy if needed.

## Flags

- `--url` — print `http://localhost:9876/` and exit (useful for piping or clipboard).
- `--health` — print the daemon's `/health` JSON and exit (debugging).
- (no flag) — open the UI in the default browser.

## Examples

- `/bm:web` — open the UI.
- `/bm:web --url | pbcopy` — copy the URL.
- `/bm:web --health` — verify daemon is up before opening.

## Notes

- **No new port.** The UI lives at the same `127.0.0.1:9876` as the bookmarklet endpoint.
- **No build step or dependencies.** Frontend is vanilla HTML/JS/CSS served straight from the plugin.
- **Always live.** Daemon walks the vault on each request — refresh the browser (or click the ↻ button) to see the latest state.

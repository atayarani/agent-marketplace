---
description: "Install (or manage) the bm bookmarklet daemon. Generates ~/Library/LaunchAgents/com.<user>.bm.plist with resolved paths, loads it via launchctl, and prints the bookmarklet for installation in your browser. Subflags: --status, --reload, --uninstall. Use when the user types /bm:install, says 'set up the bookmarklet', 'install the bm daemon', or wants to fix a stopped daemon."
argument-hint: "[--status] [--reload] [--uninstall]"
---

Install, manage, or remove the bm bookmarklet daemon (launchd user agent listening on `127.0.0.1:9876`).

Use the `install` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up + fallbacks (`$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`). Error + exit 1 if none.
2. **Resolve plugin paths** — `server.py`, `launchagent.plist.tmpl`, `bookmarklet.min.js` from `$CLAUDE_PLUGIN_ROOT/server/` (or computed from `$BASH_SOURCE`).
3. **Generate plist** at `~/Library/LaunchAgents/com.<whoami>.bm.plist`, substituting `{{LABEL}}`, `{{SERVER_PATH}}`, `{{LOG_DIR}}` (`~/.claude/logs`), `{{VAULT_PATH}}`.
4. **Reload** — `launchctl unload` (ignore failure), then `launchctl load`.
5. **Verify** — `curl -fsS http://localhost:9876/health` (retry up to 3× with 1s sleep). Print the JSON response.
6. **Print bookmarklet** — `cat server/bookmarklet.min.js`. Tell the user: copy this into a browser bookmark's URL field.

## Flags

- `--status` — print launchctl status + `/health` JSON; no install changes.
- `--reload` — regenerate plist (picks up vault/plugin path changes), unload, reload.
- `--uninstall` — `launchctl unload` + delete plist. Logs in `~/.claude/logs/` are preserved.

## Do not

- Bind to `0.0.0.0` — daemon is loopback-only by design.
- Modify the user's existing `LaunchAgents/` plists beyond `com.<whoami>.bm.plist`.
- Commit the plist into the plugin repo (it lives in `~/Library/LaunchAgents/`, generated locally).

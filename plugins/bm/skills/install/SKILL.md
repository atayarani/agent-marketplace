---
name: install
description: "Install / manage / uninstall the bm bookmarklet daemon (launchd user agent on 127.0.0.1:9876). Default action installs; --status prints health; --reload regenerates+reloads; --uninstall removes. Use when the user types /bm:install, asks to set up the bookmarklet, or wants to fix a stopped daemon."
argument-hint: "[--status] [--reload] [--uninstall]"
---

Install or manage the bm bookmarklet daemon — a pure-stdlib Python HTTP server running under launchd, listening on `127.0.0.1:9876`, that turns one-click browser saves into inbox files in the bookmark vault.

`$ARGUMENTS` carries any flags the user passed.

---

## 1. Locate the vault

Walk up from `$PWD`; fall back to `$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`. Identify the vault by its `AGENTS.md` first line containing "Bookmarks Vault".

```bash
vault=""
d="$PWD"
while [ "$d" != "/" ]; do
  if [ -f "$d/AGENTS.md" ] && head -1 "$d/AGENTS.md" | grep -q "Bookmarks Vault"; then
    vault="$d"; break
  fi
  d=$(dirname "$d")
done
for candidate in "$BM_VAULT" "$HOME/Documents/obsidian/whiskers" "$HOME/Documents/whiskers" "$HOME/whiskers"; do
  [ -n "$vault" ] && break
  [ -z "$candidate" ] && continue
  if [ -f "$candidate/AGENTS.md" ] && head -1 "$candidate/AGENTS.md" | grep -q "Bookmarks Vault"; then
    vault="$candidate"
  fi
done
[ -z "$vault" ] && { echo "error: bookmarks vault not found" >&2; exit 1; }
```

## 2. Resolve plugin paths

The plugin root contains `server/server.py`, `server/launchagent.plist.tmpl`, and `server/bookmarklet.min.js`. Use `$CLAUDE_PLUGIN_ROOT` if exported, else compute from this skill's path.

```bash
if [ -n "$CLAUDE_PLUGIN_ROOT" ] && [ -d "$CLAUDE_PLUGIN_ROOT/server" ]; then
  plugin_root="$CLAUDE_PLUGIN_ROOT"
else
  # ~/.claude/plugins/marketplaces/agent-marketplace/plugins/bm/
  plugin_root="$HOME/.claude/plugins/marketplaces/agent-marketplace/plugins/bm"
fi
server_py="$plugin_root/server/server.py"
plist_tmpl="$plugin_root/server/launchagent.plist.tmpl"
bookmarklet="$plugin_root/server/bookmarklet.min.js"
for f in "$server_py" "$plist_tmpl" "$bookmarklet"; do
  [ -f "$f" ] || { echo "error: missing plugin file: $f" >&2; exit 1; }
done
```

## 3. Compute install paths

```bash
user=$(whoami)
label="com.${user}.bm"
plist_path="$HOME/Library/LaunchAgents/${label}.plist"
log_dir="$HOME/.claude/logs"
mkdir -p "$log_dir" "$(dirname "$plist_path")"
```

## 4. Parse arguments

Tokens in `$ARGUMENTS`:
- `--status` — print launchctl + /health, no other action.
- `--reload` — regenerate plist, then unload+load (picks up vault/plugin path changes).
- `--uninstall` — unload + delete plist; leaves `$log_dir` intact.

Default (no flags) = install (or refresh) and verify.

```bash
mode="install"
for tok in $ARGUMENTS; do
  case "$tok" in
    --status)    mode="status" ;;
    --reload)    mode="reload" ;;
    --uninstall) mode="uninstall" ;;
    *) echo "error: unknown flag: $tok" >&2; exit 2 ;;
  esac
done
```

## 5. Mode: `status`

```bash
if [ "$mode" = "status" ]; then
  echo "plist: $plist_path"
  if [ -f "$plist_path" ]; then echo "  (present)"; else echo "  (missing)"; fi
  echo
  echo "launchctl list | grep $label:"
  launchctl list 2>/dev/null | grep -F "$label" || echo "  (not loaded)"
  echo
  echo "GET /health:"
  curl -fsS --max-time 2 http://localhost:9876/health || echo "  (unreachable)"
  echo
  exit 0
fi
```

## 6. Mode: `uninstall`

```bash
if [ "$mode" = "uninstall" ]; then
  [ -f "$plist_path" ] && launchctl unload "$plist_path" 2>/dev/null || true
  rm -f "$plist_path"
  echo "Uninstalled: $plist_path removed."
  echo "Logs preserved at: $log_dir/bm-server.{out,err}.log"
  exit 0
fi
```

## 7. Mode: `install` and `reload` — generate plist

Both modes regenerate the plist from the template (idempotent — captures any path changes since the last install). Use `sed` with `|` as delimiter so paths containing `/` don't need escaping.

```bash
tmp_plist=$(mktemp)
sed \
  -e "s|{{LABEL}}|$label|g" \
  -e "s|{{SERVER_PATH}}|$server_py|g" \
  -e "s|{{LOG_DIR}}|$log_dir|g" \
  -e "s|{{VAULT_PATH}}|$vault|g" \
  "$plist_tmpl" > "$tmp_plist"

# Only rewrite if content changed (cheap idempotency)
if [ -f "$plist_path" ] && cmp -s "$tmp_plist" "$plist_path"; then
  plist_changed="false"
else
  mv "$tmp_plist" "$plist_path"
  plist_changed="true"
fi
[ -f "$tmp_plist" ] && rm -f "$tmp_plist"
```

## 8. Load/reload

If plist changed, or mode is `reload`, perform unload+load. Otherwise leave the running daemon alone.

```bash
if [ "$mode" = "reload" ] || [ "$plist_changed" = "true" ]; then
  launchctl unload "$plist_path" 2>/dev/null || true
  launchctl load "$plist_path" || { echo "error: launchctl load failed" >&2; exit 1; }
  echo "Loaded $label"
else
  # Ensure it's actually running (first install or after a manual unload)
  if ! launchctl list 2>/dev/null | grep -qF "$label"; then
    launchctl load "$plist_path" || { echo "error: launchctl load failed" >&2; exit 1; }
    echo "Loaded $label (was not running)"
  else
    echo "$label already running"
  fi
fi
```

## 9. Verify

Poll `/health` with up to 3 attempts × 1s sleep. Daemon takes a moment to bind the port after launchctl load.

```bash
ok=""
for _ in 1 2 3; do
  resp=$(curl -fsS --max-time 2 http://localhost:9876/health 2>/dev/null) && { ok="$resp"; break; }
  sleep 1
done
if [ -z "$ok" ]; then
  echo "warning: daemon failed health check after 3s — check $log_dir/bm-server.err.log" >&2
else
  echo "Health: $ok"
fi
```

## 10. Print the bookmarklet

```bash
echo
echo "Bookmarklet — drag this link to your browser's bookmarks bar, or"
echo "create a new bookmark and paste the line below into its URL field:"
echo
cat "$bookmarklet"
echo
echo "Daemon endpoint: http://127.0.0.1:9876 (loopback only)"
echo "Logs:            $log_dir/bm-server.{out,err}.log"
echo "Manage:          /bm:install --status | --reload | --uninstall"
```

## Notes

- Daemon binds to `127.0.0.1` only. Never `0.0.0.0`. Same-machine processes can reach it; remote hosts cannot.
- `KeepAlive: true` + `RunAtLoad: true` in the plist mean the daemon auto-starts at login and auto-restarts on crash (with a 5s throttle).
- `BM_VAULT` is baked into the plist `EnvironmentVariables` at install time, so the daemon doesn't have to walk-search on every restart.
- The plist `Label` includes `whoami` so the daemon is namespaced per-user (and doesn't collide if multiple users share a host).
- Bookmark file naming, dedup, and inbox schema match `/bm:add` — see `skills/add/SKILL.md`. The only additive difference is `source: bookmarklet` (vs. `cli`) and an optional `title:` field that `/bm:enrich` may use as a fallback.

## Do not

- Bind to anything other than `127.0.0.1`.
- Sudo. `launchctl load` of `~/Library/LaunchAgents/` plists runs as the user.
- Add cron/at fallbacks for non-macOS. v3 is macOS-only; Linux is out of scope.
- Auto-install browser bookmarks. The user installs the bookmarklet by drag-and-drop — we just print the string.

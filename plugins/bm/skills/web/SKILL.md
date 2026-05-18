---
name: web
description: "Open the bm vault's web UI in your default browser. Requires the bm bookmarklet daemon (install via /bm:install). Use when the user types /bm:web, says 'show me the bookmarks', or wants to browse the vault visually."
argument-hint: "[--url] [--health]"
---

Open the bm web UI in the default browser. The UI is served by the existing bookmarklet daemon at `http://localhost:9876/`; this skill is a tiny convenience wrapper that health-checks the daemon and shells out to `open` (macOS) or `xdg-open` (Linux).

`$ARGUMENTS` carries optional flags.

---

## 1. Parse arguments

```bash
mode="open"
set -- $ARGUMENTS
while [ $# -gt 0 ]; do
  case "$1" in
    --url)    mode="url";    shift ;;
    --health) mode="health"; shift ;;
    --*)      echo "error: unknown flag $1" >&2; exit 2 ;;
    *)        echo "error: unexpected positional arg $1" >&2; exit 2 ;;
  esac
done

URL="http://localhost:9876/"
HEALTH="http://127.0.0.1:9876/health"
```

## 2. `--url` short-circuit

If `mode = url`, print the URL and exit 0.

```bash
if [ "$mode" = "url" ]; then
  echo "$URL"
  exit 0
fi
```

## 3. Health check

Probe the daemon. If it's not running, print a clear hint and exit 1.

```bash
health=$(curl -fsS --max-time 2 "$HEALTH" 2>/dev/null || true)
if [ -z "$health" ]; then
  echo "error: bm daemon not running on 127.0.0.1:9876" >&2
  echo "  hint: install or restart it with /bm:install" >&2
  exit 1
fi
```

## 4. `--health` short-circuit

If `mode = health`, print the health JSON and exit 0.

```bash
if [ "$mode" = "health" ]; then
  echo "$health"
  exit 0
fi
```

## 5. Open in browser

Print the URL first (so the user can copy if the browser open silently fails), then shell out to the platform opener.

```bash
echo "opening $URL"
case "$(uname -s)" in
  Darwin) open "$URL" 2>&1 || true ;;
  Linux)  xdg-open "$URL" 2>&1 || true ;;
  *)      echo "(unknown OS — open $URL manually)" ;;
esac
```

## Verification gate

- `/bm:web --url` → prints `http://localhost:9876/`, exits 0.
- `/bm:web --health` (daemon running) → prints `{"ok":true,"vault":"…","inbox_count":N}`, exits 0.
- `/bm:web` (daemon running) → prints `opening …`; browser opens to the UI.
- `/bm:web` (daemon stopped) → prints the daemon-not-running error and the `/bm:install` hint, exits 1.
- `/bm:web --nonsense` → unknown-flag error, exits 2.
- `/bm:web something extra` → unexpected-positional error, exits 2.

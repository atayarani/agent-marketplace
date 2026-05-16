---
name: add
description: "Capture a URL to the bookmarks inbox. Reads the URL from the first arg, or from the macOS clipboard if no arg given. Use when the user types /bm:add, says 'save this URL to bookmarks', 'add to /bm', or wants to drop a link into the inbox queue."
argument-hint: "[url]"
---

Capture a URL into the bookmark vault's `_inbox/` queue. Single-shot, idempotent (dedups by URL). Shell-only — no Python.

## Logic

Run as one bash block. `$ARGUMENTS` is the user's slash-command argument (empty string if none).

```bash
set -e

# 1. Locate the vault (walk up from PWD; fallback to ~/Documents/bookmarks)
vault=""
d="$PWD"
while [ "$d" != "/" ]; do
  if [ -f "$d/AGENTS.md" ] && head -1 "$d/AGENTS.md" | grep -q "Bookmarks Vault"; then
    vault="$d"; break
  fi
  d=$(dirname "$d")
done
if [ -z "$vault" ] && [ -f "$HOME/Documents/whiskers/AGENTS.md" ] \
   && head -1 "$HOME/Documents/whiskers/AGENTS.md" | grep -q "Bookmarks Vault"; then
  vault="$HOME/Documents/whiskers"
fi
[ -z "$vault" ] && { echo "error: bookmarks vault not found" >&2; exit 1; }

# 2. Resolve URL: $ARGUMENTS if non-empty, else pbpaste
raw="${ARGUMENTS:-$(pbpaste)}"
url=$(printf '%s' "$raw" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
[ -z "$url" ] && { echo "error: no URL provided (arg empty, clipboard empty)" >&2; exit 1; }

# 3. Validate
if ! printf '%s' "$url" | grep -Eq '^https?://[^[:space:]]+$'; then
  echo "error: not a valid http(s) URL: $url" >&2; exit 1
fi

# 4. Dedup (fixed-string whole-line; safe for regex metachars in URLs)
hit=$(rg -Fx -l "url: $url" "$vault" --type md 2>/dev/null | head -1 || true)
if [ -n "$hit" ]; then
  echo "already saved: $hit"; exit 0
fi

# 5. Compute 6id from URL
sixid=$(printf '%s' "$url" | shasum | head -c 6)

# 6. Write the inbox file
ts=$(date +%Y%m%d-%H%M%S)
captured=$(date -Iseconds)
out="$vault/_inbox/${ts}-${sixid}.md"
cat > "$out" <<EOF
---
url: $url
captured: $captured
source: cli
---
EOF

# 7. Echo the absolute path
echo "$out"
```

## Notes

- URL stored verbatim — do not normalize, lowercase, or strip query strings. Dedup compares raw URL strings.
- `date -Iseconds` on macOS produces `2026-05-15T14:30:12-07:00` — the local-TZ format the vault expects.
- No git commit. The user commits manually at milestones.
- Empty clipboard with no arg → error, no file written.
- File body is empty (frontmatter only). `/bm:enrich` (Phase 1.C) adds title/excerpt.

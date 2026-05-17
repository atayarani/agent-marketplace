---
name: add
description: "Capture a URL to the bookmarks inbox. Reads the URL from the first arg, or from the macOS clipboard if no arg given. Use when the user types /bm:add, says 'save this URL to bookmarks', 'add to /bm', or wants to drop a link into the inbox queue."
argument-hint: "[url] [--commit]"
---

Capture a URL into the bookmark vault's `_inbox/` queue. Single-shot, idempotent (dedups by URL). Shell-only — no Python.

## Logic

Run as one bash block. `$ARGUMENTS` is the user's slash-command argument (URL plus optional `--commit`; empty string if none).

```bash
set -e

# 1. Locate the vault (walk up from PWD; fallback: $BM_VAULT, then ~/Documents/obsidian/whiskers, ~/Documents/whiskers, ~/whiskers — first match wins)
vault=""
d="$PWD"
while [ "$d" != "/" ]; do
  if [ -f "$d/AGENTS.md" ] && head -1 "$d/AGENTS.md" | grep -q "Bookmarks Vault"; then
    vault="$d"; break
  fi
  d=$(dirname "$d")
done
# Fallback: $BM_VAULT env var, then known default locations (first match wins).
for candidate in "$BM_VAULT" "$HOME/Documents/obsidian/whiskers" "$HOME/Documents/whiskers" "$HOME/whiskers"; do
  [ -n "$vault" ] && break
  [ -z "$candidate" ] && continue
  if [ -f "$candidate/AGENTS.md" ] && head -1 "$candidate/AGENTS.md" | grep -q "Bookmarks Vault"; then
    vault="$candidate"
  fi
done
[ -z "$vault" ] && { echo "error: bookmarks vault not found" >&2; exit 1; }

# 2. Parse args: extract --commit flag; remaining tokens form the URL candidate
commit_flag="false"
remaining=""
for tok in $ARGUMENTS; do
  case "$tok" in
    --commit) commit_flag="true" ;;
    *) remaining="${remaining:+$remaining }$tok" ;;
  esac
done

# Resolve URL: remaining-after-flag-strip if non-empty, else pbpaste
raw="${remaining:-$(pbpaste)}"
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

# 8. Optional auto-commit (only when --commit and a new file was written)
if [ "$commit_flag" = "true" ]; then
  pre_staged=$(git -C "$vault" diff --cached --name-only)
  if [ -n "$pre_staged" ]; then
    echo "warning: vault has pre-existing staged changes; skipping auto-commit" >&2
    echo "staged before this run:" >&2
    printf '  %s\n' "$pre_staged" >&2
  else
    git -C "$vault" add "$out"
    if [ -z "$(git -C "$vault" diff --cached --name-only)" ]; then
      :  # nothing to commit (defensive — shouldn't fire on add path)
    else
      git -C "$vault" commit -m "bm:add: $url"
    fi
  fi
fi
```

## Notes

- URL stored verbatim — do not normalize, lowercase, or strip query strings. Dedup compares raw URL strings.
- `date -Iseconds` on macOS produces `2026-05-15T14:30:12-07:00` — the local-TZ format the vault expects.
- No git commit unless `--commit` is passed. The user commits manually at milestones otherwise.
- Empty clipboard with no arg → error, no file written.
- File body is empty (frontmatter only). `/bm:enrich` (Phase 1.C) adds title/excerpt.
- Dedup hit (`already saved: ...`) exits **before** the auto-commit step, so a re-run on the same URL creates no commit.

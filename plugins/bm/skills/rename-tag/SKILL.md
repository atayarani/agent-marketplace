---
name: rename-tag
description: "Rename a tag everywhere in the bm vault — `tags:` / `proposed_tags:` / `imported_tags:` references, plus the `tags.yaml` entry. If the new name already exists in `tags.yaml`, merges the old name into the new entry's aliases. Lists that already had both old and new dedupe on rewrite. Idempotent. Use when the user types /bm:rename-tag, says 'rename tag X to Y', or wants to merge a synonym."
argument-hint: "<from> <to> [--dry-run] [--commit]"
---

Rename a tag across the entire vault. Affects:

- Filed bookmarks under `<collection>/`, `_unsorted/`, `_broken/` — `tags:` and `proposed_tags:` rewritten. A bookmark that had both `<from>` and `<to>` gets deduplicated to a single `<to>`.
- Inbox files under `_inbox/` — `imported_tags:` rewritten so the next `/bm:enrich` carries the new name.
- `tags.yaml`:
  - If `<to>` does NOT yet exist: rename the `<from>` entry's `name:` to `<to>`. Description and aliases are preserved.
  - If `<to>` already exists: delete `<from>`'s entry; append `<from>` (and its previous aliases) to `<to>`'s `aliases:` list. Preserves discoverability — a future Raindrop re-import using the old name still routes here.

Doesn't touch `_trash/` or `_failed/`.

`$ARGUMENTS` carries the positional `<from> <to>` plus optional flags.

---

## 1. Locate the vault

Walk up from `$PWD` for a directory whose `AGENTS.md` first line contains "Bookmarks Vault". If walk-up fails, try `$BM_VAULT`, then `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/` — first match wins.

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

## 2. Parse arguments

```bash
script_dir="${CLAUDE_PLUGIN_ROOT:-/Users/ali/.claude/plugins/marketplaces/agent-marketplace/plugins/bm}/skills/rename-tag/lib"

from_tag=""
to_tag=""
dry_run=false
commit_flag=false

set -- $ARGUMENTS
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  dry_run=true;     shift ;;
    --commit)   commit_flag=true; shift ;;
    --*)        echo "error: unknown flag $1" >&2; exit 2 ;;
    *)
      if [ -z "$from_tag" ]; then from_tag="$1"
      elif [ -z "$to_tag" ]; then to_tag="$1"
      else echo "error: extra positional arg: $1" >&2; exit 2
      fi
      shift ;;
  esac
done

if [ -z "$from_tag" ] || [ -z "$to_tag" ]; then
  echo "usage: /bm:rename-tag <from> <to> [--dry-run] [--commit]" >&2
  exit 2
fi
if [ "$from_tag" = "$to_tag" ]; then
  echo "error: <from> and <to> are identical: '$from_tag'" >&2
  exit 1
fi
```

## 3. Dispatch

```bash
extra_args=()
[ "$dry_run" = "true" ] && extra_args+=("--dry-run")
"$script_dir/rename_tag.py" "$vault" "$from_tag" "$to_tag" ${extra_args[@]+"${extra_args[@]}"}
rc=$?
```

The script prints a markdown report (affected files, planned `tags.yaml` change) and either ends with `_(--dry-run: no changes written)_` or an `## Applied` section.

## 4. Optional `--commit`

```bash
if [ "$commit_flag" = "true" ] && [ "$dry_run" = "false" ] && [ $rc -eq 0 ]; then
  pre_staged=$(git -C "$vault" diff --cached --name-only)
  if [ -n "$pre_staged" ]; then
    echo "warning: vault has pre-existing staged changes; skipping auto-commit" >&2
    printf '  %s\n' "$pre_staged" >&2
  else
    git -C "$vault" add -u
    git -C "$vault" add tags.yaml 2>/dev/null || true
    if [ -n "$(git -C "$vault" diff --cached --name-only)" ]; then
      n=$(git -C "$vault" diff --cached --name-only | wc -l | tr -d ' ')
      git -C "$vault" commit -m "bm:rename-tag: $from_tag → $to_tag ($n files touched)"
    fi
  fi
fi
```

The pre-existing-staged-changes refusal mirrors `enrich/SKILL.md` step 7.

## Verification gate

Sandbox at `/tmp/bm-qol-vault` per the plan:

- `/bm:rename-tag alpha beta --dry-run` (beta exists → merge case) — report shows 4+1 affected, no changes on disk.
- `/bm:rename-tag alpha beta` — all references → `beta`; `has-both.md` dedups; `alpha`'s tags.yaml entry deleted; `alpha` + `alphabet` absorbed into `beta`'s aliases.
- Re-run → 0 affected, `_No occurrences of alpha found_`.
- `/bm:rename-tag gamma delta` (delta doesn't exist → pure rename) — `gamma`'s entry's `name:` becomes `delta`; description and aliases preserved.

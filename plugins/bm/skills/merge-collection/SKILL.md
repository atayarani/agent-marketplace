---
name: merge-collection
description: "Merge collection `<from>` into `<to>`. Moves every bookmark from `<from>/*.md` into `<to>/` (with collision suffix on duplicate filenames), rewrites `imported_collection:` in inbox files and `proposed_collection.name:` in filed bookmarks, then deletes `<from>/` entirely. Uses `git mv` so renames stay clean in history. Use when the user types /bm:merge-collection or wants to consolidate two collection directories."
argument-hint: "<from> <to> [--dry-run] [--commit]"
---

Merge collection `<from>` into `<to>`. Affects:

- Bookmark files in `<from>/` move to `<to>/` (via `git mv` when the vault is a git repo).
- Name collision: `<to>/<basename>` already exists → moved file is renamed `<stem>-<6-char-sha1(url)><suffix>`, cascading to `-N` if that also collides. Mirrors the pattern in `audit/lib/audit_links.py:move_to_broken`.
- `_inbox/*.md` files whose `imported_collection:` canonicalizes to `<from>` get rewritten to `<to>` so future enrichments file into the merged target.
- Filed bookmarks whose `proposed_collection.name` equals `<from>` get rewritten to `<to>` (description preserved).
- After all moves: `<from>/README.md` deleted and `<from>/` directory removed. (If `<from>/` contains anything beyond `.md` files + README.md, `rmdir` fails loudly and the dir is left in place for you to inspect.)

Doesn't touch `_trash/` or `_failed/`.

`$ARGUMENTS` carries positional `<from> <to>` plus optional flags.

---

## 1. Locate the vault

Same walk-up + `$BM_VAULT` fallback pattern used elsewhere.

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
script_dir="${CLAUDE_PLUGIN_ROOT:-/Users/ali/.claude/plugins/marketplaces/agent-marketplace/plugins/bm}/skills/merge-collection/lib"

from_dir=""
to_dir=""
dry_run=false
commit_flag=false

set -- $ARGUMENTS
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  dry_run=true;     shift ;;
    --commit)   commit_flag=true; shift ;;
    --*)        echo "error: unknown flag $1" >&2; exit 2 ;;
    *)
      if [ -z "$from_dir" ]; then from_dir="$1"
      elif [ -z "$to_dir" ]; then to_dir="$1"
      else echo "error: extra positional arg: $1" >&2; exit 2
      fi
      shift ;;
  esac
done

if [ -z "$from_dir" ] || [ -z "$to_dir" ]; then
  echo "usage: /bm:merge-collection <from> <to> [--dry-run] [--commit]" >&2
  exit 2
fi
if [ "$from_dir" = "$to_dir" ]; then
  echo "error: <from> and <to> are identical: '$from_dir'" >&2
  exit 1
fi
```

## 3. Dispatch

```bash
extra_args=()
[ "$dry_run" = "true" ] && extra_args+=("--dry-run")
"$script_dir/merge_collection.py" "$vault" "$from_dir" "$to_dir" ${extra_args[@]+"${extra_args[@]}"}
rc=$?
```

The script:
- Validates both dirs exist with a `README.md`.
- Plans the moves (with collision suffixes) and inbox/proposed_collection rewrites.
- Prints the plan; exits after if `--dry-run`.
- Applies via `git mv` (or `Path.rename` fallback), deletes `<from>/README.md`, `rmdir <from>/`.

Exit codes:
- 0 on success or empty merge
- 1 on validation failure (missing dir, missing README, identical args, etc.)

## 4. Optional `--commit`

```bash
if [ "$commit_flag" = "true" ] && [ "$dry_run" = "false" ] && [ $rc -eq 0 ]; then
  pre_staged=$(git -C "$vault" diff --cached --name-only)
  if [ -n "$pre_staged" ]; then
    echo "warning: vault has pre-existing staged changes; skipping auto-commit" >&2
    printf '  %s\n' "$pre_staged" >&2
  else
    git -C "$vault" add -A "$from_dir" "$to_dir" 2>/dev/null || true
    git -C "$vault" add -u
    if [ -n "$(git -C "$vault" diff --cached --name-only)" ]; then
      n=$(git -C "$vault" diff --cached --name-only | wc -l | tr -d ' ')
      git -C "$vault" commit -m "bm:merge-collection: $from_dir → $to_dir ($n bookmarks moved)"
    fi
  fi
fi
```

The pre-existing-staged-changes refusal mirrors `enrich/SKILL.md` step 7.

## Verification gate

Sandbox at `/tmp/bm-qol-vault` per the plan (collection-a contains a slug that collides with one in collection-b):

- `/bm:merge-collection collection-a collection-b --dry-run` → report shows 3 moves (2 plain + 1 collision), 1 inbox rewrite, 1 proposed_collection rewrite; no changes.
- `/bm:merge-collection collection-a collection-b` → moves applied with collision suffix `-<6-char-sha1>`; `collection-a/` removed; inbox `imported_collection: "collection-a"` rewritten to `collection-b`; filed `proposed_collection.name: collection-a` rewritten to `collection-b`. `git status` shows clean renames (R lines).
- Re-run → exits 1 with `error: source collection not found`.
- Edge: `<to>` doesn't exist → exit 1 with `mkdir + README.md` hint.

## Notes

- **Description on the destination README.md is left untouched.** If you want to merge descriptions, edit `<to>/README.md` by hand afterwards. The old description is preserved in git history of `<from>/README.md`.
- **`<from>` must contain only `.md` files (and a README.md).** Subdirs or non-md files block `rmdir` — surfaced as a warning so you can investigate.
- **Sibling to `/bm:rename-tag` and `/bm:purge-tag`.** These three together cover the audit's proposed actions for vocabulary maintenance.

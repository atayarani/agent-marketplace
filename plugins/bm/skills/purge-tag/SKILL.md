---
name: purge-tag
description: "Remove a tag from the bm vault entirely — every `tags:` / `proposed_tags:` / `imported_tags:` reference, plus its `tags.yaml` entry (and any aliases referencing it from other entries). Use after `/bm:audit tags` flags a tag as rare or noise that should go away. Idempotent. Use when the user types /bm:purge-tag, says 'remove tag X', or 'kill that bad tag everywhere'."
argument-hint: "<tag> [--dry-run] [--commit]"
---

Bulk-remove a tag from the bm vault. Affects:

- Filed bookmarks under `<collection>/`, `_unsorted/`, `_broken/` — tag dropped from `tags:` and `proposed_tags:`. A bookmark that ends up with `tags: []` is left as-is (purging isn't reclassification).
- Inbox files under `_inbox/` — tag dropped from `imported_tags:` so a future `/bm:enrich` doesn't re-introduce it.
- `tags.yaml` — `<tag>`'s entry is deleted entirely. If `<tag>` appears in another entry's `aliases:`, it's removed from that list too (otherwise the alias would redirect the LLM to a tag that no longer exists in bookmarks).

Doesn't touch `_trash/` or `_failed/`.

`$ARGUMENTS` carries the positional `<tag>` plus optional flags.

---

## 1. Locate the vault

Walk up from `$PWD` for a directory whose `AGENTS.md` first line contains "Bookmarks Vault". If walk-up fails, try `$BM_VAULT`, then `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/` — first match wins. Override via `BM_VAULT=/path/to/vault /bm:...`.

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
script_dir="${CLAUDE_PLUGIN_ROOT:-/Users/ali/.claude/plugins/marketplaces/agent-marketplace/plugins/bm}/skills/purge-tag/lib"

tag=""
dry_run=false
commit_flag=false

set -- $ARGUMENTS
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  dry_run=true;     shift ;;
    --commit)   commit_flag=true; shift ;;
    --*)        echo "error: unknown flag $1" >&2; exit 2 ;;
    *)          [ -z "$tag" ] && tag="$1" || { echo "error: extra positional arg: $1" >&2; exit 2; }; shift ;;
  esac
done

if [ -z "$tag" ]; then
  echo "usage: /bm:purge-tag <tag> [--dry-run] [--commit]" >&2
  exit 2
fi
```

## 3. Dispatch

```bash
extra_args=()
[ "$dry_run" = "true" ] && extra_args+=("--dry-run")
"$script_dir/purge_tag.py" "$vault" "$tag" ${extra_args[@]+"${extra_args[@]}"}
rc=$?
```

The script prints a markdown report (affected files, planned `tags.yaml` changes, then either `_(--dry-run: no changes written)_` or an `## Applied` section). Exits 0 on success, non-zero on error.

## 4. Optional `--commit`

If `--commit` is set, `--dry-run` is not, and the script wrote at least one file:

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
      git -C "$vault" commit -m "bm:purge-tag: $tag ($n files touched)"
    fi
  fi
fi
```

The pre-existing-staged-changes refusal mirrors `enrich/SKILL.md` step 7.

## Verification gate

Sandbox at `/tmp/bm-qol-vault` per the plan:

- `/bm:purge-tag alpha --dry-run` → report shows 4 filed + 1 inbox + 1 tags.yaml change, nothing on disk.
- `/bm:purge-tag alpha` → mutations applied. `has-alpha.md` ends with `tags: []`; `has-both.md` keeps `[beta]`; inbox `imported_tags` loses `alpha`; tags.yaml deletes `alpha` (including its `alphabet` alias).
- Re-run → `_No occurrences of `alpha` found; nothing to do._`.
- Edge: a tag that's only in `aliases:` of another entry → should still be removed from that aliases list.

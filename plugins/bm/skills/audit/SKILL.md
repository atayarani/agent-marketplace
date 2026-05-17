---
name: audit
description: "Health-audit the bm vault: links, tags, or collections. Prints report to chat — never written into the vault. Only `links` mode mutates state (moves dead URLs to `_broken/`, flips `status: broken`). Tags mode runs a Sonnet pass for semantic synonym confirmation; pass `--skip-llm` to skip. Idempotent. Use when the user types `/bm:audit <kind>` or wants to surface drift in the vault."
argument-hint: "<links|tags|collections> [--skip-llm] [--dry-run] [--out PATH] [audit-specific flags]"
---

Run a health audit on the bm vault. One skill, three modes (positional arg):

| Mode | Mutates vault? | LLM? | What it does |
|---|---|---|---|
| `links` | yes (moves to `_broken/`, flips `status`) | no | Two-pass HEAD→GET checker. Only 404/410/451 confirm-broken; 401/403/429 are bot-walled. |
| `tags` | no | yes (Sonnet, opt-out) | Walks tag distribution, finds rare/over-broad/ghost tags + Levenshtein synonym candidates, asks Sonnet to verdict the candidates. |
| `collections` | no | no | Counts per-collection sizes, proposes merges (sparse) and nestings (bloated). |

Reports are markdown, printed to stdout (lands in chat). The vault never receives audit artifacts. Use `--out PATH` to redirect to a file *outside* the vault.

`$ARGUMENTS` carries the positional `<kind>` plus any flags.

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

## 2. Parse positional arg and flags

The first non-flag token in `$ARGUMENTS` is the mode (`links`, `tags`, or `collections`). Reject if missing or unknown.

Common flags (handled by SKILL.md, not the underlying script):
- `--out PATH` — redirect the markdown report to `PATH`. **Hard-reject** if `PATH` is inside `$vault` — reports never live in the vault. Use a path like `/tmp/bm-audit.md` or `~/Desktop/bm-audit.md`.
- `--skip-llm` — `tags` only. Skip the Sonnet verdict pass; emit raw Levenshtein candidates for manual review.

Mode-specific flags pass through to the underlying script:
- `links`: `--concurrency N`, `--timeout S`, `--dry-run`, `--user-agent STR`, `--limit N`
- `tags`: `--rare-threshold N`, `--broad-pct P`, `--levenshtein-max N`
- `collections`: `--sparse-threshold N`, `--bloat-threshold N`, `--nest-cluster-min N`

```bash
script_dir="${CLAUDE_PLUGIN_ROOT:-/Users/ali/.claude/plugins/marketplaces/agent-marketplace/plugins/bm}/skills/audit/lib"

mode=""
out_path=""
skip_llm=false
passthrough=()

# crude positional+flag splitter — first non-flag is the mode, --out captures next arg,
# everything else passes through to the underlying script.
set -- $ARGUMENTS
while [ $# -gt 0 ]; do
  case "$1" in
    links|tags|collections)
      [ -z "$mode" ] && mode="$1" || passthrough+=("$1")
      shift ;;
    --out)
      out_path="$2"; shift 2 ;;
    --out=*)
      out_path="${1#--out=}"; shift ;;
    --skip-llm)
      skip_llm=true; shift ;;
    *)
      passthrough+=("$1"); shift ;;
  esac
done

if [ -z "$mode" ]; then
  echo "usage: /bm:audit <links|tags|collections> [--out PATH] [--skip-llm] [mode-specific flags]" >&2
  exit 2
fi

# Hard-reject --out paths inside the vault
if [ -n "$out_path" ]; then
  abs_out=$(python3 -c "import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))" "$out_path")
  abs_vault=$(python3 -c "import os,sys; print(os.path.abspath(sys.argv[1]))" "$vault")
  case "$abs_out/" in
    "$abs_vault/"*)
      echo "error: --out path is inside the vault ($abs_out). Reports must live outside the vault." >&2
      exit 2 ;;
  esac
fi
```

## 3. Dispatch

### Mode: `collections`

Pure-stat, fastest path. No LLM, no network.

```bash
if [ -n "$out_path" ]; then
  "$script_dir/audit_collections.py" "$vault" ${passthrough[@]+"${passthrough[@]}"} > "$out_path"
  echo "audit-collections report written to $out_path"
else
  "$script_dir/audit_collections.py" "$vault" ${passthrough[@]+"${passthrough[@]}"}
fi
```

### Mode: `links`

Two-pass HTTP checker. Mutates the vault on `confirmed_broken` unless `--dry-run` is passed. Hits the network for every active bookmark — recommend dry-run first on large vaults.

```bash
if [ -n "$out_path" ]; then
  "$script_dir/audit_links.py" "$vault" ${passthrough[@]+"${passthrough[@]}"} > "$out_path"
  echo "audit-links report written to $out_path"
else
  "$script_dir/audit_links.py" "$vault" ${passthrough[@]+"${passthrough[@]}"}
fi
```

### Mode: `tags`

Two-phase. Phase A runs `audit_tags.py analyze` (pure-stat, no LLM). Phase B optionally spawns a general-purpose Sonnet `Agent` to verdict the synonym candidates; final markdown is rendered by `audit_tags.py render`.

```bash
analysis_json=$(mktemp -t bm_audit_tags_analysis.XXXXXX.json)
verdicts_json=""
trap 'rm -f "$analysis_json" "$verdicts_json"' EXIT

"$script_dir/audit_tags.py" analyze "$vault" ${passthrough[@]+"${passthrough[@]}"} > "$analysis_json"
```

If `$skip_llm = true` OR the analysis JSON shows zero synonym candidates: skip the LLM phase.

```bash
candidate_count=$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print((d.get("totals") or {}).get("synonym_candidate_count", 0))
' "$analysis_json")
```

If `$skip_llm = false` AND `$candidate_count -gt 0`:

1. Extract a compact "candidates only" JSON from the analysis (keep `a`, `b`, `dist`, `reason`, `count_a`, `count_b`, `vocab_a`, `vocab_b`):

   ```bash
   candidates_for_llm=$(python3 -c '
   import json, sys
   d = json.load(open(sys.argv[1]))
   slim = [{k: c.get(k) for k in ("a","b","dist","reason","count_a","count_b","vocab_a","vocab_b")}
           for c in d.get("synonym_candidates") or []]
   print(json.dumps(slim, ensure_ascii=False))
   ' "$analysis_json")
   ```

2. Spawn the Agent tool with:
   - `subagent_type`: `general-purpose`
   - `model`: `sonnet`
   - `description`: `bm:audit tags synonym verdicts`
   - `prompt`: see template below.

   Prompt template (paste the candidates JSON inline):

   ```
   You are reviewing pairs of tags from a bookmark vault's controlled vocabulary to decide whether each pair represents:
     - "synonym": same concept under two names (one should be canonical, the other migrated)
     - "distinct": different concepts that look similar (Levenshtein neighbours, prefix/substring overlap)
     - "related": overlap but a hierarchy or refinement, not a merge

   For each pair, return strict JSON `[{"a": ..., "b": ..., "verdict": "synonym|distinct|related", "canonical": "<one of a/b>"|null, "reason": "<short>"}]`. Use null canonical when verdict is not "synonym".

   Be conservative: prefer "distinct" when the two tags could plausibly tag different bookmarks. Only mark "synonym" when the descriptions clearly describe the same concept.

   Each pair includes the vocab entry from `tags.yaml` (description + aliases) for both sides — read those before judging.

   Return ONLY the JSON array, no prose, no code fences.

   ## Candidates

   ```json
   <candidates_for_llm>
   ```
   ```

3. Capture the response in `$verdicts_response`. Parse defensively (Sonnet sometimes fences JSON despite instructions):

   ```bash
   verdicts_json=$(mktemp -t bm_audit_tags_verdicts.XXXXXX.json)
   printf '%s' "$verdicts_response" | python3 -c '
   import json, re, sys
   text = sys.stdin.read().strip()
   try:
       obj = json.loads(text)
   except json.JSONDecodeError:
       m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
       if m:
           obj = json.loads(m.group(1))
       else:
           m = re.search(r"\[.*\]", text, re.DOTALL)
           if not m:
               print("[]")
               sys.exit(0)
           obj = json.loads(m.group(0))
   print(json.dumps(obj))
   ' > "$verdicts_json"
   ```

   If parsing fails entirely, `verdicts_json` will be an empty array — the render step treats unverdicted candidates as "unverdicted" and lists them in a fallback table.

Render the final markdown:

```bash
render_args=("$analysis_json")
if [ -n "$verdicts_json" ]; then
  render_args+=(--verdicts "$verdicts_json")
fi

if [ -n "$out_path" ]; then
  "$script_dir/audit_tags.py" render "${render_args[@]}" > "$out_path"
  echo "audit-tags report written to $out_path"
else
  "$script_dir/audit_tags.py" render "${render_args[@]}"
fi
```

The `trap rm -f` cleans up tmp files on exit.

## 4. Conventions

- **Reports never land in the vault.** Step 2's `--out` check enforces this. The vault holds bookmarks + vocabulary + scaffolding only.
- **Mode `links` is the only one that mutates the vault.** It moves confirmed-broken files to `_broken/` and flips `status: broken`. Use `--dry-run` first on any non-trivial vault. The classifier is conservative: only 404/410/451 trigger moves; 401/403/429 are bot-walled and never moved.
- **Mode `tags` LLM pass is opt-out, not opt-in.** Most of the value of the tags audit comes from semantic synonym confirmation. `--skip-llm` is for offline use or when the LLM step would add cost the user doesn't want.
- **Idempotency.** Re-running any audit produces a fresh report. `links` is idempotent because re-run skips already-`status: broken` files. `tags` and `collections` are read-only.

## Verification gate

Run from `/Users/ali/Documents/obsidian/whiskers/`:

- `/bm:audit collections` — markdown report to chat with sparse/bloated/distribution sections. `git status` clean afterwards.
- `/bm:audit tags --skip-llm` — markdown to chat with rare/over-broad/ghost/raw-candidate sections. Spot-check ghost tags by adding a fake tag to a bookmark, re-running, confirming it appears. Undo the test edit.
- `/bm:audit tags` — same plus a "Synonym merges proposed" table populated by Sonnet verdicts.
- `/bm:audit links --dry-run --limit 5` — markdown to chat; `git status` clean; no files moved.
- `/bm:audit links` — full run. Confirmed-broken files end up in `_broken/` with `status: broken` and `broken_at:` appended. Re-run = no additional moves.
- `/bm:audit collections --out /tmp/bm-audit.md` — file written to `/tmp/`, vault untouched.
- `/bm:audit collections --out <vault>/x.md` — hard-rejected with a clear error, no file created.
- `/bm:audit` (no mode) — usage message, exit 2.
- `/bm:audit nonsense` — usage message, exit 2.

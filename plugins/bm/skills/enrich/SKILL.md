---
name: enrich
description: "Process the bookmarks `_inbox/` queue. For each file: fetch the URL via extract.py, spawn the bm:enricher subagent, parse its JSON response, and file the result into a collection. Idempotent. Use when the user types /bm:enrich, says 'process the inbox', or 'enrich the bookmarks'."
argument-hint: "[--limit N] [--failed] [--dry-run] [--force]"
---

Walk the bookmark vault's `_inbox/` (or `_failed/*/` with `--failed`), enrich each captured URL using the `bm:enricher` subagent, file the result into a collection directory.

> **Filing model**: this skill follows the vault's current `AGENTS.md` — every bookmark goes to a best-guess collection directory; `needs_review: true` plus `proposed_*` fields are carried inline in frontmatter when confidence is low or new vocabulary is suggested. This **supersedes** the older `bm-v1-phase-1c-enrich.md` design (which routed low-confidence bookmarks to `_unsorted/` and accumulated proposals in `_proposals/YYYYMMDD-*.md`). The phase doc is stale on this point — neither `_unsorted/` nor `_proposals/` exists in the vault.

`$ARGUMENTS` carries any flags the user passed.

---

## 1. Locate the vault

Walk up from `$PWD` for a directory whose `AGENTS.md` first line contains "Bookmarks Vault". Fall back to `$HOME/Documents/whiskers/` if its `AGENTS.md` matches.

```bash
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
mkdir -p "$vault/_failed/fetch" "$vault/_failed/llm"
```

## 2. Parse arguments

From `$ARGUMENTS`:
- `--limit N` — default **10**. (Each subagent return adds ~500 tokens to host context; iterate with repeated runs to drain larger queues.)
- `--failed` — also include `_failed/fetch/*.md` and `_failed/llm/*.md` in the queue.
- `--dry-run` — print what would happen; no writes, no moves, no deletes.
- `--force` — accepted, no-op in v1.

## 3. Build the queue

```bash
queue=()
while IFS= read -r f; do queue+=("$f"); done < <(find "$vault/_inbox" -maxdepth 1 -type f -name '*.md' ! -name '.gitkeep' 2>/dev/null | sort)
if [ "$failed_flag" = "true" ]; then
  while IFS= read -r f; do queue+=("$f"); done < <(find "$vault/_failed/fetch" "$vault/_failed/llm" -maxdepth 1 -type f -name '*.md' ! -name '.gitkeep' 2>/dev/null | sort)
fi
# Apply --limit (bash slice: ${queue[@]:0:$limit})
```

If `${#queue[@]} -eq 0` → print `inbox empty` and exit 0. (Idempotency: empty inbox is always a silent no-op.)

## 4. Build the per-run static inputs (compute once before the loop)

These get pasted into every subagent prompt — caching them avoids redundant work.

**a. `tags.yaml` contents**:
```bash
tags_yaml=$(cat "$vault/tags.yaml" 2>/dev/null || echo "tags: []")
```

**b. Collection list** — for each dir in `$vault/` where the name doesn't start with `_`, isn't `outputs`, AND contains a `README.md`:

```bash
collection_list=""
bootstrap_mode=true
warned_missing_readme=()
for d in "$vault"/*/; do
  name=$(basename "$d")
  case "$name" in _*|outputs) continue;; esac
  if [ -f "$d/README.md" ]; then
    desc=$(grep -m1 '^[^[:space:]#]' "$d/README.md" 2>/dev/null | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    [ -z "$desc" ] && desc="(no description in README.md)"
    collection_list+="${name}/\n  ${desc}\n"
    bootstrap_mode=false
  else
    echo "note: directory '${name}/' has no README.md; not surfacing as a filing target" >&2
  fi
done
[ -z "$collection_list" ] && collection_list="(none — vault has no collections yet)"
```

## 5. Per-file loop (sequential)

For each `inbox_file` in the queue, in order, do the steps below. Do **not** attempt to fan out Agent tool calls in parallel — process one file at a time, fully, before moving to the next.

Initialize counters: `filed=0`, `needs_review_count=0`, `fetch_failed=0`, `llm_failed=0`, `bootstrap_held=0`.

### 5.a — Pre-fetch URL dedup check

Ctrl-C safety: covers the case where a previous run wrote the filed bookmark but didn't reach the inbox-delete step.

```bash
url=$(grep -m1 '^url: ' "$inbox_file" | sed 's/^url: //; s/^[[:space:]]*//; s/[[:space:]]*$//')
hit=$(rg -Fx -l "url: $url" "$vault" --type md \
  --glob '!_inbox/**' --glob '!_failed/**' --glob '!_trash/**' --glob '!_broken/**' \
  2>/dev/null | head -1 || true)
```

If `$hit` is non-empty:
- `--dry-run`: print `would remove duplicate: $inbox_file (already filed at $hit)`.
- Otherwise: `rm "$inbox_file"`, print `already filed: $hit — removed duplicate $inbox_file`.
- Continue to next file. (Don't count toward `filed`.)

### 5.b — Fetch + extract

```bash
stderr_file=$(mktemp)
extract_out=$("${CLAUDE_PLUGIN_ROOT:-.}/skills/enrich/lib/extract.py" "$inbox_file" 2>"$stderr_file")
rc=$?
```

**Do NOT** combine streams with `2>&1` — it corrupts the JSON.

On `rc != 0`:
- Compute target path: `$vault/_failed/fetch/$(basename $inbox_file)`.
- If `$inbox_file` is already in `_failed/fetch/`, leave it in place; otherwise `mv "$inbox_file"` to the target.
- **Append** (don't overwrite) to the moved file:

  ```
  
  ## Fetch failed ($(date -Iseconds))
  
  $(cat $stderr_file)
  ```

- `fetch_failed=$((fetch_failed+1))`. Continue.

### 5.c — Spawn `bm:enricher`

Use the Agent tool with `subagent_type: "bm:enricher"`. Pass a single prompt containing:

1. The page extract JSON from step 5.b (`$extract_out`).
2. The `tags.yaml` contents from step 4.a.
3. The collection list from step 4.b (or the literal `(none — vault has no collections yet)` in bootstrap mode).
4. Any `imported_tags` / `imported_collection` from `$inbox_file`'s frontmatter (typically only present for Raindrop imports).

Prompt template:

```
Process this bookmark and return strict JSON per your system prompt schema.

## Page extract (extract.py output)
```json
<paste $extract_out>
```

## tags.yaml
```yaml
<paste $tags_yaml>
```

## Collection list
<paste $collection_list>

## Imported hints (from inbox frontmatter — if present)
<imported_tags: …, imported_collection: …, OR omit this section if absent>
```

Capture the subagent's response as `$response`.

### 5.d — Parse the response (defensive)

Haiku 4.5 frequently wraps its JSON in ```` ```json ```` fences despite the system prompt's explicit instruction not to. Tolerate it:

```bash
parsed=$(printf '%s' "$response" | python3 -c '
import json, re, sys
text = sys.stdin.read().strip()
try:
    obj = json.loads(text)
except json.JSONDecodeError:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        obj = json.loads(m.group(1))
    else:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            print("no JSON object found in response", file=sys.stderr)
            sys.exit(1)
        obj = json.loads(m.group(0))
print(json.dumps(obj))
' 2>"$stderr_file")
rc=$?
```

On `rc != 0`:
- Move `$inbox_file` to `$vault/_failed/llm/$(basename $inbox_file)` (or leave in place if already there).
- **Append** to its body:

  ```
  
  ## Enricher response did not parse ($(date -Iseconds))
  
  Error: $(cat $stderr_file)
  
  Raw response:
  \`\`\`
  $response
  \`\`\`
  ```

- `llm_failed=$((llm_failed+1))`. Continue.

Then extract fields from `$parsed` (also via `python3 -c` or `jq`):
- `collection`, `title`, `blurb`, `tags`, `proposed_tags`, `proposed_collection`, `confidence`.
- Optional: `author`, `published`.

### 5.e — Bootstrap branch

If `bootstrap_mode == true` AND `parsed.collection` is `null`:
- **Do NOT** move or delete `$inbox_file` — leave it in place.
- `bootstrap_held=$((bootstrap_held+1))`. Continue.

### 5.f — Determine `needs_review`

```
needs_review = (parsed.confidence < 0.4)
            OR (parsed.proposed_tags has any elements)
            OR (parsed.proposed_collection is not null)
```

### 5.g — Compute the slug

```python
import re
slug = re.sub(r"[^a-z0-9]+", "-", parsed["title"].lower()).strip("-")[:80]
```

Target path: `$vault/$collection/$slug.md`.

Collision handling:
1. If `$vault/$collection/$slug.md` exists → try `$slug-$(printf '%s' "$url" | shasum | head -c 6).md`.
2. If THAT also exists → append `-$(date +%s)`.

Ensure `$vault/$collection/` exists (it should, since the enricher only proposes existing collection names — `mkdir -p` defensively anyway).

### 5.h — `--dry-run` short-circuit

If `dry_run == true`:
- Print: `would write: <target>  (collection=$collection, confidence=$confidence, needs_review=$needs_review)`.
- Skip the write and the delete.
- Increment `filed` (and `needs_review_count` if applicable) so the summary reflects what would have happened.
- Continue.

### 5.i — Write the filed bookmark

Write the target file with frontmatter in this exact order. Body is **empty** (user notes area; agents never write here).

```yaml
---
url: <url from $extract_out>
title: <parsed.title>
blurb: <parsed.blurb>
tags: [<parsed.tags joined with ", ">]
captured: <carried from $inbox_file's frontmatter>
enriched: <date -Iseconds>
status: active
source: <carried from $inbox_file's frontmatter; default 'cli'>
```

Conditionally append (only if the field is present in `$parsed`):
```yaml
author: <parsed.author>
published: <parsed.published>
```

If `needs_review`:
```yaml
needs_review: true
confidence: <parsed.confidence>
```
And conditionally:
```yaml
proposed_tags: [<comma-joined>]
```
(if non-empty)
```yaml
proposed_collection:
  name: <parsed.proposed_collection.name>
  description: <parsed.proposed_collection.description>
```
(if non-null)

Close with `---` then `\n` (blank line). No body content.

Use a heredoc to preserve formatting:

```bash
cat > "$target" <<EOF
---
url: $url
title: $title
blurb: $blurb
tags: [$(printf '%s, ' "${tags[@]}" | sed 's/, $//')]
captured: $captured
enriched: $(date -Iseconds)
status: active
source: $source
...
---

EOF
```

`filed=$((filed+1))`. If `$needs_review`: `needs_review_count=$((needs_review_count+1))`.

### 5.j — Delete the inbox source

`rm "$inbox_file"`.

(In `--dry-run` this step is skipped — already handled in 5.h.)

---

## 6. End-of-run summary

Always print:

```
/bm:enrich: processed N items
  filed:           M  (K needs_review)
  bootstrap-held:  B  (inbox files left in place; no collections in vault)
  fetch-failed:    F
  llm-failed:      L
```

Where `N = ${#queue[@]}`, `M = $filed`, `K = $needs_review_count`, `B = $bootstrap_held`, `F = $fetch_failed`, `L = $llm_failed`.

If `B > 0` and `bootstrap_mode`: also print:
```
hint: create a collection with `mkdir <name> && printf "# <Name>\n\n<one-line description>\n" > <name>/README.md`, then rerun /bm:enrich.
```

## 7. No git commit

The user commits manually at milestones.

---

## Idempotency model

- **Empty inbox** → silent no-op (exit 0).
- **Half-filed bookmark** (Ctrl-C between write and inbox-delete) → step 5.a's URL dedup catches it on the next run; the orphaned inbox source is removed.
- **`--failed` retry** on a file already moved to `_failed/*/` → the file re-enters the pipeline. Failure-log sections accumulate (append, not overwrite) so retry history is preserved.

## Conventions

- URL stored **verbatim** — no normalization, lowercase, query-string stripping.
- Dates are **ISO 8601 with timezone** (`date -Iseconds` on macOS).
- Slug: kebab-case from `title`, max 80 chars, with `-<6id>` or `-<unix-ts>` collision suffix.
- Filed bookmarks have **frontmatter only**, no body — the body is the user's notes area; agents never write there.
- The subagent runs in **clean context** — it only sees what step 5.c passes. It cannot read the vault, prior conversation, or other inbox files. Always include the full `tags.yaml` and collection list, even though they're cheap repetitions.
- Haiku occasionally wraps JSON in code fences — step 5.d's parser tolerates this. Do not modify the enricher's system prompt to try to suppress the fences; the defensive parse is the real fix.

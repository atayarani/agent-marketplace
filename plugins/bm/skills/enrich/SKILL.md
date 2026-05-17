---
name: enrich
description: "Process the bookmarks `_inbox/` queue. For each file: fetch the URL via extract.py, spawn the bm:enricher subagent, parse its JSON response, and file the result into a collection. When the enricher proposes a brand-new collection, prompts the user inline (unless `--no-prompt`). Idempotent. Use when the user types /bm:enrich, says 'process the inbox', or 'enrich the bookmarks'."
argument-hint: "[--limit N] [--failed] [--dry-run] [--no-prompt] [--force]"
---

Walk the bookmark vault's `_inbox/` (or `_failed/*/` with `--failed`), enrich each captured URL using the `bm:enricher` subagent, file the result into a collection directory.

> **Filing model**: this skill follows the vault's current `AGENTS.md` — every bookmark goes to a best-guess collection directory; `needs_review: true` plus `proposed_*` fields are carried inline in frontmatter when confidence is low or new vocabulary is suggested. When the enricher proposes a *brand-new* collection (one that doesn't yet exist), this skill prompts the user inline (`AskUserQuestion`) before filing — unless `--no-prompt` is passed. This **supersedes** the older `bm-v1-phase-1c-enrich.md` design (which routed low-confidence bookmarks to `_unsorted/` and accumulated proposals in `_proposals/YYYYMMDD-*.md`).

`$ARGUMENTS` carries any flags the user passed.

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
# Fallback: $BM_VAULT env var, then known default locations (first match wins).
for candidate in "$BM_VAULT" "$HOME/Documents/obsidian/whiskers" "$HOME/Documents/whiskers" "$HOME/whiskers"; do
  [ -n "$vault" ] && break
  [ -z "$candidate" ] && continue
  if [ -f "$candidate/AGENTS.md" ] && head -1 "$candidate/AGENTS.md" | grep -q "Bookmarks Vault"; then
    vault="$candidate"
  fi
done
[ -z "$vault" ] && { echo "error: bookmarks vault not found" >&2; exit 1; }
mkdir -p "$vault/_failed/fetch" "$vault/_failed/llm"
```

## 2. Parse arguments

From `$ARGUMENTS`:
- `--limit N` — default **10**. (Each subagent return adds ~500 tokens to host context; iterate with repeated runs to drain larger queues.)
- `--failed` — also include `_failed/fetch/*.md` and `_failed/llm/*.md` in the queue.
- `--dry-run` — print what would happen; no writes, no moves, no deletes. Implies `--no-prompt`.
- `--no-prompt` — skip the interactive "create new collection?" prompt in step 5.f. Bookmarks with brand-new `proposed_collection` are filed to the under-protest existing collection with `needs_review: true` (pre-v0.3.0 behavior). Use for batch imports (`/bm:import`) where stopping for prompts would be tedious.
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

Note: this list is built once and **not refreshed** mid-run. If step 5.f creates a new collection, subsequent bookmarks in the same run won't see it in their enricher prompt — but step 5.f's auto-reroute path catches the case where the enricher re-proposes the just-created name.

## 5. Per-file loop (sequential)

For each `inbox_file` in the queue, in order, do the steps below. Do **not** attempt to fan out Agent tool calls in parallel — process one file at a time, fully, before moving to the next.

Initialize counters: `filed=0`, `needs_review_count=0`, `deferred=0`, `fetch_failed=0`, `llm_failed=0`.

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

Then extract fields from `$parsed` (via `python3 -c` or `jq`):
- `collection`, `title`, `blurb`, `tags`, `proposed_tags`, `proposed_collection`, `confidence`.
- Optional: `author`, `published`.

### 5.e — Defer when collection is null

If `parsed.collection` is `null`:
- **Do NOT** move or delete `$inbox_file` — leave it in place.
- `deferred=$((deferred+1))`. Continue to next file.

This branch fires in two cases:
- **Bootstrap mode** (zero collections exist) — the expected path per enricher rule 4. User needs to create a first collection.
- **Outside bootstrap mode** (collections exist but enricher returned null) — the enricher's rule 4 has regressed; it should have picked the least-bad existing collection and surfaced the poor fit via `proposed_collection`. The defense-in-depth here is to avoid crashing on `$vault/null/<slug>.md` — surface the condition through the end-of-run summary so the user can investigate the prompt.

### 5.f — Resolve `proposed_collection` (interactive when warranted)

When `parsed.proposed_collection` is non-null, decide whether to honor it before filing. **Skip this entire step if `parsed.proposed_collection` is `null`.**

**Auto-reroute** — if `parsed.proposed_collection.name` matches an existing directory under `$vault/` (and is not the current `$collection`):
- The proposed collection already exists — either an alternative existing dir the enricher considered, or a dir created earlier in this same run. Silently:
  - Set `$collection = parsed.proposed_collection.name`.
  - Clear `parsed.proposed_collection` (resolved — don't carry into frontmatter).
- Continue to 5.g with the rerouted target.

**Interactive prompt** — if `parsed.proposed_collection.name` is brand-new (no matching dir) AND neither `--no-prompt` nor `--dry-run` is set:

Use the `AskUserQuestion` tool:
- **header**: `"New collection?"`
- **question**: `"Bookmark '<parsed.title>' was filed to <$collection>/, but the enricher proposed creating '<parsed.proposed_collection.name>/' (<parsed.proposed_collection.description>). How would you like to handle it?"`
- **options** (3, plus "Other" added automatically by the tool):
  1. label: `"Create <name>/ and file there"` — description: `"mkdir + write README.md from the proposed description; file this bookmark in the new dir."`
  2. label: `"File to <$collection>/ with needs_review"` — description: `"keep current target; proposed_collection in frontmatter for review later."`
  3. label: `"Leave in _inbox/"` — description: `"don't file; user resolves later."`

Act on the response:

- **Option 1 (create new dir)**:
  - Validate `parsed.proposed_collection.name` matches `^[a-z0-9][a-z0-9-]*$`. If not, print warning to stderr and fall through to Option 2.
  - `mkdir -p "$vault/$proposed_name"`.
  - Title-case the dir name for the H1 (`gaming-guides` → `Gaming Guides`):
    ```bash
    h1=$(echo "$proposed_name" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)} 1')
    printf "# %s\n\n%s\n" "$h1" "$proposed_description" > "$vault/$proposed_name/README.md"
    ```
  - Set `$collection = $proposed_name`.
  - Clear `parsed.proposed_collection` (resolved).

- **Option 2 (file with needs_review)**: no change. `$collection` and `parsed.proposed_collection` stay as-is. Continue.

- **Option 3 (leave in inbox)**: `deferred=$((deferred+1))`. Do NOT move/delete `$inbox_file`. **Continue to next file** (skip remaining steps for this bookmark).

- **"Other" / unrecognized free-text**: treat as Option 3 (defer). Echo the user's text to stderr so they can act on it.

**Skip prompt** — if `--no-prompt` OR `--dry-run` is set AND name is brand-new: don't prompt. Keep current `$collection`. `proposed_collection` carried in frontmatter via the needs_review block. Continue to 5.g.

### 5.g — Determine `needs_review`

```
needs_review = (parsed.confidence < 0.4)
            OR (parsed.proposed_tags has any elements)
            OR (parsed.proposed_collection is not null)
```

Note: `parsed.proposed_collection` may have been cleared by step 5.f (Option 1 or auto-reroute), in which case it no longer contributes to `needs_review`.

### 5.h — Compute the slug

ASCII-fold the title before the regex so titles with accents, umlauts, ligatures, etc. produce readable slugs rather than collapsing to noise (e.g. `Bánh mì` → `banh-mi`, not `b-nh-m`):

```python
import re, unicodedata, hashlib
ascii_title = unicodedata.normalize('NFD', parsed["title"]).encode('ascii', 'ignore').decode('ascii')
slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:80]
if not slug:
    # Title has no ASCII-foldable chars (e.g. CJK-only title) — fall back to URL hash
    slug = hashlib.sha1(url.encode()).hexdigest()[:12]
```

Target path: `$vault/$collection/$slug.md`.

Collision handling:
1. If `$vault/$collection/$slug.md` exists → try `$slug-$(printf '%s' "$url" | shasum | head -c 6).md`.
2. If THAT also exists → append `-$(date +%s)`.

Ensure `$vault/$collection/` exists (step 5.f either kept the enricher's pick, rerouted to an existing dir, or created one — `mkdir -p` defensively anyway).

### 5.i — `--dry-run` short-circuit

If `dry_run == true`:
- Print: `would write: <target>  (collection=$collection, confidence=$confidence, needs_review=$needs_review)`.
- Skip the write and the delete.
- Increment `filed` (and `needs_review_count` if applicable) so the summary reflects what would have happened.
- Continue.

### 5.j — Write the filed bookmark

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

### 5.k — Delete the inbox source

`rm "$inbox_file"`.

(In `--dry-run` this step is skipped — already handled in 5.i.)

---

## 6. End-of-run summary

Always print:

```
/bm:enrich: processed N items
  filed:           M  (K needs_review)
  deferred:        D  (collection=null or user chose 'leave in inbox'; inbox files left in place)
  fetch-failed:    F
  llm-failed:      L
```

Where `N = ${#queue[@]}`, `M = $filed`, `K = $needs_review_count`, `D = $deferred`, `F = $fetch_failed`, `L = $llm_failed`.

If `D > 0`:
- **Bootstrap mode** (zero collections exist): `hint: create a collection with mkdir <name> && printf "# <Name>\n\n<one-line description>\n" > <name>/README.md, then rerun /bm:enrich.`
- **Otherwise** (deferred via step 5.e null-collection branch with collections present, or via step 5.f "leave in inbox"): one-line note describing the deferred count and that the inbox files are awaiting user action.

## 7. No git commit

The user commits manually at milestones.

---

## Idempotency model

- **Empty inbox** → silent no-op (exit 0).
- **Half-filed bookmark** (Ctrl-C between write and inbox-delete) → step 5.a's URL dedup catches it on the next run; the orphaned inbox source is removed.
- **`--failed` retry** on a file already moved to `_failed/*/` → the file re-enters the pipeline. Failure-log sections accumulate (append, not overwrite) so retry history is preserved.
- **User chose 'leave in inbox' in step 5.f** → bookmark stays as a regular inbox file. Re-running `/bm:enrich` re-prompts (unless the proposed collection now exists, in which case auto-reroute fires).

## Conventions

- URL stored **verbatim** — no normalization, lowercase, query-string stripping.
- Dates are **ISO 8601 with timezone** (`date -Iseconds` on macOS).
- Slug: kebab-case from `title`, max 80 chars, with `-<6id>` or `-<unix-ts>` collision suffix.
- Filed bookmarks have **frontmatter only**, no body — the body is the user's notes area; agents never write there.
- The subagent runs in **clean context** — it only sees what step 5.c passes. It cannot read the vault, prior conversation, or other inbox files. Always include the full `tags.yaml` and collection list, even though they're cheap repetitions.
- Haiku occasionally wraps JSON in code fences — step 5.d's parser tolerates this. Do not modify the enricher's system prompt to try to suppress the fences; the defensive parse is the real fix.
- Step 5.f's interactive prompt fires only for *brand-new* `proposed_collection` names. If the enricher proposes an *existing* dir as an alternative (rather than the current pick), step 5.f auto-reroutes silently.

---
name: review
description: "Review the enrichment backlog. --vocab mode: batch-promote frequent imported_tags / imported_collection values from the inbox to tags.yaml + collection dirs (pre-enrich warmup). Default mode: per-bookmark walker for needs_review:true files (post-enrich cleanup). Idempotent. Use when the user wants to resolve proposals after /bm:import or /bm:enrich."
argument-hint: "[--vocab] [--min-count N] [--top N] [--include-filed] [--collection X] [--limit N] [--refetch] [--commit]"
---

Two modes:

- **`--vocab` (pre-enrich)** — scans the inbox for frequency-ranked `imported_tags` and `imported_collection` hints, presents them in chunks via `AskUserQuestion`, batch-promotes accepted tags to `tags.yaml` and accepted collections to on-disk dirs. Best run after `/bm:import` and **before** `/bm:enrich` drains the queue.
- **Default (post-enrich walker)** — walks `needs_review: true` filed bookmarks one at a time, surfacing each via `AskUserQuestion`. For each: promote any `proposed_tags` to `tags.yaml`, accept/reject the `proposed_collection`, or move the bookmark elsewhere. Resumable — re-runs pick up where the prior session left off.

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
```

## 2. Parse arguments

From `$ARGUMENTS`:

**Mode selector**
- `--vocab` — boolean flag (default false). When set, run vocab-warmup mode (sections 4-8). When unset, run default-mode walker (section 3).

**Vocab-mode flags** (only meaningful when `--vocab` is set)
- `--min-count N` — integer (default 2). Tag/collection frequency threshold for promotion. Lower it (e.g. `--min-count 1`) to surface singletons; raise it to prune more aggressively.
- `--top N` — integer (default 50). Cap on candidates per category. Prevents drowning the user.
- `--include-filed` — boolean flag (default false). Also scan filed bookmarks under `$vault/<collection>/*.md`, not just `_inbox/*.md`. (Filed bookmarks per current enrich shape don't carry `imported_*` fields, so this is a no-op in practice today — kept for forward compatibility.)

**Default-mode flags** (only meaningful when `--vocab` is NOT set)
- `--collection X` — string (default empty). Restrict the walk to one collection dir (e.g. `--collection cloud-infrastructure`). Other dirs' `needs_review` files are not touched.
- `--limit N` — integer (default unlimited). Stop after walking N bookmarks. Useful for piloting before committing to a long session.
- `--refetch` — boolean flag (default false). Re-run `extract.py` on each bookmark and replace its cached blurb (in the body, above the `<!-- /llm-managed -->` marker) before prompting. Rare; the cached blurb is normally trustworthy. User notes below the marker are preserved.

**Both modes**
- `--commit` — boolean flag (default false). After the run completes, auto-commit the touched paths (`tags.yaml` + created/moved collection dirs) with a mode-specific templated message (see section 9). Refuses to commit if the vault has pre-existing staged changes. Push is left to the user.

## 3. Default mode — per-bookmark walker

If `--vocab` is NOT set, walk every `needs_review: true` filed bookmark once, surfacing each via `AskUserQuestion`. The walker is host-LLM-driven: this section orchestrates `Bash` + `Read` + `AskUserQuestion` calls; there is no helper script.

### 3.a — Build the queue

```bash
queue_raw=$(mktemp)
rg -l '^needs_review: true$' "$vault" --type md \
  --glob '!_inbox/**' --glob '!_failed/**' --glob '!_trash/**' --glob '!_broken/**' \
  --glob '!_proposals/**' --glob '!outputs/**' \
  2>/dev/null > "$queue_raw" || true

# Optional --collection scope
if [ -n "$collection_filter" ]; then
  grep "^$vault/$collection_filter/" "$queue_raw" > "$queue_raw.f" 2>/dev/null || : > "$queue_raw.f"
  mv "$queue_raw.f" "$queue_raw"
fi
```

### 3.b — Sort by `enriched:` descending and apply `--limit`

`enriched:` is an ISO-8601 timestamp; lexicographic sort matches chronological sort. Emit one `<path>\t<enriched>` line per file, then `sort -k2,2 -r` and `cut`.

```bash
queue_sorted=$(mktemp)
python3 - "$queue_raw" <<'PYEOF' > "$queue_sorted"
import sys, re
paths = [p for p in open(sys.argv[1]).read().splitlines() if p]
rows = []
for p in paths:
    enriched = ""
    try:
        with open(p) as f:
            head = f.read(4096)
        m = re.search(r"^enriched:\s*(\S+)", head, re.MULTILINE)
        if m:
            enriched = m.group(1)
    except OSError:
        pass
    rows.append((enriched, p))
# Sort by enriched desc; missing enriched sorts last.
rows.sort(key=lambda r: (r[0] == "", r[0]), reverse=False)
rows.sort(key=lambda r: r[0], reverse=True)
for enriched, p in rows:
    print(p)
PYEOF

# Apply --limit (no-op if unlimited)
if [ -n "$limit" ]; then
  head -n "$limit" "$queue_sorted" > "$queue_sorted.l" && mv "$queue_sorted.l" "$queue_sorted"
fi

queue_count=$(wc -l < "$queue_sorted" | tr -d ' ')
```

### 3.c — Empty queue

```bash
if [ "$queue_count" -eq 0 ]; then
  echo "no bookmarks need review"
  rm -f "$queue_raw" "$queue_sorted"
  exit 0
fi
echo "/bm:review: walking $queue_count bookmark(s) with needs_review:true"
```

Initialize counters in working memory: `resolved=0`, `partially=0`, `skipped=0`.

Also initialize a `touched_paths=()` array (used by section 9's optional auto-commit). As the loop runs, append paths whenever the skill mutates the vault:
- After a `tags.yaml` append (Option 1 or Option 2 tag promotion) → append `tags.yaml`.
- After a `mkdir + README.md` (Option 1 creating `proposed_collection`, or Option 4 / Variant-B-Option-2 creating a new "Other" dir) → append the new `<slug>/` (covers both the `README.md` and the about-to-move bookmark).
- After a `mv "$bookmark_file" "$target"` → append both the from-dir and the to-dir (relative to `$vault`).
- After the in-place frontmatter mutation in 3.f (no `mv`) → append the parent dir of `$bookmark_file` (relative to `$vault`).

Dedup the list at the end; section 9 uses it as a set of `git add` paths.

### 3.d — Per-bookmark loop

Use the `Read` tool to load `$queue_sorted`; iterate paths in order. For each `bookmark_file`:

**i. Parse frontmatter** via inline Python. The system `python3` does not have `pyyaml`; use `uv run --with pyyaml` (matches the dep-management pattern from `vocab_warmup.py`):

```bash
uv run --quiet --with pyyaml --no-project -- python3 - "$bookmark_file" <<'PYEOF' > /tmp/bm_review_fm.json
import sys, yaml, re, json, os
path = sys.argv[1]
content = open(path).read()
m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
if not m:
    # File has `needs_review: true` somewhere in the body but no YAML frontmatter
    # (e.g. a design doc containing an example). Mark as skip; walker drops it.
    print(json.dumps({"_skip": True, "_reason": "no frontmatter"}))
    sys.exit(0)
try:
    fm = yaml.safe_load(m.group(1)) or {}
except yaml.YAMLError as e:
    print(json.dumps({"_skip": True, "_reason": f"malformed frontmatter: {e}"}))
    sys.exit(0)
# Confirm `needs_review: true` is actually IN the frontmatter, not just the body.
if fm.get("needs_review") is not True:
    print(json.dumps({"_skip": True, "_reason": "needs_review not in frontmatter"}))
    sys.exit(0)
LLM_MARKER = "<!-- /llm-managed -->"
body = m.group(2) or ""
if LLM_MARKER in body:
    blurb = body.partition(LLM_MARKER)[0].strip()
else:
    # Pre-migration fallback: blurb may still be in frontmatter
    blurb = fm.get("blurb", "") or body.strip()
out = {
    "url":                fm.get("url", ""),
    "title":              fm.get("title", ""),
    "blurb":              blurb,
    "tags":               fm.get("tags") or [],
    "confidence":         fm.get("confidence", 1.0),
    "proposed_tags":      fm.get("proposed_tags") or [],
    "proposed_collection": fm.get("proposed_collection"),
    "current_collection": os.path.basename(os.path.dirname(path)),
}
print(json.dumps(out))
PYEOF
```

Then `Read` `/tmp/bm_review_fm.json` and parse into working memory. If the JSON has `_skip: true`, log `skipping <path>: <_reason>` to stderr, increment `skipped`, and `continue` to the next bookmark — do **not** prompt the user.

**ii. Optional refetch** (only if `--refetch`):

```bash
script="${CLAUDE_PLUGIN_ROOT:-/Users/ali/.claude/plugins/marketplaces/agent-marketplace/plugins/bm}/skills/enrich/lib/extract.py"
extract_out=$("$script" "$bookmark_file" 2>/dev/null) || extract_out=""
```

If extract succeeded, parse JSON, extract a fresh blurb candidate from `body_text_excerpt` (first ~280 chars), and rewrite `blurb:` via section 3.f's mutation pattern with mode `set-blurb`. Skip silently on failure (cached blurb stays).

**iii. Choose the prompt variant** based on parsed frontmatter:

- **Variant A** (full) — used when `proposed_tags` is non-empty OR `proposed_collection` is non-null.
- **Variant B** (low-confidence-only) — used when both are empty/null. The only reason this bookmark needs review is `confidence < 0.4`; the user just needs to confirm or move.

**iv. Build the question text** (used by both variants):

```
<title>
<url>

blurb:    <blurb>

tags:               <tags list, joined by ", ">
current collection: <current_collection>
confidence:         <confidence>

proposed_tags:       <proposed_tags joined; or "(none)">
proposed_collection: <proposed_collection.name> — <proposed_collection.description>
                     (or "(none)")
```

Truncate `blurb` to ~240 chars if longer, with `...` suffix.

**v. Call `AskUserQuestion`**:

**Variant A options** (4; "Other" auto-added):
1. `"Accept all proposed"` — `"Promote proposed_tags to tags.yaml + bookmark.tags; create proposed_collection/ + mv bookmark there."`
2. `"Accept tags, reject collection"` — `"Promote proposed_tags; clear proposed_collection; bookmark stays in current dir."`
3. `"Reject all proposed"` — `"Clear all proposed_* fields; bookmark stays as-is."`
4. `"Move to different collection"` — `"Pick an existing dir via a follow-up prompt."`

**Variant B options** (2; "Other" auto-added):
1. `"Confirm placement (clear needs_review)"` — `"Keep current tags + collection; clear needs_review + confidence."` (Equivalent to Reject-all on a no-proposals bookmark, but framed for clarity.)
2. `"Move to different collection"` — `"Pick an existing dir via a follow-up prompt."`

Both variants use:
- `header`: `"Resolve"` (or first ~12 chars of the title)
- `multiSelect`: `false`

### 3.e — Apply the decision

Branch on the option label. Use the mutation helper in 3.f. Update counters at the end of each branch.

**Option 1 (Variant A) — Accept all proposed**

1. Tag promotion: for each tag in `proposed_tags`, if not already present in `tags.yaml`, append using the `yaml_dq` pattern from section 7.a (variants list is empty since the LLM proposed a single canonical form):
   ```yaml
     - name: <tag>
       description: <tag>
       aliases: []
   ```
   Then merge `proposed_tags` into the bookmark's `tags` list (preserving order, dedup).
2. Collection creation (if `proposed_collection` non-null):
   ```bash
   slug=<proposed_collection.name>
   mkdir -p "$vault/$slug"
   if [ ! -f "$vault/$slug/README.md" ]; then
     printf '# %s\n\n%s\n' "$slug" "<proposed_collection.description>" > "$vault/$slug/README.md"
   fi
   target="$vault/$slug/$(basename "$bookmark_file")"
   if [ -e "$target" ] && [ "$target" != "$bookmark_file" ]; then
     echo "warn: $target exists; leaving bookmark in place" >&2
   else
     mv "$bookmark_file" "$target"
     bookmark_file="$target"
   fi
   ```
3. Frontmatter mutation: mode `clear-proposals-merge-tags` (see 3.f).
4. If `needs_review` was cleared → `resolved++`, else `partially++`.

**Option 2 (Variant A) — Accept tags, reject collection**

1. Tag promotion (same as Option 1 step 1).
2. Frontmatter mutation: mode `clear-proposals-merge-tags`. (Same mutation as Option 1; the difference is we don't `mv` the file.)
3. Counter update as above.

**Option 3 (Variant A) — Reject all proposed**

1. Frontmatter mutation: mode `clear-proposals` (drops `proposed_tags` + `proposed_collection`; does NOT merge tags).
2. If `needs_review` was cleared → `resolved++`, else `partially++`.

**Option 4 (Variant A) or Option 2 (Variant B) — Move to different collection**

Build a recency-ranked list of existing collection dirs:

```bash
python3 - "$vault" <<'PYEOF' > /tmp/bm_review_dirs.txt
import os, sys, re, glob
vault = sys.argv[1]
dirs = []
for entry in os.listdir(vault):
    p = os.path.join(vault, entry)
    if not os.path.isdir(p): continue
    if entry.startswith("_") or entry.startswith("."): continue
    # Most recent enriched among files in this dir
    latest = ""
    for f in glob.glob(os.path.join(p, "*.md")):
        try:
            with open(f) as fh: head = fh.read(2048)
            m = re.search(r"^enriched:\s*(\S+)", head, re.MULTILINE)
            if m and m.group(1) > latest: latest = m.group(1)
        except OSError: pass
    dirs.append((latest, entry))
dirs.sort(reverse=True)
for _, e in dirs: print(e)
PYEOF
```

Take the top 3 dirs (skipping the bookmark's `current_collection`) and call `AskUserQuestion`:
- `header`: `"Move to"`
- `question`: `"Move '<title>' from <current_collection>/ to which collection?"`
- `options`: 3 labels = top 3 dir names; descriptions = a one-line README excerpt if available, else dir name. "Other" auto-added for free-text entry of any other dir.
- `multiSelect`: `false`

On selection:
- If existing dir → `mv "$bookmark_file" "$vault/$choice/"`.
- If "Other" + free-text → treat the text as a kebab-case dir name. If the dir doesn't exist, create it via the same `mkdir + README` pattern as Option 1 (description: empty body; user edits later). Then `mv`.

Frontmatter mutation: mode `clear-proposed-collection` (drops `proposed_collection` only). Then recompute `needs_review`.

**Option 1 (Variant B) — Confirm placement**

Frontmatter mutation: mode `clear-proposals` (no-op on the proposed fields since they're already empty; main effect is to force the recompute and drop `needs_review` + `confidence`). Note: with `confidence < 0.4`, the recompute keeps `needs_review: true` — the only way to clear it from this state is to first re-enrich at a higher confidence, OR for the user to explicitly override.

For now, treat "Confirm placement" as a **force-clear**: in addition to the usual recompute, unconditionally drop `needs_review` and `confidence`. This is the user explicitly saying "this is fine; stop asking." Use mutation mode `force-clear` (see 3.f).

`resolved++`.

**"Other" / free-text on main prompt**

Print `skipped: <user_text>` to stderr; do nothing to the file. `skipped++`.

### 3.f — Frontmatter mutation helper

Use `ruamel.yaml` (not `pyyaml`) here: it round-trips with formatting preserved — flow-style `tags: [a, b, c]` stays flow-style, ISO-8601 datetimes keep the `T` separator, double-quoted strings keep their quotes. Plain `pyyaml.safe_dump` reformats all three and would churn the file.

```bash
uv run --quiet --with ruamel.yaml --no-project -- python3 - "$bookmark_file" "$mode" <<'PYEOF'
import sys, re, io
from ruamel.yaml import YAML
path, mode = sys.argv[1], sys.argv[2]
content = open(path).read()
m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 9999  # prevent ruamel from wrapping long quoted scalars (e.g. blurb)
fm = yaml.load(m.group(1))
body = m.group(2)

proposed_tags = list(fm.get("proposed_tags") or [])

def drop(*keys):
    for k in keys:
        if k in fm: del fm[k]

if mode == "clear-proposals-merge-tags":
    tags = fm.get("tags")
    if tags is None:
        tags = []
        fm["tags"] = tags
    for t in proposed_tags:
        if t not in tags:
            tags.append(t)
    drop("proposed_tags", "proposed_collection")
elif mode == "clear-proposals":
    drop("proposed_tags", "proposed_collection")
elif mode == "clear-proposed-collection":
    drop("proposed_collection")
elif mode == "force-clear":
    drop("proposed_tags", "proposed_collection", "needs_review", "confidence")
elif mode == "set-blurb":
    # v1.3+: blurb lives in body, above the `<!-- /llm-managed -->` marker.
    # Drop any legacy `blurb:` from frontmatter and rewrite the body region.
    import os
    new_blurb = os.environ.get("NEW_BLURB", "").strip()
    if new_blurb:
        drop("blurb")
        LLM_MARKER = "<!-- /llm-managed -->"
        if LLM_MARKER in body:
            _, _, user_notes = body.partition(LLM_MARKER)
            user_notes = user_notes.lstrip("\n").rstrip()
        else:
            user_notes = body.strip()
        parts = [new_blurb, LLM_MARKER]
        new_body = "\n\n" + "\n\n".join(parts) + "\n"
        if user_notes:
            new_body += "\n" + user_notes + "\n"
        body = new_body

# Recompute needs_review (skipped for force-clear, which already cleared it)
if mode != "force-clear":
    still = (
        (fm.get("confidence", 1.0) < 0.4) or
        bool(fm.get("proposed_tags")) or
        bool(fm.get("proposed_collection"))
    )
    if still:
        fm["needs_review"] = True
    else:
        drop("needs_review", "confidence")

buf = io.StringIO()
yaml.dump(fm, buf)
with open(path, "w") as f:
    f.write("---\n" + buf.getvalue() + "---\n" + body)

print("1" if fm.get("needs_review") else "0")
PYEOF
```

Capture the trailing `1` / `0` to decide whether to `resolved++` or `partially++`.

### 3.g — Tag promotion to `tags.yaml` (reused from section 7.a)

When Options 1 or 2 promote new `proposed_tags`, append to `$vault/tags.yaml` using the exact `yaml_dq` quoting pattern from section 7.a. Since `proposed_tags` come from the LLM enricher (no variants), the entry is always:

```yaml
  - name: <tag>
    description: <tag>
    aliases: []
```

Check first whether the tag already exists in `tags.yaml` (union of `name` + `aliases`, canonicalized per section "Conventions"). If yes, skip the append — no duplicates.

### 3.h — Summary

After the loop completes (or `--limit` is hit), print:

```
/bm:review: walked <queue_count> bookmark(s)
  resolved:  <resolved>  (needs_review cleared)
  partially: <partially> (needs_review:true remains, but proposals resolved)
  skipped:   <skipped>   (no decision)
```

Then:
```bash
rm -f "$queue_raw" "$queue_sorted" /tmp/bm_review_fm.json /tmp/bm_review_dirs.txt
```

## 4. Vocab mode — run the scanner

Run the self-bootstrapping uv script. It scans `$vault/_inbox/*.md` (plus `$vault/<dir>/*.md` if `--include-filed`) and emits a JSON decision list to stdout.

```bash
script="${CLAUDE_PLUGIN_ROOT:-/Users/ali/.claude/plugins/marketplaces/agent-marketplace/plugins/bm}/skills/review/lib/vocab_warmup.py"
tmp=$(mktemp)
if ! "$script" --vault "$vault" --min-count "$min_count" --top "$top" ${include_filed:+--include-filed} >"$tmp" 2>&1; then
  echo "vocab_warmup.py failed:" >&2; cat "$tmp" >&2; rm -f "$tmp"; exit 1
fi
```

Then use the `Read` tool to load `$tmp` and parse the JSON. Schema:

```json
{
  "vault":             "/abs/path",
  "scan_count":        1752,
  "min_count":         2,
  "top":               50,
  "tag_candidates": [
    {"canonical": "imdb", "count": 132, "variants": ["IMDb"],
     "sample_urls": ["https://...", "...", "..."]}
  ],
  "collection_candidates": [
    {"original_name": "🤖 AI & Agents", "dir_slug": "ai-agents",
     "count": 23, "sample_urls": ["...", "..."]}
  ],
  "deferred_below_threshold": 5
}
```

Print a one-line preview to the user before prompting:
```
/bm:review --vocab: scanned <scan_count> inbox files; found <T> tag candidates and <C> collection candidates (<deferred_below_threshold> additional below --min-count threshold)
```

If both `tag_candidates` and `collection_candidates` are empty, print `no candidates above threshold` and exit 0. (Idempotency: re-running with no work to do is a silent no-op.)

## 5. Tags phase (run first)

Initialize two lists in working memory: `accepted_tags = []`, `rejected_tags = []`.

Group `tag_candidates` into chunks of **5** in frequency-rank order (the script already sorts by count desc, canonical asc). For each chunk, in order:

### 5.a — Bulk-action prompt

Call `AskUserQuestion` once with:

- **header**: `"Tags <i>/<N>"` (e.g. `"Tags 1/10"`).
- **question**: A multi-line string built as:
  ```
  Tags chunk <i>/<N> (<chunk_size> candidates):
  1. <canonical> — count <count> — sample <sample_urls[0]><variants_suffix>
  2. <canonical> — count <count> — sample <sample_urls[0]><variants_suffix>
  ...
  ```
  Where `<variants_suffix>` is ` (variants: v1, v2)` if `variants` is non-empty, else empty string. Truncate long sample URLs to ~70 chars if needed.
- **options** (exactly 4):
  1. `Accept all <chunk_size>` — description: `"Promote every candidate in this chunk to tags.yaml."`
  2. `Reject all <chunk_size>` — description: `"Skip every candidate in this chunk."`
  3. `Pick individually` — description: `"Decide candidate-by-candidate via follow-up prompts."`
  4. `Skip remaining tags` — description: `"Stop the tags phase here; proceed to collections."`
- **multiSelect**: `false`.

### 5.b — Act on bulk response

- **Accept all** → append every candidate in this chunk to `accepted_tags`. Continue to next chunk.
- **Reject all** → append every candidate to `rejected_tags`. Continue to next chunk.
- **Skip remaining tags** → break out of the tags-phase loop. (Do NOT also break the collections loop.)
- **Pick individually** → cascade to 5.c.

### 5.c — Per-candidate prompt (when "Pick individually")

For each candidate in the current chunk (in order), call `AskUserQuestion`:

- **header**: `"Tag: <canonical>"` (truncate to 12 chars if needed).
- **question**: A multi-line string:
  ```
  Tag candidate: <canonical>
  Count: <count><variants_line>
  Sample URLs:
    - <sample_urls[0]>
    - <sample_urls[1]>
    - <sample_urls[2]>
  ```
  Where `<variants_line>` is `\nVariants found: v1, v2` if `variants` is non-empty, else empty. Omit any sample lines beyond the available URLs.
- **options** (exactly 2):
  1. `Accept` — description: `"Promote to tags.yaml with detected variants as aliases."`
  2. `Skip` — description: `"Do not promote this candidate."`
- **multiSelect**: `false`.

Append candidate to `accepted_tags` or `rejected_tags` accordingly. After the chunk is exhausted, continue to the next chunk.

## 6. Collections phase

Same structure as the tags phase, with these substitutions:

- Iterate `collection_candidates` (already sorted by count desc, dir_slug asc).
- State lists: `accepted_collections = []`, `rejected_collections = []`.
- Bulk question per chunk:
  ```
  Collections chunk <i>/<N> (<chunk_size> candidates):
  1. <dir_slug>/ — count <count> — original "<original_name>" — sample <sample_urls[0]>
  2. ...
  ```
- Per-candidate question (Pick individually):
  ```
  Collection candidate: <dir_slug>/
  Original Raindrop name: <original_name>
  Count: <count>
  Sample URLs:
    - <sample_urls[0]>
    ...
  ```
- Final bulk option label: `Skip remaining collections`.
- Options shape (4 bulk / 2 per-candidate) is identical.

## 7. Apply decisions

After both phases complete (or terminate via "Skip remaining"):

### 7.a — Tags → append to `$vault/tags.yaml`

**Plain-text append**, NOT a pyyaml round-trip (round-tripping would reformat existing flow-style `aliases: [...]` lists into block style and churn the file). For each `c` in `accepted_tags`, construct:

```yaml
  - name: <c.canonical>
    description: <c.canonical>
    aliases: [<quoted_variants_csv>]
```

**Variant quoting (mandatory)** — every variant must be wrapped in double quotes with `\` and `"` escaped, even when it looks "safe". Reason: unquoted variants in a flow list break when they contain `]`, `,`, `"`, leading whitespace, or other YAML-special chars (e.g., `aliases: [bracket]close]` parses as `[bracket]` + dangling junk). Always quote, always escape — never special-case.

Escape rule per variant (matches `yaml_dq()` in `skills/import/lib/raindrop_import.py`):
1. Replace every `\` with `\\`.
2. Replace every `"` with `\"`.
3. Wrap result in `"…"`.

Example transformations:
| variant input  | output token        |
|----------------|---------------------|
| `IMDb`         | `"IMDb"`            |
| `with,comma`   | `"with,comma"`      |
| `bracket]close`| `"bracket]close"`   |
| `quote"in`     | `"quote\"in"`       |
| `back\slash`   | `"back\\slash"`     |

Then `quoted_variants_csv = ", ".join(quoted_tokens)`. When `c.variants` is empty, write `aliases: []` (no quoting needed for an empty list).

Ensure `tags.yaml` ends with a newline before appending. Concatenate all new entries (preceded by a single blank line for visual separation from existing entries) and append in one write.

Python sketch (preferred — bash heredocs can't safely re-quote):
```python
def yaml_dq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

for c in accepted_tags:
    quoted = ", ".join(yaml_dq(v) for v in c["variants"])
    block += f"  - name: {c['canonical']}\n"
    block += f"    description: {c['canonical']}\n"
    block += f"    aliases: [{quoted}]\n"
```

**Verification after write**: parse the resulting `tags.yaml` with `yaml.safe_load` (one-shot). If it fails, the append corrupted the file — abort and surface the parse error so the user can roll back from git. (Existing entries are not re-quoted; only newly-appended ones use the strict-quote form. This is intentional: the existing seed-tag entries are known-safe.)

Where `$variants_csv` is the comma-space-joined list (empty for `aliases: []`).

### 7.b — Collections → create dirs + README

For each `c` in `accepted_collections`:

```bash
mkdir -p "$vault/$dir_slug"
cat > "$vault/$dir_slug/README.md" <<EOF
# $original_name

Imported from Raindrop collection: $original_name
EOF
```

(Note the H1 preserves the original emoji-prefixed name; the body line is the default description per design doc. The user can edit the README.md later to refine.)

If the README.md already exists (race / re-run / pre-existing dir not caught by the filter), **do not overwrite** — print a warning `note: $vault/$dir_slug/README.md already exists; left untouched` and continue.

### 7.c — Order

Apply tags first, then collections. (If something fails mid-tag-apply, the user still has progress to commit; failed collections can be retried by re-running with the same accepts.)

## 8. Summary

After all decisions applied, print:

```
/bm:review --vocab: promoted <T> tags, created <C> collections, skipped <S> candidates, deferred <D> below threshold
```

Where:
- `T = len(accepted_tags)`.
- `C = len(accepted_collections)`.
- `S = len(rejected_tags) + len(rejected_collections)`.
- `D = decision_json.deferred_below_threshold`.

If `T > 0`, suggest:
```
Next: run /bm:enrich --limit 20 --no-prompt to test the warmup impact (target: needs_review:true rate < 30%).
```

## 9. Optional auto-commit

If `--commit` is **not** set, exit here — the user commits manually at milestones (per vault's `AGENTS.md` contract).

If `--commit` **is** set, run the mode-appropriate block.

### 9.a — Vocab mode

Touched paths are derivable directly from the apply step:
- `tags.yaml` — if `len(accepted_tags) > 0`.
- `<slug>/` for each entry in `accepted_collections` — covers the `README.md` written in 7.b.

```bash
if [ "$commit_flag" = "true" ]; then
  pre_staged=$(git -C "$vault" diff --cached --name-only)
  if [ -n "$pre_staged" ]; then
    echo "warning: vault has pre-existing staged changes; skipping auto-commit" >&2
    echo "staged before this run:" >&2
    printf '  %s\n' "$pre_staged" >&2
  else
    [ "$T" -gt 0 ] && git -C "$vault" add tags.yaml
    for slug in "${accepted_collection_slugs[@]}"; do
      git -C "$vault" add "$slug"
    done
    if [ -z "$(git -C "$vault" diff --cached --name-only)" ]; then
      :  # nothing to commit (everything skipped or already in tree)
    else
      msg="bm:review --vocab: promoted $T tags, created $C collections"
      git -C "$vault" commit -m "$msg"
    fi
  fi
fi
```

Where `$T` and `$C` are the same values used in section 8's summary line, and `accepted_collection_slugs` is the list of `dir_slug` values from `accepted_collections`.

### 9.b — Walker mode

Touched paths are accumulated during the per-bookmark loop into `touched_paths` (see section 3.d).

```bash
if [ "$commit_flag" = "true" ]; then
  pre_staged=$(git -C "$vault" diff --cached --name-only)
  if [ -n "$pre_staged" ]; then
    echo "warning: vault has pre-existing staged changes; skipping auto-commit" >&2
    echo "staged before this run:" >&2
    printf '  %s\n' "$pre_staged" >&2
  else
    uniq_paths=$(printf '%s\n' "${touched_paths[@]}" | sort -u)
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      git -C "$vault" add "$p" 2>/dev/null || git -C "$vault" add --update "$p" 2>/dev/null || true
    done <<<"$uniq_paths"
    if [ -z "$(git -C "$vault" diff --cached --name-only)" ]; then
      :  # nothing to commit (e.g. only --refetch-set-blurb that left the file byte-identical)
    else
      msg="bm:review: resolved $resolved bookmarks ($partially partial, $skipped skipped)"
      git -C "$vault" commit -m "$msg"
    fi
  fi
fi
```

Both blocks: the commit does NOT push and does NOT pass `--no-verify`; any pre-commit hooks run as normal.

---

## Idempotency model

- **Empty inbox / no candidates above threshold** → silent no-op (exit 0).
- **Re-run after partial acceptance** — already-promoted tags are in `tags.yaml`, already-created dirs exist; both filters catch them and they don't reappear as candidates. User can safely re-run to handle additional candidates surfaced by a lowered `--min-count`.
- **User cancels mid-run** (Ctrl-C between chunks) — no partial state. Decisions are accumulated in working memory and only applied in section 7 after both phases complete. If interrupted before 7, no files are modified.

## Conventions

- **Tag canonicalization**: lowercase + `re.sub(r"[^a-z0-9]+", "-", ...).strip("-")[:80]`. Variants are original-case strings that don't equal the canonical.
- **Collection canonicalization**: strip leading non-alphanumerics (emoji + ZWJ + variation selectors + whitespace), then same kebab-case slug with 60-char cap.
- **Existing-vocab check**: union of `tags[].name` and `tags[].aliases` (both canonicalized) for tags; non-underscore non-`.git` top-level dirs for collections.
- **Chunk size**: 5 per AskUserQuestion. Smaller than the design doc's 5-10 range — keeps question text scannable and "Pick individually" cascade short.
- **Tags before collections**: tags are the noisier category (≥40 candidates typical); do them while user is fresh.
- **No `--dry-run`**: AskUserQuestion is the manual confirm; no destructive action happens without per-chunk approval.

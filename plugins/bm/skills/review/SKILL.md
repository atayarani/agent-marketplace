---
name: review
description: "Review the enrichment backlog. --vocab mode: batch-promote frequent imported_tags / imported_collection values from the inbox to tags.yaml + collection dirs (pre-enrich warmup, this phase). Default mode: per-bookmark walker for needs_review:true files (post-enrich cleanup, Phase 2.B — not yet implemented). Idempotent; no git commits. Use when the user wants to resolve proposals after /bm:import or /bm:enrich."
argument-hint: "[--vocab] [--min-count N] [--top N] [--include-filed]"
---

Two modes:

- **`--vocab` (pre-enrich, this phase)** — scans the inbox for frequency-ranked `imported_tags` and `imported_collection` hints, presents them in chunks via `AskUserQuestion`, batch-promotes accepted tags to `tags.yaml` and accepted collections to on-disk dirs. Best run after `/bm:import` and **before** `/bm:enrich` drains the queue.
- **Default (post-enrich walker, Phase 2.B)** — walks `needs_review: true` filed bookmarks one at a time. **Not yet implemented in this phase**; this skill prints a stub message and exits 0 when invoked without `--vocab`.

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
```

## 2. Parse arguments

From `$ARGUMENTS`:
- `--vocab` — boolean flag (default false). When set, run vocab-warmup mode (sections 4-7). When unset, run default-mode stub (section 3).
- `--min-count N` — integer (default 2). Tag/collection frequency threshold for promotion. Lower it (e.g. `--min-count 1`) to surface singletons; raise it to prune more aggressively.
- `--top N` — integer (default 50). Cap on candidates per category. Prevents drowning the user.
- `--include-filed` — boolean flag (default false). Also scan filed bookmarks under `$vault/<collection>/*.md`, not just `_inbox/*.md`. (Filed bookmarks per current enrich shape don't carry `imported_*` fields, so this is a no-op in practice today — kept for forward compatibility.)

## 3. Default mode (stub for Phase 2.B)

If `--vocab` is NOT set:

```bash
echo "/bm:review: default-mode walker is Phase 2.B; not yet implemented. Rerun with --vocab to run the pre-enrich vocab warmup."
exit 0
```

Phase 2.B will replace this branch with the per-bookmark walker for `needs_review: true` files.

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

## 9. No git commit

The user commits manually at milestones (per vault's `AGENTS.md` contract).

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

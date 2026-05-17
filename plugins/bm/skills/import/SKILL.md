---
name: import
description: "Import a Raindrop HTML export into the bm vault. Writes one inbox file per bookmark with carry-through imported_tags and imported_collection hints. Does NOT auto-enrich. Use when the user types /bm:import or wants to migrate a Raindrop backup."
argument-hint: "<path-to-raindrop-export.html>"
---

Parse a Raindrop HTML export (Netscape Bookmark File Format) and populate the bm vault's `_inbox/` with one file per `<A>` entry. Each inbox file carries `imported_tags` (from the bookmark's `TAGS=` attribute) and `imported_collection` (from the innermost `<H3>` ancestor folder). The downstream `bm:enricher` subagent reads both as strong hints during enrichment.

> **No subagent or skill changes from Phase 1.C.** The enricher's `## Inputs you should expect` already documents the `imported_tags` / `imported_collection` hints; they flow through unchanged.

`$ARGUMENTS` carries the path to the Raindrop HTML export.

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

## 2. Validate the export path

```bash
export_path="$ARGUMENTS"
[ -z "$export_path" ] && { echo "error: usage: /bm:import <export.html>" >&2; exit 1; }
[ ! -f "$export_path" ] && { echo "error: file not found: $export_path" >&2; exit 1; }
case "$export_path" in
  *.html|*.htm) ;;
  *) echo "error: not an HTML file: $export_path (expected .html or .htm)" >&2; exit 1 ;;
esac
```

## 3. Run the parser

```bash
"${CLAUDE_PLUGIN_ROOT:-.}/skills/import/lib/raindrop_import.py" "$export_path" --vault "$vault"
```

Pass through stdout (`imported: N, skipped: M (deduplicated)`) and stderr (one `skip:` line per deduped URL). The parser:

- Parses Netscape Bookmark File HTML with BeautifulSoup's `html.parser` backend (Raindrop's HTML is loose; strict parsers reject it).
- Walks the DOM in document order, tracking an H3 stack: when an `<H3>` is seen, it's pending; when the next `<DL>` opens, the pending text is pushed; when that `<DL>` exits, it's popped. The top of the stack at each `<A>` is the bookmark's `imported_collection`. Root-level bookmarks (no H3 ancestor) get `imported_collection: ""`.
- For each `<A HREF=... ADD_DATE=... TAGS=...>`:
  - `url` = raw HREF
  - `captured` = ISO 8601 with local TZ from the `ADD_DATE` Unix epoch (falls back to now if missing/invalid)
  - `imported_tags` = `TAGS` split on `,`, each stripped, empties dropped
  - `imported_collection` = top of H3 stack
  - `6id` = first 6 chars of `sha1(url).hexdigest()`
  - Filename: `<YYYYMMDD-HHMMSS-from-captured>-<6id>.md`
- **Dedup**: before the loop, builds a set of all `url:` values across the vault via one `rg -INo '^url: .+$'` pass. URLs already present anywhere in the vault (collection / inbox / failed / trash / broken) are skipped, not duplicated.

## 4. Surface the summary + prompt for enrichment

After the parser exits cleanly, suggest:

```
Run /bm:enrich --limit 20 --no-prompt to process the first batch.
```

`--no-prompt` is the right default for batch flows: enrichment of imported URLs uses `imported_tags` / `imported_collection` as strong signals, but new-collection proposals during a 500-URL import would surface 50+ prompts. With `--no-prompt`, brand-new `proposed_collection` is carried in frontmatter and the user resolves them later (manually, or via a future `/bm:review`).

**Do NOT auto-trigger `/bm:enrich`.** A few-thousand-bookmark import enriched in one go would block for hours.

## 5. No git commit

User commits manually at milestones.

## Conventions

- **Raindrop HTML only.** Pocket / CSV / JSON exports are out of scope.
- **URLs stored verbatim** — no normalization, lowercase, or query-string stripping.
- **`ADD_DATE`** parsed as Unix epoch → ISO 8601 with local TZ (`datetime.fromtimestamp(...).astimezone().isoformat(timespec='seconds')`).
- **`TAGS`** split on `,`, stripped, empties dropped. Always emitted as a YAML flow list (e.g. `["t1", "t2"]` or `[]`).
- **`imported_collection`** = top of H3 stack at the bookmark's document position. Empty string at root.
- **Dedup is one-pass** at the start. URLs added to the inbox earlier in the same run are also tracked (in-run dedup).
- Inbox filename uses the captured timestamp (not now) so the file ordering matches the original Raindrop chronology.

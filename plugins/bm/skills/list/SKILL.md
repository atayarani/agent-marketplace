---
name: list
description: "Search the bm vault for filed bookmarks. Filter by --tag (repeatable), --collection, --status, or --search text — flags AND-compose. Sort by captured (default) or enriched, descending. Output as a markdown table (default), bullet list, or one JSON object per line. Pure shell + inline python — no LLM, no subagent. Use when the user types /bm:list or wants to find specific bookmarks already filed in the vault."
argument-hint: "[--tag X]* [--collection Y] [--status Z] [--search W] [--limit N] [--sort captured|enriched] [--format table|list|json] [--hide-pending]"
---

Search the bm vault. No LLM, no subagent — a single python pass over filed-bookmark YAML frontmatter. Returns matching bookmarks in the chosen format.

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

## 2. Build the candidate file list

Filed bookmarks live at `<vault>/<collection>/<slug>.md`. Top-level files (AGENTS.md, tags.yaml, phase docs) and system dirs (`_inbox/`, `_failed/`, `_trash/`, `_broken/`, `_proposals/`, `outputs/`) are not bookmarks and must be excluded.

`find -mindepth 2 -maxdepth 2` naturally restricts to exactly `<vault>/<dir>/<file>` — no vault-root files, no deeper nesting.

```bash
candidates=$(mktemp)
find "$vault" -mindepth 2 -maxdepth 2 -type f -name '*.md' \
  -not -path '*/_*' \
  -not -path '*/outputs/*' \
  -not -name 'README.md' \
  -not -name '.gitkeep' \
  2>/dev/null > "$candidates" || true

if [ ! -s "$candidates" ]; then
  echo "no bookmarks match the given filters"
  rm -f "$candidates"
  exit 0
fi
```

The `-not -path '*/_*'` predicate skips every `_`-prefixed system dir in one shot (the vault contract: collections never start with `_`).

## 3. Filter, sort, format, print

Hand off to python via the same `uv run --with pyyaml` pattern as `review/SKILL.md` step 3.d.i. Python parses `$ARGUMENTS` via `argparse` + `shlex.split`, loads frontmatter for each candidate, applies AND-semantic filter predicates, sorts by `captured`/`enriched` desc, truncates to `--limit`, and emits the chosen format.

```bash
uv run --quiet --with pyyaml --no-project -- python3 - "$candidates" "$ARGUMENTS" <<'PYEOF'
import sys, yaml, re, os, json, shlex, argparse
from datetime import datetime, date as _date

candidates_path = sys.argv[1]
args_str = sys.argv[2] if len(sys.argv) > 2 else ""

def _stringify(o):
    """YAML parses ISO-8601 timestamps to datetime objects; stringify for safe downstream use."""
    if isinstance(o, dict):
        return {k: _stringify(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_stringify(v) for v in o]
    if isinstance(o, (datetime, _date)):
        return o.isoformat()
    return o

p = argparse.ArgumentParser(prog="/bm:list", add_help=False)
p.add_argument("--tag", action="append", default=[])
p.add_argument("--collection", default=None)
p.add_argument("--status", default=None)
p.add_argument("--search", default=None)
p.add_argument("--limit", type=int, default=20)
p.add_argument("--sort", choices=["captured", "enriched"], default="captured")
p.add_argument("--format", dest="fmt", choices=["table", "list", "json"], default="table")
p.add_argument("--hide-pending", action="store_true")
try:
    args = p.parse_args(shlex.split(args_str))
except SystemExit:
    print(
        "usage: /bm:list [--tag X]* [--collection Y] [--status Z] [--search W] "
        "[--limit N] [--sort captured|enriched] [--format table|list|json] [--hide-pending]",
        file=sys.stderr,
    )
    sys.exit(2)

paths = [ln for ln in open(candidates_path).read().splitlines() if ln]
search_lower = args.search.lower() if args.search else None

matches = []
for path in paths:
    try:
        content = open(path).read()
    except OSError:
        continue
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not m:
        continue
    try:
        fm = _stringify(yaml.safe_load(m.group(1)) or {})
    except yaml.YAMLError:
        continue

    coll = os.path.basename(os.path.dirname(path))
    if args.collection and coll != args.collection:
        continue

    tags = fm.get("tags") or []
    if not all(t in tags for t in args.tag):
        continue

    if args.status and fm.get("status") != args.status:
        continue

    if search_lower:
        hay = ((fm.get("title") or "") + " " + (fm.get("blurb") or "")).lower()
        if search_lower not in hay:
            continue

    if args.hide_pending and fm.get("needs_review") is True:
        continue

    matches.append((path, coll, fm))

matches.sort(key=lambda r: r[2].get(args.sort) or "", reverse=True)
matches = matches[: args.limit]

if not matches:
    print("no bookmarks match the given filters")
    sys.exit(0)

def trunc(s, n=60):
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"

def date_only(s):
    s = s or ""
    return s[:10] if len(s) >= 10 else s

if args.fmt == "table":
    print("| Title | URL | Tags | Collection | Captured |")
    print("|---|---|---|---|---|")
    for path, coll, fm in matches:
        title = trunc(fm.get("title") or "", 60).replace("|", "\\|")
        url = (fm.get("url") or "").replace("|", "\\|")
        tags = ", ".join(fm.get("tags") or []) or "—"
        tags = tags.replace("|", "\\|")
        captured = date_only(fm.get("captured") or "")
        print(f"| {title} | {url} | {tags} | {coll} | {captured} |")

elif args.fmt == "list":
    for path, coll, fm in matches:
        title = fm.get("title") or ""
        url = fm.get("url") or ""
        tags = ", ".join(fm.get("tags") or [])
        captured = date_only(fm.get("captured") or "")
        print(f"- [{title}]({url}) — tags=[{tags}], collection={coll}, captured={captured}")

elif args.fmt == "json":
    for path, coll, fm in matches:
        out = {
            "path": path,
            "url": fm.get("url") or "",
            "title": fm.get("title") or "",
            "blurb": fm.get("blurb") or "",
            "tags": fm.get("tags") or [],
            "collection": coll,
            "captured": fm.get("captured") or "",
            "enriched": fm.get("enriched") or "",
            "status": fm.get("status") or "",
            "needs_review": bool(fm.get("needs_review")),
        }
        print(json.dumps(out, ensure_ascii=False))
PYEOF

rm -f "$candidates"
```

## 4. Notes

- **AND semantics**: every flag must match. `--tag dev-tools --tag cli` requires both tags; `--tag dev-tools --collection gaming` requires both.
- **Search scope**: `title` + `blurb` only. URL is not searched (use `rg` directly for URL substring search). Body is empty by design.
- **Sort stability**: ISO-8601 timestamps lex-sort correctly, so a string compare on `captured` / `enriched` matches chronological order.
- **No `--offset` / `--page`**: deferred until needed; `--limit` is the only pagination knob.
- **System dirs**: `_inbox/`, `_failed/`, `_trash/`, `_broken/`, `_proposals/`, `outputs/` are excluded by the `*/_*` glob plus the explicit `outputs/` predicate. Confirm whenever a new system dir is added to the vault contract.

## Verification gate

Run from `/Users/ali/Documents/obsidian/whiskers/`:

- `/bm:list` — default flags; up to 20 most-recent filed bookmarks in a markdown table.
- `/bm:list --tag dev-tools` — only `dev-tools`-tagged bookmarks.
- `/bm:list --collection gaming` — only files under `gaming/`.
- `/bm:list --search "idleon"` — case-insensitive substring on title+blurb.
- `/bm:list --tag dev-tools --collection dev-tools` — AND intersection.
- `/bm:list --sort enriched` — different ordering than default `captured`.
- `/bm:list --format json | jq -s 'length'` — JSON parses cleanly.
- `/bm:list --hide-pending` — excludes `needs_review: true`.
- `/bm:list --tag bogus-tag-doesnt-exist` — prints `no bookmarks match the given filters` and exits 0.
- `/bm:list --limit 5` — caps at 5 rows.
- `/bm:list` from outside the vault — `$BM_VAULT` env var or one of the default-location fallbacks resolves.
- Files in `_inbox/`, `_failed/`, `_trash/`, `_broken/`, `_proposals/`, `outputs/` never appear.
- Vault-root files (AGENTS.md, tags.yaml, phase docs) never appear.

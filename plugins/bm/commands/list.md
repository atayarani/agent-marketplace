---
description: "Search the bm vault for filed bookmarks. Filter by --tag, --collection, --status, or --search text — multiple flags compose with AND. Default: 20 most-recently captured in a markdown table. Pure shell + inline python; no LLM, no subagent. Use when the user types /bm:list or wants to find a specific bookmark."
argument-hint: "[--tag X] [--collection Y] [--status Z] [--search W] [--limit N] [--sort captured|enriched] [--format table|list|json] [--hide-pending]"
---

Search the bm vault for filed bookmarks. Pure shell + inline python — no LLM, no subagent, no token cost. Returns matching bookmarks in the chosen format (markdown table by default).

Use the `list` skill's `SKILL.md` for the full runbook. The skill walks `<collection>/*.md` files (excludes system dirs `_*` and `outputs/`), parses each frontmatter, applies AND-semantic filter predicates, sorts by `captured` or `enriched` descending, truncates to `--limit`, and prints.

## Flags

- `--tag X` (repeatable) — bookmark must have X in its `tags:` list. Multiple `--tag` flags AND together (intersection).
- `--collection Y` — scope to `$vault/Y/`.
- `--status Z` — bookmark's `status:` field equals Z (`active`, `broken`, `archived`).
- `--search W` — case-insensitive substring match against `title:` + `blurb:`. URL and body are not searched.
- `--limit N` — cap on results (default `20`).
- `--sort captured|enriched` — sort key, descending (default `captured`).
- `--format table|list|json` — output shape (default `table`).
  - `table` — markdown table: Title | URL | Tags | Collection | Captured.
  - `list` — bullet list: `- [title](url) — tags=[...], collection=<col>, captured=<date>`.
  - `json` — one JSON object per line (pipe to `jq`).
- `--hide-pending` — exclude bookmarks with `needs_review: true`.

## Examples

- `/bm:list` — 20 most-recently captured bookmarks across the whole vault.
- `/bm:list --tag dev-tools --limit 50` — up to 50 `dev-tools`-tagged bookmarks.
- `/bm:list --collection gaming --sort enriched` — all bookmarks in `gaming/`, most recently enriched first.
- `/bm:list --search "kubernetes" --hide-pending` — finalized bookmarks mentioning kubernetes in title or blurb.
- `/bm:list --format json | jq 'select(.tags | contains(["cli"]))'` — pipe to `jq` for ad-hoc shape transforms.

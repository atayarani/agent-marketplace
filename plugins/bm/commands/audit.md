---
description: "Health-audit the bm vault: links, tags, or collections. Prints report to chat — never written into the vault. Only `links` mutates state (moves dead URLs to `_broken/`, flips `status: broken`). `tags` runs a Sonnet pass for semantic synonym confirmation; pass `--skip-llm` to skip. Idempotent. Use when the user types `/bm:audit <kind>` or wants to surface drift in the vault."
argument-hint: "<links|tags|collections> [--skip-llm] [--dry-run] [--out PATH] [audit-specific flags]"
---

Run a health audit on the bm vault. One skill, three modes (positional arg). Reports print to chat by default; use `--out PATH` to write to a file *outside* the vault.

| Mode | Mutates? | LLM? | Surfaces |
|---|---|---|---|
| `links` | yes (`_broken/` move, `status: broken` flip) | no | Two-pass HEAD→GET checker. Only 404/410/451 confirm-broken; 401/403/429 stay bot-walled. |
| `tags` | no | yes (Sonnet, opt-out) | Rare / over-broad / ghost tags + LLM-verdicted synonym merges. |
| `collections` | no | no | Sparse (<3) merge proposals, bloated (>50) nesting proposals, size histogram. |

Use the `audit` skill's `SKILL.md` for the full runbook. Brief steps:

1. **Locate the vault** — walk up from `$PWD` for an `AGENTS.md` titled "Bookmarks Vault". Fallbacks (first match wins): `$BM_VAULT`, `~/Documents/obsidian/whiskers/`, `~/Documents/whiskers/`, `~/whiskers/`.
2. **Parse positional arg** — first non-flag token is the mode. Common flags (`--out`, `--skip-llm`) handled by the skill. Mode-specific flags pass through to the underlying script. Hard-reject `--out PATH` when PATH is inside the vault.
3. **Dispatch** — run `lib/audit_<mode>.py`. `tags` mode does a two-phase analyze → Sonnet verdict → render unless `--skip-llm`.
4. **Print or redirect** — markdown to stdout (lands in chat) or to `$out_path` if set.

## Flags

**Common:**

- `--out PATH` — write report to PATH (must be outside the vault). Useful when output would be large.
- `--skip-llm` — `tags` only. Skip Sonnet verdict pass; raw Levenshtein candidates listed for manual review.

**`links`:**

- `--dry-run` — classify without moving files or editing frontmatter. Recommended for the first run on a large vault.
- `--concurrency N` (default 10) — parallel HTTP requests.
- `--timeout S` (default 10) — per-request timeout in seconds.
- `--user-agent STR` — override the default browser-mimic UA.
- `--limit N` — cap targets for testing; 0 means no cap.

**`tags`:**

- `--rare-threshold N` (default 3) — tags with fewer uses are "rare".
- `--broad-pct P` (default 0.20) — tags applied to more than 20% of bookmarks are "over-broad".
- `--levenshtein-max N` (default 2) — pair distance cap for synonym candidates.

**`collections`:**

- `--sparse-threshold N` (default 3) — collections with fewer bookmarks are "sparse".
- `--bloat-threshold N` (default 50) — collections with more bookmarks are "bloated".
- `--nest-cluster-min N` (default 10) — minimum bookmarks sharing a tag for a bloated collection to propose a nest.

## Examples

- `/bm:audit collections` — fastest audit; pure stats; report to chat.
- `/bm:audit tags --skip-llm` — offline tag audit; raw candidates for manual review.
- `/bm:audit tags` — full audit with Sonnet synonym verdicts.
- `/bm:audit links --dry-run --limit 50` — preview link classification without touching the vault.
- `/bm:audit links` — full link audit; confirmed-broken files moved to `_broken/`.
- `/bm:audit collections --out /tmp/bm-audit.md` — write report to `/tmp/`; only one-line summary in chat.

## Notes

- **The vault never receives audit reports.** Use `--out PATH` for paths outside the vault when output is large.
- **Bot-walled is conservative.** Cloudflare-fronted sites (printables.com, X/Twitter, many others) return 403 to non-browser clients regardless of UA. The classifier treats 401/403/429 as `bot_walled` and never moves them. If you have a known-dead 403 URL, flip its `status: broken` manually.
- **`tags` LLM pass is opt-out.** The Sonnet verdict step is where most of the value is — only skip when offline or cost-sensitive.

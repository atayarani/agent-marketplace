# Redesign: agent-marketplace → canonical content + per-harness adapters

## Context

`agent-marketplace` ships 6 sub-plugins (bm, bookmark, journal, reviewers, wiki_keeper)
to multiple coding-agent harnesses. Today each plugin carries **hand-authored, parallel
manifests** per harness, and the repo root holds hand-authored marketplace catalogs. This
is exactly the drift machine the project's own AGENTS.md warns about ("Marketplace drift
is the most common bug here") — and it has already drifted:

- `reviewers` is `0.2.2` in `.claude-plugin/plugin.json` but `0.2.1` in `.codex-plugin/plugin.json`.
- `.agents/plugins/marketplace.json` (Codex catalog) lists only 3 of 5 plugins; `bm`/`bookmark` are missing.
- The committed `gemini/` symlink farm is frozen at a **pre-`bm` state** and is **unrebuildable**: `bm/audit.md` collides with `wiki_keeper/audit.md`, and `bm`≡`bookmark` collide on every name, so `bin/sync-gemini.sh` aborts on collision. **Gemini support is silently broken right now.**

We refactor to the model from the design note (`agent-marketplace-cross-harness-design.md`):
**`plugins/<name>/` stays as canonical, paradigm-agnostic content; one `bin/adapters/<harness>.sh`
per harness generates that harness's manifests and installs via its native mechanism; a `Makefile`
drives them.** Generated manifests are gitignored build artifacts — drift becomes structurally
impossible. Per-harness logic lives in exactly one file per harness.

Two scope decisions confirmed with the user that go *beyond* the original note:
1. **Pi is a first-class target this pass** (Pi 0.79.0 is installed; lack of support is why it's unused).
2. **Hooks must run on Codex and Pi** (Gemini a bonus) — not "Claude-only."

### Verified facts (don't re-derive these)

- **Claude** (verified, official docs): a folder at `~/.claude/skills/<name>/` containing `.claude-plugin/plugin.json` loads as `<name>@skills-dir` — bundling *"its own skills, agents, hooks, and more"* — *"with no marketplace and no install step,"* *"discovered in place rather than copied."* Personal scope has no trust/restriction gates. A **whole-directory symlink** works (discovered in place); `SKILL.md` edits are live, agent/hook changes need `/reload-plugins`. Remove = delete the symlink + `claude plugin disable <name>@skills-dir`. **marketplace.json is install-UI only; not needed at runtime.**
- **Codex** (doc-verified; *Codex is NOT installed on this machine*): reads `hooks/hooks.json` from the plugin root and sets `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA` "for compatibility with existing plugin hooks." Payload fields match Claude (`tool_name`, `tool_input`, `prompt`); supports `{decision:"block",reason}` and exit-2. Local install path is `codex marketplace add <local-path>` reading `.agents/plugins/marketplace.json` (resolves `source.path` relative to the catalog root). **Codex needs a generated catalog — it cannot drop it the way Claude can.**
- **Gemini** (doc-verified; *NOT installed here*): one extension per repo, single flat namespace per kind; `gemini extensions link <path>` (symlink, dev) or `install --path` (copy); reads `gemini-extension.json` + the farm.
- **Pi** (installed, 0.79.0): discovers Claude-compatible `SKILL.md` skills from `~/.pi/agent/skills/<name>/` (recursive) and `.pi/skills/`; reads `AGENTS.md` as a context file; extensions are **TypeScript** at `~/.pi/agent/extensions/*/index.ts`, installed via `pi install npm:<pkg>` / `git:`. Extension API: `export default function(pi){ pi.on("tool_call", async (event,ctx)=>{ /* event.toolName, event.input mutable */ return {block:true, reason} }) }`; `pi.on("input", …)` returns `{action:"handled"|"transform"|"continue", text}`; `pi.on("before_agent_start", …)` can modify the prompt/system prompt. `pi.exec()` and `node:child_process` are available; extensions "run with full system permissions." **Pi has no shell-command hook mechanism — only TS callbacks.**

---

## Target architecture

```
plugins/<name>/
  meta.yaml            NEW — single hand-authored source per plugin
  skills/  commands/  agents/  hooks/  server/   ← UNCHANGED canonical content
bin/
  adapters/
    claude.sh   codex.sh   gemini.sh   pi.sh      NEW — one file per harness
    pi/hook-bridge/index.ts                        NEW — Pi TS hook bridge
  sync-gemini.sh                                   retired → shim to gemini.sh build
Makefile               NEW — build / install[-<h>] / uninstall-<h> / clean / validate / help
HARNESS-NOTES.md       NEW — per-harness behavior + verify/confidence flags
AGENTS.md  README.md   rewritten
.gitignore             generated artifacts added
```

Generated (and gitignored): `plugins/*/.claude-plugin/plugin.json`,
`plugins/*/.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`,
`.claude-plugin/marketplace.json`, `gemini-extension.json`, `gemini/`.

---

## 1. `plugins/<name>/meta.yaml`

Single hand-authored source the adapters read. YAML (already the frontmatter idiom). Parse with
`python3` (already a repo dependency via hook scripts) — **not** `grep|cut`: `journal`'s description
is multi-line with colons, em-dashes, and unicode glyphs.

```yaml
# plugins/reviewers/meta.yaml
name: reviewers
version: 0.2.2                 # single-sourced; fixes the 0.2.2/0.2.1 drift (pick 0.2.2)
description: Parallel PR review with a selectable team of reviewers.
# Optional:
# display_name: Reviewers       # Codex/Gemini display label; default = titlecased name
# alias_of: bm                  # this plugin's content is symlinks into another (bookmark)
# harnesses: [claude, codex, pi] # which harnesses install this; default = all four
# requires: { subagents: true }  # has agents/ → Pi adapter installs pi-subagents
```

- **`version` lives here**, projected into every generated manifest. The drift *is* the argument against parallel hand-authoring.
- **`bm` sets `harnesses: [claude, codex, pi]`** (excludes Gemini). This single field resolves *both* Gemini problems at once: bm's `server/` daemon can't resolve through Gemini's per-kind farm, and `bm/audit` would collide with `wiki_keeper/audit` in Gemini's flat namespace.
- **`bookmark` sets `alias_of: bm`**. Gemini adapter skips alias plugins (avoids the bm≡bookmark collision); Claude/Codex/Pi still install it (its `agents/commands/skills` symlinks resolve to bm content → `/bookmark:*` works).
- `requires.subagents` defaults to "presence of `agents/`"; the field is an explicit override so pi.sh can decide whether to `pi install pi-subagents` without globbing.

---

## 2. Adapter contract (`bin/adapters/<harness>.sh`)

Shared shape: `bin/adapters/<harness>.sh <build|install|uninstall> [plugin]`.

- **`build`** — pure function of `meta.yaml` + content → writes that harness's manifest projection(s) into the working tree (gitignored). No `$HOME` writes.
- **`install`** — runs `build`, then places content into the harness install root via the harness's native mechanism, **symlink-preferred** (whole-plugin-dir where possible — preserves bm's `$CLAUDE_PLUGIN_ROOT/server/` invariant and gives instant edit-reflect). `COPY=1` falls back to copy.
- **`uninstall`** — removes **only** what it created in the install root, guarded by `test -L` + `readlink` prefix-check so it never `rm -rf`s a symlink target back into the repo. **Never touches `plugins/`.**
- **`INSTALL_ROOT="${PREFIX:-<default>}"`** — the one machine-specific fact per adapter on one line; also the dry-run handle (`PREFIX=/tmp/t …`).

Sketches (concise — model on the existing `bin/sync-gemini.sh`):

- **claude.sh** — `build`: generate `plugins/<name>/.claude-plugin/plugin.json` from meta.yaml. `install`: for each plugin (honoring `harnesses`), symlink `plugins/<name>` → `$INSTALL_ROOT/skills/<name>` (`INSTALL_ROOT=$HOME/.claude`). Hooks ride along inside the dir. `uninstall`: `rm` the symlink (guarded) + note `claude plugin disable <name>@skills-dir`.
- **codex.sh** — `build`: generate per-plugin `.codex-plugin/plugin.json` **and** the root `.agents/plugins/marketplace.json` (one entry per non-alias, `harnesses`-included plugin; `source.path = ./plugins/<name>`). `install`: `codex marketplace add "$repo_root"`. `uninstall`: `codex marketplace remove agent-marketplace`. *(Commands/agents/skills + `hooks/hooks.json` are consumed natively from the plugin root.)*
- **gemini.sh** — port `sync-gemini.sh`: rebuild `gemini/{commands,skills,subagents}/`, **skipping any plugin where `alias_of` is set or `harnesses` excludes gemini** (deterministic instead of abort); keep collision-abort for genuine clashes between remaining plugins. Generate `gemini-extension.json` from meta.yaml. `install`: `gemini extensions link "$repo_root"`.
- **pi.sh** — `install` (honoring `harnesses`): symlink each plugin's `skills/*` into `$INSTALL_ROOT/skills/<name>/` (`INSTALL_ROOT=$HOME/.pi/agent`); if a plugin has `agents/` (or `requires.subagents`), `pi install pi-subagents` (idempotent) and symlink agents into Pi's agent path; install the hook bridge (Phase 4). Commands→Pi mapping (Claude flat `commands/*.md` vs Pi's `/skill:*` model) is a **verify-during-impl** item — likely surfaced as skills or prompt-templates.

---

## 3. Hooks (canonical format = `hooks.json`)

**`hooks.json` is itself the canonical intermediate** — no `events.yaml`. Claude and Codex both
consume it natively. But portability splits by hook *kind* (the script logic, not the envelope):

| Hook | Kind | Claude | Codex | Pi |
|---|---|---|---|---|
| `reviewers/prompt_require_diff` | prompt-driven (`UserPromptSubmit`, reads `prompt`) | native | **native, unchanged** (same field) | bridge via `input`/`before_agent_start` (`event.text`) |
| `wiki_keeper/protect_*` | tool-interception (`PreToolUse`, matcher `Edit\|Write\|NotebookEdit`, reads `tool_input.file_path`, switches on `tool_name`) | native | **needs adaptation** | **needs adaptation** |

**Tool-interception hooks do not port for free.** On Codex, file edits are `apply_patch` with
`tool_input.command` (a patch string) — the `Edit|Write|NotebookEdit` matcher never fires and
`file_path` is absent. On Pi, tools are lowercase `edit`/`write` with a different input shape.
The failure mode is **silent open** (hook doesn't fire → no protection), so this needs a
Claude→harness **tool-name + tool_input map**, and verification must confirm an actual **block**.

**Pi hook bridge** (`bin/adapters/pi/hook-bridge/index.ts`, new generic component):
a TS extension installed into `~/.pi/agent/extensions/hook-bridge/` that, for each installed
plugin's `hooks/hooks.json`:
- `PreToolUse` entries → `pi.on("tool_call", …)`: map `event.toolName` (e.g. `edit`/`write`) to the Claude tool name, build a Claude-shaped JSON payload (`{hook_event_name, tool_name, tool_input, cwd}`), `execFile` the script with that JSON on stdin and `CLAUDE_PLUGIN_ROOT` set, parse `{decision:"block",reason}` / exit-2 → return `{block:true, reason}`.
- `UserPromptSubmit` entries → `pi.on("input", …)`: payload `{hook_event_name, prompt: event.text}`; block → `{action:"handled"}` surfacing the reason.

Gemini hooks: **deferred (bonus)** — `gemini-extension.json` has no hook key today; document as a known gap.

---

## 4. `.gitignore`

Ignore generated **files** (not the `.claude-plugin/` dir — it may also hold a hand-authored `.lsp.json`):

```
__pycache__/
.DS_Store

# Generated manifest projections — built by bin/adapters/*.sh. Source of truth: plugins/<name>/meta.yaml.
/plugins/*/.claude-plugin/plugin.json
/plugins/*/.codex-plugin/plugin.json
/.agents/plugins/marketplace.json
/.claude-plugin/marketplace.json
/gemini-extension.json
/gemini/
```

Do **not** ignore `plugins/*/hooks/hooks.json` — that is hand-authored canonical content.

---

## 5. Makefile

Targets: `help` (default), `build`, `install` (all harnesses), `install-%`, `uninstall-%`
(pattern rules over `claude codex gemini pi`), `clean` (rm generated artifacts from the tree),
`validate` (`build` then `claude plugin validate .`; other validators wired in as available).
No per-harness logic in the Makefile — it only dispatches to `bin/adapters/<harness>.sh`.
`PREFIX=/tmp/sandbox make install-claude` is the sandboxed dry-run path.

---

## Migration — phased by what's verifiable on THIS machine

Each phase leaves the repo working; the old catalogs stay as a safety net until Phase 5.

- **Phase 0 — meta.yaml authoring.** Add `meta.yaml` to all 6 plugins; set `bm.harnesses` (no gemini) and `bookmark.alias_of: bm`; fix the reviewers version to `0.2.2`. Pure addition — nothing reads it yet.
- **Phase 1 — Claude adapter + Makefile (LOCALLY VERIFIABLE; ships standalone).** `bin/adapters/claude.sh` + Makefile skeleton. This phase alone is a complete, usable refactor. Verify per §Verification. *Keep old catalogs.*
- **Phase 2 — Codex + Gemini adapters (DOC-VERIFIED ONLY — not installable here).** `codex.sh` (generate catalog + `.codex-plugin/plugin.json`), `gemini.sh` (port sync-gemini + `alias_of`/`harnesses` skip + manifest gen). Retire `bin/sync-gemini.sh` → one-line shim to `gemini.sh build`.
- **Phase 3 — Pi content (LOCALLY VERIFIABLE).** `pi.sh` skills + agents symlinks + `pi install pi-subagents`. (Hooks deferred to Phase 4.)
- **Phase 4 — Cross-harness hooks (HARDEST / EXPERIMENTAL — deferrable without blocking 1–3).** reviewers prompt hook on Codex/Pi (cheap); Pi `hook-bridge` extension; wiki_keeper tool-interception adaptation (Claude→Codex/Pi tool maps). Per-hook block-verification required.
- **Phase 5 — Flip + docs.** `git rm -r --cached gemini/ .claude-plugin/marketplace.json .agents/plugins/marketplace.json gemini-extension.json plugins/*/.claude-plugin/plugin.json plugins/*/.codex-plugin/plugin.json`; commit the `.gitignore`. Rewrite AGENTS.md (Layout / How it works / Adding recipes / Cross-tool gotchas) + README (Install = `make install-<harness>`; the plugin table becomes the human catalog that replaced marketplace.json); add HARNESS-NOTES.md (per-harness paths, hook support matrix, bm-on-Gemini gap, Codex/Pi confidence flags).

---

## Verification (honest about machine limits)

- **Claude (Phase 1, real):** `PREFIX=/tmp/mp bin/adapters/claude.sh install reviewers` → `claude --plugin-dir /tmp/mp/skills/reviewers`; confirm `/reviewers:deep-review-pr` appears, `/agents` lists the 5 reviewers, and the **hook fires** (a `deep-review` prompt with no diff is blocked). Repeat for a no-`agents` plugin (journal) and the alias (bookmark). `--plugin-dir` is the zero-risk loader; never touch real `~/.claude`.
- **Pi content (Phase 3, real):** install into a temp `PI_*`/`HOME`; confirm `/skill:*` shows the marketplace skills and `pi install pi-subagents` is idempotent.
- **Pi hooks (Phase 4, real):** trigger `protect_raw_sources` on an actual Pi `edit` of a `sources/raw/` path and confirm it **blocks** (silent non-firing = failure). Same for the reviewers prompt hook.
- **Codex + Gemini (Phase 2, CANNOT verify here):** neither CLI is installed on this machine. State plainly in HARNESS-NOTES.md that these adapters are doc-built and untested; verification requires a machine with `codex` / `gemini` (`HOME=/tmp/… codex marketplace add "$repo_root"` then list; `gemini extensions link` against a temp HOME). Flag the Codex `~/.codex` path, `marketplace add/remove` subcommand names, and `apply_patch` tool-name mapping as to-verify.

## Risks / open items

- **Silent-open hooks** on Codex/Pi for tool-interception — the headline correctness risk; mitigated only by block-verification, not "no error."
- **Codex/Gemini unverifiable locally** — Phase 2 is doc-confidence, not tested.
- **`pi-subagents` package choice** — several forks exist (tintinweb, nicobailon, @ifi, …); pin one in pi.sh and record why.
- **Pi command mapping** — Claude flat `commands/*.md` vs Pi `/skill:*`; resolve during Phase 3.
- **bm on Gemini** — intentionally excluded (`harnesses`); documented, not fixed.
- **`yaml_get` robustness** — use a real YAML parse for `journal`'s multi-line/unicode description.

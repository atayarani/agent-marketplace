# CONTEXT — cross-harness adapter refactor (resume handoff)

**Last updated:** 2026-06-11 · **State:** Done + hardened, all on `main` (pushed; latest ≈ `b57ef89`).
Phases 0–5 + post-Phase-5 hardening: Gemini tool-interception, Pi hook-bridge, Gemini+Pi
subagents, selective install (`PLUGIN=`). Only Codex-specific gaps remain (documented).

> **Canonical in-repo docs are now [AGENTS.md](AGENTS.md)** (architecture + recipes) **and
> [HARNESS-NOTES.md](HARNESS-NOTES.md)** (per-harness behaviour + limits). This file is the
> historical build log / resume aid — if it disagrees with those, they win. `REDESIGN-PLAN.md`
> is the original plan, whose Codex/Gemini/Pi assumptions were wrong in load-bearing ways (see
> VERIFIED HARNESS FACTS below).

---

## TL;DR — where we are

Goal: replace hand-authored, per-harness manifests with **one canonical source per plugin**
(`plugins/<name>/meta.yaml`) + **one adapter per harness** (`bin/adapters/<h>.sh`) driven by a
`Makefile`. Generated manifests become gitignored build artifacts (that flip happens in Phase 5).

- **Done & committed (Phases 0–5):** meta.yaml authoring, Claude/Codex/Gemini/Pi adapters,
  shared `lib.sh`, `Makefile`, the Gemini extension rebuild, the portable reviewers hook
  (Claude+Codex+Gemini), and the gitignore-flip + doc rewrite (AGENTS.md, README.md, HARNESS-NOTES.md).
- **Remaining:** nothing required. Only Codex-specific gaps are left, both documented in
  HARNESS-NOTES: tool-interception (apply_patch/shell — investigated, opaque hook model) and
  subagents. Everything else is built + verified — Gemini tool-interception, the Pi hook-bridge,
  and subagent portability to Gemini + Pi.
- **All four CLIs were installed on the original dev machine** (Claude 2.1.170, codex-cli
  0.139.0, gemini 0.45.3, pi 0.79.1) — **a new machine may differ; verify before installing.**

---

## Resuming on a new machine

1. `git clone` the repo (all on `main`). Generated manifests are gitignored — `make build` rebuilds them.
2. Verify the CLIs you use are present (versions above are the original machine's).
3. Install — **nothing is installed by default after a clone:**
   - `make install-<harness>` (all plugins) or `make install-<harness> PLUGIN=bm,journal` (subset; comma list).
4. **Claude was migrated on the original machine** to the skills-dir model: `bm`, `journal`,
   `wiki_keeper` are `~/.claude/skills/<name>` symlinks into the repo (the old GitHub-marketplace
   installs + the `agent-marketplace` marketplace were removed). Reproduce on the new machine with
   `make install-claude PLUGIN=bm,journal,wiki_keeper`. **Codex/Gemini/Pi had nothing installed.**
   Note: skills-dir installs are symlinks into the repo path — keep the repo put, or re-run install.
5. Canonical docs: **AGENTS.md** (architecture + recipes), **HARNESS-NOTES.md** (per-harness behaviour,
   limits, and copy-paste sandbox/verify recipes). This file is the historical log.

---

## Phase status

| Phase | What | Status |
|---|---|---|
| 0 | `plugins/<name>/meta.yaml` ×5 | ✅ done, committed |
| 1 | `claude.sh` + `Makefile` | ✅ done, verified live (hook fires/blocks via `--plugin-dir`) |
| 2 | `codex.sh` + `gemini.sh` (install mechanism) | ✅ done, verified live in sandbox homes |
| 3 | `pi.sh` (skills + commands→prompt-templates) | ✅ done, verified live |
| **2b** | **Gemini adapter redesign (real 0.45 model)** | ✅ done, verified live (10 commands + 11 skills register; `gemini extensions validate` passes) |
| **4** | **Cross-harness hooks + agent definitions** | ✅ done — reviewers hook portable to Claude+Codex+Gemini; tool-interception / Pi-bridge / subagents deferred (documented in HARNESS-NOTES) |
| **5** | **Flip artifacts to gitignored + rewrite docs** | ✅ done — generated manifests untracked; AGENTS.md/README.md rewritten; HARNESS-NOTES.md added |

---

## Architecture as built

```
plugins/<name>/
  meta.yaml        ← single hand-authored source (name, version, description, + optional
                     display_name / harnesses / alias_of)
  skills/ commands/ agents/ hooks/ server/   ← unchanged canonical content
bin/adapters/
  lib.sh           ← shared, harness-AGNOSTIC helpers (meta parse via PyYAML, manifest projection)
  claude.sh codex.sh gemini.sh pi.sh         ← one file per harness; all source lib.sh
bin/sync-gemini.sh ← shim -> `gemini.sh build`
Makefile           ← help/build/install[-<h>]/uninstall-<h>/clean/validate; pure dispatch
```

**`meta.yaml` schema** (parsed with real YAML — `journal`'s description is multi-line + unicode):
```yaml
name: reviewers
version: 0.2.2
description: ...            # block scalar |- for ones with colons/unicode
# display_name: bm         # optional; default = titlecased name (wiki_keeper -> "Wiki Keeper")
# harnesses: [claude, codex, pi]   # default = all; bm excludes gemini
# alias_of: bm             # bookmark only
```

**Adapter contract:** `bin/adapters/<h>.sh <build|install|uninstall> [plugin]`.
`build` = pure function of the tree (no `$HOME` writes). `install` = build then place into the
harness root (symlink-preferred). `uninstall` = remove only what it created, guarded by
`test -L` + a `readlink` prefix-check so it never touches repo content.

**ALIAS RULE (verified):** `bookmark` (`alias_of: bm`) installs on **Claude only**. Its content is
relative symlinks into `bm`; Codex *copies* (drops them → empty shell), Gemini has a flat namespace
(name collision), Pi keys skills by name (collision). So codex/gemini/pi adapters skip aliases via
`is_alias`; `claude.sh` keeps it for the `/bookmark:*` command namespace.

Also note: **`reviewers` version drift is structurally fixed** — `meta.yaml` is the only place a
version lives; every manifest is projected from it.

---

## VERIFIED HARNESS FACTS  ← the hard-won part; trust these over REDESIGN-PLAN.md

### Claude — `claude` 2.1.170
- Install = whole-dir **symlink** `plugins/<name>` → `~/.claude/skills/<name>` (live edit-reflect;
  loads as `<name>@skills-dir`). Uninstall = `rm` link + `claude plugin disable <name>@skills-dir`.
- **Sandbox handle = `PREFIX`** → `PREFIX=/tmp/mp bin/adapters/claude.sh install reviewers`, then
  `claude --plugin-dir /tmp/mp/skills/reviewers` (zero-risk loader; never touches real `~/.claude`).
- Hooks fire via `--plugin-dir` in `-p` mode — **verified block**: a no-diff `deep-review` prompt
  yields an empty result (suppressed); a `#42` prompt proceeds.
- `claude plugin validate` warns `wiki_keeper` isn't kebab-case (accepted; only claude.ai sync cares)
  and missing `author`. Both benign.

### Codex — `codex-cli` 0.139.0  (INSTALLED — plan said it wasn't)
- Real commands (NOT `codex marketplace add`):
  - install: `codex plugin marketplace add "<repo>"` then `codex plugin add <name>@agent-marketplace`
  - uninstall: `codex plugin remove <name>@agent-marketplace` then `codex plugin marketplace remove agent-marketplace`
- Catalog `.agents/plugins/marketplace.json` with `source:{source:"local",path:"./plugins/<name>"}`
  is **accepted**; versions flow from `.codex-plugin/plugin.json`.
- **Codex COPIES** the plugin into `$CODEX_HOME/plugins/cache/.../<v>/` — a **snapshot, not a live
  symlink**. Edits need a re-add. (This is why the `bookmark` alias can't work on Codex.)
- **Sandbox handle = `CODEX_HOME`**; seed it with real auth so model calls work:
  `cp ~/.codex/{auth.json,config.toml,version.json,models_cache.json} $CODEX_HOME/`.
  Headless run = `codex exec [-s workspace-write|--dangerously-bypass-approvals-and-sandbox] "..."`.
- **Hook defects found at runtime (Phase 4 work):**
  1. **Codex IGNORES the `UserPromptSubmit` matcher.** `prompt_require_diff` ran on an unrelated
     "say hello" prompt and blocked it (no-diff git repo). As-installed, reviewers blocks *every*
     prompt on Codex in a clean repo. **Fix:** self-gate the script — read the prompt, `exit 0`
     unless it contains `deep-review` (portable; also correct on Claude).
  2. **`wiki_keeper` PreToolUse(`Edit|Write|NotebookEdit`) never fires.** Codex edits via
     `apply_patch` *or* a shell redirect (`printf > file`); neither matches the matcher and
     `tool_input.file_path` is absent. Verified silent-open (a protected `sources/raw/` file was
     modified unblocked). **Fix is hard** — must intercept apply_patch (parse the patch for a path)
     *and* shell writes.
- Verified working: `/reviewers:deep-review-staged` resolves, loads `SKILL.md`, runs; hook
  block+allow both fire.

### Gemini — `gemini` 0.45.3  (INSTALLED — plan said it wasn't)
- Subcommands: `gemini extensions link "<repo>/gemini"` (live symlink of the extension dir) /
  `uninstall agent-marketplace` / `validate "<path>"` / `list`. `link` has **two interactive trust
  prompts** — feed `yes |`, or `--skip-trust` / `GEMINI_CLI_TRUST_WORKSPACE=true` for `-p`.
- **Sandbox handle = `HOME`**; seed `cp ~/.gemini/{oauth_creds,google_accounts,settings,state}.json $HOME/.gemini/`
  and `printf '{"<abs-path>":"TRUST_FOLDER"}' > $HOME/.gemini/trustedFolders.json`.
- **Extension model** (verified from bundled docs at `.../gemini-cli/.../bundle/docs/{extensions,cli,hooks}/`
  + live): an extension is a self-contained dir with `gemini-extension.json` at its root,
  **auto-discovering at the root** (no manifest path-keys):
  - `commands/<sub>/<cmd>.toml` → `/<sub>:<cmd>` (TOML `prompt`/`description`; arg token is
    `{{args}}`, NOT `$ARGUMENTS`; `!{shell}` and `@{file}` injection)
  - `skills/<name>/SKILL.md` → `<name>` (identical to Claude)
  - `agents/*.md` → sub-agents (**PREVIEW**, different definition format)
  - `hooks/hooks.json` (Claude-like; `${extensionPath}`) — **Gemini HAS hooks** (Phase 4)
  - `contextFileName` loads a file FROM the extension dir.
- **`gemini.sh` (Phase 2b, DONE) generates `gemini/` as that extension** and links it:
  `skills/<skill>` (symlinks), `commands/<plugin>/<cmd>.toml` (converted from Claude `.md`,
  `$ARGUMENTS`→`{{args}}`), `agents/<agent>.md` (symlinks), `AGENTS.md` (→ `../AGENTS.md`).
  bm + bookmark skipped.
- **Verified live:** `gemini extensions validate` passes; `/commands list` → 10 commands namespaced
  `/<plugin>:<cmd>` with descriptions; `/skills list` → 11 skills with descriptions; context loads.
  (Live command *execution* hit a transient Google `429 no capacity`; registration proven via the
  model-free `/commands list` / `/skills list` builtins.)
- **GAP → Phase 4:** Claude-format `agents/*.md` do NOT register as Gemini sub-agents (`/agents list`
  shows only built-ins) — sub-agents are preview with a different format. Files are bundled (the
  deep-review skill can still read them) but inert as native sub-agents.

### Pi — `pi` 0.79.0  (INSTALLED)
- **Sandbox handle = `HOME`** (Pi keys discovery off `$HOME`; `PREFIX` is NOT used by `pi.sh`).
  Auth lives in `~/.pi/agent/auth.json` — seed it: `cp ~/.pi/agent/auth.json $HOME/.pi/agent/`.
  Headless run = `HOME=/tmp/pi pi -p "..." --mode text`.
- `pi.sh build` = **no-op** (Pi discovers from the filesystem; no manifest).
- **Skills:** symlink each skill dir → `~/.pi/agent/skills/<skill>` (recursive discovery;
  `SKILL.md` = Agent Skills standard, Claude-compatible; also invocable `/skill:<name>`). **Verified:**
  22 skills installed and discovered across all 4 plugins.
- **Commands → prompt templates** (resolved the plan's open question): symlink command files →
  `~/.pi/agent/prompts/<plugin>-<cmd>.md`. Pi prompt templates are flat, non-recursive, keyed by
  filename (`/name`), and understand `$1`/`$ARGUMENTS` — so Claude command bodies are compatible.
  Plugin-prefixed to avoid collisions (`bm/audit` vs `wiki_keeper/audit` → `/bm-audit`,
  `/wiki_keeper-audit`). **Verified:** `/reviewers-deep-review-staged` expanded and ran (`--no-skills`,
  so unambiguously the prompt template).
- Pi reads `AGENTS.md` + `CLAUDE.md` as context (`--no-context-files` to disable).
- **Bundled docs** (authoritative): `$(brew --prefix)/Cellar/pi-coding-agent/0.79.0/libexec/lib/node_modules/@earendil-works/pi-coding-agent/docs/`
  — esp. `skills.md`, `prompt-templates.md`, `extensions.md`, `packages.md`, `settings.md`.
- **Subagents (done)**: `pi.sh` converts each Claude `agents/*.md` (maps tool names to lowercase Pi
  names: `Read`→`read`, `Glob`→`find`, `Bash`→`bash`) into `~/.pi/agent/agents/`, and installs
  `pi-subagents` (npm v0.28.0) as the runtime consumer. **Verified**: all converted agents are
  discovered by Pi's reference subagent extension (same standard `~/.pi/agent/agents/` dir).

---

## Post-Phase-5 hardening — all done, verified live, committed

- **Codex hook fix**: `reviewers/prompt_require_diff.sh` self-gates on the prompt containing
  `deep-review` (Codex ignores the `UserPromptSubmit` matcher). Verified Codex + Claude.
- **Gemini hooks**: `gemini.sh` translates each plugin's `hooks.json` → `gemini/hooks/hooks.json`
  (`UserPromptSubmit`→`BeforeAgent`, `PreToolUse`→`BeforeTool`, `$CLAUDE_PLUGIN_ROOT`→`${extensionPath}`,
  matcher remap `Edit|Write|NotebookEdit`→`write_file|replace`). reviewers gate + wiki_keeper protect
  both verified blocking.
- **Pi hook bridge**: `bin/adapters/pi/hook-bridge/index.ts` runs the shell hooks via Pi's
  `tool_call`/`input` callbacks (manifest generated by `pi.sh build`, symlinked into
  `~/.pi/agent/extensions/`). Verified block on Pi.
- **Subagents**: register on Gemini (drop the Claude `tools:` string) and Pi (lowercase tool names →
  `~/.pi/agent/agents/`). All converted agents verified discovered.
- **Selective install**: `make install-<h> PLUGIN=a,b` (comma list, whitespace tolerant) — also fixed
  a GNU-make-3.81 `.PHONY`/pattern-rule shadow that had made `make install-<h>` a silent no-op.
- **`make clean`** now removes every harness's generated output (incl. Pi manifest/agents) + `__pycache__`.

## What genuinely remains — Codex-only, documented in HARNESS-NOTES

- **Codex tool-interception** (wiki_keeper protect): investigated and abandoned — Codex's plugin-hook
  trust/loading model is opaque (a fresh plugin's hooks wouldn't fire even with
  `--dangerously-bypass-hook-trust`), and `apply_patch`/shell edits carry no `tool_input.file_path`.
- **Codex subagents**: untested (same opaque model).

Everything else works on every harness it reasonably can. Nothing is required.

---

## Sandbox / verify recipes (copy-paste)

```bash
# CLAUDE — zero-risk loader
PREFIX=/tmp/mp bin/adapters/claude.sh install reviewers
claude --plugin-dir /tmp/mp/skills/reviewers -p "..." --output-format json

# CODEX — sandboxed home, seeded auth
export CODEX_HOME=/tmp/cx; mkdir -p $CODEX_HOME
cp ~/.codex/{auth.json,config.toml,version.json,models_cache.json} $CODEX_HOME/
bin/adapters/codex.sh install                       # marketplace add + plugin add x4
codex plugin list
(cd /some/git/repo && codex exec "deep-review please")   # observe `hook: UserPromptSubmit ...`
bin/adapters/codex.sh uninstall

# GEMINI — sandboxed HOME, seeded auth + trust
rm -rf /tmp/gh; mkdir -p /tmp/gh/.gemini
cp ~/.gemini/{oauth_creds,google_accounts,settings,state}.json /tmp/gh/.gemini/
printf '{"%s":"TRUST_FOLDER"}' "$PWD" > /tmp/gh/.gemini/trustedFolders.json
bin/adapters/gemini.sh build                                  # generates the gemini/ extension
yes | HOME=/tmp/gh gemini extensions link "$PWD/gemini"       # link the generated extension dir
HOME=/tmp/gh gemini extensions list
HOME=/tmp/gh gemini -p "/commands list" --skip-trust          # model-free: confirms commands register
HOME=/tmp/gh gemini extensions uninstall agent-marketplace

# PI — sandboxed HOME, seeded auth (PREFIX does NOT work for Pi)
rm -rf /tmp/pi; mkdir -p /tmp/pi/.pi/agent
cp ~/.pi/agent/auth.json /tmp/pi/.pi/agent/
HOME=/tmp/pi PI_SKIP_SUBAGENTS=1 bin/adapters/pi.sh install
HOME=/tmp/pi pi -p "List your loaded skill names." --mode text
HOME=/tmp/pi pi --no-skills -p "/reviewers-deep-review-staged" --mode text   # prompt template
HOME=/tmp/pi bin/adapters/pi.sh uninstall
```
All four CLIs run real model calls — keep test prompts tiny.

---

## Open questions / risks
- **Silent-open hooks on Codex** (and unverified on Gemini/Pi) — the headline correctness risk;
  only block-verification settles it.
- **Subagents on Codex** — untested (opaque hook/agent model). They DO work on Claude/Gemini/Pi via
  per-harness frontmatter conversion (built + verified).
- **Live command execution on Gemini** — registration + namespacing verified via the model-free
  `/commands list` builtin; a full live model run once hit a transient Google `429 no capacity`
  (server-side, not our extension).
- **Skills-dir installs are repo-path symlinks** — moving the repo breaks installed plugins; re-run
  `make install-<h>` after a move.
- **Generated artifacts are still tracked** — Phase 5 flips them; until then `git status` after a
  build may show manifest changes (expected).
- `bm` is intentionally excluded from Gemini (`harnesses: [claude, codex, pi]`) — documented, not a bug.

## Key files
- `REDESIGN-PLAN.md` — original plan (note: its Codex/Gemini/Pi assumptions are partly wrong; this
  file's VERIFIED HARNESS FACTS supersede them).
- `bin/adapters/*.sh`, `Makefile`, `plugins/*/meta.yaml` — the system.
- `AGENTS.md` — **stale** (old model) until Phase 5.

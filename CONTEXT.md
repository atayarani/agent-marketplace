# CONTEXT — cross-harness adapter refactor (resume handoff)

**Last updated:** 2026-06-10 · **HEAD at handoff:** `b1dba34` on `main` (pushed).
**Companion docs:** `REDESIGN-PLAN.md` (the full plan), `AGENTS.md` (still describes the
*old* model — not yet rewritten; see Phase 5).

This file is a handoff so the refactor can resume from a different machine. The headline
is in **VERIFIED HARNESS FACTS** below: the original plan's assumptions about Codex, Gemini,
and Pi were wrong in several load-bearing ways. Those facts were verified against the real
CLIs and are the most valuable thing here — trust them over the plan.

---

## TL;DR — where we are

Goal: replace hand-authored, per-harness manifests with **one canonical source per plugin**
(`plugins/<name>/meta.yaml`) + **one adapter per harness** (`bin/adapters/<h>.sh`) driven by a
`Makefile`. Generated manifests become gitignored build artifacts (that flip happens in Phase 5).

- **Done & committed (Phases 0–3):** meta.yaml authoring, Claude/Codex/Gemini/Pi adapters,
  shared `lib.sh`, `Makefile`, `sync-gemini.sh` retired to a shim.
- **Remaining:** **Phase 2b** (Gemini adapter redesign — the current one targets a stale Gemini
  model), **Phase 4** (Codex hook fixes + Gemini/Pi hooks + Pi agent wiring), **Phase 5**
  (gitignore-flip + rewrite `AGENTS.md`/`README.md` + add `HARNESS-NOTES.md`).
- **All four CLIs are installed on this dev machine** (the plan wrongly assumed Codex/Gemini
  were absent): Claude 2.1.170, codex-cli 0.139.0, gemini 0.45.2, pi 0.79.0.

---

## Phase status

| Phase | What | Status |
|---|---|---|
| 0 | `plugins/<name>/meta.yaml` ×5 | ✅ done, committed |
| 1 | `claude.sh` + `Makefile` | ✅ done, verified live (hook fires/blocks via `--plugin-dir`) |
| 2 | `codex.sh` + `gemini.sh` (install mechanism) | ✅ done, verified live in sandbox homes |
| 3 | `pi.sh` (skills + commands→prompt-templates) | ✅ done, verified live |
| **2b** | **Gemini adapter redesign for modern Gemini** | ⬜ TODO (current `gemini.sh` largely ignored by Gemini 0.45.2) |
| **4** | **Cross-harness hooks + Pi agent wiring** | ⬜ TODO (2 verified Codex defects; Gemini hooks now feasible; Pi agents unverified) |
| **5** | **Flip generated artifacts to gitignored + rewrite docs** | ⬜ TODO |

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

### Gemini — `gemini` 0.45.2  (INSTALLED — plan said it wasn't)
- Subcommands: `gemini extensions link "<repo>"` (live symlink) / `uninstall agent-marketplace` /
  `validate "<path>"` / `list`. `link` has **two interactive trust prompts** ([Y/n] workspace-trust
  + third-party warning) — feed `yes |` headlessly, or use `--skip-trust` / `GEMINI_CLI_TRUST_WORKSPACE=true` for `-p`.
- **Sandbox handle = `HOME`**; seed `cp ~/.gemini/{oauth_creds,google_accounts,settings,state}.json $HOME/.gemini/`
  and `printf '{"<abs-repo-path>":"TRUST_FOLDER"}' > $HOME/.gemini/trustedFolders.json`.
  Headless run = `gemini -p "..." --skip-trust --approval-mode yolo`.
- **The current `gemini.sh` targets a STALE model → Phase 2b.** Ground truth from
  `gemini extensions new <path> <template>` (templates: `custom-commands exclude-tools hooks
  mcp-server policies skills themes-example`):
  - **Commands are TOML** (`prompt="""...{{args}}...!{shell}"""`), auto-discovered at the extension
    **root** `commands/`. Our `.md` farm via a `"commands"` path-key **does not load as commands.**
  - **Skills are `SKILL.md`** (identical to Claude), auto-discovered at root `skills/`. Portable —
    just need to live at root, not behind a path-key.
  - **Gemini HAS hooks** (plan said it doesn't): `hooks/hooks.json` at root, *Claude-like* structure
    (`{"hooks":{Event:[{"hooks":[{"type":"command","command":"... ${extensionPath} ..."}]}]}}`),
    runs shell. So our reviewers/wiki_keeper hooks are **feasible** on Gemini. Events: `SessionStart`
    confirmed; `PreToolUse`/`UserPromptSubmit` + block protocol = TO-VERIFY.
  - **`subagents` is not a Gemini concept** (no template). Drop it for Gemini.
  - `contextFileName: AGENTS.md` **works** (confirmed at link).
- Verified working today: `link`/`uninstall`/`validate` round-trip; a `/highlights` probe returned
  wiki_keeper-specific output (some content reaches the model via context/skills).

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
- **`pi-subagents`** = real npm pkg (v0.28.0); `pi.sh` runs `pi install npm:pi-subagents` when a
  plugin has `agents/`. **UNVERIFIED:** whether it reads Claude-format `agents/*.md` personas and
  from where → Phase 4. (reviewers deep-review can *plan* the parallel review on Pi, but spawning
  the reviewer subagents depends on this.)

---

## What's left — detailed & actionable

### Phase 2b — Gemini adapter redesign (biggest correctness gap)
Rebuild `gemini.sh` to emit an extension matching Gemini 0.45.2:
- root `skills/<name>/SKILL.md` (portable as-is — symlink or copy),
- root `commands/*.toml` **converted** from Claude `commands/*.md` (`prompt="""<body>"""`; map
  `$ARGUMENTS`/`$1`; `!{cmd}` for shell injection),
- root `hooks/hooks.json` (Gemini event names; `${extensionPath}`),
- keep `contextFileName: AGENTS.md`; drop `subagents`; keep bm/alias skips.
Decide: a real generated extension dir vs a root-level farm. Re-validate with
`gemini extensions validate` + a `-p` command invocation.

### Phase 4 — hooks + Pi agents
- **Codex defect 1 (easy):** self-gate `plugins/reviewers/hooks/scripts/prompt_require_diff.sh` on
  the prompt containing `deep-review` (don't rely on the matcher). Re-verify on Codex *and* Claude.
- **Codex defect 2 (hard):** make `wiki_keeper` protection fire on Codex `apply_patch` + shell writes
  (no `tool_input.file_path`). Investigate Codex hook events/tool-name mapping; block-verify.
- **Gemini hooks:** wire `hooks/hooks.json` (feasible now). Verify `PreToolUse`/`UserPromptSubmit`
  support + `{decision:block}` protocol. Depends on Phase 2b.
- **Pi hooks:** check `extensions.md` — does Pi have a `hooks.json`-style mechanism or only TS-callback
  extensions? Original plan = TS bridge `bin/adapters/pi/hook-bridge/index.ts` mapping
  `PreToolUse→tool_call`, `UserPromptSubmit→input`.
- **Pi agents:** resolve `pi-subagents` config — where/how it reads agent personas; wire `agents/*.md`.
- **Every hook needs BLOCK verification** (silent-open is the headline risk).

### Phase 5 — flip + docs
- `git rm -r --cached` the generated artifacts and add `.gitignore`:
  `plugins/*/.claude-plugin/plugin.json`, `plugins/*/.codex-plugin/plugin.json`,
  `.agents/plugins/marketplace.json`, `.claude-plugin/marketplace.json`, `gemini-extension.json`,
  `gemini/` (do NOT ignore `plugins/*/hooks/hooks.json` — that's hand-authored).
- Rewrite `AGENTS.md` (currently describes the OLD model) + `README.md` (install = `make install-<h>`).
- Add `HARNESS-NOTES.md` from the VERIFIED HARNESS FACTS above + a hook-support matrix + confidence flags.
- **Currently the generated manifests are still tracked** (intentional pre-flip safety net), so a
  fresh checkout already has them; `make build` regenerates byte-identical for Claude.

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
yes | HOME=/tmp/gh gemini extensions link "$PWD"
HOME=/tmp/gh gemini extensions list
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
- **Gemini command format** — `.md` farm doesn't load; needs `.toml` conversion (Phase 2b).
- **Pi `pi-subagents` agent format** — unverified; reviewers subagents on Pi blocked on it.
- **Generated artifacts are still tracked** — Phase 5 flips them; until then `git status` after a
  build may show manifest changes (expected).
- `bm` is intentionally excluded from Gemini (`harnesses: [claude, codex, pi]`) — documented, not a bug.

## Key files
- `REDESIGN-PLAN.md` — original plan (note: its Codex/Gemini/Pi assumptions are partly wrong; this
  file's VERIFIED HARNESS FACTS supersede them).
- `bin/adapters/*.sh`, `Makefile`, `plugins/*/meta.yaml` — the system.
- `AGENTS.md` — **stale** (old model) until Phase 5.

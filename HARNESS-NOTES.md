# HARNESS-NOTES

Per-harness behaviour, install mechanics, and limitations for the four targets.
Unless noted, everything here was **verified against the real CLI** on a dev
machine — Claude Code 2.1.170, codex-cli 0.139.0, gemini 0.45.3, pi 0.79.1.
(The CLIs ship authoritative bundled docs; where a fact came from those, it's
flagged.) Update this file when you change cross-harness behaviour.

## At a glance

| | Install mechanism | Live vs snapshot | Sandbox handle | Skills | Commands | Hooks | Subagents |
|---|---|---|---|---|---|---|---|
| **Claude** | symlink `plugins/<name>` → `~/.claude/skills/<name>` | live | `PREFIX` (+ `--plugin-dir`) | ✅ | ✅ | ✅ full | ✅ native |
| **Codex** | `plugin marketplace add` + `plugin add` | **snapshot copy** | `CODEX_HOME` | ✅ | ✅ | ⚠️ prompt-only | ❓ untested |
| **Gemini** | `extensions link <repo>/gemini` | live | `HOME` | ✅ | ✅ (TOML) | ✅ prompt + write/edit (shell bypasses) | ✅ (adapter drops `tools:`) |
| **Pi** | symlink into `~/.pi/agent/{skills,prompts}` | live | `HOME` | ✅ | ✅ (prompt-templates) | ✅ via TS bridge | ✅ (converted → `agents/`) |

## Claude Code (2.1.170)

- **Install**: whole-dir symlink `plugins/<name>` → `~/.claude/skills/<name>`,
  discovered in place as `<name>@skills-dir` (live edit-reflect; agent/hook
  changes need `/reload-plugins`). Uninstall: remove the symlink + `claude plugin
  disable <name>@skills-dir`.
- **Sandbox**: `PREFIX=/tmp/mp bin/adapters/claude.sh install <plugin>`, then
  `claude --plugin-dir /tmp/mp/skills/<plugin>` — a zero-risk loader that never
  touches real `~/.claude`.
- **Hooks**: full support (`UserPromptSubmit`, `PreToolUse`, …). Verified: the
  reviewers diff-gate blocks a no-diff `deep-review` prompt and allows otherwise.
- `claude plugin validate` warns `wiki_keeper` isn't kebab-case (accepted by
  Claude Code; only the claude.ai marketplace sync cares) and that plugins lack an
  `author`. Both benign.

## Codex (codex-cli 0.139.0)

- **Install** (two steps, not one):
  ```
  codex plugin marketplace add "<repo>"
  codex plugin add <name>@agent-marketplace
  ```
  Uninstall: `codex plugin remove <name>@agent-marketplace` then `codex plugin
  marketplace remove agent-marketplace`. The adapter does all of this.
- **Catalog**: `.agents/plugins/marketplace.json` with
  `source: {source: "local", path: "./plugins/<name>"}`. Accepted; versions flow
  from each `.codex-plugin/plugin.json`.
- **Snapshot, not live**: Codex **copies** the plugin into
  `$CODEX_HOME/plugins/cache/.../<version>/`. Edits to the working tree do **not**
  reflect until you re-install. (This is also why the `bookmark` alias can't work
  on Codex — its symlinked content doesn't survive the copy → empty shell.)
- **Sandbox**: `CODEX_HOME=/tmp/cx`, seeded with auth so model calls work:
  `cp ~/.codex/{auth.json,config.toml,version.json,models_cache.json} $CODEX_HOME/`.
  Headless: `codex exec [-s workspace-write] "…"`.
- **Hooks**:
  - The reviewers prompt hook **works** — but Codex **ignores the
    `UserPromptSubmit` matcher** and runs the hook on every prompt. The script is
    self-gated (checks the prompt for `deep-review` itself), so this is handled;
    write hooks self-gating, never rely on the matcher.
  - Tool-interception (wiki_keeper `PreToolUse`) does **not** fire: Codex edits
    via `apply_patch` (a patch string in `tool_input.command`) **or** a shell
    redirect, neither carrying `tool_input.file_path`. **Shell writes are
    fundamentally unprotectable via tool hooks.** Documented limitation.
  - Investigated the `apply_patch` path empirically (a throwaway probe plugin with
    `PreToolUse` matchers for `apply_patch`/`.*`): could **not** get Codex to fire a
    fresh plugin's hooks in a sandbox — not even `UserPromptSubmit` — even with
    `--dangerously-bypass-hook-trust`. Codex's plugin-hook trust/loading model is
    opaque enough that reliable tool-interception isn't achievable here. **Not pursued.**

## Gemini CLI (0.45.3)

- **Install**: `gemini extensions link "<repo>/gemini"` (symlinks the generated
  extension; live). Uninstall: `gemini extensions uninstall agent-marketplace`.
  `gemini extensions validate "<repo>/gemini"` checks the extension.
- **Extension model** (from the CLI's bundled docs + verified): a self-contained
  dir with `gemini-extension.json` at its root, auto-discovering at the root —
  `commands/<sub>/<cmd>.toml` → `/<sub>:<cmd>`, `skills/<name>/SKILL.md`,
  `agents/*.md` (preview), `hooks/hooks.json`, and `contextFileName` loaded from
  the extension dir. The adapter generates all of this under `gemini/` from
  canonical content: skills/agents are symlinked, commands are **converted** from
  Claude `.md` to TOML (`$ARGUMENTS` → `{{args}}`), `AGENTS.md` is the context file.
- **Trust prompts**: `link` prompts twice (workspace trust + third-party warning).
  Headless: feed `yes |`, or `--skip-trust` / `GEMINI_CLI_TRUST_WORKSPACE=true`.
- **Sandbox**: `HOME=/tmp/gh`; seed
  `cp ~/.gemini/{oauth_creds,google_accounts,settings,state}.json $HOME/.gemini/`
  and `printf '{"<abs-path>":"TRUST_FOLDER"}' > $HOME/.gemini/trustedFolders.json`.
- **Hooks**: the adapter translates `hooks.json` to Gemini events
  (`UserPromptSubmit`→`BeforeAgent`, `PreToolUse`→`BeforeTool`;
  `$CLAUDE_PLUGIN_ROOT`→`${extensionPath}`). Verified: the reviewers `BeforeAgent`
  hook blocks/allows correctly (Claude's `{decision:"block"}` is honored).
  Tool-interception (`BeforeTool`) **works**: the adapter remaps tool-name
  matchers (`Edit|Write|NotebookEdit` → `write_file|replace`) and Gemini's
  `write_file`/`replace` use `tool_input.file_path` — the same field as Claude —
  so the protect scripts (which also recognize `write_file`/`replace`) fire
  unchanged. **Verified**: `write_file`/`replace` to `sources/raw/` is blocked
  ("Tool execution blocked: sources/raw/ is immutable…") and the new-file-capture
  nuance holds. Remaining gap: a `run_shell_command` redirect (shell write)
  isn't matched and bypasses it — same as Codex.
- **Verified registration** of commands/skills via the model-free `/commands list`
  and `/skills list` builtins. (Live command *execution* was blocked once by a
  transient Google `429 no capacity` — a server condition, not our extension.)

## Pi (0.79.1)

- **Install**: `pi.sh build` is a no-op (Pi discovers from the filesystem). Install
  symlinks each skill into `~/.pi/agent/skills/<skill>` (recursive discovery;
  `SKILL.md` = Agent Skills standard) and each command into
  `~/.pi/agent/prompts/<plugin>-<cmd>.md` (Pi prompt templates: flat, non-recursive,
  `/name`; plugin-prefixed to avoid `bm/audit` vs `wiki_keeper/audit` collisions;
  Claude `$ARGUMENTS` bodies are compatible). Skills are also invocable as `/skill:<name>`.
- **Sandbox**: `HOME` (Pi keys discovery off `$HOME`; `PREFIX` is unused here).
  Seed `cp ~/.pi/agent/auth.json $HOME/.pi/agent/`. Headless: `pi -p "…" --mode text`.
- Pi reads `AGENTS.md` + `CLAUDE.md` as context (`--no-context-files` to disable).
- **Hooks**: Pi has **no shell `hooks.json`** — only TS-callback extensions. The
  repo ships a generic **bridge** (`bin/adapters/pi/hook-bridge/index.ts`) that runs
  our Claude-format shell hook scripts unchanged: `pi.on("tool_call")` → PreToolUse
  (maps `write`/`edit` → `Write`/`Edit`; blocks via `{block:true}`) and
  `pi.on("input")` → UserPromptSubmit (blocks via `{action:"handled"}`;
  `before_agent_start` can only inject, not block, so the bridge uses `input`).
  `pi.sh` generates a manifest of hook scripts (absolute paths) and symlinks the
  bridge into `~/.pi/agent/extensions/hook-bridge/` (auto-discovered). **Verified
  live**: the reviewers gate blocks `deep-review` with no diff (allows a PR number /
  non-deep-review prompt), and wiki_keeper blocks a write to `sources/raw/`. A
  shell-redirect write still bypasses it (no `bash` matcher), as on the others.
- **Subagents**: Pi subagents are `agents/*.md` discovered from `~/.pi/agent/agents/`
  (`name`/`description`/`tools`/`model` + body), run as isolated sub-processes by a
  subagent extension. `pi.sh` **converts** each Claude agent (maps tool names to
  lowercase Pi names: `Read`→`read`, `Grep`→`grep`, `Glob`→`find`, `Bash`→`bash`)
  and symlinks it into `~/.pi/agent/agents/`, and runs `pi install npm:pi-subagents`
  (the consumer) when a plugin has `agents/`. **Verified**: all converted agents are
  discovered by Pi's reference subagent extension (which reads the same standard dir).
- Bundled docs: `<brew cellar>/pi-coding-agent/<v>/…/pi-coding-agent/docs/`
  (`skills.md`, `prompt-templates.md`, `extensions.md`, `examples/extensions/`).

## Cross-harness limitations (known, by design or deferred)

1. **Tool-interception hooks** (wiki_keeper `protect_*`): work on **Claude**,
   **Gemini** (the adapter remaps the matcher to `write_file|replace`, which share
   Claude's `tool_input.file_path`), and **Pi** (via the TS hook-bridge `tool_call`
   handler) — all verified block. **Inert on Codex** —
   edits arrive as `apply_patch` (a patch string in `tool_input.command`) or a
   shell redirect, neither carrying `file_path`. **Shell writes** (`run_shell_command`
   on Gemini, shell on Codex) bypass tool hooks on every harness — a tool-name
   matcher can't catch an arbitrary `>` redirect. Covering Codex would need
   patch-string parsing (apply_patch) + is impossible for its shell path.
2. **Pi hooks** run via the bundled TS bridge (`bin/adapters/pi/hook-bridge`): Pi has
   no native shell-hook mechanism, but the bridge maps its `tool_call`/`input` events
   onto the Claude protocol and runs the scripts (verified). Shell-redirect writes
   bypass it, as elsewhere.
3. **Subagent definitions** work on **Claude** (native), **Gemini**, and **Pi** —
   each via a small per-harness conversion of the same Claude `agents/*.md`:
   - Gemini: drop the Claude `tools:` string (Gemini wants a YAML tool-name array;
     the invalid field blocked registration). Converted agents register and expose
     as subagent tools (verified — all 8); they inherit the parent session's tools.
   - Pi: map tool names to lowercase Pi names and place under `~/.pi/agent/agents/`;
     verified discovered by Pi's reference subagent extension (consumer: pi-subagents).
   **Codex**: untested (its hook/agent model proved opaque — see above). So
   `reviewers` can spawn its personas on Claude, Gemini, and Pi; Codex is the lone gap.
4. **`bm` is excluded from Gemini** (`harnesses: [claude, codex, pi]`) — its
   `server/` daemon can't resolve through Gemini's flat namespace and `bm/audit`
   would collide with `wiki_keeper/audit`.
5. **`bookmark` (alias) installs on Claude only.** Codex copy drops its symlinks;
   Gemini and Pi collide on the shared skill names. Its value is the Claude
   `/bookmark:*` command namespace.

## Confidence

Install/registration, the reviewers prompt hook (Claude/Codex/Gemini/Pi), the Gemini
`BeforeTool` wiki_keeper block, and the Pi hook-bridge (`tool_call` + `input`) are all
**verified live** on the relevant harnesses (in sandboxed homes; real configs untouched). The limitations above are verified negatives, not
guesses. The only doc-derived (not behaviourally exercised) facts left are the Pi
`pi-subagents` definition format and Codex subagent support.

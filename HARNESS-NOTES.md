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
| **Gemini** | `extensions link <repo>/gemini` | live | `HOME` | ✅ | ✅ (TOML) | ✅ prompt + write/edit (shell bypasses) | ❌ preview/diff format |
| **Pi** | symlink into `~/.pi/agent/{skills,prompts}` | live | `HOME` | ✅ | ✅ (prompt-templates) | ❌ needs TS bridge | ⚠️ pi-subagents (unverified) |

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
- **Hooks**: Pi has **no shell `hooks.json`** — only TS-callback extensions
  (`pi.on("tool_call", …) → {block:true,reason}` ≈ PreToolUse;
  `pi.on("before_agent_start", …)` with `event.prompt` ≈ UserPromptSubmit). Running
  our shell hook scripts requires a TS bridge extension
  (`bin/adapters/pi/hook-bridge/index.ts`) — **not yet built**.
- **Subagents**: `pi.sh` runs `pi install npm:pi-subagents` (real package) when a
  plugin has `agents/`, but whether pi-subagents consumes Claude-format
  `agents/*.md` is **unverified**.
- Bundled docs: `<brew cellar>/pi-coding-agent/<v>/…/pi-coding-agent/docs/`
  (`skills.md`, `prompt-templates.md`, `extensions.md`, `examples/extensions/`).

## Cross-harness limitations (known, by design or deferred)

1. **Tool-interception hooks** (wiki_keeper `protect_*`): work on **Claude** and
   **Gemini** (the Gemini adapter remaps the matcher to `write_file|replace`, which
   share Claude's `tool_input.file_path`; verified block). **Inert on Codex** —
   edits arrive as `apply_patch` (a patch string in `tool_input.command`) or a
   shell redirect, neither carrying `file_path`. **Shell writes** (`run_shell_command`
   on Gemini, shell on Codex) bypass tool hooks on every harness — a tool-name
   matcher can't catch an arbitrary `>` redirect. Covering Codex would need
   patch-string parsing (apply_patch) + is impossible for its shell path.
2. **Pi hooks** need a TS bridge extension (deferred). No shell-hook mechanism.
3. **Subagent definitions are not portable.** Native only on Claude. Gemini
   sub-agents are a preview feature with a different definition format (Claude
   `agents/*.md` do not register — verified). Pi uses the `pi-subagents` package
   (format unverified). Codex: untested. This is why `reviewers` can *plan* a
   parallel review off-Claude but can't spawn the reviewer personas there.
4. **`bm` is excluded from Gemini** (`harnesses: [claude, codex, pi]`) — its
   `server/` daemon can't resolve through Gemini's flat namespace and `bm/audit`
   would collide with `wiki_keeper/audit`.
5. **`bookmark` (alias) installs on Claude only.** Codex copy drops its symlinks;
   Gemini and Pi collide on the shared skill names. Its value is the Claude
   `/bookmark:*` command namespace.

## Confidence

Install/registration, the reviewers prompt hook, and the Gemini `BeforeTool`
wiki_keeper block are all **verified live** on the relevant harnesses (in sandboxed
homes; real configs untouched). The limitations above are verified negatives, not
guesses. The only doc-derived (not behaviourally exercised) facts left are the Pi
`pi-subagents` definition format and Codex subagent support.

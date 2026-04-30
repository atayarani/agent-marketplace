# AGENTS.md

This is `agent-marketplace`, a personal toolkit repo that ships sub-plugins to
Claude Code, Codex, and Gemini CLI. Each sub-plugin lives under
`plugins/<name>/` and carries its own per-ecosystem manifests. The repo root
holds the marketplace catalogs that point at them.

## Layout

    plugins/<name>/
      .claude-plugin/plugin.json       Claude plugin manifest.
      .codex-plugin/plugin.json        Codex plugin manifest.
      skills/                          SKILL.md content.
      agents/                          Subagent definitions in markdown.
      commands/                        Slash command bodies in markdown.
      hooks/hooks.json                 Hook config (Claude format).
      hooks/scripts/                   Hook logic as shell scripts.

    .claude-plugin/marketplace.json    Claude marketplace catalog.
    .agents/plugins/marketplace.json   Codex marketplace catalog.
    gemini-extension.json              Gemini extension manifest (aggregator).

## How it works

Claude Code and Codex both support sub-plugins natively. The top-level
marketplace catalogs index each `plugins/<name>/` entry by path; the
sub-plugin's own manifest declares its name, version, and content.

Gemini's extension model is one extension per repo, so `gemini-extension.json`
at the root aggregates content from sub-plugins by pointing its `commands`,
`skills`, and `subagents` paths into `plugins/<name>/`. This means Gemini sees
all sub-plugin content under one extension namespace — no per-sub-plugin
namespacing on Gemini, but every sub-plugin's content is reachable.

Each sub-plugin owns its hooks. Hook event names and payload shapes differ
per ecosystem; check the relevant docs before assuming an event fires in all
three.

## Conventions

Directory names use snake_case. Manifest identifiers follow whatever case each
ecosystem requires.

Shell scripts use bash. Exit 0 means allow. Non-zero means block. Stderr
surfaces to the agent.

Skills follow the SKILL.md spec: YAML frontmatter with `name` and
`description`, markdown body underneath. Keep descriptions tight and
trigger-focused. The description is what the agent reads to decide whether to
load the skill.

Sub-plugin content stays portable. No hardcoded paths, no machine-specific
assumptions, no embedded secrets.

## Adding to an existing sub-plugin

**Skill.** Create `plugins/<name>/skills/<skill>/SKILL.md`. Auto-discovered.

**Slash command.** Write `plugins/<name>/commands/<command>.md`.
Auto-discovered. Claude namespaces as `/<plugin-name>:<command>`. Codex
namespaces as `/<plugin-name>:<command>` (verify against current Codex docs).
Gemini uses `/<command>` because all sub-plugin commands aggregate under the
single Gemini extension.

**Subagent.** Write `plugins/<name>/agents/<agent>.md`. Auto-discovered.

**Hook.** Add the script at `plugins/<name>/hooks/scripts/<purpose>.sh` and
register it in `plugins/<name>/hooks/hooks.json`. Hook configs differ by
ecosystem; the current hooks here use Claude's format.

## Adding a new sub-plugin

1. Create `plugins/<new-plugin>/` with `.claude-plugin/plugin.json` and
   `.codex-plugin/plugin.json`, each declaring `name`, `version`, and
   `description`.
2. Add an entry to `.claude-plugin/marketplace.json` and
   `.agents/plugins/marketplace.json` pointing at the new sub-plugin path.
3. If the new sub-plugin should be reachable from Gemini, extend
   `gemini-extension.json` — but Gemini accepts only single string paths for
   `commands` / `skills` / `subagents`, so multi-sub-plugin Gemini support
   needs a deliberate choice (aggregate via symlinks, or pick one sub-plugin
   to be Gemini's entry point).

## Cross-tool gotchas

Claude Code supports LSP servers as a plugin primitive (`.lsp.json`, requires
Claude Code 2.0.74+). Codex and Gemini do not expose LSP through their plugin
or extension manifests. LSP content stays under the relevant sub-plugin's
`.claude-plugin/` and we accept the asymmetry.

Gemini supports themes. Claude Code and Codex do not. Same deal in reverse.

Gemini lacks native sub-plugins. The aggregator pattern in
`gemini-extension.json` collapses the namespace; commands from different
sub-plugins cannot collide.

`AGENTS.md` is the source of truth for project context. `CLAUDE.md` and
`GEMINI.md` are pointer files that reference this one. Edit `AGENTS.md`, not
the pointers.

## Working in this repo

When adding new content, update the sub-plugin and any affected top-level
manifest in the same commit. Marketplace drift is the most common bug here.

Run `claude plugin validate .` before pushing. Codex and Gemini validators
get wired into CI later.

No secrets in any file. Content runs on machines we do not control.

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
    gemini-extension.json              Gemini extension manifest.
    gemini/                            Generated symlink farm Gemini reads from.
    bin/sync-gemini.sh                 Rebuilds gemini/ from plugins/<name>/.

## How it works

Claude Code and Codex both support sub-plugins natively. The top-level
marketplace catalogs index each `plugins/<name>/` entry by path; the
sub-plugin's own manifest declares its name, version, and content.

Gemini's extension model is one extension per repo, and each of its
`commands` / `skills` / `subagents` keys accepts only a single string path.
We collapse all sub-plugin content into one path per kind via a generated
symlink farm under `gemini/`. `gemini-extension.json` points at that farm;
`bin/sync-gemini.sh` rebuilds it from `plugins/<name>/`. Run the script
after adding, removing, or renaming any sub-plugin command, skill, or
subagent. Names must be unique across sub-plugins — the script aborts on
collision rather than picking a winner.

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

**Skill.** Create `plugins/<name>/skills/<skill>/SKILL.md`. Auto-discovered
on Claude Code and Codex; run `bin/sync-gemini.sh` to expose it on Gemini.

**Slash command.** Write `plugins/<name>/commands/<command>.md`.
Auto-discovered on Claude Code and Codex; run `bin/sync-gemini.sh` to
expose it on Gemini. Claude namespaces as `/<plugin-name>:<command>`. Codex
namespaces as `/<plugin-name>:<command>` (verify against current Codex docs).
Gemini uses `/<command>` because all sub-plugin commands aggregate under the
single Gemini extension.

**Subagent.** Write `plugins/<name>/agents/<agent>.md`. Auto-discovered
on Claude Code and Codex; run `bin/sync-gemini.sh` to expose it on Gemini.

**Hook.** Add the script at `plugins/<name>/hooks/scripts/<purpose>.sh` and
register it in `plugins/<name>/hooks/hooks.json`. Hook configs differ by
ecosystem; the current hooks here use Claude's format.

## Adding a new sub-plugin

1. Create `plugins/<new-plugin>/` with `.claude-plugin/plugin.json` and
   `.codex-plugin/plugin.json`, each declaring `name`, `version`, and
   `description`.
2. Add an entry to `.claude-plugin/marketplace.json` and
   `.agents/plugins/marketplace.json` pointing at the new sub-plugin path.
3. Run `bin/sync-gemini.sh` to refresh `gemini/`. The new sub-plugin's
   commands, skills, and subagents become reachable from Gemini through
   the existing extension manifest — no manifest edit needed unless you
   are changing the layout itself.

## Cross-tool gotchas

Claude Code supports LSP servers as a plugin primitive (`.lsp.json`, requires
Claude Code 2.0.74+). Codex and Gemini do not expose LSP through their plugin
or extension manifests. LSP content stays under the relevant sub-plugin's
`.claude-plugin/` and we accept the asymmetry.

Gemini supports themes. Claude Code and Codex do not. Same deal in reverse.

Gemini lacks native sub-plugins. The `gemini/` symlink farm collapses the
namespace into one path per kind; commands, skills, and subagents from
different sub-plugins must have globally unique names.

`AGENTS.md` is the source of truth for project context. `CLAUDE.md` and
`GEMINI.md` are pointer files that reference this one. Edit `AGENTS.md`, not
the pointers.

## Working in this repo

When adding new content, update the sub-plugin and any affected top-level
manifest in the same commit. Marketplace drift is the most common bug here.

Run `claude plugin validate .` before pushing. Codex and Gemini validators
get wired into CI later.

No secrets in any file. Content runs on machines we do not control.

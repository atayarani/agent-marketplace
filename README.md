# agent-marketplace

A personal toolkit shipping sub-plugins to [Claude Code](https://docs.claude.com/en/docs/claude-code), [Codex](https://github.com/openai/codex), and [Gemini CLI](https://github.com/google-gemini/gemini-cli).

Each sub-plugin lives under `plugins/<name>/` and ships its own per-ecosystem manifests, skills, slash commands, subagents, and hooks. The repo root holds the marketplace catalogs that point at them.

## Sub-plugins

| Plugin | What it does |
|---|---|
| [`reviewers`](plugins/reviewers/) | Parallel PR review with a selectable team of reviewers (security, performance, style). |
| [`wiki_keeper`](plugins/wiki_keeper/) | Discipline for LLM-maintained personal wikis. Ingest sources, query the wiki, file durable insights back, audit for drift. |

## Install

### Claude Code

```bash
/plugin marketplace add atayarani/agent-marketplace
/plugin install reviewers@agent-marketplace
/plugin install wiki_keeper@agent-marketplace
```

### Codex

The Codex marketplace catalog is at `.agents/plugins/marketplace.json`. Follow the Codex docs for adding a marketplace by GitHub source.

### Gemini CLI

Gemini's extension model is one-extension-per-repo, so `gemini-extension.json` aggregates content from a single sub-plugin (currently `reviewers`). To use a different sub-plugin under Gemini, edit the extension manifest's `commands` / `skills` / `subagents` paths or aggregate via symlinks. See [`AGENTS.md`](AGENTS.md) for the rationale.

## Layout

```
plugins/<name>/
  .claude-plugin/plugin.json     Claude plugin manifest
  .codex-plugin/plugin.json      Codex plugin manifest
  skills/                        SKILL.md content
  agents/                        Subagent definitions
  commands/                      Slash command bodies
  hooks/hooks.json               Hook config (Claude format)
  hooks/scripts/                 Hook logic as shell scripts

.claude-plugin/marketplace.json  Claude marketplace catalog
.agents/plugins/marketplace.json Codex marketplace catalog
gemini-extension.json            Gemini extension manifest (aggregator)
AGENTS.md                        Project context — source of truth
CLAUDE.md, GEMINI.md             One-line pointers to AGENTS.md
```

## Adding content

See [`AGENTS.md`](AGENTS.md) for conventions and the full add-a-skill / add-a-command / add-a-subagent / add-a-hook / add-a-sub-plugin recipes.

Before pushing:

```bash
claude plugin validate .
```

## License

MIT — see [`LICENSE`](LICENSE).

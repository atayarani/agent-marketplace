# agent-marketplace

A personal toolkit that ships sub-plugins to four coding-agent harnesses —
[Claude Code](https://docs.claude.com/en/docs/claude-code),
[Codex](https://github.com/openai/codex),
[Gemini CLI](https://github.com/google-gemini/gemini-cli), and
[Pi](https://github.com/badlogic/pi-mono).

Each sub-plugin is authored **once** as paradigm-agnostic content under
`plugins/<name>/`. One adapter per harness (`bin/adapters/<harness>.sh`)
generates that harness's manifests from a single source (`meta.yaml`) and
installs them. See [AGENTS.md](AGENTS.md) for how it works and
[HARNESS-NOTES.md](HARNESS-NOTES.md) for per-harness behaviour.

## Sub-plugins

| Plugin | What it does | Harnesses |
|---|---|---|
| [`reviewers`](plugins/reviewers/) | Parallel PR review with a selectable team of reviewers (security, performance, style, ansible). | all |
| [`wiki_keeper`](plugins/wiki_keeper/) | Discipline for LLM-maintained personal wikis: ingest sources, query, file durable insights back, audit for drift, enrich book/movie lists. | all |
| [`journal`](plugins/journal/) | BuJo-style journaling across daily / weekly / monthly cadences with reflection rituals. | all |
| [`bm`](plugins/bm/) | Raindrop-style bookmark manager: capture, enrich, and file URLs into a plain-text vault. | claude, codex, pi |
| [`bookmark`](plugins/bookmark/) | Long-form alias of `bm` (so `/bookmark:*` works alongside `/bm:*`). | claude only |

This table is the human catalog. The machine catalogs are generated build
artifacts (not committed).

## Install

Everything goes through the `Makefile`, which dispatches to the per-harness
adapter. Install one harness or all of them:

```bash
make install-claude     # symlinks into ~/.claude/skills/ (live edit-reflect)
make install-codex      # codex plugin marketplace add + plugin add (snapshot copy)
make install-gemini     # gemini extensions link (prompts twice to trust)
make install-pi         # symlinks skills + prompt-templates into ~/.pi/agent/
make install            # every harness that has an adapter
```

Install (or uninstall) only some plugins with `PLUGIN=` — a single name or a
comma-separated list (default is all):

```bash
make install-claude PLUGIN=reviewers
make install-pi     PLUGIN=reviewers,wiki_keeper
make uninstall-codex PLUGIN=journal
```

`PLUGIN=` works for Claude, Codex, and Pi (each installs plugins independently).
**Gemini ignores it** — it's one extension per repo, so it's all-or-nothing; control
which plugins exist on Gemini via each plugin's `meta.yaml` `harnesses:` field instead.

Other targets: `make build` (regenerate all manifests, no install), `make
uninstall-<harness>`, `make validate`, `make clean`, `make help`.

Sandboxed dry run (Claude): `PREFIX=/tmp/mp make install-claude`, then
`claude --plugin-dir /tmp/mp/skills/<plugin>`.

**Per-harness notes that will bite you otherwise** (full detail in
[HARNESS-NOTES.md](HARNESS-NOTES.md)):

- **Codex** copies plugins into its cache at install — edits need a re-install,
  unlike Claude/Gemini/Pi which symlink live.
- **Gemini** `link` prompts twice for trust on first install.
- **`bm`** is intentionally excluded from Gemini; **`bookmark`** installs on
  Claude only.
- Hooks: the reviewers diff-gate works on Claude, Codex, and Gemini. Some
  tool-interception and subagent features are Claude-only — see HARNESS-NOTES.

## Layout

```
plugins/<name>/meta.yaml + skills/ commands/ agents/ hooks/    canonical content
bin/adapters/<harness>.sh                                       one adapter per harness
Makefile                                                        build / install / …
AGENTS.md                                                       project context (source of truth)
HARNESS-NOTES.md                                                per-harness behaviour + limits
```

Generated manifests (`.claude-plugin/`, `.codex-plugin/`, `.agents/…`,
`gemini-extension.json`, `gemini/`) are git-ignored build artifacts — run `make
build`, never edit them.

## Adding content

See [AGENTS.md](AGENTS.md) for the add-a-skill / command / subagent / hook /
sub-plugin recipes. In short: author content + `meta.yaml`, then `make build`.

## License

MIT — see [`LICENSE`](LICENSE).

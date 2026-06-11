# AGENTS.md

This is `agent-marketplace`, a personal toolkit that ships sub-plugins to four
coding-agent harnesses — **Claude Code, Codex, Gemini CLI, and Pi**. Each
sub-plugin is authored **once** as paradigm-agnostic content under
`plugins/<name>/`; one **adapter per harness** (`bin/adapters/<harness>.sh`)
projects that content into the manifest/extension shape each harness wants and
installs it. A `Makefile` drives the adapters.

The single source for a plugin's identity is `plugins/<name>/meta.yaml`. Every
generated manifest is projected from it, so the per-harness version/drift bugs
this repo used to have are now structurally impossible.

> Per-harness behaviour, install mechanics, the hook-support matrix, and known
> limitations live in **[HARNESS-NOTES.md](HARNESS-NOTES.md)** — read it before
> assuming a feature behaves the same on every harness. It records facts verified
> against the real CLIs.

## Layout

```
plugins/<name>/
  meta.yaml            Single hand-authored source: name, version, description,
                       + optional display_name / harnesses / alias_of.
  skills/<s>/SKILL.md  Skills (Agent Skills standard; portable as-is).
  commands/<c>.md      Slash-command bodies (Claude format; adapters convert).
  agents/<a>.md        Subagent definitions (Claude format).
  hooks/hooks.json     Hook config (Claude format) — canonical intermediate.
  hooks/scripts/       Hook logic as shell scripts.
  server/              (bm only) bookmarklet daemon.

bin/adapters/
  lib.sh               Shared, harness-AGNOSTIC helpers (meta.yaml parse, manifest projection).
  claude.sh codex.sh gemini.sh pi.sh   One file per harness — the ONLY place
                       per-harness logic lives.
bin/sync-gemini.sh     Back-compat shim -> `gemini.sh build`.
Makefile               help / build / install[-<h>] / uninstall-<h> / clean / validate.
```

**Generated, git-ignored build artifacts** (never edit by hand — run `make build`):
`plugins/*/.claude-plugin/plugin.json`, `plugins/*/.codex-plugin/plugin.json`,
`.agents/plugins/marketplace.json`, `gemini-extension.json`, and the whole
`gemini/` extension directory.

## How it works

`meta.yaml` + canonical content is the input. Each adapter has the same contract:

    bin/adapters/<harness>.sh <build|install|uninstall> [plugin]

- **build** — pure function of the working tree → writes that harness's
  manifest projection(s). No `$HOME` writes.
- **install** — `build`, then place content into the harness's install root via
  its native mechanism (symlink-preferred where the harness supports it).
- **uninstall** — remove only what it created (guarded by `test -L` + a
  `readlink` prefix check). Never touches `plugins/`.

`make install-<harness>` is the entry point; `make install` does every harness
that has an adapter. The Makefile contains **no** per-harness logic — it only
dispatches.

The adapters parse `meta.yaml` with a real YAML parser (PyYAML via `python3`),
not `grep|cut` — `journal`'s description is multi-line with colons and unicode.

### `meta.yaml`

```yaml
name: reviewers
version: 0.2.2
description: Parallel PR review with a selectable team of reviewers.
# display_name: bm                 # Codex/Gemini label; default = titlecased name
# harnesses: [claude, codex, pi]   # default = all four; bm omits gemini
# alias_of: bm                     # this plugin's content is symlinks into another
```

- `harnesses` restricts which harnesses install a plugin. `bm` sets
  `[claude, codex, pi]` (its `server/` daemon can't resolve through Gemini's
  flat namespace, and `bm/audit` would collide with `wiki_keeper/audit` there).
- `alias_of` marks a plugin whose `skills/commands/agents` are symlinks into
  another (`bookmark` → `bm`). **Alias plugins install on Claude only** — Codex
  copies (and drops the symlinks), Gemini and Pi key by name (and collide). The
  alias exists for Claude's `/bookmark:*` command namespace. Adapters skip
  aliases via `is_alias`; `claude.sh` keeps them.

## Adding to an existing sub-plugin

Author canonical content, then `make build` (or `make install-<h>`). No
hand-editing of any generated manifest, ever.

- **Skill** — `plugins/<name>/skills/<skill>/SKILL.md`. Portable to every harness.
- **Slash command** — `plugins/<name>/commands/<command>.md`. Claude/Codex use it
  as-is; the Gemini adapter converts it to TOML; the Pi adapter exposes it as a
  prompt template. Use `$ARGUMENTS` for args (mapped per harness).
- **Subagent** — `plugins/<name>/agents/<agent>.md`. **Native only on Claude** —
  agent *definitions* are not portable (see HARNESS-NOTES).
- **Hook** — script at `plugins/<name>/hooks/scripts/<purpose>.sh`, registered in
  `plugins/<name>/hooks/hooks.json` (Claude event names + payload). Make the
  script **self-gating** (check its own trigger condition) rather than relying on
  the `matcher` — Codex ignores `UserPromptSubmit` matchers. The adapters
  translate `hooks.json` per harness; tool-interception hooks have real
  cross-harness limits (HARNESS-NOTES).

## Adding a new sub-plugin

1. `mkdir plugins/<new>/` and write `meta.yaml` + content (`skills/`, etc.).
2. Set `harnesses` / `alias_of` if needed.
3. `make build` (regenerates every harness's manifests) and `make install-<h>`.

There are no catalogs to hand-edit — the adapters regenerate them. The
human-facing catalog is the plugin table in [README.md](README.md).

## Conventions

- Directory names use snake_case. Manifest identifiers follow each harness's casing.
- Shell scripts use bash; exit 0 = allow, non-zero = block, stderr surfaces to the agent.
- Skills follow the SKILL.md spec (YAML frontmatter `name` + `description`, body
  under). Keep descriptions tight and trigger-focused.
- Content stays portable: no hardcoded paths, no machine-specific assumptions, no
  secrets. Content runs on machines we don't control.
- `AGENTS.md` is the source of truth for project context; `CLAUDE.md` / `GEMINI.md`
  are pointer files — edit this one.

## Working in this repo

- Edit `meta.yaml` + canonical content. **Never** edit a generated manifest; it
  will be overwritten by `make build` and isn't tracked.
- Run `make validate` (builds, then `claude plugin validate .`) before pushing.
- When changing cross-harness behaviour, verify against the real CLI and update
  HARNESS-NOTES. Marketplace/manifest drift used to be the most common bug here;
  the single-source design removes it — keep it that way.

#!/usr/bin/env bash
# Gemini adapter — one of bin/adapters/<harness>.sh.
#
#   bin/adapters/gemini.sh <build|install|uninstall> [plugin]
#
#   build      Rebuild the gemini/{commands,skills,subagents}/ symlink farm and
#              write gemini-extension.json. Pure function of the working tree.
#   install    build, then `gemini extensions link "$repo_root"` (dev symlink).
#   uninstall  `gemini extensions uninstall agent-marketplace`.
#
# Gemini has ONE extension per repo and a single flat namespace per kind, so all
# remaining plugins' commands/skills/subagents collapse into one path per kind.
# Two plugins are excluded by design (REDESIGN-PLAN §1):
#   - bm:        harnesses excludes gemini (server/ daemon can't resolve through
#                the farm; bm/audit would collide with wiki_keeper/audit).
#   - bookmark:  alias_of is set (its content == bm; would collide name-for-name).
# This is the fix for the frozen, unrebuildable farm: the old script aborted on
# the bm collisions; here the skip is deterministic. Genuine clashes between the
# REMAINING plugins still abort (a real authoring bug, not an alias).
#
# DOC-VERIFIED ONLY for install/uninstall: `gemini` is not installed here. The
# farm rebuild + manifest generation (build) ARE locally verifiable.

set -euo pipefail

HARNESS=gemini
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
source "$(dirname "$0")/lib.sh"
shopt -s nullglob

link_one() {
  local src=$1 dest_kind=$2          # src is repo-relative, e.g. plugins/x/commands/y.md
  local name=${src##*/}
  local dest="gemini/$dest_kind/$name"
  if [[ -e $dest || -L $dest ]]; then
    echo "gemini: collision in gemini/$dest_kind/: $name" >&2
    echo "        two non-alias plugins claim the same name — rename one." >&2
    exit 1
  fi
  ln -s "../../$src" "$dest"
}

build_farm() {
  cd "$repo_root"
  local kind
  for kind in commands skills subagents; do
    rm -rf "gemini/$kind"; mkdir -p "gemini/$kind"
  done

  local count=0 plugin_dir name meta f d
  local -a skipped=()
  for plugin_dir in plugins/*/; do
    name=$(basename "$plugin_dir")
    meta="${plugin_dir}meta.yaml"
    [ -f "$meta" ] || { echo "gemini: skip $name — no meta.yaml" >&2; continue; }
    if is_alias "$meta"; then skipped+=("$name(alias)"); continue; fi
    if ! installs_on "$meta" "$HARNESS"; then skipped+=("$name(excluded)"); continue; fi

    count=$((count + 1))
    for f in "${plugin_dir}commands"/*.md;  do link_one "$f"      commands; done
    for d in "${plugin_dir}skills"/*/;      do link_one "${d%/}"  skills;   done
    for f in "${plugin_dir}agents"/*.md;    do link_one "$f"      subagents; done
  done
  echo "gemini: farm rebuilt from $count plugin(s); skipped: ${skipped[*]:-none}"
}

build_extension() {
  # Repo-level extension manifest. It only declares the farm paths + context
  # file — it does not enumerate plugins — so its fields are repo constants, not
  # per-plugin meta. Emitted here so it is a build artifact like the rest.
  cat > "$repo_root/gemini-extension.json" <<'JSON'
{
  "name": "agent-marketplace",
  "version": "0.2.0",
  "description": "Personal toolkit shared across Claude Code, Codex, and Gemini CLI.",
  "contextFileName": "AGENTS.md",
  "commands": "./gemini/commands/",
  "skills": "./gemini/skills/",
  "subagents": "./gemini/subagents/",
  "mcpServers": {}
}
JSON
  echo "gemini: wrote gemini-extension.json"
}

require_gemini() {
  if ! command -v gemini >/dev/null 2>&1; then
    echo "gemini: 'gemini' CLI not found on this machine — the farm + manifest are" >&2
    echo "        built, but install/uninstall need Gemini. Run on a machine with gemini:" >&2
    echo "          gemini extensions link \"$repo_root\"          # install (dev symlink)" >&2
    echo "          gemini extensions uninstall agent-marketplace  # uninstall" >&2
    return 1
  fi
}

cmd=${1:-}
case "$cmd" in
  build|install|uninstall) ;;
  *) echo "usage: $(basename "$0") <build|install|uninstall> [plugin]" >&2; exit 2 ;;
esac

# Gemini collapses everything into one extension; there is no per-plugin install,
# so the optional [plugin] arg is ignored and we always rebuild the whole farm.
build_farm
build_extension

case "$cmd" in
  install)   require_gemini && { gemini extensions link "$repo_root"; echo "gemini: extension linked."; } ;;
  uninstall) require_gemini && { gemini extensions uninstall agent-marketplace; echo "gemini: extension removed."; } ;;
esac

#!/usr/bin/env bash
# Pi adapter — one of bin/adapters/<harness>.sh.   (Pi 0.79.0)
#
#   bin/adapters/pi.sh <build|install|uninstall> [plugin]
#
#   build      No-op. Pi needs no generated manifest — it discovers SKILL.md
#              skills straight from the filesystem. Kept so `make build` is uniform.
#   install    Symlink each plugin's skills into Pi's skill-discovery dir
#              ($INSTALL_ROOT/skills/<skill>). Pi reads Claude-compatible SKILL.md
#              (verified: a planted SKILL.md is discovered without --skill).
#              If a plugin has agents/, install the pi-subagents extension (idempotent).
#   uninstall  Remove only the skill symlinks we created (guarded). Never touches plugins/.
#
# SANDBOX HANDLE = HOME (not PREFIX): Pi discovers skills under $HOME/.pi/agent/skills,
# so the adapter targets the same place Pi reads. Test with:
#   HOME=/tmp/pi bin/adapters/pi.sh install   (then HOME=/tmp/pi pi -p "...")
#
# ALIAS PLUGINS ARE SKIPPED (bookmark -> bm): Pi's skill space is keyed by SKILL.md
# `name`, and the alias's skills are the same files as bm's -> identical names ->
# collision. The /bookmark alias is a Claude-only convenience (its value is the
# /bookmark:* command namespace, which Pi's by-name skills don't reproduce).

set -euo pipefail

HARNESS=pi
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
INSTALL_ROOT="${PI_AGENT_DIR:-$HOME/.pi/agent}"
PI_SUBAGENTS_PKG="npm:pi-subagents"   # real package (npm pi-subagents); pinned here
source "$(dirname "$0")/lib.sh"

skills_dir="$INSTALL_ROOT/skills"
prompts_dir="$INSTALL_ROOT/prompts"   # Pi prompt-templates: ~/.pi/agent/prompts/*.md -> /<name>

link_skill() {
  local src=$1                       # absolute repo path to a skill dir
  local name=${src##*/}
  local dest="$skills_dir/$name"
  if [ -L "$dest" ]; then
    local tgt; tgt=$(readlink "$dest")
    case "$tgt" in
      "$repo_root"/*) rm "$dest" ;;  # ours — refresh
      *) echo "pi: collision at $dest -> $tgt (foreign); skipping $name" >&2; return 0 ;;
    esac
  elif [ -e "$dest" ]; then
    echo "pi: $dest exists and is not our symlink; skipping $name" >&2; return 0
  fi
  ln -s "$src" "$dest"
  echo "pi: linked skill $name -> $dest"
}

link_prompt() {
  local src=$1 plugin=$2            # src = absolute repo path to a command .md
  # Pi prompt-template discovery is flat + non-recursive + keyed by filename, so
  # prefix with the plugin name to avoid cross-plugin collisions (bm/audit vs
  # wiki_keeper/audit). Invoked as /<plugin>-<cmd>.
  local cname="$plugin-${src##*/}"
  local dest="$prompts_dir/$cname"
  if [ -L "$dest" ]; then
    local tgt; tgt=$(readlink "$dest")
    case "$tgt" in
      "$repo_root"/*) rm "$dest" ;;
      *) echo "pi: collision at $dest -> $tgt (foreign); skipping" >&2; return 0 ;;
    esac
  elif [ -e "$dest" ]; then
    echo "pi: $dest exists and is not our symlink; skipping" >&2; return 0
  fi
  ln -s "$src" "$dest"
  echo "pi: linked prompt /${cname%.md} -> $dest"
}

install_one() {
  local name=$1
  local sdir="$repo_root/plugins/$name/skills"
  if [ -d "$sdir" ]; then
    mkdir -p "$skills_dir"
    local d
    for d in "$sdir"/*/; do
      [ -d "$d" ] || continue
      link_skill "${d%/}"
    done
  fi
  # Commands -> Pi prompt templates (Claude command bodies use $1/$ARGUMENTS, which
  # Pi prompt templates also understand).
  local cdir="$repo_root/plugins/$name/commands"
  if [ -d "$cdir" ]; then
    mkdir -p "$prompts_dir"
    local f
    for f in "$cdir"/*.md; do
      [ -e "$f" ] || continue
      link_prompt "$f" "$name"
    done
  fi
  # Subagents: a plugin with agents/ wants the pi-subagents extension.
  if [ -d "$repo_root/plugins/$name/agents" ]; then
    if [ "${PI_SKIP_SUBAGENTS:-0}" != "1" ] && command -v pi >/dev/null 2>&1; then
      echo "pi: $name has agents/ -> ensuring $PI_SUBAGENTS_PKG (idempotent)"
      pi install "$PI_SUBAGENTS_PKG" >/dev/null 2>&1 \
        || echo "pi: warn — 'pi install $PI_SUBAGENTS_PKG' failed; agents unavailable for $name" >&2
    else
      echo "pi: NOTE — $name has agents/; install $PI_SUBAGENTS_PKG to enable subagents (set PI_SKIP_SUBAGENTS=1 to silence)"
    fi
    # Agent-file -> pi-subagents wiring is format-dependent and unverified; see HARNESS-NOTES.
  fi
}

rm_our_symlink() {            # rm a symlink only if it points back into the repo
  local dest=$1 label=$2 tgt
  [ -L "$dest" ] || return 0
  tgt=$(readlink "$dest")
  case "$tgt" in
    "$repo_root"/*) rm "$dest"; echo "pi: removed $label $dest" ;;
    *) echo "pi: skip $dest — points outside repo ($tgt)" >&2 ;;
  esac
}

uninstall_one() {
  local name=$1
  local sdir="$repo_root/plugins/$name/skills"
  local cdir="$repo_root/plugins/$name/commands"
  local d f
  if [ -d "$sdir" ]; then
    for d in "$sdir"/*/; do
      [ -d "$d" ] || continue
      rm_our_symlink "$skills_dir/$(basename "${d%/}")" "skill symlink"
    done
  fi
  if [ -d "$cdir" ]; then
    for f in "$cdir"/*.md; do
      [ -e "$f" ] || continue
      rm_our_symlink "$prompts_dir/$name-${f##*/}" "prompt symlink"
    done
  fi
}

cmd=${1:-}
target=${2:-}
case "$cmd" in
  build) echo "pi: build is a no-op (Pi discovers SKILL.md from the filesystem; no manifest to generate)"; exit 0 ;;
  install|uninstall) ;;
  *) echo "usage: $(basename "$0") <build|install|uninstall> [plugin]" >&2; exit 2 ;;
esac

while IFS= read -r name; do
  [ -n "$name" ] || continue
  meta_path="$repo_root/plugins/$name/meta.yaml"
  [ -f "$meta_path" ] || { echo "pi: skip $name — no meta.yaml" >&2; continue; }
  if is_alias "$meta_path"; then
    echo "pi: skip $name — alias plugin (duplicate skill names; alias is Claude-only)"; continue
  fi
  if ! installs_on "$meta_path" "$HARNESS"; then
    echo "pi: skip $name — harnesses excludes $HARNESS"; continue
  fi
  "${cmd}_one" "$name"
done < <(plugins_list "$target")

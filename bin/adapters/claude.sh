#!/usr/bin/env bash
# Claude adapter — one of bin/adapters/<harness>.sh.
#
#   bin/adapters/claude.sh <build|install|uninstall> [plugin]
#
# Source of truth is plugins/<name>/meta.yaml. Nothing here is hand-authored
# downstream of that file.
#
#   build      Generate plugins/<name>/.claude-plugin/plugin.json from meta.yaml.
#              Pure function of the working tree — no $HOME writes.
#   install    build, then symlink plugins/<name> -> $INSTALL_ROOT/skills/<name>
#              (whole-dir; Claude discovers it in place as <name>@skills-dir).
#              COPY=1 copies instead of symlinking.
#   uninstall  Remove only the symlink/copy we created. Never touches plugins/.
#
# INSTALL_ROOT is the one machine-specific fact, and the dry-run handle:
#   PREFIX=/tmp/mp bin/adapters/claude.sh install reviewers
#   -> claude --plugin-dir /tmp/mp/skills/reviewers

set -euo pipefail

HARNESS=claude
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
INSTALL_ROOT="${PREFIX:-$HOME/.claude}"
source "$(dirname "$0")/lib.sh"

build_one() {
  local name=$1
  gen_plugin_json "$repo_root/plugins/$name/meta.yaml" \
                  "$repo_root/plugins/$name/.claude-plugin/plugin.json"
  echo "claude: built $name/.claude-plugin/plugin.json"
}

install_one() {
  local name=$1
  build_one "$name"
  local src="$repo_root/plugins/$name"
  local dest="$INSTALL_ROOT/skills/$name"
  mkdir -p "$INSTALL_ROOT/skills"

  # Clear any prior install at dest, never touching repo content.
  if [ -L "$dest" ]; then
    rm "$dest"
  elif [ -d "$dest" ]; then
    case "$dest" in
      "$repo_root"/*) echo "claude: refuse — $dest is inside the repo" >&2; return 1 ;;
      *) rm -rf "$dest" ;;
    esac
  elif [ -e "$dest" ]; then
    echo "claude: refuse — $dest exists and is not a dir/symlink" >&2; return 1
  fi

  if [ "${COPY:-0}" = "1" ]; then
    cp -R "$src" "$dest"
    echo "claude: copied $name -> $dest"
  else
    ln -s "$src" "$dest"
    echo "claude: linked  $name -> $dest"
  fi
}

uninstall_one() {
  local name=$1
  local dest="$INSTALL_ROOT/skills/$name"
  if [ -L "$dest" ]; then
    local tgt; tgt=$(readlink "$dest")
    case "$tgt" in
      "$repo_root"/*) rm "$dest"; echo "claude: removed symlink $dest" ;;
      *) echo "claude: skip $dest — symlink points outside repo ($tgt)" >&2 ;;
    esac
  elif [ -d "$dest" ]; then
    case "$dest" in
      "$repo_root"/*) echo "claude: refuse — $dest is inside the repo" >&2 ;;
      *) rm -rf "$dest"; echo "claude: removed copy $dest" ;;
    esac
  elif [ -e "$dest" ]; then
    echo "claude: skip $dest — not a symlink or dir" >&2
  else
    echo "claude: $name not installed at $dest"
  fi
}

cmd=${1:-}
target=${2:-}
case "$cmd" in
  build|install|uninstall) ;;
  *) echo "usage: $(basename "$0") <build|install|uninstall> [plugin]" >&2; exit 2 ;;
esac

did_any=0
while IFS= read -r name; do
  [ -n "$name" ] || continue
  meta_path="$repo_root/plugins/$name/meta.yaml"
  if [ ! -f "$meta_path" ]; then
    echo "claude: skip $name — no meta.yaml" >&2; continue
  fi
  if ! installs_on "$meta_path" "$HARNESS"; then
    echo "claude: skip $name — harnesses excludes $HARNESS"; continue
  fi
  "${cmd}_one" "$name"
  did_any=1
done < <(plugins_list "$target")

if [ "$cmd" = "uninstall" ] && [ "$did_any" = "1" ]; then
  echo "claude: note — also run 'claude plugin disable <name>@skills-dir' to drop it from the UI."
fi

#!/usr/bin/env bash
# Pi adapter — one of bin/adapters/<harness>.sh.   (Pi 0.79.0)
#
#   bin/adapters/pi.sh <build|install|uninstall> [plugin]
#
#   build      Generate the hook-bridge manifest (bin/adapters/pi/hook-bridge/manifest.json).
#              Skills/prompts need no manifest — Pi discovers those from the filesystem.
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

# --- hook bridge: Pi has no shell hooks.json, so a TS extension runs our scripts ---
BRIDGE_SRC="$repo_root/bin/adapters/pi/hook-bridge"
BRIDGE_DEST="$INSTALL_ROOT/extensions/hook-bridge"   # auto-discovered: ~/.pi/agent/extensions/<name>/index.ts

# gen_manifest <plugin...> : write BRIDGE_SRC/manifest.json (absolute script paths)
# so the bridge can run each plugin's Claude-format hook scripts. Working-tree only.
gen_manifest() {
  python3 - "$repo_root" "$@" <<'PY'
import sys, os, json, re
root, plugins = sys.argv[1], sys.argv[2:]
entries = []
for p in plugins:
    hp = os.path.join(root, "plugins", p, "hooks", "hooks.json")
    if not os.path.exists(hp):
        continue
    plugin_root = os.path.join(root, "plugins", p)
    for event, defs in (json.load(open(hp)).get("hooks") or {}).items():
        for d in defs:
            for h in d.get("hooks", []):
                m = re.search(r'\$CLAUDE_PLUGIN_ROOT(/\S*?\.sh)', h.get("command") or "")
                if not m:
                    continue
                entries.append({"event": event, "matcher": d.get("matcher"),
                                "script": plugin_root + m.group(1), "pluginRoot": plugin_root})
out = os.path.join(root, "bin", "adapters", "pi", "hook-bridge", "manifest.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump({"hooks": entries}, f, indent=2); f.write("\n")
print(f"pi: hook-bridge manifest -> {len(entries)} hook(s)")
PY
}

install_bridge() {
  [ -s "$BRIDGE_SRC/manifest.json" ] || return 0     # no hooks -> no bridge
  mkdir -p "$INSTALL_ROOT/extensions"
  if [ -L "$BRIDGE_DEST" ]; then rm "$BRIDGE_DEST"
  elif [ -e "$BRIDGE_DEST" ]; then echo "pi: $BRIDGE_DEST exists and is not our symlink; skipping bridge" >&2; return 0; fi
  ln -s "$BRIDGE_SRC" "$BRIDGE_DEST"
  echo "pi: linked hook-bridge -> $BRIDGE_DEST (auto-discovered; /reload to refresh)"
}

# --- Pi subagents: convert Claude agents -> Pi format under ~/.pi/agent/agents/ ---
# Pi subagents are agents/*.md (name/description/tools/model + body) discovered from
# ~/.pi/agent/agents/ and run as isolated sub-processes by a subagent extension
# (pi-subagents, installed per-plugin when agents/ is present). `tools` must be a
# comma string of LOWERCASE Pi tool names — verified discovered by Pi's reference
# subagent extension.
agents_dir="$INSTALL_ROOT/agents"
AGENTS_BUILD="$repo_root/bin/adapters/pi/agents"   # generated, gitignored

gen_agent() {            # <src.md> <dest.md> : Claude agent -> Pi agent (map tool names)
  python3 - "$1" "$2" <<'PY'
import sys
MAP = {"read":"read","write":"write","edit":"edit","multiedit":"edit","bash":"bash",
       "grep":"grep","glob":"find","ls":"ls"}
src, dest = sys.argv[1], sys.argv[2]
text = open(src).read()
if text.startswith("---"):
    _, fm, body = text.split("---", 2)
    out = []
    for line in fm.splitlines():
        s = line.strip()
        if s.lower().startswith("tools:"):
            toks = [t.strip().lower() for t in s.split(":", 1)[1].split(",") if t.strip()]
            out.append("tools: " + ", ".join(MAP.get(t, t) for t in toks))
        else:
            out.append(line)
    open(dest, "w").write("---" + "\n".join(out) + "\n---" + body)
else:
    open(dest, "w").write(text)
PY
}

gen_agents() {           # <plugin...> : regenerate AGENTS_BUILD from pi-targeted plugins
  rm -rf "$AGENTS_BUILD"
  local p f adir n=0
  for p in "$@"; do
    adir="$repo_root/plugins/$p/agents"
    [ -d "$adir" ] || continue
    mkdir -p "$AGENTS_BUILD"
    for f in "$adir"/*.md; do [ -e "$f" ] || continue; gen_agent "$f" "$AGENTS_BUILD/$(basename "$f")"; n=$((n + 1)); done
  done
  [ "$n" -gt 0 ] && echo "pi: converted $n subagent(s) for Pi (consumer: pi-subagents)"
}

install_agents() {
  [ -d "$AGENTS_BUILD" ] || return 0
  mkdir -p "$agents_dir"
  local f dest
  for f in "$AGENTS_BUILD"/*.md; do
    [ -e "$f" ] || continue
    dest="$agents_dir/$(basename "$f")"
    if [ -L "$dest" ]; then rm "$dest"
    elif [ -e "$dest" ]; then echo "pi: $dest exists and is not our symlink; skipping" >&2; continue; fi
    ln -s "$f" "$dest"; echo "pi: linked subagent $(basename "${f%.md}") -> $dest"
  done
}

uninstall_agents() {
  [ -d "$AGENTS_BUILD" ] || return 0
  local f
  for f in "$AGENTS_BUILD"/*.md; do
    [ -e "$f" ] || continue
    rm_our_symlink "$agents_dir/$(basename "$f")" "subagent symlink"
  done
}

cmd=${1:-}
target=${2:-}
case "$cmd" in
  build|install|uninstall) ;;
  *) echo "usage: $(basename "$0") <build|install|uninstall> [plugin]" >&2; exit 2 ;;
esac

# Resolve the pi-targeted plugin set (non-alias, harnesses includes pi).
pi_plugins=()
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
  pi_plugins+=("$name")
done < <(plugins_list "$target")

# build (all commands): regenerate the hook-bridge manifest + converted subagents (working tree).
[ ${#pi_plugins[@]} -gt 0 ] && { gen_manifest "${pi_plugins[@]}"; gen_agents "${pi_plugins[@]}"; }

case "$cmd" in
  install)
    [ ${#pi_plugins[@]} -gt 0 ] && for name in "${pi_plugins[@]}"; do install_one "$name"; done
    install_bridge
    install_agents
    ;;
  uninstall)
    [ ${#pi_plugins[@]} -gt 0 ] && for name in "${pi_plugins[@]}"; do uninstall_one "$name"; done
    rm_our_symlink "$BRIDGE_DEST" "hook-bridge symlink"
    uninstall_agents
    ;;
esac

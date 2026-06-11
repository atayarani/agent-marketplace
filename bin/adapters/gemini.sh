#!/usr/bin/env bash
# Gemini adapter — one of bin/adapters/<harness>.sh.   (Gemini CLI 0.45.x)
#
#   bin/adapters/gemini.sh <build|install|uninstall> [plugin]
#
# REWRITTEN against the real Gemini 0.45 extension model (verified from the CLI's
# own bundled docs at .../gemini-cli/.../bundle/docs/{extensions,cli,hooks}/). The
# previous farm-at-gemini/{commands,skills,subagents} + manifest-path-keys design
# targeted an older Gemini and is NOT loaded by current Gemini. Real model:
#   - An extension is a directory with gemini-extension.json at its root, loaded
#     from <home>/.gemini/extensions/. `gemini extensions link <dir>` symlinks it (live).
#   - commands/<sub>/<cmd>.toml -> /<sub>:<cmd>   (TOML, dir path -> colon namespace)
#   - skills/<name>/SKILL.md     -> <name> skill   (Claude-compatible SKILL.md)
#   - agents/*.md                -> sub-agents      (preview feature)
#   - hooks/hooks.json           -> hooks           (Phase 4; not emitted yet)
#   - contextFileName loads a file FROM the extension dir.
#
# So we generate a self-contained extension under gemini/ (gitignored at Phase 5)
# and link THAT. bm (harnesses) and bookmark (alias) are skipped as before.
#
#   build      Regenerate gemini/ as the extension. Pure function of the tree.
#   install    build, then `gemini extensions link "<repo>/gemini"`.
#   uninstall  `gemini extensions uninstall agent-marketplace`.
#
# Claude command bodies use $ARGUMENTS -> mapped to Gemini's {{args}}. Sandbox = HOME.

set -euo pipefail

HARNESS=gemini
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
EXT_DIR="$repo_root/gemini"          # the generated extension root
source "$(dirname "$0")/lib.sh"
shopt -s nullglob

# link_unique <abs-src> <dest-dir> <kind> : relative symlink, abort on genuine collision
link_unique() {
  local src=$1 dest_dir=$2 kind=$3
  local name=${src##*/}
  local dest="$dest_dir/$name"
  if [[ -e $dest || -L $dest ]]; then
    echo "gemini: collision in $kind/: $name — two non-skipped plugins claim it. Rename one." >&2
    exit 1
  fi
  ln -s "$(python3 -c 'import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))' "$src" "$dest_dir")" "$dest"
}

# gen_command_toml <command.md> <out.toml> : convert a Claude slash-command to a Gemini TOML command
gen_command_toml() {
  python3 - "$1" "$2" <<'PY'
import sys, os, yaml
md, out = sys.argv[1], sys.argv[2]
text = open(md).read()
desc, body = "", text
if text.startswith("---"):
    parts = text.split("---", 2)
    if len(parts) == 3:
        fm = yaml.safe_load(parts[1]) or {}
        desc = (fm.get("description") or "").strip()
        body = parts[2].lstrip("\n")
body = body.replace("$ARGUMENTS", "{{args}}")          # Claude -> Gemini arg token
os.makedirs(os.path.dirname(out), exist_ok=True)
def basic(s):                                          # TOML single-line basic string
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
if "'''" not in body:                                  # TOML literal multiline: zero escaping
    prompt = "'''\n" + body + ("" if body.endswith("\n") else "\n") + "'''"
else:                                                  # fall back to basic multiline
    esc = body.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    prompt = '"""\n' + esc + ('' if esc.endswith('\n') else '\n') + '"""'
with open(out, "w") as f:
    if desc:
        f.write("description = " + basic(desc) + "\n")
    f.write("prompt = " + prompt + "\n")
PY
}

build() {
  rm -rf "$EXT_DIR"
  mkdir -p "$EXT_DIR/skills" "$EXT_DIR/commands" "$EXT_DIR/agents"

  # Manifest (repo-level constants; commands/skills/agents are auto-discovered, no path keys).
  cat > "$EXT_DIR/gemini-extension.json" <<'JSON'
{
  "name": "agent-marketplace",
  "version": "0.2.0",
  "description": "Personal toolkit shared across Claude Code, Codex, and Gemini CLI.",
  "contextFileName": "AGENTS.md"
}
JSON
  # contextFileName loads from the extension dir; point at the repo's AGENTS.md.
  ln -s ../AGENTS.md "$EXT_DIR/AGENTS.md"

  local count=0 plugin_dir name meta d f
  local -a skipped=()
  for plugin_dir in "$repo_root"/plugins/*/; do
    name=$(basename "$plugin_dir")
    meta="${plugin_dir}meta.yaml"
    [ -f "$meta" ] || { echo "gemini: skip $name — no meta.yaml" >&2; continue; }
    if is_alias "$meta"; then skipped+=("$name(alias)"); continue; fi
    if ! installs_on "$meta" "$HARNESS"; then skipped+=("$name(excluded)"); continue; fi
    count=$((count + 1))

    for d in "${plugin_dir}skills"/*/;  do link_unique "${d%/}" "$EXT_DIR/skills" skills; done
    for f in "${plugin_dir}agents"/*.md; do link_unique "$f" "$EXT_DIR/agents" agents; done
    # commands -> commands/<plugin>/<cmd>.toml  => /<plugin>:<cmd>
    if [ -d "${plugin_dir}commands" ]; then
      for f in "${plugin_dir}commands"/*.md; do
        gen_command_toml "$f" "$EXT_DIR/commands/$name/$(basename "${f%.md}").toml"
      done
    fi
  done
  # Drop empty kind dirs so the extension stays clean.
  for d in skills commands agents; do rmdir "$EXT_DIR/$d" 2>/dev/null || true; done
  echo "gemini: built extension at gemini/ from $count plugin(s); skipped: ${skipped[*]:-none}"
}

require_gemini() {
  command -v gemini >/dev/null 2>&1 && return 0
  echo "gemini: 'gemini' CLI not found — extension built at gemini/, but install needs Gemini:" >&2
  echo "          gemini extensions link \"$EXT_DIR\"" >&2
  echo "          gemini extensions uninstall agent-marketplace" >&2
  return 1
}

cmd=${1:-}
case "$cmd" in
  build)     build ;;
  install)   build; require_gemini && { gemini extensions link "$EXT_DIR"; echo "gemini: extension linked."; } ;;
  uninstall) require_gemini && { gemini extensions uninstall agent-marketplace; echo "gemini: extension removed."; } ;;
  *) echo "usage: $(basename "$0") <build|install|uninstall> [plugin]" >&2; exit 2 ;;
esac

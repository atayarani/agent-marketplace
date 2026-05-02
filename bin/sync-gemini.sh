#!/usr/bin/env bash
# Rebuild gemini/{commands,skills,subagents}/ as a symlink farm pointing
# into each plugins/<sub-plugin>/ directory.
#
# Why: Gemini's extension manifest accepts only one path per kind, but
# this repo ships multiple sub-plugins. We collapse all sub-plugin
# content into one path per kind so gemini-extension.json can point at
# a single place per kind. Claude Code and Codex read directly from
# plugins/<sub-plugin>/ via their own marketplace catalogs and ignore
# this farm.
#
# Run this after adding, removing, or renaming any sub-plugin command,
# skill, or subagent. Idempotent — wipes and rebuilds every time.

set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

shopt -s nullglob

link_one() {
  local src=$1 dest_kind=$2
  local name=${src##*/}
  local dest="gemini/$dest_kind/$name"
  if [[ -e $dest || -L $dest ]]; then
    echo "sync-gemini: collision in gemini/$dest_kind/: $name" >&2
    echo "  two sub-plugins claim the same name. Rename one." >&2
    exit 1
  fi
  ln -s "../../$src" "$dest"
}

for kind in commands skills subagents; do
  rm -rf "gemini/$kind"
  mkdir -p "gemini/$kind"
done

count=0
for plugin_dir in plugins/*/; do
  count=$((count + 1))

  for f in "${plugin_dir}commands"/*.md; do
    link_one "$f" commands
  done

  for d in "${plugin_dir}skills"/*/; do
    link_one "${d%/}" skills
  done

  for f in "${plugin_dir}agents"/*.md; do
    link_one "$f" subagents
  done
done

echo "sync-gemini: aggregated $count sub-plugin(s) into gemini/"

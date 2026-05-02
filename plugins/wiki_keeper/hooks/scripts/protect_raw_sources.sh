#!/usr/bin/env bash
# Claude Code only — uses the PreToolUse JSON hook protocol.
# Blocks Edit / Write / NotebookEdit calls that target a path under
# `sources/raw/` anywhere in the tree. The wiki pattern's first rule:
# raw sources are immutable.
#
# To override (rare — usually a normalization pass), set
# WIKI_KEEPER_ALLOW_RAW_EDITS=1 in the environment.
set -euo pipefail

if [[ "${WIKI_KEEPER_ALLOW_RAW_EDITS:-}" == "1" ]]; then
  exit 0
fi

input="$(cat)"

file_path="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = data.get("tool_input") or {}
path = ti.get("file_path") or ti.get("notebook_path") or ""
print(path)
' 2>/dev/null || true)"

if [[ -z "$file_path" ]]; then
  exit 0
fi

case "$file_path" in
  */sources/raw/*|sources/raw/*)
    reason="sources/raw/ is immutable per the wiki pattern. Edit sources/normalized/ instead, or set WIKI_KEEPER_ALLOW_RAW_EDITS=1 if you really mean to modify the raw capture."
    printf '{"decision": "block", "reason": %s}\n' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$reason")"
    exit 0
    ;;
esac

exit 0

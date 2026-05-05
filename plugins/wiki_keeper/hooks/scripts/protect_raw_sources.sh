#!/usr/bin/env bash
# Claude Code only — uses the PreToolUse JSON hook protocol.
# Protects `sources/raw/` (the immutable-capture layer of the wiki pattern).
#
# Rules:
# - Edit and NotebookEdit always modify existing files → blocked under
#   sources/raw/. Edit sources/normalized/ instead.
# - Write to a path under sources/raw/ is *allowed* when the file does
#   not yet exist (initial capture — that's what `youtube-transcript`,
#   `ai-chat-source`, etc. produce). Write to a path that already exists
#   is *blocked* (overwriting a captured artifact violates immutability).
#
# To override (rare — e.g. a manual rewrite of an already-captured file),
# set WIKI_KEEPER_ALLOW_RAW_EDITS=1 in the environment.
set -euo pipefail

if [[ "${WIKI_KEEPER_ALLOW_RAW_EDITS:-}" == "1" ]]; then
  exit 0
fi

input="$(cat)"

tool_name="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print(data.get("tool_name") or "")
' 2>/dev/null || true)"

file_path="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = data.get("tool_input") or {}
print(ti.get("file_path") or ti.get("notebook_path") or "")
' 2>/dev/null || true)"

if [[ -z "$file_path" ]]; then
  exit 0
fi

case "$file_path" in
  */sources/raw/*|sources/raw/*) ;;
  *) exit 0 ;;
esac

# Path is under sources/raw/. Decide based on tool + whether the file already exists.
case "$tool_name" in
  Write)
    # Allow new-file capture; block overwrites of existing raws.
    if [[ ! -e "$file_path" ]]; then
      exit 0
    fi
    reason="sources/raw/ is immutable per the wiki pattern. The target file already exists; overwriting a captured raw is blocked. Set WIKI_KEEPER_ALLOW_RAW_EDITS=1 if you really mean to overwrite."
    ;;
  Edit|NotebookEdit)
    reason="sources/raw/ is immutable per the wiki pattern. Edit/NotebookEdit modify existing files; raw captures must not be modified. Edit sources/normalized/ instead, or set WIKI_KEEPER_ALLOW_RAW_EDITS=1 if you really mean to modify the raw capture."
    ;;
  *)
    # Matcher should restrict us to Edit|Write|NotebookEdit, but be conservative on anything unexpected.
    reason="sources/raw/ is immutable per the wiki pattern. Set WIKI_KEEPER_ALLOW_RAW_EDITS=1 if you really mean to modify the raw capture."
    ;;
esac

printf '{"decision": "block", "reason": %s}\n' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$reason")"
exit 0

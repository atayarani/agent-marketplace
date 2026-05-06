#!/usr/bin/env bash
# Claude Code only — uses the PreToolUse JSON hook protocol.
# Protects `sources/normalized/` from synthesis content.
#
# `system/schemas/source-normalization.md` says normalized files
# "must not include: summaries, conclusions, interpretations,
# cross-source synthesis, unsupported claims, agent opinions."
# `system/schemas/youtube-ingestion.md` rules 6–7 say the same for
# YouTube transcripts. Synthesis belongs in `wiki/`, not in normalized
# sources.
#
# This hook blocks Write / Edit / NotebookEdit on paths under
# `sources/normalized/` when the content being written contains a
# top-level markdown heading matching one of the synthesis-shaped
# section markers. The match is line-start `## ` plus the marker text;
# transcript prose containing the word "thesis" or "concepts" mid-line
# is unaffected.
#
# Forbidden section markers:
#   ## Thesis
#   ## Distinctive moves
#   ## Cross-source observations
#   ## Candidate concepts
#   ## Empirical claims worth tracking
#   ## Related concepts
#   ## Related claims
#
# To override (rare — e.g. an exotic source-type genuinely needs one of
# these section names), set WIKI_KEEPER_ALLOW_NORMALIZED_SYNTHESIS=1 in
# the environment.
set -euo pipefail

if [[ "${WIKI_KEEPER_ALLOW_NORMALIZED_SYNTHESIS:-}" == "1" ]]; then
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
  */sources/normalized/*|sources/normalized/*) ;;
  *) exit 0 ;;
esac

# Extract the new content / new_string depending on tool.
new_content="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = data.get("tool_input") or {}
tool_name = data.get("tool_name") or ""
if tool_name == "Write":
    print(ti.get("content") or "")
elif tool_name == "Edit":
    print(ti.get("new_string") or "")
elif tool_name == "NotebookEdit":
    print(ti.get("new_source") or "")
else:
    print("")
' 2>/dev/null || true)"

if [[ -z "$new_content" ]]; then
  exit 0
fi

# Check for synthesis-section markers at line-start. Use grep -E with
# anchored alternation; a hit means the content carries a forbidden
# header.
forbidden_pattern='^## (Thesis( \(.*\))?|Distinctive moves|Cross-source observations|Candidate concepts|Empirical claims worth tracking|Related concepts|Related claims)[[:space:]]*$'

matched_marker="$(printf '%s' "$new_content" | grep -E "$forbidden_pattern" | head -1 || true)"

if [[ -z "$matched_marker" ]]; then
  exit 0
fi

reason="sources/normalized/ must not contain synthesis per system/schemas/source-normalization.md and youtube-ingestion.md (rules 6–7). The content being written contains a synthesis-shaped section header: '${matched_marker}'. Move synthesis to wiki/ pages (entity, concept, or claim) and keep the normalized file to source metadata + transcript only. Set WIKI_KEEPER_ALLOW_NORMALIZED_SYNTHESIS=1 if a specific source type genuinely needs this section name."

printf '{"decision": "block", "reason": %s}\n' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$reason")"
exit 0

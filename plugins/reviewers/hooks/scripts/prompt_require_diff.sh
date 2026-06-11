#!/usr/bin/env bash
# Claude Code only — uses the UserPromptSubmit JSON hook protocol and is not
# wired into Codex or Gemini.
set -euo pipefail

# UserPromptSubmit hooks receive a JSON payload on stdin: {"prompt": "...", ...}.
input="$(cat 2>/dev/null || true)"

prompt=""
if [[ -n "$input" ]] && command -v python3 >/dev/null 2>&1; then
  prompt="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("prompt", ""))
except Exception:
    pass' 2>/dev/null || true)"
fi

# Self-gate (portable across harnesses): this hook only concerns deep-review
# requests. Claude restricts it via the hooks.json UserPromptSubmit matcher, but
# Codex IGNORES that matcher and runs the hook on EVERY prompt — without this gate
# it blocks every no-diff prompt. If the prompt doesn't mention deep-review (or
# couldn't be read), allow and get out of the way.
if ! printf '%s' "$prompt" | grep -Eqi '(^|[^[:alnum:]])deep-review([^[:alnum:]]|$)'; then
  exit 0
fi

# If the prompt names a PR/issue number, the deep-review skill fetches the diff
# itself via `gh pr diff <number>`, so the local diff/staged checks below do not apply.
if [[ -n "$prompt" ]] && printf '%s' "$prompt" | grep -Eq '(^|[^[:alnum:]])(#?[0-9]+)([^[:alnum:]]|$)'; then
  exit 0
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

if ! git diff --staged --quiet; then
  exit 0
fi

ref="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)" || ref=""
default_branch="${ref#origin/}"
if [[ -z "$default_branch" ]]; then
  for candidate in main master; do
    if git show-ref --verify --quiet "refs/heads/$candidate"; then
      default_branch="$candidate"
      break
    fi
  done
fi

if [[ -n "$default_branch" ]] && ! git diff --quiet "$default_branch...HEAD" 2>/dev/null; then
  exit 0
fi

echo '{"decision": "block", "reason": "No staged changes or branch diff vs the default branch. Stage changes or specify a PR number."}'

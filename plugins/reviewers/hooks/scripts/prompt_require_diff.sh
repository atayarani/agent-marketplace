#!/usr/bin/env bash
# Claude Code only — uses the UserPromptSubmit JSON hook protocol and is not
# wired into Codex or Gemini.
set -euo pipefail

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

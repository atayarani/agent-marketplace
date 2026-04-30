---
name: deep-review
description: Parallel PR review with a selectable team of reviewers. Use for reviewing staged changes, a branch diff, or a GitHub PR. Caller specifies which reviewers to run.
---

Run the requested reviewers in parallel against the diff. Do not review the diff yourself in this session.

## Available reviewers

- security: injection, authn/authz, secrets, crypto, IaC permissions
- performance: N+1, unbounded work, blocking I/O, memory, lock contention
- style: local conventions, naming, error handling, doc comments

Add more by dropping files into `agents/<name>-reviewer.md` and listing them here.

## Selecting reviewers

The caller specifies reviewers one of three ways:

1. Explicit list: "deep-review PR 1234 with security and style"
2. Preset: `full` runs all three reviewers.
3. Auto: if unspecified, run all three on any source-code diff. If the diff only touches docs or config, ask the user before spawning.

Confirm the selection in one line before spawning: "Running: security, style. Proceed? (or specify others)"
Skip confirmation if the caller already named reviewers explicitly.

## Steps

1. Resolve the diff:
   - PR number: `gh pr diff <number>`
   - Branch: resolve default branch via `git symbolic-ref --short refs/remotes/origin/HEAD | sed 's@^origin/@@'` (fall back to `main`/`master`), then `git diff <default>...<branch>`
   - Otherwise: `git diff --staged`
   Save to `/tmp/review.diff`.

2. Determine the reviewer set per the rules above.

3. Spawn the selected subagents in parallel. Pass each one:
   "Review /tmp/review.diff. Repo root: <pwd>."
   For style-reviewer, also pass: "Style guide: docs/style-guide.md if present."

4. Merge results. Deduplicate where reviewers flag the same line. Sort by severity: blocker, concern, nit. Each row: file:line, severity, category, reviewer, issue, fix.

5. Return the merged table plus a one-line header: "Reviewed by: <list>. N findings (X blocker, Y concern, Z nit)."

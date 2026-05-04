---
description: Run a parallel review on a GitHub PR
argument-hint: "<PR number> [reviewers]"
---

Run the deep-review skill against the specified PR.

## Steps

1. Parse `$ARGUMENTS`. The first token is the PR number. Any remaining tokens are the reviewer selection.

2. If no PR number is given, stop and ask the user which PR to review.

3. Fetch the diff: `gh pr diff <number> > /tmp/review.diff`

4. Invoke the deep-review skill with the diff path and reviewer selection. If no reviewers were specified, let deep-review auto-select.

5. Return the merged findings from deep-review unchanged.

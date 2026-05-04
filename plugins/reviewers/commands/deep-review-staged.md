---
description: Run a parallel review on staged changes
argument-hint: "[reviewers: security, performance, style, full]"
---

Run the deep-review skill against the currently staged changes.

## Steps

1. Verify there are staged changes. Run `git diff --staged --stat`. If the output is empty, stop and tell the user there is nothing staged.

2. Save the staged diff to `/tmp/review.diff`:
   `git diff --staged > /tmp/review.diff`

3. Determine reviewers:
   - If `$ARGUMENTS` is non-empty, pass it through to deep-review as the reviewer selection (explicit list or preset name).
   - If `$ARGUMENTS` is empty, let deep-review auto-select based on the diff content.

4. Invoke the deep-review skill with the diff path and reviewer selection. Do not review the diff yourself in this session.

5. Return the merged findings from deep-review unchanged.

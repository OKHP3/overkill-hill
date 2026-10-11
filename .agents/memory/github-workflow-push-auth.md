---
name: GitHub workflow push authentication
description: The reliable Git transport and diagnosis for pushing workflow changes from this Repl.
---

When a GitHub push includes workflow files, the connected Replit GitHub OAuth identity may authenticate successfully but lack the `workflow` scope. Use the existing workflow-scoped `GITHUB_PAT` through GitHub's Basic `x-access-token` HTTP transport for the push; a Bearer header can be rejected as invalid Git credentials even when the PAT is valid.

For REST Git-Database API writes, successful blob creation does not prove tree or ref creation will work. Stop if tree creation fails; the accepted blobs are unreachable objects, not a branch or completed PR.

**Why:** The repository's Git remote can select the connected OAuth credential by default, while the workspace PAT is a separate credential. GitHub's smart HTTP Git endpoint accepted the same PAT only when supplied using the standard Basic token form. On 2026-10-06, the connected GitHub App accepted five blob writes but returned 404 for tree creation against the same accessible repository and base tree; no branch or PR was created, and the cause was not confirmed.

**How to apply:** First fetch and audit divergence, then obtain the user's merge/rebase choice if histories diverge. Disable terminal prompts and use a bounded push command with the PAT without printing it. Never force-push. Verify local `HEAD` and `origin/main` match after the push. For API-based Git-object transfer, verify the whole tree/ref/PR path and stop before updating refs if tree creation fails.
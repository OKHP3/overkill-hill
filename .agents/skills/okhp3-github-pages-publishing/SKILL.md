---
name: okhp3-github-pages-publishing
description: >
  Publish a validated static release to GitHub Pages. Use when deploying a
  specific commit, checking Pages workflow permissions, verifying the live edge,
  handling cache fingerprints, or using a secure workflow-capable credential.
  Also activate for post-deploy smoke checks and incomplete deployment diagnosis.
  Do not use this skill to bypass validation or expose credentials.
license: MIT
compatibility: Git, GitHub Actions or an approved GitHub API client, and network access for live verification.
metadata:
  author: Jamie Hill (OverKill Hill P³)
  version: "1.0.0"
  category: deployment
  origin: okhp3/skillz
  homepage: https://overkillhill.com
  author-github: https://github.com/OKHP3
  in_scope: "Commit-identity gates, GitHub Pages workflow deployment, secure credential boundaries, cache-aware edge verification, and reporting."
  out_of_scope: "Running unvalidated code, changing workflow security, storing credentials, or publishing companion repositories."
---

# okhp3-github-pages-publishing

**OverKill Hill P³** · [overkillhill.com](https://overkillhill.com) · [github.com/OKHP3](https://github.com/OKHP3)

## Scope

Deploy only after the site-release-validation gate has passed for the exact
commit. The normal path is a push to the repository’s protected `main` branch;
the workflow validates that commit before `deploy-pages` runs. Publishing is a
write and requires explicit authorization.

## Procedure

1. Capture repository, branch, full release SHA, working-tree status, and the
   validation report. Refuse to deploy if the tree differs from the validated
   commit, any required gate is `FAIL`, `BLOCKED`, or `NOT RUN`, or the report
   is for another SHA.
2. Inspect the workflow before using it. The OverKill Hill adapter requires
   validation as `needs` for deploy, checkout of the validated commit, Pages
   `pages: write` and OIDC `id-token: write`, `contents: read`, and serialized
   Pages concurrency. Never run untrusted pull-request code with write
   permissions. Fork validation must use trusted checker code and read-only
   permissions.
3. Deploy through the normal workflow by pushing the reviewed commit to `main`.
   Do not deploy a local working tree, force-push, rewrite remotes, or bypass a
   failed check. If the workflow is unavailable, stop and request authorization
   for the approved alternative rather than inventing a new deploy path.
4. For an explicitly authorized Replit API fallback, keep the fine-grained,
   workflow-capable credential in the workspace secret manager. Pass it through
   the process environment only; never put it in a file, Git remote, command
   transcript, URL, or chat. A credential without repository contents/workflow
   permission is a hard failure. Repair the secret’s provider permissions
   without asking the user to paste its value.
5. Verify the deployment run and live edge. Confirm the Pages deployment refers
   to the release SHA, then check representative HTML, headers, sitemap,
   generated index, and at least one cache-busted shared asset. Record status,
   final URL, response metadata, and retrieval time. Check both a normal route
   and a known noindex/utility boundary where applicable.
6. Treat cache fingerprints as content identity. A changed CSS/JS byte must
   produce the expected fingerprint; stale HTML references are a release
   failure. HTML and search data should remain revalidating, while immutable
   caching is appropriate only for correctly fingerprinted assets.
7. Report `DEPLOYED`, `BLOCKED`, `FAILED`, or `PARTIAL` with commit identity,
   workflow/deployment IDs, edge checks, cache observations, credential scope
   (never its value), and remaining limitations. An incomplete post-deploy
   verification is `PARTIAL`, not success.

## Host adapters

**This repository:** `.github/workflows/validate.yml` gates `deploy` on
`validate`, checks out the validated push, uploads `.` as the Pages artifact,
and uses `actions/deploy-pages`. `docs/publishing.md` describes the only
approved API fallback, `GITHUB_PAT` in workspace secrets plus
`GITHUB_TOKEN="$GITHUB_PAT" python3 scripts/push-to-github.py`; that helper is
limited to its explicit governance-file map and must not be generalized.

**Other GitHub Pages repositories:** substitute the repository’s actual
workflow, artifact path, custom domain, and route inventory. Confirm permissions
and SHA binding in that workflow. Never assume OverKill Hill paths or headers.

**Companion sites:** compare deployment mechanics only. Do not modify or publish
Glee-fully or AskJamie from this package, and do not transfer OverKill Hill
visual or content rules to them.

## References

- `references/publish-gate.md` — commit, permission, trust, and edge rules.
- `references/regression-cases.md` — deployment failure and safety cases.
- `evals/evals.json` — three narrow fixture cases; benchmark.json records limited evidence only and makes no broader publishing-reliability claim.
- `scripts/verify-release-commit.py` — read-only local SHA/tree gate.

## About

Built by [Jamie Hill](https://overkillhill.com) · [OverKill Hill P³](https://overkillhill.com)
Published at [github.com/OKHP3](https://github.com/OKHP3)
Part of the [OKHP3/skillz](https://github.com/OKHP3/skillz) Agent Skill library.
MIT License -- free to use, fork, and adapt. A nod to the source is appreciated.
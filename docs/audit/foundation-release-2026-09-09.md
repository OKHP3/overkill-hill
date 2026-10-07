# Shared foundation release — 2026-09-09

## Decision

The reviewed compatible superset was selected from an explicit immutable source
revision, not from commit timestamps or whichever checkout happened to be newer.
The final source revision is:

- `overkill-hill@9e0c2f80ed33a53b61cde9a59a33f87a86bc33a0`

The release was applied with `scripts/sync-foundation-files.py` only after the
read-only audit had confirmed the three-site foundation contract. The release
also preserves the stable shared search-index URL required by the cross-site
browser fixtures. Glee's cache-buster now versions HTML and service-worker
references without rewriting the shared `app.js` runtime.

## Published commits

| Site | Foundation sync commit | Final published commit | Publication |
| --- | --- | --- | --- |
| OKH | `062e09659edf02b715b99aaf2dc7f73a675fee58` | `062e09659edf02b715b99aaf2dc7f73a675fee58` | `main` |
| Glee | `7c19339a6c0ea47d774e9f6807f65b7a5f118d39` | `4b249b5c8ec63f9d15c372524253053f6f602cbf` | `agent/foundation-sync-20260909`, PR #42 |
| AskJamie | `7e1bc496c0ea47d774e9f6807f65b7a5f118d398` | `7e1bc496c0ea47d774e9f6807f65b7a5f118d398` | `main` |

Glee's final commits include the generated cache-buster refresh after the
foundation write and the aligned compatibility fixture. The Glee-specific
cache-buster boundary change is in
`92842622e04bf38435dd17f74cef01200b7f2690`; the generated refresh is
`ad86b8b9a92f9a3249585d1f0ce293b1758d2824`.

At the time of this audit, Glee `main` was protected at
`d6f3319100bc9bd923f3ef93f1ca8e58`; the reviewed release was published on the PR
branch:

<https://github.com/OKHP3/Glee-fullyTools/pull/42>

## Current Glee PR #42 status (checked 2026-10-06)

The PR is now closed and merged, so its former branch is not an active release
candidate:

- Current Glee `main` revision: `0aeeb5ab72582266ffcd0b5392a322b8a72e4ef4`.
- PR #42 head: `c9c197c54ad3aed0b992e352d67ed587097dc3a6`.
- PR #42 base at merge: `39744374e342924498bfac55e793f5635b6c63ab`.
- Merge commit: `9e4005d190d7dc07a04f124334f122ee91fc9f82`.
- Merged: 2026-09-16 18:56:11 UTC.
- The old branch compares as 217 commits behind current `main`; that is expected
  after a merged branch's base advances. GitHub reported all four PR review
  threads resolved at this check.

No rebase or update is required for the already-merged PR #42. For new
foundation work, start a fresh `agent/foundation-sync-*` branch from the current
Glee `main` revision, bring any open branch up to date, resolve conflicts,
rerun checks, and complete required review conversations. Merge only through
the protected Glee pull request. The read-only freshness job in
`.github/workflows/pages.yml` records the current base revision and required
action for open foundation-sync PRs; it does not update branches or merge them,
and it does not gate this repository's independent Pages deployment.

## Final foundation fingerprints

| File | SHA-256 | Bytes |
| --- | --- | ---: |
| `assets/css/theme.css` | `a95520942508a9116933df4bc56cbada5f844ea7e8064b693101af456264bf65` | 240135 |
| `assets/js/app.js` | `b938b2004dcba53a31b0d09dca65ff3e3b11b2f3db759587e293a338348aa8da` | 58009 |
| `assets/js/mermaid-init.js` | `19730e6371c9dc6845d94cd1a7b49c7c1796d131755676c8933e7d780ece4c7e` | 13537 |

The final `--json` audit reports `in-sync` for every file, with one fingerprint
group containing `overkill-hill`, `glee-fullytools`, and `askjamie` for each
asset.

## Validation evidence

- Read-only foundation inspection completed before the first propagation.
- Final `scripts/sync-foundation-files.py --json` audit: passed; all three
  assets are `in-sync`.
- `tests/test-sync-foundation-files.py`: 7 tests passed.
- Shared search/French interaction suite: 17 tests passed.
- Glee `scripts/sync-css-version.py --check`: passed.
- Glee `scripts/sync-portfolio-stats.py --check`: passed.
- Glee cache-buster unit tests and browser fixture tests: passed locally.
- Glee's final PR checks from `4b249b5c…` passed: site validation, translated
  page freshness, sparkle smoke, resilient web behavior, and responsive
  viewport QA. At the time of this audit, the PR remained open and was awaiting
  review through Glee's protected main branch.

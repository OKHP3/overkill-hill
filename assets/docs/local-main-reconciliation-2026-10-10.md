# Local Main Reconciliation

Date: October 10, 2026
Scope: preserved OverKill Hill local work, compared with current origin main at `de6a1a0f4f74f153cdae414a7f2eb24d26d2038b`.

## Publication decision

The owner authorized retrying reconciliation and pushing legitimate local changes to main. Two authored records were absent from the current tracked tree. They are preserved as historical documents:

- [August 29 static-site parity draft](../../docs/archive/static-site-parity-contract-2026-08-29.md), recovered from the untracked-file parent of stash `d1d85689d1fe8499f94b3dbdad6040f4ef77920d`.
- [September 5 R04 release handoff](../../docs/archive/r04-shared-foundation-handoff-2026-09-05.md), recovered from independent-clone commit `5d95183533d24032b870b6f1099752f7afe194c9`.

Neither document replaces current governance or production code. Their archival notices distinguish historical statements from current verification. Host-specific paths were replaced with portable repository or artifact labels. Original source bytes remain preserved locally.

## Confirmed source dispositions

| Local material | Direct comparison | Disposition |
| --- | --- | --- |
| Detached W06 baseline browser-test edits | Current main retains the keyboard, geometry, resize, theme, and no-JavaScript tests from this file, and adds computed-accessibility assertions and a negative control. The older local file removes those later checks. | Already superseded by current tests, including PRs #168 and #169. Preserve the detached checkout; do not replace current tests. |
| August 30 audit-script stash `ea250c89e7f6024ad7d9ebeea397a121be253798` | Current `scripts/audit-site.py` includes UTF-8 reading, `report_display_path`, and support for absolute report paths. Current CI has separate validation and Pages concurrency with regression tests. | Useful implementation already present. Preserve the stash rather than apply its older workflow. |
| Independent recovery clones at `cc0ab75e`, `5d951835`, and `c4330517` | Capture metadata records a full independent Git directory with tracked files reconstructable from HEAD. Each archive verification records matching source/archive bytes and unchanged refs before source removal. All current deletions are tracked files absent by that archival design; remaining untracked files are snapshot and integrity receipts. | Recovery storage, not thousands of intended production deletions. Preserve the clones and their receipts. Publish the missing authored R04 handoff separately. |
| Closeout commit `c433051777840a3890c3651d4feed3ee46f1ca84` | It is an ancestor of current origin main. GitHub PR #77 is merged with this reviewed head. | Already preserved on main. |
| August 23 live-edge and responsive-QA stashes `f8829e69`, `b157e48b`, `6ec5f6ea`, and `1399026e` | Stash inventories contain dated generated audit JSON and browser screenshots. | Retain as historical local evidence. Do not overwrite current reports or publish generated test-output directories. |

## Evidence limits and follow-up

This receipt does not certify every fleet branch, every local stash, all three computers, or Replit's Source Control connector. It does not resolve active technology-review issues or assert new live-site acceptance. No old runtime code, bulk deletions, or generated screenshot directories are part of this publication.

After the archive PR passes the repository's checks and merges, fast-forward only the clean primary main checkout and verify its commit against live GitHub main. Other preserved stashes and worktrees retain their original state for subsequent review.

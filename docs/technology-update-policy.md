# Technology update policy

This repository tracks upstream releases through reviewable updates. A newer
version is a candidate, not proof of compatibility. This policy covers the
OverKill Hill static site, its build and QA tools, and preserved media tooling.
Linked applications retain their own repositories and release processes.

## Implemented update paths

| Technology | Detection | How changes reach the solution |
| --- | --- | --- |
| npm direct dependencies and their lockfile | Daily Dependabot | Update manifest and lockfile in a PR; retain exact pins; pass Site Validation |
| Python QA dependencies | Daily Dependabot | Update `requirements-qa.txt` in a PR; clean environment and Site Validation |
| Audio-production requirements | Daily Dependabot in the nested source directory | Review a PR; preserve original requirements/delivery evidence; validate a separate reproduction environment and audition before accepting a new toolchain |
| GitHub Actions | Daily Dependabot | Review action release notes and SHA changes; validate workflows and release-artifact behavior |
| Node.js and bundled npm | Daily Technology Version Watch | Coordinate preferred `.nvmrc`/`.node-version` pins, supported package engine bounds, lock metadata, Replit module, stack checker, and README in one migration PR |
| Python runtime | Daily Technology Version Watch | Test a new stable release alongside the current CI version, then update all workflow selectors and supported Replit modules |
| Vendored Mermaid | Existing daily Mermaid Version Watch, also inventoried here | Review and replace the complete upstream bundle, VERSION and relevant docs; run diagram, CSP, link, accessibility and browser checks |
| Blender, FFmpeg, GarageBand | Daily publisher lookup; local version gaps remain visible | Upgrade the authoring workstation, preserve originals, and verify new render/export provenance separately |
| Transitive npm, Mermaid bundle and Python media dependencies | Full daily report | Upgrade the owning parent or refresh a compatible lockfile in a reviewed PR; never force every child to its independent latest major |
| Host libraries, browser binaries, standards and hosted services | Host updates plus quarterly owner review | Follow the host/package compatibility contract and regression checks described below |

Dependabot waits three days after a normal package release, groups minor/patch
updates within each ecosystem, and leaves major changes separate. Major updates
are not ignored. The Python media group is separate from site QA. Security
updates follow GitHub's security-update settings, which were not changed by
this work. See [GitHub's configuration reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference).

The new watcher runs daily at 15:23 UTC and on manual dispatch from the default
branch. It saves JSON, a complete Markdown inventory, and a shorter run summary.
Network failures fail the job and remain UNKNOWN; they cannot close an existing
tracking issue. Issue content stays unchanged when findings stay unchanged.
All release lookups share a ten-minute budget, including retries and supplemental
dependency discovery. Once it expires, pending lookups become UNKNOWN so reports
can be saved with time left for artifact upload and issue reporting.
The workflow has no repository-write, merge or deployment permission. PR runs
execute only the offline regression tests, without issue-write permissions.

## Activation and acceptance

These files are prepared locally. They become active after a reviewed PR lands
on the GitHub default branch. No personal access token, external bot installation,
or new application dependency is required; the scheduled job uses `github.token`.

1. Merge the tracking change through the existing protected-main process.
2. Run **Technology Version Watch** manually on `main`. Verify both jobs pass,
   the version artifact is downloadable, and one coordinated-maintenance issue
   records the runtime mismatch and missing media version evidence.
3. Inspect Dependabot's update logs for all four configured directories/ecosystems.
   Check that eligible package updates create PRs and that Site Validation runs
   on those PRs. A configured file alone does not prove successful operation.
4. Maintain the existing owner merge decision. Auto-merge was disabled when
   inspected. This change does not enable unattended merging. Compatible PRs
   must pass the checks; major and media changes need their additional review.
5. After each accepted update, verify the exact merged commit's Pages workflow
   and live-edge result. A package-version change is not evidence of deployment.

GitHub schedules may be delayed and public-repository schedules can be disabled
after 60 days without activity. Check workflow activity during the quarterly
review; use manual dispatch to verify a re-enabled watcher. This is ongoing
maintenance, not a guarantee of zero lag. See [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Initial upgrade sequence

1. **Reconcile Node first.** Candidate: Node 24.21.0 LTS and its bundled npm
   11.19.0, verified September 18, 2026. Node 26.9.0 is the latest Current
   release; npm 12.0.2 is independently latest. The production-tooling policy
   follows supported LTS, rather than installing npm's newest major independently.
   Update all Node declarations and the hardcoded constants in
   `scripts/check-stack-conformance.py` together. Confirm a supported Replit
   module exists and inspect the actual running version there.
2. **Update browser QA.** Candidate: Playwright 1.63.0 and Lighthouse 13.5.0.
   Regenerate the lockfile using the selected runtime, reinstall the browser
   bundle, and inspect all transitive changes. Run the existing site/browser
   gates. The installed local Playwright folder is not the lockfile baseline.
3. **Trial Python 3.14.7.** Start with a temporary CI matrix of 3.11 and 3.14.
   Confirm Beautiful Soup, Pillow, generators and all tests on the newer
   interpreter before making it primary. Current 3.11 patch: 3.11.16.
   Replit module availability is an independent check. Do not use the local
   3.14.0rc1 interpreter as evidence of stable-3.14 compatibility.
4. **Review Mermaid 12.0.0 as a major migration.** Preserve the 11.17.2 bundle
   for rollback in Git history. Download the publisher artifact, verify its
   integrity, retain license notices, replace the entire entry/chunk set and
   update VERSION. Review initializer/security behavior and all diagram types.
   Do not update sibling-project compatibility badges as if they were this
   site's runtime version. Shared initializer edits also require the existing
   cross-site foundation review.
5. **Reconcile authoring and hosts.** Record FFmpeg and GarageBand versions from
   the machines that produced the artifacts, trial Blender 5.2.2, and review
   Replit's supported replacement for `stable-25_05`. Keep immutable original
   media and its recorded reproduction requirements. If an audio dependency PR
   changes the reproduction recipe, preserve the old recipe and record the new
   output/toolchain separately before merging.
6. **Remove future pin conflicts deliberately.** The stack checker currently
   hardcodes dependency versions and unrelated cleanup rules. It is not called
   by Site Validation. In a focused follow-up, make its dependency checks verify
   exact pin/lock agreement against an approved manifest instead of stale
   literals. Until then, update its applicable constants in each upgrade PR;
   do not run its broad `--fix` mode as part of this update pipeline.

## Validation and rollback

### September 20 runtime maintenance

The preferred repository and CI pins now use Node 24.21.0 and bundled npm
11.19.0. Replit currently supplies Node 24.13.0 and npm 11.6.2 through its
`nodejs-24` module. Supported engine bounds are `>=24.13.0 <25` for Node and
`>=11.6.2 <12` for npm; engine enforcement remains enabled. The checker
verifies preferred pins separately from compatible manifest/lockfile bounds
and the Replit major. Verify each host's actual runtime separately. The
inventory still compares the preferred pin with the current LTS target and
does not report the managed Replit patch as verified latest.

The **Runtime compatibility** workflow trials Python 3.14.7 alongside the
current 3.11 line using the unchanged QA requirements, maintained Python
regression suites, and static release gates. Every active Python test entry
point in `validate.yml`, including the universe-map skill suite, runs under
both interpreters. `tests/test-runtime-coverage.py` fails if a newly added
validation suite is missing from the matrix. The matrix also checks generated
release packaging and MurderBird provenance. Browser checks, pinned cross-site
checkout verification, and live external/hosting probes retain their full
Site Validation workflow contract. This is a compatibility trial:
the primary release jobs and Replit remain on 3.11 until the candidate passes
hosted checks and Replit module availability is confirmed. The September 20
Replit module inventory has no Python 3.14 selector. The daily inventory
continues reporting the older Python selectors while that work remains.

Blender, FFmpeg, and GarageBand observations remain authoring-host work.
Repository CI cannot establish their installed versions or certify historical
media with a newer toolchain. Preserve UNKNOWN findings and original media
provenance until actual host inspection supplies the required evidence.

Every upgrade uses a clean install: `npm ci` and a fresh Python virtual
environment with `python -m pip install -r requirements-qa.txt`, followed by
`python -m pip check`. Run generated HTML/search/universe checks, structural,
SEO, locale, CSP, cache, link, release-boundary and performance-budget checks.
Use the full existing `.github/workflows/validate.yml` contract for responsive,
overflow, TOC, accessibility, theme, search, embedding and Mermaid behavior.
Reinstall Playwright's matching Chromium build before browser tests.

The Lighthouse 13.5.0 update coordinates the exact manifest and lockfile pin
with `NPM_REQUIRED` in `scripts/check-stack-conformance.py`. The runtime
alignment suite checks this declaration on both CI Python versions. Keep
these declarations together in future browser QA upgrades until the focused
manifest/lock agreement follow-up replaces the checker's version literals.

Python media updates additionally require import/dependency checks, rendering
into a new isolated directory, deterministic score/MIDI checks, output duration,
channels, sample rate, peak and loudness checks, plus listening review. Site
Validation alone does not certify audio or a native GarageBand project.

Keep the prior manifest, lock, vendor bytes and media provenance in Git history.
Rollback with a reviewed revert PR and the same release checks. Do not fix a
failed upgrade by weakening tests, force-pushing `main`, or overwriting a
historical rendered artifact.

## Quarterly coverage review

The owner reviews new manifests, external scripts/iframes, runner-image changes,
Replit modules/Nix channel, the 19 declared OS packages, and media-native
libraries. Record actual host package versions and provenance on each host.
For newly verified Blender, FFmpeg or GarageBand installations, the inventory
accepts an optional `config/technology-host-versions.json` object keyed by
`Blender`, `FFmpeg`, or `GarageBand (macOS)`. Each entry must include a numeric
`version`, an ISO `verified_at` date/time, and `evidence` identifying the saved
host check. Create this only after inspection; no values are prefilled from
upstream releases. This allows the watcher to compare current installations
without altering historical media verification records.
Do not equate a NixOS upstream release with a Replit-supported channel name.
Playwright owns its supported browser and helper binaries; update that bundle
through Playwright. A browser standards release does not require a package bump:
adopt needed features only after testing the site's supported browsers.

For unversioned Google Fonts, Analytics, GitHub Pages, Cloudflare, Replit, and
embedded sibling apps, retain availability/CSP/visual checks and coordinate
changes with the provider or owning repository. No fabricated semantic version
or package auto-updater can govern a hosted service's internal deployment.

## Reproduce the inventory

```bash
python3 scripts/technology-inventory.py --offline
python3 scripts/technology-inventory.py \
  --json-output assets/audit/technology-versions.json \
  --markdown-output assets/audit/technology-versions.md \
  --summary-output assets/audit/technology-summary.md
python3 tests/test-technology-inventory.py
node --test tests/technology-watch.test.mjs
```

On Windows, use `py -3 -X utf8` instead of `python3`. The script only reads
source files and public release metadata, then writes the selected report
paths. GitHub's public API has a low anonymous quota; a normal authenticated
`GH_TOKEN`/`GITHUB_TOKEN` can be supplied locally, while Actions supplies its
own token. Never commit a token. Reports under `assets/audit/` are ignored;
the workflow preserves them as downloadable artifacts for 30 days.

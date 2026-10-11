# R04 Shared Foundation Handoff

Archived October 10, 2026, from recovery-clone commit `5d95183533d24032b870b6f1099752f7afe194c9`. All release, check, version, and live-site statements below describe the September 5 release and have not been reverified as current conditions. This is a historical receipt, not a request to restore older source files. Original bytes remain in the independent recovery clone; the host-specific evidence path is replaced with its artifact name.

Date: 2026-09-05

## Status

R04 reconciles the shared CSS, application runtime, and Mermaid runtime across
OverKill Hill P3, Glee-fully Tools, and AskJamie while preserving each site's
brand-owned behavior. The final CSS and application source is frozen at
OverKill Hill commit `c2baf4f4427fe8dde4c575ad8c1ca4bb82e5aa1b`.

R04 is released on all three production sites. Each release used a normal,
guarded pull-request merge with its exact reviewed head; no administrative
bypass, force push, or direct push to `main` was used. Source branches and the
transport clones remain available as provenance records.

## Review Surfaces

| Site | Review branch or pull request | Immutable head | State |
|---|---|---|---|
| OverKill Hill P3 | [PR 11](https://github.com/OKHP3/OverKill-Hill/pull/11), then scoped [PR 13](https://github.com/OKHP3/OverKill-Hill/pull/13) | `630bb40b3e4a1d45e079051f5a5448b4add9a6db`; recovery `4a238f3c6e4913277a940b4acbdf1973880f42a3` | Merged as `c1b45ee21f57aa3902db012c7fbb427eb3d24332`, then `0ee6bc875a183ca2e065448d01fe97da62fc1ff7`; deployed and live-verified |
| Glee-fully Tools | [PR 19](https://github.com/OKHP3/Glee-fullyTools/pull/19) | `848447778684f0827b606555d1107a8cda61c2ec` | Merged as `f5689fe4852b72e5d584db9d8f87cac9121b87c4`; deployed and live-verified |
| AskJamie | [PR 10](https://github.com/OKHP3/AskJamie/pull/10) | `6c10e5ff35f7417d06af124037cf66c7497a44f3` | Merged as `e800d4aebf0dc2543c5ced295ec78d10ba192473`; deployed and live-verified |

The final R10 rendered-contrast evidence is stored outside the repositories at:

`r10-a39-final-composite-acceptance.md` (retained host-local evidence)

## Shared Source Provenance

The following committed Git blobs and raw-byte SHA-256 values are the canonical
R04 target. CSS and application blobs match on all three transport branches.
The Mermaid blob is the LF-normalized sibling blob adopted by the final
OverKill Hill integration candidate.

| Shared file | Git blob | Raw committed-byte SHA-256 |
|---|---|---|
| `assets/css/theme.css` | `dcab6c7e2e35c028949a22dbc2c70104d802fd1c` | `b60e5d8337d73b196f394bb861f3b4e509d29d7abd81d6f42bd69056ed42f11d` |
| `assets/js/app.js` | `5ddad63558afe6c5299313238204d09712aaf294` | `33c354b0b21eea42bfb5b855869d3808f54fe2272e4c0b4a3d0fbe46f73c9023` |
| `assets/js/mermaid-init.js` | `420effa94deb78302090e3369e45c1bc8d315dea` | `d0b6657726e69353ddb98fc19d4ae65763fd1fdd6b9887f7858729de85663dad` |

The transport source commit still records the semantically identical Mermaid
file as mixed line endings (`ea2c76d0f680320c66c725babc5d2bb7c5fe7892`).
Do not use its working-tree SHA-256 as convergence evidence. The release
integration normalizes only this OverKill Hill blob to the canonical sibling
blob above; no sibling code change is required.

The hardened synchronization workflow requires an explicit source repository
and full immutable source commit, refuses dirty or locked repositories, and
checks generated and hook-owned files before applying changes. Convergence must
be proven from committed Git blobs; working-tree hashes can mask line-ending
differences on Windows.

## Ownership Boundaries

### Shared foundation

- `assets/css/theme.css` owns the common design tokens and brand-scoped rules.
- `assets/js/app.js` owns common navigation, theme handling, search, and shared
  browser behavior.
- `assets/js/mermaid-init.js` owns the shared local Mermaid loader, strict-by-
  default security policy, idle and intersection-based rendering, and generated
  accessibility links.

### OverKill Hill P3

- Remains the authoritative R04 source for the three shared files.
- Generated cache fingerprints, CSP, and English and French search indexes are
  integration-owned outputs and must be regenerated after source adoption.
- The release integration candidate is owned by `codex/release-artifact-boundary`,
  not the transport branch itself.

### Glee-fully Tools

- `assets/js/glee-site-enhancements.js` owns Glee-only analytics consent,
  root-scope service-worker registration, external-frame fallback, Sparkle, and
  the Glee inline-search adapter.
- Validators and browser regression fixtures read the shared application file
  together with the Glee module; they do not require shared files to reclaim
  Glee-only behavior.
- Cache-busting and service-worker artifacts remain generated outputs.

### AskJamie

- `assets/js/askjamie-analytics.js` owns AskJamie analytics behavior.
- AskJamie remains brand-locked under ADR-0001. Its early bootstrap uses
  `askjamie-color-scheme` and `data-color-scheme`; it does not adopt the
  OverKill Hill `okh-theme` storage contract.
- The AskJamie CSP and affected HTML are generated or mechanically maintained
  outputs. The strengthened smoke test verifies computed light/dark rendering,
  reload persistence, and automatic-mode restoration.

## Verification Evidence

### OverKill Hill production release

- Pre-merge hosted Site Validation passed for final integration head
  `630bb40b3e4a1d45e079051f5a5448b4add9a6db`:
  <https://github.com/OKHP3/OverKill-Hill/actions/runs/33950607453/job/101264551062>
- Hosted i18n validation passed for the same final head:
  <https://github.com/OKHP3/OverKill-Hill/actions/runs/33950607461/job/101264533554>
- Structural, generated-source, cache, CSP, search-index, locale-link, sync
  safety, search, embed, overflow, accessibility, diagram, and contrast gates
  passed.
- The retained rendered R10 test passed at 6.64:1 in automatic dark mode and
  5.80:1 in explicit dark mode, both above the 4.5:1 acceptance threshold.
- The locale freshness checker now canonicalizes line endings and has regression
  coverage for LF/CRLF equivalence, real text changes, and meaningful-space
  changes. All four reviewed French routes passed; the eight German and Spanish
  findings remain intentional advisories.
- PR 11 merged as `c1b45ee21f57aa3902db012c7fbb427eb3d24332`.
  Artifact verification then detected that the publication package had omitted
  hidden `.nojekyll`. Scoped PR 13 corrected that single release-boundary issue
  and merged as final `main` commit
  `0ee6bc875a183ca2e065448d01fe97da62fc1ff7`.
- The final [Pages run](https://github.com/OKHP3/OverKill-Hill/actions/runs/33951232498)
  succeeded. Its exact-revision validation job passed every release gate, and
  the deploy job verified downloaded artifact provenance and the live edge.
  The standalone Site Validation run was cancelled by workflow concurrency;
  acceptance is bound to the successful reusable validation inside this Pages
  run for the same merge commit.
- The live release manifest reports commit
  `0ee6bc875a183ca2e065448d01fe97da62fc1ff7` and 302 files. Core routes and the
  public download return 200; governance, authoring source, scripts, tests,
  templates, and `package-lock.json` return 404. The Universe Mermaid diagram,
  BFS independent-prototype notice, and Mermaid Theme Builder installation
  content rendered as expected.

### Glee-fully Tools

- Local site validation passed with zero issues and zero warnings.
- Client regression tests, static resilience QA, CSS-version consistency, and
  strict accent-contrast checks passed. The strict contrast result reported
  zero advisories and zero hover failures.
- A focused local browser journey passed accented search, the correct first
  result, live announcements, list and listitem counts, preserved link role and
  destination, arrow navigation, Escape focus return, category controls, and
  dedicated-page results.
- Hosted site validation, i18n, Sparkle, Chromium/Firefox/WebKit resilience,
  all-page viewport QA, and inclusive-accessibility QA passed on draft PR 19.
- Final viewport and inclusive-accessibility evidence:
  <https://github.com/OKHP3/Glee-fullyTools/actions/runs/33949945879/job/101262695991>
- PR 19 merged as `f5689fe4852b72e5d584db9d8f87cac9121b87c4`.
  Main-branch production runs all completed successfully: [Site Validation](https://github.com/OKHP3/Glee-fullyTools/actions/runs/33950879636),
  [Sparkle](https://github.com/OKHP3/Glee-fullyTools/actions/runs/33950879590),
  [i18n](https://github.com/OKHP3/Glee-fullyTools/actions/runs/33950879635),
  [resilience](https://github.com/OKHP3/Glee-fullyTools/actions/runs/33950879642),
  [all-page viewport and inclusive QA](https://github.com/OKHP3/Glee-fullyTools/actions/runs/33950879607),
  and [Pages publication](https://github.com/OKHP3/Glee-fullyTools/actions/runs/33950879631).
- Live rendered acceptance passed: the site-specific enhancement module loaded;
  Today's Sparkle remained visible; the theme control switched from pinned
  light to pinned dark; accented `résumé` search announced eight results with
  real linked list items; the Ecosystem route loaded both runtime modules,
  rendered Mermaid SVG content, and reported zero console errors.

### AskJamie

- The JavaScript smoke suite passed Mermaid, search, and strengthened theme
  behavior checks against a local server.
- Privacy consent tests passed (`3 passed`).
- Site validation, CSP checks, and both hosted workflows passed on draft PR 10.
- Final hosted validation evidence:
  <https://github.com/OKHP3/AskJamie/actions/runs/33949948290/job/101262702621>
- The full local pytest run had only three already-documented Windows CRLF
  failures from direct execution of `scripts/post-merge.sh`; the hosted Linux
  suite passed. This is an existing platform limitation, not an R04 regression.
- PR 10 merged as `e800d4aebf0dc2543c5ced295ec78d10ba192473`.
  Main-branch [i18n](https://github.com/OKHP3/AskJamie/actions/runs/33950879874)
  and [Site Validation plus Pages deployment](https://github.com/OKHP3/AskJamie/actions/runs/33950879891)
  completed successfully.
- Live rendered acceptance passed: the AskJamie analytics module loaded; the
  theme control reached pinned dark with the expected computed dark heading
  color; `BrandGuard` search announced twelve results with linked list items;
  the Universe route loaded both runtime modules, rendered its Mermaid SVG, and
  reported zero console errors. The homepage retained its BFS feature and
  explicit independent-R&D disclosure.

### Final three-site live parity

Cache-bypassed production fetches returned status 200 and identical lengths and
SHA-256 values on `overkillhill.com`, `glee-fully.tools`, and `askjamie.bot`:

| Shared file | Bytes | Live SHA-256 on all three domains |
|---|---:|---|
| `assets/css/theme.css` | 230961 | `b60e5d8337d73b196f394bb861f3b4e509d29d7abd81d6f42bd69056ed42f11d` |
| `assets/js/app.js` | 44849 | `33c354b0b21eea42bfb5b855869d3808f54fe2272e4c0b4a3d0fbe46f73c9023` |
| `assets/js/mermaid-init.js` | 13298 | `d0b6657726e69353ddb98fc19d4ae65763fd1fdd6b9887f7858729de85663dad` |

These live hashes exactly match the committed canonical hashes in Shared Source
Provenance; R04 byte convergence is confirmed across all three public sites.

## Deferred and Excluded Work

- French reviewed adoption and its cross-platform freshness gate are complete
  on final integration head `630bb40b3e4a1d45e079051f5a5448b4add9a6db`.
- Expanded `en-GB` and `es-MX` search indexes remain P2 follow-on work. That
  implementation must preserve the complete BCP 47 tag before attempting a
  primary-subtag fallback.
- The known extensionless inactive workflow and CRLF maintenance risk remain
  outside R04 unless the owner authorizes a separate maintenance change.
- The Node 20-to-24 forced-runtime warning on some GitHub Actions is a future
  workflow-maintenance item, not a release failure.

## Reviewer Checklist

- Confirm the immutable reviewed heads, merge commits, production run URLs, and
  three shared SHA-256 values above.
- Keep each site's owned module outside the shared application file.
- Retain the source branches and transport clones as provenance; do not prune
  them as part of release cleanup.
- Treat `0ee6bc875a183ca2e065448d01fe97da62fc1ff7`,
  `f5689fe4852b72e5d584db9d8f87cac9121b87c4`, and
  `e800d4aebf0dc2543c5ced295ec78d10ba192473` as the released `main` revisions.

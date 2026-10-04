# OverKill Hill P³ maintenance scripts

This directory contains the scripts that are safe to use for the current
overkill-hill repository. The active scripts are the only scripts kept at
this level. Historical and manual tools are preserved in `scripts/archive/`
so they cannot be mistaken for current pipeline commands. Classification
follows the same convention as `askjamie/scripts/README.md`.

## Classification

| Script | Classification | Use |
| --- | --- | --- |
| `technology-inventory.py` | active | Read-only version inventory and publisher stable-release checks; JSON/Markdown reports for Technology Version Watch |
| `build-murderbird-hero.py` | active | Hash-locked proportional delivery for six accepted still sources |
| `build-murderbird-story-social.mjs` | active | Full-art story social raster with real fonts; local-only review HTML |
| `build-murderbird-site-assets.py` | active | Proportional PNG/WebP delivery copies of the corrected site-lineage images |
| `build-murderbird-brand-share.mjs` | active | Typeset 1200 × 630 generic v2 brand sharing card |
| `build-murderbird-release-register.py` | active | Derived accepted subset and built-release dependency checks |
| `murderbird-integration-qa.mjs` | active | Six-homepage and five-scene local browser checks; translation fallback receipt |
| `accessibility-qa.mjs` | active | Accessibility QA (`npm run test:*`) |
| `audit-site.py` | active | Site audit |
| `build-search-index.py` | active | Rebuild the generated search index |
| `build-site.py` | active | Regenerate HTML from `site-src/` sources |
| `generate-atom-feed.py` | active | Generate and freshness-check deterministic Atom XML from published English Article sources; packaged and SHA-bound in the GitHub Pages release |
| `generate-theme-controls.py` | active | Generate browser theme constants from the reviewed brand contract |
| `cache-bust.py` | active | Cache-busting query params |
| `strip-google-fonts-links.py` | active | Remove legacy font links from tracked pages and authoring inputs; excludes recovery copies |
| `check-banner.py` | active | Construction-banner consistency check (invoked by `validate-site.py`) |
| `check-csp.py` | active | CI guard against CSP drift |
| `csp-qa.mjs` | active | Route-wide browser CSP and runtime QA (`npm run test:csp`) |
| `check-links.py` | active | Internal/external link check |
| `check-locale-links.py` | active | Locale link check |
| `check-mtb-version.py` | active | MTB version consistency (invoked by `post-merge.sh` and `validate-site.py`) |
| `csp.py` | active | Canonical CSP policy generation module |
| `generate-csp.py` | active | Apply CSP policies to every page |
| `lint-voice.py` | active | Voice/style lint (invoked by `validate-site.py`) |
| `phone-overflow-qa.mjs` | active | Phone-viewport overflow QA (`npm run test:*`) |
| `toc-follow-qa.mjs` | active | All published sidebar menus: centered easing, footer clearance, keyboard reachability, breakpoint changes and reduced motion (`npm run test:toc`) |
| `check-performance-budget.py` | active | Deterministic first-party asset-weight regression guard for three representative routes |
| `measure-page-costs.mjs` | active | Manual cold/warm Chromium transfer experiment; gzip/cache fixture, live external costs, phone/desktop trials; writes `.local/a16/` |
| `build-etch-webp.py` | active | Lossless ETCH-AI-SKETCH WebP derivative with exact RGBA validation; retains original PNG |
| `check-etch-parity.mjs` | active | Phone/desktop light/dark image geometry and pixel comparison against PNG fallback; loopback preview required |
| `post-merge.sh` | active | Post-merge rebuild and validation hook |
| `responsive-qa.mjs` | active | Responsive QA entry point |
| `screen-reader-tree-audit.mjs` | active | Screen-reader accessibility tree audit (`npm run test:*`) |
| `sync-foundation-files.py` | active | Read-only audit/verification and explicit-revision sync of theme.css/app.js/mermaid-init.js across the three sibling repos |
| `test-check-banner.py` | active | Focused regression checks for localized construction-banner validation |
| `validate-site.py` | active | Structural site validation |
| `verify-live-edge.py` | active | Live-edge deployment verification |
| `write-actions-summary.py` | active | Compact Actions summaries from existing live-edge and external-runtime JSON; first-party failures remain distinct |

### Live-edge archive coverage

`python3 tests/test-actions-summary.py` defaults to clean-checkout compatibility
mode. If an ignored retained report is absent, the tracked fixture still checks
the registry contract, report shape, and renderer compatibility; that fixture-only
compatibility does not establish actual retained archive coverage. Whenever a
registered source is present, the test resolves both paths inside their permitted
directories and requires the source bytes to match the tracked fixture exactly.

For an operator audit that requires every registered source to be present, set
the repository Actions variable `OKHP3_STRICT_LIVE_EDGE_ARCHIVE_AUDIT` to `1`.
The main validation workflow passes this variable to the test. Strict mode fails
with the missing source path and remedy instead of falling back to a fixture.
Unset the variable or set it to `0` for fixture-only compatibility on clean
checkouts.

The following scripts are **reference-only**. They may still be useful for a
deliberately scoped maintenance or migration task, but they are not part of
the current validation or release pipeline: `apply-modern-baseline.py`,
`audit-assets.py`, `audit-meta-versions.py`, `check-accent-contrast.py`,
`cross-site-sync.py`, `enhance-pages.py`, `extract-templates.py`,
`fix-audit-2026-05-12.py`, `fix-image-performance.py`,
`fix-placeholder-gpt-links.py`, `generate-illustrations.py`,
`generate-templates.py`, `inject-gpt-icon-picture.py`,
`inject-keep-exploring.py`, `inject-sparkle-loader.py`,
`inject-toolette-hub.py`, `kebab-rename-images.py`, `modernize-pages.py`,
`move-orphans-to-library.py`, `normalize-head.py`, `picture-upgrade.py`,
`png-to-webp.py`, `reclassify-construction-banners.py`,
`remove-deprecated-meta.py`, `rename-img-kebab.py`, `reorg-theme-css.py`,
`responsive-audit.py`, `sync-portfolio-stats.py`, `update-card-srcsets.py`,
`update-image-refs.py`, and `update-placeholder-dimensions.py`.

The locale drift detector that owns the translation operating guide lives in
`.agents/skills/okhp3-i18n-page-sync/scripts/i18n-page-sync.py`. It is a
skill-owned helper, not a top-level pipeline script, and its current interface
is `--mode report`, `--mode check`, and `--mode adopt`.

The following scripts are **retired**. They are preserved for history only
and must not be run against overkill-hill: `activate-icons.py`,
`add-toolbox-to-footer.py`, `convert-gpt-icons-webp.py`,
`convert-hero-webp.py`, `fix-banner-text.py`, `generate-feed.py`,
`inject-breadcrumb.py`, `inject-color-scheme-init.py`,
`inject-hero-picture.py`, `inject-jsonld.py`, `inject-nav-logo-webp.py`,
`inject-showcase-footer.py`, `inject-showcase-subnav.py`,
`push-to-github.py`, `release-mtb.py`, `run-viewport-qa.py`,
`site-audit.py`, `viewport-qa.py`, and `wire-illustrations.py`.

`site-audit.py` is retired rather than reference-only specifically: it is a
different, superseded tool from the active `audit-site.py` (3.3% code
similarity between the two — not a variant, a different script with a
confusingly similar name), byte-identical to glee-fullytools' own retired
copy of the same file, and had zero references anywhere in this repo,
including its own governance docs, before this move.

All reference-only and retired scripts live in `scripts/archive/`. Read
their headers and review their target paths before adapting any of them.

## Provenance

This classification and the `scripts/archive/` convention were ported from
`askjamie/scripts/README.md` as part of the 2026-08-30 scripts/ unification
pass (see `docs/sxs-infrastructure-audit-2026-08-29.md`). AskJamie triaged
this same body of shared migration tooling first; this file reclassifies
overkill-hill's copies against that precedent plus a live repo-wide
reference check (CI workflows, `post-merge.sh`, `package.json`, and
cross-script `Path(__file__)`/`subprocess` calls).

## Foundation synchronization safety contract

`sync-foundation-files.py` is read-only unless `--apply` or `--commit` is
supplied. It does not infer a canonical copy from timestamps. A write requires
both `--source-repo` and an owner-reviewed, full 40-character
`--source-revision` commit SHA; content is read from that commit, never from a
working tree. It refuses all writes when any sibling repository has a Git lock,
staged/unstaged change, or untracked file. It never moves or removes a lock.

Use a dry run to inspect divergence, then only after R04 has produced the
reviewed compatible superset, use `--apply` or `--commit` with that exact
revision. Configured post-write generators run by default. Their changed paths
are reported as generated changes and included in a `--commit`; a generator
failure prevents every commit and leaves the written paths reported for manual,
reviewed recovery. `--no-hooks` is an explicit exceptional mode, not a default.

The browser-level theme synchronization check is opt-in because sibling
checkouts are not guaranteed to be mounted in every workspace. It reads each
configured checkout's actual `index.html`, `assets/css/theme.css`, and
`assets/js/app.js`, compares the foundation bytes, and reports the site and
revision for every drift:

```bash
THEME_CONTROL_SITES='[
  {"name":"OKH","root":"../overkill-hill","revision":"0ee6bc875a183ca2e065448d01fe97da62fc1ff7"},
  {"name":"Glee","root":"../glee-fullytools","revision":"f5689fe4852b72e5d584db9d8f87cac9121b87c4"},
  {"name":"AskJamie","root":"../askjamie","revision":"e800d4aebf0dc2543c5ced295ec78d10ba192473"}
]' npm run test:theme-controls
```

Each entry must include a reviewed full commit SHA as `revision` when the
cross-site mode is enabled. The test reads all three files from that immutable
revision instead of the working tree, and prints every site and revision before
the browser audit so a failed run preserves its exact evidence. The default
browser fixtures remain available when the sibling repositories are absent.

### Immutable cross-site verification

CI can verify an approved source revision and the exact commit pin used for each
remote sibling without selecting a checkout from timestamps or reading mutable
working-tree files:

```bash
python3 scripts/sync-foundation-files.py --verify \
  --source-repo overkill-hill \
  --source-revision APPROVED_SOURCE_SHA \
  --repo-path overkill-hill=. \
  --repo-path glee-fullytools=.ci/theme-sites/glee-fullytools \
  --repo-path askjamie=.ci/theme-sites/askjamie \
  --site-revision overkill-hill=OKH_PIN_SHA \
  --site-revision glee-fullytools=GLEE_PIN_SHA \
  --site-revision askjamie=ASKJAMIE_PIN_SHA
```

`--site-revision` is required for all three sites and must contain full
40-character commit SHAs. The verifier reads every asset with `git show` at its
pin, compares it with the approved source revision, and exits nonzero on drift.
Its JSON report includes the site, pinned revision, asset, expected fingerprint,
and actual fingerprint for every mismatch. `--verify` cannot be combined with
`--apply` or `--commit`, so it cannot rewrite sibling repositories.

### Universe map integration

`sync-universe-map.py` calls the installed `okhp3-universe-map` generator and
updates only the owned universe source block. `--check` verifies freshness.
The default search-index rebuild invokes it automatically, then rebuilds HTML.
`tests/test-universe-integration.py` checks source stability and search exclusion;
`tests/test-universe-browser.mjs` checks rendering and navigation.

## Shipped-page QA output

Functional phone, responsive, accessibility, and CSP loops consume
`release-qa-inventory.mjs`, which reads `build-release.py`'s `load_public_pages`
without generating a release. This includes shipped noindex drafts, review
pages, redirect notices, and utilities. The helper logs total/tested counts and
named exceptions; currently every shipped page is tested. Sitemap checks retain
their separate indexing scope. Representative keyboard tasks remain a focused
sample, not a full accessibility certification.

Responsive QA requires Playwright and Chromium by default. Missing execution
returns nonzero status and a `BLOCKED` report with browser acceptance `NOT RUN`.
Use `--static` only for explicit structural lint; it cannot satisfy browser
acceptance. `--report=<path>` selects the JSON output; the default is ignored
`test-results/responsive-qa/results.json`, with failure screenshots alongside it.
Reports include commit, environment, mode, inventory, and results. The static
site audit's existing `--report <path>` flag remains supported; its default is
now ignored `test-results/audit-site/report.md`. CI uploads both output folders.
Historical reports under `assets/docs/` are retained and are no longer overwritten.

# Site Maintenance Map

**Source baseline:** `origin/main` at `2317272cc285217f55b8718dd07fb7bd99986436`,
verified October 2, 2026. The initial map was prepared against `2f75120f` and
reconciled after PR #146 merged.

This map records current source ownership, automation, outputs, and verification
boundaries. It is not a deployment report or authorization to publish. For the
release procedure, see [`publishing.md`](publishing.md). For the active,
reference-only, and retired script inventory, see
[`scripts/README.md`](../scripts/README.md).

## Current publication and preview state

GitHub Pages is the only authorized publishing destination. The checked-in
`.replit` at this baseline has no deployment table. It defines the Free
development preview on port 5000 and the
`contrast` and `locale-links` checks.

PR #146 removed the configured Replit publication target while retaining
preview workflows and safeguards. `tests/test-replit-static-publication.py`
checks the preview-only configuration as well as the retained release wrapper's
accepted-revision and recovery behavior. Removing a configuration table does
not prove that an existing hosted deployment was deleted or that the platform's
Publish control cannot be used. Decline all Replit publishing offers.

Repository documentation identifies `main` as the protected release branch.
The `github-pages` environment and its permissions are visible in the
workflow, but required-reviewer and branch-rule settings are outside this
checkout and were not inspected. A workflow environment name is not proof of
native approval enforcement.

## Authoring-to-release flow

| Responsibility | Trigger and consumer | Output | Verification and status |
|---|---|---|---|
| English generated pages | Maintainers edit `site-src/pages.json` and the corresponding `site-src/pages/` sources. `scripts/build-site.py` first runs `scripts/generate-theme-controls.py`, then renders the manifest-listed pages; the Replit `postMerge` hook also invokes the generator. | Generated HTML in the repository and Article lastmod updates in `sitemap.xml`; URL inventory remains authored. Other standalone and locale HTML remains separately maintained unless listed in the source manifest. | `python3 scripts/build-site.py --check` checks theme-control and page output without writing. CI and `scripts/post-merge.sh` run it. A normal build mutates generated files. |
| Search index and universe map | After English content changes, `scripts/build-search-index.py` rebuilds the main search index. The normal build first builds the site, then writes the index, refreshes the universe authoring block through `scripts/sync-universe-map.py`, and rebuilds the site. | `assets/data/search-index.json`, the generated block in `site-src/pages/universe/index.main.html`, and rendered universe HTML. Locale indexes use the builder's `--locale=<tag>` option. | CI checks `python3 scripts/build-search-index.py --check` and `python3 scripts/sync-universe-map.py --check`. Both check modes avoid writes. |
| CSP policy and shared asset fingerprints | Maintainers change canonical CSP inputs or shared CSS/JavaScript, then run the matching generator. `scripts/post-merge.sh` runs the mutators; CI checks the committed result. | CSP policy data in `config/csp-policies.json`, `_headers`, generated page meta policies, and versioned shared-asset URLs in published pages and maintained HTML inputs. | `python3 scripts/generate-csp.py --check`, `python3 scripts/check-csp.py`, and `python3 scripts/cache-bust.py --check` are CI checks. The default generator modes write files. Browser CSP QA tests runtime behavior, not delivery of response headers by GitHub Pages. |
| Locale pages and freshness | Locale pages use the exact-pair translation skills declared in `i18n/sync.config.json`. CI runs the locale-link check and the published-locale freshness checker. | Locale HTML, sitemap and search-index consistency findings, plus a freshness report. | `python3 scripts/check-locale-links.py` is release-blocking for declared route, metadata, indexing, and index-freshness errors. `python3 scripts/check-i18n-release.py --mode check --format json` reports blocking versus advisory freshness; the checked-in `blocking_locales` list is empty, so this policy currently adds no blocking locale freshness items. The same file labels the approval requirement `ai-reviewed-accepted` and native certification optional. Those are repository policy values, not platform approval settings. Separately, CI runs `python3 scripts/check-regional-drafts.py` and `tests/test-locale-drafts.py`: the regional gate blocks stale canonical source hashes or featured-release markers and violations of en-GB/es-MX draft protections. Empty `blocking_locales` does not disable this gate. Locale quality and acceptance still need maintainer review. |
| Structural and link validation | CI runs `scripts/validate-site.py`, `scripts/audit-site.py --quiet`, and `scripts/check-links.py`, including its explicit `--external-archives` pass. The post-merge hook runs the site validator and internal-link check. | Findings in workflow output and validation reports. | These commands fail on their configured regressions and are part of the validation job that the Pages deploy job needs. `scripts/README.md` is the authority for whether a script is active, reference-only, or retired; “active” alone does not mean CI-gating. |
| Browser and accessibility regression checks | CI starts `server.py` locally for phone overflow, responsive, TOC, accessibility, and CSP browser checks. Separate steps run theme-control, search, and other browser regressions. `package.json` also exposes `npm run test:screen-reader`; it is not invoked by the current `validate.yml`. | Test results and selected QA artifacts under `test-results/` or workflow artifacts. | Failures in the commands called by `validate.yml` fail its validation job. These are automated regression checks, not WCAG certification, field usability evidence, or performance measurements from visitors. |
| Deterministic performance budget | CI runs `python3 scripts/check-performance-budget.py` against checked-in route and asset bytes. | Budget findings for homepage, article and Mermaid Theme Builder routes. | This static budget is release-blocking but does not measure imported-module graphs, external/dynamic requests, compression, browser timing, Lighthouse scores or field performance. |
| Local preview and CSP reports | Replit's `Start application` workflow and local development run `python3 server.py`; the configured preview listens on port 5000. | No-cache local preview. CSP reports are held in a temporary file for the server process and discarded when it closes. | `tests/test-preview-server.py` covers the serving and report-storage boundaries in CI. The preview is not a public release endpoint. |
| Public-page boundary and release package | The release workflow runs `tests/test-public-page-boundary.py` and `tests/test-release-package.py`, then `scripts/build-release.py --output site-release --commit <validated-sha>`. The shared policy is `scripts/public_page_boundary.py`. | An allowlisted `site-release/` tree and schema-3 `assets/audit/release-manifest.json` with the commit, inventory, hashes, and byte lengths. | Tests check shared page discovery and release exclusions. The builder rejects unsafe paths and links, validates pages against the shared boundary, and verifies packaged bytes. This is a release-blocking CI boundary. |
| Retained release wrapper | `scripts/build-replit-release.py` is retained but is not invoked by a `.replit` deployment command. It requires an accepted full SHA matching a clean checkout, builds and verifies privately, then promotes the staged output while preserving prior bytes in its private staging area. | `.local/site-release` plus private recovery material under `.local/` when explicitly run; not a Replit publishing authorization. | `tests/test-replit-static-publication.py` runs in CI and covers preview-only configuration, accepted-SHA and dirty-check rejection, symlink refusal, failure handling, and recovery. The wrapper regressions remain after PR #146. |
| Pages deployment and live verification | `.github/workflows/pages.yml` calls validation for the release SHA, downloads that workflow's named artifact, verifies it with `scripts/build-release.py --verify`, then uploads and deploys it to GitHub Pages. The Pages concurrency group queues deployments. | The GitHub Pages release and a `live-edge-report` artifact. | After deploy, `scripts/verify-live-edge.py` uses the deployment URL and expected SHA to check routes, release-manifest integrity, shared asset fingerprints, and observed response headers. A missing header can be a `WARN` under the documented direct-Pages mode; the report does not claim that GitHub Pages enforced it. |
| Scheduled operational monitoring | The validation workflow's `monitor-third-party-runtime` and `monitor-live-edge` jobs run on schedule or manual dispatch and retain reports. Their probe steps use `continue-on-error` and summarize evidence. | Third-party runtime and live-edge reports. | These are monitoring evidence, distinct from pull-request validation and the Pages release artifact. External availability can be `BLOCKED`; it is not a policy pass. |

## Privacy and release boundaries to preserve

- `server.py` defaults to `127.0.0.1:5000` and uses the release builder's public
  file inventory. It rejects traversal and noncanonical paths, hidden paths
  except the explicit `.well-known` root, symlinks and directory junctions, and
  directory listings. It sets no-cache headers.
- The preview's `/__csp-report` endpoint accepts bounded JSON reports,
  rejects transfer encoding, caps each report at 64 KiB and in-process storage
  at 1 MiB, and uses temporary rather than persistent report storage.
- `scripts/build-release.py` combines the source manifest, sitemap, explicit
  public-page discovery, and runtime-asset allowlist. It refuses hidden or
  linked release paths and honors the private-source archive exclusion policy.
  The preview server reuses this inventory instead of defining a second
  public-file list.
- Keep `tests/test-preview-server.py`, `tests/test-public-page-boundary.py`,
  `tests/test-release-package.py`, and
  `tests/test-replit-static-publication.py` in the validation inventory. They
  protect different boundaries and are not interchangeable.

## Review and evidence boundaries

- Page content, metadata, locale promotion, and publication changes need review
  by the maintainer. A generated file or successful local check is not approval
  to publish.
- Source/configuration expresses intended policy. Local preview verifies local
  behavior. Hosted CI verifies its checked-out revision. Artifact verification
  verifies packaged bytes. Deployment records the Pages action. Live-edge
  checks observe public responses. GitHub connector, PR, or task status is a
  separate evidence source and does not prove any of those results.
- A live response-header observation is not proof of response-header
  enforcement by the hosting edge. Browser accessibility tests do not establish
  WCAG certification, and automated QA does not establish field performance.
- `scripts/README.md` distinguishes active, reference-only, and retired
  maintenance tools. Reference-only and retired scripts live under
  `scripts/archive/`; they are not current pipeline steps. `scripts/post-merge.sh`
  is an active mutating hook, not a read-only validator.

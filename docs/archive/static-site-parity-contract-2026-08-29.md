# Static Site Parity Contract

Archived October 10, 2026, from preserved stash `d1d85689d1fe8499f94b3dbdad6040f4ef77920d` (untracked-file parent). This is an August 29 architecture draft, not an adopted policy or a current audit. Versions, counts, proposed targets, and acceptance steps below are historical. Follow current `AGENTS.md` and current site validation for active work. Original bytes remain in the stash; host-specific checkout paths in this copy are replaced with repository labels.

Status: local architecture draft. Read-only comparison completed 2026-08-29.

This document covers shared static-site mechanics only. It does not authorize
source, workflow, governance, or deployment changes.

## Evidence set

| Site | Local checkout | HEAD | Core file evidence |
|---|---|---|---|
| OverKill Hill | `overkill-hill` (historical detached checkout) | `759bf59f092056be16e90d1597ce3d33c93676dd` | `app.js` 31,943 bytes, `theme.css` 194,024 bytes, `mermaid-init.js` 11,999 bytes |
| Glee-fullyTools | `glee-fullytools` | `3c4e59c6a92aa237b83bb30757a9fda7b8c6c04a` | `app.js` 39,379 bytes, `theme.css` 183,391 bytes, `mermaid-init.js` 1,584 bytes |
| AskJamie | `askjamie` | `e97c2974b977e21cb3da08715bbf1177bf77d860` | `app.js` 37,757 bytes, `theme.css` 153,280 bytes, `mermaid-init.js` 2,842 bytes |

The three core files are present in all checkouts but have different SHA-256
content. Mermaid is vendored at version `11.17.2` with 106 tracked vendor files
in each checkout.

## Machine-checkable target contract

```yaml
contract_version: 1
architecture:
  deployment: static
  public_directory: "."
  local_port: 5000
  browser_script: classic-deferred
  shared_paths:
    stylesheet: assets/css/theme.css
    browser_runtime: assets/js/app.js
    mermaid_runtime: assets/js/mermaid-init.js
    search_index: assets/data/search-index.json
    manifest: site.webmanifest
  required_page_contract:
    exactly_one:
      - stylesheet_reference
      - browser_runtime_reference
      - manifest_reference
      - content_security_policy_meta
      - canonical_url
      - meta_description
      - theme_color
    browser_runtime:
      defer: true
      duplicate_references: false
    mermaid_runtime:
      module: true
      only_on_pages_with_diagrams: true
      vendored_version_matches_VERSION: true
      default_security: strict
      loose_security_requires: data-mermaid-security=loose
      render_is_idempotent: true
      lazy_render_allowed: true
  generated_integrity:
    search_index_check: required
    sitemap_matches_indexable_routes: required
    manifest_icons_resolve: required
    cache_bust_tokens_match_content: required_when_enabled
    csp_hashes_match_inline_sources: required
  release_integrity:
    validation_precedes_deployment: true
    deployed_artifact_is_validated_commit: true
    live_edge_probe: required_when_host_supports_it
    edge_headers_are_not_claimed_from__headers_alone: true
  brand_adapter:
    body_class: required
    design_tokens: site_specific
    fonts: site_specific
    analytics: explicit_consent_and_policy
    search_schema: adapter_or_versioned_contract
    hostname: site_specific
```

The YAML is a target contract, not a claim that the current three sites pass
every field.

## Exact comparison

### `assets/js/app.js`

All three runtimes contain the same broad feature families: reading progress,
navigation, header shadow, year stamps, header controls, theme behavior, scroll
reveal, smooth anchors, construction gating, sticky TOC behavior, and the
client-side search overlay/page.

Observed differences that must remain visible in any synchronization plan:

| Site | Current behavior | Contract implication |
|---|---|---|
| OverKill Hill | 765 lines. Adds Mermaid text alternatives and stronger mobile-nav accessibility. Uses `okh-theme`. HTML app references are not deferred. | Candidate reference for accessibility and Mermaid pre-processing, but its current loading behavior is not the target. |
| Glee-fullyTools | 919 lines. Adds `data-color-scheme` handling for Glee and AskJamie, offline service-worker registration, and sparkle loading. All 63 validator-page app references are deferred. | Candidate reference for deferred loading and offline/sparkle adapters. Service-worker behavior is Glee-specific. |
| AskJamie | 928 lines. Adds consent-gated GA4 and inquiry/GPT click events. `askjamie-main` pages currently use the OKH theme branch because the runtime checks `glee-main` only. Only 4 of 26 app references are deferred. | Analytics and consent remain AskJamie-specific. The theme-branch mismatch is a synchronization defect to fix deliberately, not to copy into siblings. |

Asset versioning also differs. OverKill Hill uses `theme.css?v=0a325877` and
`app.js?v=b36c89ac` in sampled pages. Glee-fullyTools uses
`theme.css?v=1b4bb2d6` and `app.js?v=3`. AskJamie has no query token on sampled
references. A future shared check must validate tokens per site, not require
one token value across sites.

### `assets/css/theme.css`

The files retain the intended layered shape: global tokens and components,
OverKill Hill defaults, `.glee-main` overrides, and `.askjamie-main` overrides.
They are not byte-parity artifacts.

Current section markers are approximately:

| Site | Global | Glee scope | AskJamie scope |
|---|---:|---:|---:|
| OverKill Hill | 20 | 5,221 | 6,027 |
| Glee-fullyTools | 20 | 4,456 | 5,678 |
| AskJamie | 22 | 4,423 | 5,229 |

The root token layer is shared in shape, including `--color-*`,
`--mermaid-*`, typography, spacing, radius, and transition tokens. Values and
scope behavior are adapters. For example, OverKill Hill currently carries
additional light-mode status/link tokens and a lightened gray value, while
Glee-fullyTools and AskJamie retain older root gray values. Glee-fullyTools
also has a dedicated warm-dark coverage section. Fonts, accents, dark-mode
policy, and Mermaid palette values must not be synchronized as universal
invariants.

### `assets/js/mermaid-init.js`

| Site | Lines | Current contract |
|---|---:|---|
| OverKill Hill | 286 | Vendored ESM import, strict by default, explicit loose opt-in, outbound click allowlist and sanitization, theme-color resolution, accessible alternatives, idempotent lazy rendering. |
| Glee-fullyTools | 48 | Vendored ESM import, global `securityLevel: loose`, idempotent rendering, viewport lazy rendering. |
| AskJamie | 85 | Same global loose setting, idempotent rendering, idle scheduling, viewport lazy rendering, post-render SVG link enhancement. |

The security posture is materially different. The future invariant should use
OverKill Hill's strict-default and allowlist boundary, then preserve any
site-specific link destinations through adapter data. Accessibility enhancement
should be a shared acceptance test. The exact theme palette remains CSS-owned.

### Scripts and lifecycle

Active scripts use lowercase kebab-case in all three checkouts. The lifecycle
hook is the required `scripts/post-merge.sh` path in every `.replit`, but its
responsibility is not equivalent:

| Site | Replit post-merge timeout | Current post-merge lifecycle |
|---|---:|---|
| OverKill Hill | 30,000 ms | Checks required files, checks MTB versions, rebuilds site HTML, regenerates CSP, checks generated HTML and CSP, then runs the validator as advisory for tracked backlog. |
| Glee-fullyTools | 30,000 ms | Checks required files, rebuilds search index, and syncs portfolio stats. |
| AskJamie | 60,000 ms | Reuses or starts a local server, runs responsive QA, and runs JavaScript smoke tests. |

OverKill Hill has 70 root `scripts/*` files in the tracked inventory, Glee has
69, and AskJamie has 14 active root scripts plus 44 archived scripts. This is
script-lifecycle divergence, not proof that one inventory should be copied to
the others. The target is a shared lifecycle order with site adapters:

1. Verify required entrypoints and generated inputs.
2. Run check-only generated-data and metadata checks.
3. Run structural and link validation.
4. Run browser checks appropriate to the site.
5. Produce a release artifact only after required checks pass.

### Workflows and release gates

All three repositories have a `validate.yml` workflow on pushes and pull
requests to `main`, and all three have a deployment job that depends on
validation. The gates are not equivalent:

| Site | Required or notable gates |
|---|---|
| OverKill Hill | Site validation, generated HTML, CSP, search index, locale links, cache-bust, audit, internal links, phone overflow, responsive QA, accessibility QA, contrast, release manifest, and live-edge verification. Also has a scheduled live-edge monitor and PR contrast reporter. |
| Glee-fullyTools | Workflow-action checks, search/index and portfolio/social synchronizers, CSP, unit tests, site/link validation, strict contrast, Glee dark coverage, viewport QA, Pages artifact validation, and public-header smoke. The advisory site audit and public-header smoke are explicitly non-blocking in parts of the Pages workflow. Separate sparkle and viewport workflows run. |
| AskJamie | Site/link validation, pytest, search-index check, responsive QA, JavaScript smoke, site audit, validated Pages artifact, and deployment. Separate scheduled hosted-JavaScript smoke and public GPT destination probes run. No equivalent deployment live-edge or public-header gate is present in `validate.yml`. |

Mitigation: define a required release gate matrix per site and make the
artifact, browser, accessibility, security, and live-edge evidence status
explicit. A green structural validator alone is not release acceptance.

### Metadata, search, favicon, and manifest behavior

The three sites consistently attempt to provide canonical URL, description,
theme color, CSP meta, manifest, favicon, and search-index metadata. Current
route and payload shapes are site-specific:

| Site | CNAME | Sitemap `<loc>` count | Search payload | Search count | Manifest identity |
|---|---|---:|---|---:|---|
| OverKill Hill | `overkillhill.com` | 30 | `site`, `generated`, `count`, `entries` | 159 | 6 icons, dark forge colors |
| Glee-fullyTools | `glee-fully.tools` | 60 | `generated_at`, `version`, `site`, `count`, `pages` | 60 | 7 icons, coral and cream |
| AskJamie | `askjamie.bot` | 24 | `generated`, `site`, `count`, `entries` | 24 | 2 icons, teal and paper |

The OverKill Hill search count is larger than its sitemap count because the
index includes deep-link section entries. It must not be compared as a page
count. Search builders also have different exclusion rules and field names.
Future synchronization must either preserve versioned adapters or migrate all
three payloads under an explicit compatibility plan.

Favicon paths differ. OverKill Hill has root `favicon.svg` and its favicon PNG
set under `assets/img/favicons`; Glee-fullyTools and AskJamie keep SVG masters
under `assets/img/favicons`. Manifest icon paths must be checked against the
site's actual files, not inferred from sibling layout.

### CSP and edge headers

All three repositories contain `_headers`, per-page CSP meta tags, a CSP policy
module, and a generator/check wrapper. All three also carry the same broad
baseline header names: MIME sniffing protection, frame policy, referrer policy,
permissions policy, HSTS, COOP, CORP, and Origin-Agent-Cluster.

The policies are adapters, not one shared string:

- OverKill Hill allows its vendored Mermaid CDN path, uses a report URI, and
  has site-specific image, frame, font, and Google service sources.
- Glee-fullyTools includes Google Analytics, Ko-fi, Google Fonts, and a broad
  image source policy. It has a public-header smoke script.
- AskJamie includes Google Tag Manager for consent-gated analytics and a
  narrower font policy. It has no equivalent public-header step in the Pages
  workflow.

The `_headers` files are source policy artifacts. GitHub Pages does not consume
them as edge configuration. Per-page CSP meta tags provide browser-level
policy evidence; actual response-header delivery requires a live host probe.
Do not claim delivered headers from `_headers` presence alone.

### Replit workflows

All three use static deployment with `publicDir = "."`, local port 5000, and
external port 80. The start commands differ:

| Site | Start command | Project workflow extras |
|---|---|---|
| OverKill Hill | `python3 server.py` | `contrast` and `locale-links` validation tasks run beside the app. |
| Glee-fullyTools | `python3 scripts/serve-site.py` | Starts only the application in the Project workflow. |
| AskJamie | `python3 -m http.server 5000 --bind 0.0.0.0` | Runs responsive QA and site audit beside the app. |

The common target is a no-cache server readiness check on port 5000 and an
explicit distinction between Replit workflow completion and browser-level or
live-host acceptance.

## Acceptance tests for future synchronization

Run these independently in each checkout after any shared-mechanics change.

1. Inventory every validator-in-scope HTML page. Assert exactly one
   `theme.css`, `app.js`, manifest, CSP meta, canonical, description, and
   theme-color reference. Assert every `app.js` tag is deferred and appears
   once, except an explicitly recorded legacy exception.
2. Assert each Mermaid page has one module loader, the loader resolves to the
   vendored artifact, and `assets/vendor/mermaid/VERSION` matches the tested
   artifact. Render one diagram with default security and one explicit loose
   allowlisted-link case. Confirm disallowed click targets are removed.
3. Assert Mermaid rendering is idempotent, lazy rendering does not duplicate
   nodes, generated SVG links have the required accessibility behavior, and a
   parse failure leaves a diagnosable console message without breaking the
   page shell.
4. Run the local site's check-only generators: search index, CSP, cache-bust
   or CSS token checks when enabled, and generated HTML checks when enabled.
5. Run the local site's structural validator and link/sitemap checker. Assert
   no missing or extra sitemap route, no unresolved manifest or favicon path,
   and no search payload count mismatch.
6. Recompute CSS scope checks. Global selectors must remain brand-neutral;
   brand declarations must be under the declared body-class adapter. Assert
   required global semantic and Mermaid token names exist without asserting
   brand-specific values.
7. Run the site's required browser checks at root, search, and at least one
   Mermaid page. Cover keyboard navigation, reduced motion, theme or color
   scheme behavior, search loading/error fallback, and console errors.
8. For AskJamie, test denied, granted, and previously granted analytics
   consent. Assert no GA request occurs before grant and event hooks remain
   no-ops when analytics is unavailable.
9. Build the Pages artifact from the exact validated commit. Confirm the
   deployed artifact contains the expected CNAME, sitemap, manifest, favicon,
   search index, and core scripts. Run a live-edge probe for response headers
   when the host exposes that capability.
10. Record commit SHA, core-file hashes, test commands, exit status, artifact
    identity, and live evidence status as `live`, `analytical`, `historical`,
    or `not-run`.

## Current mitigation priority

1. Establish a versioned contract and site adapter manifest before copying any
   shared file.
2. Repair the deferred-script and AskJamie theme-branch inconsistencies under
   their respective owners.
3. Adopt strict-default Mermaid security and shared accessibility assertions,
   preserving destination allowlists and palettes as adapters.
4. Align required release gates around validated artifacts and browser/live
   evidence. Keep advisory checks visibly advisory until they are made blocking.
5. Continue treating `_headers` as policy source rather than delivery proof.

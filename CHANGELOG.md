# Changelog

All notable changes to the **OverKill Hill P³™** public repository should be recorded here.

## 2026-11-13: MurderBird: Uncaged project page closeout

- Record the owner's v1.0 closeout on `/projects/murderbird-uncaged/`: complete
  as a study, V37 exhibit live, final character likeness parked and not claimed.
- Add a dated "Since September" account sourced from the exhibit repository's
  V37 release record and CG assessment closeout, plus a lead-model credit.
- Give the page its own share card: a byte-identical copy of the exhibit's
  published `og-image.png`, with a provenance record beside it.
- Refresh the status registry, structured data, sitemap date, search index,
  and the CSP hashes that follow from the changed JSON-LD.

## 2026-09-20: Skillz Forge address and Skillz Shield companion

- Move the existing Skillz Forge page to `/skillz-forge/`, preserving its
  content, catalog embed, and installation guide.
- Redirect `/projects/skillz/` to the new address, retaining bookmarked
  sections and query parameters when JavaScript is available.
- Add `/skillz-forge/skillz-shield/` with a shorter project overview, application
  embed, scanner scope, evidence limits, and integration links.
- Feature Forge and Shield as equal entries in the Our Projects menu and
  project shelf. Refresh search, sitemap, breadcrumbs, and universe navigation.
- Keep project-status and search checks working for projects outside
  `/projects/`, with regressions for navigation parity and legacy links.

## 2026-09-19: Replit task executor 1.2.0

- Preserve Replit planning and design while external agents own architecture,
  implementation, testing, and Git integration.
- Add finite task intake, revision-bound completion receipts, design acceptance,
  and a supported, authorized administrative return with concurrency guards.
- Record three analytical Foundry/Equilibrium review passes and visible
  development cases. Maturity remains draftable; native completion and cost
  savings are not established by these reviews.

## [Unreleased — 2026-09-03]

### Changed
- **CSP moved to enforcing mode** — the canonical generator now rejects
  Report-Only edge headers and missing/stale page policies. Regenerated
  `_headers`, `config/csp-policies.json`, and all 47 production page meta tags
  use `Content-Security-Policy`; the live route observation found and added the
  legitimate `okhp3.github.io` Skillz data endpoint to `connect-src`. See
  `docs/csp-enforcement-2026-09-03.md` for verification evidence and sibling
  site parity requirements.

## [Unreleased — 2026-09-04]

### Changed
- **Completed a bounded Notion-backed editorial pass** across `/writings/`,
  `/manifesto/`, and `/about/`. Corrected the `/writings/` featured-card
  release label from v1.0 to v0.5, confirmed the About voice and typo fixes
  already present, and left the proposed credentials grid pending owner
  sign-off. The review record is exported to
  `docs/editorial-review-2026-09-04.md`; no sibling-site files were changed.

## [Unreleased — 2026-05-04]

### Changed
- **Consolidated `assets/js/search.js` → `assets/js/app.js`** (Section 5). All search logic — overlay, dedicated `/search/` page, index loader, scoring engine, highlight/snippet rendering, keyboard shortcuts — now lives in a single JS file. Eliminates one HTTP request per page load across all 26 production pages.
- **Consolidated `assets/css/search.css` → `assets/css/theme.css`** (new OKH SEARCH section). All search styles — trigger button, overlay, panel, results, hint chips, `/search/` page — now live in a single stylesheet. Eliminates one render-blocking CSS request per page load. The runtime `ensureStyles()` fallback in `app.js` removed as redundant.

### Removed
- `assets/js/search.js` — deleted; content fully merged into `app.js`.
- `assets/css/search.css` — deleted; content fully merged into `theme.css`.
- `<script src="…/search.js">` tag stripped from all 26 live pages and all 16 source templates.
- `<link href="…/search.css">` tag stripped from all 26 live pages and all 16 source templates (42 files total).

---

## [v0.3 — 2026-04-21] — The First Diagram Is Usually a Liar: Visual Edition

### Added
- **v0.3 Visual Edition section** (`#visual-edition`) — deck-is-live framing, key quote pull-quote, What v0.3 Adds list, Public Scoring Bracket, and three-lane scoring model overview.
- **Poll Schedule table** (`#poll-schedule`) — seven-row schedule covering April 21 through post-close debrief (v0.3.1.1 through v0.3.3).
- **Scoring Model section** (`#scoring-model`) — three-lane grid: Audience Scoring, Architect Scoring (seven-point rubric), and Council-Assisted Scoring.
- **V1 First-Pass Diagram gallery** (`#v1-diagrams`) — seven diagram cards with quick-reads and confirmed Mermaid.ai live links for all seven models (Copilot, Claude, ChatGPT, Perplexity, Gemini, Notion, Replit).
- **V2 Revised Diagram gallery** (`#v2-diagrams`) — eight diagram cards including ChatGPT V2 Pro, with confirmed Mermaid.ai live links for all eight.
- **Deck download section** (`#v03-deck`) — Square and Wide formats each with PDF and PPTX links to the public GitHub repository.
- **v0.3 High-Resolution Field Guide section** (`#v03-field-guide`) — four heat guide cards linking to dedicated field guide pages.
- **Four new static heat guide pages** — `v03/v1-heat-a/`, `v03/v1-heat-b/`, `v03/v2-heat-a/`, `v03/v2-heat-b/` — each with poll question, competitor quick-reads, Mermaid.ai links, back-to-article navigation, and a separate Mermaid referral CTA.
- **v0.3 Field Guides sidebar widget** — fourth sidebar widget listing all four heat guide pages.
- **New CSS classes** — `.schedule-table`, `.scoring-lanes`/`.scoring-lane`, `.diagram-gallery`/`.diagram-grid`/`.diagram-card`, `.download-options`/`.download-format`, `.heat-guide-grid`/`.heat-guide-card`, `.heat-guide-hero`, `.heat-actions`, `.mermaid-cta` — all using OKH design tokens.

### Updated
- Article version throughout: `v0.2` → `v0.3` (eyebrow, subtitle, protoform notice, sidebar badge, meta tags, JSON-LD `dateModified`).
- Protoform notice: removed coming-soon language; updated to v0.3 Visual Edition Live summary.
- Article banner: Mermaid hook → Visual Edition hook, link target `#what-mermaid-actually-is` → `#visual-edition`.
- JSON-LD `dateModified`: `2026-04-16` → `2026-04-21`.
- CSS cache-bust: `?v=14` → `?v=15`.
- TOC sidebar: seven new entries added (Visual Edition, Poll Schedule, Scoring Model, V1 Diagrams, V2 Diagrams, v0.3 Deck, Field Guide).
- About This Article sidebar widget: updated to reference v0.3 additions.
- Site-wide announcement banner on 19 pages: `"Updated v0.2: …Plus: Mermaid.ai explained →"` → `"v0.3 Visual Edition: The First Diagram Is Usually a Liar →"`.
- Home page article card blurb updated to reference v0.3 Visual Edition and scoring bracket.
- Writings index article card blurb updated to reference v0.3 Visual Edition.

---

## [v0.2 — 2026-04-16] — The First Diagram Is Usually a Liar

### Added
- **"What a Mermaid Diagram Actually Is"** — new section (`#what-mermaid-actually-is`) establishing that Mermaid is a text syntax, not an AI format. Includes raw code example and the Notepad test.
- **"Mermaid the Syntax vs Mermaid.ai the Platform"** — new section (`#mermaid-syntax-vs-platform`) disambiguating the open-source JS library from the commercial AI product. Reframes the council comparison.
- **"The One That Should Have Won"** — new section (`#one-that-should-have-won`) covering Mermaid.ai's premature rendering failure and the Think Mode product recommendation.
- **Replit** added to the council scorecard in the article body (was already in sidebar).
- **LinkedIn Post v0.2** artifact card — Mermaid.ai, premature rendering, and the missing Think Mode.
- **LinkedIn Comment v0.2** artifact card — Mermaid syntax vs Mermaid.ai platform clarification.

### Updated
- Article version throughout: `v0.1` → `v0.2` (eyebrow, subtitle, protoform notice, sidebar badge, meta tags, JSON-LD schema description).
- Read time: `~12 min` → `~18 min`.
- JSON-LD `dateModified`: `2026-04-10` → `2026-04-16`.
- CSS cache-bust: `?v=9` → `?v=10`.
- TOC sidebar: three new entries added (What a Mermaid Diagram Is, Mermaid vs Mermaid.ai, The One That Should Have Won).
- About This Article sidebar widget: updated to reflect v0.2 additions.
- Site-wide announcement banner on 19 pages: `"New: …ROY, Mermaid, and a Council of AIs →"` → `"Updated v0.2: …Plus: Mermaid.ai explained →"`.
- Home page article card blurb updated to reference v0.2 content and Mermaid.ai.
- Writings index article card blurb updated to flag Mermaid.ai exclusion.

---

## [Unreleased]

### Added
- **Cross-repo foundation alignment** — re-established the original design intent that `assets/css/theme.css`, `assets/js/app.js`, and `assets/js/mermaid-init.js` ship byte-identically across `overkillhill.com`, `glee-fully.tools`, and `askjamie.bot`. New `SHARED UTILITIES` section in `theme.css` (margin scale `.mt-1/2/3/4/075` + AskJamie-style `.u-mt-sm/md/lg/xl` aliases + `.u-flex-center`, `.u-opacity-90`, `.img-fluid`, `.img-constrained`). Brand-neutral header on `mermaid-init.js`. Drop-in canonical files for both sibling repos staged at `dist/sync/` with full `MIGRATION.md`.
- **Internal search engine** — new `/search/` results page plus a sitewide `Ctrl/Cmd+K` (or `/`) overlay injected into the primary nav of every page via `assets/js/search.js`. Results highlight matched terms, support category filters, and link directly to article sections.
- **Per-section deep-link indexing** for `/writings/first-diagram-is-a-liar/` — 23 article sections now individually searchable (e.g. searching "ROY", "council", or "mermaid" returns specific in-article anchors, not just the parent page).
- `assets/scripts/build-search-index.py` — re-runnable Python script that walks all `*.html`, skips `noindex`, and produces `assets/search-index.json` (39 entries).
- `assets/css/search.css` — overlay + results-page styles using OKH design tokens.
- New artifact cards: **LinkedIn Post v0.3.2** and **LinkedIn Comment v0.3.2** in `#artifacts`.

### Updated
- **`sitemap.xml`** — rebuilt with all 18 indexable URLs (previously 8). Now includes the `/writings/` hub, both other writings, all four v03 field guides, the Mermaid Theme Builder project, and `/search/`.
- **`robots.txt`** — explicit allow opt-ins for GPTBot, ChatGPT-User, OAI-SearchBot, Google-Extended, ClaudeBot, anthropic-ai, PerplexityBot, CCBot, Applebot-Extended, Bytespider. Crawl-delay 10 for AhrefsBot and SemrushBot. `Disallow: /404.html` added.
- **`site.webmanifest`** — fixed (was previously empty `name`/`short_name` and pointed at non-existent root favicons). Now includes name, short name, description, scope, dark theme color #111827, and correct `/assets/img/favicons/` icon paths including 192/512 maskable variants.
- **JSON-LD `SearchAction`** on 18 pages — phantom `https://overkillhill.com/?s={search_term_string}` replaced with the real `https://overkillhill.com/search/?q={search_term_string}` pattern.

### Planned (deferred follow-up)
- BreadcrumbList JSON-LD on article + project + heat pages
- Sitewide Organization JSON-LD with `sameAs` social links
- `og:type=article` and `article:published_time` on writings pages
- Per-page landscape (1200×630) Open Graph images
- `prev`/`next` `rel` links across the four v03 field-guide pages
- "Recent Writings" home-page block surfacing magnus-saga and biases-as-constants

## [Unreleased — May 2026 forensic audit pass]

### Added (sixth backlog sweep — 2025/2026 modernization, 2026-05-03 late)
- **Modern security headers** (`_headers`):
  - `Cross-Origin-Opener-Policy: same-origin` (Spectre-class isolation, MDN 2024+ baseline)
  - `Cross-Origin-Resource-Policy: same-origin` site-wide, with `/assets/img/*` overridden to `cross-origin` so LinkedIn / Twitter share-card crawlers can still fetch `og:image`
  - `Origin-Agent-Cluster: ?1` for stronger Chromium process isolation
  - `Permissions-Policy` expanded from 4 to **27** directives — comprehensive 2026 deny-by-default surface
- **Speculation Rules API** (Chrome 121+) on all 26 pages — moderate-eagerness prefetch of internal links for instant navigation, with sensible exclusions (`rel=nofollow`, asset/PDF URLs)
- **Skip-link as first `<body>` child on all 26 pages** — WCAG 2.4.1 baseline; `.okh-skip-link` is visually hidden until focused, then slides in with brand colors and brand-orange focus ring
- **Comprehensive `prefers-reduced-motion` rule** in `theme.css` — disables ALL animations/transitions/scroll-behavior, plus targeted overrides for `.brand-stripes` and `.reveal-on-scroll`. WCAG 2.3.3 baseline
- **`<meta name="color-scheme" content="dark light">`** on every page (was on 3, now on 26) — proper UA dark/light hint
- **`<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>`** + **`<link rel="modulepreload">`** for mermaid ESM on all 6 diagram pages — eliminates render-blocking discovery for the mermaid module
- `assets/scripts/modernize_pages.py` — idempotent page modernizer with `--check`; wired into CI
- `assets/scripts/move_orphans_to_library.py` — orphan-asset detector + archiver with `--check`; wired into CI
- CI workflow now runs **5** validators (was 3) — modernization-drift and orphan-presence both gate merges

### Fixed (sixth sweep — caught by post-build code review)
- **Skip-link duplication**: pre-existing legacy `.skip-link` (hardcoded `#111827` colors, no brand identity) was on all 26 production pages. The new `.okh-skip-link` insertion left both in place — two consecutive "Skip to content" links would have shown to screen-reader users. Modernizer now detects the legacy form and either replaces it (first run) or removes the duplicate (re-run after the new one is already there). Legacy CSS rule deleted from `theme.css`.

### Changed (sixth sweep)
- **123 MB of orphan brand imagery archived** to `assets/img/library/` — live image tree shrank from 140 MB → 16 MB (-89%). All 98 unreferenced files preserved as a media kit (with `assets/img/library/README.md` documenting disposition options); production deploys won't carry the dead weight
- All 16 templates regenerated to pick up the new `<head>`/`<body>` hygiene
- Search index refreshed (no field deltas — body extractor strips `<script>`/`<nav>`/`<footer>`, so the new `speculationrules` script and skip-link don't bleed into search bodies)

### Added (fifth backlog sweep, 2026-05-03 late)
- `.gitignore` — covers Python `__pycache__`, `*.pyc`, editor cruft, OS junk, build dirs (none of this was being ignored before; first commit could have leaked `__pycache__` from the new scripts)
- `CONTRIBUTING.md`: added a "Validation before you commit" section with the three CI commands, so contributors know what gates merges
- `alt=` attributes on the 3 inline `<img>` tags inside Mermaid node strings on `writings/first-diagram-is-a-liar/v03/v2-heat-b/` (defensive — Mermaid may strip them, but they're correct in the source either way)

### Reported (action requires user decision — NOT executed)
- **125 MB of orphan brand imagery** detected in `assets/img/` — 53 PNGs + 49 WebP siblings totaling 124 MB across 103 files, none referenced by any HTML/CSS/JS/JSON/MD on disk. Breakdown: 94 MB wide-format hero/background variants, 28 MB square sentinel/avatar variants, 1 MB other. Did **not** delete (per AGENTS.md "Ask before large refactors") — operator should choose: (a) move to `assets/img/library/` archive subdir to retain as a media kit, or (b) delete to shrink deploy. Re-run detection: `python3 -c "..."` block in this audit pass.

### Added (fourth backlog sweep, 2026-05-03 evening)
- `_headers`: more-specific `/assets/search-index.json` rule with `max-age=300, must-revalidate` so the rebuilt index isn't trapped behind the 1-year `/assets/*` immutable cache (browsers will see search updates within 5 min, not 1 year)
- `extract_templates.py --check`: now exits non-zero on **any** template drift (not just conformance violations), aligning CI gating semantics with `validate_site.py` and `build_search_index.py --check`. Caught real drift on first run — 16 templates were stale because the third-pass `rel="author"` injection and `universe/` HMT label fix never reached the extracted templates
- Regenerated all 16 templates from current source pages
- `README.md`: added a CI section pointing at `.github/workflows/validate.yml`

### Fixed (fourth sweep)
- All 16 extracted templates were silently stale w.r.t. source pages (no diagnostic before this sweep)
- `assets/search-index.json` would have been trapped in 1-year immutable cache after every rebuild — defeats the purpose of CI re-running the index builder

### Added (third backlog sweep, 2026-05-03 PM)
- `assets/scripts/build_search_index.py` — refreshes `assets/search-index.json` against current HTML; preserves hand-curated anchor entries; supports `--check` for CI
- `.github/workflows/validate.yml` — CI workflow running `validate_site.py`, `extract_templates.py --check`, and `build_search_index.py --check` on every push / PR (closes "wire validators as a pre-commit hook or GitHub Action" from Recommended Next Pass)
- `<link rel="author" href="/humans.txt" />` on all 26 pages — gives `humans.txt` proper machine-discoverable provenance per the humanstxt.org convention
- 8 missing pages now indexed for site search: `/found-ry/`, `/prompt-forge/`, `/projects/abrahamic-reference-engine/`, `/projects/hometools/`, `/projects/pathscrib-r/`, `/projects/un-nocked-truth/`, `/writings/biases-as-constants/`, `/writings/magnus-saga/` (47 entries total, was 39)

### Fixed (third sweep)
- `universe/index.html` HomeTools sub-system labels: `HMT02/HMT03/HMT04` nodes were all displaying `"HMT01 — …"` (copy-paste typo); now show their correct codes
- `assets/search-index.json` was stale — home entry body still quoted the pre-soften "⚠ Active build zone" eyebrow; refreshed against current HTML, 42 field/entry changes

### Added
- `_headers` (Cloudflare/Netlify-style) — full security header set: HSTS preload, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, plus a real-deps-aware **Content-Security-Policy-Report-Only** (allows GA gtag, Google Fonts, jsdelivr Mermaid, and the 67 inline scripts the site actually uses)
- `assets/templates/` — 16 stripped layout templates derived from every unique page layout, with placeholder tokens, live nav/footer, root-relative asset paths, and a `README.md` index (see `assets/scripts/extract_templates.py`)
- `.well-known/security.txt` — RFC 9116 disclosure contact
- `humans.txt` — credit + stack file
- `llms.txt` — structured site map for LLM consumers (especially on-brand for a Promptcraft site)
- `assets/scripts/png_to_webp.py` — Pillow-based bulk converter (PNG ≥200 KB → WebP at q=82, method=6)
- `assets/scripts/picture_upgrade.py` — wraps `<img>` in `<picture>` with WebP source + PNG fallback
- `assets/scripts/cache_bust.py` — appends `?v=<sha256[:8]>` to local CSS/JS refs
- `assets/scripts/extract_templates.py` — BeautifulSoup template extractor with idempotent `--check` conformance asserts
- `width`/`height` attributes on every remaining `<img>` (CLS = 0)

### Changed
- Favicon redesign: brighter teal/copper raven on cream circular vignette, regenerated at every required size from a 1024 px source. Old 2.4 MB unreferenced `favicon.svg` removed (~3.6 MB net favicon savings)
- Theme color migrated to brand espresso `#2a2320` in `site.webmanifest` and the `theme-color` meta on all 26 pages
- Bulk PNG → WebP conversion: **123.9 MB → 11.4 MB (-91%)** across 55 images
- `assets/js/mermaid-init.js` rewritten to lazy-render via `IntersectionObserver` (rootMargin 400 px)
- Homepage eyebrow softened: ⚠ "Active build zone" → ⚙ "Forge in motion — actively iterated, not under construction"
- Standardized email to `contact@overkillhill.com` everywhere
- `robots.txt` now disallows `/assets/templates/` for every crawler group
- `sitemap.xml` lastmod bumped to 2026-05-03 across the board

### Fixed
- 404.html `@overkillhillp3` → `@OverKillHillP3` Twitter handle case
- under-construction.html missing `twitter:site` / `twitter:creator` added
- 4 images missing `width`/`height` causing potential CLS

### Deferred (intentional)
- Header/footer dedup (would introduce a build step — separate scoped task)
- Notion-backed editorial review (no agent access)
- CSP enforcement flip — completed 2026-09-03 after local route-wide
  verification; see `docs/csp-enforcement-2026-09-03.md`
- `git push` (operator action)
- Device QA for new favicon (operator action)

---

## [Current Public Baseline]

### Established
- Core brand README
- Public website source for overkillhill.com
- Writings section and related feature pages
- Public-facing companion pages for ecosystem properties including Glee-fully and AskJamie

### Notes
- This repository serves as the main public source for the OverKill Hill web presence and brand artifacts.

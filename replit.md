# OverKill Hill P³™ — overkillhill.com

## User preferences

- **Em dashes are rare, not banned.** Fine for breaking a heading/title into two parts (e.g. "Brand — Tagline"); everywhere else (body copy, meta descriptions, sentences), use commas, parentheses, or a period/new sentence instead. When in doubt, don't use one.
- **Conventional American English** spelling, grammar, and punctuation (the register taught in a US classroom to someone born in 1975, high school class of 1994). Avoid trendy/AI-sounding phrasing.
- Site positioning has moved on from "custom GPT" as the headline technology (that was the starting point ~14 months ago). Lead copy should foreground protocol-first AI systems design, local inference, multi-model coordination, and governance. References to custom GPTs are fine only when factually describing past work or an external product (e.g. Glee-fully) that is genuinely GPT-based.
- Keep the owner's current employer unnamed in public biography and credential copy. Describe the scale and nature of the experience without implying that the employer is connected to OverKill Hill P³™.

## Project Overview

MurderBird creative production and its interactive exhibit now belong to
`OKHP3/murderbird-uncaged`. Keep this project focused on the public brand,
portfolio, and stories. Preserve `/writings/murderbird/` and its required
delivery assets here; send new music, video, lyrics, model work, and creative
source iterations to the sibling project. See
`docs/murderbird-repository-boundary.md` for retained compatibility copies,
transfer evidence, and the separate private archive boundary.

Static portfolio/documentation site for OverKill Hill P³™ (overkillhill.com). English authoring sources live under `site-src/` and are rendered into the English published HTML tree by `scripts/build-site.py`. Locale HTML is updated using exact-pair translation Agent Skills; page-sync detects freshness and `scripts/check-locale-links.py` validates structure. The runtime is HTML, CSS, and vanilla JS. Coordinated with GitHub repo `OKHP3/OverKill-Hill` (website source) and `OKHP3/first-diagram-is-a-liar` (methodology archive).

## Server

Python simple HTTP server via `server.py` — serves the static site from root.

**Workflow:** `Start application` → `python3 server.py`

### Preview exposure boundary

Workstation preview defaults to `127.0.0.1:5000`. `HOST` and `PORT` are explicit
operator overrides. An external bind requires a separately reviewed exposure
path. The preview serves the release allowlist from its own checkout, rejects
source, hidden and linked paths, and disables directory listings. Restart after
adding public files so its startup inventory includes them.

CSP reports require a single positive Content-Length up to 64 KiB, reject transfer
encoding, and use a private temporary file capped at 1 MiB per process. Full
storage returns 507; restart clears it. Reports are deleted at shutdown and
`CSP_REPORT_FILE` is no longer used. This is a local diagnostic receiver, not a
persistent report service. Requests have a five-second socket inactivity timeout.

The checked-in `.replit` still declares `publicDir = "."`. No connected Replit
checkout or live exposure was verified for A18. External Replit publication
requires an allowlisted release directory or retirement of that route; the local
preview fix does not validate that separate publication path. These checks assume
a trusted local checkout, not concurrent malicious filesystem replacement.

## Architecture

- Root `/` — home page, site-wide assets
- `/assets/css/theme.css` — single global stylesheet (dark theme + OKH design tokens). **Organized in 4 sections in this order: GLOBAL → OKH → GLEE → ASKJAMIE.** See "CSS file structure" below.
- `/assets/js/app.js` — vanilla JS, sectioned `1. progress bar · 2. nav/year/theme/scroll-reveal/anchors · 3. GLEE construction overlay · 4. sticky TOC`
- `/assets/vendor/mermaid/` — self-hosted diagram runtime; its authoritative version is `assets/vendor/mermaid/VERSION`. See the README's Mermaid runtime trust decision for compatibility and update requirements. Mermaid Theme Builder's compatibility badge describes that separate project.
- `/assets/img/` — favicons, logos, OG images
- `/writings/` — article pages
- `/projects/` — project pages (`mermaid-theme-builder/`, `bpmn-for-mermaid/`)
- `/universe/`, `/manifesto/`, `/about/`, `/contact/`, `/legal/` — brand pages
- No `_replit/mermaid-theme-builder-preview/` directory exists in this checkout. The live Mermaid Theme Builder page is the generated static HTML at `projects/mermaid-theme-builder/index.html`.

## Key CSS Design Tokens (theme.css)

- `--okh-orange` — primary brand accent (#c46a2c or similar)
- `--okh-amber` — secondary accent (lighter warm tone)
- `--color-surface` — card/widget backgrounds
- `--color-border-subtle` — borders
- `--color-muted` — body/secondary text
- `--color-fg` — primary text
- `--radius-md` — card border-radius

**CSS cache-bust:** Currently at `?v=15`

## CSS file structure (theme.css)

`assets/css/theme.css` is **organized in 4 banner-separated sections in canonical order**:

1. **GLOBAL** — tokens, reset, base, shared utilities + components used by all 3 sites
2. **OVERKILL HILL** — site-specific (default brand). Scoped via `body:not(.glee-main):not(.askjamie-main)` OR uses OKH-only component classes (`.article-*`, `.heat-*`, `.diagram-*`, `.bfs-hero`, `.gpt-hero`, `.brand-stripes--okh`, etc.)
3. **GLEE-FULLY** — `.glee-main`-scoped overrides + `--glee` BEM modifiers
4. **ASKJAMIE** — `.askjamie-main`-scoped overrides + `--jamie` BEM modifiers

**Maintenance:** edit the canonical `assets/css/theme.css` within its GLOBAL,
OVERKILL HILL, GLEE-FULLY, or ASKJAMIE scope. Do not add a parallel stylesheet.
Run the active workflow checks after changes; generated HTML and search data
are verified with the commands below.

```
python3 scripts/build-site.py --check          # verify generated HTML is current
python3 scripts/build-search-index.py --check  # verify generated search data is current
```

Foundation synchronization remains a separate, owner-reviewed workflow. See
`scripts/README.md` before using `scripts/sync-foundation-files.py`.

## Current Feature: Article — The First Diagram Is Usually a Liar

Path: `/writings/first-diagram-is-a-liar/`

**Version:** v0.5 — The Council Scores the Field (2026-05-24)

### Article Sections
- `#visual-edition` — v0.3 Visual Edition overview (deck framing, scoring bracket, what v0.3 adds)
- `#poll-schedule` — 9-row poll schedule table (Apr 21 through v0.4)
- `#scoring-model` — 3-lane scoring grid (Audience / Architect / Council)
- `#pivot` — From Drawing to Modeling (intro)
- `#roy` — ROY: Return on Your Words
- `#what-mermaid-actually-is` — What a Mermaid diagram actually is
- `#mermaid-syntax-vs-platform` — Mermaid vs Mermaid.ai distinction
- `#one-that-should-have-won` — Mermaid.ai premature rendering analysis
- `#council-origin` — v0.4: Why I Built a Council of AIs (added Task #15)
- `#council` — Council of AIs (scorecard table + roles)
- `#why-one-model` — Why One Model Is Not Enough ← NEW in v0.4
- `#crude-manual-process` — The Crude Manual Process (fan out / compare / adjudicate / synthesize) ← NEW in v0.4
- `#co-opetition` — Co-opetition and What the Platforms Are Now Building ← NEW in v0.4
- `#council-seats` — Why Each Seat Existed ← NEW in v0.4
- `#council-synthesis` — What the Council Produced That a Single Model Could Not ← NEW in v0.4
- `#round1` — Round 1: Copilot
- `#round2` — Round 2: Claude
- `#prompts` — Prompts in the Wild
- `#v1-diagrams` — V1 First-Pass diagram gallery (7 cards, confirmed Mermaid.ai links)
- `#v2-diagrams` — V2 Revised diagram gallery (8 cards, confirmed Mermaid.ai links)
- `#v03-deck` — Download deck (Square + Wide, PDF + PPTX)
- `#v03-field-guide` — Heat guide cards (links to 4 static heat guide pages)
- `#council-scoring` — The Council Scores the Field ← NEW in v0.5
- `#model-interviews` — The Models Interview Themselves ← NEW in v0.5
- `#artifacts` — Launch Artifacts (LinkedIn artifact cards)
- `#thesis` — Thesis

### v0.3 Heat Guide Pages
- `/writings/first-diagram-is-a-liar/v03/v1-heat-a/` — ChatGPT, Claude, Gemini, Perplexity (V1)
- `/writings/first-diagram-is-a-liar/v03/v1-heat-b/` — Copilot, Notion, Replit (V1)
- `/writings/first-diagram-is-a-liar/v03/v2-heat-a/` — ChatGPT, Copilot, Gemini, Notion (V2)
- `/writings/first-diagram-is-a-liar/v03/v2-heat-b/` — ChatGPT Pro, Claude, Replit, Perplexity (V2)

All 15 confirmed Mermaid.ai diagram links are real (no placeholders). Poll URLs are TODO placeholders (not yet published on LinkedIn). v0.4 added ~700 words of new prose across 5 sections; v0.5 adds #council-scoring and #model-interviews. Refresh the generated search index after searchable content changes and verify it with `build-search-index.py --check`.

### Sidebar Widgets

1. **Start Now** — CTA button linking to the live GitHub Pages tool
2. **Project Info** — meta card: Status, Build Phase, License, Type, Cost, Maintained by, Mermaid.js compat (v11.16.0); GitHub links (View, Issues, Contribute)
3. **Related Resources** — live app (Compose tab), GitHub repo, BPMN for Mermaid, Mermaid.js theming docs, themeVariables reference, FDIAL article, all projects

## Site-Wide Banner
All 19 non-article pages + the article page itself have a site-wide "HOT OFF THE FORGE" banner.
- **Non-article pages (19):** Link to `/writings/first-diagram-is-a-liar/#council-scoring`, text: "v0.5 is live: the Council of AIs scored each other, every model was harder on itself than the architect was. Read it →"
- **Article page:** Links to `#council-scoring`, text: "v0.5 is live: the Council of AIs scored each other, every model was harder on itself than the architect was. Read it →"

**Canonical text lives in one place:** `scripts/check-banner.py` (top of file, `CANONICAL_BANNER`). To change the wording, update that constant and run:
```
python3 scripts/check-banner.py --update   # propagates to all HTML files
python3 scripts/check-banner.py            # verify (exits 1 on any mismatch)
```

**Automatic enforcement:** `scripts/check-banner.py` is called by `scripts/validate-site.py` as part of the standard site audit. Any banner mismatch causes the validation run to exit non-zero, the same way other checks do.

## Validation

The active validation contract is defined by `.github/workflows/validate.yml`.
It runs the structural validator, generated HTML and search-index checks, SEO
fixtures, project-status records, CSP and embedded-app checks, locale and link
checks, cache-bust checks, static audit, browser responsive/overflow and
accessibility QA, and contrast QA. Use `scripts/README.md` for the current
script classification; archived commands are not current workflow steps.

The Pages workflow in `.github/workflows/pages.yml` validates and deploys the
exact SHA-bound release artifact, then runs the read-only live-edge verifier.

## GitHub publication contract

GitHub `main` is the canonical release branch and is protected. Replit work
must follow this publication contract:

1. Work on a named branch. Never push directly to `origin/main`.
2. Batch related generated and static changes into one coherent commit.
3. Run the validation commands above before pushing the branch.
4. Push the branch once and open or update one pull request.
5. Never run per-file commit or push loops.
6. Stop on a rejected `main` push. Do not retry or force-push.

## Site Validation (CI)

The full validation harness runs automatically on every push and pull request to `main` via `.github/workflows/validate.yml`. Its structural validation command is:

```
python3 scripts/validate-site.py
```

This covers all checks in one shot: HTML structure (title, meta description, canonical, h1, JSON-LD), sitemap inclusion, broken internal links and assets, brand violations, MTB version consistency (`check-mtb-version.py`), and banner consistency (`check-banner.py`). The workflow also runs `python3 scripts/build-search-index.py --check`, which compares the generated payload in memory and fails if `assets/data/search-index.json` needs a refresh. The workflow exits non-zero on any error, which blocks merge on GitHub.

The workflow also runs `npm run test:phone-overflow` in Chromium at a 320px
viewport. It checks every page listed in `sitemap.xml` for page-level
horizontal overflow. The manifesto, Mac Studio, and First Diagram article
retain targeted assertions for table wrappers, reachable rightmost columns,
and diagram grids.

To run the same gate locally before pushing:

```
python3 scripts/validate-site.py
python3 scripts/build-search-index.py --check
```

## Mermaid Theme Builder Project Page

Path: `/projects/mermaid-theme-builder/`

**Current version:** v0.6.1 — shipped Aug 2026. Active sprint: v0.6.x Export & Workflow Polish.

**Live tool:** `okhp3.github.io/mermaid-theme-builder/` — browser-only, no login, MIT licensed.

### Page Sections

| Section ID | Heading | Notes |
|---|---|---|
| `#embed-tool` | *(embedded iframe)* | Live tool iframe at top of page; reload button included |
| `#release` | Current Release | v0.6.1 metadata card — version, active sprint, license, runtime, live tool link, source link |
| `#what-it-is` | A governance workbench, not a diagram editor | Is/Is-Not grid — two-column comparison of what the tool is and isn't |
| `#why-this-exists` | What you get here that you don't get from prompting an LLM | Why-grid — LLM prompting vs. MTB side-by-side |
| `#since-v03` | What changed between v0.3 and v0.5 | 7 change cards: Renderer Intelligence, Look API Support, Reference Capability Registry, SKILL.md Agent Packaging, Multi-Diagram Splitting, Shareable URL State, Vitest 4 Test Suite |
| `#features` | What the builder does | Feature card grid — 16 cards covering all major capabilities |
| `#roadmap` | Where the build is going | Progress track — 10 entries: V0.1–V0.4 Shipped ✓, v0.5.x SKILL.md Hardening Shipped ✓, v0.6.1 Export & Workflow Polish Shipped ✓, v0.6.x Export & Workflow Polish ▶ (active), v0.7.x Session Persistence + Multi-Diagram Canvas, v0.8.x Collaboration + Governance Hardening, v1.0 Production Release (planned) |
| *(no ID — collapsibles block)* | User Guide / Palette Reference / FAQ | Three collapsible `<details>` sections: 6-step User Guide, 21-row Palette Reference variable table, FAQ with 11 Q&A pairs |
| *(no ID — builder's note + dev update)* | *(closing)* | Builder's Note blockquote, Development Update (May 2026), BPMN for Mermaid sibling link, builder sign-off |

### Sidebar Widgets

1. **Start Now** — CTA button linking to the live GitHub Pages tool
2. **Project Info** — meta card: Status, Build Phase, License, Type, Cost, Maintained by, Mermaid.js compat (v11.16.0); GitHub links (View, Issues, Contribute)
3. **Related Resources** — live app (Compose tab), GitHub repo, BPMN for Mermaid, Mermaid.js theming docs, themeVariables reference, FDIAL article, all projects

### Live page

The static HTML at `projects/mermaid-theme-builder/index.html` is the live page. No nested React/Vite preview is present in this checkout.

### MTB release update procedure

The historical `release-mtb.py` helper is archived and is not a current
command. Use the active checker for a read-only version check:

```
python3 scripts/check-mtb-version.py
```

Inspect the archived helper's header before using it for a deliberately scoped
migration; do not treat its old release workflow as current repository
architecture.

**Active checker and optional auto-fixer:**

```
python3 scripts/check-mtb-version.py              # check only
python3 scripts/check-mtb-version.py --update     # backup + patch + re-verify
python3 scripts/check-mtb-version.py --update --prev-sprint v0.5.x
python3 scripts/check-mtb-version.py --dry-run    # preview fixes, no writes
```

The active checker supports these options, as verified with `--help` on
2026-09-07. Check mode and `--dry-run` do not write. `--update` backs up and
patches the files named in the checker; it is an optional mutator, not a
read-only validation command. Keep the English `site-src/` authoring inputs
aligned with any release change and verify `scripts/build-site.py --check`
afterward so regeneration cannot undo a direct HTML patch.

**Manual checklist: locations targeted by the active checker in update mode:**

| Location | What changes |
|---|---|
| Hero tag | `v{version} Shipped` |
| `#release` card `<h2>` | `v{version}: Shipped {Month YYYY}` |
| `#release` Version meta-val | `v{version}: shipped {Month YYYY}` |
| `#release` Active Sprint meta-val | `v{sprint} {sprint-name}` |
| `#roadmap` — `▶` marker + `Active` pill | Auto-promoted via `--prev-sprint`. Marker classes: `progress-marker--active` / `progress-marker--done`; pill classes: `phase-pill--active` / `phase-pill--shipped` |
| Sidebar · Status meta-val | `v{version} Shipped` |
| Sidebar · Build Phase meta-val | `v{sprint} {sprint-name}` |

In `--update` mode, the checker also targets the `**Current version:**` and active-sprint lines in this section; check mode never updates them. Review the release and roadmap table summaries after each release because they intentionally describe more than the structured values the checker manages.

## Internal Search Engine

Static, client-side search across the entire site. Consolidated 2026-05-03.

- `/search/` — dedicated results page (URL-shareable: `/search/?q=foo`). Body class `search-page` activates the JS page initializer.
- **All search logic lives in `assets/js/app.js` Section 5** (consolidated from the retired `assets/js/search.js`). Ctrl/Cmd+K or `/` opens overlay; Esc closes; ↑↓ navigate; ↵ follows.
- **All search CSS lives in `assets/css/theme.css`** under the `SECTION · OKH SEARCH` banner (consolidated from the retired `assets/css/search.css`).
- `assets/data/search-index.json` — generated index. `INDEX_URL` in `app.js` points to `/assets/data/search-index.json`.
- `scripts/build-search-index.py` — Python re-builder. Walks all `*.html`, skips `noindex`, extracts title + description + headings + body excerpt, plus per-section deep links for the FDIAL article. Re-run any time content changes:
  ```
  python3 scripts/build-search-index.py
  ```
  Verify the committed data without rewriting it:
  ```
  python3 scripts/build-search-index.py --check
  ```

### Adding deep-link entries for project page sections

The script **auto-detects** which sections to index on any `/projects/*/` page. No code changes are needed — just add `data-search-index` to the opening tag of any `content-block` div (or section/article) you want surfaced as an independent search result:

```html
<div class="content-block" id="my-section" data-search-index>
```

The attribute value is ignored; its presence is the signal. The script discovers all such elements across all project pages on every run. See `discover_sentinel_sections()` in the script for implementation details.

- Each page retains `SearchAction` JSON-LD for the site's own search route, `/search/?q={search_term_string}`. Google retired the sitelinks search box feature in November 2024; this markup no longer implies a Google searchbox.

### Cross-site search prompt

`docs/cross-site-search-prompt.md` — a self-contained prompt (780+ lines) for the Glee-fully.tools and AskJamie.bot Replit agents to implement functionally identical search on their sites. Covers: index builder adaptation, CORS setup, `app.js` tuning, CSS brand-color overrides, the `/search/` page template, and the peer-results feature (each site shows its own results first, then a secondary section of top results from the other two sibling sites with absolute cross-domain links).

## SEO / Metadata Status

The bullets and deferred list below preserve an earlier SEO checkpoint; they
are not the current inventory or an executable backlog. On 2026-09-07,
`scripts/check-links.py` verified 31 sitemap URLs, with `/search/` intentionally
excluded by noindex. Use that check and `scripts/test-seo-fixtures.py` to verify
current metadata before acting on any historical item below.

- `sitemap.xml` — rebuilt with all 18 indexable URLs (was 8). Includes writings hub, all writings, all 4 v03 field guides, projects hub, both indexable projects, and `/search/`.
- `robots.txt` — explicit opt-ins for GPTBot, ChatGPT-User, OAI-SearchBot, Google-Extended, ClaudeBot, anthropic-ai, PerplexityBot, CCBot, Applebot-Extended, Bytespider; crawl-delay for AhrefsBot/SemrushBot.
- `site.webmanifest` — fixed (was empty name + broken icon paths). Now: name "OverKill Hill P³™", short_name "OKHP³", correct favicon paths, dark theme color #111827.

### Historical deferred proposals (recheck before implementation)
- BreadcrumbList JSON-LD on article + project + heat pages
- Sitewide Organization JSON-LD with sameAs (LinkedIn/Fiverr/X/YouTube/Facebook/Ko-fi)
- `og:type=article` + `article:published_time` on writings pages (currently `website`)
- Per-page OG landscape images (most pages still use the 1024² sentinel; article uses a landscape image correctly)
- `prev`/`next` rel links on the four v03 field-guide pages
- "Recent Writings" surfacing block on the home page so magnus-saga and biases-as-constants aren't dropdown-only

## Cross-Site Foundation Files

`overkillhill.com`, `glee-fully.tools`, and `askjamie.bot` each live in their own GitHub Pages repo but share three foundation files that must stay byte-identical:

- `assets/css/theme.css`
- `assets/js/app.js`
- `assets/js/mermaid-init.js`

**As of 2026-09-02 this is a 3-way sync of one shared superset, not a one-directional "OKH is source of truth" push.** A change made in glee-fully.tools or askjamie.bot flows into overkill-hill, and a change made in overkill-hill flows out to both siblings. OverKill Hill is the *hub* the other two sync through, not a permanent single source of truth to hand-edit-then-broadcast. The compatibility decision is recorded in [`docs/adr/0001-shared-runtime-compatibility.md`](docs/adr/0001-shared-runtime-compatibility.md).

### Propagation workflow

Use this checkout's `scripts/sync-foundation-files.py`; its default mode audits
all three sibling checkouts without writing. Writes require an explicitly
selected source repository and its approved full 40-character commit SHA:

```bash
python3 scripts/sync-foundation-files.py
python3 scripts/sync-foundation-files.py --apply --source-repo overkill-hill --source-revision APPROVED_FULL_COMMIT_SHA
python3 scripts/sync-foundation-files.py --commit --source-repo overkill-hill --source-revision APPROVED_FULL_COMMIT_SHA
```

Replace `APPROVED_FULL_COMMIT_SHA` with the reviewed immutable revision.
`--source-repo` also accepts `glee-fullytools` or `askjamie`. The source bytes
come from that commit, not its working tree. The script never chooses a winner
from commit timestamps, file modification times, or the hub designation.
Inspect and reconcile differing legitimate work before choosing the source.

Before writing, the script refuses dirty, staged, or untracked sibling work
and Git locks; locks are reported, never removed. Missing sibling checkouts
produce configuration status 3. Configured post-write generators run by
default, and the report accounts for foundation and generated changes.
A failed generator prevents all commits. A later commit failure can leave
reported, recoverable writes; inspect the change account before continuing.
`--commit` includes only accounted paths and does not push any repository.

The three foundation files retain their byte-identical contract. Site-specific
behavior belongs in the shared superset through `.glee-main`,
`.askjamie-main`, `data-theme`, `data-color-scheme`, page data attributes, and
optional markup. The compatibility ADR above defines the runtime design.

### Site-specific divergence is expressed via class hooks, not separate files

The shared `theme.css` already scopes site-specific styling via class selectors on `<body>`:

- `.glee-main` — Glee-fully.tools pages
- `.askjamie-main` — AskJamie.bot pages
- `body:not(.glee-main):not(.askjamie-main)` — OverKill Hill pages

Add new site-specific styles inside one of those scopes — never as a parallel file.

### Theme switching mechanism (do not regress)

The shared `app.js` sets `data-theme` on the `<html>` element (`document.documentElement`), **not on `<body>`**. The matching CSS uses `html[data-theme="…"] body { … }`. If you ever see `body[data-theme="…"]` rules creeping in, those are dead code — the selector will never match.

## Skillz project routes

The Skillz Forge project page lives at `/skillz-forge/`; its shorter Skillz
Shield companion lives at `/skillz-forge/skillz-shield/`. Both appear as peer
entries in the Our Projects menu. `/projects/skillz/` is a noindex compatibility
redirect, preserving query parameters and fragments with JavaScript and using
a no-script refresh fallback. Author these pages under the matching
`site-src/pages/` paths and maintain their metadata in `site-src/pages.json`.
Project-status coverage includes both `projects/` and `skillz-forge/` sources;
manifest-declared redirects are excluded from detail inventory.

## Template Library

Path: `assets/templates/`

10 production-ready HTML templates following the `template--[slug].html` naming
convention. Index and full token reference: `assets/templates/index.md`.

| Template | Slug | Key Pages |
|----------|------|-----------|
| `template--homepage.html` | homepage | `index.html` |
| `template--interior-single.html` | interior-single | about, legal, manifesto, universe, prompt-forge |
| `template--interior-form.html` | interior-form | contact |
| `template--hub.html` | hub | projects/index, writings/index |
| `template--project-detail.html` | project-detail | all `/projects/*/`, found-ry, biases-as-constants, magnus-saga |
| `template--article.html` | article | writings/first-diagram-is-a-liar |
| `template--article-study.html` | article-study | v03/v1-heat-a, v1-heat-b, v2-heat-a, v2-heat-b |
| `template--utility.html` | utility | search |
| `template--error.html` | error | 404.html |
| `template--holding.html` | holding | under-construction.html |

**Validation exclusion:** `assets/templates/` is in `SKIP_DIRS` inside
`scripts/validate-site.py` so `[[token]]` placeholders don't cause false
positives during the site audit.

**Status:** Complete (2026-05-04). Post-audit fixes applied:
- `template--project-detail.html` — `robots` corrected from `noindex, nofollow` to the standard `index, follow` block (+ googlebot / bingbot / revisit-after), matching published project pages.
- `template--article-study.html` — About submenu fixed to canonical 4-item cluster (Universe / About / Contact / Legal); Contact and Legal were erroneously top-level nav items.

**Spec:** `assets/templates/index.md` is the current template inventory and token reference.

## Out of Scope for This Session
- LinkedIn poll URLs (not yet published; TODO comments in heat pages)
- GitHub Mermaid source `.mmd` file links (not yet verified)
- PNG thumbnail images for diagram cards
- glee-fully.tools and askjamie.bot (separate Replit projects)

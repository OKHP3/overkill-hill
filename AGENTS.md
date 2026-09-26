# Agent Guidelines: OverKill Hill P³

This file is the operating constitution for any AI agent working in this repo.
Read it before touching any file. It applies equally to Replit Agent, Copilot,
Claude, and any other AI assistant.

Cross-reference `replit.md` for site-specific architecture, script inventory,
and current audit state.

## Current Project Context

This section records the repository facts verified during the 2026-09-05
context-alignment pass. Update it when the project shape, entry points, or
validation workflow changes.

### Identity and scope

- Owner-directed MurderBird boundary (2026-09-26): `OKHP3/murderbird-uncaged`
  owns MurderBird creative production and the interactive application. Route
  new music, video, lyrics, model work, source images, and production sessions
  there. This website retains its published story, generated page shells,
  stable delivery assets, and the image/build fixtures still required by site
  checks. Retained source copies are compatibility snapshots, not a second
  production workbench. See `docs/murderbird-repository-boundary.md`.

- Confirmed: this is one Git repository for the OverKill Hill P³™ public static
  site and its public writings, project pages, and supporting artifacts.
- Confirmed: the production-facing site is generated static HTML, one shared
  CSS file, and browser JavaScript. English authoring sources live under
  `site-src/`; `scripts/build-site.py` renders the English published root and
  content pages. Locale HTML is updated using exact-pair translation Agent
  Skills; page-sync detects freshness and `scripts/check-locale-links.py`
  validates structure. The root
  `package.json` provides browser QA scripts and a Playwright dependency; there
  is no root application build system.
- Confirmed: no `_replit/mermaid-theme-builder-preview/` directory exists in
  this checkout. The live Mermaid Theme Builder project page is the static
  HTML under `projects/mermaid-theme-builder/`; do not treat this repository
  as a monorepo.

### Purpose and users

- Confirmed from `README.md` and the homepage: the site is a public portfolio
  and artifact archive for protocol-driven promptcraft, custom GPT
  architecture, AI systems design, and structured visual communication.
- Inferred: primary audiences are prospective collaborators or clients,
  readers of the site's writings, and visitors exploring related projects.
- Unknown: no separate owner brief or formal product requirements document is
  present in this checkout. Do not invent business goals, guarantees, or a
  roadmap beyond the published pages and project documents.

### Architecture and entry points

- `index.html` is the homepage and root of the published static tree.
- `skillz-forge/index.html` is the existing Skillz Forge project page, moved
  from `/projects/skillz/`, which remains a noindex redirect. Its companion
  page is `skillz-forge/skillz-shield/index.html`. Both are peer entries in the
  Our Projects menu, even though Shield has a nested URL.
- `server.py` provides the local no-cache preview server on port 5000.
- `assets/css/theme.css` is the canonical shared stylesheet for the OKH,
  GLEE, and ASKJAMIE brand scopes.
- `assets/js/app.js` provides shared browser interactions, including
  navigation, theme switching, scroll behavior, and site search.
  `mermaid-init.js` is used on pages that render Mermaid diagrams.
- `scripts/sync-universe-map.py` generates universe navigation from the search
  index using `.agents/skills/okhp3-universe-map/`. Default index writes refresh
  the universe source and published HTML; CI verifies rendering and freshness.
- `assets/data/search-index.json` is generated from indexable HTML by
  `scripts/build-search-index.py`; use its `--check` mode for freshness rather
  than relying on a hardcoded entry count.
- `scripts/` contains the active Python, shell, and Node QA tools listed in
  `scripts/README.md`; archived tools are not current pipeline commands.
- Deployment metadata points at a static directory. The public domain and
  hosting arrangement are documented in `README.md`, `CNAME`, and
  `.replit`.

### Validation status

- Confirmed: `scripts/validate-site.py` is the structural site gate; its
  production inventory is derived from the current HTML and sitemap boundaries,
  not a fixed count. It also runs the MTB version and banner checks.
- Confirmed: generated HTML is checked with `scripts/build-site.py --check`,
  and generated search data with `scripts/build-search-index.py --check`.
- Confirmed: the active workflow is `.github/workflows/validate.yml`; it also
  runs the project-status, SEO fixture, CSP, locale-link, cache-bust, audit,
  internal-link, browser, accessibility, embedded-app, and contrast gates.
  `.github/workflows/pages.yml` deploys only the validated SHA-bound release
  artifact.
- Confirmed: `scripts/check-links.py` distinguishes indexable sitemap pages
  from intentional noindex exclusions across localized draft pages, draft
  project routes, and utility or redirect boundaries. Use its current report
  rather than a hardcoded exclusion count.
- Open risk: `.github/workflows/sedMiHLjD` is tracked without a YAML extension
  and contains stale underscored script paths. GitHub Actions does not treat it
  as an active workflow. Do not delete or repair it without owner direction.
- Confirmed: `scripts/post-merge.sh` is an active rebuild and validation hook;
  its line-ending contract is recorded in `.gitattributes`.

### Guidance scope note

The static-site rules in Sections 0 through 8 apply here. The generic web-app
reference in Section 2B and the app-level Section 9 slot describe sibling
TypeScript/Vite repositories and do not describe this static site. Do not use
their `src/`, pnpm, Vite deployment, or app-governance requirements here.

- Work in small steps. Ask before large refactors.
- Prefer adding tests before changing logic if risk is medium/high.
- Keep changes localized. Avoid touching unrelated files.
- If you need config/secrets, stop and ask. Never invent credentials.
- Summarize what you changed and why at the end.

> **AGENTS.md sync circuit** -- This file is the Tier 0 constitutional authority
> for the OKHP3 repository ecosystem. Structural edits to universal governance
> sections must be propagated through the sync cycle before the session closes.
>
> **Tier 0 -- Golden master authority**
> - **OverKill Hill P³:** <https://github.com/OKHP3/OverKill-Hill/blob/main/AGENTS.md>
>
> **Tier 1 -- FoundRy relay repositories**
> These repos translate the golden master into brand/domain-specific child-repo
> scaffolds. They inherit the universal law, but may define relay-specific
> registries, templates, schemas, and Section 9 governance.
>
> - **OverKill Hill FoundRy:** <https://github.com/OKHP3/OverKill-Hill-FoundRy/blob/main/AGENTS.md>
> - **AskJamie FoundRy:** <https://github.com/OKHP3/AskJamie-FoundRy/blob/main/AGENTS.md>
> - **Glee-fully Tools FoundRy:** <https://github.com/OKHP3/Glee-fullyTools-FoundRy/blob/main/AGENTS.md>
>
> **Tier 2 -- Public static site repositories**
> These repos share Sections 0-8 in full unless a site-specific override is
> explicitly documented. Section 2.2.1 and Section 9 remain repo-specific.
>
> - **AskJamie:** <https://github.com/OKHP3/AskJamie/blob/main/AGENTS.md>
> - **Glee-fully Tools:** <https://github.com/OKHP3/Glee-fullyTools/blob/main/AGENTS.md>
>
> **Tier 2 -- Web application repositories**
> These repos share the Sections 0-8 skeleton, but carry repo-specific Section 9
> implementation rules, build commands, and app-level governance.
>
> - **BPMN for Mermaid:** <https://github.com/OKHP3/mermaid-diagram-bpmn/blob/main/AGENTS.md>
> - **Mermaid Theme Builder:** <https://github.com/OKHP3/mermaid-theme-builder/blob/main/AGENTS.md>
>
> **Tier 2+ -- Child capability repositories**
> Capability repos inherit from their parent FoundRy relay. Their root
> `manifest.yaml` must identify `parent_foundry`, `brand_domain`,
> `governance.naming_pattern`, lifecycle status, and visibility controls.
>
> **Propagation rule:** When Sections 0-8 change in this file, update the three
> FoundRy relay repos first. Relay repos then govern downstream child repos
> through their `_template/`, `registry/`, `schemas/`, and `docs/` folders.
>
> **Override rule:** Section 2.2.1, Section 6 brand contract, and Section 9 may be
> repo-specific. Sections 0-5, 7, and 8 are universal unless this file explicitly
> defines an exception.
>
> When a child repo, web app, site repo, or relay AGENTS.md is silent or ambiguous
> on any governance matter, defer to this file as the resolution authority.

---

## Repository Hygiene Standard
**Brand:** OverKill Hill P³ (Forge / Rust-orange)
**Body scope class:** none -- this is the default brand; pages set no body class
**Canonical stylesheet:** https://raw.githubusercontent.com/OKHP3/OverKill-Hill/main/assets/css/theme.css
**Version:** 3.2
**GitHub:** https://github.com/OKHP3/OverKill-Hill
**Notion Anchor:** https://app.notion.com/p/2cc812e0ced480389730dbd833839ae6
**Local path (Windows):** `C:\Users\jamie\OKH-Local\04_GitHub_Mirrors\overkill-hill`
**Local path (Mac):** `/Volumes/OKH-Local/04_GitHub_Mirrors/OverKill-Hill`

This section governs how files and folders are named, what structure all sibling
repos share, what counts as detritus, and the brand contract this repo serves.
It exists because AI agents, left alone, will name files inconsistently across
sessions, scatter working artifacts into the repo root, and leave paste-buffer
transcripts in `attached_assets/`. A reader two months later cannot tell what is
real, what is stale, and what was junk from the start. The rules below stop that.

---

### 0. Language Standard: en-US

This project is authored, owned, and maintained by a United States-based creator.
All user-facing content must use United States English (`en-US`).

**Scope:** UI copy, documentation, README content, release notes, comments intended
for human readers, prompts, tooltips, button text, error messages, validation
messages, QA/QC reports, marketing language, and any new code identifiers
authored in this repo.

**Examples of required US-EN spellings:** color, behavior, organization, optimize,
customize, center, analyze, modeling, artifact, visualization, standardization,
initialize, finalize, prioritize, summarize, license (noun), program, catalog,
fulfill, gray, toward, among, while.

**Protected exceptions (do NOT change spelling in):**
- Direct quotations from external sources
- Proper nouns, brand names, product names
- Dependency, package, or library names
- URLs, file names, route names
- API fields, schema keys, existing code identifiers
- Generated lockfiles or external standards

**Identifier rule:** en-US applies to identifiers authored in *new* code.
Renaming *existing* identifiers (variables, functions, types, exported symbols)
is a breaking change and falls under the same renaming policy as files in
Section 1: update every importer in the same commit, run the build and tests
after, and set up a redirect if anything external depends on the old name. Do
not run a blanket find-and-replace across existing identifiers without explicit
instruction.

**Status:** US English compliance is a required QA/QC gate, not a stylistic
preference. Any output failing this standard is a defect.

---

### 1. Naming conventions

#### 1.1 Default: lowercase with hyphens (kebab-case)

Every file and folder name defaults to lowercase letters and digits, with words
separated by single hyphens. Use this for documentation, configuration, assets,
data files, CSS, plain scripts, and folder names.

Examples that are correct:
- `site-tokens.css`
- `design-system.md`
- `brand-conformance-checklist.md`
- `sync-skills.sh`
- `assets/img/brand-sigil.svg`
- `assets/docs/release-plan.md`
- `scripts/build-search-index.py`

Examples that are wrong and must be renamed when discovered:
- `SiteTokens.css` (PascalCase used for a stylesheet)
- `designSystem.md` (camelCase)
- `BrandConformanceChecklist.md` (PascalCase used for a doc)
- `My Document.md` (spaces)

The convention does not change with file extension. A markdown doc and a YAML
workflow and an SVG asset all follow the same rule.

#### 1.2 The full convention by file role

The rule is "kebab-case by default" with three structural exceptions, all
dictated by ecosystem convention rather than preference. The table below is the
complete decision; deviations from it require an explicit reason.

| File role | Convention | Examples |
|---|---|---|
| Documentation (`.md`) | kebab-case | `design-system.md`, `release-plan.md` |
| Stylesheets (`.css`) | kebab-case | `theme.css`, `site-tokens.css` |
| YAML, JSON, TOML data and config | kebab-case | `sync-tokens.yml`, `palette-defaults.json` |
| Plain scripts (`.sh`, `.py`) | kebab-case | `sync-skills.sh`, `build-tokens.py` |
| Assets (SVG, PNG, WebP, etc.) | kebab-case | `brand-sigil.svg`, `og-cover.webp` |
| Folder names | kebab-case | `assets/img/`, `assets/docs/`, `scripts/` |
| Plain TypeScript modules (`.ts` not exporting a hook or component) | kebab-case | `theme-mode.ts`, `chat-store.ts` |
| React hooks (`.ts` exporting `useFoo`) | camelCase matching the hook | `useTheme.ts`, `useDebounce.ts` |
| React components (`.tsx`/`.jsx`) | PascalCase matching the component | `ChatPane.tsx`, `MessageList.tsx` |
| Root governance files | ALL CAPS (ecosystem convention) | `README.md`, `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `AGENTS.md`, `SKILL.md` |
| Tool-required filenames | Whatever the tool requires | `package.json`, `tsconfig.json`, `vite.config.ts`, `.gitignore`, `.replit`, `.npmrc`, `.prettierrc`, `Makefile`, `CNAME` |
| Web-standard files | Whatever the spec dictates | `humans.txt`, `robots.txt`, `llms.txt`, `404.html`, `_headers`, `favicon.ico`, `site.webmanifest` |

#### 1.3 The "why" behind the three structural exceptions

The three non-kebab cases (PascalCase components, camelCase hooks, ALL CAPS
governance) are not aesthetic choices. They are ecosystem signals.

- PascalCase `.tsx` matches the React component it exports, so the filename and
  the JSX tag read the same: `import Button from './Button'; <Button />`.
  Renaming it to kebab-case breaks tooling assumptions.
- camelCase `useTheme.ts` matches the hook function name. The convention is
  universal in the React ecosystem.
- ALL CAPS root files (LICENSE, README, etc.) trigger special rendering on
  GitHub and are recognized by virtually every tool that scans repos.
  Renaming them costs visibility.

Everything else is kebab-case because it is the most readable choice in URLs,
shell history, and `ls` output, and the broadly accepted default across modern
web ecosystems.

#### 1.4 Code identifiers are separate from filenames

These rules govern filenames and folder names only. Identifiers inside code
follow their language conventions: TypeScript uses `camelCase` for variables
and `PascalCase` for types; CSS custom properties use `--kebab-case`; Python
uses `snake_case`. Do not change identifiers when renaming files.

#### 1.5 Decision tree (when in doubt)

1. Is it a root governance file with a universally expected name (`README`,
   `LICENSE`, `CHANGELOG`, etc.)? Keep the ALL CAPS conventional name.
2. Is it a tool-required filename (`package.json`, `tsconfig.json`, dotfile,
   etc.)? Use whatever the tool requires.
3. Is it a `.tsx`/`.jsx` exporting a React component? Use PascalCase matching
   the component.
4. Is it a `.ts` exporting a React hook (`useFoo`)? Use camelCase matching the
   hook.
5. Otherwise: kebab-case.

#### 1.6 Renaming policy

Renaming a file changes import paths and deployed URLs. When fixing a casing
violation:
- Update every importer in the same change.
- If the file is referenced by a deployed URL, add a redirect or keep a stub
  at the old path until traffic clears.
- Never rename without running the build and tests after.

---

### 2. Sibling repo structural standard

Every OverKill Hill P3 static site repo shares this top-level structure.
Existing siblings converge toward it; deviations are permitted only when
site-specific content genuinely requires a different layout.

```
<repo-root>/
|-- .agents/               Replit Agent working memory (committed; canonical)
|   +-- skills/            agent skills consumed by this app
|-- .github/               GitHub Actions, issue templates
|-- .gitignore
|-- .replit
|-- .replitignore
|-- AGENTS.md              governance for AI agents working in this repo
|-- CHANGELOG.md
|-- CNAME                  GitHub Pages custom domain
|-- CODE_OF_CONDUCT.md
|-- CONTRIBUTING.md
|-- LICENSE
|-- README.md
|-- ROADMAP.md
|-- SECURITY.md
|-- about/                 /about/ page directory
|-- assets/
|   |-- audit/             machine-generated QA and test-run output (JSON, etc.)
|   |-- css/               stylesheets (theme.css is the canonical shared sheet)
|   |-- data/              JSON data files (search-index.json, etc.)
|   |-- docs/              human-authored documentation and audit artifacts
|   |-- downloads/         files offered for direct visitor download
|   |-- img/               brand assets and images (kebab-case filenames)
|   |   |-- favicons/      full favicon set
|   |   |-- library/       extended brand image library (variants, source assets)
|   |   +-- webp/          WebP conversions of PNG/JPG assets
|   |-- js/                JavaScript (app.js, mermaid-init.js, etc.)
|   +-- templates/         reusable HTML page-shell fragments (template-- prefix)
|-- docs/                  top-level GitHub-rendered project documentation
|   +-- archive/           archived and superseded documentation
|-- contact/               /contact/ page directory
|-- favicon.ico
|-- humans.txt
|-- index.html             site homepage
|-- legal/                 /legal/ page directory
|-- llms.txt               LLM crawler guidance
|-- replit.md              Replit-specific project notes (not for GitHub display)
|-- robots.txt
|-- scripts/               Python build, audit, and maintenance scripts
|-- search/                /search/ page directory
|-- site.webmanifest
|-- sitemap.xml
|-- under-construction.html
+-- universe/              /universe/ page directory
```
Each site also has its own unique content directories (e.g. `writings/`,
`projects/`, `found-ry/`, `manifesto/`, `prompt-forge/`, `vault/` for
OverKill Hill) that are not part of the shared standard. Do not remove content
directories that are unique to a site.

#### 2.1 Folders that must not exist at the repo root

These names are reserved for detritus (see Section 3) and must not be used
as legitimate folders: `_unused/`, `attached_assets/`, `attached-assets/`,
`_drafts/`, `_scratch/`, `_old/`, `tmp/`, `temp/`, `unused/`.

#### 2.2 Directory purposes and expected contents

The definitions below describe the purpose and expected contents of every
required shared folder. Use this as the placement guide when creating a new
file -- put it in the most specific folder that matches its type. Do not store
working artifacts here (see Section 3). Folders that are currently empty hold
a `.gitkeep` placeholder; remove it when the first real file is added.

---

**`assets/`**
Top-level container for all compiled, generated, and static front-end assets.
No files live directly in `assets/` itself. HTML pages live at the repo root
or in named content subdirectories. Tooling scripts belong in `scripts/`.

---

**`assets/audit/`**
Machine-generated QA and test-run JSON output worth keeping as a dated record.
Written automatically by the validator and QA scripts -- never hand-edited.

Expected file types and naming patterns:
- `validation-report-YYYY-MM-DD.json` -- `scripts/validate-site.py` output
- `links-report-YYYY-MM-DD.json` -- `scripts/check-links.py` output
- `asset-inventory-YYYY-MM-DD.json` -- `scripts/audit-assets.py` output
- `responsive-audit-YYYY-MM-DD.json` -- `scripts/responsive-audit.py` output
- `viewport-qa-YYYY-MM-DD.json` / `viewport-qa-full-YYYY-MM-DD.json` --
  `scripts/viewport-qa.py` / `scripts/run-viewport-qa.py` output
- `lighthouse-YYYY-MM-DD.json` -- Lighthouse CI output (if run)
- `accent-contrast-report.json` -- `scripts/check-accent-contrast.py` output
- `screenshots/` subdirectory -- retained visual-QA captures and Playwright failure captures (gitignored at root)
  - `screenshots/canvas/` -- retained captures from the former root `.canvas/` workspace

Human-authored audit reports belong in `assets/docs/`, not here.

---

**`assets/css/`**
Stylesheets only. One canonical file: `theme.css`. It is the shared stylesheet
that drives all three brand tiers (GLOBAL, OVERKILL, GLEE, ASKJAMIE) via
scoped selectors. The CSS Scope Map in `replit.md` documents which line ranges
belong to which scope.

- `theme.css` -- the only file that should normally live here
- `theme.css.bak-*` -- pre-reorg safety backups; delete after verifying the
  reorg succeeded (or gitignore them)

No JavaScript, no data files, no images. All filenames must be kebab-case.
Do not add component-level or page-specific CSS files -- extend `theme.css`.

---

**`assets/data/`**
Structured JSON (or YAML) data files consumed at runtime by front-end scripts
or at build time by maintenance scripts. All files here are auto-generated or
machine-maintained -- do not hand-edit files generated by a script.

Expected files:
- `search-index.json` -- rebuilt by `scripts/build-search-index.py`; powers
  the client-side search engine. Regenerate after any content change.
- `sparkle.json` -- single-source data for the "Today's Sparkle" banner;
  managed by `scripts/inject-sparkle-loader.py` (present on sites that use
  the Sparkle feature).
- `icon-map.json` -- mapping of page/tool slugs to image paths; rebuilt by
  `scripts/audit-assets.py` (present on sites with a tool/GPT icon set).

Audit output and documentation do not belong here.

---

**`assets/downloads/`**
Files offered for direct download by site visitors -- PDFs, ZIPs, exportable
templates, printable guides, prompt protocols. Keep this minimal and intentional.

Expected file types: `.pdf`, `.zip`, `.md` (printable reference docs), `.csv`.
Naming convention: kebab-case with a version slug or date where relevant, e.g.
`okh-prompt-protocol-v1.md`, `brand-guide-2026.pdf`.

Use `.gitkeep` when empty. Remove it when the first real file is added.
Internal tooling assets, scripts, and site images do not belong here.

---

**`assets/docs/`**
Human-authored project documentation: audit reports, design records, planning
artifacts, cross-site sync guides, and theme/style reference documents. All
files here are Markdown (`.md`). Not crawled -- excluded from the search
indexer, validators, and `sitemap.xml` by every HTML-walking script.

Expected naming patterns:
- `audit-topic-YYYY-MM-DD.md` or `AUDIT-TOPIC-YYYY-MM-DD.md` (historical)
- `LIVE_SITE_EVALUATION_YYYY-MM-DD.md` -- full evaluation reports
- `OPEN_TODOS_YYYY-MM-DD.md` -- deferred work and known placeholders
- `og-image-requirements.md`, `image-usage-report.md` -- standing reference docs
- `sister-site-sync.md` -- cross-site sync constant map and checklist
- Theme guides: `gleefully-replit-theme-guide.md`, etc.

May contain sub-folders for organizing related documents (e.g., `sister-site-sync/`
for cross-site coordination files). Machine-generated JSON output belongs in
`assets/audit/`, not here. Superseded docs move to `docs/archive/`.

---

**`assets/downloads/`**
*(See above.)*

---

**`assets/img/`**
All site images served directly to browsers via HTML or CSS. Filenames must be
kebab-case with descriptive slugs and dimension/variant suffixes, e.g.
`brand-hero-wide-1536.png`, `sentinel-waiting-square-1024.png`.

Expected file types: PNG (source), WebP (if not yet moved to `assets/img/webp/`).
For hero images, encode orientation and width in the name:
`<brand>-<subject>-<orientation>-<width>.<ext>`

Sub-folders permitted directly under `assets/img/`:
- `favicons/` -- the complete favicon set (see below)
- `library/` -- reusable brand library and source variants (see below)
- `webp/` -- WebP pipeline output (see below)
- `og/` -- Open Graph card images (AskJamie convention; add to siblings as needed)
- `brandguard/` -- AI/design reference brand assets (AskJamie convention)
- `tool-ettes/` -- per-tool-ette hero images (Glee-fully only)
- `toolbox/` -- toolbox hub images (Glee-fully only)

Do not place favicon files, WebP output, or library variants directly in
`assets/img/` -- use the appropriate sub-folder.

---

**`assets/img/favicons/`**
The complete favicon set for the site. Generated once; rarely changed.
Referenced via `<link rel="icon">` tags in every page `<head>`.

Required minimum set:
- `favicon-16x16.png`, `favicon-32x32.png`, `favicon-48x48.png`
- `android-chrome-192x192.png`, `android-chrome-512x512.png`
- `apple-touch-icon.png`
- `favicon.png` (full-resolution source master)
- `favicon.svg` (vector master, if available)
- `favicon.ico` (legacy; may live at repo root instead)

Do not store nav-bar logos or hero images here.

---

**`assets/img/library/`**
Reusable brand image library: unused variants, alternate crops, source assets,
and color-variant images kept for reference or future use. Files here are not
necessarily referenced by any live page -- this is the on-disk brand archive
so assets are not permanently lost.

Expected file types: PNG source files and WebP counterparts, named in kebab-case
by subject and variant. Do not store WebP pipeline output here -- that belongs
in `assets/img/webp/`. Use `.gitkeep` when the library is empty.

---

**`assets/img/webp/`**
WebP-format output of the image conversion pipeline. Generated by
`scripts/convert-hero-webp.py`, `scripts/convert-gpt-icons-webp.py`,
`scripts/png-to-webp.py`, or `scripts/picture-upgrade.py`. Never hand-placed.

Expected file types: `.webp` only. Filenames mirror the source PNG with a
width or size suffix, e.g. `brand-hero-wide-768.webp`,
`gpt-icon-01-careers-retro-stripe-512.webp`. PNG source files stay in
`assets/img/`. Use `.gitkeep` when the pipeline has not yet been run.

---

**`assets/js/`**
JavaScript files served directly to browsers. No build step; files are served
as-is. No TypeScript, no bundled output. Node.js tooling belongs in `scripts/`.

Expected files:
- `app.js` -- the primary shared script: site search, nav toggle, GA4 analytics
  bootstrap, theme toggle, reading progress bar, scroll reveal, sticky TOC.
- `mermaid-init.js` -- Mermaid v11 ESM initializer; loaded only on pages that
  contain diagrams (`ecosystem/`, `universe/`).
- `sparkle-loader.js` -- loads and renders the "Today's Sparkle" banner from
  `assets/data/sparkle.json` (present on sites using the Sparkle feature).

Do not add vendor libraries here -- load from CDN per the static-only constraint.

---

**`assets/templates/`**
Structural HTML shell templates for scaffolding new pages. Development
artifacts only -- excluded from the search indexer, validators, and
`sitemap.xml` by every HTML-walking script.

Expected contents:
- `template--<page-type>.html` files, one per page type, using double-dash
  separator. Each carries a comment block listing every `[[TOKEN]]` before
  `<!DOCTYPE html>`.
- `INDEX.md` or `index.md` / `template-index.md` -- documents every template,
  its token list, and the workflow for creating new pages from it.
- `template-system-prompt.md` -- optional AI prompt document for using
  templates (AskJamie convention; adopt on siblings as needed).

Page types currently templated across the family:
homepage, hub, interior-single, tool/lens detail, error, holding/utility,
article, case study, mermaid-diagram, interior-form, project detail.

Finished published pages do not belong here. Images do not belong here.

---

**`docs/`**
Top-level cross-functional documentation directory rendered by GitHub as the
repo's documentation root. Intended for project-level documents that apply
across planning sessions or across multiple repos -- distinct from
`assets/docs/`, which holds per-site audit and evaluation reports.

Expected contents:
- Cross-site coordination docs: sync plans, dispatch notes, search design specs
- Sprint planning summaries and design decision records
- Integration research and tool evaluation documents
- `.gitkeep` placeholder when empty

Keep `docs/` for planning-level content. If a document is purely a site audit
report, it belongs in `assets/docs/` instead.

---

**`docs/archive/`**
Superseded documentation removed from active use but preserved for historical
context. Triage before adding -- if a document has no future reference value,
delete it rather than archiving it.

Expected contents:
- Completed sprint plans and summaries, prefixed `YYYY-MM-DD-`
- Superseded audit reports replaced by newer versions
- Design decision records for concluded decisions
- `.gitkeep` placeholder when empty

---

**`scripts/`**
Python (`.py`) and shell (`.sh`) maintenance, build, audit, and migration
scripts. Node.js QA runners (`.mjs`) also live here. All filenames must be
kebab-case. Scripts are run manually from the command line or invoked from
`post-merge.sh`; they are never served to browsers.

Script categories:
- **Validators** (exit non-zero on regressions; safe for CI):
  `validate-site.py`, `check-links.py`, `audit-assets.py`,
  `audit-site.py`, `audit-meta-versions.py`
- **Index and feed builders** (regenerate data files):
  `build-search-index.py`, `generate-feed.py`
- **Idempotent mutators** (safe to re-run; AUTOGEN-marker-driven):
  `normalize-head.py`, `inject-jsonld.py`, `inject-breadcrumb.py`,
  `enhance-pages.py`, `apply-modern-baseline.py`,
  `inject-color-scheme-init.py`, `remove-deprecated-meta.py`
- **Image pipeline** (WebP conversion and `<picture>` injection):
  `png-to-webp.py`, `picture-upgrade.py`, `convert-hero-webp.py`,
  `inject-hero-picture.py`, `inject-nav-logo-webp.py`
- **Governance and sync**:
  `push-to-github.py`, `post-merge.sh`, `rename-img-kebab.py`
- **QA runners**:
  `responsive-audit.py`, `responsive-qa.mjs`, `viewport-qa.py`

When adapting a script for a sibling repo, update these per-site constants:
`SITE` / `SITE_ORIGIN`, `GA4_ID`, `EXPECTED_THEME_COLOR`, any hardcoded
localStorage key, and any brand-specific image filename lists.
See `docs/cross-site-sync-plan.md` for the local cross-site sync plan and
foundation-file workflow.

Scripts that mutate HTML must carry an `<!-- AUTOGEN:<MARKER> -->` comment for
idempotency so re-runs are no-ops on already-processed pages.

Do not place application source code, HTML templates (those go in
`assets/templates/`), or test fixtures here.

#### 2.2.1 Per-site directory inventory (OverKill Hill P3)

**Mermaid runtime override (verified 2026-09-20):** This repository uses
Mermaid **12.0.0**, with the authoritative pin in
`assets/vendor/mermaid/VERSION` and the self-hosted bundle under
`assets/vendor/mermaid/`. This per-site override supersedes the legacy v11
description and CDN guidance in Section 2.2 for Mermaid. The shared
`assets/js/mermaid-init.js` initializes page diagrams;
`assets/js/universe-map.js` initializes the universe diagrams. Follow the
README's Mermaid runtime trust decision when updating the pin and bundle.

Current state of shared directories as surveyed 2026-07-13. Use this as the
baseline -- update it here when the inventory changes materially.

| Directory | Current state | Notes |
|---|---|---|
| `assets/audit/` | `.gitkeep` plus `screenshots/canvas/` with two retained visual-QA captures | Populate by running `scripts/validate-site.py`, `check-links.py`, `viewport-qa.py`; retained screenshots are visual-QA evidence |
| `assets/css/` | `theme.css` (136 KB) | Single canonical stylesheet |
| `assets/fonts/` | Eleven self-hosted WOFF2 subsets, three upstream OFL license texts, provenance metadata | Alfa Slab One 400; DM Sans and JetBrains Mono variable weights. Release includes font and license files; see `assets/fonts/font-provenance.md`. |
| `assets/data/` | Generated search and runtime data | Rebuild with the owning script and verify with its `--check` mode |
| `assets/downloads/` | `okh-prompt-protocol-template.md` | User-facing prompt protocol download |
| `assets/docs/` | `.gitkeep` only | Add audit and evaluation reports here |
| `assets/img/` | 14 direct image files plus subdirectories | Includes Sentinel, BirdPatrol, and cross-site reference assets |
| `assets/img/favicons/` | 8 files | PNG set plus root and vector favicon references |
| `assets/img/library/` | 99 files (49 PNG + 49 WebP + README) | Full brand library with WebP pairs |
| `assets/img/webp/` | `.gitkeep` only | Run `scripts/convert-hero-webp.py` to populate |
| `assets/js/` | `app.js`, `mermaid-init.js` | |
| `assets/templates/` | 10 HTML templates plus `index.md` | Article, hub, project-detail, form, and utility types |
| `dist/` | Not present in this checkout | Reserved, ignored cross-site sync staging area when the sync workflow is run |
| `docs/` | 4 cross-site planning docs | `cross-site-sync-plan.md`, `cross-site-search-dispatch.md`, `cross-site-search-prompt.md`, `project-page-mermaid-theme-builder-salvage.md` |
| `docs/archive/` | 6 archived sprint and audit docs | Sprint plans from 2026 |
| `scripts/` | Active tools plus archived historical tools | See `scripts/README.md` for the current classification |

**OKH-specific sub-folders under `assets/img/`:**
- `assets/img/library/` -- fully populated; 49 PNG + 49 WebP project/article images
- `assets/img/AskJamie/` -- cross-site asset folder (AskJamie brand images stored here
  for cross-site reference); evaluate moving to `assets/img/library/` for clarity

**OKH-specific scripts not present on siblings:** See `scripts/README.md` for
the active list and the separate reference-only/retired archive. Do not copy
an archived command into current instructions without verifying its target
paths and classification.

**Using `scripts/`:** `scripts/README.md` classifies every script as active,
reference-only, or retired -- only active scripts remain at the top level of
`scripts/`; everything else lives in `scripts/archive/` with the
classification and rationale recorded there. Use `scripts/audit-site.py`
for the canonical site audit, `scripts/validate-site.py` for structural
validation, and `scripts/check-links.py`/`scripts/responsive-qa.mjs` for
link and responsive QA. Do not run an archived script without reading its
header and confirming its target paths still apply -- several were written
for an earlier repo layout or reference sibling-site constants. This
convention was ported from `askjamie/scripts/README.md`; see
`docs/sxs-infrastructure-audit-2026-08-29.md` for the full classification
evidence.


---

### 3. Detritus (what does not belong in version control)

Replit Agent generates working artifacts during a build. Some are useful in
the moment and become noise the next week. The categories below are detritus
by default and must be gitignored, moved to a proper home, or deleted.

#### 3.1 Replit working-buffer artifacts

- **`attached_assets/`**: paste-buffer transcripts and screenshots from Replit
  Agent prompts. Filenames look like `Pasted--<title>-<timestamp>.txt` or
  `image_<timestamp>.png`. Never useful after the session. Always gitignore.
  Delete from history if accidentally committed.
- **`_unused/`**: code Replit moved out of the way during a refactor. Read it
  once to confirm nothing important is stranded, then delete the folder.
- **`attached-assets/`** (hyphen variant) and **`unused/`**: same rules.

#### 3.2 Test and build output

- **`test-results/`**: Playwright run output. Always gitignored. Delete if
  committed.
- **`playwright-report/`**: same.
- **`coverage/`**: same.
- **`build/`**, **`.next/`**, **`.vite/`**: build output. Gitignore.
- **`dist/`**: build output on most projects — gitignore. **Exception: OverKill Hill P³.**
  In this repo `dist/` is the cross-site sync staging area (see section 2.2.1).
  Its contents are still gitignored, but the directory is intentional; do not delete it.
- **`node_modules/`**: already gitignored by default; verify.

#### 3.3 IDE and OS junk

- **`.DS_Store`**, **`Thumbs.db`**, **`.idea/`**, **`.vscode/`** (with
  team-specific settings): gitignore unless the project deliberately ships a
  workspace config.

#### 3.4 Stale planning artifacts

- **`_replit/`**: old Replit working notes that may contain genuinely useful
  audits or sprint plans. Triage before deleting: move anything worth keeping
  into `assets/docs/` or `assets/docs/archive/`, delete the rest.

#### 3.5 Duplicated content from sibling repos

When an agent copies a skill or asset from another repo, it sometimes lands in
the wrong repo. If the skill or folder is not actually owned by this app,
remove it.

#### 3.6 Pre-deploy preview directories

Pre-deploy previews of sibling apps copied into this repo are dead weight once
the live URL is deployed. Delete them.

---

### 4. Required `.gitignore` entries

Every OKHP3 repo must include at least the following. Add these where absent.

```
# Replit working-buffer artifacts
attached_assets/
attached-assets/
_unused/
unused/

# Test and build output
test-results/
playwright-report/
coverage/
dist/
build/
.next/
.vite/

# IDE / OS
.DS_Store
Thumbs.db
.idea/

# Node
node_modules/
*.log
```

If a folder in this list is currently tracked, remove it from the index before
committing the `.gitignore` change so it disappears from tracking.

---

### 5. Decrapify command (reusable instruction)

When the repo accumulates working artifacts, paste this message to Replit Agent:

> **Decrapify this repo per the Repository Hygiene Standard in `AGENTS.md`
> Section 5.** Triage, do not just delete. Produce a plan first, then execute
> on confirmation. Cover: `attached_assets/` and any hyphen variant, `_unused/`,
> `test-results/`, `playwright-report/`, `coverage/`, `dist/`, `build/`,
> `_replit/` (triage into `assets/docs/` or `assets/docs/archive/` before
> deleting), any duplicated sibling-repo content, any file or folder violating
> Section 1, and any forbidden folder name from Section 3. Output a plan with
> four sections: A. DELETE / B. GITIGNORE-AND-UNTRACK / C. TRIAGE-THEN-DELETE /
> D. RENAME. Wait for "go" before executing.

---

---

### 6. Brand contract (OverKill Hill P³)

This repo serves the OverKill Hill P³ brand.
Canonical reference: https://raw.githubusercontent.com/OKHP3/OverKill-Hill/main/assets/css/theme.css

OverKill Hill P³ Forge motif declared values:

| Aspect | Value |
|---|---|
| Body scope class | none -- this is the default brand; pages set no body class |
| Display font | Alfa Slab One |
| Body font | DM Sans |
| Mono font | JetBrains Mono |
| Primary accent | rust-orange `#c46a2c` |
| Secondary accent | amber `#e6a03c` |
| Header surface | teal `#1c3a34` |
| Light page background | `#f0ebe5` (warm paper) |
| Light ink | `#0f172a` (deep navy) |
| Dark mode | espresso/slate-blue family |
| Mermaid line/border | `#c46a2c` |
| Tone | precise, editorial, forge-mode |

**Forbidden in this brand's design system:**
- Coral `#d94f63` (that is Glee-fully)
- Aqua/teal `#2d6f7e` as a primary accent (that is AskJamie)
- Fredoka or Baloo 2 headings (those are Glee-fully and AskJamie)
- Any font outside Alfa Slab One / DM Sans / JetBrains Mono

**Note on BFS content:** The site hosts a legitimate client project page at
`/projects/bfs-framing-intelligent-futures/`. BFS brand colors, images, and
copy on that page are intentional content, not violations. The prohibition above
applies to OverKill Hill's own design system, not to documented client work.

---

### 7. Universal guardrails

These apply in every session, regardless of task:

- No em dashes anywhere (code, comments, copy, commit messages). Use periods
  or restructure the sentence.
- No AI filler in copy or comments: not "seamlessly," "robust," "powerful,"
  "effortlessly," "elevate," "unleash."
- Tailwind v4 only if Tailwind is in use: no `tailwind.config.js` (tokens live
  in CSS via `@theme inline`).
- No new dependencies unless explicitly requested.
- All user-facing content must use US English per the Language Standard in
  Section 0. UK and Commonwealth spellings are defects, not stylistic variants.
- Preserve standalone punchy lines in copy -- do not consolidate them into
  surrounding paragraphs. A one-sentence paragraph is intentional.
- ROY principle: understanding produced divided by explanation invested --
  verbosity must earn its space. If a shorter phrasing conveys the same meaning,
  use it.
- AutoCAD version in use is R10 -- locked, not negotiable. Do not suggest
  upgrades or reference features from later releases.

---

### 8. US English audit command (reusable instruction)

When the repo accumulates UK or Commonwealth spellings, paste this message to
Replit Agent:

> **Run the US English audit per the Language Standard in `AGENTS.md` Section
> 0.** Produce a QA summary first; execute corrections only after I say "go."
> Cover: UI copy, docs, README, release notes, human-readable comments,
> prompts, tooltips, error and validation messages, and QA/QC reports. Apply
> protected exceptions in Section 0. For existing code identifiers with UK
> spellings, list them as renaming candidates but do not auto-rename without
> confirmation. Output: (1) files scanned, (2) files to change, (3) UK spellings
> found with location, (4) US-EN replacements proposed, (5) protected exceptions
> intentionally left unchanged with reason, (6) identifier renaming candidates
> flagged for separate handling, (7) final confirmation the report itself
> contains no UK spellings. Wait for "go." No em dashes.

---
 
### 2B. Web application repo structural standard
 
Every OKHP3 web application repo (TypeScript / Vite / React / Tailwind v4) shares
this top-level structure. Web application repos differ from static site repos in
that source code is compiled, output lands in `dist/`, and GitHub Pages deployment
is driven by a CI workflow rather than committed HTML files.
 
```
<repo-root>/
|-- .agents/                  Replit Agent working memory (committed; canonical)
|   +-- skills/               agent skills consumed by this app
|-- .github/
|   |-- workflows/            GitHub Actions (CI, deploy-pages, e2e, link-check,
|   |                         release-gate, skill-tests, sync-forge-tokens)
|   |-- dependabot.yml
|   |-- FUNDING.yml
|   +-- copilot-instructions.md
|-- .gitignore
|-- .npmrc
|-- .prettierrc
|-- .prettierignore
|-- .replit
|-- .replitignore
|-- AGENTS.md                 governance for AI agents working in this repo
|-- CHANGELOG.md
|-- LICENSE
|-- README.md
|-- docs/                     human-authored design, product, and process docs
|-- e2e/                      end-to-end tests (Playwright)
|-- examples/                 .mmd or other reference input files (authoring only;
|                             not compiled; content may be inlined into src/data/)
|-- index.html                Vite entry point (at repo root for flat layout)
|-- package.json              the app package (named @workspace/<app-name>)
|-- playwright.config.ts
|-- pnpm-lock.yaml
|-- pnpm-workspace.yaml       workspace wrapper; retains catalog: version pins and
|                             Replit artifact registration even in single-app repos
|-- public/                   static assets copied verbatim into dist/ by Vite
|-- replit.md                 Replit-specific project notes
|-- scripts/                  build, maintenance, and authoring scripts
|-- skills/                   SKILL.md packages this app owns or ships
|   +-- <skill-name>/         one folder per skill package
|-- src/                      application source (the app lives here)
|   |-- __tests__/            unit and component tests (Vitest)
|   |   +-- __snapshots__/    generated snapshot files (gitignored or regenerable)
|   |-- components/           PascalCase React components
|   |-- data/                 static data files (kebab-case filenames)
|   |-- hooks/                React hooks (camelCase: useFoo.ts)
|   |-- lib/                  pure logic modules (kebab-case filenames)
|   |-- pages/                top-level route components (PascalCase)
|   |   +-- tabs/             tab-level route sub-components
|   |-- styles/               CSS files including forge-tokens.css
|   |-- App.tsx               root shell component
|   |-- index.css             global Tailwind directives and CSS custom properties
|   |-- main.tsx              Vite entry point (React root mount)
|   +-- vite-env.d.ts         Vite environment type declarations
|-- standards/                process standards and reference checklists
|-- tsconfig.base.json        shared strict TypeScript defaults
|-- tsconfig.json             app typecheck config (extends tsconfig.base.json)
|-- vite.config.ts            Vite build config (base path injected via env var)
+-- vitest.config.ts          Vitest unit test config
```
 
Additional directories that may be present depending on the app:
 
- `artifacts/<app-name>/.replit-artifact/artifact.toml` -- Replit platform
  registration file. This is a one-file platform token. It is not a pnpm
  workspace package, it contains no source code, and it must not be deleted.
  Note: MTB retains this at `artifacts/mermaid-theme-builder/.replit-artifact/`.
  BPMN uses `app/.replit-artifact/` after its migration to the `app/` layout.
- `context/` -- variable layer templates (BPMN for Mermaid only)
- `evals/` -- eval fixtures and rubrics (BPMN for Mermaid only)
#### 2B.1 Flat layout is the standard
 
Web application repos use a flat layout: `src/` at the repo root. The presence
of `pnpm-workspace.yaml` and `artifacts/<app-name>/` is Replit scaffolding and
does not indicate a monorepo. The actual application package is always the root
`package.json`, named `@workspace/<app-name>`.
 
Do not place application source code under `artifacts/<app-name>/src/`. If it
is found there, that is a Replit scaffolding artifact requiring correction.
 
#### 2B.2 Build output and deployment
 
Web application repos always gitignore `dist/`. Unlike OverKill Hill P3 (where
`dist/` is an intentional cross-site sync staging area), `dist/` in web app repos
is pure Vite build output and must never be committed.
 
Build output path: `dist/public/` (relative to repo root; set in `vite.config.ts`).
 
GitHub Pages deployment is handled by `workflows/deploy-pages.yml`. The base
path (`/mermaid-theme-builder/`, `/mermaid-diagram-bpmn/`) is injected at build
time via `BASE_PATH` environment variable -- it is not hardcoded in
`vite.config.ts`. The config throws if `PORT` or `BASE_PATH` is missing.
 
#### 2B.3 Folders that must not exist at the repo root
 
Same reserved names as static site repos: `_unused/`, `attached_assets/`,
`attached-assets/`, `_drafts/`, `_scratch/`, `_old/`, `tmp/`, `temp/`, `unused/`.
 
Additionally reserved in web app repos: `build/`, `.next/`, `.vite/` (Vite
internal cache -- gitignore but do not commit).
 
#### 2B.4 Web app decrapify command (reusable instruction)
 
When the repo accumulates working artifacts, paste this message to Replit Agent:
 
> **Decrapify this repo per the Repository Hygiene Standard in `AGENTS.md`
> Section 5 and Section 2B.4.** Triage, do not just delete. Produce a plan
> first, then execute on confirmation. Cover: `attached_assets/` and any hyphen
> variant, `_unused/`, `test-results/`, `playwright-report/`, `coverage/`,
> `dist/`, `build/`, `_replit/` (triage contents into `docs/` or
> `docs/archive/` before deleting), any duplicated sibling-repo content, any
> file or folder violating the naming rules in Section 1, and any folder name
> listed as forbidden in Section 2B.3. Do NOT delete `artifacts/<app-name>/
> .replit-artifact/artifact.toml` -- that is a required Replit platform file.
> Ensure `.gitignore` covers everything in Section 4 and `git rm -r --cached`
> anything that became newly-ignored. Output a plain-text plan with: each item,
> category (gitignore-only, delete, triage-then-delete, rename), justification,
> and risk. Wait for "go" before executing. No em dashes in the plan.
 
---
 
### 9. App-level governance
 
Sections 0-8 of this file apply to all five OKHP3 repos. Section 9 is different.
It defines the *slot* for app-level governance content -- content that is
intentionally local to one repo and must not be synchronized across siblings.
 
Each web application repo carries its own Section 9 with the following subsections.
Static site repos do not carry a Section 9.
 
#### 9.1 Project identity and brand firewall
 
What this project is. What it is not. Which brand properties it is allowed to
reference. Which third-party brands are explicitly prohibited. The canonical
disclaimer to include in README and major docs.
 
#### 9.2 Architecture constraints
 
What this app must never do. Examples: no backend server, no user authentication,
no AI API calls, no payment processing, no file upload, no analytics that capture
pasted content, no forked or copied dependencies.
 
#### 9.3 Core workflow
 
The user-facing workflow the app implements. This must be preserved at all times.
Any change that breaks the core workflow is a defect, regardless of other intent.
 
#### 9.4 Dependency governance
 
Rules for managing the app's primary external dependencies. Which dependencies
are managed via npm. Which must never be forked or copied into the repo. What
update and review process applies. Which constants or registry files must be
manually updated after each dependency version change.
 
#### 9.5 App-specific conventions
 
Rules that apply only to this app's codebase. Examples: which file is the
canonical data source for a given capability, which generated directories must
not be hand-edited, which validation commands must pass before commit, which
naming tokens must be used for UI classes.
 
#### 9.6 Per-app directory inventory
 
Current state of the repo's directories as surveyed on a given date. Format
matches Section 2.2.1 in the static site repos -- a table of directory, current
state, and notes. Updated here when the inventory changes materially.
 
#### 9.7 Deprecated files and workflows
 
Files or GitHub Actions workflows that have been superseded and are safe to
delete. Named explicitly here so agents do not treat them as live.
 
---
 
**Note for agents reading a web app AGENTS.md:** The above subsections (9.1-9.7)
define the expected structure. Each web app repo fills them with its own content.
If a subsection is missing from a local AGENTS.md, it should be added on the
next governance pass -- do not invent content for it.

---

 

## Imported Claude Cowork project instructions

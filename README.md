# OverKill Hill P³™

**Precision · Protocol · Promptcraft**

The public site and source materials for **OverKill Hill P³™** — the digital forge behind protocol-driven promptcraft, custom GPT architecture, AI system design, and structured visual communication.

- **Live site:** <https://overkillhill.com>
- **Status:** Active build zone (forge mode, not museum mode)
- **License:** [CC BY 4.0](LICENSE)
- **Contact:** <contact@overkillhill.com>

---

## What this repo is

A static HTML/CSS/JS site, hand-authored, hosted on GitHub Pages with an
intended Cloudflare-fronted custom domain (`overkillhill.com`). No framework.
No tracking beyond the analytics declared on the relevant pages.

There is a build step. `scripts/build-site.py` generates page content from
`site-src/pages.json`, and `.replit` defines a separate release build
(`scripts/build-replit-release.py`, output `.local/site-release`). Check
`build-site.py` before hand-editing generated page HTML, or a later build may
overwrite the edit.

The repo also serves as the public artifact archive for OverKill Hill P³ writings, projects, and the surrounding ecosystem (AskJamie™, Glee-fully Personalizable Tools™, Mermaid Theme Builder, Prompt Forge).

MurderBird creative production and its interactive exhibit have a dedicated
home in [murderbird-uncaged](https://github.com/OKHP3/murderbird-uncaged).
This site keeps the published origin story and the assets required by its
pages. New music, video, lyrics, models, and creative source iterations belong
in that sibling repository. See the
[repository boundary](docs/murderbird-repository-boundary.md) for transfer
evidence and retained website compatibility copies.

## Stack

| Layer | Choice |
|---|---|
| Markup | Plain HTML 5 |
| Styling | Hand-authored CSS in `assets/css/theme.css` (token-driven) |
| Scripting | Vanilla JS (`assets/js/app.js`, `mermaid-init.js`) |
| Diagrams | [Mermaid](https://mermaid.js.org/) v12.0.0, self-hosted under `assets/vendor/mermaid/` |
| Search | Client-side index in `assets/data/search-index.json` |

### Mermaid runtime trust decision

Mermaid 12.0.0 is vendored under `assets/vendor/mermaid/`, including the
relative ESM chunks it imports. Production pages therefore do not fetch the
diagram runtime from a third-party CDN. Update the complete vendor directory
only when intentionally reviewing a new pinned Mermaid release; the pinned
version is the single line in `assets/vendor/mermaid/VERSION`, and it must
always match the version string actually inside `mermaid.esm.min.mjs`
(`scripts/validate-site.py` checks this on every run).

Mermaid 12 requires ES2024-capable browsers (including Safari 17.4 or newer).
Flowcharts retain the earlier `dagre`/`classic` defaults where inherited;
authored layout/look choices, brand themes, and interaction settings remain intact.
See [the reviewed migration and verification record](assets/docs/mermaid-12-review-2026-09-20.md).

The scheduled **Mermaid Version Watch** workflow
(`.github/workflows/mermaid-version-watch.yml`) checks `mermaid@latest` on
npm daily and opens (or updates) a tracking issue the moment the vendored
pin falls behind. It never re-vendors automatically -- that stays an
intentional, reviewed step -- it only makes sure the gap gets noticed the
same day instead of weeks later. The identical VERSION-pin + watcher
mechanism is also deployed on askjamie.bot and glee-fully.tools.

The shared initializer uses `securityLevel: "strict"` by default. The two v2
heat-guide pages opt into `loose` with a body data attribute because their
outbound diagram links are part of the published artifact. The Universe page
has its own inline Mermaid configuration and is the only other approved
loose-security page; its links are constrained to documented partner and site
path prefixes. Before rendering, every heat-guide click target must match an
exact HTTPS origin and path allowlist in `assets/js/mermaid-init.js`;
unlisted targets are removed.

CSP / Mermaid style alignment: `scripts/csp.py` computes the `style-src` /
`style-src-attr` allowlists by statically hashing inline styles in the built
HTML, but Mermaid generates its own inline styles and `<style>` blocks at
render time in the browser -- no static hash can ever cover that. Pages
carrying a live Mermaid diagram now get a scoped `diagram` (or
`embed-diagram`, for the found-ry page) CSP class instead: `style-src` /
`style-src-attr` grant `unsafe-inline` for style only, while `script-src`
stays exactly as hash-locked as every other page class. This is deployed on
all three OKHP3 sites the same way. `scripts/validate-site.py` flags any
page that renders a live diagram under a CSP class without this allowance,
so a future page can't silently regress.

Residual risk: the two v2 pages still require Mermaid's looser interaction
mode, and the vendored JavaScript remains a large third-party dependency even
though it is now reviewed and served from this repository. The allowlist is
not a substitute for reviewing diagram source changes.
| Hosting | GitHub Pages with `CNAME` + Cloudflare |
| Local preview | `python3 server.py` (port 5000, no-cache headers) |

## Local development

```bash
python3 server.py
# then open http://localhost:5000
```

The server is dev-only. It serves the repo root with no caching so edits are immediately visible. Production routing (404, redirects) is handled by GitHub Pages and Cloudflare, not by this script.

## Repository layout

```
.
├── index.html                       Homepage
├── 404.html                         Brand-styled 404
├── under-construction.html          Forge-in-progress shell
├── about/                           About OverKill Hill
├── contact/                         Contact + social
├── legal/                           Legal notice + usage disclaimer
├── manifesto/                       The manifesto (canonical declaration)
├── universe/                        Ecosystem map (parent/child relationships)
├── search/                          Client-side site search
├── prompt-forge/                    The Prompt Forge tool entry
├── found-ry/                        Found-Rᵧ meta-framework page
├── projects/
│   ├── index.html                   Projects hub
│   ├── mermaid-theme-builder/       Live tool + landing
│   ├── bfs-framing-intelligent-futures/
│   ├── abrahamic-reference-engine/
│   ├── hometools/                   Homestead-R
│   ├── pathscrib-r/                 Narrative copilot
│   └── un-nocked-truth/             Inclusive archery program
├── writings/
│   ├── index.html                   Writings hub
│   ├── first-diagram-is-a-liar/     Featured essay (v0.3 Visual Edition)
│   │   └── v03/                     v1/v2 heat pages (poll bracket)
│   ├── biases-as-constants/
│   └── magnus-saga/                 Speculative fiction series
├── assets/
│   ├── css/theme.css                Single stylesheet, token-driven
│   ├── js/app.js                    Mobile nav + year setter + search
│   ├── img/                         Logos, hero images, favicons
│   ├── data/search-index.json       Generated search index
│   ├── templates/                   10 production HTML scaffolds
├── scripts/                         All dev + CI maintenance scripts
├── sitemap.xml                      All canonical public URLs
├── robots.txt                       Crawler policy + AI-bot opt-ins
├── site.webmanifest                 PWA manifest
├── server.py                        Dev preview server
├── CNAME                            overkillhill.com
└── _replit/                         Workspace-internal previews (not deployed)
```

## Major routes

Brand: `/`, `/about/`, `/manifesto/`, `/universe/`, `/contact/`, `/legal/`
Projects: `/projects/`, `/projects/mermaid-theme-builder/`, `/projects/bfs-framing-intelligent-futures/`, `/projects/abrahamic-reference-engine/`, `/projects/hometools/`, `/projects/pathscrib-r/`, `/projects/un-nocked-truth/`
Tools: `/prompt-forge/`, `/found-ry/`, `/search/`
Writings: `/writings/`, `/writings/first-diagram-is-a-liar/` (+ four `v03/v1-heat-*` and `v03/v2-heat-*` subpages), `/writings/biases-as-constants/`, `/writings/magnus-saga/`
Utility: `/404.html`, `/under-construction.html`

## Validation

```bash
python3 scripts/validate-site.py
```

Checks every HTML page for: title, meta description, canonical, single H1, JSON-LD, sitemap inclusion, broken internal links, broken asset references, external `target="_blank"` links missing `rel="noopener"`, placeholder hrefs, `P3` (without superscript) brand violations, and old-tagline regressions. Run before every commit.

For the browser-level phone layout check used in CI:

Use the preferred Node.js version in `.nvmrc` and `.node-version` for local
browser QA and CI: **24.21.0**, with bundled npm **11.19.0**. Run `npm ci`
to preserve the dependency lockfile.

Managed Replit runtimes can lag behind the latest LTS patch. The manifest and
lockfile therefore support **Node >=24.13.0 <25** with **npm >=11.6.2 <12**.
`.npmrc` keeps engine enforcement enabled; unsupported Node/npm majors and
older patches are rejected. The September 20 Replit inspection found Node
24.13.0 and npm 11.6.2. This is supported compatibility, not a claim that the
managed runtime runs the latest patch. See [the update policy](docs/technology-update-policy.md).

Replit preview uses `python3 server.py`. Its `.replit` environment selects
`nodejs-24` for browser QA. Verify actual `node --version` and `npm --version`
against the supported bounds before running `npm ci`.
Open a fresh Shell after changing modules so it loads the selected runtime.
Connected Replit installation, browser and preview checks are recorded in
[the A08 runtime evidence](assets/docs/qa-runtime-a08-2026-09-07.md).

```bash
npm ci
npx playwright install chromium
python3 server.py &
npm run test:phone-overflow
```

This opens the manifesto, Mac Studio workbench, and First Diagram article at
320px and fails on document overflow, inaccessible final table columns, or
diagram grids that escape the viewport.

## Build / maintenance scripts

`scripts/` holds Python and Node runners. The Python helpers are dependency-light (`beautifulsoup4`, `Pillow`, `soupsieve`, `typing-extensions` — see `requirements-qa.txt`; there is no `lxml` dependency) and **idempotent** — re-running them on an already-processed repo is a no-op. Each supports `--check` where documented.

Retired one-shot scripts live in `scripts/archive/` and are not part of any pipeline. Read a script's header before adapting one.

| Script | Purpose |
|---|---|
| `build-site.py` | Generates page content from `site-src/pages.json` |
| `build-replit-release.py` | Assembles the Replit static release into `.local/site-release` |
| `validate-site.py` | Editorial + structural validator (run before every commit) |
| `cache-bust.py` | Appends `?v=<sha256[:8]>` to local CSS/JS refs in HTML |
| `build-search-index.py` | Refreshes `/assets/data/search-index.json` from live HTML. `--check` compares the expected index in memory and exits non-zero when stale without writing the JSON. |
| `check-stack-conformance.py` | Asserts the ADR-0007 canonical OKHP3 stack; `--fix` repairs mechanical items only |

Templates under `/assets/templates/` are **scaffolds, not pages** — they're disallowed in `robots.txt` and skipped by `validate-site.py`. The script that derived them is archived and is not re-run.

### Continuous integration

`.github/workflows/validate.yml` runs `validate-site.py` and the non-mutating
`build-search-index.py --check` on every push and pull request to `main`. It
also runs the comprehensive static audit, internal-link/sitemap check, shared
asset fingerprint check, phone browser QA, and contrast audit. On a push to
`main`, it deploys the checked-out commit only after that validation job
succeeds.

### Accessibility QA coverage

The required CI gate runs browser checks for keyboard reachability, the skip
link, keyboard-visible focus outlines, basic ARIA attribute values and ID
references, Mermaid text alternatives, layout tables that would lose their
row/cell semantics for screen readers, and reduced-motion behavior. ARIA,
Mermaid, and layout-table checks run across every sitemap route; keyboard and
focus interaction checks run on representative home, article, project, and
utility pages. Contrast and phone/viewport overflow remain separate required
checks.

Chromium exposes a bare `<table>` with real `table`/`row`/`cell` semantics
only when it has at least one `<th>`, a `<caption>`, or an explicit `role`;
otherwise it applies a "layout table" heuristic and silently strips those
semantics, so a screen reader loses row/column navigation even though the
table renders normally. `scripts/accessibility-qa.mjs` flags any table that
would fall into that heuristic before it can ship.

This is automated regression coverage, not full WCAG conformance. It does not
replace manual screen-reader testing, keyboard testing with every browser or
assistive technology, cognitive accessibility review, or human judgment of
alternative-text quality.

### Screen-reader verification (manual QA, August 25, 2026)

This workspace is a headless Linux sandbox: no audio device, no desktop
session, and no installed screen reader (NVDA/JAWS require Windows, VoiceOver
requires macOS, and Orca needs a graphical AT-SPI session that isn't present
here). A literal "run NVDA and listen" session is not possible in this
environment, so verification used the same accessibility tree that screen
readers consume on the user's own machine:

```bash
python3 server.py &
node scripts/screen-reader-tree-audit.mjs
```

`scripts/screen-reader-tree-audit.mjs` opens Chromium, pulls the CDP
Accessibility domain's full tree (the same tree Chromium hands to
UIA/AT-SPI/AX platform APIs, which NVDA, JAWS, VoiceOver, and Orca all read
from), and checks the home, article, project, utility, universe, and
found-ry pages for: landmark exposure (banner/navigation/main/contentinfo),
Mermaid diagrams exposed with `role="image"` and a real accessible name,
table structures exposed with `role="table"`, and the search overlay
exposing `role="dialog"` with focus moving in on open and returning to the
trigger on close.

This run found and fixed one real gap: the Council Snapshot table on the
First Diagram Is a Liar article (`class="council-table"`) has no `<th>`
cells, so Chromium's accessibility tree applied its layout-table heuristic
and stripped its `table`/`row`/`cell` semantics -- screen-reader users
would have heard the seven name/role pairs as a flat run of text instead of
a navigable table. Adding an explicit `role="table"` (in both
`writings/first-diagram-is-a-liar/index.html` and its `site-src` source)
restores table semantics without changing the visual design. Re-running the
audit and `npm run test:accessibility` confirmed the fix and found no
further gaps on the checked pages.

**Coverage:** Chromium (headless), the same engine and accessibility-tree
plumbing used by Chrome/Edge on Windows and Linux with NVDA or Narrator.
**Not covered by this pass:** a live NVDA+Chrome or JAWS+Chrome session on
Windows, a live VoiceOver+Safari session on macOS/iOS, and TalkBack on
Android. The accessibility-tree audit verifies what is exposed to assistive
technology (roles, names, landmarks, dialog semantics); it does not verify
a specific screen reader's spoken phrasing, verbosity settings, or
browser-specific AT interop quirks. Before a major accessibility-sensitive
release, pair this automated pass with at least one real NVDA+Chrome (or
VoiceOver+Safari) session on the home, article, project, and utility pages.

## Editing guidance

- **Brand name** is `OverKill Hill P³™` (Unicode `³`, not `P3`). The script will fail the build if `P3` slips into a title or meta tag.
- **Tagline** is `Precision · Protocol · Promptcraft` — never `Precision. Power. Presence.` (the pre-2026 form).
- **Sub-brands** (AskJamie™, Glee-fully Personalizable Tools™) are separate; do not collapse them into OverKill Hill copy.
- **`AutoCAD 10`** is a deliberate locked literal in the manifesto — leave it alone.
- When adding an indexable page, also add a `<url>` entry to `sitemap.xml`.
  Redirects and WIP pages marked `noindex` stay out of the sitemap and are
  reported as intentional exclusions by `check-links.py`.
- After changing searchable content, refresh and verify the committed index:
  `python3 scripts/build-search-index.py` followed by
  `python3 scripts/build-search-index.py --check`.

## Related projects

- **AskJamie™** — <https://askjamie.bot> — mid-century AI helpdesk persona
- **Mermaid Theme Builder** — `/projects/mermaid-theme-builder/` — live tool, MIT-licensed
- **Prompt Forge** — `/prompt-forge/` — protocol-driven prompt engineering workshop

## Known limitations

- Image-format optimization is **not currently running**. The PNG-to-WebP and picture-upgrade scripts are in `scripts/archive/`, and `assets/img/` still holds PNGs above 1 MB with no WebP sibling. Restore the scripts to `scripts/` and run them, or drop the optimization claim.
- `_headers` declares a report-only CSP and related security/cache headers for
  the intended edge. The August 22, 2026 live check found those headers absent
  and observed `Cache-Control: max-age=600` on the canonical domain, so
  production enforcement is **not confirmed**. See
  `assets/audit/live-edge-report-2026-08-22.json` and
  `docs/publishing.md`; do not treat `_headers` as active on GitHub Pages.
- Search index (`assets/data/search-index.json`) is committed. Refresh it after
  searchable content changes, then use `build-search-index.py --check` to
  verify the generated file without rewriting it.
- Publishing authentication: use the GitHub Actions Pages workflow for normal
  releases. If a controlled API publish is required from Replit, store a
  fine-grained GitHub credential as the `GITHUB_PAT` workspace secret and run
  `GITHUB_TOKEN="$GITHUB_PAT" python3 scripts/push-to-github.py`. Never put the
  credential in a remote URL, repository file, shell history, or chat. The
  helper sends it only in an HTTPS Authorization header and exits on any API
  failure. See `docs/publishing.md`.

## Contact

Project inquiries, collaboration, or audit reports: <contact@overkillhill.com>

---

*This repo is the artifact, not the product. The product is whatever the page tells you it is.*

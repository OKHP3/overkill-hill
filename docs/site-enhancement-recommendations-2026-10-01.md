# overkillhill.com: Flawless GitHub Pages Plan

Oct 1, 2026 · Jamie Hill

## Executive summary

The call: stop adding and start subtracting. overkillhill.com becomes the exemplar by doing everything GitHub Pages allows, perfectly, and nothing it pretends to allow.

- **The pipeline is already better than most.** SHA-pinned actions, a validate-then-deploy release gate, a byte-verified release artifact, and a post-deploy live-edge check. Keep all of it.
- **The site claims controls it doesn't have.** `_headers` declares HSTS, COOP, CORP, frame-ancestors, immutable caching and a report-uri. GitHub Pages ignores that file. The live edge sends `server: GitHub.com` and `cache-control: max-age=600`, nothing else. The README still says "GitHub Pages + Cloudflare"; DNS says otherwise.
- **The CSP works, but by brute force.** Every page ships a meta CSP with ~30 script hashes and ~20 style hashes. An exemplar externalizes inline code and gets to `script-src 'self'` with zero hashes.
- **The repo is the weak point, not the site.** 1,696 tracked files for ~35 indexable URLs. 543 files in `.agents/`, 110 in `scripts/`, 97 in `tests/`, a 52 KB AGENTS.md, a 183 MB PNG library and a local `.git` near 1 GB. A stranger can't learn from it.
- **Two deploy paths still exist.** GitHub Pages plus a Replit static target with its own release builder and tests. Flawless means one.
- **Unmeasured basics.** No Lighthouse CI budget, no Atom feed for writings, a hand-maintained sitemap, GA4 as the only third-party dependency.
- **One brand-boundary flag.** `/projects/bfs-framing-intelligent-futures/` is indexed, in the sitemap, and names the employer 49 times. That's your call, not mine, but it conflicts with the stated OKHP3/BFS separation.
- **Recommendation:** Option B, the pure-Pages exemplar. Five phases, each with a hard gate, ending in a public scorecard page that proves the claims live.

## Current state

Strong release engineering, weak legibility. Evidence from the local clone (HEAD `34b26243`) and live curl checks on 2026-10-01.

| Dimension | Evidence | Grade |
| --- | --- | --- |
| Deploy pipeline | `pages.yml` deploys only the artifact `validate.yml` produced; actions pinned by SHA; live-edge verifier runs after deploy | A |
| Domain and TLS | http and www both 301 to `https://overkillhill.com/`; `okhp3.github.io/overkill-hill/` 301s to apex; real 404 status on missing paths | A |
| Security headers | None beyond GitHub defaults; `_headers` (7.9 KB) is inert on Pages, which `docs/publishing.md` already admits | D |
| CSP | Meta CSP enforced, `script-src-attr 'none'`; but ~30 script and ~20 style hashes per page; `frame-ancestors` and `report-uri` can't work in meta | B- |
| Caching | Flat `max-age=600` on everything; `?v=` fingerprints exist but can't earn immutable caching on Pages | B |
| Performance | Not measured this pass (Lighthouse run failed in sandbox, PSI quota exhausted); no CI budget enforces it | ? |
| Media | 126 images in `assets/img/library` at 183 MB, many 3 to 4.5 MB PNGs; 110 WebP exist alongside | C |
| Content surface | 35 sitemap URLs; 5 writings, 17 project pages; no Atom/RSS feed; sitemap hand-maintained | C+ |
| i18n | fr, de, es, es-mx, en-gb trees with hreflang; locale HTML hand-maintained outside the generator | B- |
| Repo legibility | 1,696 tracked files; 62 scripts, 24 docs, 8 workflows plus a stray `sedMiHLjD`; 52 KB AGENTS.md, 25 KB replit.md | D |
| Repo weight | Local `.git` reports 709 MB loose + 282 MB packed, 284 garbage temp objects; `.local/` holds a 184 MB release copy | D |
| Working tree | 1,038 modified files locally, mostly `.agents/` line-ending noise | C |
| Single source of truth | Dual deploy (Pages + Replit static target); CHANGELOG lags production per the 2026-09 audit | C |

The pattern from the September audit still holds: process volume outruns content volume, and each AI sweep adds tooling rather than removing it.

## The flawless standard

Flawless means every claim below is enforced by CI on every push and visible on a public scorecard. If a gate can't be automated, it isn't part of the standard.

| Pillar | Definition of done | Enforced by |
| --- | --- | --- |
| Performance | Lighthouse 100 on all four categories, mobile, for every page template; Core Web Vitals good at p75: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 ([web.dev](https://web.dev/articles/vitals)) | Lighthouse CI with assertions |
| Weight | ≤ 150 KB transferred per page before the hero image; hero served as AVIF/WebP with `srcset`; no image over 300 KB in the release | Byte budget check on the release artifact |
| Accessibility | WCAG 2.2 AA; 0 axe violations; keyboard path through nav, search and theme toggle | axe via Playwright (existing) |
| Security | Meta CSP with `script-src 'self'`, zero hashes, zero `unsafe-inline`; no inline handlers; no claims of headers the host doesn't send | CSP lint + live-edge verifier |
| Privacy | Zero third-party requests on first load, or one consented analytics call disclosed on the legal page | Network-request assertion in Playwright |
| Correctness | Valid HTML on every page; 0 broken internal or external links; real 404 status | html-validate, lychee |
| Discoverability | Generated sitemap with `lastmod`; Atom feed for writings; canonical, hreflang, Open Graph and JSON-LD on every indexable page | Generator `--check` modes |
| i18n | Every locale page generated from one source plus translation files, never hand-edited HTML | Generator `--check` |
| Repo legibility | A stranger understands it in 5 minutes: ≤ 15 root entries, README quick start in 3 commands, AGENTS.md ≤ 10 KB, no tool output committed | Root-allowlist test |
| Repo weight | `.git` under 250 MB fresh clone; source art outside the site repo | Size check in CI |
| Ops | One deploy path; CI under 5 minutes; every merge to `main` via PR with required checks | Branch protection + workflow timing |
| Honesty | README, `docs/publishing.md` and the scorecard page match what the live edge returns | Live-edge verifier diff |

The last row is the one that makes it an exemplar. Most sites are good. Few can prove it.

## Options

Four paths. Only one of them keeps the word "GitHub Pages" honest in the brief.

| | A. Polish in place | B. Pure-Pages exemplar | C. Cloudflare-fronted | D. Rebuild on an SSG |
| --- | --- | --- | --- | --- |
| What it is | Keep all tooling, fix gaps one by one | Subtract to the platform; swap bespoke scripts for standard tools; externalize inline code | Proxy the apex through Cloudflare; make `_headers` real via Transform Rules | Move to Eleventy or Astro, deploy with the official Pages action |
| Real security headers | No | No, and says so publicly | Yes | No |
| Immutable asset caching | No | No (fingerprints still bust 600 s cache) | Yes | No |
| Repo legibility | Stays D | A | Stays D unless paired with B | A, but new learning curve |
| Effort | Low, forever | Medium, once | Low to add, ongoing vendor | High |
| Risk | Sprawl keeps compounding | Coverage loss if scripts are cut blindly | Second vendor, DNS/TLS coupling, "is it still a Pages site?" | Regression across 35 URLs and 5 locales |
| Teaches the reader | Nothing new | How far plain Pages goes, done right | How to escape Pages | How to use an SSG |

**A** is what the last six weeks have been. **C** solves headers but answers a different question. **D** buys a cleaner generator at the cost of re-proving everything you already proved; `build-site.py` already does the SSG job.

## Recommendation

Go with B. The pure-Pages exemplar is the only option where the finished repo teaches something most people get wrong.

The pitch writes itself: no CDN, no server, no headers, and still a perfect scorecard. Every constraint GitHub Pages imposes becomes a documented design decision instead of a quietly broken file. `_headers` goes away; a "Platform limits" section on the scorecard page states exactly what Pages can't do and how the site compensates.

Three rules govern the work:

1. **Subtract before you add.** No new script lands unless it retires two.
2. **Standard tools over bespoke ones.** Lighthouse CI, axe, html-validate and lychee replace homegrown checks wherever they cover the same ground. Bespoke stays only where nothing standard exists (live-edge provenance, locale freshness).
3. **One source, one path.** One generator for all locales, one deploy target, one agent-guidance file a human can read in a sitting.

Keep C in the back pocket. If you later want real HSTS preload or immutable caching, Cloudflare can be layered on without undoing any of B.

## Phased roadmap

Six phases, strictly sequential. Subtraction comes before every improvement, because every later phase is cheaper on a smaller repo.

| Phase | Work | Gate to exit |
| --- | --- | --- |
| 0 · Decide and baseline | Decide BFS page, analytics, Replit's role; protect `main`; commit a Lighthouse and axe baseline for every template; clean the working tree; tag `pre-exemplar` as the rollback point | Baseline committed; tree clean; `main` protected |
| 1 · Subtract | Map every bespoke script to a standard tool, then cut; retire Replit deploy, `_headers`, stray workflow; AGENTS.md to 10 KB; move the image library out; rewrite history once | 15 root entries or fewer; clone under 250 MB; CI under 5 min |
| 2 · Platform-honest security | Externalize inline scripts and styles; meta CSP down to `'self'` only, zero hashes; rewrite README and `publishing.md` to match the live edge | 0 hashes, 0 `unsafe-inline`; docs match live edge |
| 3 · Performance and media | Ship AVIF and WebP with `srcset`; subset and preload fonts; byte budgets enforced on the release artifact; Lighthouse CI assertions on every template | Lighthouse 100 x4 mobile, every template, in CI |
| 4 · Content and discoverability | Generator owns every locale; sitemap generated with `lastmod`; Atom feed for writings; JSON-LD and Open Graph everywhere; lychee link check, internal and external | 0 hand-edited locale HTML; 0 broken links |
| 5 · Prove it | Public `/scorecard/` page fed by CI results; Platform limits section (what Pages can't do, and the answer); README badges; lift the content freeze | Scorecard page live, every row green |

No phase starts until the previous gate passes in CI. Phase 1 is the long pole; Phases 2 to 4 are mostly mechanical once the repo is small.

What Phase 1 cuts, specifically:

- `_headers`, `.github/workflows/sedMiHLjD`, `server.py` (replace with `python -m http.server`), `.replit` and `replit.md` once Replit is editor-only
- `scripts/` and `tests/` down to what the coverage map keeps; target under 20 files each
- `docs/` down to `publishing.md`, ADRs and one current plan; audits and handoffs move to Notion, which is the workshop anyway
- `.agents/` out of the site repo, or reduced to the skills this repo actually invokes
- `assets/img/library/` source art to a separate archive repo or release assets; only the derivatives the site serves stay
- One `git filter-repo` pass to drop the purged blobs, then re-clone on both machines

## Risks and mitigations

The biggest risk is the one already in the record: agents re-growing what you prune.

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| AI agents (Replit, Codex, Copilot) re-add tooling and docs after Phase 1 | High | Branch protection on `main`; required checks include the root allowlist and a file-count ceiling for `scripts/`, `docs/`, `tests/`; AGENTS.md states "subtract before add" as rule one |
| Cutting a bespoke script silently drops a check | Medium | Coverage map first: each script mapped to the standard tool or test that replaces it; delete only mapped rows |
| History rewrite to shrink `.git` breaks other clones (two machines, Replit) | Medium | Do it once, in Phase 1; re-clone everywhere the same day; keep a tagged mirror archive before rewriting |
| Externalizing inline scripts breaks theme-flash prevention or GA bootstrap | Medium | Keep one tiny blocking `theme-init.js` in `<head>`; Playwright test for no flash of wrong theme |
| Locale trees diverge while moving them under the generator | Medium | Migrate one locale end to end, diff rendered output against today's HTML, then the rest |
| Dropping GA4 loses traffic insight | Low | Use GitHub's repo traffic plus Search Console, or keep GA4 behind consent and disclose it |
| BFS-named project page creates a brand-boundary issue | Owner call | Decide in Phase 0: keep, rename to a generic framing, or `noindex` and pull from sitemap |
| Scope creep into new content during cleanup | High | Content freeze for Phases 1 to 3, except fixes |

## Next actions

This week is Phase 0: decide, freeze and measure. Nothing gets deleted until the baseline exists.

- [ ] Decide the BFS project page: keep, reframe generically, or noindex and drop from sitemap
- [ ] Decide analytics: keep GA4 behind consent, or drop it for zero third-party requests
- [ ] Decide Replit's role: retire the Replit static deploy target, keep Replit as an editor only
- [ ] Turn on branch protection for `main` with `validate` as a required check
- [ ] Run Lighthouse and axe against every page template on the live site; commit the baseline as `docs/baseline-2026-10.json`
- [ ] Normalize line endings and commit or discard the 1,038 dirty files so the tree starts clean
- [ ] Tag `pre-exemplar` on `main` as the rollback point

### Follow-ups that would sharpen this plan

1. Grant this session GitHub access to `OKHP3/overkill-hill` so I can read Pages settings, branch protection and Actions run history directly.
2. Let me draft the script-to-standard-tool coverage map for Phase 1; it's the gating artifact for every deletion.
3. Want the scorecard page designed now, so every phase has a visible target?
4. Run the same audit on AskJamie and Glee-fully Tools; they share Sections 0 to 8 and likely the same sprawl.
5. Decide whether AGENTS.md stays the Tier 0 golden master for the whole ecosystem or moves to the FoundRy repo, which would let this one shrink.

## Sources

- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits): 1 GB published site, 1 GB recommended repo, 100 GB/month soft bandwidth, 10-minute deploy timeout
- [MDN: frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors): not supported in a `<meta>` element
- [MDN: Content Security Policy guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): meta delivery doesn't support all CSP features, including report-only
- [web.dev: Web Vitals](https://web.dev/articles/vitals): LCP, INP and CLS thresholds at p75
- Live edge: `curl -I` against overkillhill.com, www, http and okhp3.github.io on 2026-10-01
- Repo: local clone at HEAD `34b26243` (`pages.yml`, `validate.yml`, `_headers`, `docs/publishing.md`, `git count-objects`)

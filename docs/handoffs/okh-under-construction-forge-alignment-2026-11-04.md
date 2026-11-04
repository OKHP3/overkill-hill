# OKH | /under-construction.html | Forge alignment — thread handoff

**Status:** BLOCKED — NOT READY TO ARCHIVE. Reviewed 2026-11-04 (America/Chicago).  
**Stable thread key:** `okh-under-construction-forge-alignment-2026-11-04` (platform chat ID unavailable).  
**Repo:** [OKHP3/overkill-hill](https://github.com/OKHP3/overkill-hill), release branch `main`.  
**Review:** [draft PR #252](https://github.com/OKHP3/overkill-hill/pull/252), branch `okh/under-construction-forge-20261104`, initial commit `6851506dd46001dd2bbe0345b09f6e8aaf49a379`.

## Purpose, decisions, sources

User chose option C, the construction page, with three original black-and-white illustrations and explicitly asked that the real live Forge homepage supply header, footer and theme instead of the AskJamie-derived page. Earlier assistant standalone replacement drafts are superseded. Keep scope to existing utility route. `site-src/pages/under-construction.main.html` is authoritative; `scripts/build-site.py` generates root `under-construction.html`.

Reviewed all conversation turns visible in this session, three PNG originals, current repository source/generated page/homepage/theme, `docs/publishing.md`, `docs/site-maintenance-map.md`, Pages/validation workflows, and the `skillz` contracts for session-handoff, evidence-standard, artifact-validation. The historical ChatGPT share URL and live utility page were inaccessible to the web reader. Three additional uploaded HTML/CSS snapshots were listed but could not be read or materialized. Local developer-machine clone, its worktrees, active ownership, Replit state, and exact chat ID are unverified. Do not claim full history or filesystem coverage.

## Obligation ledger

| Requirement | Evidence | Status and owner |
|---|---|---|
| Use true OKH masthead, blueprint, navigation, CTA/cards; avoid AskJamie layout | PR #252 source/generated files, `forge-masthead` classes, no new CSS/JS | SOURCE VERIFIED; visual QA pending, assistant |
| Preserve existing header, footer, CSP, noindex | Remote branch comparisons with base `f0cc88d`: header/footer/CSP unchanged | VERIFIED, assistant |
| Preserve and integrate three new original illustrations | Exact originals and 6 optimized derivatives packaged in chat artifact `okh-under-construction-review-package.zip` | BLOCKED: binaries not in canonical repo, maintainer |
| Keep generated output synchronized | Source body occurs once in root page; no local full-repo generator | PARTIAL: `build-site.py --check` not run on final artwork revision, maintainer/CI |
| Validate responsive/a11y/links/security | Package HTML/parser/hash checks PASS; fallback image paths verified tracked | PARTIAL: browser, CI and final revision checks outstanding |
| Review/merge/deploy | Draft PR #252 only; `main` unchanged; Pages main-push validation/deploy requires maintainer publication approval | BLOCKED by artwork and approval |
| Durable evidence + exact-thread archive | This record and original-preserving ZIP; no project evidence-home transfer verified | BLOCKED — do not archive |

## Evidence tiers, constraints and continuation

**CONFIRMED**: Initial PR changed only template and generated page, six internal hrefs use the canonical routes, one H1, no AskJamie copy in the new body, existing GitHub images resolve in the repo tree. Existing open PRs #251 and #219 are separate scopes. Normal workflow uses PR review then approved merge to GitHub Pages. No Replit paid mode or release was used.

**CONFIRMED**: Original user image SHA-256 hashes: empty wide `dc11404e67ba953b3d3e11e59e3d92ff9940eee97bf89dd545995e606b18ee0b`; MurderBird wide `35bb43e2568dd899f5e0b2ac92368d9bc2a195b109c77fd33f63f05236ea0bea`; square `0aefbd694c34d357d661385df11fc6c547b3b89ba8dbec6d82b2346bf1e0793c`. ZIP includes original files separately from optimized website images.

**UNKNOWN**: Whether the supplied images are persisted in an authorized remote project evidence location; exact final-build/PR CI result; real browser accessibility and viewport behavior; post-merge Pages release/live-edge; exact thread archive action. An archived chat or a ZIP link alone would not prove remote artifact preservation.

**Pass A:** Source/header/footer/CSP parity and image-path checks passed for the fallback branch; local package source parsing, internal link paths, image presence/size and original SHA checks passed. Full build, screenshots and live deploy NOT RUN.

**Pass B (adversarial):** Original three-image requirement is not met by fallback branch, earlier standalone HTML proposals are not generation-safe, original uploaded HTML/CSS were unavailable to inspect, and no user approval to merge exists. Therefore do not claim completion or archive.

**Artifact paths:** `site-src/pages/under-construction.main.html` (authoritative), `under-construction.html` (generated), `assets/img/under-construction/forge-{workshop-empty-wide-1536,murderbird-wide-1536,murderbird-square-1024}.{png,webp}` (six optimized replacements in downloadable package), `original-artwork/` (original sources in package), this handoff under `docs/handoffs/`.

**Next action:** In existing authorized checkout, reconcile workers and PR #252, copy intended source and six optimized artwork files from chat-delivered ZIP, run `python3 scripts/build-site.py` and `--check`, project link/CSP/site/browser checks, inspect diff, stage only in-scope outputs, commit to the draft PR, secure maintainer review and merge approval, verify workflow + exact deployed revision and live edge, store original sources in approved durable evidence location, refresh both independent QA passes and this ledger. Keep Replit preview-only, no new clone, force push, paid credit, or cleanup.

This handoff is a **summary**, not a lossless transcript.
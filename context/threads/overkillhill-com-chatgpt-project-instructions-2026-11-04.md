---
title: "OverKillHill.com ChatGPT Project Instructions and Thread Closeout"
primary_topic: "OverKillHill.com project separation and site-specific operating instructions"
source_platform: "ChatGPT"
capture_mode: "unknown"
completeness: "partial"
source_title: "Web: OverKillHill.com - Instructions (project listing; exact conversation title unverified)"
source_date: "unknown"
source_locator: "ChatGPT conversation ID and URL not exposed to this session"
retention_decision: "public-safe"
source_independence: "pass for the approved instruction set; not a lossless conversation archive"
artifact_type: "thread-closeout-and-instructions"
capture_date: "2026-11-04"
thread_key: "web-overkillhill-com-instructions"
thread_id: "unavailable"
---

# OverKillHill.com project instructions and thread closeout

> **Scope:** This record preserves the OverKillHill.com spinoff instructions and the decisions that led to them. It is public-safe documentation, **not** a ChatGPT Project-setting write, a website change, or proof that this chat has been archived.

## 1. Project instructions: maintained, copy-ready version

**Identity and purpose.** This ChatGPT Project concerns only the public website at https://overkillhill.com and its source repository, https://github.com/OKHP3/overkill-hill. Maintain a fast, accessible, static-first, GitHub Pages-compatible portfolio and publication site for OverKill Hill P³. Favor the existing HTML/CSS/vanilla-JS architecture, not a framework migration. Content, design, and engineering changes must respect the existing brand and repository rules.

**Boundaries.** Keep website implementation here. Other websites, including https://glee-fully.tools and https://askjamie.bot, have their own project scopes. Common UI tokens, styles, utilities, and scripts are a separate intended common-elements workstream. **Current-state exception:** this repository still documents `assets/css/theme.css` and `assets/js/app.js` as shared foundations and `docs/cross-site-sync-plan.md` identifies OverKill Hill as the historical cross-site sync authority. Do not assume a separate shared repository has taken ownership. Do not migrate, fork, or duplicate shared assets without a verified cross-project decision and compatibility checks. Site-specific changes must not silently change sibling websites.

**Authoritative sources, in order.** Follow the current repository `AGENTS.md`, `README.md`, `docs/site-maintenance-map.md`, `docs/publishing.md`, active `site-src/pages.json`, and `sitemap.xml`. The earlier ChatGPT project sitemap is planning context, not a reason to remove newer live routes. When a source disagrees with an old instruction, identify the conflict before editing. Preserve clean, trailing-slash folder routes where established, and redirects for moved routes.

**Route portfolio from the approved planning brief.** Home `/` (The Forge), `/projects/`, `/found-ry/`, `/projects/homestead-r/`, `/projects/un-nocked-truth/`, `/projects/pathscrib-r/`, `/manifesto/`, `/writings/`, `/writings/magnus-saga/`, `/writings/biases-as-constants/`, `/ponders-concepts/`, `/prompt-gallery/`, `/universe/`, and `/about/`. The Found-Ry planning brief names Cage-Fight-Ry, Phenomould-R, PromptAscend-R, ToneStrik-Ry, TellePrompt-Ry, and StructRefino-Ry as sections, not automatically separate pages. This is a *planning inventory*, not an assertion that every route currently ships or a complete live route inventory. Validate existence, canonical paths, and newer live pages against the repository before changing them. Preserve published routes omitted from the older planning brief.

**Authoring.** A sitemap page corresponds to a route and published `index.html`; sections have stable heading IDs. Many English published pages are generated from `site-src/` by `scripts/build-site.py`. Determine whether a target is generated before editing; change the appropriate authoring source, not only its rendered HTML. Keep the `site-src/pages.json` manifest, search index, universe map, locale boundaries, and sitemap consistent when a change affects them. Eleventy is not an assumed dependency or an approved replacement for this existing pipeline.

**Global experience.** Maintain navigation consistency with Forge, Our Projects, Manifesto, Universe, About, and existing Contact or Legal entries where applicable. Prefer semantic HTML, keyboard-operable controls, meaningful accessible names, focus visibility, reduced-motion handling, mobile readability, and efficient asset delivery. Use existing brand tokens rather than proliferating parallel design systems. Restrict JavaScript to necessary interaction.

**Publication and secrets.** `main` is the protected release branch. Work on a review branch, run the relevant repository validation, and open a PR. Do not merge or publish without the required owner authorization. GitHub Pages is the only approved publication target; Replit is a Free development preview, not a deployment destination. Verify published behavior at the exact deployed revision when publication is authorized. Never commit secrets, private archives, private personal records, or employer-confidential content to this public repository. Preserve repository-owned, uncommitted, and concurrent work.

**Thread and delivery contract.** Use one thread per route or a clearly bounded global-shell/build concern. Name threads `OKH | /route/ | change-summary` (example: `OKH | /manifesto/ | hierarchy and accessibility`). Provide the objective, authoritative files inspected, exact repo-relative paths, scoped patch/diff, checks and results, changed-state risks, and unresolved questions. Route out-of-sitemap proposals to backlog rather than silently implementing them. Avoid claiming completion from assistant prose, draft PRs, or unrelated green tests.

## 2. Provenance, scope, and coverage

- **Original request:** Split a previously combined website conversation Project into a common-elements area plus three site-specific projects for OverKillHill.com, Glee-fully.tools, and AskJamie.bot, with instructions for each.
- **Later direction:** The user narrowed this conversation to `Overkillhill.com`; the later assistant answer supplied OverKillHill.com-specific instructions. Therefore this closeout covers that site only. Sibling project instructions appeared in an earlier assistant response but their ChatGPT Project activation and any separate project creation are outside this thread's verified scope.
- **Missing earlier source:** The user stated that the original custom instructions were no longer available. The earlier assistant's file references and citations are not a substitute for those originals. No historical instruction payload, lossless transcript, original sitemap attachment, or full ChatGPT export was available during this review.
- **Reviewed in this capture:** Visible request and assistant responses in this conversation; current project-specific instruction context; current public GitHub repository metadata and documentation; selected OKHP3 skillz instructions (session-handoff, evidence-standard, artifact-validation, ChatGPT thread extraction); linked Notion routing hub read-only. No files were attached to the current conversation. Notion was consulted only to verify identity and routing context, not treated as a content-authoring destination.
- **Coverage boundary:** This is a compact, public-safe extraction of accessible messages and verified repository context. Hidden branches, exact message timestamps, native conversation ID, any unavailable earlier files, local Mac/Windows clone state, and ChatGPT Project-setting edit history are not captured.
- **Thread identity:** Stable descriptive key `web-overkillhill-com-instructions` is a local matching key, **not** a verified ChatGPT conversation ID. The source title appears in a project conversation listing but could not be confirmed against the chat URL.
- **Environment:** GitHub remote `OKHP3/overkill-hill`, public, protected `main`; base SHA `f0cc88d77bdf3102308f9b203edc7499e904f650` at inspection on 2026-11-04. Review branch `docs/okh-chatgpt-project-instructions-20261104`. Local working folder, dirty state, worktrees, and Replit live checkout are unknown because no local checkout or Replit workspace was opened.

## 3. Completion ledger

| Obligation | Source | Acceptance / current evidence | Owner | Status |
|---|---|---|---|---|
| Draft instructions for three sites | Initial user request | Earlier assistant message supplied three separate drafts; no ChatGPT Project creation verified | User / sibling project owners | **Retired for this thread by later site-specific narrowing; sibling Project activation uncertain** |
| Prioritize OverKillHill.com | Later user request `Overkillhill.com` | Follow-up assistant supplied site-specific instructions; current Project context also has OKH-only guidance | This thread | **Verified complete as text** |
| Reconcile instructions with active repo | Closeout request | Current `AGENTS.md`, `README.md`, `docs/site-maintenance-map.md`, `docs/publishing.md`, `.replit`, and workflow read; corrections incorporated above | This thread | **Verified complete for reviewed sources** |
| Preserve the reusable instructions and decision rationale | Closeout request | This document is the proposed durable record under established `context/threads/`; remote readback and PR validation must confirm preservation | This thread | **Verified present on the dedicated review branch; integration pending** |
| Rework shared-code ownership | Initial architecture motivation, but not requested as a website code change | Historical shared CSS/JS authority conflicts with intended common-elements separation; no migration or synchronized sibling change authorized | Common-elements workstream | **Explicitly deferred, not silently implemented** |
| Modify or republish site code | Not required by this thread | Documentation-only scope; no site code, DNS, domain, deployment, or Replit publication changes intended | Other site-change threads | **Not in scope** |
| Two quality checks, durable receipt, safe archival | Closeout request | Artifact validation and independent requirements review are required; archiving needs a supported action and all final gates | This thread / user for UI archive | **Artifact checks complete; integration and native archive action pending** |

## 4. Artifact and evidence manifest

- **Primary artifact:** `context/threads/overkillhill-com-chatgpt-project-instructions-2026-11-04.md`, in `OKHP3/overkill-hill`.
- **Branch:** `docs/okh-chatgpt-project-instructions-20261104` based on `f0cc88d77bdf3102308f9b203edc7499e904f650`; protected `main` remains untouched by preparation.
- **Authoritative reference files:** `AGENTS.md`, `README.md`, `docs/site-maintenance-map.md`, `docs/publishing.md`, `docs/cross-site-sync-plan.md`, `site-src/pages.json`, `sitemap.xml`, `.github/workflows/pages.yml`, `.replit`.
- **No generated website assets or transcripts:** This documentation snapshot is not a lossless ChatGPT export. It preserves the substantive instruction set and decisions, not hidden chat metadata or unavailable original files.
- **Exclusions:** No passwords, private personal records, employer information, local file paths, or Notion private page contents are copied here.

## 5. Verification, holds, and continuation

**Pass A, artifact checks:** Compare this file on the exact review branch with this draft, validate Markdown structure and the instruction/ledger/manifest sections, check that only this thread-owned path changed, and verify no secret or private content is included. Site builds and browser checks are not substitutes for this documentation review.

**Pass B, adversarial requirements review:** Reconcile the original three-site request, the later OverKillHill.com narrowing, missing original instructions, active generated-site architecture, shared-assets discrepancy, PR and publishing authorization boundaries, and thread-archive gate. Do not mark missing local checkout, unavailable attachments, absent integration, or no archive tool as passes.

**Recorded pass A (2026-11-04, artifact/readback): PASS for documentation artifact.** Direct GitHub file readback found the full committed Markdown and expected metadata, instruction section, coverage record, completion ledger, manifest, and handoff. Regex-based content checks found no em dash, known credential patterns, private IP examples, or accidental secrets. GitHub comparison against `main` reported exactly one added file, no deletions, one commit at the first check, and no changes to published pages or workflow files. The first artifact commit was `92c48cfe0dd674aed503559d317c55fedae5e697`; this record's final documentation-only update requires readback again. Browser tests, site rebuilds, and Replit runtime checks are **NOT RUN** because the target is nonserved Markdown, not a site behavior change.

**Recorded pass B (2026-11-04, separate adversarial requirements review by the same assistant): PASS for honest scope accounting, not external independent review.** The initial three-site request was compared with the later OKH-only direction and the previously delivered instructions. The original custom instructions, chat ID, and historical attachments are not recoverable, and the document does not claim otherwise. The planned route list was compared with the actual current `sitemap.xml`: **6 of 14** listed planned routes appear there; **8 of 14 are not listed**. This is not proof that the other routes are broken or unpublished, and the project instructions deliberately label that list as a planning brief rather than the live inventory. The repo's newer paths, including `/writings/murderbird/`, `/skillz-forge/`, and `/prompt-forge/`, are not removed from the instructions' scope by omission from the old brief. The historical shared CSS/JS authority conflict is explicitly reserved for separate ownership review. No ChatGPT account-level settings, default-branch commits, website deployments, or conversation archival are claimed.

**Known holds:** The native ChatGPT conversation ID and archive action are unavailable in the connected toolset. Local checkout and active worktrees were not accessible. A pull request remains a review handoff until merged through the owner's authorized workflow. Replit runtime verification is not applicable to the documentation-only change; no Replit action is dispatched. The original custom instructions remain unavailable.

**Next action:** Review the PR containing this record, merge when authorized and its exact revision satisfies required checks, then confirm the project instructions are still present in the designated ChatGPT Project. Archive this *exact* ChatGPT thread from its own conversation menu only after every applicable gate is satisfied; this file does not prove archive state. On rerun, find this filename and branch first; update the existing record instead of creating a duplicate.

# Shared foundation alignment handoff: 2026-10-13

## Status and boundary

**Planning handoff only. This is not approval of a release baseline.** No
shared source files, site pins, or the existing release record were changed.
The purpose of this packet is to give an external coding owner a bounded
three-site alignment task with reviewable evidence and acceptance criteria.

The existing release record at
`docs/audit/foundation-release-2026-09-09.md` and the pins in
`.github/workflows/validate.yml` remain unchanged. Do not update either until
the compatible source has been reviewed, site changes have passed their own
checks, immutable verification passes, and the owner separately approves the
baseline.

## External task-packet metadata

- **Project and verified origins:** OverKill Hill P³; <https://github.com/OKHP3/overkill-hill>,
  <https://github.com/OKHP3/Glee-fullyTools>, and
  <https://github.com/OKHP3/AskJamie>.
- **Replit project URL:** not available in this session; do not infer one.
- **Selected task:** “Approve a current shared-foundation release baseline,”
  assigned in this session. The board reference is intentionally not copied
  into this repository document; current external board state was not
  independently inspected.
- **Original criteria:** review the compatible foundation and sibling pins;
  update the release record only after explicit owner approval and a passing
  immutable cross-site check.
- **User-directed scope amendment:** prepare a versioned alignment plan and
  acceptance criteria for external coding; make no source changes in Replit;
  leave release record/pins untouched; keep baseline approval separate.
- **Design review:** not applicable; this task changes no user interface.
- **Intended outcome:** external implementation in existing Windows mirrors,
  with three scoped PRs and per-site checks; no merge or deployment in this
  handoff.
- **Ownership:** no external coding owner/session or shared cross-machine
  single-writer claim is established. The local packet does not transfer
  ownership or authorize source edits; the external owner must confirm a
  single-writer handoff before editing.
- **Board privacy:** this repository handoff excludes private board details and
  is not a cross-machine ownership lock.
- **Current limits and authority:** Free mode only; stop if quota-blocked; no
  paid upgrade, new clone/snapshot, Replit Publish, release-pin update, or PR
  merge authorized here.
- **Hosting / non-Git state:** the repository targets GitHub Pages. No
  deployment or live-site action is part of this handoff.
- **Follow-up proposals:** the Replit task board has separate proposed work
  for the three-site alignment PRs and later owner-approved baseline recording.
  Their board status is not treated as accepted or completed here.

## Evidence snapshot

The supplied revisions were checked against each repository's public `main`
ref on 2026-10-13. All three supplied full SHAs matched their respective
`refs/heads/main` at that check:

| Site | Immutable main revision | SHA check |
| --- | --- | --- |
| OKH | `72619190af8b5f65cc6f6d64c0e225991f8b1558` | confirmed |
| Glee | `0aeeb5ab72582266ffcd0b5392a322b8a72e4ef4` | confirmed |
| AskJamie | `d4c0dcbdf7087c96c041e15641630aa8426642b1` | confirmed |

### Immutable foundation fingerprint matrix

These are SHA-256 hashes and committed byte counts read from the exact revisions
above, not from mutable site working trees.

| Foundation file | OKH | Glee | AskJamie |
| --- | --- | --- | --- |
| `assets/css/theme.css` | `a6d303b4475c226da7f3542729fa3802acf917b9c6a79e6fc9953d20ba619780` (254,479 bytes) | `1b69c2a06f69c750ba38352d3f3a1220d48e092f676796d0473b66ed52de2c25` (242,823 bytes) | `aa2f071c247531c32690031ade3cf48903a31e9a0d37829b9546ecd754072121` (248,271 bytes) |
| `assets/js/app.js` | `170961adae719c355015208d83071f67f4d29c5ce2952cb7470576f01bbcf9c7` (61,476 bytes) | `9e7b7199582e2b730101f29a08e0860c0e81a7ff5eb452ca8f0bffbeea0e2413` (55,348 bytes) | `89a38b6320feea0f46dd94827f5c06525b197827534f7659994ba159a64050a5` (61,390 bytes) |
| `assets/js/mermaid-init.js` | `9104802f4a06e722758f541c789ffc5986ae7882af6a317e63a894f1fc3eb326` (14,084 bytes) | `19730e6371c9dc6845d94cd1a7b49c7c1796d131755676c8933e7d780ece4c7e` (13,537 bytes) | `751bc4e3fd552388ea58c57a66166ad9f9d18faef2d9777156e91de6ad0c01b5` (13,910 bytes) |

All nine fingerprints are distinct. The current three-site immutable
verification therefore cannot pass.

### Replit planning-checkout snapshot

- **Confirmed:** before creating this handoff, the isolated Replit planning checkout was clean at
  `8ae63957dbf9ea3559c970b83b9ff1a45375325a`. The handoff and a project-memory
  note are now the only uncommitted paths; no foundation source was edited.
  After fetching the canonical
  OKH `main` ref without pruning, it is 23 commits behind
  `72619190af8b5f65cc6f6d64c0e225991f8b1558` and has no Replit-only commits
  ahead of that base. Its three foundation files differ from current OKH `main`
  only by the OKH-only Mermaid label foreground correction and the joined-route
  search scoring addition.
- **Confirmed:** the running `python3 server.py` process is the only observed
  process matching the project's server, foundation sync, or Git-write
  commands. No active local foundation writer was observed.
- **Confirmed:** the public GitHub API showed zero open pull requests in each
  of the three public repositories at the time checked. This does not establish
  the absence of private work or other off-platform writers.
- **Confirmed:** `git worktree list` contains old entries marked prunable, with
  stale Git-directory pointers. No worktree cleanup was attempted. The sole
  stash changes only `assets/audit/links-report-2026-08-22.json`; it contains
  no stashed foundation edits.
- **Existing planning:** `.local/tasks/shared-runtime-divergence.md` already
  requires classifying each three-way difference and recording a compatibility
  design before changing files. Use it as context, not as evidence that a
  current sync has been completed.
- **Owner-reported, not independently checked here:** Windows mirrors are clean
  `main`, `0/0`. Use those existing mirrors for the external work; do not use
  the stale Replit checkout as the implementation base, and do not create a new
  clone or snapshot.

### Claims and remaining uncertainty

| Claim | Tier | Evidence | Consequence if false | Next check |
| --- | --- | --- | --- | --- |
| All current pinned foundation files differ across all three sites. | Confirmed | Immutable hashes above; exact `main` revisions resolve. | A redundant or incomplete alignment could be attempted. | Recompute hashes from exact PR merge commits before release verification. |
| Current OKH `main` is a useful integration starting point, but is not yet a compatible superset. | Proposal | It contains the newest observed OKH foundation and explicit OKH security behavior; sibling revisions contain unique changes listed below. | Choosing it as winner would discard sibling behavior or dependencies. | External owner classifies every material delta and records the chosen superset before edits. |
| The user's Windows mirrors have no local changes or commits outside `main`. | Unknown here | Owner supplied `0/0`; not directly inspected from this Replit session. | An external edit could overwrite unreviewed local work. | External coder rechecks status, branch, and exact SHAs immediately before editing. |
| No private PRs or off-platform writers exist. | Unknown | Public API showed no open PRs; GitHub App integration is unavailable in this session. | A parallel change could conflict with the candidate. | Check authorized GitHub/task surfaces before opening scoped PRs. |
| The v2 heat pages actually carry the loose-mode opt-in at the supplied revisions. | Unknown | The sibling initializers describe two such pages, but the exact page markup was not independently checked. | A merged runtime could change those diagrams' security behavior. | Locate and inspect the actual page markup at each supplied commit before changing Mermaid behavior. |
| The September release record still describes current publication/PR state. | Not confirmed | Its Glee row says a PR remains open; the current public PR listing returned zero open PRs. | Retaining stale publication evidence would misstate the release. | Reconcile exact merged/current site commits when a new baseline is approved. |

## Drift review and preservation map

### Theme stylesheet

- OKH `theme.css` now contains the self-hosted font-face block. The current
  OKH tree includes 13 WOFF2 files plus license/provenance files under
  `assets/fonts/`; neither sibling tree has `assets/fonts/` entries or
  `@font-face` rules. Do not propagate CSS that points to absent font assets.
  Either bring the required font files and provenance/license material into
  both siblings and verify their serving/CSP behavior, or keep the font block
  in an OKH-owned layer while preserving byte-identical shared CSS.
- Glee has its own story framing, reveal-state treatment, and Glee-scoped
  capability-transition styles. AskJamie has its own hero/BrandGuard styles,
  swipeable generated-map behavior, and AskJamie-scoped transition styles.
  Preserve those within their brand scopes; do not let either set leak into the
  other brand or the OKH default.
- Current OKH `main` adds a narrowly OKH-scoped Mermaid nested-label foreground
  rule. Preserve its site scope rather than applying it to sibling brand
  surfaces without evidence.

### Shared browser runtime

- OKH's shared runtime uses generated brand configuration; the sibling copies
  have direct brand detection and storage/color configuration. Preserve the
  distinct Glee and AskJamie body-class hooks, storage keys, colors, and
  persistence behavior. Do not share stored theme preferences between brands.
- Current OKH `main` adds joined-hyphenated-route search scoring without
  rewriting displayed titles. Port this behavior only with its regression test.
- Glee has a Glee-specific enhancement module and service worker. AskJamie has
  its own analytics loader and event module. Keep those site-owned files,
  markup, consent/analytics behavior, search index contents, generated CSP,
  import maps, and cache/version references site-owned.
- There is a specific search-version boundary conflict to resolve: current
  Glee `app.js` embeds `?v=4bbebbc1` in its search-index URL, while the approved
  September release notes say the shared search URL is stable and cache
  busting belongs in generated HTML/service-worker references. Prefer the
  recorded boundary: keep the runtime URL stable and move any needed
  versioning to the site-owned generated references.
- AskJamie has its own locale fallback and search suggestions. Glee and
  AskJamie search indexes are not interchangeable with OKH's indexes. Keep
  index selection and site-specific copy under explicit site behavior while
  retaining the stable shared runtime contract.

### Mermaid runtime and trust boundary

- The current self-hosted vendor versions are OKH **12.1.0**, Glee **12.0.0**,
  and AskJamie **11.17.2**. All three initializers import the local path
  `/assets/vendor/mermaid/mermaid.esm.min.mjs`.
- Preserve the OKH self-hosted Mermaid 12.1.0 trust decision. Do not downgrade
  OKH or switch it to a remote CDN. The current Glee and AskJamie versions are
  12.0.0 and 11.17.2; test the reconciled initializer against each site's
  existing local bundle before deciding whether either sibling needs a version
  change. If a bundle changes, update its local license/chunks with it.
- Keep Mermaid strict by default. The sibling initializers describe a
  `data-mermaid-security="loose"` opt-in on two v2 heat pages; verify those
  pages' actual markup at the supplied commits before changing the behavior.
  Preserve Glee's keyboard-link ordering and AskJamie's render-failure status,
  or explicitly replace them with equivalent tested behavior.
- Do not overstate the allowlist: current OKH comments say it filters the
  source `click NODE "URL"` syntax, not every Mermaid-created SVG URL anchor.
  Retain that distinction in the implementation and tests.

## Smallest proposed alignment

**Proposal:** use OKH `main` at
`72619190af8b5f65cc6f6d64c0e225991f8b1558` as a provisional integration spine,
not as an approved winner. Before any source write, have the external coder
produce a short hunk-level reconciliation table for the three foundation files:
shared behavior to retain, site-scoped behavior to preserve/rehome, and obsolete
behavior to remove with evidence. The result must be a reviewed compatible
superset, not a blind copy from one site.

1. Reconfirm ownership and exact input SHAs in the existing clean Windows
   mirrors. Preserve local work; do not create clones/snapshots or update the
   Replit checkout.
2. Classify CSS differences and decide how the OKH self-hosted font dependency
   is satisfied on Glee and AskJamie before adopting the shared stylesheet.
3. Reconcile runtime differences while preserving per-brand theme state,
   site-owned analytics/enhancement modules, distinct search-index behavior,
   the stable search URL, and Glee's generated cache-buster/service-worker
   boundary.
4. Reconcile the Mermaid initializer and vendor compatibility together. Keep
   OKH's local Mermaid 12.1.0, strict-by-default behavior, reviewed explicit
   opt-ins, and sibling accessibility/failure behavior. Upgrade a sibling
   bundle only if compatibility evidence requires it.
5. Open scoped, protected PRs in OKH, Glee, and AskJamie. Regenerate only each
   site's own derived HTML/CSP/import-map/cache/service-worker/index outputs.
   Do not merge or publish as part of this handoff.
6. After each PR is reviewed and merged by its authorized owner, record the
   final immutable merge commits and run the cross-site checks on those exact
   commits. Only then request separate owner approval to update the release
   record and CI pins.

## Acceptance criteria for external coding

- The change review names every material CSS, JS, and Mermaid delta from each
  of the three input revisions and classifies it as shared, brand-specific, or
  obsolete with evidence.
- The chosen source is an immutable full commit on OKH and represents the
  reviewed compatible superset. Glee and AskJamie retain required scoped
  styling, control hooks, storage keys, search behavior, and unique modules.
- Shared search runtime behavior uses the stable URL contract. Site-specific
  cache busting, CSP, import maps, search indexes, HTML, and service-worker
  references remain generated/owned by the relevant site.
- Font URLs resolve to local files on all three sites, or the font-face rules
  are kept out of the shared CSS. Font license/provenance is retained; no
  broken font requests are introduced.
- All three sites use compatible self-hosted Mermaid assets with the
  reconciled shared initializer; OKH remains on local Mermaid 12.1.0. A sibling
  version change is justified by compatibility evidence and includes its
  matching local bundle/license. Strict mode remains the default; reviewed
  loose-mode pages, link handling limits, keyboard accessibility, and failure
  messaging are tested.
- Each site passes its own site validation and relevant theme, search, Mermaid,
  security/CSP, cache/version, service-worker, responsive, and accessibility
  checks against the exact reviewed PR head. Generated changes are scoped to
  the site that owns them.
- After merges, `scripts/sync-foundation-files.py --verify` passes using the
  exact full commit SHA for the reviewed OKH source and all three final site
  commits. The actual-markup cross-site browser check also passes against those
  immutable revisions.
- The release record and CI pins remain unchanged until a separate explicit
  owner approval after the above evidence exists. A passing plan or PR does not
  itself approve a release.

## Next executable external handoff

Use this packet with the external coding owner and the already existing Windows
mirrors. Begin with read-only checks of each mirror's branch, clean status, exact
SHA, current writers, and protected-PR path. Then produce the hunk-level
reconciliation table before editing. Use the three revisions in this document
as the immutable comparison inputs; recheck that each is still the intended
base at execution time.

The isolated Replit planning checkout at the snapshot above is not an
implementation base: it was 23 commits behind the recorded OKH `main`; its only
uncommitted paths were this handoff and a project-memory note recording the
requested Mermaid trust boundary. This is historical task-checkout evidence,
not a statement about the primary Replit checkout after task application. No source
changes or PR merges were made in this Replit task. External work should proceed
as a separately assigned coding step; this packet does not authorize merging or
publishing. The desired return is three scoped PR links, per-site test receipts
tied to exact PR heads, and an immutable cross-site verification report. The
separate baseline-approval step remains pending.

## Validation record

- Exact ref check against all three public `main` refs: **PASS** at the snapshot
  time above.
- Immutable fingerprint comparison: **FAIL as expected**; all nine hashes are
  distinct, so there is no current byte-identical three-site foundation.
- Replit source edit / sync / pin update: **NOT RUN by design**.
- Windows-mirror status: **UNKNOWN in this session**; the clean `0/0` state is
  owner-reported and must be rechecked by the external coder.
- Protected-PR checks, site validation, and actual-markup cross-site browser
  audit: **NOT RUN**; they require the reconciled PR heads.
- Local `python3 scripts/validate-site.py`: **PASS** with no errors; it
  reported 32 HTML warnings, primarily missing analytics tags and JSON-LD in
  translated pages. Voice warnings were within the reviewed baseline.
- GitHub CI: **NOT RUN**; there were no PR heads to validate.

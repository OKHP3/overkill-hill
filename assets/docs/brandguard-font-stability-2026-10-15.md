# BrandGuard font loading and enlarged text

## Change

PR #219 originally tried to match fallback and loaded line counts with narrow
viewport bands, smaller type and tighter tracking. The remaining movement
reached downstream quotations and changed again when text was enlarged.

The revision replaces those bands with scoped aliases for the same Baloo 2,
Open Sans and Kalam font bytes. The shared runtime imports
`assets/js/brandguard-fonts.js` only for BrandGuard pages. It registers local
optional faces before first contentful paint. If it arrives late, or paint
timing is unavailable, it keeps the already visible fallback for that visit. Available
fonts may render the brand faces; a font that misses the first-paint deadline
leaves readable fallback text for that page visit. It does not hide content
while waiting or switch families after the reader starts reading. Ordinary
AskJamie, Glee and OKH pages keep their existing policy.

The full shared theme restores canonical hero type sizes and tracking, lets
breadcrumbs wrap, uses a relative body size, and keeps BrandGuard navigation
in normal flow. This prevents an enlarged header from overlaying content or
anchor targets. The native hub's more specific critical-shell font declarations
are superseded when the full theme becomes active. The separate critical-to-full
stylesheet activation is outside the font-arrival acceptance claim.

## Regression contract

`tests/test-brandguard-font-browser.mjs` reads all 14 native BrandGuard routes
from frozen AskJamie revision `7d719683bf1fe416be4c2aba9cb676146268be04`.
Candidate foundation bytes are projected in memory; the sibling checkout is
not rewritten. Font responses use the byte-verified local assets and their retained OFL licenses.
The native CSP remains active. A separate five-case boundary gate verifies
that ordinary OKH, Glee and AskJamie pages do not request the BrandGuard faces
that all declarations respect a self-only font policy, and that delayed
loader initialization cannot move visible text. Six loader timing/scope unit
cases cover the early, late and unsupported-platform branches.

The matrix has 448 states: Chromium and WebKit; 320, 360, 390, 401 and 900px;
16px and 32px root sizes; delayed fonts throughout, plus immediate, failed and
predecoded-font witnesses at 390px. Delayed-font geometry is checked before
and after arrival, including every downstream quotation. It also checks real
body enlargement, text and container bounds, header positioning, missing local
assets and page errors. Predecoded witnesses exercise canonical glyphs even
when an immediate response misses the optional deadline; Chromium verifies
that the heading actually paints a custom font.

The new test fails against the original PR on the previously reviewed Dollar
General 360px witnesses in both engines. Native breadcrumb keyboard/focus
checks and ordinary-brand controls remain separate regressions.

The validation workflow runs this test and retains its JSON report. Its frozen
AskJamie input is a test fixture, not an approved foundation or release pin.

## Boundaries

This is technical regression evidence, not human assistive-technology, device
or owner acceptance. It does not establish every fractional width, operating
system or possible font arrival order. The upstream OFL license bytes are
retained unchanged, including their original trailing spaces.

Shared foundation validation uses both the retained approved pins and private
immutable projections onto current sibling source. Matching projection bytes
and browser behavior do not mean the sibling repositories have adopted them.
A future foundation adoption must include `assets/js/brandguard-fonts.js`
and the font/license companions listed in `assets/fonts/brandguard-provenance.json`.
The three-file foundation sync alone is insufficient for BrandGuard pages.
The scoped import keeps these bytes outside ordinary pages' request graphs
and preserves the existing source-budget limits. No publication, Mermaid
update or release/foundation pin promotion is included.

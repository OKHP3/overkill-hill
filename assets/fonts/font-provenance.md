# Self-hosted brand fonts

These eleven original WOFF2 files were preserved from the editor commit and verified byte-for-byte against official Google Fonts responses on September 20, 2026. `provenance.json` records the CSS request, exact source URLs, SHA256 values, and pinned license sources. Each family carries its unmodified SIL Open Font License 1.1 text.

Alfa Slab One is static weight 400. DM Sans has a variable `wght` axis from 100 to 1000; JetBrains Mono has a variable `wght` axis from 400 to 800. The inherited filenames contain 400, but those two families are variable fonts. Shared CSS retains the site's requested weights (DM Sans 400/500/600 and JetBrains Mono 400/700). No font binary was converted or modified.

To refresh, review the official Google Fonts CSS and font bytes, update the source manifest and licenses, and validate real font loading and typography in the browser. Do not replace a file merely to match a hash. Runtime font URLs are root-relative so the live-edge verifier checks their MIME types. The release allowlist ships WOFF2 files and accompanying license text; authoring provenance stays in the repository.

## Scoped BrandGuard fonts

The seventeen `brandguard-*.woff2` subsets preserve the existing Baloo 2,
Open Sans and Kalam bytes declared by the AskJamie BrandGuard pages. They are
local companions to the shared stylesheet's BrandGuard-only font aliases and
the scoped `assets/js/brandguard-fonts.js` loader. They do not replace OKH's three canonical font families. Ordinary
OKH, Glee and AskJamie pages do not select or request these aliases.

`brandguard-provenance.json` records the October 15, 2026 retrieval, exact
upstream URLs, SHA256 values and unchanged OFL licenses. Local delivery keeps
the shared CSS compatible with OKH's self-only font CSP; no policy allowance
or Mermaid release pin changes are required. No font binary was converted.
The native-page regression harness reuses these bytes offline and verifies
normal, enlarged, delayed, immediate, failed and predecoded-font witnesses.

The loader catalog retains the family, weight and Unicode ranges in the
recorded Google Fonts CSS. Update its references and the provenance manifests
together when deliberately reviewing new source bytes. Ordinary pages do not
import the loader or pay its font transfer cost; source-budget limits are
unchanged. A loader that arrives after first contentful paint, or cannot
observe paint timing, retains fallback rather than changing visible text.

Pending faces remain outside the active font set. Only Unicode subsets needed
by rendered page text are decoded; the ready class is applied atomically when
all required faces finish before the frame deadline. Late or failed decoding
retains the explicit system-font stack, including on engines whose optional
font timing differs. No source-budget limit or movement threshold is relaxed.

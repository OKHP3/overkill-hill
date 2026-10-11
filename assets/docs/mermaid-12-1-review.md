# Mermaid 12.1 runtime review

Reviewed October 11, 2026 for the technology-alert reconciliation. This record
supersedes the upgrade recommendation, not the historical observations, in the
October 2 preparation reports. Browser and release results are separate gates.

## Publisher provenance

- [Official release](https://github.com/mermaid-js/mermaid/releases/tag/mermaid%4012.1.0): October 2, 2026; tag commit `21f72f07ea22c0af48a3149c550654e80d8e40cb`.
- [npm metadata](https://registry.npmjs.org/mermaid/12.1.0) and [publisher tarball](https://registry.npmjs.org/mermaid/-/mermaid-12.1.0.tgz) fetched October 11, 2026.
- Verified SHA-512: `sha512-wlVCp+8eTupfCeeFvoZNNiTuHrvag0P2jz/ILgb/f/6jkVokUefOcujefi8qUe/j2asHiSePncVsz/xzzA80LQ==`.
- Tarball SHA-256: `3e516f33246e1a6a5bc5ebcabd35434669b487c3b3791f9b0466aa2c254d004a`; 25,936,795 bytes.
- All 1,329 archive entries are regular files with unique package-relative paths. No archive extraction API, package installation, or package scripts were used.
- Selected publisher content is the complete `mermaid.esm.min.mjs` entry, its minified ESM chunks, and LICENSE: 106 files and 5,393,458 bytes. This is 65,460 bytes smaller than the previous publisher selection.
- Static parsing with the existing Playwright Babel parser verifies 105 reachable modules and 948 relative import references. There are zero missing, external, bare, nonliteral, or unreachable module imports in this graph.

The one retained publisher archive, per-file SHA-256 ledger, and module graph
are stored in the owner's existing OverKill Hill exports project under
`operations/mermaid-review/`. No extracted candidate tree or source snapshot
was retained. The earlier Windows preparation directory contains its two
reports, but not the referenced package or browser inventories; those reports
were not used as fresh package verification.

## Compatibility and security review

The [tagged comparison](https://github.com/mermaid-js/mermaid/compare/mermaid%4012.0.0...mermaid%4012.1.0)
contains 111 commits and 121 changed files. The release adds default-enabled
ELK feedback-edge orientation, packet bit ordering with the existing ascending
default, and fixes for repeated subgraphs, sequence syntax, labels, partial
theme overrides, and frontmatter parsing cost. Parser updates remove the
reported vulnerable lodash-es 4.17.23 dependency. This is an upstream dependency
fix, not evidence that the site's authored diagrams were exploitable.

The [tagged ELK renderer](https://github.com/mermaid-js/mermaid/blob/21f72f07ea22c0af48a3149c550654e80d8e40cb/packages/mermaid/src/rendering-util/layout-algorithms/elk/render.ts)
skips its new feedback-edge orientation when `elk.orientFeedbackEdges` is
explicitly false. The two authored ELK heat examples need that scoped setting
if the previous routing is to be retained. Keep their authored ELK and look
choices, and retain existing Dagre/classic defaults elsewhere. Other ELK label
fixes can still change geometry; rendered comparison remains necessary.

The [tagged schema](https://github.com/mermaid-js/mermaid/blob/21f72f07ea22c0af48a3149c550654e80d8e40cb/packages/mermaid/src/schemas/config.schema.yaml)
still defaults to strict and protects `securityLevel` from diagram directives.
`config.ts` is unchanged in the tagged comparison. The flowchart database diff
changes repeated-subgraph handling, not its callback or URL-link handling.
This is a scoped compatibility review, not a comprehensive upstream security
audit. Keep the README's corrected strict-mode/URL-link distinction and
inactive custom allowlist description; do not enable loose mode to activate
that filter. No shared initializer, theme, CSP permission, or click policy is
changed by the vendor replacement.

The package still requires Node >=22.12.0. The existing Mermaid 12 ES2024
browser floor remains; this upgrade does not newly establish older-browser
support. Registry integrity and publisher bytes were verified; npm signature
and provenance-attestation cryptographic verification were not performed.

## Validation boundary

Publisher integrity and static graph checks pass. After the integrating review
captured its fresh 12.0 browser baseline, all 106 selected publisher files were
installed and compared byte-for-byte with the verified archive. Superseded
hashed modules were removed only after the complete new graph was verified.
VERSION and the embedded entry version both read 12.1.0. Actual-page
rendering across all diagram routes, light/dark themes and phone/desktop
widths, ELK geometry comparison, generated-output checks, CSP, protected CI,
and deployed verification belong to the integrating release review.

The local integrating review passed all eight diagram routes at 1440px and
390px in explicit light and dark themes: 32 states, all 26 diagram nodes
rendered, and zero document overflow. Captured SVG viewboxes, node text and
transforms, edge paths, and links match the fresh 12.0 baseline exactly in all
32 states, including both ELK examples with the scoped false setting. Focused
CSP browser QA passed eight routes and 20 initializer-managed diagrams with
zero route failures; the universe diagrams rendered in the separate actual-page
comparison. Cross-origin resources blocked by that offline QA are recorded as
warnings, not upstream availability failures. Generated HTML, search and CSP
checks and structural validation pass. Protected hosted CI and deployed
verification remain required before accepting this candidate on main.

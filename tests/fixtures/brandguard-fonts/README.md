# BrandGuard font replay fixtures

This test-only manifest and cached stylesheet are excluded from the site release.
They replay the local font assets under `assets/fonts/` and reproduce the
fonts declared by the native AskJamie BrandGuard pages at immutable revision
`7d719683bf1fe416be4c2aba9cb676146268be04`. `manifest.json` records every URL
and byte hash. The CSS was retrieved October 15, 2026 with a Chromium user
agent; the returned WOFF2 subsets retain their upstream family names, weights
and Unicode ranges. Each family retains its upstream OFL license with the local assets.

The candidate loader decodes needed faces outside the active font set and
adopts them atomically only before the next frame and first contentful paint.
A ready class then enables the BrandGuard family aliases. Late or unsupported
initialization retains fallback for the visit. It uses local copies of the
same font bytes, without adding a remote font requirement to the shared CSS. Other brands and ordinary AskJamie pages keep their font
policy. Fast fonts may render the canonical brand faces; late fonts retain
the readable fallback for that page visit. This deliberately removes a late
font swap instead of trying to predict line counts with narrow pixel bands.
See the [CSS Fonts specification](https://www.w3.org/TR/css-fonts-4/#font-display-desc).

Run `node tests/test-brandguard-font-browser.mjs` with
`BRANDGUARD_SOURCE_REPO` pointing at a Git repository containing the exact
source revision. The runner reads native HTML and assets with `git show`,
projects candidate foundation bytes in memory, and replays integrity-checked
font responses offline with the original page CSP. It requires Chromium and
WebKit. Source objects are fetched by CI as test inputs; the accepted
foundation and release pins are unchanged.

The matrix covers all 14 BrandGuard routes, five widths, two root text sizes
and two engines. At 390px it also exercises immediate responses, failed fonts, and a separate
predecoded-font witness. An immediate response can still miss the optional
font deadline. The predecoded witness loads the same fixture bytes through
FontFace before measuring; Chromium verifies that canonical heading glyphs
actually paint through its platform-font inspection API.
The native critical-shell stylesheet activation completes before the first
measurement; this test does not claim to stabilize that separate activation.
Checks include normal and enlarged geometry before/after delayed font arrival,
all downstream quotation positions, horizontal overflow, text-container
bounds, nonsticky compact headers, real font loading in immediate cases, page
errors and missing local assets. Root enlargement is a rem reflow stress test,
not browser zoom or human assistive-technology acceptance. It does not prove
all fractional widths, font release orders, operating systems or devices.

Before opening the font gate, root-size and style geometry must match in four
consecutive 50ms samples (bounded to 20 attempts). This isolates WebKit inline
layout settlement from font arrival. Fonts remain held throughout; movement
after release still has the same one-pixel limit. Failure traces retain the
settlement samples, descendant font styles and active font-set states.

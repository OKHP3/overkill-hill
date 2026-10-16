# Search-test portability

The search browser suite uses Playwright's `ControlOrMeta+k`: Command+K on
macOS and Ctrl+K on the other supported desktop hosts. Production shortcut
handling is unchanged.

Scrollbar regressions run in two measured configurations. Native mode removes
Playwright's default scrollbar-hiding argument and records the actual viewport
gutter. Overlay mode retains that default and requires a zero-width gutter.
Both configurations check history reading focus, Tab continuation, scroll
position, and the missing CSS convenience-getter fallback. Neither skips
behavior checks or changes system scrollbar preferences.

The Linux validation job sets `SEARCH_REQUIRE_CLASSIC_SCROLLBARS=1`. Native
cases must then measure a positive classic gutter; an overlay-only CI host
fails rather than silently dropping that coverage. Without that setting, a
Mac's native overlay geometry is valid and reported as such. The explicit
overlay cases still require zero gutter on every host. Existing important
inline-gutter and competing-controller regressions remain in the suite.

Use the repository's supported Node 24 runtime and locked Playwright version:

```sh
node --test tests/search-page.test.mjs
```

On a host with actual classic scrollbar geometry, the CI contract can also be
run explicitly:

```sh
SEARCH_REQUIRE_CLASSIC_SCROLLBARS=1 node --test tests/search-page.test.mjs
```

An expected prerequisite failure on an overlay-only Mac is evidence that the
classic guard remains enforced, not classic-scrollbar acceptance. Linux CI
provides that acceptance. This test-only change does not establish human
assistive-technology/device acceptance, publish a site, change shared runtime
behavior, modify Windows runners, or promote release/foundation pins.

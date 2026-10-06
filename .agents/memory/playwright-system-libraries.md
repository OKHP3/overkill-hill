---
name: Playwright system libraries
description: Local Chromium runtime requirements for browser QA in this Replit project.
---

The cached Playwright Chromium binary does not start in the base development
runtime unless the Nix environment includes `libgbm` and `cups`.

**Why:** The Playwright package and browser cache can both be present while
Chromium still exits before creating a page when these shared libraries are
not exposed.

**How to apply:** Keep `libgbm` and `cups` in the project Nix package list and
restart the application workflow after changing that list before running
browser QA.

The Replit runtime may also provide Chromium independently of Playwright's
versioned browser cache. Check `command -v chromium` and, if that binary launches
through Playwright, pass it as `executablePath` before installing another
browser.

**Why:** In this project the expected Playwright browser-cache build was absent,
while `/repl/tools/bin/chromium` launched under the existing runtime; no install
was needed.

**How to apply:** Try the managed Chromium executable first. Keep the separate
`libgbm`/`cups` guidance for launch failures caused by missing shared libraries.
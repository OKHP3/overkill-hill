#!/usr/bin/env node
/**
 * Screen-reader accessibility-tree audit.
 *
 * This environment is a headless Linux sandbox with no audio device, no
 * desktop session, and no installed screen reader (no NVDA/JAWS on Windows,
 * no VoiceOver on macOS, no Orca on Linux — Orca requires a graphical
 * session and speech-dispatcher, neither of which exist here). A literal
 * "turn on a screen reader and listen" session is not possible in this
 * sandbox.
 *
 * The closest rigorous substitute available here is Chromium's accessibility
 * tree via Playwright's `page.accessibility.snapshot()`. Screen readers
 * consume this same platform accessibility tree (via UIA/AT-SPI/AX APIs), so
 * inspecting it verifies exactly what would be announced: computed roles,
 * accessible names/descriptions, landmark structure, table semantics, and
 * live-region/dialog exposure. It does NOT verify a specific screen reader's
 * verbosity, rendering quirks, or browser-specific AT interop bugs — see
 * README.md "Accessibility QA coverage" for that limitation and the
 * recommendation to pair this with a real NVDA+Chrome / VoiceOver+Safari
 * session before a major release.
 *
 * Usage:
 *   node scripts/screen-reader-tree-audit.mjs
 *   node scripts/screen-reader-tree-audit.mjs --base-url=http://127.0.0.1:5000
 */

import { chromium } from "playwright";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_BASE_URL = "http://127.0.0.1:5000";
const baseArg = process.argv.find((arg) => arg.startsWith("--base-url="));
const baseUrl = (baseArg ? baseArg.slice("--base-url=".length) : DEFAULT_BASE_URL)
  .replace(/\/$/, "");

const PAGES = [
  { name: "home", path: "/" },
  { name: "article (Mermaid-heavy, tables)", path: "/writings/first-diagram-is-a-liar/" },
  { name: "project (Mermaid + 3 tables)", path: "/projects/mac-studio-local-ai-workbench/" },
  { name: "utility (404)", path: "/404.html" },
  { name: "universe (Mermaid)", path: "/universe/" },
  { name: "found-ry project (Mermaid)", path: "/projects/found-ry/" },
];

// Playwright dropped the old page.accessibility.snapshot() helper. The CDP
// Accessibility domain exposes the same underlying tree that Chromium hands
// to platform screen-reader APIs (UIA/AT-SPI/AX), so we query it directly.
async function getAxNodes(page) {
  const client = await page.context().newCDPSession(page);
  await client.send("Accessibility.enable");
  const { nodes } = await client.send("Accessibility.getFullAXTree");
  await client.detach().catch(() => {});
  return nodes
    .filter((n) => !n.ignored)
    .map((n) => ({
      role: n.role?.value,
      name: n.name?.value || "",
    }));
}

// The first-visit announcement owns focus and hides the underlying page from
// the accessibility tree. Dismiss it as a visitor would before auditing that
// tree and the search dialog, while retaining a failure for an unnamed modal.
export async function dismissTransitionAnnouncement(page, failures) {
  const announcement = page.locator("#capability-transition-dialog[open]");
  if (!await announcement.count()) return true;

  const namedAnnouncement = announcement.and(page.getByRole("dialog", { name: /\S/ }));
  if (!await namedAnnouncement.count()) {
    failures.push("transition announcement has no accessible dialog name");
  }

  await announcement.evaluate((dialog) => {
    dialog.__auditCloseObserved = false;
    dialog.addEventListener("close", () => { dialog.__auditCloseObserved = true; }, { once: true });
  });
  await page.keyboard.press("Escape");
  try {
    await page.waitForFunction(() => {
      const dialog = document.getElementById("capability-transition-dialog");
      return dialog && !dialog.open && dialog.__auditCloseObserved === true;
    }, undefined, { timeout: 5000 });
  } catch {
    failures.push("transition announcement did not close after Escape");
    return false;
  }
  return true;
}

async function auditPage(page, def) {
  const failures = [];
  await page.goto(`${baseUrl}${def.path}`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(200);

  if (!await dismissTransitionAnnouncement(page, failures)) {
    return { failures, nodeCount: 0, landmarks: [] };
  }

  // Mermaid diagrams below the fold render lazily via IntersectionObserver,
  // mirroring what happens as a screen-reader user scrolls/tabs down the
  // page. Scroll every diagram into view so the accessible name exists
  // before we snapshot the tree, the same way it would exist by the time a
  // real user's AT reaches that content.
  const diagramHandles = await page.$$(".mermaid");
  for (const handle of diagramHandles) {
    await handle.scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(120);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(100);

  const nodes = await getAxNodes(page);

  // Landmarks: banner (header), navigation, main, contentinfo (footer)
  const landmarkRoles = ["banner", "navigation", "main", "contentinfo"];
  for (const role of landmarkRoles) {
    if (!nodes.some((n) => n.role === role)) {
      failures.push(`no accessible "${role}" landmark exposed in the a11y tree`);
    }
  }

  // Mermaid diagrams: role "img" with a non-trivial accessible name.
  const domDiagramCount = await page.evaluate(
    () => document.querySelectorAll(".mermaid, svg[role='img'][aria-label^='Diagram ']").length,
  );
  // Chromium's CDP Accessibility tree reports the ARIA "img" role as
  // "image" (not "img") in its role value.
  const imgNodes = nodes.filter((n) => n.role === "image");
  if (domDiagramCount > 0) {
    const labeledDiagrams = imgNodes.filter((n) => (n.name || "").trim().length >= 8);
    if (labeledDiagrams.length < domDiagramCount) {
      failures.push(
        `expected ${domDiagramCount} Mermaid diagram(s) exposed as role="img" with a real name, ` +
        `found ${labeledDiagrams.length} in the a11y tree`,
      );
    }
  }

  // Tables: role "table" with either a name or a row/column structure a
  // screen reader can navigate (rows exposed as children).
  const domTableCount = await page.evaluate(() => document.querySelectorAll("table").length);
  const tableNodes = nodes.filter((n) => n.role === "table");
  if (domTableCount > 0 && tableNodes.length < domTableCount) {
    failures.push(`expected ${domTableCount} table(s) exposed with role="table", found ${tableNodes.length}`);
  }

  // Keyboard focus / dialog check only on home (search overlay lives on every page,
  // but we only need to confirm it once per run to keep this fast).
  if (def.name === "home") {
    const trigger = await page.$(".okh-search-trigger");
    if (!trigger) {
      failures.push("no search trigger button found to open the search dialog");
    } else {
      await trigger.click();
      await page.waitForTimeout(150);
      const dialogNodes = await getAxNodes(page);
      const dialog = dialogNodes.find((n) => n.role === "dialog");
      if (!dialog) {
        failures.push("search overlay does not expose role=\"dialog\" to the a11y tree when open");
      } else if (!(dialog.name || "").trim()) {
        failures.push("search dialog has no accessible name");
      }
      const focused = await page.evaluate(() => document.activeElement?.className || "");
      if (!focused.includes("okh-search-input")) {
        failures.push("opening the search dialog did not move focus into the search input");
      }
      await page.keyboard.press("Escape");
      await page.waitForTimeout(100);
      const afterClose = await page.evaluate(() => document.activeElement?.className || "");
      if (!afterClose.includes("okh-search-trigger")) {
        failures.push("closing the search dialog with Escape did not return focus to the trigger");
      }
    }
  }

  return { failures, nodeCount: nodes.length, landmarks: nodes.filter((n) => landmarkRoles.includes(n.role)).map((n) => n.role) };
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  let totalFailures = 0;

  try {
    for (const def of PAGES) {
      const result = await auditPage(page, def);
      if (result.failures.length) {
        totalFailures += result.failures.length;
        console.error(`FAIL  ${def.name} (${def.path})`);
        result.failures.forEach((f) => console.error(`      - ${f}`));
      } else {
        console.log(`PASS  ${def.name} (${def.path}) — ${result.nodeCount} a11y nodes, landmarks: ${result.landmarks.join(", ")}`);
      }
    }
  } finally {
    await context.close();
    await browser.close();
  }

  if (totalFailures) {
    console.error(`\n${totalFailures} screen-reader-tree check(s) failed.`);
    process.exit(1);
  }
  console.log(`\nScreen-reader accessibility-tree audit passed for ${PAGES.length} pages.`);
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    console.error(`Screen-reader tree audit could not run: ${error.stack || error.message}`);
    process.exit(1);
  });
}

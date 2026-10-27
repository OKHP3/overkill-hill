#!/usr/bin/env node
/**
 * Screen-reader accessibility-tree audit.
 *
 * This audit uses headless Chromium and does not run a screen reader.
 *
 * This audit inspects Chromium's computed accessibility tree through CDP,
 * including roles, names, landmarks, table semantics, and dialog exposure.
 * It does not record actual screen-reader output or verify a specific screen
 * reader's verbosity, rendering quirks, or browser-specific AT interop bugs. See
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

function domAttributes(node) {
  const attributes = node.attributes || [];
  const result = {};
  for (let i = 0; i < attributes.length; i += 2) result[attributes[i]] = attributes[i + 1];
  return result;
}

// Read one carrier per diagram, including standalone SVGs but not an SVG
// already contained by a Mermaid carrier. The existing data-diagram-label
// authoring marker survives a missing role or accessible name. An unmarked
// standalone SVG is discoverable only while its legacy role and name remain.
function collectDiagramCarriers(root) {
  const diagrams = [];
  function visit(node, diagram = null, inSvg = false) {
    const tag = (node.nodeName || "").toLowerCase();
    const attrs = domAttributes(node);
    const classes = (attrs.class || "").split(/\s+/);
    const isStandaloneDiagram = tag === "svg" && (
      Object.hasOwn(attrs, "data-diagram-label") ||
      (attrs.role === "img" && (attrs["aria-label"] || "").startsWith("Diagram "))
    );
    if (!diagram && (classes.includes("mermaid") || isStandaloneDiagram)) {
      diagram = { backendId: node.backendNodeId, svgCarrier: tag === "svg", hasSvg: false, links: [] };
      diagrams.push(diagram);
    }
    const insideSvg = inSvg || tag === "svg";
    if (diagram && tag === "svg") diagram.hasSvg = true;
    if (diagram && insideSvg && tag === "a" && (attrs.href || attrs["xlink:href"])) {
      diagram.links.push(node.backendNodeId);
    }
    for (const child of node.children || []) visit(child, diagram, insideSvg);
  }
  visit(root);
  return diagrams;
}

// The prior global image count could let unrelated images hide an unnamed
// diagram. Bind each carrier and interactive link to its own Chromium AX node.
export async function checkMermaidDiagrams(page) {
  const client = await page.context().newCDPSession(page);
  try {
    await client.send("Accessibility.enable");
    let diagrams;
    let axNodes;
    let stable = false;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const before = await client.send("DOM.getDocument", { depth: -1 });
      diagrams = collectDiagramCarriers(before.root);
      ({ nodes: axNodes } = await client.send("Accessibility.getFullAXTree"));
      const after = await client.send("DOM.getDocument", { depth: -1 });
      if (JSON.stringify(diagrams) === JSON.stringify(collectDiagramCarriers(after.root))) {
        stable = true;
        break;
      }
    }
    if (!stable) return ["Mermaid diagram identities changed during accessibility inspection"];

    const failures = [];
    const nodesById = new Map(axNodes.map((node) => [node.nodeId, node]));
    const matchingNode = (backendId, role) => axNodes.filter((node) =>
      !node.ignored && node.backendDOMNodeId === backendId && node.role?.value === role);
    function descendants(node) {
      const found = new Set();
      const pending = [...(node.childIds || [])];
      while (pending.length) {
        const id = pending.pop();
        if (found.has(id)) continue;
        found.add(id);
        pending.push(...(nodesById.get(id)?.childIds || []));
      }
      return found;
    }

    diagrams.forEach((diagram, index) => {
      const label = `Mermaid diagram ${index + 1}`;
      if (!Number.isInteger(diagram.backendId)) {
        failures.push(`${label}: missing DOM backend identity`);
        return;
      }
      if (!diagram.hasSvg) {
        failures.push(`${label}: no rendered SVG found`);
        return;
      }
      const roles = diagram.links.length
        ? (diagram.svgCarrier ? ["group", "graphics-document"] : ["group"])
        : ["image"];
      const carriers = roles.flatMap((role) => matchingNode(diagram.backendId, role));
      const role = roles.join(" or ");
      if (carriers.length !== 1) {
        failures.push(`${label}: expected its own accessible ${role}, found ${carriers.length}`);
        return;
      }
      const carrier = carriers[0];
      if ((carrier.name?.value || "").trim().length < 8) {
        failures.push(`${label}: accessible ${role} needs a name of at least 8 characters`);
      }
      const children = descendants(carrier);
      diagram.links.forEach((backendId, linkIndex) => {
        const linkLabel = `${label} link ${linkIndex + 1}`;
        if (!Number.isInteger(backendId)) {
          failures.push(`${linkLabel}: missing DOM backend identity`);
          return;
        }
        const links = matchingNode(backendId, "link").filter((link) => children.has(link.nodeId));
        if (links.length !== 1) failures.push(`${linkLabel}: expected its own accessible link in the group`);
        else if (!(links[0].name?.value || "").trim()) failures.push(`${linkLabel}: accessible link has no name`);
      });
    });
    return failures;
  } finally {
    await client.detach().catch(() => {});
  }
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
  try {
    await page.waitForFunction(
      () => [...document.querySelectorAll(".mermaid")].every((diagram) => diagram.querySelector("svg")),
      undefined,
      { timeout: 8000 },
    );
  } catch {
    // Inspect the actual DOM below so an unrendered carrier is reported.
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

  failures.push(...await checkMermaidDiagrams(page));

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

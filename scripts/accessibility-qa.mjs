#!/usr/bin/env node
/**
 * Browser accessibility QA for representative page types.
 *
 * This is intentionally a focused regression gate, not a claim of complete
 * WCAG conformance. It checks keyboard reachability and the skip link,
 * keyboard-visible focus styling, basic ARIA validity/reference integrity,
 * Mermaid text alternatives, and reduced-motion behavior.
 *
 * Usage:
 *   npm run test:accessibility
 *   node scripts/accessibility-qa.mjs --base-url=http://127.0.0.1:5000
 */

import { loadFunctionalPaths } from './release-qa-inventory.mjs';
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const DEFAULT_BASE_URL = "http://127.0.0.1:5000";
const baseArg = process.argv.find((arg) => arg.startsWith("--base-url="));
const baseUrl = (baseArg ? baseArg.slice("--base-url=".length) : DEFAULT_BASE_URL)
  .replace(/\/$/, "");

const REPRESENTATIVE_PAGES = [
  { name: "home", path: "/" },
  { name: "article", path: "/writings/first-diagram-is-a-liar/" },
  { name: "project", path: "/projects/mac-studio-local-ai-workbench/" },
  { name: "utility", path: "/404.html" },
];

const KNOWN_ROLES = new Set([
  "alert", "alertdialog", "application", "article", "banner", "button",
  "cell", "checkbox", "complementary", "contentinfo", "definition",
  "dialog", "directory", "document", "feed", "figure", "form", "grid",
  "gridcell", "group", "heading", "img", "link", "list", "listbox",
  "listitem", "log", "main", "marquee", "math", "menu", "menubar",
  "menuitem", "meter", "navigation", "none", "note", "option", "presentation",
  "progressbar", "radio", "radiogroup", "region", "row", "rowgroup",
  "rowheader", "scrollbar", "search", "separator", "slider", "spinbutton",
  "status", "switch", "tab", "table", "tablist", "tabpanel", "term",
  "textbox", "timer", "toolbar", "tooltip", "tree", "treegrid", "treeitem",
  "graphics-document", "graphics-symbol", "graphics-object",
]);

const BOOLEAN_ARIA = new Set([
  "aria-busy", "aria-checked", "aria-disabled", "aria-expanded", "aria-hidden",
  "aria-modal", "aria-multiline", "aria-multiselectable", "aria-readonly",
  "aria-required", "aria-selected",
]);

function loadPublicPaths() {
  return loadFunctionalPaths();
}

const PUBLIC_PATHS = loadPublicPaths();

function localPagePath(path) {
  return path.endsWith(".html")
    ? new URL(`..${path}`, import.meta.url)
    : new URL(`..${path}index.html`, import.meta.url);
}

async function inspectAriaAndDiagrams(page, path) {
  const staticHtml = readFileSync(localPagePath(path), "utf8");
  const expectedDiagrams = [...staticHtml.matchAll(/class=["']([^"']+)["']/g)]
    .filter((match) => match[1].split(/\s+/).includes("mermaid")).length;
  await page.goto(`${baseUrl}${path}`, {
    waitUntil: "domcontentloaded",
    timeout: 30000,
  });
  await page.waitForTimeout(150);
  return page.evaluate(({ expected, booleanAria, knownRoles }) => {
    const failures = [];
    const booleanAttributes = new Set(booleanAria);
    const roles = new Set(knownRoles);
    const ids = new Set();
    document.querySelectorAll("[id]").forEach((element) => {
      if (ids.has(element.id)) failures.push(`duplicate id="${element.id}"`);
      ids.add(element.id);
    });

    document.querySelectorAll("*").forEach((element) => {
      for (const attribute of element.attributes) {
        const name = attribute.name.toLowerCase();
        const value = attribute.value.trim();
        if (!name.startsWith("aria-")) continue;
        if (booleanAttributes.has(name) && !["true", "false", "mixed"].includes(value)) {
          failures.push(`${name} has invalid value "${value}"`);
        }
        if (name === "aria-labelledby" || name === "aria-describedby" || name === "aria-owns") {
          for (const id of value.split(/\s+/).filter(Boolean)) {
            if (!document.getElementById(id)) failures.push(`${name} references missing #${id}`);
          }
        }
      }
      const role = element.getAttribute("role");
      if (role && !role.split(/\s+/).every((token) => roles.has(token))) {
        failures.push(`unknown role "${role}"`);
      }
      if (element.hasAttribute("tabindex") && !/^-?\d+$/.test(element.getAttribute("tabindex"))) {
        failures.push("tabindex must be an integer");
      }
    });

    // Chromium exposes a bare <table> to the accessibility tree as a real
    // "table"/"row"/"cell" structure only when it has at least one <th>, a
    // <caption>, or an explicit role. Lacking all three, Chromium applies its
    // "layout table" heuristic and silently strips table semantics, so a
    // screen reader user loses row/column navigation entirely even though
    // the table renders normally. Flag any table that would fall into that
    // heuristic before it ships.
    document.querySelectorAll("table").forEach((table, index) => {
      const hasHeaderCell = Boolean(table.querySelector("th"));
      const hasCaption = Boolean(table.querySelector("caption"));
      const explicitRole = (table.getAttribute("role") || "").trim();
      if (!hasHeaderCell && !hasCaption && !explicitRole) {
        failures.push(
          `table ${index + 1} has no <th>, no <caption>, and no explicit role — ` +
          `it will be exposed as a layout table with no row/cell semantics for screen readers`,
        );
      }
    });

    const diagrams = [...document.querySelectorAll(
      ".mermaid, svg[role='img'][aria-label^='Diagram ']",
    )];
    if (diagrams.length !== expected) {
      failures.push(`expected ${expected} Mermaid instances, found ${diagrams.length}`);
    }
    diagrams.forEach((diagram, index) => {
      const label = diagram.getAttribute("aria-label");
      const described = diagram.getAttribute("aria-describedby");
      if ((!label || label.trim().length < 8) && !described) {
        failures.push(`Mermaid instance ${index + 1} has no text alternative`);
      }
      if (diagram.getAttribute("role") !== "img") {
        failures.push(`Mermaid instance ${index + 1} is missing role="img"`);
      }
    });
    return failures;
  }, {
    expected: expectedDiagrams,
    booleanAria: [...BOOLEAN_ARIA],
    knownRoles: [...KNOWN_ROLES],
  });
}

async function inspectKeyboardAndFocus(page, definition) {
  const failures = [];
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto(`${baseUrl}${definition.path}`, { waitUntil: "domcontentloaded", timeout: 30000 });

  // A first-visit announcement intentionally owns focus before the page.
  // Verify its focus, dismiss it, then audit the underlying skip-link order.
  const announcement = page.locator('#capability-transition-dialog[open]');
  if (await announcement.count()) {
    if (!await page.getByRole('button', { name: 'Close transition announcement' }).evaluate(el => el === document.activeElement)) {
      failures.push('transition announcement did not receive initial focus');
    }
    await page.keyboard.press('Escape');
    // Reload the dismissed state to reset the sequential focus starting point.
    await page.reload({ waitUntil: 'domcontentloaded' });
  }

  const keyboard = await page.evaluate(() => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden"
        && element.getClientRects().length > 0;
    };
    const focusable = [...document.querySelectorAll(
      'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
    )].filter(visible);
    return {
      hasSkip: Boolean(document.querySelector(".okh-skip-link")),
      hasMain: Boolean(document.querySelector("main#main")),
      focusableCount: focusable.length,
      positiveTabindex: focusable.filter((element) => Number(element.tabIndex) > 0).length,
    };
  });
  if (!keyboard.hasSkip) failures.push("missing skip link");
  if (!keyboard.hasMain) failures.push("missing main#main landmark");
  if (keyboard.focusableCount === 0) failures.push("no keyboard-focusable controls");
  if (keyboard.positiveTabindex) failures.push("positive tabindex disrupts keyboard order");

  await page.evaluate(() => document.body.focus());
  await page.keyboard.press("Tab");
  const firstFocus = await page.evaluate(() => ({
    className: document.activeElement?.className || "",
    href: document.activeElement?.getAttribute("href") || "",
    visible: Boolean(document.activeElement && getComputedStyle(document.activeElement).visibility !== "hidden"),
  }));
  if (!firstFocus.visible || !firstFocus.className.includes("okh-skip-link")) {
    failures.push("first Tab does not reach the skip link");
  }

  await page.keyboard.press("Tab");
  const focusStyle = await page.evaluate(() => {
    const element = document.activeElement;
    if (!element) return { focused: false };
    const style = getComputedStyle(element);
    return {
      focused: document.hasFocus(),
      focusVisible: element.matches(":focus-visible"),
      outline: style.outlineStyle,
      outlineWidth: style.outlineWidth,
    };
  });
  if (!focusStyle.focused || !focusStyle.focusVisible || focusStyle.outline === "none"
      || focusStyle.outlineWidth === "0px") {
    failures.push("keyboard focus does not have a visible outline");
  }
  return failures;
}

async function inspectReducedMotion(page, definition) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`${baseUrl}${definition.path}`, { waitUntil: "domcontentloaded", timeout: 30000 });
  return page.evaluate(() => {
    const failures = [];
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      failures.push("reduced-motion media preference was not applied");
    }
    for (const element of document.querySelectorAll("*")) {
      const style = getComputedStyle(element);
      const hasMotion = style.animationName !== "none"
        || (style.transitionProperty !== "none" && style.transitionProperty !== "all");
      if (!hasMotion) continue;
      const activeDuration = [style.animationDuration, style.transitionDuration]
        .join(",")
        .split(",")
        .some((duration) => Number.parseFloat(duration) > 0.00001);
      if (activeDuration) {
        failures.push("animation or transition remains active under reduced motion");
        break;
      }
    }
    const hiddenReveals = [...document.querySelectorAll(".reveal-on-scroll")]
      .filter((element) => getComputedStyle(element).opacity !== "1");
    if (hiddenReveals.length) failures.push("scroll-reveal content remains hidden under reduced motion");
    return failures;
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  let failures = 0;

  try {
    for (const definition of REPRESENTATIVE_PAGES) {
      const ariaFailures = await inspectAriaAndDiagrams(page, definition.path);
      const keyboardFailures = await inspectKeyboardAndFocus(page, definition);
      const motionFailures = await inspectReducedMotion(page, definition);
      const pageFailures = [...ariaFailures, ...keyboardFailures, ...motionFailures];
      if (pageFailures.length) {
        failures += pageFailures.length;
        pageFailures.forEach((failure) => console.error(`FAIL  ${definition.name}: ${failure}`));
      } else {
        console.log(`PASS  ${definition.name}: keyboard, focus, ARIA, diagrams, reduced motion`);
      }
    }

    // ARIA and Mermaid alternatives are checked on every public route, not
    // only on the representative interaction pages above.
    for (const path of PUBLIC_PATHS) {
      await page.emulateMedia({ reducedMotion: "no-preference" });
      const response = await page.goto(`${baseUrl}${path}`, {
        waitUntil: "domcontentloaded",
        timeout: 30000,
      });
      if (!response || response.status() >= 400) {
        failures++;
        console.error(`FAIL  ${path}: HTTP ${response?.status() ?? "no response"}`);
        continue;
      }
      const routeFailures = await inspectAriaAndDiagrams(page, path);
      if (routeFailures.length) {
        failures += routeFailures.length;
        routeFailures.forEach((failure) => console.error(`FAIL  ${path}: ${failure}`));
      }
    }
  } finally {
    await context.close();
    await browser.close();
  }

  if (failures) {
    console.error(`\n${failures} accessibility check(s) failed.`);
    process.exit(1);
  }
  console.log(`\nAccessibility QA passed: ${REPRESENTATIVE_PAGES.length} representative pages and ${PUBLIC_PATHS.length} public routes.`);
}

main().catch((error) => {
  console.error(`Accessibility QA could not run: ${error.stack || error.message}`);
  process.exit(1);
});

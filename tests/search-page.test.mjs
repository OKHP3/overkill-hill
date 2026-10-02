import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";
import { dirname, extname, resolve } from "node:path";
import { chromium } from "playwright";

const testsDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(testsDirectory, "..");
let server;
let baseUrl;

// Search interactions begin after the first-visit announcement is dismissed.
// The announcement's own focus and persistence have dedicated regressions.
async function dismissAnnouncement(page) {
  await page.waitForLoadState('load');
  const announcement = page.locator('#capability-transition-dialog[open]');
  if (await announcement.count()) {
    await page.getByRole('button', { name: 'Close transition announcement' }).click();
    await page.waitForFunction(() => !document.getElementById('capability-transition-dialog').open);
  }
}


function contentTypeFor(pathname) {
  const ext = extname(pathname).toLowerCase();
  return { ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp" }[ext] || "text/plain; charset=utf-8";
}

async function serveFile(request, response) {
  const url = new URL(request.url, "http://search-test");
  let pathname = url.pathname;
  if (pathname.endsWith("/")) pathname += "index.html";
  const filePath = resolve(repositoryRoot, "." + pathname);
  if (!filePath.startsWith(repositoryRoot)) { response.writeHead(403); response.end("forbidden"); return; }
  try { const body = await readFile(filePath); response.writeHead(200, { "content-type": contentTypeFor(filePath) }); response.end(body); }
  catch { response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }); response.end("missing"); }
}

before(async () => {
  server = createServer((request, response) => serveFile(request, response).catch((error) => { response.writeHead(500); response.end(error.message); }));
  await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});
after(async () => { await new Promise((resolveClose, rejectClose) => server.close((error) => error ? rejectClose(error) : resolveClose())); });

function makeSearchEntries() {
  const entries = [];
  for (let i = 1; i <= 60; i += 1) entries.push({ url: `/brand-${String(i).padStart(2, "0")}/`, title: `Brand ${i}`, category: "Brand", description: `omega brand ${i}`, headings: [], body: `omega brand ${i}` });
  entries.push({ url: "/project-61/", title: "Project 61", category: "Project", description: "omega project 61", headings: [], body: "omega project 61" });
  for (let i = 62; i <= 80; i += 1) entries.push({ url: `/project-${i}/`, title: `Project ${i}`, category: "Project", description: `omega project ${i}`, headings: [], body: `omega project ${i}` });
  return entries;
}

for (const overlayMode of [true, false]) {
  test(`search distinguishes loading and an empty index (${overlayMode ? "overlay" : "page"})`, async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    let releaseIndex;
    const pending = new Promise(resolve => { releaseIndex = resolve; });
    try {
      await page.route("**/assets/data/search-index.json", async route => {
        await pending;
        await route.fulfill({ contentType: "application/json", body: '{"entries":[]}' });
      });
      await page.goto(`${baseUrl}${overlayMode ? "/" : "/search/"}`, { waitUntil: "domcontentloaded" });
      await dismissAnnouncement(page);
      if (overlayMode) await page.locator(".okh-search-trigger").click();
      const input = page.locator(overlayMode ? ".okh-search-input" : "#search-page-input");
      const status = page.locator(overlayMode ? ".okh-search-status" : "#search-stats");
      await input.fill("omega");
      assert.match(await status.textContent(), /Loading/);
      releaseIndex();
      await page.waitForFunction(selector => document.querySelector(selector).textContent.includes("No indexed pages"), overlayMode ? ".okh-search-status" : "#search-stats");
      await input.fill("");
      assert.match(await status.textContent(), /No indexed pages/);
      await input.press("Enter");
      assert.equal(await input.evaluate(el => el === document.activeElement), true);
    } finally { releaseIndex(); await browser.close(); }
  });

  test(`search focuses ordinary result links (${overlayMode ? "overlay" : "page"})`, async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
      await page.route("**/assets/data/search-index.json", route => route.fulfill({
        contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries().slice(0, 3) }),
      }));
      await page.goto(`${baseUrl}${overlayMode ? "/" : "/search/?q=omega"}`, { waitUntil: "networkidle" });
      await dismissAnnouncement(page);
      const trigger = page.locator(".okh-search-trigger");
      if (overlayMode) await trigger.click();
      const input = page.locator(overlayMode ? ".okh-search-input" : "#search-page-input");
      const scope = page.locator(overlayMode ? ".okh-search-results" : "#search-results");
      await input.fill("omega");
      const links = scope.locator(".okh-search-result");
      await links.first().waitFor();
      await input.press("ArrowDown");
      assert.equal(await links.first().evaluate(el => el === document.activeElement), true);
      await page.keyboard.press("ArrowDown");
      assert.equal(await links.nth(1).evaluate(el => el === document.activeElement), true);
      await page.keyboard.press("Tab");
      assert.equal(await links.last().evaluate(el => el === document.activeElement), true);
      await page.keyboard.press("ArrowDown");
      assert.equal(await links.last().evaluate(el => el === document.activeElement), true);
      await page.keyboard.press("ArrowUp");
      await page.keyboard.press("ArrowUp");
      await page.keyboard.press("ArrowUp");
      assert.equal(await input.evaluate(el => el === document.activeElement), true);
      assert.equal(await input.inputValue(), "omega");
      await input.press("ArrowUp");
      assert.equal(await links.last().evaluate(el => el === document.activeElement), true);
      await input.focus();
      await input.fill("no-such-result");
      await input.press("ArrowDown");
      assert.equal(await input.evaluate(el => el === document.activeElement), true);
      await input.fill("omega");
      if (overlayMode) {
        await input.press("ArrowDown");
        await page.keyboard.press("Escape");
        assert.equal(await trigger.evaluate(el => el === document.activeElement), true);
        await trigger.click();
      }
      await input.press("ArrowDown");
      const target = await links.first().getAttribute("href");
      await page.keyboard.press("Enter");
      await page.waitForURL(`${baseUrl}${target}`);
    } finally { await browser.close(); }
  });
}

test("overlay keyboard selection survives the delayed opener focus after reopening", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.clock.install();
    await page.route("**/assets/data/search-index.json", route => route.fulfill({
      contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries().slice(0, 3) }),
    }));
    await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
    await dismissAnnouncement(page);

    const trigger = page.locator(".okh-search-trigger");
    const overlay = page.locator(".okh-search-overlay");
    const input = overlay.locator(".okh-search-input");
    await trigger.click();
    await input.fill("omega");
    const first = overlay.locator(".okh-search-result").first();
    await first.waitFor();
    await page.clock.fastForward(31);

    await page.keyboard.press("Escape");
    await overlay.waitFor({ state: "hidden" });
    await trigger.click();
    await overlay.waitFor({ state: "visible" });
    await input.press("ArrowDown");
    await page.clock.fastForward(31);

    const navigationState = await page.evaluate(() => {
      const active = document.activeElement;
      const marked = document.querySelector('.okh-search-result[data-active="true"]');
      return {
        focusedHref: active?.matches(".okh-search-result") ? active.getAttribute("href") : null,
        markedHref: marked?.getAttribute("href") || null,
      };
    });
    assert.deepEqual(navigationState, {
      focusedHref: "/brand-01/",
      markedHref: "/brand-01/",
    });

    await page.keyboard.press("Enter");
    await page.waitForURL(`${baseUrl}/brand-01/`);
  } finally {
    await browser.close();
  }
});

test("Enter from the dedicated search input opens its first result", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await openSearchPage(page, route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries() }) }));
    const target = await page.locator("#search-results .okh-search-result").first().getAttribute("href");
    await page.locator("#search-page-input").press("Enter");
    await page.waitForURL(`${baseUrl}${target}`);
  } finally { await browser.close(); }
});

test("uses each site's identity and vocabulary in the shared search overlay", async () => {
  const browser = await chromium.launch({ headless: true });
  const home = await readFile(resolve(repositoryRoot, "index.html"), "utf8");
  const brands = [
    { bodyClass: "", label: "Search OverKill Hill", hint: "mermaid", introduction: /writings, projects, manifesto/ },
    { bodyClass: "glee-main", label: "Search Glee‑fully Tools", hint: "budget", introduction: /Glee‑fully Toolbox/ },
    { bodyClass: "askjamie-main", label: "Search AskJamie", hint: "clarity", introduction: /across AskJamie/ },
  ];
  try {
    for (const brand of brands) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      try {
        // Set the brand before deferred shared code runs. Retain the real shell
        // and CSP; optional sibling modules are outside this copy regression.
        await page.route(`${baseUrl}/`, route => route.fulfill({
          contentType: "text/html", body: home.replace(/<body\b[^>]*>/i, `<body class="${brand.bodyClass}">`),
        }));
        await page.route(/\/assets\/js\/(?:glee-site-enhancements|askjamie-analytics)\.js(?:\?.*)?$/, route => route.fulfill({ contentType: "text/javascript", body: "export {};" }));
        await page.route("**/assets/data/search-index.json", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries() }) }));
        await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
        await dismissAnnouncement(page);
        await page.locator(".okh-search-trigger").click();
        const overlay = page.getByRole("dialog", { name: brand.label, exact: true });
        await overlay.waitFor({ state: "visible" });
        await overlay.getByRole("button", { name: brand.hint, exact: true }).waitFor();
        assert.match(await overlay.locator(".okh-search-empty").innerText(), brand.introduction);
        if (brand.bodyClass) assert.doesNotMatch(await overlay.innerText(), /Search across writings|Council archives/);
      } finally { await page.close(); }
    }
  } finally { await browser.close(); }
});

async function openSearchPage(page, indexResponder, path = "/search/?q=omega&cat=Project") {
  let requestCount = 0;
  await page.route("**/assets/data/search-index.json", async (route) => { requestCount += 1; await indexResponder(route, requestCount); });
  await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
  await dismissAnnouncement(page);
  return () => requestCount;
}

test("shows a retry when the search index fails, then recovers on retry", async () => {
  const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  try {
    let firstRequest = true;
    const count = await openSearchPage(page, async (route) => { if (firstRequest) { firstRequest = false; await route.fulfill({ status: 503, contentType: "application/json", body: "{}" }); } else await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 80, entries: makeSearchEntries() }) }); });
    await assert.match(await page.locator(".okh-search-noresults--error").innerText(), /Search could not load the index/i);
    await page.locator(".okh-search-retry").click(); await page.waitForTimeout(1000);
    assert.equal(count() >= 2, true); await assert.match(await page.locator("#search-results").innerText(), /Project 61/);
  } finally { await browser.close(); }
});

test("times out a shared stalled index request and both search views recover on retry", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let retryRequestCount = 0;
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  try {
    await page.addInitScript((indexPath) => {
      const nativeFetch = window.fetch.bind(window);
      let indexFetchCount = 0;
      window.__searchIndexFetchCount = () => indexFetchCount;
      window.fetch = (input, options = {}) => {
        const requestUrl = typeof input === "string" || input instanceof URL ? input : input.url;
        const url = new URL(requestUrl, window.location.href);
        if (url.pathname !== indexPath) return nativeFetch(input, options);
        indexFetchCount += 1;
        if (indexFetchCount !== 1) return nativeFetch(input, options);
        return new Promise((resolve, reject) => {
          const signal = options.signal;
          if (!signal) return;
          const rejectAborted = () => reject(new DOMException("The operation was aborted.", "AbortError"));
          if (signal.aborted) rejectAborted();
          else signal.addEventListener("abort", rejectAborted, { once: true });
        });
      };
    }, "/assets/data/search-index.json");
    await page.route("**/assets/data/search-index.json", async (route) => {
      retryRequestCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ entries: makeSearchEntries() }),
      });
    });

    await page.goto(`${baseUrl}/search/?q=omega&cat=Project`, { waitUntil: "domcontentloaded" });
    await dismissAnnouncement(page);
    await page.getByRole("button", { name: "Search" }).click();

    assert.equal(await page.evaluate(() => window.__searchIndexFetchCount()), 1,
      "the overlay should reuse the page's pending index request");
    assert.equal(retryRequestCount, 0);
    await Promise.all([
      page.locator("#search-results .okh-search-noresults--error").waitFor({ timeout: 15_000 }),
      page.locator(".okh-search-overlay .okh-search-noresults--error").waitFor({ timeout: 15_000 }),
    ]);
    assert.equal(await page.locator("#search-stats").getAttribute("role"), "status");
    assert.equal(await page.locator(".okh-search-status").getAttribute("role"), "status");
    assert.match(await page.locator("#search-stats").innerText(), /failed to load/i);
    assert.match(await page.locator(".okh-search-status").innerText(), /failed to load/i);
    assert.equal(await page.evaluate(() => window.__searchIndexFetchCount()), 1,
      "the shared stalled fetch should time out without being duplicated");

    const overlayRetryResponse = page.waitForResponse((response) =>
      response.url().endsWith("/assets/data/search-index.json") && response.status() === 200);
    await page.locator(".okh-search-overlay .okh-search-retry").click();
    await overlayRetryResponse;
    await page.locator(".okh-search-overlay .okh-search-noresults--error").waitFor({ state: "hidden" });
    await page.locator(".okh-search-input").fill("project 61");
    await page.locator(".okh-search-overlay").getByText("Project 61", { exact: true }).waitFor();
    assert.equal(retryRequestCount, 1);
    assert.equal(await page.evaluate(() => window.__searchIndexFetchCount()), 2);

    await page.keyboard.press("Escape");
    await page.locator(".okh-search-overlay").waitFor({ state: "hidden" });
    const pageRetryResponse = page.waitForResponse((response) =>
      response.url().endsWith("/assets/data/search-index.json") && response.status() === 200);
    await page.locator("#search-results .okh-search-retry").click();
    await pageRetryResponse;
    await page.locator("#search-results").getByText("Project 61", { exact: true }).waitFor();
    assert.equal(retryRequestCount, 2);
    assert.equal(await page.evaluate(() => window.__searchIndexFetchCount()), 3);
    assert.deepEqual(pageErrors, []);
  } finally {
    await browser.close();
  }
});

test("filters before the global cap and restores URL state", async () => {
  const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  try {
    await openSearchPage(page, async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ count: 80, entries: makeSearchEntries() }) }));
    await page.getByRole("button", { name: /^Project \(/ }).click(); assert.equal(page.url().includes("cat=Project"), true); await assert.match(await page.locator("#search-results").innerText(), /Project 61/);
    await page.getByRole("button", { name: /^Brand \(/ }).click(); await page.goBack(); assert.equal(page.url().includes("cat=Project"), true);
  } finally { await browser.close(); }
});

test("normalizes an unknown category and restores an empty query", async () => {
  const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  try {
    await openSearchPage(page, async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries() }) }), "/search/?q=omega&cat=NotARealCategory");
    await assert.equal(await page.locator("#search-page-input").inputValue(), "omega"); await assert.equal(await page.locator('[data-cat="all"]').getAttribute("aria-pressed"), "true");
    await page.evaluate(() => window.history.pushState({}, "", "/search/")); await page.evaluate(() => window.dispatchEvent(new PopStateEvent("popstate"))); await assert.equal(await page.locator("#search-page-input").inputValue(), "");
  } finally { await browser.close(); }
});

test("contains overlay index failures without an unhandled rejection", async () => {
  const browser = await chromium.launch({ headless: true }); const page = await browser.newPage({ viewport: { width: 1280, height: 900 } }); const errors = []; let requests = 0; page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.route("**/assets/data/search-index.json", async (route) => { requests += 1; await route.fulfill(requests === 1 ? { status: 503, contentType: "application/json", body: "{}" } : { status: 200, contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries() }) }); });
    await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
    await dismissAnnouncement(page);
    await page.getByRole("button", { name: "Search" }).click();
    await page.locator(".okh-search-overlay .okh-search-noresults--error").waitFor();
    // Arm the retry response before clicking. The previous document's
    // networkidle state can already be satisfied before this fetch starts.
    const retryResponse = page.waitForResponse((response) =>
      response.url().endsWith("/assets/data/search-index.json") && response.status() === 200);
    await page.locator(".okh-search-overlay .okh-search-retry").click();
    await retryResponse;
    await page.locator(".okh-search-overlay .okh-search-noresults--error").waitFor({ state: "hidden" });
    assert.equal(requests >= 2, true);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test("preserves an overlay query entered while the index is loading", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  try {
    await page.route("**/assets/data/search-index.json", async (route) => {
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          entries: [{
            url: "/resume-builder/",
            title: "Resume Builder",
            category: "Tool",
            description: "Build a clear resume",
            headings: [],
            body: "resume guidance",
          }],
        }),
      });
    });
    await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
    await dismissAnnouncement(page);
    await page.getByRole("button", { name: "Search" }).click();
    await page.locator(".okh-search-input").fill("resume");
    await page.locator('.okh-search-result[href="/resume-builder/"]').waitFor();
    await assert.match(await page.locator(".okh-search-status").innerText(), /1 result found/i);
    await assert.equal(await page.locator(".okh-search-input").inputValue(), "resume");
    await assert.equal(await page.locator('.okh-search-results > [role="listitem"]').count(), 1);
    await assert.equal(await page.getByRole("link", { name: /Resume Builder/ }).getAttribute("href"), "/resume-builder/");
  } finally {
    await browser.close();
  }
});

test("highlights normalized matches in original text and locates snippets after Unicode expansions", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const title = "P³ résumé cafe\u0301 & <notes>";
  try {
    await openSearchPage(page, route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ entries: [{
      url: "/normalized-example/", title, category: "Project", headings: [],
      body: "ﬃ ".repeat(100) + "anchor résumé marker", description: "Unicode examples",
    }] }) }), "/search/?q=resume");
    const result = page.locator('.okh-search-result[href="/normalized-example/"]');
    assert.equal(await result.locator("h3 mark").innerText(), "résumé");
    assert.match(await result.locator(".okh-search-result-snippet").innerText(), /anchor résumé marker/);
    assert.equal(await result.locator("h3").innerText(), title);
    assert.equal(await result.locator("h3 notes").count(), 0, "Original markup-like content stays text");
    await page.locator("#search-page-input").fill("p3");
    assert.equal(await result.locator("h3 mark").innerText(), "P³");
    await page.locator("#search-page-input").fill("cafe");
    assert.equal(await result.locator("h3 mark").textContent(), "cafe\u0301");
    await page.locator("#search-page-input").fill("resume sum");
    assert.equal(await result.locator("h3 mark").count(), 1, "Overlapping matches merge without nested markup");
    assert.equal(await result.locator("h3 mark").innerText(), "résumé");
  } finally { await browser.close(); }
});

test("Glee's unfiltered catalog omits snippets while searched results retain them", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    const html = await readFile(resolve(repositoryRoot, "search/index.html"), "utf8");
    await page.route(`${baseUrl}/search/`, route => route.fulfill({ contentType: "text/html", body: html.replace(/<body\b[^>]*>/i, '<body class="glee-main">') }));
    await page.route(/\/assets\/js\/glee-site-enhancements\.js(?:\?.*)?$/, route => route.fulfill({ contentType: "text/javascript", body: "export {};" }));
    await openSearchPage(page, route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries() }) }), "/search/");
    assert.equal(await page.locator("#search-results .okh-search-result").count(), 60);
    assert.equal(await page.locator("#search-results .okh-search-result-snippet").count(), 0);
    await page.locator("#search-page-input").fill("omega");
    assert.equal(await page.locator("#search-results .okh-search-result-snippet").count(), 60);
  } finally { await browser.close(); }
});

test("Glee hero heading contrasts with its actual paper panel in light, dark and automatic modes", async () => {
  const browser = await chromium.launch({ headless: true });
  const css = await readFile(resolve(repositoryRoot, "assets/css/theme.css"), "utf8");
  const luminance = rgb => rgb.match(/\d+/g).slice(0, 3).map(Number).map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((n, v, i) => n + v * [0.2126, 0.7152, 0.0722][i], 0);
  try {
    for (const [mode, system] of [["light", "light"], ["dark", "light"], ["auto", "dark"]]) {
      const page = await browser.newPage({ colorScheme: system });
      try {
        await page.setContent(`<html data-theme="light"${mode === "auto" ? "" : ` data-color-scheme="${mode}"`}><body class="glee-main"><div class="glee-hero-card"><h1>Glee-fully Tools</h1></div></body></html>`);
        await page.addStyleTag({ content: css });
        const colors = await page.locator(".glee-hero-card").evaluate(card => ({ ink: getComputedStyle(card.querySelector("h1")).color, paper: getComputedStyle(card, "::before").backgroundColor }));
        const values = [luminance(colors.ink), luminance(colors.paper)].sort((a, b) => b - a);
        const ratio = (values[0] + 0.05) / (values[1] + 0.05);
        assert(ratio >= 4.5, `${mode}: ${JSON.stringify(colors)}, contrast ${ratio.toFixed(2)}:1`);
      } finally { await page.close(); }
    }
  } finally { await browser.close(); }
});

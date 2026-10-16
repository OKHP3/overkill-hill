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
  test(`search leaves composing and modified input keys to the browser (${overlayMode ? "overlay" : "page"})`, async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
      await page.goto(`${baseUrl}${overlayMode ? "/prompt-forge/" : "/search/"}`);
      await dismissAnnouncement(page);
      if (overlayMode) await page.locator(".okh-search-trigger").click();
      const input = page.locator(overlayMode ? ".okh-search-input" : "#search-page-input");
      const results = page.locator(overlayMode ? ".okh-search-results" : "#search-results");
      await input.fill("FoundRy");
      await results.locator('.okh-search-result[href="/projects/found-ry/"]').waitFor();
      const searchUrl = page.url();
      for (const options of [
        { key: "ArrowDown", isComposing: true },
        { key: "ArrowUp", keyCode: 229 },
        { key: "ArrowDown", ctrlKey: true },
        { key: "ArrowDown", metaKey: true },
        { key: "ArrowDown", altKey: true },
        { key: "ArrowDown", shiftKey: true },
        { key: "Enter", isComposing: true },
      ]) {
        await input.focus();
        const state = await input.evaluate((element, options) => {
          const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...options });
          element.dispatchEvent(event);
          return { prevented: event.defaultPrevented, inputFocused: document.activeElement === element };
        }, options);
        assert.deepEqual(state, { prevented: false, inputFocused: true }, JSON.stringify(options));
        assert.equal(page.url(), searchUrl);
      }
      await input.press("ArrowDown");
      assert.equal(await results.locator('.okh-search-result:focus').count(), 1);
      await page.keyboard.press("Enter");
      await page.waitForURL(`${baseUrl}/projects/found-ry/`);
    } finally { await browser.close(); }
  });
}

for (const width of [1280, 320]) {
  for (const overlayMode of [true, false]) {
    test(`FoundRy joined name finds its published project (${width}px, ${overlayMode ? "overlay" : "page"})`, async () => {
      const browser = await chromium.launch({ headless: true });
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      try {
        await page.goto(`${baseUrl}${overlayMode ? "/prompt-forge/" : "/search/"}`);
        await dismissAnnouncement(page);
        if (overlayMode) await page.locator(".okh-search-trigger").click();
        const input = page.locator(overlayMode ? ".okh-search-input" : "#search-page-input");
        const results = page.locator(overlayMode ? ".okh-search-results" : "#search-results");
        const first = results.locator(".okh-search-result").first();
        for (const query of ["FoundRy", "FOUNDRY", "found-ry", "Found‑Rᵧ"]) {
          await input.fill(query);
          await page.waitForFunction(({ selector, query }) => document.querySelector(selector).textContent.includes(query), { selector: overlayMode ? ".okh-search-status" : "#search-stats", query });
          const href = await first.getAttribute("href");
          if (query === "Found‑Rᵧ") assert(href.startsWith("/projects/found-ry/"), query);
          else assert.equal(href, "/projects/found-ry/", query);
          assert.match(await first.textContent(), /Found‑Rᵧ/);
        }
        await input.fill("FoundRy");
        await page.waitForFunction(selector => document.querySelector(selector).textContent.includes("FoundRy"), overlayMode ? ".okh-search-status" : "#search-stats");
        await first.click();
        await page.waitForURL(`${baseUrl}/projects/found-ry/`);
        assert.match(await page.locator("h1").textContent(), /Found/);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      } finally { await browser.close(); }
    });
  }
}

for (const overlayMode of [true, false]) {
  test(`joined route names exclude fragments and partial names (${overlayMode ? "overlay" : "page"})`, async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    try {
      const entries = [
        { url: "/unrelated/#found-ry", title: "Unrelated anchor" },
        { url: "/other/?found-ry", title: "Unrelated query" },
        { url: "/projects/found-ry-extra/", title: "Longer name" },
        { url: "/projects/found-ry/", title: "Found‑Rᵧ" },
      ];
      await page.route("**/assets/data/search-index.json", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ entries }) }));
      await page.goto(`${baseUrl}${overlayMode ? "/prompt-forge/" : "/search/"}`);
      await dismissAnnouncement(page);
      if (overlayMode) await page.locator(".okh-search-trigger").click();
      await page.locator(overlayMode ? ".okh-search-input" : "#search-page-input").fill("FoundRy");
      const links = page.locator(overlayMode ? ".okh-search-results .okh-search-result" : "#search-results .okh-search-result");
      await links.first().waitFor();
      assert.equal(await links.count(), 1);
      assert.equal(await links.first().getAttribute("href"), "/projects/found-ry/");
    } finally { await browser.close(); }
  });

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

test("320px empty search keeps its query through keyboard full-search recovery", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const absentQuery = "missing & route?";
  try {
    await page.route("**/assets/data/search-index.json", route => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ entries: [
        { url: "/projects/found-ry/", title: "FoundRy", category: "Project", description: "recovery fixture", headings: [], body: "recovery fixture" },
        { url: "/writings/murderbird/", title: "The MurderBird", category: "Writing", description: "recovery fixture", headings: [], body: "recovery fixture" },
      ] }),
    }));
    await page.goto(`${baseUrl}/writings/`);
    await dismissAnnouncement(page);
    await page.locator(".okh-search-trigger").press("Enter");
    const overlay = page.getByRole("dialog", { name: "Search OverKill Hill", exact: true });
    await overlay.waitFor({ state: "visible" });
    const input = overlay.locator(".okh-search-input");
    await page.waitForFunction(() => document.activeElement?.matches(".okh-search-input"));
    await input.fill(absentQuery);
    await page.waitForFunction(() => document.querySelector(".okh-search-status").textContent.includes("No search results"));
    assert.equal(await overlay.locator(".okh-search-result").count(), 0);

    await input.press("Tab");
    assert.equal(await overlay.getByRole("button", { name: "Close search", exact: true }).evaluate(el => el === document.activeElement), true);
    await page.keyboard.press("Tab");
    const fullSearch = overlay.getByRole("link", { name: "Open full search →", exact: true });
    assert.equal(await fullSearch.evaluate(el => el === document.activeElement), true);
    await page.keyboard.press("Enter");
    await page.waitForURL(url => url.pathname === "/search/" && url.searchParams.get("q") === absentQuery);
    const pageInput = page.locator("#search-page-input");
    assert.equal(await pageInput.inputValue(), absentQuery);
    assert.equal(await pageInput.evaluate(el => el === document.activeElement), true);
    await page.waitForFunction(() => document.querySelector("#search-stats").textContent.includes("0 results"));

    await pageInput.fill("recovery");
    await page.waitForFunction(() => document.querySelectorAll("#search-results .okh-search-result").length === 2);
    assert.equal(new URL(page.url()).searchParams.get("q"), "recovery");
    assert.equal(await pageInput.evaluate(el => el === document.activeElement), true);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

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

test("320px keyboard retry preserves search state after an index outage", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  try {
    const count = await openSearchPage(page, async (route, attempt) => {
      await route.fulfill(attempt === 1
        ? { status: 503, contentType: "application/json", body: "{}" }
        : { contentType: "application/json", body: JSON.stringify({ entries: makeSearchEntries() }) });
    });
    const input = page.locator("#search-page-input");
    const retry = page.getByRole("button", { name: "Retry search index", exact: true });
    await retry.waitFor();
    assert.equal(count(), 1);
    assert.match(await page.locator("#search-stats").innerText(), /failed to load/i);
    await input.focus();
    await page.keyboard.press("Tab");
    assert.equal(await retry.evaluate(el => el === document.activeElement), true);
    await page.keyboard.press("Enter");
    await page.locator('#search-results a[href="/project-61/"]').waitFor();
    assert.equal(count(), 2);
    assert.equal(await input.inputValue(), "omega");
    assert.equal(await input.evaluate(el => el === document.activeElement), true);
    assert.equal(new URL(page.url()).searchParams.get("q"), "omega");
    assert.equal(new URL(page.url()).searchParams.get("cat"), "Project");
    assert.equal(await page.locator('#search-categories [data-cat="Project"]').getAttribute("aria-pressed"), "true");
    assert.equal(await page.locator("#search-results .okh-search-result").count(), 20);
    assert.equal(await retry.count(), 0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
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


async function settleReadingGeometry(page, selector) {
  let previous;
  let equal = 0;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 50));
    const sample = await page.locator(selector).evaluate(element => {
      const rect = element.getBoundingClientRect();
      return { values: [scrollY, rect.top, rect.height, document.documentElement.scrollHeight], fonts: document.fonts.status };
    });
    equal = sample.fonts !== 'loading' && previous && sample.values.every((value, index) => Math.abs(value - previous[index]) < 0.25) ? equal + 1 : 0;
    if (equal >= 4) return;
    previous = sample.values;
  }
  assert.fail('Reading geometry did not settle');
}

async function openArticleSection(page, articleHtml) {
  await page.route('**/*', route => new URL(route.request().url()).origin === baseUrl ? route.continue() : route.abort('blockedbyclient'));
  if (articleHtml) await page.route('**/writings/first-diagram-is-a-liar/', route => route.fulfill({ contentType: 'text/html', body: articleHtml }));
  await page.goto(`${baseUrl}/writings/first-diagram-is-a-liar/`, { waitUntil: 'load' });
  await dismissAnnouncement(page);
  await page.locator('a.okh-skip-link[href="#toc-widget"]').focus();
  await page.keyboard.press('Enter');
  await settleReadingGeometry(page, '#toc-widget');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator(':focus').getAttribute('href'), '#the-cost-of-a-tidy-lie');
  await page.keyboard.press('Enter');
  await settleReadingGeometry(page, '#the-cost-of-a-tidy-lie');
}

async function openHistorySearch(page, query = 'first diagram') {
  await page.keyboard.press('Control+k');
  await page.waitForFunction(() => document.querySelector('.okh-search-overlay').dataset.open === 'true' && document.activeElement.matches('.okh-search-input'));
  await page.locator('.okh-search-input').fill(query);
  await page.locator('.okh-search-result').first().waitFor();
}

async function assertVisibleReadingFocus(page, id) {
  const state = await page.evaluate(() => {
    const active = document.activeElement;
    const rect = active.getBoundingClientRect();
    return { id: active.id, top: rect.top, height: innerHeight, header: document.querySelector('header').getBoundingClientRect().bottom, overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth) };
  });
  assert.equal(state.id, id);
  assert.ok(state.top >= Math.max(0, state.header) && state.top < state.height, JSON.stringify(state));
  assert.equal(state.overflow, 0);
}

const researchHref = 'https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1551-6708.1987.tb00863.x';
for (const dismissal of ['Escape', 'Close button']) {
  test(`search restores a transient article opener after ${dismissal}`, async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'reduce' });
    try {
      await openArticleSection(page);
      const before = await page.evaluate(() => scrollY);
      await openHistorySearch(page);
      if (dismissal === 'Close button') {
        await page.keyboard.press('Tab');
        assert.equal(await page.locator('.okh-search-close:focus').count(), 1);
        await page.keyboard.press('Enter');
      } else await page.keyboard.press('Escape');
      await page.waitForFunction(() => document.querySelector('.okh-search-overlay').dataset.open === 'false');
      await settleReadingGeometry(page, '#the-cost-of-a-tidy-lie');
      await assertVisibleReadingFocus(page, 'the-cost-of-a-tidy-lie');
      assert.ok(Math.abs(await page.evaluate(() => scrollY) - before) < 1);
      assert.equal(await page.locator('.okh-search-input').inputValue(), 'first diagram');
      await page.keyboard.press('Tab');
      assert.equal(await page.locator(':focus').getAttribute('href'), researchHref);
      assert.equal(await page.locator('#the-cost-of-a-tidy-lie').getAttribute('tabindex'), null);
    } finally { await browser.close(); }
  });
}

test('search dismissal preserves native Back and Forward reading focus', async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'reduce' });
  try {
    await openArticleSection(page);
    await openHistorySearch(page);
    await page.goBack();
    await settleReadingGeometry(page, '#toc-widget');
    assert.equal(new URL(page.url()).hash, '#toc-widget');
    assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'false');
    await assertVisibleReadingFocus(page, 'toc-widget');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), '#read-the-story-work-through-the-idea');
    await openHistorySearch(page);
    await page.goForward();
    await settleReadingGeometry(page, '#the-cost-of-a-tidy-lie');
    assert.equal(new URL(page.url()).hash, '#the-cost-of-a-tidy-lie');
    assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'false');
    await assertVisibleReadingFocus(page, 'the-cost-of-a-tidy-lie');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), researchHref);
  } finally { await browser.close(); }
});

for (const [alias, heading, nextHref] of [
  ['roy', 'roy-what-did-the-words-buy', 'https://mermaid.js.org/intro/'],
  ['scoring-model', 'how-the-council-experiment-was-run', 'https://github.com/OKHP3/first-diagram-is-a-liar/tree/main/archive/diagramming-shootout'],
  ['council-scoring', 'what-the-two-rounds-actually-reveal', 'https://raw.githubusercontent.com/OKHP3/first-diagram-is-a-liar/main/archive/diagramming-shootout/images/v1/etch-ai-sketch-using-a-council-to-design-at-velocity-copilot-v1.png'],
]) {
  test(`search history continues reading at the visible heading for legacy #${alias}`, async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'reduce' });
    try {
      await page.route('**/*', route => new URL(route.request().url()).origin === baseUrl ? route.continue() : route.abort('blockedbyclient'));
      await page.goto(`${baseUrl}/writings/first-diagram-is-a-liar/#${alias}`, { waitUntil: 'load' });
      await dismissAnnouncement(page);
      await settleReadingGeometry(page, `#${heading}`);
      const nativeScroll = await page.evaluate(() => scrollY);
      await page.locator('a.okh-skip-link[href="#toc-widget"]').focus();
      await page.keyboard.press('Enter');
      await settleReadingGeometry(page, '#toc-widget');
      await openHistorySearch(page);
      await page.goBack();
      await settleReadingGeometry(page, `#${heading}`);
      assert.equal(new URL(page.url()).hash, `#${alias}`);
      assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'false');
      await assertVisibleReadingFocus(page, heading);
      assert.ok(Math.abs(await page.evaluate(() => scrollY) - nativeScroll) < 2, 'Back retains native alias reading position');
      await page.keyboard.press('Tab');
      assert.equal(await page.locator(':focus').getAttribute('href'), nextHref);
      // Visit the compatibility URL through native same-document navigation,
      // then exercise Forward independently of the Back restoration above.
      await page.goto(`${baseUrl}/writings/first-diagram-is-a-liar/#toc-widget`);
      await settleReadingGeometry(page, '#toc-widget');
      await page.goto(`${baseUrl}/writings/first-diagram-is-a-liar/#${alias}`);
      await settleReadingGeometry(page, `#${heading}`);
      await page.goBack();
      await settleReadingGeometry(page, '#toc-widget');
      await openHistorySearch(page);
      await page.goForward();
      await settleReadingGeometry(page, `#${heading}`);
      assert.equal(new URL(page.url()).hash, `#${alias}`);
      assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'false');
      await assertVisibleReadingFocus(page, heading);
      assert.ok(Math.abs(await page.evaluate(() => scrollY) - nativeScroll) < 2, 'Forward retains native alias reading position');
      await page.keyboard.press('Tab');
      assert.equal(await page.locator(':focus').getAttribute('href'), nextHref);
    } finally { await browser.close(); }
  });
}

test('search history does not reinterpret non-alias hidden content as a sibling focus target', async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'reduce' });
  try {
    const article = await readFile(resolve(repositoryRoot, 'writings/first-diagram-is-a-liar/index.html'), 'utf8');
    const marker = '<span aria-hidden="true" id="roy"></span>';
    assert.ok(article.includes(marker));
    const fixture = article.replace(marker, '<span aria-hidden="true" id="roy">Hidden content</span><button id="not-a-fragment-alias">Unrelated control</button>');
    await page.route('**/*', route => new URL(route.request().url()).origin === baseUrl ? route.continue() : route.abort('blockedbyclient'));
    await page.route('**/writings/first-diagram-is-a-liar/', route => route.fulfill({ contentType: 'text/html', body: fixture }));
    await page.goto(`${baseUrl}/writings/first-diagram-is-a-liar/#roy`, { waitUntil: 'load' });
    await dismissAnnouncement(page);
    await settleReadingGeometry(page, '#roy-what-did-the-words-buy');
    await page.locator('a.okh-skip-link[href="#toc-widget"]').focus();
    await page.keyboard.press('Enter');
    await settleReadingGeometry(page, '#toc-widget');
    await openHistorySearch(page);
    await page.goBack();
    await settleReadingGeometry(page, '#roy-what-did-the-words-buy');
    assert.equal(new URL(page.url()).hash, '#roy');
    assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'false');
    assert.equal(await page.locator('.okh-search-trigger:focus').count(), 1);
    assert.equal(await page.locator('#not-a-fragment-alias:focus').count(), 0);
  } finally { await browser.close(); }
});

test('query-only history dismisses overlay search and restores its visible trigger', async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 } });
  try {
    await openSearchPage(page, route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ entries: makeSearchEntries() }) }), '/search/?q=omega');
    await page.locator('[data-cat="Project"]').click();
    await page.locator('[data-cat="Brand"]').click();
    await page.locator('.okh-search-trigger').focus();
    await openHistorySearch(page, 'omega');
    await page.goBack();
    await settleReadingGeometry(page, 'header');
    assert.equal(new URL(page.url()).searchParams.get('cat'), 'Project');
    assert.equal(await page.locator('[data-cat="Project"]').getAttribute('aria-pressed'), 'true');
    assert.equal(await page.locator('#search-page-input').inputValue(), 'omega');
    assert.equal(await page.locator('#search-results .okh-search-result').count(), 20);
    assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'false');
    assert.equal(await page.locator('.okh-search-trigger:focus').count(), 1);
    assert.equal(await page.locator('.okh-search-input').inputValue(), 'omega');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('.okh-search-overlay :focus').count(), 0);
  } finally { await browser.close(); }
});

test('pending history focus cannot replace a newly reopened search interaction', async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'reduce' });
  try {
    await openArticleSection(page);
    await openHistorySearch(page);
    // Deliberately delay animation callbacks to exercise an adversarial ordering.
    await page.evaluate(() => {
      window.__historyFrames = [];
      window.__nativeHistoryFrame = window.requestAnimationFrame;
      window.requestAnimationFrame = callback => window.__historyFrames.push(callback);
    });
    await page.goBack();
    await page.waitForFunction(() => document.querySelector('.okh-search-overlay').dataset.open === 'false');
    assert.ok(await page.evaluate(() => window.__historyFrames.length > 0));
    await openHistorySearch(page, 'mermaid');
    await page.evaluate(() => {
      const queued = window.__historyFrames;
      window.requestAnimationFrame = window.__nativeHistoryFrame;
      queued.forEach(callback => window.requestAnimationFrame(callback));
    });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'true');
    assert.equal(await page.locator('.okh-search-input:focus').count(), 1);
    assert.equal(await page.locator('.okh-search-input').inputValue(), 'mermaid');
    assert.equal(new URL(page.url()).hash, '#toc-widget');
  } finally { await browser.close(); }
});

test('search preserves the native reading position through visible-scrollbar history', async () => {
  const browser = await chromium.launch({ headless: true, ignoreDefaultArgs: ['--hide-scrollbars'] });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'no-preference' });
  try {
    await openArticleSection(page);
    const initial = await page.evaluate(() => ({ scroll: scrollY, gutter: innerWidth - document.documentElement.clientWidth }));
    assert.ok(initial.gutter > 0, 'This regression requires actual classic scrollbar geometry');
    await openHistorySearch(page);
    await page.goBack();
    await settleReadingGeometry(page, '#toc-widget');
    await assertVisibleReadingFocus(page, 'toc-widget');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), '#read-the-story-work-through-the-idea');
    await openHistorySearch(page);
    await page.goForward();
    await settleReadingGeometry(page, '#the-cost-of-a-tidy-lie');
    await assertVisibleReadingFocus(page, 'the-cost-of-a-tidy-lie');
    assert.ok(Math.abs(await page.evaluate(() => scrollY) - initial.scroll) < 2, 'Search must not rewrite the section entry through scrollbar reflow');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), researchHref);
  } finally { await browser.close(); }
});

test('search preserves a preexisting important stable gutter through ordinary and history dismissal', async () => {
  const browser = await chromium.launch({ headless: true, ignoreDefaultArgs: ['--hide-scrollbars'] });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'no-preference' });
  const styles = () => page.evaluate(() => ({
    gutter: document.documentElement.style.getPropertyValue('scrollbar-gutter'),
    priority: document.documentElement.style.getPropertyPriority('scrollbar-gutter'),
    overflow: document.documentElement.style.overflow,
  }));
  try {
    const article = await readFile(resolve(repositoryRoot, 'writings/first-diagram-is-a-liar/index.html'), 'utf8');
    const fixture = article.replace('<html ', '<html style="scrollbar-gutter: stable both-edges !important; overflow: auto" ');
    assert.notEqual(fixture, article);
    await openArticleSection(page, fixture);
    const initial = await styles();
    assert.deepEqual(initial, { gutter: 'stable both-edges', priority: 'important', overflow: 'auto' });
    await openHistorySearch(page);
    assert.equal((await styles()).gutter, initial.gutter);
    assert.equal((await styles()).priority, initial.priority);
    await page.keyboard.press('Escape');
    assert.deepEqual(await styles(), initial);
    await assertVisibleReadingFocus(page, 'the-cost-of-a-tidy-lie');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), researchHref);
    const link = await page.locator(':focus').boundingBox();
    assert.ok(link && link.y >= 0 && link.y < 844);
    await openHistorySearch(page);
    await page.goBack();
    await settleReadingGeometry(page, '#toc-widget');
    assert.deepEqual(await styles(), initial);
    await assertVisibleReadingFocus(page, 'toc-widget');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), '#read-the-story-work-through-the-idea');
  } finally { await browser.close(); }
});

test('search dismissal keeps a newer gutter declaration from another controller', async () => {
  const browser = await chromium.launch({ headless: true, ignoreDefaultArgs: ['--hide-scrollbars'] });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'no-preference' });
  try {
    await openArticleSection(page);
    await openHistorySearch(page);
    await page.evaluate(() => document.documentElement.style.setProperty('scrollbar-gutter', 'stable both-edges', 'important'));
    await page.keyboard.press('Escape');
    assert.deepEqual(await page.evaluate(() => ({ value: document.documentElement.style.getPropertyValue('scrollbar-gutter'), priority: document.documentElement.style.getPropertyPriority('scrollbar-gutter') })), { value: 'stable both-edges', priority: 'important' });
    await assertVisibleReadingFocus(page, 'the-cost-of-a-tidy-lie');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), researchHref);
  } finally { await browser.close(); }
});

test('search can open when the scrollbar-gutter convenience getter is unavailable', async () => {
  const browser = await chromium.launch({ headless: true, ignoreDefaultArgs: ['--hide-scrollbars'] });
  const page = await browser.newPage({ viewport: { width: 320, height: 844 }, reducedMotion: 'no-preference' });
  try {
    // Emulate an older engine's missing CSS convenience property while retaining
    // the standard CSSStyleDeclaration methods and every other computed value.
    await page.addInitScript(() => {
      const computed = window.getComputedStyle;
      window.getComputedStyle = (element, ...args) => {
        const style = computed.call(window, element, ...args);
        if (element !== document.documentElement) return style;
        return new Proxy(style, { get(target, name) {
          if (name === 'scrollbarGutter') return undefined;
          const value = Reflect.get(target, name, target);
          return typeof value === 'function' ? value.bind(target) : value;
        } });
      };
    });
    await openArticleSection(page);
    assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).scrollbarGutter), undefined);
    assert.ok(await page.evaluate(() => innerWidth > document.documentElement.clientWidth), 'Reach the classic-scrollbar feature branch');
    await page.keyboard.press('Control+k');
    assert.equal(await page.locator('.okh-search-overlay').getAttribute('data-open'), 'true');
    await page.locator('.okh-search-input').press('Escape');
    await assertVisibleReadingFocus(page, 'the-cost-of-a-tidy-lie');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').getAttribute('href'), researchHref);
  } finally { await browser.close(); }
});

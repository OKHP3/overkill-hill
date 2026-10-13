import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { extname, resolve } from "node:path";

const repositoryRoot = resolve(import.meta.dirname, "..");
let server;
let baseUrl;

function contentTypeFor(pathname) {
  return {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
  }[extname(pathname).toLowerCase()] || "text/plain; charset=utf-8";
}

before(async () => {
  server = createServer(async (request, response) => {
    const url = new URL(request.url, "http://embed-test");
    const filePath = resolve(repositoryRoot, "." + (url.pathname.endsWith("/") ? url.pathname + "index.html" : url.pathname));
    if (!filePath.startsWith(repositoryRoot)) {
      response.writeHead(403);
      response.end();
      return;
    }
    try {
      const body = await readFile(filePath);
      response.writeHead(200, { "content-type": contentTypeFor(filePath) });
      response.end(body);
    } catch {
      response.writeHead(404);
      response.end("missing");
    }
  });
  await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise((resolveClose, rejectClose) =>
    server.close((error) => (error ? rejectClose(error) : resolveClose()))
  );
});

const embeds = [
  ["/projects/abrahamic-reference-engine/", "are-tool-iframe", "are-reload-btn", "https://okhp3.github.io/abrahamic-reference-engine/"],
  ["/projects/bpmn-for-mermaid/", "bpmn-tool-iframe", "bpmn-reload-btn", "https://okhp3.github.io/mermaid-diagram-bpmn/"],
  ["/projects/found-ry/", "foundry-tool-iframe", "foundry-reload-btn", "https://okhp3.github.io/overkill-hill-foundry/"],
  ["/projects/mermaid-theme-builder/", "tool-iframe", "reload-btn", "https://okhp3.github.io/mermaid-theme-builder/?embed=1"],
  ["/skillz-forge/", "tool-iframe", "reload-btn", "https://okhp3.github.io/skillz/"],
  ["/skillz-forge/skillz-shield/", "tool-iframe", "reload-btn", "https://okhp3.github.io/skillz-shield/"],
];

async function waitForEmbeddedReload(page, iframeId, reloadId, childUrl, timeout = 10_000) {
  // Settle the lazy iframe's first load so it cannot satisfy the reload check.
  await page.locator(`#${iframeId}`).scrollIntoViewIfNeeded();
  await page.frameLocator(`#${iframeId}`).locator("main").waitFor({ state: "visible", timeout });
  const [request] = await Promise.all([
    page.waitForRequest((candidate) => candidate.url() === childUrl
      && candidate.isNavigationRequest()
      && candidate.frame().parentFrame() === page.mainFrame(), { timeout }),
    page.locator(`#${reloadId}`).click({ timeout }),
  ]);
  const response = await request.response();
  assert.ok(response, `${iframeId}: reload did not receive a response`);
  assert.equal(response.status(), 200, `${iframeId}: reload response failed`);
  assert.equal(await response.finished(), null, `${iframeId}: reload response did not finish`);
}

test("reload observation waits for delayed navigation and rejects a broken button", async () => {
  const browser = await chromium.launch({ headless: true });
  const childUrl = embeds[2][3];
  try {
    for (const delay of [250, null]) {
      const page = await browser.newPage();
      await page.route(childUrl, (route) => route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<!doctype html><main>Reload fixture</main>",
      }));
      // Only this disposable fixture delays or disables the button; site code is unchanged.
      const action = delay === null ? "" : `setTimeout(() => { document.getElementById('fixture-frame').src = '${childUrl}'; }, ${delay})`;
      await page.setContent(`<iframe id="fixture-frame" src="${childUrl}"></iframe>
        <button id="fixture-reload" onclick="${action}">Reload</button>`);
      await page.frameLocator("#fixture-frame").locator("main").waitFor({ state: "visible" });
      if (delay === null) {
        await assert.rejects(
          waitForEmbeddedReload(page, "fixture-frame", "fixture-reload", childUrl, 500),
          (error) => error.message.includes('waiting for event "request"') && error.message.includes("Timeout"),
        );
      } else {
        await waitForEmbeddedReload(page, "fixture-frame", "fixture-reload", childUrl);
      }
      await page.close();
    }
  } finally {
    await browser.close();
  }
});

test("legacy Skillz links preserve the destination section and query", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.route("https://**", (route) => route.abort());
    for (const legacy of ["/projects/skillz/", "/projects/skillz/index.html"]) {
      await page.goto(`${baseUrl}${legacy}?ref=bookmark#install-guide`);
      await page.waitForURL(`${baseUrl}/skillz-forge/?ref=bookmark#install-guide`);
      assert.equal(await page.locator("h1").innerText(), "Skillz Forge");
      assert.equal(await page.locator("#install-guide").count(), 1);
    }
    const offline = await browser.newContext({ javaScriptEnabled: false });
    const plain = await offline.newPage();
    await plain.goto(`${baseUrl}/projects/skillz/`);
    await plain.waitForURL(`${baseUrl}/skillz-forge/`);
    assert.equal(await plain.locator("h1").innerText(), "Skillz Forge");
    await offline.close();
  } finally {
    await browser.close();
  }
});

test("embedded parent pages preserve the security contract and reload fallback", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    for (const [path, iframeId, reloadId, childUrl] of embeds) {
      await page.route("https://okhp3.github.io/**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "text/html",
          body: "<!doctype html><title>Embedded fixture</title><main>Fixture</main>",
        });
      });
      await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
      const iframe = page.locator(`#${iframeId}`);
      await assert.equal(await iframe.getAttribute("referrerpolicy"), "strict-origin-when-cross-origin");
      await assert.equal(await iframe.getAttribute("sandbox"), "allow-scripts allow-same-origin allow-forms" + (path.includes("bpmn") || path.includes("mermaid-theme") ? " allow-downloads" : ""));
      await assert.equal(await iframe.getAttribute("allow"), "clipboard-read 'none'; clipboard-write 'none'; fullscreen 'none'");
      await assert.equal(await iframe.getAttribute("src"), childUrl);
      const directLaunch = page.locator(`a[target="_blank"][href^="${new URL(childUrl).origin}"]`);
      await assert.equal(await directLaunch.count() > 0, true);
      await waitForEmbeddedReload(page, iframeId, reloadId, childUrl);
    }
  } finally {
    await browser.close();
  }
});

test("BPMN parent copy writes the advertised DSL payload when clipboard is available", async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: baseUrl });
  const page = await context.newPage();
  try {
    await page.route("https://okhp3.github.io/**", async (route) => {
      await route.fulfill({ status: 200, contentType: "text/html", body: "<main>Fixture</main>" });
    });
    await page.goto(`${baseUrl}/projects/bpmn-for-mermaid/`, { waitUntil: "networkidle" });
    await page.locator("#dsl-copy-btn").click();
    const copied = await page.evaluate(() => navigator.clipboard?.readText() || "");
    if (copied) {
      assert.match(copied, /bpmn-beta/);
      assert.match(copied, /Approved\?/);
    } else {
      assert.notEqual(await page.locator("#dsl-copy-btn").innerText(), "✓ Copied");
    }
  } finally {
    await context.close();
    await browser.close();
  }
});

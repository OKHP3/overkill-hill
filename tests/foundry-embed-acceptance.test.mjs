import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { after, before, test } from "node:test";
import { extname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const repositoryRoot = resolve(import.meta.dirname, "..");
const pagePath = "/projects/found-ry/";
const liveAppUrl = "https://okhp3.github.io/overkill-hill-foundry/";
let server;
let baseUrl;

function contentTypeFor(pathname) {
  return {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
  }[extname(pathname).toLowerCase()] || "text/plain; charset=utf-8";
}

before(async () => {
  server = createServer(async (request, response) => {
    const url = new URL(request.url, "http://foundry-embed-test");
    const requested = url.pathname.endsWith("/") ? `${url.pathname}index.html` : url.pathname;
    const filePath = resolve(repositoryRoot, `.${requested}`);
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
  await new Promise((listenResolve) => server.listen(Number(process.env.PORT) || 0, "127.0.0.1", listenResolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise((closeResolve, closeReject) =>
    server.close((error) => (error ? closeReject(error) : closeResolve()))
  );
});

test("FoundRy embed keeps the external-app sandbox and direct fallback affordances", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.goto(`${baseUrl}${pagePath}`, { waitUntil: "domcontentloaded" });

    const iframe = page.locator("#foundry-tool-iframe");
    assert.equal(await iframe.getAttribute("src"), liveAppUrl);
    assert.equal(await iframe.getAttribute("title"), "The OverKill Hill Found-Ry: Custom GPT build workbench");
    assert.equal(await iframe.getAttribute("referrerpolicy"), "strict-origin-when-cross-origin");
    assert.equal(await iframe.getAttribute("allow"), "clipboard-read 'none'; clipboard-write 'none'; fullscreen 'none'");
    assert.equal(await iframe.getAttribute("sandbox"), "allow-scripts allow-same-origin allow-forms");
    assert.equal((await iframe.getAttribute("sandbox"))?.includes("allow-downloads"), false);

    const directLinks = page.locator(`a[target="_blank"][href="${liveAppUrl}"]`);
    assert.ok((await directLinks.count()) >= 3, "hero, toolbar, and fallback links should reach the direct app");
    assert.equal(await page.locator("#foundry-reload-btn").getAttribute("aria-label"), "Reload workbench");
    assert.equal(await page.locator("#foundry-reload-btn").isEnabled(), true);
    assert.equal(await page.locator("#foundry-reload-btn").getAttribute("title"), "Reload workbench");
  } finally {
    await browser.close();
  }
});

test("FoundRy embed controls are keyboard reachable and reload remains local to the iframe", async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.goto(`${baseUrl}${pagePath}`, { waitUntil: "domcontentloaded" });
    await page.locator("#embed-tool").scrollIntoViewIfNeeded();
    await page.locator("#foundry-reload-btn").focus();
    assert.equal(await page.evaluate(() => document.activeElement?.id), "foundry-reload-btn");
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("href")), liveAppUrl);

    const iframeReload = page.locator("#foundry-tool-iframe").evaluate(
      (iframe) => new Promise((resolve) => iframe.addEventListener("load", resolve, { once: true }))
    );
    await page.locator("#foundry-reload-btn").click();
    await iframeReload;
    assert.equal(page.url(), `${baseUrl}${pagePath}`);
  } finally {
    await browser.close();
  }
});

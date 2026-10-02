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
      let childRequests = 0;
      await page.route("https://okhp3.github.io/**", async (route) => {
        childRequests += 1;
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
      await page.locator(`#${reloadId}`).click();
      await page.waitForTimeout(100);
      await assert.equal(childRequests >= 2, true);
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

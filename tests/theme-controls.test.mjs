import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { dirname, extname, join, resolve, sep } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createHash } from "node:crypto";

const testsDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = join(testsDirectory, "..");
const appScript = await readFile(join(repositoryRoot, "assets", "js", "app.js"), "utf8");
const brandThemeContract = JSON.parse(
  await readFile(join(repositoryRoot, "config", "brand-theme-contract.json"), "utf8"),
);
const execFileAsync = promisify(execFile);

const BRAND_EXPECTATIONS = brandThemeContract.brands;

let browser;

before(async () => {
  browser = await chromium.launch({ headless: true });
});

after(async () => {
  await browser?.close();
});

function fixtureMarkup(bodyClass = "") {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="theme-color" media="(prefers-color-scheme: light)" content="fixture-light">
    <meta name="theme-color" media="(prefers-color-scheme: dark)" content="fixture-dark">
  </head>
  <body class="${bodyClass}">
    <header class="site-header">
      <div class="container"></div>
    </header>
    <main><h1>Theme control fixture</h1></main>
    <script>${appScript}</script>
  </body>
</html>`;
}

function withFoundation(markup, css, script) {
  // The browser fixture injects the reviewed external script as inline text.
  // Remove production CSP metadata so Chromium can execute that fixture code;
  // CSP enforcement is covered by the dedicated CSP audit.
  const withoutScripts = markup
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(
      /<meta\b[^>]*http-equiv\s*=\s*["']Content-Security-Policy["'][^>]*>/gi,
      "",
    );
  const withStyles = css ? withoutScripts.replace("</head>", `<style>${css}</style>\n</head>`) : withoutScripts;
  const injected = `<script>${script}</script>`;
  return withStyles.includes("</body>") ? withStyles.replace("</body>", `${injected}</body>`) : `${withStyles}${injected}`;
}

async function openFixture({
  bodyClass = "",
  storage = {},
  colorScheme = "light",
  markup = fixtureMarkup(bodyClass),
  css = "",
  script = appScript,
} = {}) {
  const page = await browser.newPage();
  await page.emulateMedia({ colorScheme });
  await page.addInitScript(({ mode, values }) => {
    const saved = { ...values };
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        if (mode === "blocked") {
          throw new DOMException("Storage is disabled", "SecurityError");
        }
        return {
          getItem(key) {
            return Object.prototype.hasOwnProperty.call(saved, key) ? saved[key] : null;
          },
          setItem(key, value) {
            saved[key] = String(value);
          },
          removeItem(key) {
            delete saved[key];
          },
        };
      },
    });
  }, {
    mode: storage === "blocked" ? "blocked" : "available",
    values: storage === "blocked" ? {} : storage,
  });
  await page.setContent(withFoundation(markup, css, script), { waitUntil: "domcontentloaded" });
  return page;
}

async function readState(page, selector) {
  return page.locator(selector).evaluate((toggle) => ({
    state: toggle.dataset.state,
    theme: document.documentElement.getAttribute("data-theme"),
    colorScheme: document.documentElement.getAttribute("data-color-scheme"),
    labels: toggle.getAttribute("aria-label"),
    colors: [...document.querySelectorAll('meta[name="theme-color"]')].map((meta) => ({
      media: meta.getAttribute("media"),
      content: meta.getAttribute("content"),
    })),
  }));
}

async function clickAndRead(page, selector) {
  await page.locator(selector).click();
  return readState(page, selector);
}

async function serveGeneratedHomepage() {
  const server = createServer((request, response) => {
    const pathname = new URL(request.url || "/", "http://theme-controls.test").pathname;
    const resolvedPath = resolve(repositoryRoot, `.${pathname.endsWith("/") ? `${pathname}index.html` : pathname}`);
    if (resolvedPath !== repositoryRoot && !resolvedPath.startsWith(`${repositoryRoot}${sep}`)) {
      response.writeHead(403);
      response.end("forbidden");
      return;
    }
    const contentType = {
      ".css": "text/css; charset=utf-8",
      ".html": "text/html; charset=utf-8",
      ".ico": "image/x-icon",
      ".js": "text/javascript; charset=utf-8",
      ".json": "application/json; charset=utf-8",
      ".png": "image/png",
      ".svg": "image/svg+xml",
      ".webp": "image/webp",
    }[extname(resolvedPath).toLowerCase()] || "application/octet-stream";
    readFile(resolvedPath).then((body) => {
      response.writeHead(200, { "content-type": contentType });
      response.end(body);
    }).catch(() => {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      response.end("missing");
    });
  });
  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  return {
    server,
    url: `http://127.0.0.1:${server.address().port}/`,
  };
}

async function openGeneratedHomepage({ storageMode, storedTheme, colorScheme }) {
  const { server, url } = await serveGeneratedHomepage();
  const page = await browser.newPage();
  const pageErrors = [];
  let appScriptRequests = 0;
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.emulateMedia({ colorScheme });
  await page.addInitScript(({ mode, preference }) => {
    if (location.origin === "null") return;
    if (mode === "blocked") {
      Object.defineProperty(window, "localStorage", {
        configurable: true,
        get() {
          throw new DOMException("Storage is disabled", "SecurityError");
        },
      });
    } else {
      window.localStorage.setItem("okh-theme", preference);
    }
  }, { mode: storageMode, preference: storedTheme });
  await page.route(/\/assets\/js\/app\.js(?:\?.*)?$/, (route) => {
    appScriptRequests += 1;
    return route.abort();
  });
  const response = await page.goto(url, { waitUntil: "domcontentloaded" });
  return { appScriptRequests, page, pageErrors, response, server };
}

test("OKH supports system, light, and dark transitions", async () => {
  const page = await openFixture();
  try {
    const selector = ".theme-toggle";
    assert.deepEqual(await readState(page, selector), {
      state: "system",
      theme: "light",
      colorScheme: null,
      labels: "Switch to light mode",
      colors: [
        { media: "(prefers-color-scheme: light)", content: "fixture-light" },
        { media: "(prefers-color-scheme: dark)", content: "fixture-dark" },
      ],
    });

    assert.equal((await clickAndRead(page, selector)).state, "light");
    assert.equal((await readState(page, selector)).theme, "light");

    assert.equal((await clickAndRead(page, selector)).state, "dark");
    assert.equal((await readState(page, selector)).theme, "dark");

    assert.equal((await clickAndRead(page, selector)).state, "system");
    assert.equal((await readState(page, selector)).theme, "light");

    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
    assert.equal((await readState(page, selector)).theme, "dark");
  } finally {
    await page.close();
  }
});


test("Glee and AskJamie keep their light baseline and update theme-color metadata", async () => {
  for (const [brand, expected] of Object.entries(BRAND_EXPECTATIONS)) {
    const page = await openFixture({ bodyClass: expected.bodyClass });
    try {
      const selector = ".glee-color-toggle";
      assert.deepEqual(await readState(page, selector), {
        state: "auto",
        theme: "light",
        colorScheme: null,
        labels: "Color scheme: following your device — click to pin light",
        colors: [
          { media: "(prefers-color-scheme: light)", content: expected.light },
          { media: "(prefers-color-scheme: dark)", content: expected.dark },
        ],
      }, `${brand} auto baseline`);

      const light = await clickAndRead(page, selector);
      assert.equal(light.state, "light", `${brand} light state`);
      assert.equal(light.theme, "light", `${brand} light data-theme baseline`);
      assert.equal(light.colorScheme, "light", `${brand} light data-color-scheme`);
      assert(light.colors.every(({ content }) => content === expected.light), `${brand} light metadata`);

      const dark = await clickAndRead(page, selector);
      assert.equal(dark.state, "dark", `${brand} dark state`);
      assert.equal(dark.theme, "light", `${brand} dark data-theme baseline`);
      assert.equal(dark.colorScheme, "dark", `${brand} dark data-color-scheme`);
      assert(dark.colors.every(({ content }) => content === expected.dark), `${brand} dark metadata`);

      const auto = await clickAndRead(page, selector);
      assert.equal(auto.state, "auto", `${brand} auto state`);
      assert.equal(auto.theme, "light", `${brand} auto data-theme baseline`);
      assert.equal(auto.colorScheme, null, `${brand} auto removes data-color-scheme`);
      assert.deepEqual(auto.colors.map(({ media, content }) => ({ media, content })), [
        { media: "(prefers-color-scheme: light)", content: expected.light },
        { media: "(prefers-color-scheme: dark)", content: expected.dark },
      ], `${brand} auto metadata`);
    } finally {
      await page.close();
    }
  }
});

test("brand control colors stay aligned with the reviewed theme contract", () => {
  for (const expected of Object.values(BRAND_EXPECTATIONS)) {
    assert.match(
      appScript,
      new RegExp(`"light":\\s*["']${expected.light}["']`),
      `${expected.name} light color`,
    );
    assert.match(
      appScript,
      new RegExp(`"dark":\\s*["']${expected.dark}["']`),
      `${expected.name} dark color`,
    );
    assert.match(
      appScript,
      new RegExp(`"storageKey":\\s*["']${expected.storageKey}["']`),
      `${expected.name} storage key`,
    );
  }
});

test("browser theme constants are generated from the reviewed contract", async () => {
  await assert.doesNotReject(
    () => execFileAsync("python3", ["scripts/generate-theme-controls.py", "--check"], {
      cwd: repositoryRoot,
    }),
  );
});

test("all three theme controls survive disabled storage", async () => {
  const fixtures = [
    { name: "OKH", bodyClass: "", selector: ".theme-toggle" },
    { name: "Glee", bodyClass: "glee-main", selector: ".glee-color-toggle" },
    { name: "AskJamie", bodyClass: "askjamie-main", selector: ".glee-color-toggle" },
  ];

  for (const fixture of fixtures) {
    const pageErrors = [];
    const page = await openFixture({ bodyClass: fixture.bodyClass, storage: "blocked" });
    page.on("pageerror", (error) => pageErrors.push(error));
    try {
      const initial = await readState(page, fixture.selector);
      assert.equal(initial.state, fixture.name === "OKH" ? "system" : "auto", `${fixture.name} fallback state`);
      assert.equal(initial.theme, "light", `${fixture.name} fallback theme`);

      await clickAndRead(page, fixture.selector);
      await clickAndRead(page, fixture.selector);
      await clickAndRead(page, fixture.selector);

      const final = await readState(page, fixture.selector);
      assert.equal(final.state, fixture.name === "OKH" ? "system" : "auto", `${fixture.name} cycles without storage`);
      assert.equal(pageErrors.length, 0, `${fixture.name} has no storage exception`);
    } finally {
      await page.close();
    }
  }
});

const GENERATED_HEAD_SCENARIOS = [
  { name: "uses the dark system preference when storage is blocked", storageMode: "blocked", colorScheme: "dark", expectedTheme: "dark" },
  { name: "uses the light system preference when storage is blocked", storageMode: "blocked", colorScheme: "light", expectedTheme: "light" },
  { name: "keeps a stored dark preference without app.js", storageMode: "available", storedTheme: "dark", colorScheme: "light", expectedTheme: "dark" },
  { name: "keeps a stored light preference without app.js", storageMode: "available", storedTheme: "light", colorScheme: "dark", expectedTheme: "light" },
];

for (const scenario of GENERATED_HEAD_SCENARIOS) {
  test(`generated homepage head initializer ${scenario.name}`, async () => {
    const { appScriptRequests, page, pageErrors, response, server } = await openGeneratedHomepage(scenario);
    try {
      assert.equal(response.status(), 200);
      assert.equal(appScriptRequests, 1, "the external app.js request should be blocked");
      assert.equal(
        await page.locator("head script").evaluateAll((scripts) =>
          scripts.some((script) => script.textContent.includes('getItem("okh-theme")')),
        ),
        true,
        "the actual generated homepage must include the early theme initializer",
      );
      assert.equal(await page.locator("html").getAttribute("data-theme"), scenario.expectedTheme);
      assert.deepEqual(pageErrors, []);
    } finally {
      await page.close();
      await new Promise((resolveClose, rejectClose) => {
        server.close((error) => error ? rejectClose(error) : resolveClose());
      });
    }
  });
}

const DEFAULT_SITE_ROOTS = [
  { name: "OKH", expectedRoot: ".", root: join(repositoryRoot, "..", "overkill-hill"), bodyClass: "", selector: ".theme-toggle" },
  { name: "Glee", expectedRoot: ".ci/theme-sites/glee-fullytools", root: join(repositoryRoot, "..", "glee-fullytools"), bodyClass: "glee-main", selector: ".glee-color-toggle" },
  { name: "AskJamie", expectedRoot: ".ci/theme-sites/askjamie", root: join(repositoryRoot, "..", "askjamie"), bodyClass: "askjamie-main", selector: ".glee-color-toggle" },
];

function configuredSiteInputs() {
  if (process.env.THEME_CONTROL_SITES) {
    const configured = JSON.parse(process.env.THEME_CONTROL_SITES);
    assert.ok(Array.isArray(configured), "THEME_CONTROL_SITES must be a JSON array");
    const names = new Set();
    for (const site of configured) {
      if (names.has(site.name)) {
        const expected = DEFAULT_SITE_ROOTS.find(({ name }) => name === site.name);
        throw new Error(
          `duplicate THEME_CONTROL_SITES site ${site.name}; ` +
          `expected checkout path ${expected?.expectedRoot || site.root || "<unknown>"}`,
        );
      }
      names.add(site.name);
    }
    assert.equal(
      configured.length,
      DEFAULT_SITE_ROOTS.length,
      "THEME_CONTROL_SITES must contain exactly the three reviewed sites",
    );
    assert.deepEqual(
      [...names].sort(),
      DEFAULT_SITE_ROOTS.map(({ name }) => name).sort(),
      "THEME_CONTROL_SITES must contain exactly OKH, Glee, and AskJamie",
    );
    for (const site of configured) {
      assert.match(
        site.revision || "",
        /^[0-9a-f]{40}$/,
        `${site.name || "configured site"} must provide an immutable full commit SHA`,
      );
    }
    return configured.map((site) => ({
      ...site,
      root: resolve(repositoryRoot, site.root),
    }));
  }

  const available = DEFAULT_SITE_ROOTS.filter((site) => site.root && directoryExists(site.root));
  if (available.length === 0) return [];
  if (available.length !== DEFAULT_SITE_ROOTS.length) {
    throw new Error(`Theme-control sync requires all three site checkouts; found ${available.map(({ name }) => name).join(", ")}`);
  }
  return available;
}

function directoryExists(path) {
  return existsSync(join(path, "index.html")) &&
    existsSync(join(path, "assets", "css", "theme.css")) &&
    existsSync(join(path, "assets", "js", "app.js"));
}

async function loadConfiguredSite(site) {
  let revision = site.revision || "unavailable";
  try {
    let markup;
    let cssBuffer;
    let scriptBuffer;
    if (site.revision) {
      const { stdout: resolvedRevision } = await execFileAsync(
        "git",
        ["-C", site.root, "rev-parse", "--verify", `${site.revision}^{commit}`],
      );
      if (resolvedRevision.trim() !== site.revision) {
        throw new Error(`reviewed revision resolved unexpectedly to ${resolvedRevision.trim()}`);
      }
      const readReviewedFile = async (path) => {
        const { stdout } = await execFileAsync(
          "git",
          ["-C", site.root, "show", `${site.revision}:${path}`],
          { encoding: "buffer", maxBuffer: 16 * 1024 * 1024 },
        );
        return stdout;
      };
      [markup, cssBuffer, scriptBuffer] = await Promise.all([
        readReviewedFile("index.html"),
        readReviewedFile("assets/css/theme.css"),
        readReviewedFile("assets/js/app.js"),
      ]);
      markup = markup.toString("utf8");
    } else {
      [markup, cssBuffer, scriptBuffer] = await Promise.all([
        readFile(join(site.root, "index.html"), "utf8"),
        readFile(join(site.root, "assets", "css", "theme.css")),
        readFile(join(site.root, "assets", "js", "app.js")),
      ]);
      const { stdout: actualRevision } = await execFileAsync("git", ["-C", site.root, "rev-parse", "HEAD"]);
      revision = actualRevision.trim();
    }
    return {
      ...site,
      markup,
      cssBuffer,
      scriptBuffer,
      revision,
      css: cssBuffer.toString("utf8"),
      script: scriptBuffer.toString("utf8"),
    };
  } catch (error) {
    throw new Error(`${site.name} foundation revision ${revision}: ${error.message}`, { cause: error });
  }
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

test("configured sites keep foundation bytes and run against actual markup hooks", async (t) => {
  const inputs = configuredSiteInputs();
  if (inputs.length === 0) {
    t.skip("no three-site checkout set; set THEME_CONTROL_SITES for the cross-site sync audit");
    return;
  }
  assert.equal(inputs.length, 3, "exactly OKH, Glee, and AskJamie must be configured");

  console.log(
    `Theme-control audit inputs: ${inputs.map(({ name, root, revision }) => (
      `${name}@${revision} (${root})`
    )).join(", ")}`,
  );
  const sites = await Promise.all(inputs.map(loadConfiguredSite));
  const byName = new Map(sites.map((site) => [site.name, site]));
  for (const expectedName of ["OKH", "Glee", "AskJamie"]) {
    assert.ok(byName.has(expectedName), `missing configured site ${expectedName}`);
  }

  for (const file of ["cssBuffer", "scriptBuffer"]) {
    const baseline = sites[0][file];
    const baselineHash = sha256(baseline);
    for (const site of sites.slice(1)) {
      assert.deepEqual(
        site[file],
        baseline,
        `${site.name} foundation drift at ${site.revision}: ${file} sha256 ${sha256(site[file])}, expected ${baselineHash}`,
      );
    }
  }

  for (const site of sites) {
    const expected = DEFAULT_SITE_ROOTS.find(({ name }) => name === site.name);
    assert.ok(expected, `unknown configured site ${site.name} at foundation revision ${site.revision}`);
    const page = await openFixture({
      markup: site.markup,
      css: site.css,
      script: site.script,
    });
    try {
      assert.equal(
        await page.locator("body").evaluate((body, expectedBodyClass) => (
          expectedBodyClass
            ? body.classList.contains(expectedBodyClass)
            : !body.classList.contains("glee-main") && !body.classList.contains("askjamie-main")
        ), expected.bodyClass),
        true,
        `${site.name} markup hook missing at foundation revision ${site.revision}`,
      );
      await assert.doesNotReject(
        () => page.locator(expected.selector).waitFor({ state: "attached", timeout: 2000 }),
        `${site.name} theme control missing at foundation revision ${site.revision}`,
      );
      const state = await readState(page, expected.selector);
      assert.equal(
        state.state,
        site.name === "OKH" ? "system" : "auto",
        `${site.name} theme baseline at foundation revision ${site.revision}`,
      );
    } finally {
      await page.close();
    }
  }
});
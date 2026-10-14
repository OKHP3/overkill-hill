import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { copyFile, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { dirname, extname, join, resolve, sep } from "node:path";
import { tmpdir } from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createHash } from "node:crypto";

const testsDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = join(testsDirectory, "..");
const appScript = await readFile(join(repositoryRoot, "assets", "js", "app.js"), "utf8");
const brandThemeContract = JSON.parse(
  await readFile(join(repositoryRoot, "config", "brand-theme-contract.json"), "utf8"),
);
const foundationSiteContract = JSON.parse(
  await readFile(join(repositoryRoot, "config", "theme-control-sites.json"), "utf8"),
).sites;
const execFileAsync = promisify(execFile);

const BRAND_EXPECTATIONS = brandThemeContract.brands;
assert.ok(Array.isArray(foundationSiteContract), "shared foundation site contract must be an array");
assert.equal(foundationSiteContract.length, 3, "shared foundation contract must contain exactly three reviewed sites");
const FOUNDATION_SITE_NAMES = foundationSiteContract.map(({ name }) => name);
assert.equal(
  new Set(FOUNDATION_SITE_NAMES).size,
  foundationSiteContract.length,
  "shared foundation contract must not contain duplicate site names",
);

let browser;

before(async () => {
  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  browser = await chromium.launch(launchOptions);
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

function brandThemeContractDrift(site, brandExpectations = BRAND_EXPECTATIONS) {
  const contractLabel = site.contractRevision
    ? `; contract revision ${site.contractRevision}`
    : "";
  const label = `${site.name} revision ${site.revision}${contractLabel}`;
  const beginMarker = "// BEGIN GENERATED BRAND THEME CONFIG. Do not edit this block.";
  const endMarker = "// END GENERATED BRAND THEME CONFIG.";
  const start = site.script.indexOf(beginMarker);
  const end = site.script.indexOf(endMarker, start);
  if (start < 0 || end < 0) {
    return [`${label}: generated brand theme block is missing or incomplete`];
  }

  const block = site.script.slice(start, end);
  const serialized = block.match(
    /const BRAND_THEME_CONFIG = Object\.freeze\(([\s\S]*?)\);/,
  )?.[1];
  if (!serialized) {
    return [`${label}: generated BRAND_THEME_CONFIG is missing or malformed`];
  }

  let actualBrands;
  try {
    actualBrands = JSON.parse(serialized);
  } catch (error) {
    return [`${label}: generated BRAND_THEME_CONFIG is not valid JSON (${error.message})`];
  }
  if (!actualBrands || typeof actualBrands !== "object" || Array.isArray(actualBrands)) {
    return [`${label}: generated BRAND_THEME_CONFIG is not an object`];
  }

  const drift = [];
  for (const [brandId, expected] of Object.entries(brandExpectations)) {
    const actual = actualBrands[brandId];
    if (!actual || typeof actual !== "object" || Array.isArray(actual)) {
      drift.push(`${label}: ${brandId} is missing or is not an object; expected ${JSON.stringify(expected)}`);
      continue;
    }
    for (const key of new Set([...Object.keys(expected), ...Object.keys(actual)])) {
      if (actual[key] !== expected[key]) {
        const actualValue = Object.hasOwn(actual, key) ? JSON.stringify(actual[key]) : "<missing>";
        const expectedValue = Object.hasOwn(expected, key) ? JSON.stringify(expected[key]) : "<not in contract>";
        drift.push(`${label}: ${brandId}.${key} is ${actualValue}; expected ${expectedValue}`);
      }
    }
  }
  for (const brandId of Object.keys(actualBrands)) {
    if (!Object.hasOwn(brandExpectations, brandId)) {
      drift.push(`${label}: unexpected generated brand ${brandId}=${JSON.stringify(actualBrands[brandId])}`);
    }
  }
  return drift;
}

async function loadReviewedBrandThemeContract(revision, repoRoot = repositoryRoot) {
  assert.match(
    revision || "",
    /^[0-9a-f]{40}$/,
    "THEME_CONTROL_CONTRACT_REVISION must be an immutable full commit SHA",
  );
  const { stdout: resolvedRevision } = await execFileAsync(
    "git",
    ["-C", repoRoot, "rev-parse", "--verify", `${revision}^{commit}`],
  );
  assert.equal(
    resolvedRevision.trim(),
    revision,
    "THEME_CONTROL_CONTRACT_REVISION must resolve to the exact reviewed commit",
  );
  const { stdout } = await execFileAsync(
    "git",
    ["-C", repoRoot, "show", `${revision}:config/brand-theme-contract.json`],
    { encoding: "utf8", maxBuffer: 1024 * 1024 },
  );
  const contract = JSON.parse(stdout);
  assert.ok(
    contract.brands && typeof contract.brands === "object" && !Array.isArray(contract.brands),
    `brand theme contract at ${revision} must contain a brands object`,
  );
  return contract;
}

test("reviewed brand contract loading ignores changes in the working tree", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "reviewed-brand-contract-"));
  try {
    await execFileAsync("git", ["init", "--quiet"], { cwd: temporary });
    await execFileAsync("git", ["config", "user.email", "theme-controls@example.test"], { cwd: temporary });
    await execFileAsync("git", ["config", "user.name", "Theme Controls Test"], { cwd: temporary });
    await mkdir(join(temporary, "config"));
    const reviewed = {
      brands: {
        glee: {
          name: "Glee",
          bodyClass: "glee-main",
          storageKey: "reviewed-storage-key",
          light: "#123456",
          dark: "#654321",
          colorScheme: "dark light",
        },
      },
    };
    const contractPath = join(temporary, "config", "brand-theme-contract.json");
    await writeFile(contractPath, JSON.stringify(reviewed));
    await execFileAsync("git", ["add", "config/brand-theme-contract.json"], { cwd: temporary });
    await execFileAsync("git", ["commit", "-m", "review contract"], { cwd: temporary });
    const { stdout: revision } = await execFileAsync("git", ["rev-parse", "HEAD"], { cwd: temporary });

    await writeFile(contractPath, JSON.stringify({ brands: { glee: { light: "#000000" } } }));
    assert.deepEqual(
      await loadReviewedBrandThemeContract(revision.trim(), temporary),
      reviewed,
    );
    await assert.rejects(
      () => loadReviewedBrandThemeContract("not-a-full-sha", temporary),
      /THEME_CONTROL_CONTRACT_REVISION must be an immutable full commit SHA/,
    );
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});

test("brand runtime audit names site, revision, and changed contract values", () => {
  assert.deepEqual(
    brandThemeContractDrift({
      name: "OKH",
      revision: "a".repeat(40),
      script: appScript,
    }),
    [],
  );

  const glee = BRAND_EXPECTATIONS.glee;
  const outdatedScript = appScript.replace(
    `"light": "${glee.light}"`,
    '"light": "#000000"',
  );
  const drift = brandThemeContractDrift({
    name: "Glee",
    revision: "b".repeat(40),
    script: outdatedScript,
  });
  assert.equal(drift.length, 1);
  assert.match(drift[0], /Glee revision b{40}: glee\.light is "#000000"; expected "#d35b2d"/);

  const contractRevision = "c".repeat(40);
  const pinnedDrift = brandThemeContractDrift({
    name: "Glee",
    revision: "b".repeat(40),
    contractRevision,
    script: outdatedScript,
  });
  assert.match(pinnedDrift[0], new RegExp(`Glee revision b{40}; contract revision ${contractRevision}`));
});

test("brand runtime audit reports missing and malformed generated blocks with site and immutable revision", () => {
  const siteName = "Glee";
  const revision = "d".repeat(40);
  const declarationPattern = /(const BRAND_THEME_CONFIG = Object\.freeze\()[\s\S]*?(\);)/;
  const declaration = appScript.match(declarationPattern);
  assert.ok(declaration, "fixture must contain a generated brand configuration");
  const originalBrands = JSON.parse(declaration[0].match(/\(([\s\S]*?)\);/)[1]);
  const scriptWithBrands = (brands) => appScript.replace(
    declarationPattern,
    `$1${JSON.stringify(brands)}$2`,
  );
  const missingBrand = { ...originalBrands };
  delete missingBrand.glee;
  const unexpectedBrand = {
    ...originalBrands,
    unreviewed: { name: "Unreviewed" },
  };
  const cases = [
    {
      name: "missing marker",
      script: appScript.replace(
        "// BEGIN GENERATED BRAND THEME CONFIG. Do not edit this block.",
        "",
      ),
      expectedDiagnostic: /generated brand theme block is missing or incomplete/,
    },
    {
      name: "invalid generated JSON",
      script: appScript.replace(
        declarationPattern,
        "$1{ invalid JSON }$2",
      ),
      expectedDiagnostic: /generated BRAND_THEME_CONFIG is not valid JSON/,
    },
    {
      name: "missing brand",
      script: scriptWithBrands(missingBrand),
      expectedDiagnostic: /glee is missing or is not an object/,
    },
    {
      name: "unexpected brand",
      script: scriptWithBrands(unexpectedBrand),
      expectedDiagnostic: /unexpected generated brand unreviewed/,
    },
  ];

  for (const testCase of cases) {
    const diagnostics = brandThemeContractDrift({
      name: siteName,
      revision,
      script: testCase.script,
    });
    assert.ok(diagnostics.length > 0, `${testCase.name} must produce a diagnostic`);
    assert.ok(
      diagnostics.some((diagnostic) => testCase.expectedDiagnostic.test(diagnostic)),
      `${testCase.name} diagnostic should describe the drift`,
    );
    for (const diagnostic of diagnostics) {
      assert.match(
        diagnostic,
        new RegExp(`${siteName} revision ${revision}`),
        `${testCase.name} diagnostic should name the site and immutable revision`,
      );
    }
  }
});

test("allowlisted Pages package retains brand runtime values and a matching app.js fingerprint", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "brand-theme-release-"));
  const source = join(temporary, "source");
  const output = join(temporary, "release");

  async function writeSource(relativePath, contents) {
    const target = join(source, relativePath);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, contents);
  }

  try {
    await writeSource(
      "site-src/pages.json",
      JSON.stringify({ pages: [{ path: "index.html" }, { path: "about/index.html" }] }),
    );
    await writeSource(
      "sitemap.xml",
      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://overkillhill.com/</loc></url><url><loc>https://overkillhill.com/about/</loc></url></urlset>',
    );
    await writeSource(
      "config/murderbird-source-archive.json",
      JSON.stringify({
        schema: 1,
        excludedLibraryPngs: ["assets/img/library/archive.png"],
      }),
    );
    for (const [path, contents] of Object.entries({
      ".nojekyll": "",
      "CNAME": "overkillhill.com\n",
      "feed.xml": "<feed />\n",
      "favicon.ico": "",
      "favicon.svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" />\n",
      "humans.txt": "Fixture\n",
      "llms.txt": "Fixture\n",
      "robots.txt": "User-agent: *\n",
      "site.webmanifest": "{}\n",
      "assets/data/search-index.json": "{}\n",
    })) {
      await writeSource(path, contents);
    }
    await writeSource("index.html", await readFile(join(repositoryRoot, "index.html")));
    const sourceApp = await readFile(join(repositoryRoot, "assets", "js", "app.js"), "utf8");
    const sourceFingerprint = createHash("sha256")
      .update(sourceApp.replace(/\r\n/g, "\n"))
      .digest("hex")
      .slice(0, 8);
    await writeSource(
      "about/index.html",
      `<html><body><script src="/assets/js/app.js?v=${sourceFingerprint}"></script></body></html>`,
    );
    await mkdir(join(source, "assets", "js"), { recursive: true });
    await copyFile(
      join(repositoryRoot, "assets", "js", "app.js"),
      join(source, "assets", "js", "app.js"),
    );

    await execFileAsync(
      "python3",
      [
        "scripts/build-release.py",
        "--source",
        source,
        "--output",
        output,
        "--commit",
        "a".repeat(40),
      ],
      { cwd: repositoryRoot },
    );

    const packagedApp = await readFile(join(output, "assets", "js", "app.js"), "utf8");
    const beginMarker = "// BEGIN GENERATED BRAND THEME CONFIG. Do not edit this block.";
    const endMarker = "// END GENERATED BRAND THEME CONFIG.";
    const start = packagedApp.indexOf(beginMarker);
    const end = packagedApp.indexOf(endMarker, start);
    assert.notEqual(start, -1, "packaged app.js has the generated theme block start marker");
    assert.notEqual(end, -1, "packaged app.js has the generated theme block end marker");
    const block = packagedApp.slice(start, end);
    const serialized = block.match(
      /const BRAND_THEME_CONFIG = Object\.freeze\(([\s\S]*?)\);/,
    )?.[1];
    assert.ok(serialized, "packaged app.js contains a parseable generated brand config");
    const packagedBrands = JSON.parse(serialized);
    for (const [brandId, expected] of Object.entries(BRAND_EXPECTATIONS)) {
      assert.equal(packagedBrands[brandId]?.storageKey, expected.storageKey, `${brandId} storage key`);
      assert.equal(packagedBrands[brandId]?.light, expected.light, `${brandId} light color`);
      assert.equal(packagedBrands[brandId]?.dark, expected.dark, `${brandId} dark color`);
    }

    const expectedFingerprint = createHash("sha256")
      .update(packagedApp.replace(/\r\n/g, "\n"))
      .digest("hex")
      .slice(0, 8);
    const packagedHtmlPaths = (await readdir(output, { recursive: true }))
      .filter((path) => path.endsWith(".html"))
      .map((path) => path.replaceAll("\\", "/"))
      .sort();
    const pagesWithAppReferences = [];
    for (const path of packagedHtmlPaths) {
      const html = await readFile(join(output, path), "utf8");
      const appReferences = [
        ...html.matchAll(/\b(?:src|href)=["']\/assets\/js\/app\.js(?:\?([^"']*))?["']/g),
      ];
      if (appReferences.length === 0) continue;
      pagesWithAppReferences.push(path);
      for (const appReference of appReferences) {
        const fingerprint = appReference[1]?.match(/(?:^|&)v=([a-f0-9]{8})(?:&|$)/)?.[1];
        assert.equal(
          fingerprint,
          expectedFingerprint,
          `${path} app.js fingerprint matches packaged app.js bytes`,
        );
      }
    }
    assert.ok(
      pagesWithAppReferences.includes("index.html"),
      "a packaged published page references fingerprinted app.js",
    );
    assert.ok(
      pagesWithAppReferences.includes("about/index.html"),
      "the package regression covers more than the homepage",
    );
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
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

const DEFAULT_SITE_ROOTS = foundationSiteContract.map((site) => ({
  ...site,
  expectedRoot: site.checkoutPath,
  root: resolve(repositoryRoot, site.localPath),
}));

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
          `expected checkout path ${expected?.checkoutPath || site.root || "<unknown>"}`,
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
      `THEME_CONTROL_SITES must contain exactly ${FOUNDATION_SITE_NAMES.join(", ")}`,
    );
    for (const site of configured) {
      const expected = DEFAULT_SITE_ROOTS.find(({ name }) => name === site.name);
      assert.equal(
        site.root,
        expected?.checkoutPath,
        `${site.name || "configured site"} expected checkout path ${expected?.checkoutPath || "<unknown>"}`,
      );
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

test("configured foundation paths match the shared site contract", () => {
  const previous = process.env.THEME_CONTROL_SITES;
  const configured = foundationSiteContract.map((site) => ({
    name: site.name,
    root: site.checkoutPath,
    revision: "a".repeat(40),
  }));
  try {
    process.env.THEME_CONTROL_SITES = JSON.stringify(configured);
    assert.equal(configuredSiteInputs().length, 3);

    const drifted = configured.map((site) => (
      site.name === "Glee" ? { ...site, root: ".ci/theme-sites/wrong-glee-path" } : site
    ));
    process.env.THEME_CONTROL_SITES = JSON.stringify(drifted);
    assert.throws(
      () => configuredSiteInputs(),
      /Glee expected checkout path \.ci\/theme-sites\/glee-fullytools/,
    );
  } finally {
    if (previous === undefined) delete process.env.THEME_CONTROL_SITES;
    else process.env.THEME_CONTROL_SITES = previous;
  }
});

test("duplicate configured sites retain the expected checkout-path diagnostic", () => {
  const previous = process.env.THEME_CONTROL_SITES;
  const configured = foundationSiteContract.map((site) => ({
    name: site.name,
    root: site.checkoutPath,
    revision: "a".repeat(40),
  }));
  try {
    process.env.THEME_CONTROL_SITES = JSON.stringify([...configured, { ...configured[1] }]);
    assert.throws(
      () => configuredSiteInputs(),
      /duplicate THEME_CONTROL_SITES site Glee; expected checkout path \.ci\/theme-sites\/glee-fullytools/,
    );
  } finally {
    if (previous === undefined) delete process.env.THEME_CONTROL_SITES;
    else process.env.THEME_CONTROL_SITES = previous;
  }
});

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
  const contractRevision = process.env.THEME_CONTROL_CONTRACT_REVISION;
  const reviewedContract = await loadReviewedBrandThemeContract(contractRevision);

  console.log(
    `Theme-control audit inputs: ${inputs.map(({ name, root, revision }) => (
      `${name}@${revision} (contract@${contractRevision}; ${root})`
    )).join(", ")}`,
  );
  const sites = await Promise.all(inputs.map(async (site) => ({
    ...await loadConfiguredSite(site),
    contractRevision,
  })));
  const byName = new Map(sites.map((site) => [site.name, site]));
  for (const expectedName of FOUNDATION_SITE_NAMES) {
    assert.ok(byName.has(expectedName), `missing configured site ${expectedName}`);
  }

  // Accepted historical pins predate the generated runtime marker. Their
  // byte equality and browser behavior remain checked below; the current
  // generated runtime contract is checked independently above.

  for (const file of ["cssBuffer", "scriptBuffer"]) {
    const baseline = sites[0][file];
    const baselineHash = sha256(baseline);
    for (const site of sites.slice(1)) {
      assert.deepEqual(
        site[file],
        baseline,
        `${site.name} foundation drift at ${site.revision} (contract ${contractRevision}): ${file} sha256 ${sha256(site[file])}, expected ${baselineHash}`,
      );
    }
  }

  for (const site of sites) {
    const expected = DEFAULT_SITE_ROOTS.find(({ name }) => name === site.name);
    assert.ok(expected, `unknown configured site ${site.name} at foundation revision ${site.revision} (contract ${contractRevision})`);
    // Retained release pins predate generated brand blocks. Check those
    // immutable runtimes through their actual controls; do not advance pins
    // merely to satisfy a newer serialization format.
    if (site.script.includes("// BEGIN GENERATED BRAND THEME CONFIG.")) {
      assert.deepEqual(
        brandThemeContractDrift(site, reviewedContract.brands),
        [],
        `${site.name} brand runtime drift at site revision ${site.revision} (contract ${contractRevision})`,
      );
    }
    for (const brand of Object.values(reviewedContract.brands)) {
      const brandPage = await openFixture({
        bodyClass: brand.bodyClass,
        storage: { [brand.storageKey]: "dark" },
        script: site.script,
      });
      const context = `${site.name}@${site.revision}, ${brand.name}, contract@${contractRevision}`;
      try {
        const dark = await readState(brandPage, ".glee-color-toggle");
        assert.equal(dark.state, "dark", `${context}: reviewed storage key restores dark`);
        assert.equal(dark.colorScheme, "dark", `${context}: dark scheme`);
        assert.ok(dark.colors.length > 0, `${context}: theme metadata exists`);
        assert.ok(dark.colors.every(({ content }) => content === brand.dark), `${context}: dark color`);
        const auto = await clickAndRead(brandPage, ".glee-color-toggle");
        assert.equal(auto.state, "auto", `${context}: auto transition`);
        assert.deepEqual(auto.colors.map(({ content }) => content), [brand.light, brand.dark], `${context}: automatic colors`);
        const light = await clickAndRead(brandPage, ".glee-color-toggle");
        assert.equal(light.colorScheme, "light", `${context}: light scheme`);
        assert.ok(light.colors.every(({ content }) => content === brand.light), `${context}: light color`);
        assert.equal(await brandPage.evaluate((key) => localStorage.getItem(key), brand.storageKey), "light", `${context}: reviewed storage key persists light`);
      } finally {
        await brandPage.close();
      }
    }
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
        `${site.name} markup hook missing at foundation revision ${site.revision} (contract ${contractRevision})`,
      );
      await assert.doesNotReject(
        () => page.locator(expected.selector).waitFor({ state: "attached", timeout: 2000 }),
        `${site.name} theme control missing at foundation revision ${site.revision} (contract ${contractRevision})`,
      );
      const state = await readState(page, expected.selector);
      assert.equal(
        state.state,
        site.name === "OKH" ? "system" : "auto",
        `${site.name} theme baseline at foundation revision ${site.revision} (contract ${contractRevision})`,
      );
    } finally {
      await page.close();
    }
  }
});

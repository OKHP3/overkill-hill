#!/usr/bin/env node
/**
 * Route-wide browser check for the enforcing Content Security Policy.
 *
 * Every functional route in the release inventory is loaded in a real browser. Cross-origin
 * requests are intentionally aborted so the result does not depend on CDN,
 * analytics, font, or embedded-app availability. Chromium still evaluates
 * the page's CSP before a request reaches the route handler, so an
 * unexpected CSP diagnostic remains a hard failure.
 *
 * The check fails on:
 *   - CSP violations reported by the browser console
 *   - page-level JavaScript errors
 *   - failed local requests or local HTTP error responses
 *   - Mermaid render warnings or diagrams left without an SVG
 *
 * Usage:
 *   npm run test:csp
 *   node scripts/csp-qa.mjs --base-url=http://127.0.0.1:5000
 *   node scripts/csp-qa.mjs --base-url=http://127.0.0.1:5000 --paths=/fixture.html
 *   node scripts/csp-qa.mjs --base-url=http://127.0.0.1:5000 --paths=/fixture.html --report=fixture.json
 *   node scripts/csp-qa.mjs --external-health --base-url=https://overkillhill.com
 *   node scripts/csp-qa.mjs --external-health --report=third-party-report.json
 *   node scripts/csp-qa.mjs --external-health --external-budget-ms=120000
 *   node scripts/csp-qa.mjs --external-health --browser=firefox
 *   External-health browser choices: chromium (default), firefox, or webkit.
 *   node scripts/csp-qa.mjs --fixture-summary=fixture-results.json
 */

import { loadFunctionalPaths } from './release-qa-inventory.mjs';
import { chromium, firefox, webkit } from "playwright";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";

const DEFAULT_BASE_URL = "http://127.0.0.1:5000";
const baseArg = process.argv.find((arg) => arg.startsWith("--base-url="));
const baseUrl = (baseArg ? baseArg.slice("--base-url=".length) : DEFAULT_BASE_URL)
  .replace(/\/$/, "");
const baseOrigin = new URL(baseUrl).origin;
const pathsArg = process.argv.find((arg) => arg.startsWith("--paths="));
const reportArg = process.argv.find((arg) => arg.startsWith("--report="));
const fixtureSummaryArg = process.argv.find((arg) => arg.startsWith("--fixture-summary="));
const summaryArg = process.argv.find((arg) => arg.startsWith("--summary="));
const artifactUrlArg = process.argv.find((arg) => arg.startsWith("--artifact-url="));
const externalBudgetArg = process.argv.find((arg) => arg.startsWith("--external-budget-ms="));
const externalHealthMode =
  process.argv.includes("--external-health") || process.argv.includes("--check-external");
const browserArguments = process.argv.filter(
  (arg) => arg === "--browser" || arg.startsWith("--browser="),
);

if (browserArguments.length > 1) {
  throw new Error("--browser may be specified only once");
}
if (browserArguments[0] === "--browser") {
  throw new Error("--browser requires a value: chromium, firefox, or webkit");
}

const browserName = browserArguments.length
  ? browserArguments[0].slice("--browser=".length)
  : "chromium";
const browserTypes = { chromium, firefox, webkit };
if (!Object.hasOwn(browserTypes, browserName)) {
  throw new Error(
    `Invalid --browser=${browserName}. Choose chromium, firefox, or webkit.`,
  );
}
if (browserName !== "chromium" && !externalHealthMode) {
  throw new Error(`--browser=${browserName} is only supported with --external-health.`);
}
const externalHealthBrowserType = browserTypes[browserName];

if (reportArg && !externalHealthMode && !pathsArg) {
  throw new Error("--report requires --external-health or --paths");
}

function loadPublicPaths() {
  if (pathsArg) {
    const paths = pathsArg.slice("--paths=".length)
      .split(",")
      .map((path) => path.trim())
      .filter(Boolean);
    if (!paths.length) throw new Error("--paths must contain at least one route");
    return [...new Set(paths.map((path) => {
      const url = new URL(path, baseUrl);
      if (url.origin !== baseOrigin || !path.startsWith("/") || url.search || url.hash) {
        throw new Error(`Invalid --paths route: ${path}`);
      }
      return url.pathname || "/";
    }))];
  }

  return loadFunctionalPaths();
}

const PUBLIC_PATHS = fixtureSummaryArg ? [] : loadPublicPaths();
const CSP_DIAGNOSTIC = /content security policy|violates the following.*policy|refused to .* policy/i;
const MERMAID_RENDER_ERROR = /^\[mermaid-init\] render error/i;
const INTENTIONAL_EXTERNAL_FAILURE = "Failed to load resource: net::ERR_FAILED";
const EXTERNAL_SETTLE_TIMEOUT_MS = 5000;
const EXTERNAL_QUIET_WINDOW_MS = 250;
const DEFAULT_EXTERNAL_HEALTH_BUDGET_MS = 120000;

function parsePositiveIntegerArgument(argument, name, defaultValue) {
  if (!argument) return defaultValue;
  const value = Number(argument.slice(`--${name}=`.length));
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`--${name} must be a positive integer number of milliseconds`);
  }
  return value;
}

const externalHealthBudgetMs = parsePositiveIntegerArgument(
  externalBudgetArg,
  "external-budget-ms",
  DEFAULT_EXTERNAL_HEALTH_BUDGET_MS,
);

function isHttpUrl(value) {
  return value.protocol === "http:" || value.protocol === "https:";
}

function isLocalUrl(value) {
  try {
    return new URL(value).origin === baseOrigin;
  } catch {
    return false;
  }
}

function formatConsoleMessage(message) {
  const location = message.location?.url ? ` (${message.location.url})` : "";
  return `${message.type.toUpperCase()}: ${message.text}${location}`;
}

function normalizeHttpUrl(value) {
  try {
    const url = new URL(value);
    if (!isHttpUrl(url)) return null;
    url.search = "";
    url.hash = "";
    return url.href;
  } catch {
    return null;
  }
}

function classifyExternalDependency(dependency) {
  const hasHttpError = dependency.responses.some(({ status }) => status >= 400);
  const cspEvidence = dependency.cspEvidence || [];
  const cspBlocked = cspEvidence.length > 0;
  const hasNonCspFailure = dependency.failures.some(
    (failure) => !cspEvidence.some(
      (evidence) => evidence.route === failure.route &&
        evidence.blockedURI === dependency.url,
    ),
  );

  if (hasHttpError || hasNonCspFailure) return "unavailable";
  if (cspBlocked) return "blocked-by-csp";
  if (dependency.responses.length) return "available";
  return "no-response";
}

function reportPathFromArgument(argument, name) {
  const path = argument?.slice(`--${name}=`.length);
  if (!path) throw new Error(`--${name} must contain a file path`);
  return path;
}

function writeFocusedReport(results) {
  if (!reportArg) return;
  const reportPath = reportPathFromArgument(reportArg, "report");
  const failures = results.filter((result) => !result.pass);
  writeFileSync(reportPath, `${JSON.stringify({
    version: 1,
    mode: "focused",
    baseUrl,
    routes: PUBLIC_PATHS,
    results,
    summary: {
      routes: results.length,
      failures: failures.length,
    },
  }, null, 2)}\n`);
}

function markdownCell(value) {
  return String(value ?? "")
    .replaceAll("|", "\\|")
    .replaceAll("\r", " ")
    .replaceAll("\n", " ");
}

const DIAGNOSTIC_CATEGORY = /^(CSP|PAGEERROR|CONSOLE|LOCAL REQUEST FAILED|LOCAL HTTP ERROR|MERMAID):/;

function fixtureDiagnostics(errors) {
  const categories = new Set();
  const evidence = [];
  for (const error of errors) {
    const text = String(error).replace(/^\s*→\s*/, "");
    const category = text.match(DIAGNOSTIC_CATEGORY)?.[1];
    if (category) categories.add(category);
    evidence.push(text);
  }
  return {
    categories: [...categories].join(", ") || "none observed",
    evidence: evidence.join(" / ") || "No browser diagnostic was captured.",
  };
}

function writeFixtureSummary(reportPath) {
  let report;
  try {
    report = JSON.parse(readFileSync(reportPath, "utf8"));
  } catch (error) {
    report = {
      mode: "csp-fixtures",
      fixtures: [],
      error: `Could not read focused CSP fixture report: ${error.message}`,
    };
  }

  const fixtures = Array.isArray(report.fixtures) ? report.fixtures : [];
  const lines = [
    "## CSP fixture diagnostics",
    "",
    "Focused CSP fixture regressions failed. The full browser output remains in the check log.",
    "",
    "| Fixture | Diagnostic categories | Key browser diagnostic |",
    "| --- | --- | --- |",
  ];
  if (fixtures.length) {
    for (const fixture of fixtures) {
      const diagnostics = fixtureDiagnostics(
        Array.isArray(fixture.errors) ? fixture.errors : [],
      );
      lines.push(
        `| ${markdownCell(fixture.path)} | ${markdownCell(diagnostics.categories)} | ` +
        `${markdownCell(diagnostics.evidence)} |`,
      );
    }
  } else {
    lines.push(
      `| unavailable | unknown | ${markdownCell(report.error || "No fixture results were recorded.")} |`,
    );
  }
  lines.push("");
  const artifactUrl = artifactUrlArg?.slice("--artifact-url=".length);
  if (artifactUrl) {
    lines.push(
      `Focused CSP evidence artifact: [csp-fixture-report.json](${markdownCell(artifactUrl)})`,
    );
  } else {
    lines.push(
      "Focused CSP evidence artifact: unavailable; check the upload step for a warning or missing report.",
    );
  }
  lines.push("");

  const rendered = `${lines.join("\n")}\n`;
  const summaryPath = summaryArg
    ? reportPathFromArgument(summaryArg, "summary")
    : process.env.GITHUB_STEP_SUMMARY;
  if (summaryPath) appendFileSync(summaryPath, rendered);
  console.log(rendered);
}

async function checkRoute(browser, path) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const blockedExternal = new Set();
  const consoleMessages = [];
  const pageErrors = [];
  const failedLocalRequests = [];
  const localHttpErrors = [];

  await page.route("**/*", async (route) => {
    const requestUrl = new URL(route.request().url());
    if (isHttpUrl(requestUrl) && requestUrl.origin !== baseOrigin) {
      blockedExternal.add(requestUrl.origin);
      await route.abort();
      return;
    }
    await route.continue();
  });

  page.on("console", (message) => {
    consoleMessages.push({
      type: message.type(),
      text: message.text(),
      location: message.location(),
    });
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.stack || error.message);
  });
  page.on("requestfailed", (request) => {
    if (isLocalUrl(request.url())) {
      failedLocalRequests.push(
        `${request.url()} (${request.failure()?.errorText || "unknown failure"})`,
      );
    }
  });
  page.on("response", (response) => {
    if (isLocalUrl(response.url()) && response.status() >= 400) {
      localHttpErrors.push(`${response.status()} ${response.url()}`);
    }
  });

  const errors = [];
  let response;
  try {
    response = await page.goto(`${baseUrl}${path}`, {
      waitUntil: "commit",
      timeout: 30000,
    });
    if (!response) {
      errors.push("navigation returned no response");
    } else if (response.status() >= 400) {
      errors.push(`navigation returned HTTP ${response.status()}`);
    }
    try {
      await page.waitForLoadState("domcontentloaded", { timeout: 5000 });
    } catch {
      errors.push("DOMContentLoaded was not observed within 5s");
    }
    await page.waitForTimeout(250);
  } catch (error) {
    errors.push(`navigation failed: ${error.message.split("\n")[0]}`);
  }

  let diagramCount = 0;
  if (!errors.length) {
    diagramCount = await page.locator(".mermaid").count();
    for (let index = 0; index < diagramCount; index += 1) {
      await page.locator(".mermaid").nth(index).scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
    }
    await page.waitForTimeout(500);
  }

  const diagramState = await page.evaluate(() => {
    const diagrams = [...document.querySelectorAll(".mermaid")];
    return {
      expected: diagrams.length,
      rendered: diagrams.filter((diagram) => diagram.querySelector("svg")).length,
      unrendered: diagrams
        .map((diagram, index) => ({ diagram, index }))
        .filter(({ diagram }) => !diagram.querySelector("svg"))
        .map(({ index }) => index + 1),
    };
  }).catch(() => ({ expected: diagramCount, rendered: 0, unrendered: [] }));

  const cspViolations = consoleMessages.filter(
    ({ text }) => CSP_DIAGNOSTIC.test(text),
  );
  const mermaidErrors = consoleMessages.filter(
    ({ type, text }) => (type === "warning" || type === "error") && MERMAID_RENDER_ERROR.test(text),
  );
  // A route-aborted cross-origin resource produces this generic browser
  // message. It is expected only because external availability is deliberately
  // removed from this gate; all specific diagnostics, including CSP messages,
  // stay unsuppressed.
  const unexpectedConsoleErrors = consoleMessages.filter(
    ({ type, text }) => type === "error" && text !== INTENTIONAL_EXTERNAL_FAILURE,
  );

  errors.push(
    ...cspViolations.map((message) => `CSP: ${formatConsoleMessage(message)}`),
    ...pageErrors.map((message) => `PAGEERROR: ${message}`),
    ...unexpectedConsoleErrors
      .filter(({ text }) => !cspViolations.some((message) => message.text === text))
      .map((message) => `CONSOLE: ${formatConsoleMessage(message)}`),
    ...failedLocalRequests.map((request) => `LOCAL REQUEST FAILED: ${request}`),
    ...localHttpErrors.map((responseError) => `LOCAL HTTP ERROR: ${responseError}`),
    ...mermaidErrors.map((message) => `MERMAID: ${formatConsoleMessage(message)}`),
  );
  if (diagramState.expected !== diagramState.rendered) {
    errors.push(
      `MERMAID: rendered ${diagramState.rendered}/${diagramState.expected} diagrams` +
      (diagramState.unrendered.length
        ? ` (missing ${diagramState.unrendered.map((index) => `#${index}`).join(", ")})`
        : ""),
    );
  }

  await page.close();
  return {
    path,
    pass: errors.length === 0,
    errors,
    diagrams: diagramState,
    blockedExternal: [...blockedExternal].sort(),
  };
}

function getExternalDependency(dependencies, request) {
  return getExternalDependencyForUrl(dependencies, request.url());
}

function getExternalDependencyForUrl(dependencies, value) {
  const requestUrl = new URL(value);
  if (!isHttpUrl(requestUrl) || requestUrl.origin === baseOrigin) return null;

  // Query strings often contain per-visit analytics identifiers. They are
  // irrelevant to endpoint availability, so keep the inventory stable and
  // avoid copying those values into CI logs or uploaded reports.
  requestUrl.search = "";
  requestUrl.hash = "";
  const key = requestUrl.href;
  if (!dependencies.has(key)) {
    dependencies.set(key, {
      url: key,
      origin: requestUrl.origin,
      routes: new Set(),
      resourceTypes: new Set(),
      requestCount: 0,
      responses: [],
      failures: [],
      timeouts: [],
      cspEvidence: [],
    });
  }
  const dependency = dependencies.get(key);
  return dependency;
}

function serialiseExternalDependency(dependency, cspEvidence) {
  const dependencyCspEvidence = cspEvidence.filter(
    ({ blockedURI }) => blockedURI === dependency.url,
  );
  const routeOutcomes = [...dependency.routes]
    .filter(Boolean)
    .sort()
    .map((route) => {
      const routeCspEvidence = dependencyCspEvidence.filter(
        (evidence) => evidence.route === route,
      );
      const routeFailures = dependency.failures.filter(
        (failure) => failure.route === route,
      );
      const routeTimeouts = dependency.timeouts.filter(
        (timeout) => timeout.route === route,
      );
      return {
        route,
        state: classifyExternalDependency({
          ...dependency,
          failures: routeFailures,
          cspEvidence: routeCspEvidence,
        }),
        cspBlocked: routeCspEvidence.length > 0,
        responses: dependency.responses,
        failures: routeFailures,
        timeouts: routeTimeouts,
        cspEvidence: routeCspEvidence,
      };
    });
  return {
    url: dependency.url,
    origin: dependency.origin,
    routes: [...dependency.routes].filter(Boolean).sort(),
    routeOutcomes,
    resourceTypes: [...dependency.resourceTypes].sort(),
    requestCount: dependency.requestCount,
    responses: dependency.responses,
    failures: dependency.failures,
    timeouts: dependency.timeouts,
    cspEvidence: dependencyCspEvidence,
    cspBlocked: dependencyCspEvidence.length > 0,
    state: classifyExternalDependency({
      ...dependency,
      cspEvidence: dependencyCspEvidence,
    }),
  };
}

function groupFailureRecords(failures, publicRoutes = null) {
  const grouped = new Map();
  for (const failure of failures) {
    const route = failure.route || "";
    const errorText = failure.errorText || "unknown failure";
    if (publicRoutes && !publicRoutes.has(route)) {
      throw new Error(
        `External failure route must match a checked public route: ${route || "(missing)"}`,
      );
    }
    if (typeof errorText !== "string" || !errorText.trim()) {
      throw new Error("External failure must include non-empty error text");
    }
    const key = JSON.stringify([route, errorText]);
    const existing = grouped.get(key);
    if (existing) {
      existing.count += failure.count || 1;
    } else {
      grouped.set(key, { route, errorText, count: failure.count || 1 });
    }
  }
  return [...grouped.values()];
}

async function waitForExternalRequestsToSettle(page, pendingRequests, overallDeadline) {
  const settleDeadline = Date.now() + EXTERNAL_SETTLE_TIMEOUT_MS;
  let quietSince = null;
  while (Date.now() < settleDeadline && Date.now() < overallDeadline) {
    if (pendingRequests.size) {
      quietSince = null;
    } else if (quietSince === null) {
      quietSince = Date.now();
    } else if (Date.now() - quietSince >= EXTERNAL_QUIET_WINDOW_MS) {
      return {
        requestsTimedOut: false,
        budgetExceeded: false,
      };
    }
    const remainingMs = Math.min(
      50,
      settleDeadline - Date.now(),
      overallDeadline - Date.now(),
    );
    if (remainingMs > 0) await page.waitForTimeout(remainingMs);
  }
  return {
    requestsTimedOut: pendingRequests.size > 0,
    budgetExceeded: Date.now() >= overallDeadline,
  };
}

async function checkExternalRoute(browser, path, overallDeadline) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const dependencies = new Map();
  const pendingExternalRequests = new Set();
  const cspDiagnostics = [];
  const localErrors = new Set();
  let budgetExceeded = false;

  // The DOM event exposes structured CSP evidence independently of
  // browser-specific request failure text.
  await page.addInitScript(() => {
    window.__cspViolationEvidence = [];
    document.addEventListener("securitypolicyviolation", (event) => {
      window.__cspViolationEvidence.push({
        blockedURI: event.blockedURI,
        effectiveDirective: event.effectiveDirective,
        violatedDirective: event.violatedDirective,
        disposition: event.disposition,
        documentURI: event.documentURI,
        sourceFile: event.sourceFile,
        lineNumber: event.lineNumber,
        columnNumber: event.columnNumber,
        statusCode: event.statusCode,
      });
    }, true);
  });

  page.on("console", (message) => {
    if (CSP_DIAGNOSTIC.test(message.text())) {
      cspDiagnostics.push(formatConsoleMessage({
        type: message.type(),
        text: message.text(),
        location: message.location(),
      }));
    }
  });
  page.on("request", (request) => {
    const dependency = getExternalDependency(dependencies, request);
    if (dependency) {
      pendingExternalRequests.add(request);
      dependency.requestCount += 1;
      dependency.resourceTypes.add(request.resourceType());
      dependency.routes.add(path);
    }
  });
  page.on("requestfailed", (request) => {
    const dependency = getExternalDependency(dependencies, request);
    if (dependency) {
      pendingExternalRequests.delete(request);
      dependency.failures.push({
        route: path,
        errorText: request.failure()?.errorText || "unknown failure",
      });
    } else if (isLocalUrl(request.url())) {
      localErrors.add(
        `local request failed: ${request.url()} ` +
        `(${request.failure()?.errorText || "unknown failure"})`,
      );
    }
  });
  page.on("response", (response) => {
    const request = response.request();
    const dependency = getExternalDependency(dependencies, request);
    if (dependency) {
      pendingExternalRequests.delete(request);
      dependency.responses.push({
        status: response.status(),
        statusText: response.statusText(),
      });
    } else if (isLocalUrl(response.url()) && response.status() >= 400) {
      localErrors.add(`local HTTP error: ${response.status()} ${response.url()}`);
    }
  });

  try {
    const navigationTimeout = Math.min(30000, overallDeadline - Date.now());
    if (navigationTimeout <= 0) {
      budgetExceeded = true;
    } else {
      const response = await page.goto(`${baseUrl}${path}`, {
        waitUntil: "commit",
        timeout: navigationTimeout,
      });
      if (!response) {
        localErrors.add("navigation returned no response");
      } else if (response.status() >= 400) {
        localErrors.add(`navigation returned HTTP ${response.status()}`);
      }
    }
    if (!budgetExceeded) {
      const loadStateTimeout = Math.min(5000, overallDeadline - Date.now());
      if (loadStateTimeout <= 0) {
        budgetExceeded = true;
      } else {
        try {
          await page.waitForLoadState("domcontentloaded", { timeout: loadStateTimeout });
        } catch {
          if (Date.now() >= overallDeadline) {
            budgetExceeded = true;
          } else {
            localErrors.add("DOMContentLoaded was not observed within 5s");
          }
        }
      }
    }
    if (!budgetExceeded) {
      // Give deferred analytics, fonts, embeds, and images a short, bounded
      // window to make their requests without making monitoring hang on them.
      const deferredWaitMs = Math.min(1000, overallDeadline - Date.now());
      if (deferredWaitMs <= 0) {
        budgetExceeded = true;
      } else {
        await page.waitForTimeout(deferredWaitMs);
        budgetExceeded = Date.now() >= overallDeadline;
      }
    }
  } catch (error) {
    if (Date.now() >= overallDeadline) {
      budgetExceeded = true;
    } else {
      localErrors.add(`navigation failed: ${error.message.split("\n")[0]}`);
    }
  }

  // Wait for terminal response/failure events instead of closing after a fixed
  // sleep. The quiet window catches deferred requests without allowing a
  // hanging third-party request to hold the health check forever.
  const settleResult = await waitForExternalRequestsToSettle(
    page,
    pendingExternalRequests,
    overallDeadline,
  );
  budgetExceeded = budgetExceeded || settleResult.budgetExceeded;
  if (settleResult.requestsTimedOut) {
    for (const request of pendingExternalRequests) {
      const dependency = getExternalDependency(dependencies, request);
      if (!dependency || dependency.timeouts.some(({ route }) => route === path)) continue;
      dependency.timeouts.push({
        route: path,
        url: dependency.url,
      });
    }
  }
  const cspEvidence = await page.evaluate(() => (
    Array.isArray(window.__cspViolationEvidence)
      ? window.__cspViolationEvidence
      : []
  )).catch(() => []);
  const externalCspEvidence = cspEvidence
    .map((evidence) => ({
      route: path,
      blockedURI: normalizeHttpUrl(evidence.blockedURI),
      effectiveDirective: evidence.effectiveDirective || "",
      violatedDirective: evidence.violatedDirective || "",
      disposition: evidence.disposition || "",
      documentURI: evidence.documentURI || "",
      sourceFile: evidence.sourceFile || "",
      lineNumber: evidence.lineNumber || 0,
      columnNumber: evidence.columnNumber || 0,
      statusCode: evidence.statusCode || 0,
    }))
    .filter(({ blockedURI }) => blockedURI);
  // Firefox and WebKit can enforce CSP before emitting a request event.
  // Retain that dependency from structured evidence without inventing a
  // request count, resource type, response, or browser failure.
  for (const { blockedURI } of externalCspEvidence) {
    const dependency = getExternalDependencyForUrl(dependencies, blockedURI);
    if (dependency) dependency.routes.add(path);
  }
  await page.close();
  return {
    path,
    budgetExceeded,
    dependencies: [...dependencies.values()]
      .map((dependency) => serialiseExternalDependency(dependency, externalCspEvidence)),
    cspDiagnostics,
    cspEvidence: externalCspEvidence,
    localErrors: [...localErrors],
  };
}

function mergeExternalDependencies(results) {
  const merged = new Map();
  const publicRoutes = new Set(results.map(({ path }) => path));
  for (const result of results) {
    for (const dependency of result.dependencies) {
      if (!merged.has(dependency.url)) {
        merged.set(dependency.url, {
          ...dependency,
          requestCount: 0,
          routes: [],
          routeOutcomes: [],
          resourceTypes: [],
          responses: [],
          failures: [],
          timeouts: [],
          cspEvidence: [],
          cspBlocked: false,
        });
      }
      const existing = merged.get(dependency.url);
      existing.routes = [...new Set([...existing.routes, ...dependency.routes])].sort();
      existing.routeOutcomes.push(...(dependency.routeOutcomes || []));
      existing.resourceTypes = [
        ...new Set([...existing.resourceTypes, ...dependency.resourceTypes]),
      ].sort();
      existing.requestCount += dependency.requestCount;
      existing.responses.push(...dependency.responses);
      existing.failures.push(...dependency.failures);
      existing.timeouts.push(...dependency.timeouts);
      existing.cspEvidence.push(...dependency.cspEvidence);
      existing.cspBlocked = existing.cspBlocked || dependency.cspBlocked;
      existing.state = classifyExternalDependency(existing);
    }
  }
  for (const dependency of merged.values()) {
    dependency.failures = groupFailureRecords(dependency.failures, publicRoutes);
    const routeOutcomes = new Map();
    for (const outcome of dependency.routeOutcomes) {
      const existing = routeOutcomes.get(outcome.route);
      if (!existing) {
        routeOutcomes.set(outcome.route, {
          ...outcome,
          failures: [...outcome.failures],
          timeouts: [...outcome.timeouts],
          cspEvidence: [...outcome.cspEvidence],
        });
        continue;
      }
      existing.responses.push(...outcome.responses);
      existing.failures.push(...outcome.failures);
      existing.timeouts.push(...outcome.timeouts);
      existing.cspEvidence.push(...outcome.cspEvidence);
      existing.cspBlocked = existing.cspBlocked || outcome.cspBlocked;
      existing.state = classifyExternalDependency({
        responses: existing.responses,
        failures: existing.failures,
        cspEvidence: existing.cspEvidence,
      });
    }
    dependency.routeOutcomes = [...routeOutcomes.values()]
      .map((outcome) => ({
        ...outcome,
        failures: groupFailureRecords(outcome.failures, publicRoutes),
        timeouts: [...new Map(
          outcome.timeouts.map((timeout) => [
            JSON.stringify([timeout.route, timeout.url]),
            timeout,
          ]),
        ).values()],
      }))
      .sort((left, right) => left.route.localeCompare(right.route));
    dependency.timeouts = [...new Map(
      dependency.timeouts.map((timeout) => [
        JSON.stringify([timeout.route, timeout.url]),
        timeout,
      ]),
    ).values()];
  }
  return [...merged.values()].sort((left, right) => left.url.localeCompare(right.url));
}

async function runExternalHealth() {
  const startedAt = Date.now();
  const overallDeadline = startedAt + externalHealthBudgetMs;
  console.log("OverKill Hill third-party runtime health");
  console.log("=".repeat(40));
  console.log(`Base URL: ${baseUrl}`);
  console.log(`Browser engine: ${browserName}`);
  console.log(`Routes: ${PUBLIC_PATHS.length}`);
  if (pathsArg) console.log(`Focused paths: ${PUBLIC_PATHS.join(", ")}`);
  console.log(
    "Cross-origin requests are allowed for this non-blocking availability check.",
  );
  console.log(
    "External outages, CSP diagnostics, and local route failures are reported separately.\n",
  );
  console.log(
    `Overall time budget: ${externalHealthBudgetMs}ms; ` +
    `per-route settle limit: ${EXTERNAL_SETTLE_TIMEOUT_MS}ms.\n`,
  );

  const browser = await externalHealthBrowserType.launch({ headless: true });
  const results = [];
  const routesCutShortByBudget = [];
  const routesSkippedByBudget = [];
  try {
    for (const [index, path] of PUBLIC_PATHS.entries()) {
      if (Date.now() >= overallDeadline) {
        routesSkippedByBudget.push(...PUBLIC_PATHS.slice(index));
        break;
      }
      const result = await checkExternalRoute(browser, path, overallDeadline);
      results.push(result);
      if (result.budgetExceeded) {
        routesCutShortByBudget.push(path);
      }
      console.log(
        `${result.localErrors.length ? "FAIL" : "CHECK"} ${path} ` +
        `(${result.dependencies.length} external request(s))`,
      );
      result.localErrors.forEach((error) => console.log(`      LOCAL: ${error}`));
      result.cspDiagnostics.forEach((message) => console.log(`      CSP: ${message}`));
      if (result.budgetExceeded) {
        routesSkippedByBudget.push(...PUBLIC_PATHS.slice(index + 1));
        break;
      }
    }
  } finally {
    await browser.close();
  }

  const timeBudget = {
    limitMs: externalHealthBudgetMs,
    elapsedMs: Date.now() - startedAt,
    exceeded: routesCutShortByBudget.length > 0 || routesSkippedByBudget.length > 0,
    routesCutShort: routesCutShortByBudget,
    routesSkipped: routesSkippedByBudget,
  };
  const dependencies = mergeExternalDependencies(results);
  const externalOutages = dependencies.filter(
    ({ state }) => state === "unavailable" || state === "no-response",
  );
  const cspDiagnostics = results.flatMap(({ path, cspDiagnostics: messages }) =>
    messages.map((message) => ({ path, message })),
  );
  const cspEvidence = results.flatMap(({ cspEvidence: evidence }) => evidence);
  const timeouts = dependencies.flatMap(({ timeouts: evidence }) => evidence);
  const localFailures = results.flatMap(({ path, localErrors }) =>
    localErrors.map((error) => ({ path, error })),
  );
  const failureEvents = dependencies.reduce(
    (total, dependency) =>
      total + dependency.failures.reduce((count, failure) => count + (failure.count || 1), 0),
    0,
  );
  const report = {
    version: 1,
    mode: "external-health",
    baseUrl,
    routes: PUBLIC_PATHS,
    dependencies,
    externalOutages,
    cspDiagnostics,
    cspEvidence,
    timeouts,
    localFailures,
    timeBudget,
    summary: {
      routes: results.length,
      dependencies: dependencies.length,
      available: dependencies.filter(({ state }) => state === "available").length,
      externalOutages: externalOutages.length,
      failureEvents,
      cspDiagnostics: cspDiagnostics.length,
      cspEvidence: cspEvidence.length,
      timeouts: timeouts.length,
      localFailures: localFailures.length,
      budgetExceeded: timeBudget.exceeded,
      routesCutShortByBudget: routesCutShortByBudget.length,
      routesSkippedByBudget: routesSkippedByBudget.length,
    },
    status: externalOutages.length
      ? "EXTERNAL_OUTAGE"
      : cspDiagnostics.length || cspEvidence.length
        ? "CSP_BLOCKED"
        : localFailures.length
          ? "LOCAL_FAILURE"
          : timeBudget.exceeded
            ? "TIME_BUDGET_EXCEEDED"
            : "PASS",
  };

  console.log(
    `\nExternal health: ${report.summary.dependencies} dependency URL(s), ` +
    `${report.summary.available} available, ` +
    `${report.summary.externalOutages} external outage(s), ` +
    `${report.summary.cspDiagnostics} CSP diagnostic(s), ` +
    `${report.summary.timeouts} timed-out request(s), ` +
    `${report.summary.localFailures} local route failure(s).`,
  );
  externalOutages.forEach((dependency) => {
    const failureReasons = dependency.failures
      .map(({ route, errorText, count = 1 }) => {
        const occurrences = count > 1 ? ` (${count} occurrences)` : "";
        // Reports written before route attribution may omit `route`; keep those
        // legacy v1 reports readable while current reports enforce public routes.
        return `${route || "unknown route"}: ${errorText}${occurrences}`;
      })
      .filter(Boolean);
    const diagnostic = failureReasons.length ? `: ${failureReasons.join(", ")}` : "";
    console.log(`  EXTERNAL OUTAGE: ${dependency.url} (${dependency.state})${diagnostic}`);
  });
  timeouts.forEach(({ route, url }) => {
    console.log(`  EXTERNAL TIMEOUT: ${route} ${url}`);
  });
  if (timeBudget.exceeded) {
    console.log(
      `  EXTERNAL HEALTH TIME BUDGET: ${externalHealthBudgetMs}ms overall limit reached.`,
    );
    routesCutShortByBudget.forEach((route) => {
      console.log(`  ROUTE CUT SHORT BY OVERALL BUDGET: ${route}`);
    });
    routesSkippedByBudget.forEach((route) => {
      console.log(`  ROUTE SKIPPED BY OVERALL BUDGET: ${route}`);
    });
  }
  if (cspDiagnostics.length || cspEvidence.length) {
    console.log("  CSP diagnostics were observed during the availability check.");
  }
  if (localFailures.length) {
    console.log("  Local route failures were observed during the availability check.");
  }

  if (reportArg) {
    const reportPath = reportArg.slice("--report=".length);
    if (!reportPath) throw new Error("--report must contain a file path");
    writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    console.log(`Report: ${reportPath}`);
  }

  if (
    externalOutages.length ||
    cspDiagnostics.length ||
    cspEvidence.length ||
    localFailures.length ||
    timeBudget.exceeded
  ) {
    process.exitCode = 1;
  }
}

async function main() {
  if (externalHealthMode) {
    await runExternalHealth();
    return;
  }
  console.log("OverKill Hill CSP browser QA");
  console.log("=".repeat(32));
  console.log(`Base URL: ${baseUrl}`);
  console.log(`Routes: ${PUBLIC_PATHS.length}`);
  if (pathsArg) console.log(`Focused paths: ${PUBLIC_PATHS.join(", ")}`);
  console.log("Cross-origin requests are blocked; blocked origins are reported as warnings.");
  console.log("CSP diagnostics remain unsuppressed.\n");

  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const path of PUBLIC_PATHS) {
      const result = await checkRoute(browser, path);
      results.push(result);
      if (result.pass) {
        console.log(`PASS  ${path} (${result.diagrams.rendered} Mermaid diagram(s))`);
      } else {
        console.log(`FAIL  ${path}`);
        result.errors.forEach((error) => console.log(`      → ${error}`));
      }
      if (result.blockedExternal.length) {
        console.log(`      WARN blocked cross-origin requests: ${result.blockedExternal.join(", ")}`);
      }
    }
  } finally {
    await browser.close();
  }

  const failures = results.filter((result) => !result.pass);
  const renderedDiagrams = results.reduce(
    (total, result) => total + result.diagrams.rendered,
    0,
  );
  writeFocusedReport(results);
  console.log(
    `\nCSP QA: ${results.length} routes, ${renderedDiagrams} Mermaid diagram(s), ` +
    `${failures.length} route failure(s).`,
  );
  if (failures.length) process.exitCode = 1;
}

if (fixtureSummaryArg) {
  try {
    writeFixtureSummary(reportPathFromArgument(fixtureSummaryArg, "fixture-summary"));
  } catch (error) {
    console.error(`CSP fixture summary could not be written: ${error.stack || error.message}`);
    process.exitCode = 1;
  }
} else {
  main().catch((error) => {
    console.error(`CSP QA could not run: ${error.stack || error.message}`);
    process.exitCode = 1;
  });
}

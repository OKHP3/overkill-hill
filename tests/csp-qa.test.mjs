import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";

const testsDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = join(testsDirectory, "..");
const cspQaScript = join(repositoryRoot, "scripts", "csp-qa.mjs");
const fixtureDirectory = join(testsDirectory, "fixtures", "csp");
const fixtureFiles = new Map([
  ["/console-violation.html", "console-violation.html"],
  ["/page-error.html", "page-error.html"],
  ["/missing-resource.html", "missing-resource.html"],
  ["/unrendered-mermaid.html", "unrendered-mermaid.html"],
  ["/external-network-failure.html", "external-network-failure.html"],
  ["/external-network-failure-shared.html", "external-network-failure-shared.html"],
  ["/external-repeated-network-failure.html", "external-repeated-network-failure.html"],
  ["/external-different-network-failures.html", "external-different-network-failures.html"],
  ["/external-csp-blocked.html", "external-csp-blocked.html"],
  ["/external-csp-and-outage.html", "external-csp-and-outage.html"],
  ["/external-csp-shared.html", "external-csp-shared.html"],
  ["/external-outage-shared.html", "external-outage-shared.html"],
  ["/external-csp-network-shared.html", "external-csp-network-shared.html"],
  ["/external-network-failure-network-shared.html", "external-network-failure-network-shared.html"],
  ["/external-delayed-outage.html", "external-delayed-outage.html"],
  ["/external-timeout.html", "external-timeout.html"],
]);

let server;
let externalServer;
const pendingExternalSockets = new Set();
let baseUrl;
let externalBaseUrl;
let focusedReportDirectory;
let focusedReportNumber = 0;
const focusedResults = [];

async function serveFixture(request, response) {
  const path = new URL(request.url, "http://csp-fixture").pathname;

  if (path === "/boom.js") {
    response.writeHead(200, { "content-type": "text/javascript" });
    response.end('throw new Error("fixture page error");');
    return;
  }

  if (path === "/missing-local.png") {
    response.writeHead(404, { "content-type": "text/plain" });
    response.end("fixture resource intentionally missing");
    return;
  }

  if (path === "/external-health.html") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(`<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>External health fixture</title></head>
  <body>
    <main><h1>External health fixture</h1>
      <img src="${externalBaseUrl}/healthy.png" alt="healthy dependency">
      <img src="${externalBaseUrl}/outage.png" alt="unavailable dependency">
    </main>
  </body>
</html>`);
    return;
  }

  if (path === "/external-healthy-only.html") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(`<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Healthy external dependency fixture</title></head>
  <body>
    <main><h1>Healthy external dependency fixture</h1>
      <img src="${externalBaseUrl}/healthy.png" alt="healthy dependency">
    </main>
  </body>
</html>`);
    return;
  }

  const fixtureName = fixtureFiles.get(path);
  if (fixtureName) {
    const fixture = await readFile(join(fixtureDirectory, fixtureName), "utf8");
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(fixture.replaceAll("__EXTERNAL_BASE_URL__", externalBaseUrl));
    return;
  }

  response.writeHead(404, { "content-type": "text/plain" });
  response.end("fixture route not found");
}

before(async () => {
  focusedReportDirectory = await mkdtemp(join(tmpdir(), "csp-focused-results-"));
  externalServer = createServer((request, response) => {
    const path = new URL(request.url, "http://external-fixture").pathname;
    if (path === "/healthy.png") {
      response.writeHead(200, { "content-type": "image/png" });
      response.end(Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "base64",
      ));
      return;
    }
    if (path === "/outage.png") {
      response.writeHead(503, { "content-type": "text/plain" });
      response.end("fixture dependency intentionally unavailable");
      return;
    }
    if (path === "/aborted.png") {
      request.socket.destroy();
      return;
    }
    if (path === "/different-failure.png") {
      const variant = new URL(request.url, "http://external-fixture").searchParams.get("variant");
      if (variant === "truncated") {
        response.writeHead(200, {
          "content-type": "image/png",
          "content-length": "64",
        });
        response.end(Buffer.from("truncated"));
      } else {
        request.socket.destroy();
      }
      return;
    }
    if (path === "/network-shared.png") {
      request.socket.destroy();
      return;
    }
    if (path === "/blocked.png") {
      response.writeHead(200, { "content-type": "image/png" });
      response.end(Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "base64",
      ));
      return;
    }
    if (path === "/shared.png") {
      response.writeHead(503, { "content-type": "text/plain" });
      response.end("shared fixture dependency intentionally unavailable");
      return;
    }
    if (path === "/delayed-outage.png") {
      setTimeout(() => {
        response.writeHead(503, { "content-type": "text/plain" });
        response.end("delayed fixture dependency intentionally unavailable");
      }, 1400);
      return;
    }
    if (path === "/pending.png") {
      pendingExternalSockets.add(request.socket);
      request.socket.once("close", () => pendingExternalSockets.delete(request.socket));
      return;
    }
    response.writeHead(404, { "content-type": "text/plain" });
    response.end("external fixture route not found");
  });
  await new Promise((resolve) => externalServer.listen(0, "127.0.0.1", resolve));
  const externalAddress = externalServer.address();
  externalBaseUrl = `http://127.0.0.1:${externalAddress.port}`;

  server = createServer((request, response) => {
    serveFixture(request, response).catch((error) => {
      response.writeHead(500, { "content-type": "text/plain" });
      response.end(error.message);
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  baseUrl = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  for (const socket of pendingExternalSockets) socket.destroy();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  await new Promise((resolve, reject) =>
    externalServer.close((error) => error ? reject(error) : resolve()));
  const reportPath = process.env.CSP_FIXTURE_REPORT;
  if (reportPath) {
    try {
      await writeFile(reportPath, `${JSON.stringify({
        version: 1,
        mode: "csp-fixtures",
        fixtures: focusedResults,
      }, null, 2)}\n`);
    } catch (error) {
      console.error(`Could not write CSP fixture report: ${error.message}`);
    }
  }
  await rm(focusedReportDirectory, { recursive: true, force: true });
});

function runCspQa(path, flags = []) {
  return new Promise((resolve, reject) => {
    const focused = !flags.includes("--external-health") && !flags.includes("--check-external");
    const reportPath = focused
      ? join(focusedReportDirectory, `${focusedReportNumber++}.json`)
      : null;
    const child = spawn(
      process.execPath,
      [
        cspQaScript,
        `--base-url=${baseUrl}`,
        `--paths=${path}`,
        ...(reportPath ? [`--report=${reportPath}`] : []),
        ...flags,
      ],
      { cwd: repositoryRoot },
    );
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`CSP QA timed out for ${path}`));
    }, 60000);

    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on("close", (status, signal) => {
      clearTimeout(timeout);
      const result = {
        output: `${stdout}\n${stderr}`,
        status,
        signal,
      };
      if (reportPath) {
        readFile(reportPath, "utf8")
          .then((content) => {
            const report = JSON.parse(content);
            focusedResults.push({
              path,
              pass: report.results?.[0]?.pass ?? status === 0,
              errors: report.results?.[0]?.errors ?? [],
            });
            resolve({ ...result, report });
          })
          .catch(reject);
        return;
      }
      resolve(result);
    });
  });
}

function runFixtureSummary(reportPath, summaryPath, artifactUrl = null) {
  const args = [
    cspQaScript,
    `--fixture-summary=${reportPath}`,
    `--summary=${summaryPath}`,
  ];
  if (artifactUrl) args.push(`--artifact-url=${artifactUrl}`);
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      args,
      { cwd: repositoryRoot },
    );
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("CSP fixture summary timed out"));
    }, 10000);

    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on("close", (status, signal) => {
      clearTimeout(timeout);
      resolve({
        output: `${stdout}\n${stderr}`,
        status,
        signal,
      });
    });
  });
}

function assertExternalFailureReportContract(report) {
  assert.equal(report.version, 1);
  assert.equal(report.mode, "external-health");
  assert.ok(Array.isArray(report.routes));
  assert.equal(typeof report.status, "string");
  assert.ok(report.summary && typeof report.summary === "object");
  assert.equal(typeof report.summary.failureEvents, "number");

  const failures = [
    ...report.dependencies.flatMap(({ failures = [] }) => failures),
    ...report.dependencies.flatMap(({ routeOutcomes = [] }) =>
      routeOutcomes.flatMap(({ failures = [] }) => failures),
    ),
    ...report.externalOutages.flatMap(({ failures = [] }) => failures),
    ...report.externalOutages.flatMap(({ routeOutcomes = [] }) =>
      routeOutcomes.flatMap(({ failures = [] }) => failures),
    ),
  ];

  for (const failure of failures) {
    assert.equal(
      typeof failure.route,
      "string",
      "current external failure records must include route attribution",
    );
    assert.ok(
      report.routes.includes(failure.route),
      `external failure route is not a public checked route: ${failure.route}`,
    );
    assert.equal(typeof failure.errorText, "string");
    assert.ok(failure.errorText.trim(), "external failure error text must be non-empty");
  }
}

test("links the focused CSP summary to its uploaded artifact", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-link-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");
  const artifactUrl = "https://github.com/example/site/actions/runs/123/artifacts/456";

  try {
    await writeFile(reportPath, `${JSON.stringify({
      version: 1,
      mode: "csp-fixtures",
      fixtures: [{ path: "/blocked.html", errors: ["CSP: blocked"] }],
    })}\n`);

    const result = await runFixtureSummary(reportPath, summaryPath, artifactUrl);
    assert.equal(result.status, 0, result.output);
    const summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      new RegExp(
        String.raw`Focused CSP evidence artifact: \[csp-fixture-report\.json\]\(` +
        artifactUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") +
        String.raw`\)`,
      ),
    );
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});


test("keeps the focused CSP summary useful without an uploaded artifact", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-missing-"));
  const reportPath = join(reportDirectory, "missing-report.json");
  const summaryPath = join(reportDirectory, "summary.md");

  try {
    const result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    const summary = await readFile(summaryPath, "utf8");
    assert.match(summary, /\| unavailable \| unknown \| Could not read focused CSP fixture report:/);
    assert.match(
      summary,
      /Focused CSP evidence artifact: unavailable; check the upload step for a warning or missing report\./,
    );
    assert.doesNotMatch(summary, /Focused CSP evidence artifact: \[/);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("keeps every browser diagnostic category visible in the focused summary", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");
  const diagnostics = [
    ["CSP", "CSP: blocked | policy\nwith a second line"],
    ["PAGEERROR", "PAGEERROR: Error: page exploded"],
    ["CONSOLE", "CONSOLE: ERROR: console exploded"],
    [
      "LOCAL REQUEST FAILED",
      "LOCAL REQUEST FAILED: /app.js (net::ERR_FAILED)",
    ],
    [
      "LOCAL HTTP ERROR",
      "LOCAL HTTP ERROR: 404 /missing.png",
    ],
    ["MERMAID", "MERMAID: ERROR: render failed"],
  ];
  const fixtures = [{
    path: "/combined.html",
    errors: diagnostics.map(([, message]) => message),
  }, {
    path: "/unknown.html",
    errors: ["NETWORK: new browser diagnostic | preserve this"],
  }];

  try {
    await writeFile(reportPath, `${JSON.stringify({
      version: 1,
      mode: "csp-fixtures",
      fixtures,
    })}\n`);

    const result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    const summary = await readFile(summaryPath, "utf8");

    const combinedRow = summary
      .split("\n")
      .find((line) => line.startsWith("| /combined.html |"));
    assert.equal(
      combinedRow,
      "| /combined.html | CSP, PAGEERROR, CONSOLE, LOCAL REQUEST FAILED, " +
      "LOCAL HTTP ERROR, MERMAID | " +
      "CSP: blocked \\| policy with a second line / " +
      "PAGEERROR: Error: page exploded / " +
      "CONSOLE: ERROR: console exploded / " +
      "LOCAL REQUEST FAILED: /app.js (net::ERR_FAILED) / " +
      "LOCAL HTTP ERROR: 404 /missing.png / " +
      "MERMAID: ERROR: render failed |",
      "combined browser diagnostics were not retained in one focused summary row",
    );
    assert.match(
      summary,
      /\| \/unknown\.html \| none observed \| NETWORK: new browser diagnostic \\| preserve this \|/,
    );
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("fails on a browser CSP console violation", async () => {
  const result = await runCspQa("/console-violation.html");
  assert.notEqual(result.status, 0, result.output);
  const output = result.output;
  assert.match(output, /CSP: ERROR:/);
  assert.match(output, /console-violation\.html/);
});

test("fails on a page-level JavaScript error", async () => {
  const result = await runCspQa("/page-error.html");
  assert.notEqual(result.status, 0, result.output);
  const output = result.output;
  assert.match(output, /PAGEERROR: Error: fixture page error/);
  assert.match(output, /page-error\.html/);
});

test("fails on a failed local resource", async () => {
  const result = await runCspQa("/missing-resource.html");
  assert.notEqual(result.status, 0, result.output);
  const output = result.output;
  assert.match(output, /LOCAL HTTP ERROR: 404 .*missing-local\.png/);
});

test("fails when a Mermaid diagram does not render", async () => {
  const result = await runCspQa("/unrendered-mermaid.html");
  assert.notEqual(result.status, 0, result.output);
  const output = result.output;
  assert.match(output, /MERMAID: rendered 0\/1 diagrams/);
  assert.match(output, /unrendered-mermaid\.html/);
});

test("reports external outages separately from the local CSP gate", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-external-health-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-health.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.doesNotMatch(result.output, /CSP diagnostics were observed/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.mode, "external-health");
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.cspDiagnostics, 0);
    assert.equal(report.summary.localFailures, 0);
    assert.equal(report.summary.externalOutages, 1);

    const healthy = report.dependencies.find(({ url }) => url.endsWith("/healthy.png"));
    const outage = report.dependencies.find(({ url }) => url.endsWith("/outage.png"));
    assert.equal(healthy.state, "available");
    assert.equal(outage.state, "unavailable");
    assert.ok(healthy.requestCount >= 1);
    assert.ok(outage.requestCount >= 1);
    assert.deepEqual(outage.routes, ["/external-health.html"]);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("reports an explicit zero failure total for an available dependency", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-healthy-only-"));
  const reportPath = join(reportDirectory, "report.json");
  const route = "/external-healthy-only.html";
  try {
    const result = await runCspQa(route, [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.equal(result.status, 0, result.output);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "PASS", JSON.stringify(report, null, 2));
    assert.equal(report.mode, "external-health");
    assert.deepEqual(report.routes, [route]);
    assert.equal(report.summary.failureEvents, 0, JSON.stringify(report, null, 2));
    assertExternalFailureReportContract(report);
    assert.equal(report.summary.dependencies, 1);
    assert.equal(report.summary.available, 1);
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.localFailures, 0);
    assert.equal(report.summary.cspDiagnostics, 0);
    assert.equal(report.summary.cspEvidence, 0);
    assert.equal(report.summary.timeouts, 0);
    assert.deepEqual(report.externalOutages, []);
    assert.deepEqual(report.localFailures, []);
    assert.deepEqual(report.cspDiagnostics, []);
    assert.deepEqual(report.cspEvidence, []);
    assert.deepEqual(report.timeouts, []);

    assert.equal(report.dependencies.length, 1);
    const [healthy] = report.dependencies;
    assert.ok(healthy.url.endsWith("/healthy.png"), JSON.stringify(report, null, 2));
    assert.equal(healthy.state, "available");
    assert.deepEqual(healthy.routes, [route]);
    assert.ok(healthy.requestCount >= 1);
    assert.ok(healthy.responses.some(({ status }) => status === 200));
    assert.deepEqual(healthy.failures, []);
    assert.deepEqual(healthy.timeouts, []);
    assert.deepEqual(healthy.cspEvidence, []);
    assert.deepEqual(
      healthy.routeOutcomes.map(({ route: outcomeRoute, state }) => ({
        route: outcomeRoute,
        state,
      })),
      [{ route, state: "available" }],
    );
    const [routeOutcome] = healthy.routeOutcomes;
    assert.deepEqual(routeOutcome.failures, []);
    assert.ok(routeOutcome.responses.some(({ status }) => status === 200));
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("preserves the browser failure reason for an aborted external request", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-network-failure-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-network-failure.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /\/external-network-failure\.html: net::ERR_/);
    assert.match(result.output, /net::ERR_/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assertExternalFailureReportContract(report);
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.summary.failureEvents, 1);

    const aborted = report.dependencies.find(({ url }) => url.endsWith("/aborted.png"));
    assert.ok(aborted, JSON.stringify(report, null, 2));
    assert.equal(aborted.state, "unavailable");
    assert.equal(aborted.responses.length, 0);
    assert.equal(aborted.failures.length, 1);
    assert.equal(aborted.failures[0].route, "/external-network-failure.html");
    assert.match(aborted.failures[0].errorText, /^net::ERR_/);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("attributes repeated external failures to every public route", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-failure-routes-"));
  const reportPath = join(reportDirectory, "report.json");
  const paths = "/external-network-failure.html,/external-network-failure-shared.html";
  try {
    const result = await runCspQa(paths, [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /\/external-network-failure\.html: net::ERR_/);
    assert.match(result.output, /\/external-network-failure-shared\.html: net::ERR_/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assertExternalFailureReportContract(report);
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);

    const aborted = report.dependencies.find(({ url }) => url.endsWith("/aborted.png"));
    assert.ok(aborted, JSON.stringify(report, null, 2));
    assert.equal(aborted.state, "unavailable");
    assert.deepEqual(aborted.routes, [
      "/external-network-failure-shared.html",
      "/external-network-failure.html",
    ].sort());
    assert.deepEqual(
      aborted.failures.map(({ route }) => route).sort(),
      [
        "/external-network-failure-shared.html",
        "/external-network-failure.html",
      ].sort(),
    );
    assert.ok(aborted.failures.every(({ errorText }) => /^net::ERR_/.test(errorText)));
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("groups repeated failures for one dependency without losing the browser reason", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-repeated-failures-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-repeated-network-failure.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /2 occurrences/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.summary.failureEvents, 2);

    const aborted = report.dependencies.find(({ url }) => url.endsWith("/aborted.png"));
    assert.ok(aborted, JSON.stringify(report, null, 2));
    assert.equal(aborted.state, "unavailable");
    assert.equal(aborted.failures.length, 1);
    assert.deepEqual(aborted.failures[0], {
      route: "/external-repeated-network-failure.html",
      errorText: aborted.failures[0].errorText,
      count: 2,
    });
    assert.match(aborted.failures[0].errorText, /^net::ERR_/);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("counts shared repeated failures once while preserving route evidence", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-shared-repeated-failures-"));
  const reportPath = join(reportDirectory, "report.json");
  const repeatedRoute = "/external-repeated-network-failure.html";
  const sharedRoute = "/external-network-failure-shared.html";
  const routes = [repeatedRoute, sharedRoute].sort();
  try {
    const result = await runCspQa(routes.join(","), [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    for (const route of routes) {
      assert.ok(result.output.includes(`${route}: net::ERR_`), result.output);
    }

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assertExternalFailureReportContract(report);
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.summary.failureEvents, 3, JSON.stringify(report, null, 2));

    const dependency = report.dependencies.find(({ url }) => url.endsWith("/aborted.png"));
    assert.ok(dependency, JSON.stringify(report, null, 2));
    assert.equal(dependency.url.includes("?"), false);
    assert.equal(dependency.state, "unavailable");
    assert.deepEqual(dependency.routes, routes);
    assert.deepEqual(
      dependency.failures.map(({ route, count }) => ({ route, count }))
        .sort((left, right) => left.route.localeCompare(right.route)),
      [
        { route: sharedRoute, count: 1 },
        { route: repeatedRoute, count: 2 },
      ].sort((left, right) => left.route.localeCompare(right.route)),
    );
    assert.ok(dependency.failures.every(({ errorText }) => /^net::ERR_/.test(errorText)));

    assert.deepEqual(
      dependency.routeOutcomes.map(({ route, state }) => ({ route, state })),
      routes.map((route) => ({ route, state: "unavailable" })),
    );
    for (const outcome of dependency.routeOutcomes) {
      const expectedCount = outcome.route === repeatedRoute ? 2 : 1;
      assert.deepEqual(
        outcome.failures.map(({ route, count }) => ({ route, count })),
        [{ route: outcome.route, count: expectedCount }],
      );
      assert.ok(outcome.failures.every(({ errorText }) => /^net::ERR_/.test(errorText)));
    }

    const outage = report.externalOutages.find(({ url }) => url.endsWith("/aborted.png"));
    assert.ok(outage, JSON.stringify(report, null, 2));
    assert.equal(outage.state, "unavailable");
    assert.deepEqual(outage.routes, routes);
    assert.deepEqual(outage.routeOutcomes, dependency.routeOutcomes);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("keeps different browser failure reasons separate for one normalized dependency", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-different-failures-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-different-network-failures.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.equal((result.output.match(/net::ERR_EMPTY_RESPONSE/g) || []).length, 1, result.output);
    assert.equal(
      (result.output.match(/net::ERR_CONTENT_LENGTH_MISMATCH/g) || []).length,
      1,
      result.output,
    );

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assertExternalFailureReportContract(report);
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);

    const dependency = report.dependencies.find(({ url }) =>
      url.endsWith("/different-failure.png"),
    );
    assert.ok(dependency, JSON.stringify(report, null, 2));
    assert.deepEqual(dependency.routes, ["/external-different-network-failures.html"]);
    assert.equal(dependency.failures.length, 2);
    assert.deepEqual(
      dependency.failures.map(({ route, errorText, count }) => ({
        route,
        errorText,
        count,
      })).sort((left, right) => left.errorText.localeCompare(right.errorText)),
      [
        {
          route: "/external-different-network-failures.html",
          errorText: "net::ERR_CONTENT_LENGTH_MISMATCH",
          count: 1,
        },
        {
          route: "/external-different-network-failures.html",
          errorText: "net::ERR_EMPTY_RESPONSE",
          count: 1,
        },
      ],
    );
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("reports CSP-blocked dependencies separately from external outages", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-blocked-health-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-csp-blocked.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /CSP diagnostics were observed/);
    assert.doesNotMatch(result.output, /EXTERNAL OUTAGE:/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.mode, "external-health");
    assert.equal(report.status, "CSP_BLOCKED");
    assert.equal(report.summary.cspDiagnostics, 1);
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.failureEvents, 1);
    assert.equal(report.summary.localFailures, 0);

    const blocked = report.dependencies.find(({ url }) => url.endsWith("/blocked.png"));
    assert.ok(blocked, JSON.stringify(report, null, 2));
    assert.equal(blocked.state, "blocked-by-csp");
    assert.equal(blocked.cspBlocked, true);
    assert.equal(blocked.failures[0].route, "/external-csp-blocked.html");
    assert.equal(blocked.cspEvidence.length, 1);
    assert.equal(blocked.cspEvidence[0].route, "/external-csp-blocked.html");
    assert.equal(blocked.cspEvidence[0].blockedURI, blocked.url);
    assert.equal(blocked.cspEvidence[0].effectiveDirective, "img-src");
    assert.equal(blocked.cspEvidence[0].violatedDirective, "img-src");
    assert.equal(blocked.cspEvidence[0].disposition, "enforce");
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("keeps an external outage visible alongside a CSP-blocked dependency", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-mixed-health-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-csp-and-outage.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /CSP diagnostics were observed/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.mode, "external-health");
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.dependencies, 2);
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.summary.cspDiagnostics, 1);
    assert.equal(report.summary.localFailures, 0);
    assert.equal(report.externalOutages.length, 1);
    assert.equal(report.cspDiagnostics.length, 1);

    const blocked = report.dependencies.find(({ url }) => url.endsWith("/blocked.png"));
    const outage = report.dependencies.find(({ url }) => url.endsWith("/outage.png"));
    assert.ok(blocked, JSON.stringify(report, null, 2));
    assert.ok(outage, JSON.stringify(report, null, 2));
    assert.equal(blocked.state, "blocked-by-csp");
    assert.equal(blocked.cspBlocked, true);
    assert.equal(outage.state, "unavailable");
    assert.equal(outage.cspBlocked, false);
    assert.ok(outage.responses.some(({ status }) => status === 503));
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("keeps a genuine network failure visible when another route blocks the same URL with CSP", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-network-shared-health-"));
  const reportPath = join(reportDirectory, "report.json");
  const paths = "/external-csp-network-shared.html,/external-network-failure-network-shared.html";
  try {
    const result = await runCspQa(paths, [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /CSP diagnostics were observed/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.summary.cspEvidence, 1);

    const shared = report.dependencies.find(({ url }) => url.endsWith("/network-shared.png"));
    assert.ok(shared, JSON.stringify(report, null, 2));
    assert.equal(shared.state, "unavailable");
    assert.equal(shared.cspBlocked, true);
    assert.deepEqual(shared.cspEvidence.map(({ route }) => route), [
      "/external-csp-network-shared.html",
    ]);
    assert.deepEqual(shared.failures.map(({ route }) => route), [
      "/external-csp-network-shared.html",
      "/external-network-failure-network-shared.html",
    ].sort());
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("keeps a shared-route outage visible when another route blocks the same URL with CSP", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-shared-health-"));
  const reportPath = join(reportDirectory, "report.json");
  const paths = "/external-csp-shared.html,/external-outage-shared.html";
  try {
    const result = await runCspQa(paths, [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /CSP diagnostics were observed/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.deepEqual(report.routes, [
      "/external-csp-shared.html",
      "/external-outage-shared.html",
    ]);
    assert.equal(report.summary.dependencies, 1);
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.summary.cspDiagnostics, 1);

    const shared = report.dependencies.find(({ url }) => url.endsWith("/shared.png"));
    assert.ok(shared, JSON.stringify(report, null, 2));
    assert.deepEqual(shared.routes, [
      "/external-csp-shared.html",
      "/external-outage-shared.html",
    ]);
    assert.deepEqual(
      shared.routeOutcomes.map(({ route, state }) => ({ route, state })),
      [
        {
          route: "/external-csp-shared.html",
          state: "blocked-by-csp",
        },
        {
          route: "/external-outage-shared.html",
          state: "unavailable",
        },
      ],
    );
    const cspRoute = shared.routeOutcomes.find(
      ({ route }) => route === "/external-csp-shared.html",
    );
    const outageRoute = shared.routeOutcomes.find(
      ({ route }) => route === "/external-outage-shared.html",
    );
    assert.ok(cspRoute.cspEvidence.some(({ blockedURI }) => blockedURI === shared.url));
    assert.equal(cspRoute.responses.length, 0);
    assert.ok(outageRoute.responses.some(({ status }) => status === 503));
    assert.equal(outageRoute.cspEvidence.length, 0);
    assert.equal(shared.cspBlocked, true);
    assert.equal(shared.state, "unavailable");
    assert.ok(shared.responses.some(({ status }) => status === 503));

    const outage = report.externalOutages.find(({ url }) => url.endsWith("/shared.png"));
    assert.ok(outage, JSON.stringify(report, null, 2));
    assert.deepEqual(outage.routes, shared.routes);
    assert.ok(outage.responses.some(({ status }) => status === 503));
    assert.equal(outage.state, "unavailable");
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("waits for a delayed external response before classifying the dependency", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-delayed-health-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-delayed-outage.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE:/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);

    const delayed = report.dependencies.find(({ url }) => url.endsWith("/delayed-outage.png"));
    assert.ok(delayed, JSON.stringify(report, null, 2));
    assert.equal(delayed.state, "unavailable");
    assert.ok(delayed.responses.some(({ status }) => status === 503));
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("identifies external requests that remain pending through the settle timeout", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-timeout-health-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-timeout.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /EXTERNAL OUTAGE: .*pending\.png \(no-response\)/);
    assert.match(result.output, /EXTERNAL TIMEOUT: \/external-timeout\.html .*pending\.png/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.summary.timeouts, 1);
    assert.deepEqual(report.timeouts, [{
      route: "/external-timeout.html",
      url: report.timeouts[0].url,
    }]);

    const pending = report.dependencies.find(({ url }) => url.endsWith("/pending.png"));
    assert.ok(pending, JSON.stringify(report, null, 2));
    assert.equal(pending.state, "no-response");
    assert.equal(pending.responses.length, 0);
    assert.equal(pending.failures.length, 0);
    assert.deepEqual(pending.timeouts, [{
      route: "/external-timeout.html",
      url: pending.url,
    }]);
    assert.deepEqual(pending.routeOutcomes, [{
      route: "/external-timeout.html",
      state: "no-response",
      cspBlocked: false,
      responses: [],
      failures: [],
      timeouts: [{
        route: "/external-timeout.html",
        url: pending.url,
      }],
      cspEvidence: [],
    }]);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("enforces one external-health budget across routes and reports affected routes", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-budget-health-"));
  const reportPath = join(reportDirectory, "report.json");
  const paths = "/external-timeout.html,/external-delayed-outage.html";
  try {
    const result = await runCspQa(paths, [
      "--external-health",
      "--external-budget-ms=1500",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /ROUTE CUT SHORT BY OVERALL BUDGET: \/external-timeout\.html/);
    assert.match(result.output, /ROUTE SKIPPED BY OVERALL BUDGET: \/external-delayed-outage\.html/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.timeBudget.limitMs, 1500);
    assert.equal(report.timeBudget.exceeded, true);
    assert.deepEqual(report.timeBudget.routesCutShort, ["/external-timeout.html"]);
    assert.deepEqual(report.timeBudget.routesSkipped, ["/external-delayed-outage.html"]);
    assert.equal(report.summary.routes, 1);
    assert.equal(report.summary.budgetExceeded, true);
    assert.equal(report.summary.routesCutShortByBudget, 1);
    assert.equal(report.summary.routesSkippedByBudget, 1);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});
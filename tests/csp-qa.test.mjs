import assert from "node:assert/strict";
import { createServer } from "node:http";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { after, before, test } from "node:test";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { runInNewContext } from "node:vm";
import { firefox, webkit } from "playwright";

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
  ["/external-csp-same-path-different-hosts.html", "external-csp-same-path-different-hosts.html"],
  ["/external-non-network-csp.html", "external-non-network-csp.html"],
  ["/external-csp-and-outage.html", "external-csp-and-outage.html"],
  ["/external-csp-shared.html", "external-csp-shared.html"],
  ["/external-outage-shared.html", "external-outage-shared.html"],
  ["/external-outage-shared-second.html", "external-outage-shared-second.html"],
  ["/external-csp-network-shared.html", "external-csp-network-shared.html"],
  ["/external-network-failure-network-shared.html", "external-network-failure-network-shared.html"],
  ["/external-delayed-outage.html", "external-delayed-outage.html"],
  ["/external-timeout.html", "external-timeout.html"],
  ["/external-late-response.html", "external-late-response.html"],
]);
const optionalEngineChecks = [
  {
    name: "firefox",
    browserType: firefox,
    userAgentPattern: /Firefox\//,
  },
  {
    name: "webkit",
    browserType: webkit,
    userAgentPattern: /Version\/.*Safari\//,
  },
].map(({ name, browserType, userAgentPattern }) => {
  const executablePath = browserType.executablePath();
  const available = existsSync(executablePath);
  return {
    name,
    executablePath,
    available,
    skipReason: available
      ? false
      : `${name} skipped: configured Playwright executable is missing at ${executablePath}`,
    userAgentPattern,
  };
});

let server;
let externalServer;
const pendingExternalSockets = new Set();
const externalFixtureObservations = [];
let baseUrl;
let externalBaseUrl;
let observedCspBlockedFixtureResponse = "";
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

  if (
    path === "/external-healthy-only.html" ||
    path === "/external-healthy-shared.html"
  ) {
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

  if (
    path === "/external-no-content-one.html" ||
    path === "/external-no-content-two.html"
  ) {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(`<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Healthy no-content dependency fixture</title></head>
  <body>
    <main><h1>Healthy no-content dependency fixture</h1>
      <script>
        fetch("${externalBaseUrl}/no-content.json")
          .then(async (response) => {
            window.fixtureResponse = {
              status: response.status,
              body: await response.text(),
            };
          });
      </script>
    </main>
  </body>
</html>`);
    return;
  }

  if (
    path === "/external-redirect-healthy-one.html" ||
    path === "/external-redirect-healthy-two.html"
  ) {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(`<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Healthy redirect fixture</title></head>
  <body>
    <main><h1>Healthy redirect fixture</h1>
      <img src="${externalBaseUrl}/redirect.png" alt="healthy redirected dependency">
    </main>
  </body>
</html>`);
    return;
  }

  const fixtureName = fixtureFiles.get(path);
  if (fixtureName) {
    const fixture = await readFile(join(fixtureDirectory, fixtureName), "utf8");
    const renderedFixture = fixture.replaceAll(
      "__EXTERNAL_BASE_URL__",
      externalBaseUrl,
    ).replaceAll(
      "__EXTERNAL_OTHER_HOST_URL__",
      externalBaseUrl.replace("127.0.0.1", "localhost"),
    );
    if (path === "/external-csp-blocked.html") {
      observedCspBlockedFixtureResponse = renderedFixture;
      const evidenceDirectory = process.env.CSP_TASK385_EVIDENCE_DIR;
      if (evidenceDirectory) {
        await mkdir(evidenceDirectory, { recursive: true });
        await writeFile(join(evidenceDirectory, "fixture-source.html"), fixture);
        await writeFile(
          join(evidenceDirectory, "fixture-rendered.html"),
          renderedFixture,
        );
      }
    }
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(renderedFixture);
    return;
  }

  response.writeHead(404, { "content-type": "text/plain" });
  response.end("fixture route not found");
}

before(async () => {
  focusedReportDirectory = await mkdtemp(join(tmpdir(), "csp-focused-results-"));
  const engineEvidenceDirectory = process.env.CSP_TASK384_EVIDENCE_DIR;
  if (engineEvidenceDirectory) {
    await mkdir(engineEvidenceDirectory, { recursive: true });
    await writeFile(
      join(engineEvidenceDirectory, "optional-engine-availability.json"),
      `${JSON.stringify(optionalEngineChecks.map(({
        name,
        executablePath,
        available,
        skipReason,
      }) => ({
        name,
        executablePath,
        available,
        skipReason,
      })), null, 2)}\n`,
    );
  }
  externalServer = createServer((request, response) => {
    const requestUrl = new URL(request.url, "http://external-fixture");
    const path = requestUrl.pathname;
    if (path === "/no-content.json") {
      externalFixtureObservations.push({ path, method: request.method, status: 204 });
      response.writeHead(204, {
        "access-control-allow-origin": "*",
        "content-type": "application/json",
      });
      response.end();
      return;
    }
    if (path === "/redirect.png") {
      externalFixtureObservations.push({ path, method: request.method, status: 302 });
      response.writeHead(302, {
        location: "/healthy.png",
        "content-type": "text/plain",
      });
      response.end("fixture dependency moved permanently for this request");
      return;
    }
    if (path === "/healthy.png") {
      externalFixtureObservations.push({ path, method: request.method, status: 200 });
      response.writeHead(200, { "content-type": "image/png" });
      response.end(Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "base64",
      ));
      return;
    }
    if (path === "/outage.png") {
      externalFixtureObservations.push({ path, method: request.method, status: 503 });
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
      externalFixtureObservations.push({
        path,
        method: request.method,
        query: requestUrl.search,
        status: 200,
      });
      response.writeHead(200, { "content-type": "image/png" });
      response.end(Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "base64",
      ));
      return;
    }
    if (path === "/same-path.png") {
      externalFixtureObservations.push({ path, method: request.method, status: 200 });
      response.writeHead(200, { "content-type": "image/png" });
      response.end(Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "base64",
      ));
      return;
    }
    if (path === "/blocked.css" || path === "/blocked.woff2") {
      externalFixtureObservations.push({
        path,
        method: request.method,
        query: requestUrl.search,
        status: 200,
      });
      response.writeHead(200, {
        "content-type": path.endsWith(".css")
          ? "text/css"
          : "font/woff2",
      });
      response.end(path.endsWith(".css") ? "/* fixture stylesheet */" : "");
      return;
    }
    if (path === "/shared.png") {
      externalFixtureObservations.push({
        path,
        method: request.method,
        status: 503,
        userAgent: request.headers["user-agent"] || null,
      });
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
    if (path === "/late-response.png") {
      // The runner spends 1s collecting deferred requests, then has a 5s
      // settle limit and a separate 1s late-response observation window.
      // This reply arrives about 500ms into that final window.
      setTimeout(() => {
        externalFixtureObservations.push({
          path,
          method: request.method,
          status: 200,
        });
        response.writeHead(200, { "content-type": "image/png" });
        response.end(Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
          "base64",
        ));
      }, 6500);
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

function runCspQa(path, flags = [], envOverrides = {}) {
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
      { cwd: repositoryRoot, env: { ...process.env, ...envOverrides } },
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

function runCspQaCommand(flags = []) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [cspQaScript, `--base-url=${baseUrl}`, ...flags],
      { cwd: repositoryRoot },
    );
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`CSP QA CLI timed out for ${flags.join(" ")}`));
    }, 60000);

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

async function readExternalHealthReport(reportPath, evidenceFilename) {
  const reportText = await readFile(reportPath, "utf8");
  const evidenceDirectory = process.env.CSP_TASK387_EVIDENCE_DIR;
  if (evidenceDirectory) {
    await writeFile(join(evidenceDirectory, evidenceFilename), reportText);
  }
  return JSON.parse(reportText);
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

// Validate current generated reports only; archived-report compatibility stays separate.
function assertExternalFailureReportContract(report) {
  assert.equal(report.version, 1);
  assert.equal(report.mode, "external-health");
  assert.ok(Array.isArray(report.routes));
  assert.equal(typeof report.status, "string");
  assert.ok(report.summary && typeof report.summary === "object");
  assert.equal(typeof report.summary.failureEvents, "number");

  const failures = [
    ...report.dependencies.flatMap((dependency, dependencyIndex) => {
      const { failures = [] } = dependency;
      return failures.map((failure, failureIndex) => ({
        failure,
        dependencyUrl: dependency.url,
        location: `dependencies[${dependencyIndex}].failures[${failureIndex}]`,
      }));
    }),
    ...report.dependencies.flatMap((dependency, dependencyIndex) => {
      const { routeOutcomes = [] } = dependency;
      return routeOutcomes.flatMap((routeOutcome, routeOutcomeIndex) => {
        const { failures = [] } = routeOutcome;
        return failures.map((failure, failureIndex) => ({
          failure,
          dependencyUrl: dependency.url,
          location:
            `dependencies[${dependencyIndex}].routeOutcomes[${routeOutcomeIndex}]` +
            `.failures[${failureIndex}]`,
          parentRoute: routeOutcome.route,
        }));
      });
    }),
    ...report.externalOutages.flatMap((outage, outageIndex) => {
      const { failures = [] } = outage;
      return failures.map((failure, failureIndex) => ({
        failure,
        dependencyUrl: outage.url,
        location: `externalOutages[${outageIndex}].failures[${failureIndex}]`,
      }));
    }),
    ...report.externalOutages.flatMap((outage, outageIndex) => {
      const { routeOutcomes = [] } = outage;
      return routeOutcomes.flatMap((routeOutcome, routeOutcomeIndex) => {
        const { failures = [] } = routeOutcome;
        return failures.map((failure, failureIndex) => ({
          failure,
          dependencyUrl: outage.url,
          location:
            `externalOutages[${outageIndex}].routeOutcomes[${routeOutcomeIndex}]` +
            `.failures[${failureIndex}]`,
          parentRoute: routeOutcome.route,
        }));
      });
    }),
  ];

  for (const record of failures) {
    const { failure, dependencyUrl, location, parentRoute } = record;
    const parentRouteContext = Object.hasOwn(record, "parentRoute")
      ? `; route outcome route: ${String(parentRoute)}`
      : "";
    const actualRouteContext = typeof failure.route === "string"
      ? `; reported route: ${failure.route}`
      : "";
    const context =
      `dependency ${dependencyUrl} at ${location}${parentRouteContext}${actualRouteContext}`;

    assert.equal(
      typeof failure.route,
      "string",
      `${context}: failure.route must be a string`,
    );
    assert.ok(
      report.routes.includes(failure.route),
      `${context}: failure.route is not in report.routes`,
    );
    assert.equal(
      typeof failure.errorText,
      "string",
      `${context}: failure.errorText must be a string`,
    );
    assert.ok(
      failure.errorText.trim(),
      `${context}: failure.errorText must be non-empty`,
    );
  }
}

function makeSyntheticExternalFailureReport() {
  return {
    version: 1,
    mode: "external-health",
    routes: ["/checked/alpha.html", "/checked/beta.html"],
    status: "EXTERNAL_OUTAGE",
    summary: { failureEvents: 1 },
    dependencies: [
      {
        url: "https://first.test/dependency.png",
        failures: [],
        routeOutcomes: [],
      },
      {
        url: "https://second.test/dependency.png",
        failures: [],
        routeOutcomes: [],
      },
    ],
    externalOutages: [
      {
        url: "https://first.test/outage.png",
        failures: [],
        routeOutcomes: [],
      },
      {
        url: "https://second.test/outage.png",
        failures: [],
        routeOutcomes: [],
      },
    ],
  };
}

function assertFailureDiagnosticContext(report, expected) {
  let error;
  assert.throws(() => {
    try {
      assertExternalFailureReportContract(report);
    } catch (caught) {
      error = caught;
      throw caught;
    }
  }, assert.AssertionError);
  assert.ok(error, "current external-health report should be rejected");
  for (const context of [
    expected.url,
    expected.location,
    expected.reason,
    expected.parentRoute,
    expected.actualRoute,
  ].filter(Boolean)) {
    assert.ok(
      error.message.includes(context),
      `failure diagnostic must include ${context}; received: ${error.message}`,
    );
  }
}

test("diagnoses missing attribution in dependency failures with URL and location", () => {
  const report = makeSyntheticExternalFailureReport();
  report.dependencies[1].failures = [{ errorText: "net::ERR_EMPTY_RESPONSE" }];

  assertFailureDiagnosticContext(report, {
    url: report.dependencies[1].url,
    location: "dependencies[1].failures[0]",
    reason: "failure.route",
  });
});

test("diagnoses missing attribution in nested dependency failures with parent route", () => {
  const report = makeSyntheticExternalFailureReport();
  report.dependencies[1].routeOutcomes = [{
    route: report.routes[0],
    failures: [{ errorText: "net::ERR_EMPTY_RESPONSE" }],
  }];

  assertFailureDiagnosticContext(report, {
    url: report.dependencies[1].url,
    location: "dependencies[1].routeOutcomes[0].failures[0]",
    reason: "failure.route",
    parentRoute: report.routes[0],
  });
});

test("diagnoses missing error text in nested dependency failures with route context", () => {
  const report = makeSyntheticExternalFailureReport();
  report.dependencies[1].routeOutcomes = [{
    route: report.routes[0],
    failures: [{ route: report.routes[0], errorText: " " }],
  }];

  assertFailureDiagnosticContext(report, {
    url: report.dependencies[1].url,
    location: "dependencies[1].routeOutcomes[0].failures[0]",
    reason: "failure.errorText",
    parentRoute: report.routes[0],
    actualRoute: report.routes[0],
  });
  assert.equal(report.status, "EXTERNAL_OUTAGE");
});

test("diagnoses blank error text in outage failures with URL and location", () => {
  const report = makeSyntheticExternalFailureReport();
  report.externalOutages[1].failures = [{
    route: report.routes[1],
    errorText: " ",
  }];

  assertFailureDiagnosticContext(report, {
    url: report.externalOutages[1].url,
    location: "externalOutages[1].failures[0]",
    reason: "failure.errorText",
    actualRoute: report.routes[1],
  });
});

test("diagnoses an unchecked route in nested outage failures with parent route", () => {
  const report = makeSyntheticExternalFailureReport();
  report.externalOutages[0].routeOutcomes = [{
    route: report.routes[0],
    failures: [{
      route: "/not-checked.html",
      errorText: "net::ERR_EMPTY_RESPONSE",
    }],
  }];

  assertFailureDiagnosticContext(report, {
    url: report.externalOutages[0].url,
    location: "externalOutages[0].routeOutcomes[0].failures[0]",
    reason: "failure.route",
    parentRoute: report.routes[0],
    actualRoute: "/not-checked.html",
  });
});

test("accepts a healthy external report with no failure records", () => {
  const report = makeSyntheticExternalFailureReport();
  report.status = "PASS";
  report.summary.failureEvents = 0;

  assert.doesNotThrow(() => assertExternalFailureReportContract(report));
});

test("accepts attributed failures in all current report collections", () => {
  const report = makeSyntheticExternalFailureReport();
  report.dependencies[0].failures = [{
    route: report.routes[0],
    errorText: "net::ERR_EMPTY_RESPONSE",
  }];
  report.dependencies[1].routeOutcomes = [{
    route: report.routes[1],
    failures: [{
      route: report.routes[1],
      errorText: "net::ERR_CONNECTION_RESET",
    }],
  }];
  report.externalOutages[0].failures = [{
    route: report.routes[0],
    errorText: "net::ERR_ABORTED",
  }];
  report.externalOutages[1].routeOutcomes = [{
    route: report.routes[1],
    failures: [{
      route: report.routes[1],
      errorText: "net::ERR_FAILED",
    }],
  }];

  assert.doesNotThrow(() => assertExternalFailureReportContract(report));
});

test("links the focused CSP summary to its uploaded artifact", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-link-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");
  const artifactUrl = "https://github.com/example/site/actions/runs/123/artifacts/456";

  try {
    await writeFile(reportPath, `${JSON.stringify({
      version: 1,
      mode: "csp-fixtures",
      fixtures: [{ path: "/blocked.html", pass: false, errors: ["CSP: blocked"] }],
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

test("marks unsupported focused CSP report formats unavailable and preserves artifact links", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-unsupported-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");
  const artifactUrl = "https://github.com/example/site/actions/runs/123/artifacts/456";
  const unsupportedFormats = [
    {
      version: 2,
      mode: "csp-fixtures",
      expected: /unsupported version \(expected 1; found 2\)/,
    },
    {
      version: 1,
      mode: "future-fixtures",
      expected: /unsupported mode \(expected csp-fixtures; found "future-fixtures"\)/,
    },
    {
      version: 2,
      mode: "future-fixtures",
      expected: /unsupported version \(expected 1; found 2\) and mode \(expected csp-fixtures; found "future-fixtures"\)/,
    },
  ];

  try {
    for (const format of unsupportedFormats) {
      await writeFile(reportPath, `${JSON.stringify({
        version: format.version,
        mode: format.mode,
        fixtures: [{ path: "/unsupported.html", pass: false, errors: ["CSP: blocked"] }],
      })}\n`);
      await writeFile(summaryPath, "");

      const result = await runFixtureSummary(reportPath, summaryPath, artifactUrl);
      assert.equal(result.status, 0, result.output);
      const summary = await readFile(summaryPath, "utf8");
      assert.match(
        summary,
        /\| unavailable \| UNKNOWN \| unknown \| Focused CSP fixture report uses unsupported /,
      );
      assert.match(summary, format.expected);
      assert.doesNotMatch(summary, /\/unsupported\.html|Fixture totals:/);
      assert.match(
        summary,
        new RegExp(
          String.raw`Focused CSP evidence artifact: \[csp-fixture-report\.json\]\(` +
          artifactUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") +
          String.raw`\)`,
        ),
      );
    }
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
    assert.match(
      summary,
      /\| unavailable \| UNKNOWN \| unknown \| Focused CSP fixture report is missing; the fixture test did not create the report file\./,
    );
    assert.match(
      summary,
      /Focused CSP evidence artifact: unavailable; the report file was missing, so the warning-only upload had nothing to retain\./,
    );
    assert.doesNotMatch(summary, /Focused CSP evidence artifact: \[/);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("reports unreadable focused CSP reports without treating them as missing", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-unreadable-"));
  const summaryPath = join(reportDirectory, "summary.md");
  const artifactUrl = "https://github.com/example/site/actions/runs/123/artifacts/456";

  try {
    // Reading a directory as a file reliably produces a non-ENOENT filesystem error,
    // including when the test process runs with permission to read every file.
    const result = await runFixtureSummary(reportDirectory, summaryPath, artifactUrl);
    assert.equal(result.status, 0, result.output);
    const summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      /\| unavailable \| UNKNOWN \| unknown \| Could not read focused CSP fixture report:/,
    );
    assert.doesNotMatch(
      summary,
      /Focused CSP fixture report is missing|report file was missing/,
    );
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

test("distinguishes empty and malformed focused CSP reports", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-invalid-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");

  try {
    await writeFile(reportPath, "");
    let result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    let summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      /\| unavailable \| UNKNOWN \| unknown \| Focused CSP fixture report is empty \(zero bytes\)\./,
    );
    assert.doesNotMatch(summary, /report file was missing/);

    await writeFile(reportPath, "{not-json");
    await writeFile(summaryPath, "");
    result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      /\| unavailable \| UNKNOWN \| unknown \| Focused CSP fixture report is malformed JSON:/,
    );
    assert.doesNotMatch(summary, /report file was missing/);

    await writeFile(reportPath, `${JSON.stringify({ version: 1, mode: "csp-fixtures", results: [] })}\n`);
    await writeFile(summaryPath, "");
    result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      /\| unavailable \| UNKNOWN \| unknown \| Focused CSP fixture report is malformed: expected an object with a fixtures array\./,
    );
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("distinguishes a valid report with no fixture results", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-no-results-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");

  try {
    await writeFile(reportPath, `${JSON.stringify({ version: 1, mode: "csp-fixtures", fixtures: [] })}\n`);
    const result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    const summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      /\| unavailable \| UNKNOWN \| unknown \| Focused CSP fixture report is empty: no fixture results were recorded\./,
    );
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("shows explicit pass and fail results for a mixed focused fixture report", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-status-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");

  try {
    await writeFile(reportPath, `${JSON.stringify({
      version: 1,
      mode: "csp-fixtures",
      fixtures: [
        { path: "/passing.html", pass: true, errors: [] },
        { path: "/also-passing.html", pass: true, errors: [] },
        { path: "/failing.html", pass: false, errors: ["CSP: blocked"] },
        { path: "/also-failing.html", pass: false, errors: ["CSP: inline script blocked"] },
      ],
    })}\n`);

    const result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    const summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      /\| \/passing\.html \| PASS \| none observed \| No browser diagnostic was captured\. \|/,
    );
    assert.match(
      summary,
      /\| \/failing\.html \| FAIL \| CSP \| CSP: blocked \|/,
    );
    assert.match(
      summary,
      /\| \/also-failing\.html \| FAIL \| CSP \| CSP: inline script blocked \|/,
    );
    assert.match(summary, /Fixture totals: \*\*2 PASS\*\*, \*\*2 FAIL\*\*\./);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("keeps fixtures with missing or non-boolean pass values UNKNOWN", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-summary-unknown-"));
  const reportPath = join(reportDirectory, "fixture-report.json");
  const summaryPath = join(reportDirectory, "summary.md");

  try {
    await writeFile(reportPath, `${JSON.stringify({
      version: 1,
      mode: "csp-fixtures",
      fixtures: [
        { path: "/missing-pass.html", errors: ["CSP: blocked"] },
        {
          path: "/non-boolean-pass.html",
          pass: "false",
          errors: ["PASS: no browser violations found"],
        },
      ],
    })}\n`);

    const result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    const summary = await readFile(summaryPath, "utf8");
    assert.match(
      summary,
      /\| \/missing-pass\.html \| UNKNOWN \| CSP \| CSP: blocked \|/,
    );
    assert.match(
      summary,
      /\| \/non-boolean-pass\.html \| UNKNOWN \| none observed \| PASS: no browser violations found \|/,
    );
    assert.match(summary, /Fixture totals: \*\*0 PASS\*\*, \*\*0 FAIL\*\*\./);
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
    pass: false,
    errors: [
      ...diagnostics.map(([, message]) => message),
      diagnostics[0][1],
      diagnostics[3][1],
    ],
  }, {
    path: "/unknown.html",
    pass: false,
    errors: ["NETWORK: new browser diagnostic | preserve this"],
  }];
  const fixtureReport = `${JSON.stringify({
    version: 1,
    mode: "csp-fixtures",
    fixtures,
  })}\n`;

  try {
    await writeFile(reportPath, fixtureReport);

    const result = await runFixtureSummary(reportPath, summaryPath);
    assert.equal(result.status, 0, result.output);
    const savedFixtureReport = await readFile(reportPath, "utf8");
    assert.equal(
      savedFixtureReport,
      fixtureReport,
      "writing the Markdown summary must not change the original fixture JSON",
    );
    assert.deepEqual(
      JSON.parse(savedFixtureReport).fixtures[0].errors,
      fixtures[0].errors,
      "the raw fixture JSON must retain repeated browser diagnostic evidence",
    );
    const summary = await readFile(summaryPath, "utf8");

    const combinedRow = summary
      .split("\n")
      .find((line) => line.startsWith("| /combined.html |"));
    assert.equal(
      combinedRow,
      "| /combined.html | FAIL | CSP, PAGEERROR, CONSOLE, LOCAL REQUEST FAILED, " +
      "LOCAL HTTP ERROR, MERMAID | " +
      "CSP: blocked \\| policy with a second line (2 occurrences) / " +
      "PAGEERROR: Error: page exploded / " +
      "CONSOLE: ERROR: console exploded / " +
      "LOCAL REQUEST FAILED: /app.js (net::ERR_FAILED) (2 occurrences) / " +
      "LOCAL HTTP ERROR: 404 /missing.png / " +
      "MERMAID: ERROR: render failed |",
      "combined browser diagnostics were not retained once per message with occurrence counts",
    );
    assert.equal(
      (combinedRow.match(/CSP: blocked/g) || []).length,
      1,
      "repeated CSP evidence should keep one representative message",
    );
    assert.equal(
      (combinedRow.match(/LOCAL REQUEST FAILED: \/app\.js/g) || []).length,
      1,
      "repeated local-request evidence should keep one representative message",
    );
    assert.match(
      summary,
      /\| \/unknown\.html \| FAIL \| none observed \| NETWORK: new browser diagnostic \\| preserve this \|/,
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
      "--browser=chromium",
      `--report=${reportPath}`,
    ]);
    assert.equal(result.status, 0, result.output);
    assert.match(result.output, /Browser engine: chromium/);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "PASS", JSON.stringify(report, null, 2));
    assert.equal(report.mode, "external-health");
    assert.equal(report.browser.engine, "chromium");
    assert.match(report.browser.version, /\S/);
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

test("rejects an unsupported external-health browser before launch", async () => {
  const result = await runCspQaCommand([
    "--external-health",
    "--paths=/external-healthy-only.html",
    "--browser=phantom",
  ]);
  assert.equal(result.status, 1, result.output);
  assert.match(result.output, /Invalid --browser=phantom/);
  assert.doesNotMatch(result.output, /Browser engine:/);
});

test("rejects empty entries in explicit external-health route lists before browser launch", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-empty-route-entry-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQaCommand([
      "--external-health",
      "--paths=/one,,/two",
      `--report=${reportPath}`,
    ]);
    assert.equal(result.status, 1, result.output);
    assert.match(result.output, /--paths must not contain empty route entries/);
    assert.doesNotMatch(result.output, /Browser engine:|External health:/);
    assert.equal(existsSync(reportPath), false);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("rejects query strings and fragments in explicit routes before browser launch", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-invalid-route-url-parts-"));
  const invalidRoutes = [
    {
      route: "/external-healthy-only.html?cache-buster=1",
      diagnostic: /Invalid --paths route: query strings are not allowed:/,
    },
    {
      route: "/external-healthy-only.html#section",
      diagnostic: /Invalid --paths route: fragments are not allowed:/,
    },
    {
      route: "/external-healthy-only.html?",
      diagnostic: /Invalid --paths route: query strings are not allowed:/,
    },
    {
      route: "/external-healthy-only.html#",
      diagnostic: /Invalid --paths route: fragments are not allowed:/,
    },
  ];
  try {
    for (const [index, { route, diagnostic }] of invalidRoutes.entries()) {
      const reportPath = join(reportDirectory, `report-${index}.json`);
      const result = await runCspQaCommand([
        "--external-health",
        `--paths=${route}`,
        `--report=${reportPath}`,
      ]);
      assert.equal(result.status, 1, `route=${route}\n${result.output}`);
      assert.match(result.output, diagnostic, `route=${route}\n${result.output}`);
      assert.doesNotMatch(result.output, /Browser engine:|External health:/);
      assert.equal(existsSync(reportPath), false, `invalid route=${route}`);
    }
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("rejects non-Chromium selection outside external-health", async () => {
  const result = await runCspQaCommand([
    "--paths=/external-csp-blocked.html",
    "--browser=firefox",
  ]);
  assert.equal(result.status, 1, result.output);
  assert.match(result.output, /--browser=firefox is only supported with --external-health/);
  assert.doesNotMatch(result.output, /Browser engine:/);
});

test("retains successful shared dependency evidence for two healthy routes", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-healthy-shared-routes-"));
  const reportPath = join(reportDirectory, "report.json");
  const routes = [
    "/external-healthy-only.html",
    "/external-healthy-shared.html",
  ];
  const evidenceDirectory = process.env.CSP_TASK386_EVIDENCE_DIR;

  try {
    const observationStart = externalFixtureObservations.length;
    const result = await runCspQa(routes.join(","), [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    const fixtureRequests = externalFixtureObservations.slice(observationStart);
    const reportText = await readFile(reportPath, "utf8");

    if (evidenceDirectory) {
      await writeFile(
        join(evidenceDirectory, "healthy-two-routes-report.json"),
        reportText,
      );
      await writeFile(
        join(evidenceDirectory, "healthy-two-routes-fixture-observations.json"),
        `${JSON.stringify({
          inputRoutes: routes,
          exitCode: result.status,
          requests: fixtureRequests,
        }, null, 2)}\n`,
      );
    }

    const report = JSON.parse(reportText);
    assert.equal(result.status, 0, result.output);
    assert.equal(report.status, "PASS", JSON.stringify(report, null, 2));
    assert.equal(report.mode, "external-health");
    assert.deepEqual(report.routes, routes);
    assert.equal(report.summary.routes, 2);
    assert.equal(report.summary.dependencies, 1);
    assert.equal(report.summary.available, 1);
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.failureEvents, 0);
    assert.equal(report.summary.localFailures, 0);
    assert.equal(report.summary.cspDiagnostics, 0);
    assert.equal(report.summary.cspEvidence, 0);
    assert.equal(report.summary.timeouts, 0);
    assert.equal(report.summary.budgetExceeded, false);
    assert.equal(report.summary.routesCutShortByBudget, 0);
    assert.equal(report.summary.routesSkippedByBudget, 0);
    assert.deepEqual(report.externalOutages, []);
    assert.deepEqual(report.localFailures, []);
    assert.deepEqual(report.cspDiagnostics, []);
    assert.deepEqual(report.cspEvidence, []);
    assert.deepEqual(report.timeouts, []);
    assert.equal(report.timeBudget.exceeded, false);
    assert.deepEqual(report.timeBudget.routesCutShort, []);
    assert.deepEqual(report.timeBudget.routesSkipped, []);
    assertExternalFailureReportContract(report);

    assert.equal(report.dependencies.length, 1);
    const [healthy] = report.dependencies;
    assert.ok(healthy.url.endsWith("/healthy.png"), JSON.stringify(report, null, 2));
    assert.equal(healthy.state, "available");
    assert.deepEqual(healthy.routes, routes.slice().sort());
    assert.equal(healthy.requestCount, 2);
    assert.deepEqual(
      fixtureRequests.map(({ path, method, status }) => ({ path, method, status })),
      [
        { path: "/healthy.png", method: "GET", status: 200 },
        { path: "/healthy.png", method: "GET", status: 200 },
      ],
    );
    assert.equal(
      healthy.requestCount,
      fixtureRequests.length,
      `merged request count versus local server observations: ${JSON.stringify({
        requestCount: healthy.requestCount,
        fixtureRequests,
      })}`,
    );
    assert.equal(healthy.responses.length, fixtureRequests.length);
    assert.deepEqual(
      healthy.responses.map(({ status }) => status),
      fixtureRequests.map(({ status }) => status),
    );
    for (const response of healthy.responses) {
      assert.deepEqual(Object.keys(response).sort(), ["route", "status", "statusText"]);
      assert.ok(routes.includes(response.route));
      assert.equal(response.status, 200);
      assert.equal(typeof response.statusText, "string");
      assert.ok(response.statusText.length > 0);
    }
    assert.deepEqual(healthy.failures, []);
    assert.deepEqual(healthy.timeouts, []);
    assert.deepEqual(healthy.cspEvidence, []);

    const expectedOutcomeRoutes = routes.slice().sort();
    assert.deepEqual(
      healthy.routeOutcomes.map(({ route }) => route),
      expectedOutcomeRoutes,
      "each distinct healthy route must retain its own outcome",
    );
    for (const routeOutcome of healthy.routeOutcomes) {
      assert.deepEqual(
        Object.keys(routeOutcome).sort(),
        ["cspBlocked", "cspEvidence", "failures", "responses", "route", "state", "timeouts"],
      );
      assert.equal(routeOutcome.state, "available", routeOutcome.route);
      assert.equal(routeOutcome.cspBlocked, false, routeOutcome.route);
      assert.deepEqual(routeOutcome.failures, [], routeOutcome.route);
      assert.deepEqual(routeOutcome.timeouts, [], routeOutcome.route);
      assert.deepEqual(routeOutcome.cspEvidence, [], routeOutcome.route);
      assert.equal(
        routeOutcome.responses.length,
        1,
        `route ${routeOutcome.route} must retain its single HTTP response`,
      );
      const [response] = routeOutcome.responses;
      assert.deepEqual(Object.keys(response).sort(), ["route", "status", "statusText"]);
      assert.equal(response.route, routeOutcome.route);
      assert.equal(response.status, 200, routeOutcome.route);
      assert.equal(typeof response.statusText, "string", routeOutcome.route);
      assert.ok(response.statusText.length > 0, routeOutcome.route);
    }
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("treats shared HTTP 204 responses as available on both routes", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-no-content-shared-routes-"));
  const reportPath = join(reportDirectory, "report.json");
  const routes = [
    "/external-no-content-one.html",
    "/external-no-content-two.html",
  ];

  try {
    const observationStart = externalFixtureObservations.length;
    const result = await runCspQa(routes.join(","), [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    const fixtureRequests = externalFixtureObservations.slice(observationStart);
    const report = JSON.parse(await readFile(reportPath, "utf8"));

    assert.equal(result.status, 0, result.output);
    assert.equal(report.status, "PASS", JSON.stringify(report, null, 2));
    assert.equal(report.mode, "external-health");
    assert.deepEqual(report.routes, routes);
    assert.equal(report.summary.routes, 2);
    assert.equal(report.summary.dependencies, 1);
    assert.equal(report.summary.available, 1);
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.failureEvents, 0);
    assert.equal(report.summary.localFailures, 0);
    assert.equal(report.summary.cspDiagnostics, 0);
    assert.equal(report.summary.cspEvidence, 0);
    assert.equal(report.summary.timeouts, 0);
    assert.deepEqual(report.externalOutages, []);
    assert.deepEqual(report.localFailures, []);
    assert.deepEqual(report.cspDiagnostics, []);
    assert.deepEqual(report.cspEvidence, []);
    assert.deepEqual(report.timeouts, []);
    assertExternalFailureReportContract(report);

    assert.deepEqual(
      fixtureRequests.map(({ path, method, status }) => ({ path, method, status })),
      [
        { path: "/no-content.json", method: "GET", status: 204 },
        { path: "/no-content.json", method: "GET", status: 204 },
      ],
    );
    assert.equal(report.dependencies.length, 1);
    const [dependency] = report.dependencies;
    assert.ok(dependency.url.endsWith("/no-content.json"));
    assert.equal(dependency.state, "available");
    assert.deepEqual(dependency.routes, routes.slice().sort());
    assert.equal(dependency.requestCount, 2);
    assert.deepEqual(
      dependency.responses.map(({ status }) => status),
      [204, 204],
    );
    assert.deepEqual(dependency.failures, []);
    assert.deepEqual(dependency.timeouts, []);
    assert.deepEqual(dependency.cspEvidence, []);

    assert.deepEqual(
      dependency.routeOutcomes.map(({ route }) => route),
      routes.slice().sort(),
    );
    for (const routeOutcome of dependency.routeOutcomes) {
      assert.deepEqual(
        Object.keys(routeOutcome).sort(),
        ["cspBlocked", "cspEvidence", "failures", "responses", "route", "state", "timeouts"],
      );
      assert.equal(routeOutcome.state, "available", routeOutcome.route);
      assert.equal(routeOutcome.cspBlocked, false, routeOutcome.route);
      assert.deepEqual(routeOutcome.failures, [], routeOutcome.route);
      assert.deepEqual(routeOutcome.timeouts, [], routeOutcome.route);
      assert.deepEqual(routeOutcome.cspEvidence, [], routeOutcome.route);
      assert.equal(routeOutcome.responses.length, 1, routeOutcome.route);
      assert.deepEqual(Object.keys(routeOutcome.responses[0]).sort(), [
        "route",
        "status",
        "statusText",
      ]);
      assert.equal(routeOutcome.responses[0].route, routeOutcome.route);
      assert.equal(routeOutcome.responses[0].status, 204, routeOutcome.route);
    }
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("retains each route's successful redirect chain without creating outages or duplicate outcomes", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-healthy-redirect-routes-"));
  const reportPath = join(reportDirectory, "report.json");
  const routes = [
    "/external-redirect-healthy-one.html",
    "/external-redirect-healthy-two.html",
  ];

  try {
    const observationStart = externalFixtureObservations.length;
    const result = await runCspQa(routes.join(","), [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    const fixtureRequests = externalFixtureObservations.slice(observationStart);
    const report = JSON.parse(await readFile(reportPath, "utf8"));

    assert.equal(result.status, 0, result.output);
    assert.equal(report.status, "PASS", JSON.stringify(report, null, 2));
    assert.deepEqual(report.routes, routes);
    assert.equal(report.summary.routes, routes.length);
    assert.equal(report.summary.dependencies, 2);
    assert.equal(report.summary.available, 2);
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.failureEvents, 0);
    assert.deepEqual(report.externalOutages, []);
    assert.deepEqual(
      fixtureRequests.map(({ path, method, status }) => ({ path, method, status }))
        .sort((left, right) => left.path.localeCompare(right.path)),
      [
        { path: "/healthy.png", method: "GET", status: 200 },
        { path: "/healthy.png", method: "GET", status: 200 },
        { path: "/redirect.png", method: "GET", status: 302 },
        { path: "/redirect.png", method: "GET", status: 302 },
      ],
    );

    const redirect = report.dependencies.find(({ url }) => url.endsWith("/redirect.png"));
    const finalResource = report.dependencies.find(({ url }) => url.endsWith("/healthy.png"));
    assert.ok(redirect, JSON.stringify(report, null, 2));
    assert.ok(finalResource, JSON.stringify(report, null, 2));
    for (const dependency of [redirect, finalResource]) {
      assert.equal(dependency.state, "available", dependency.url);
      assert.deepEqual(dependency.routes, routes.slice().sort(), dependency.url);
      assert.equal(dependency.requestCount, routes.length, dependency.url);
      assert.deepEqual(dependency.routeOutcomes.map(({ route }) => route), routes.slice().sort());
      assert.equal(
        new Set(dependency.routeOutcomes.map(({ route }) => route)).size,
        routes.length,
        `each route should have exactly one outcome for ${dependency.url}`,
      );
      for (const routeOutcome of dependency.routeOutcomes) {
        assert.equal(routeOutcome.state, "available", `${dependency.url}: ${routeOutcome.route}`);
        assert.deepEqual(routeOutcome.responses.map(({ status }) => status), [
          dependency === redirect ? 302 : 200,
        ]);
        assert.deepEqual(
          routeOutcome.responses.map(({ route }) => route),
          [routeOutcome.route],
        );
        assert.deepEqual(routeOutcome.failures, []);
        assert.deepEqual(routeOutcome.timeouts, []);
      }
    }
    assert.deepEqual(redirect.responses.map(({ status }) => status), [302, 302]);
    assert.deepEqual(finalResource.responses.map(({ status }) => status), [200, 200]);
    assert.deepEqual(redirect.failures, []);
    assert.deepEqual(finalResource.failures, []);
    assertExternalFailureReportContract(report);
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("deduplicates repeated route input without inflating dependency request counts", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-duplicate-route-counts-"));
  const singleRoute = "/external-healthy-only.html";
  const duplicateRoute = "/external-health.html";
  const duplicateInput = [duplicateRoute, duplicateRoute].join(",");
  const singleReportPath = join(reportDirectory, "single-route.json");
  const duplicateReportPath = join(reportDirectory, "duplicate-route.json");
  const evidenceDirectory = process.env.CSP_TASK387_EVIDENCE_DIR;

  try {
    const singleObservationStart = externalFixtureObservations.length;
    const singleResult = await runCspQa(singleRoute, [
      "--external-health",
      `--report=${singleReportPath}`,
    ]);
    assert.equal(singleResult.status, 0, singleResult.output);
    assert.match(singleResult.output, /External health:/, singleResult.output);
    const singleFixtureRequests = externalFixtureObservations
      .slice(singleObservationStart);
    const singleReport = await readExternalHealthReport(
      singleReportPath,
      "single-route-report.json",
    );

    const duplicateObservationStart = externalFixtureObservations.length;
    const duplicateResult = await runCspQa(duplicateInput, [
      "--external-health",
      `--report=${duplicateReportPath}`,
    ]);
    assert.notEqual(duplicateResult.status, 0, duplicateResult.output);
    assert.match(duplicateResult.output, /External health:/, duplicateResult.output);
    const duplicateFixtureRequests = externalFixtureObservations
      .slice(duplicateObservationStart);
    const duplicateReport = await readExternalHealthReport(
      duplicateReportPath,
      "duplicate-route-report.json",
    );

    if (evidenceDirectory) {
      await writeFile(
        join(evidenceDirectory, "fixture-observations.json"),
        `${JSON.stringify({
          singleRouteControl: {
            input: singleRoute,
            exitCode: singleResult.status,
            requests: singleFixtureRequests,
          },
          duplicateRouteInput: {
            input: duplicateInput,
            exitCode: duplicateResult.status,
            requests: duplicateFixtureRequests,
          },
        }, null, 2)}\n`,
      );
    }

    assert.equal(singleReport.status, "PASS", JSON.stringify(singleReport, null, 2));
    assert.deepEqual(singleReport.routes, [singleRoute]);
    assert.equal(singleReport.summary.routes, 1);
    assert.equal(singleReport.summary.failureEvents, 0);
    assert.equal(singleReport.summary.externalOutages, 0);
    assert.equal(singleReport.dependencies.length, 1);

    const [singleHealthy] = singleReport.dependencies;
    assert.equal(singleHealthy.state, "available");
    assert.deepEqual(singleHealthy.routes, [singleRoute]);
    assert.deepEqual(
      singleHealthy.routeOutcomes.map(({ route, state }) => ({ route, state })),
      [{ route: singleRoute, state: "available" }],
    );
    assert.deepEqual(singleHealthy.responses.map(({ status }) => status), [200]);
    assert.deepEqual(singleHealthy.failures, []);
    assert.deepEqual(singleHealthy.routeOutcomes[0].failures, []);

    assert.equal(
      duplicateReport.status,
      "EXTERNAL_OUTAGE",
      JSON.stringify(duplicateReport, null, 2),
    );
    assert.deepEqual(duplicateReport.routes, [duplicateRoute]);
    assert.equal(duplicateReport.summary.routes, 1);
    assert.equal(duplicateReport.summary.dependencies, 2);
    assert.equal(duplicateReport.summary.externalOutages, 1);
    assert.equal(duplicateReport.summary.failureEvents, 0);
    assert.equal(duplicateReport.externalOutages.length, 1);

    const duplicateHealthy = duplicateReport.dependencies.find(
      ({ url }) => url.endsWith("/healthy.png"),
    );
    const duplicateOutage = duplicateReport.dependencies.find(
      ({ url }) => url.endsWith("/outage.png"),
    );
    assert.ok(duplicateHealthy, JSON.stringify(duplicateReport, null, 2));
    assert.ok(duplicateOutage, JSON.stringify(duplicateReport, null, 2));
    for (const dependency of [duplicateHealthy, duplicateOutage]) {
      assert.deepEqual(dependency.routes, [duplicateRoute]);
      assert.deepEqual(
        dependency.routeOutcomes.map(({ route }) => route),
        [duplicateRoute],
      );
      assert.deepEqual(dependency.failures, []);
      assert.deepEqual(dependency.routeOutcomes[0].failures, []);
    }
    assert.equal(duplicateHealthy.state, "available");
    assert.deepEqual(duplicateHealthy.responses.map(({ status }) => status), [200]);
    assert.equal(duplicateOutage.state, "unavailable");
    assert.deepEqual(duplicateOutage.responses.map(({ status }) => status), [503]);
    assert.equal(duplicateReport.externalOutages[0].url, duplicateOutage.url);

    // These complete 200/503 replies avoid aborted-socket retries.
    assert.deepEqual(
      singleFixtureRequests.map(({ path, method, status }) => ({ path, method, status })),
      [{ path: "/healthy.png", method: "GET", status: 200 }],
    );
    assert.deepEqual(
      duplicateFixtureRequests
        .map(({ path, method, status }) => ({ path, method, status }))
        .sort((left, right) => left.path.localeCompare(right.path)),
      [
        { path: "/healthy.png", method: "GET", status: 200 },
        { path: "/outage.png", method: "GET", status: 503 },
      ],
    );

    assert.equal(
      singleHealthy.requestCount,
      singleFixtureRequests.length,
      `single-route browser count versus local fixture requests: ${JSON.stringify({
        browserRequestCount: singleHealthy.requestCount,
        fixtureRequests: singleFixtureRequests,
      })}`,
    );
    for (const dependency of [duplicateHealthy, duplicateOutage]) {
      const observedRequests = duplicateFixtureRequests.filter(
        ({ path }) => new URL(dependency.url).pathname === path,
      );
      assert.equal(
        dependency.requestCount,
        observedRequests.length,
        `duplicate-route browser count versus local fixture requests: ${JSON.stringify({
          dependencyUrl: dependency.url,
          browserRequestCount: dependency.requestCount,
          fixtureRequests: observedRequests,
        })}`,
      );
      assert.equal(dependency.responses.length, observedRequests.length);
      assert.deepEqual(
        dependency.responses.map(({ status }) => status),
        observedRequests.map(({ status }) => status),
      );
    }
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
    assert.doesNotMatch(result.output, /HTTP status(?:es)?:/);

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
  const route = "/external-csp-blocked.html";
  const observationStart = externalFixtureObservations.length;
  observedCspBlockedFixtureResponse = "";
  try {
    const result = await runCspQa(route, [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    const reportText = await readFile(reportPath, "utf8");
    const report = JSON.parse(reportText);
    const fixtureObservations = externalFixtureObservations.slice(observationStart);
    const blockedResourcePaths = [
      "/blocked.png",
      "/blocked.css",
      "/blocked.woff2",
    ];
    const blockedEndpointRequests = fixtureObservations.filter(
      ({ path }) => blockedResourcePaths.includes(path),
    );
    const evidenceDirectory = process.env.CSP_TASK385_EVIDENCE_DIR;
    if (evidenceDirectory) {
      await mkdir(evidenceDirectory, { recursive: true });
      await writeFile(join(evidenceDirectory, "report.json"), reportText);
      await writeFile(
        join(evidenceDirectory, "runner-output.txt"),
        result.output,
      );
      await writeFile(
        join(evidenceDirectory, "runner-status.json"),
        `${JSON.stringify({
          exitCode: result.status,
          signal: result.signal,
        }, null, 2)}\n`,
      );
      await writeFile(
        join(evidenceDirectory, "server-observations.json"),
        `${JSON.stringify({
          externalBaseUrl,
          endpoints: blockedResourcePaths,
          endpointHitCount: blockedEndpointRequests.length,
          endpointRequests: blockedEndpointRequests,
          allNewExternalFixtureObservations: fixtureObservations,
          browserRequestCounts: Object.fromEntries(blockedResourcePaths.map((path) => [
            path,
            report.dependencies.find(({ url }) => url.endsWith(path))?.requestCount ?? null,
          ])),
        }, null, 2)}\n`,
      );
    }

    const expectedDependencies = [
      {
        path: "/blocked.png",
        request: `src="${externalBaseUrl}/blocked.png?fixture=synthetic-csp-case"`,
        effectiveDirective: "img-src",
        violatedDirective: "img-src",
      },
      {
        path: "/blocked.css",
        request: `href="${externalBaseUrl}/blocked.css?fixture=synthetic-csp-stylesheet"`,
        effectiveDirective: "style-src-elem",
        violatedDirective: "style-src-elem",
      },
      {
        path: "/blocked.woff2",
        request:
          `url("${externalBaseUrl}/blocked.woff2?fixture=synthetic-csp-font")`,
        effectiveDirective: "font-src",
        violatedDirective: "font-src",
      },
    ].map(({ path, request, effectiveDirective, violatedDirective }) => ({
      url: new URL(path, externalBaseUrl).href,
      request,
      effectiveDirective,
      violatedDirective,
    }));
    for (const { request } of expectedDependencies) {
      assert.ok(
        observedCspBlockedFixtureResponse.includes(request),
        `the fixture response must request the blocked resource: ${request}\n` +
          `${observedCspBlockedFixtureResponse}\n${result.output}\n` +
          JSON.stringify(report, null, 2),
      );
    }
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /CSP diagnostics were observed/);
    assert.doesNotMatch(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /Browser engine: chromium/);

    assert.equal(report.mode, "external-health");
    assert.equal(report.status, "CSP_BLOCKED");
    assert.deepEqual(report.routes, [route]);
    assert.equal(report.summary.cspDiagnostics, expectedDependencies.length);
    assert.equal(report.summary.cspEvidence, expectedDependencies.length);
    assert.equal(report.summary.dependencies, expectedDependencies.length);
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.failureEvents, expectedDependencies.length);
    assert.equal(report.summary.localFailures, 0);
    assert.equal(report.summary.timeouts, 0);
    assert.equal(report.summary.budgetExceeded, false);
    assert.equal(report.summary.routesCutShortByBudget, 0);
    assert.equal(report.summary.routesSkippedByBudget, 0);
    assert.deepEqual(report.externalOutages, []);
    assert.deepEqual(report.localFailures, []);
    assert.deepEqual(report.timeouts, []);
    assert.equal(report.timeBudget.exceeded, false);
    assert.deepEqual(report.timeBudget.routesCutShort, []);
    assert.deepEqual(report.timeBudget.routesSkipped, []);
    assert.deepEqual(
      report.cspEvidence.map(({ blockedURI }) => blockedURI).sort(),
      expectedDependencies.map(({ url }) => url).sort(),
    );

    for (const expected of expectedDependencies) {
      const blocked = report.dependencies.find(({ url }) => url === expected.url);
      assert.ok(blocked, JSON.stringify(report, null, 2));
      assert.equal(new URL(blocked.url).search, "");
      assert.equal(new URL(blocked.url).hash, "");
      assert.equal(blocked.state, "blocked-by-csp");
      assert.equal(blocked.cspBlocked, true);
      assert.equal(blocked.requestCount, 1);
      assert.deepEqual(blocked.routes, [route]);
      assert.deepEqual(blocked.responses, []);
      assert.equal(blocked.failures.length, 1);
      assert.equal(blocked.failures[0].route, route);
      assert.equal(blocked.failures[0].count, 1);
      assert.deepEqual(blocked.timeouts, []);
      assert.equal(blocked.cspEvidence.length, 1);
      assert.equal(blocked.cspEvidence[0].route, route);
      assert.equal(blocked.cspEvidence[0].blockedURI, blocked.url);
      assert.equal(
        blocked.cspEvidence[0].effectiveDirective,
        expected.effectiveDirective,
      );
      assert.equal(
        blocked.cspEvidence[0].violatedDirective,
        expected.violatedDirective,
      );
      assert.equal(blocked.cspEvidence[0].disposition, "enforce");

      assert.equal(blocked.routeOutcomes.length, 1);
      const [routeOutcome] = blocked.routeOutcomes;
      assert.deepEqual(
        Object.keys(routeOutcome).sort(),
        ["cspBlocked", "cspEvidence", "failures", "responses", "route", "state", "timeouts"],
      );
      assert.equal(routeOutcome.route, route);
      assert.equal(routeOutcome.state, "blocked-by-csp");
      assert.equal(routeOutcome.cspBlocked, true);
      assert.deepEqual(routeOutcome.responses, []);
      assert.equal(routeOutcome.failures.length, 1);
      assert.equal(routeOutcome.failures[0].count, 1);
      assert.deepEqual(routeOutcome.timeouts, []);
      assert.equal(routeOutcome.cspEvidence.length, 1);
      assert.equal(
        report.externalOutages.some(({ url }) => url === blocked.url),
        false,
        `CSP-only ${expected.effectiveDirective} dependency must not become an outage`,
      );
    }

    for (const evidence of [
      ...report.cspEvidence,
      ...report.dependencies.flatMap(({ cspEvidence }) => cspEvidence),
      ...report.dependencies.flatMap(({ routeOutcomes }) =>
        routeOutcomes.flatMap(({ cspEvidence }) => cspEvidence)),
    ]) {
      assert.ok(
        expectedDependencies.some(({ url }) => evidence.blockedURI === url),
        `unexpected CSP blocked URI: ${evidence.blockedURI}`,
      );
      for (const field of ["blockedURI", "documentURI", "sourceFile"]) {
        if (!evidence[field]) continue;
        const evidenceUrl = new URL(evidence[field]);
        assert.equal(evidenceUrl.search, "", `${field} must not retain a query`);
        assert.equal(evidenceUrl.hash, "", `${field} must not retain a fragment`);
      }
    }
    assert.deepEqual(blockedEndpointRequests, [], "CSP-blocked requests must not reach the server");
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("keeps CSP attribution separate for different hosts sharing a resource path", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-same-path-hosts-"));
  const reportPath = join(reportDirectory, "report.json");
  const route = "/external-csp-same-path-different-hosts.html";
  const allowedUrl = new URL("/same-path.png", externalBaseUrl).href;
  const blockedUrl = new URL(
    "/same-path.png",
    externalBaseUrl.replace("127.0.0.1", "localhost"),
  ).href;

  try {
    const result = await runCspQa(route, [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    const allowed = report.dependencies.find(({ url }) => url === allowedUrl);
    const blocked = report.dependencies.find(({ url }) => url === blockedUrl);

    assert.equal(report.status, "CSP_BLOCKED", result.output);
    assert.equal(report.summary.dependencies, 2);
    assert.equal(report.summary.cspEvidence, 1);
    assert.equal(report.summary.externalOutages, 0);
    assert.deepEqual(report.externalOutages, []);
    assert.ok(allowed, JSON.stringify(report, null, 2));
    assert.ok(blocked, JSON.stringify(report, null, 2));
    assert.equal(new URL(allowed.url).pathname, "/same-path.png");
    assert.equal(new URL(blocked.url).pathname, "/same-path.png");
    assert.notEqual(new URL(allowed.url).origin, new URL(blocked.url).origin);
    assert.equal(new URL(allowed.url).search, "");
    assert.equal(new URL(blocked.url).search, "");

    assert.equal(allowed.state, "available");
    assert.equal(allowed.cspBlocked, false);
    assert.deepEqual(allowed.cspEvidence, []);
    assert.deepEqual(allowed.failures, []);
    assert.ok(allowed.responses.some(({ status }) => status === 200));

    assert.equal(blocked.state, "blocked-by-csp");
    assert.equal(blocked.cspBlocked, true);
    assert.equal(blocked.responses.length, 0);
    assert.equal(blocked.cspEvidence.length, 1);
    assert.equal(blocked.cspEvidence[0].blockedURI, blocked.url);
    assert.deepEqual(
      report.cspEvidence.map(({ blockedURI }) => blockedURI),
      [blocked.url],
    );
    assert.equal(
      report.externalOutages.some(({ url }) => url === blocked.url),
      false,
    );
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

test("does not count non-network CSP blocks as external dependencies or outages", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-non-network-health-"));
  const reportPath = join(reportDirectory, "report.json");
  try {
    const result = await runCspQa("/external-non-network-csp.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    const report = JSON.parse(await readFile(reportPath, "utf8"));

    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /CSP diagnostics were observed/);
    assert.doesNotMatch(result.output, /EXTERNAL OUTAGE:/);
    assert.equal(report.status, "CSP_BLOCKED");
    assert.equal(report.summary.dependencies, 0);
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.cspEvidence, 0);
    assert.deepEqual(report.dependencies, []);
    assert.deepEqual(report.externalOutages, []);
    assert.deepEqual(report.cspEvidence, []);
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
  const observationStart = externalFixtureObservations.length;
  try {
    const result = await runCspQa(paths, [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    assert.match(result.output, /Browser engine: chromium/);
    assert.match(result.output, /EXTERNAL OUTAGE:/);
    assert.match(result.output, /CSP diagnostics were observed/);

    const reportText = await readFile(reportPath, "utf8");
    const report = JSON.parse(reportText);
    const sharedRequests = externalFixtureObservations
      .slice(observationStart)
      .filter(({ path }) => path === "/shared.png");
    const evidenceDirectory = process.env.CSP_TASK384_EVIDENCE_DIR;
    if (evidenceDirectory) {
      const engineDirectory = join(evidenceDirectory, "chromium");
      await mkdir(engineDirectory, { recursive: true });
      await writeFile(join(engineDirectory, "shared-route-report.json"), reportText);
      await writeFile(
        join(engineDirectory, "shared-route-runner-output.txt"),
        result.output,
      );
      await writeFile(
        join(engineDirectory, "shared-route-runner-status.json"),
        `${JSON.stringify({
          exitCode: result.status,
          signal: result.signal,
        }, null, 2)}\n`,
      );
      await writeFile(
        join(engineDirectory, "shared-route-server-observations.json"),
        `${JSON.stringify({
          selectedEngine: "chromium",
          expectedUserAgentPattern: "Chrome/",
          routes: paths.split(","),
          sharedRequests,
        }, null, 2)}\n`,
      );
    }
    assert.ok(sharedRequests.length >= 1, JSON.stringify(sharedRequests, null, 2));
    for (const request of sharedRequests) {
      assert.equal(request.method, "GET");
      assert.equal(request.status, 503);
      assert.match(request.userAgent || "", /Chrome\//);
    }

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

test("shows every route receiving an HTTP error from a shared dependency", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-shared-http-error-routes-"));
  const reportPath = join(reportDirectory, "report.json");
  const routes = [
    "/external-outage-shared.html",
    "/external-outage-shared-second.html",
  ];
  try {
    const result = await runCspQa(routes.join(","), [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);
    const outageSummary = result.output
      .split("\n")
      .find((line) => line.includes("EXTERNAL OUTAGE:"));
    assert.ok(outageSummary, result.output);
    assert.match(outageSummary, /HTTP error on route\(s\):/);
    assert.match(outageSummary, /HTTP status(?:es)?: 503/);
    for (const route of routes) {
      assert.ok(outageSummary.includes(route), `${route}\n${outageSummary}`);
    }

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.deepEqual(report.routes, routes);
    assert.equal(report.summary.externalOutages, 1);
    assert.equal(report.externalOutages.length, 1);
    const outage = report.externalOutages[0];
    assert.ok(outage.url.endsWith("/shared.png"));
    assert.equal(outage.state, "unavailable");
    assert.deepEqual(outage.routes, routes.slice().sort());
    for (const route of routes) {
      const routeOutcome = outage.routeOutcomes.find(({ route: value }) => value === route);
      assert.ok(routeOutcome, JSON.stringify(outage.routeOutcomes, null, 2));
      assert.equal(routeOutcome.state, "unavailable");
      assert.ok(routeOutcome.responses.some(({ status }) => status === 503));
    }
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

for (const {
  name,
  executablePath,
  available,
  skipReason,
  userAgentPattern,
} of optionalEngineChecks) {
  test(
    `keeps CSP-only and shared HTTP 503 evidence distinct in ${name}`,
    { skip: skipReason },
    async () => {
      assert.ok(
        existsSync(executablePath),
        `${name} executable disappeared after the optional test was registered`,
      );
      const reportDirectory = await mkdtemp(join(tmpdir(), `csp-${name}-health-`));
      const reportPath = join(reportDirectory, "report.json");
      const routePaths = [
        "/external-csp-blocked.html",
        "/external-csp-shared.html",
        "/external-outage-shared.html",
      ];
      const observationStart = externalFixtureObservations.length;
      try {
        const result = await runCspQa(routePaths.join(","), [
          "--external-health",
          `--browser=${name}`,
          `--report=${reportPath}`,
        ]);
        const reportText = await readFile(reportPath, "utf8");
        const report = JSON.parse(reportText);
        const newObservations = externalFixtureObservations.slice(observationStart);
        const blockedResourcePaths = [
          "/blocked.png",
          "/blocked.css",
          "/blocked.woff2",
        ];
        const blockedEndpointRequests = newObservations.filter(
          ({ path }) => blockedResourcePaths.includes(path),
        );
        const sharedRequests = newObservations.filter(
          ({ path }) => path === "/shared.png",
        );
        const evidenceDirectory = process.env.CSP_TASK384_EVIDENCE_DIR;
        if (evidenceDirectory) {
          const engineDirectory = join(evidenceDirectory, name);
          await mkdir(engineDirectory, { recursive: true });
          await writeFile(join(engineDirectory, "report.json"), reportText);
          await writeFile(
            join(engineDirectory, "runner-output.txt"),
            result.output,
          );
          await writeFile(
            join(engineDirectory, "runner-status.json"),
            `${JSON.stringify({
              exitCode: result.status,
              signal: result.signal,
            }, null, 2)}\n`,
          );
          await writeFile(
            join(engineDirectory, "server-observations.json"),
            `${JSON.stringify({
              selectedEngine: name,
              configuredExecutable: executablePath,
              configuredExecutableExists: available,
              expectedUserAgentPattern: userAgentPattern.source,
              routes: routePaths,
              blockedEndpointRequests,
              sharedRequests,
              allNewExternalFixtureObservations: newObservations,
            }, null, 2)}\n`,
          );
        }

        assert.notEqual(result.status, 0, result.output);
        assert.match(result.output, new RegExp(`Browser engine: ${name}`));
        assert.match(result.output, /Browser version: \S/);
        assert.match(result.output, /EXTERNAL OUTAGE:/);
        assert.match(result.output, /CSP diagnostics were observed/);
        assert.equal(report.status, "EXTERNAL_OUTAGE");
        assert.equal(report.browser.engine, name);
        assert.match(report.browser.version, /\S/);
        assert.deepEqual(report.routes, routePaths);
        assert.equal(report.summary.externalOutages, 1);
        assert.equal(report.summary.localFailures, 0);
        assert.equal(report.summary.timeouts, 0);
        assert.equal(report.summary.budgetExceeded, false);
        assert.equal(report.timeBudget.exceeded, false);

        const cspOnlyDependencies = blockedResourcePaths.map((path) => {
          const dependency = report.dependencies.find(({ url }) => url.endsWith(path));
          assert.ok(dependency, `${path}\n${JSON.stringify(report, null, 2)}`);
          return dependency;
        });
        const shared = report.dependencies.find(({ url }) => url.endsWith("/shared.png"));
        assert.ok(shared, JSON.stringify(report, null, 2));
        for (const dependency of [...cspOnlyDependencies, shared]) {
          const normalizedUrl = new URL(dependency.url);
          assert.equal(normalizedUrl.search, "");
          assert.equal(normalizedUrl.hash, "");
        }

        for (const cspOnly of cspOnlyDependencies) {
          assert.equal(cspOnly.state, "blocked-by-csp");
          assert.equal(cspOnly.cspBlocked, true);
          assert.deepEqual(cspOnly.responses, []);
          assert.deepEqual(
            cspOnly.routeOutcomes.map(({ route, state }) => ({ route, state })),
            [{ route: routePaths[0], state: "blocked-by-csp" }],
          );
          assert.ok(
            cspOnly.cspEvidence.some(({ blockedURI }) => blockedURI === cspOnly.url),
            `${name} must retain CSP evidence for ${cspOnly.url}`,
          );
          assert.equal(
            report.externalOutages.some(({ url }) => url === cspOnly.url),
            false,
            `CSP-only dependency ${cspOnly.url} must not appear as an external outage`,
          );
        }

        assert.equal(shared.state, "unavailable");
        assert.equal(shared.cspBlocked, true);
        assert.deepEqual(shared.routes, routePaths.slice(1));
        assert.ok(shared.responses.some(({ status }) => status === 503));
        const sharedCspOutcome = shared.routeOutcomes.find(
          ({ route }) => route === routePaths[1],
        );
        const sharedHttpOutcome = shared.routeOutcomes.find(
          ({ route }) => route === routePaths[2],
        );
        assert.equal(sharedCspOutcome.state, "blocked-by-csp");
        assert.ok(sharedCspOutcome.cspEvidence.some(
          ({ blockedURI }) => blockedURI === shared.url,
        ));
        assert.deepEqual(sharedCspOutcome.responses, []);
        assert.equal(sharedHttpOutcome.state, "unavailable");
        assert.ok(sharedHttpOutcome.responses.some(({ status }) => status === 503));
        assert.deepEqual(sharedHttpOutcome.cspEvidence, []);
        assert.deepEqual(report.externalOutages.map(({ url }) => url), [shared.url]);
        assert.ok(report.externalOutages[0].responses.some(({ status }) => status === 503));

        assert.deepEqual(blockedEndpointRequests, []);
        assert.ok(sharedRequests.length >= 1, JSON.stringify(sharedRequests, null, 2));
        for (const request of sharedRequests) {
          assert.equal(request.method, "GET");
          assert.equal(request.status, 503);
          assert.match(
            request.userAgent || "",
            userAgentPattern,
            `${name} response must come from the selected browser engine`,
          );
        }
      } finally {
        await rm(reportDirectory, { recursive: true, force: true });
      }
    },
  );
}

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

test("keeps timeout evidence when a healthy response arrives within the late-response window", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-late-response-health-"));
  const reportPath = join(reportDirectory, "report.json");
  const observationStart = externalFixtureObservations.length;
  try {
    const result = await runCspQa("/external-late-response.html", [
      "--external-health",
      `--report=${reportPath}`,
    ]);
    assert.notEqual(result.status, 0, result.output);

    const report = JSON.parse(await readFile(reportPath, "utf8"));
    const observations = externalFixtureObservations.slice(observationStart);
    assert.equal(report.status, "EXTERNAL_TIMEOUT");
    assert.equal(report.summary.externalOutages, 0);
    assert.equal(report.summary.timeouts, 1);
    assert.deepEqual(report.timeouts, [{
      route: "/external-late-response.html",
      url: report.timeouts[0].url,
    }]);

    const dependency = report.dependencies.find(
      ({ url }) => url.endsWith("/late-response.png"),
    );
    assert.ok(dependency, JSON.stringify(report, null, 2));
    assert.equal(dependency.state, "available");
    assert.deepEqual(dependency.routes, ["/external-late-response.html"]);
    assert.equal(dependency.requestCount, 1);
    assert.deepEqual(dependency.responses.map(({ status }) => status), [200]);
    assert.deepEqual(dependency.failures, []);
    assert.deepEqual(dependency.timeouts, [{
      route: "/external-late-response.html",
      url: dependency.url,
    }]);
    assert.equal(dependency.routeOutcomes.length, 1);
    assert.equal(dependency.routeOutcomes[0].state, "available");
    assert.deepEqual(
      dependency.routeOutcomes[0].responses.map(({ status }) => status),
      [200],
    );
    assert.deepEqual(dependency.routeOutcomes[0].timeouts, dependency.timeouts);
    assert.deepEqual(observations, [{
      path: "/late-response.png",
      method: "GET",
      status: 200,
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

test("rejects invalid external-health budgets before browser startup or report creation", async () => {
  const reportDirectory = await mkdtemp(join(tmpdir(), "csp-invalid-budget-"));
  const invalidValues = ["not-a-number", "", "0", "-25", "1.5"];
  try {
    for (const value of invalidValues) {
      const reportPath = join(
        reportDirectory,
        `report-${value.replace(/[^a-z0-9]/gi, "_") || "empty"}.json`,
      );
      const result = await runCspQaCommand([
        "--external-health",
        "--paths=/external-healthy-only.html",
        `--external-budget-ms=${value}`,
        `--report=${reportPath}`,
      ]);
      assert.equal(result.status, 1, `value=${JSON.stringify(value)}\n${result.output}`);
      assert.match(
        result.output,
        /--external-budget-ms must be a positive integer number of milliseconds/,
        `value=${JSON.stringify(value)}\n${result.output}`,
      );
      assert.doesNotMatch(result.output, /Browser engine:|External health:/);
      assert.equal(existsSync(reportPath), false, `invalid value=${JSON.stringify(value)}`);
    }
  } finally {
    await rm(reportDirectory, { recursive: true, force: true });
  }
});

// Exercise the actual CLI report and deadline logic with deterministic clocks
// and launch boundaries, without platform-specific fake browser executables.
async function simulateExternalHealth({
  budget = 6500, lateHealthy = true, startup = null,
  pageCloseMs = 0, browserCloseMs = 0,
  routeStatuses = null, lateResponseStatus = 200, browserName = "chromium",
} = {}) {
  const source = await readFile(cspQaScript, "utf8");
  const entry = source.indexOf("\nif (fixtureSummaryArg) {");
  assert.ok(entry > 0, "CSP CLI entry marker missing");
  const declarations = source.slice(0, entry).replace(/^import .*;\r?$/gm, "");
  let now = 0;
  let report;
  let responded = false;
  const logs = [];
  const handlers = {};
  const request = {
    url: () => "https://third.example/late.png", resourceType: () => "image",
  };
  const page = {
    addInitScript: async () => {},
    on: (name, handler) => { handlers[name] = handler; },
    goto: async (url) => {
      handlers.request(request);
      if (routeStatuses) {
        const status = routeStatuses[new URL(url).pathname];
        handlers.response({
          request: () => request, status: () => status,
          statusText: () => status === 200 ? "OK" : "Service Unavailable",
        });
      }
      return { status: () => 200 };
    },
    waitForLoadState: async () => {},
    waitForTimeout: async (ms) => {
      now += ms;
      if (lateHealthy && !responded && now >= 6250) {
        responded = true;
        handlers.response({
          request: () => request,
          status: () => lateResponseStatus,
          statusText: () => lateResponseStatus === 200 ? "OK" : "Service Unavailable",
        });
      }
    },
    evaluate: async () => [],
    close: async () => { now += pageCloseMs; },
  };
  const browserType = {
    launch: async ({ timeout }) => {
      assert.equal(timeout, budget);
      if (startup) {
        if (startup === "timeout") now += timeout;
        const error = new Error(startup === "timeout"
          ? "synthetic launch timeout" : "synthetic missing executable");
        error.name = startup === "timeout" ? "TimeoutError" : "Error";
        throw error;
      }
      return {
        newPage: async () => page,
        version: () => "Synthetic browser 1.2",
        close: async () => { now += browserCloseMs; },
      };
    },
  };
  const isolatedProcess = {
    argv: ["node", cspQaScript, "--external-health",
      "--base-url=https://first.example",
      `--paths=${routeStatuses ? Object.keys(routeStatuses).join(",") : "/only/"}`,
      "--report=memory.json", `--external-budget-ms=${budget}`,
      ...(browserName === "chromium" ? [] : [`--browser=${browserName}`])],
    env: {}, exitCode: 0,
  };
  await runInNewContext(`${declarations}\nrunExternalHealth();`, {
    URL, Date: { now: () => now }, process: isolatedProcess,
    chromium: browserType, firefox: browserType, webkit: browserType,
    console: {
      log: (message) => logs.push(message),
      error: (message) => logs.push(message),
    },
    writeFileSync: (path, content) => {
      assert.equal(path, "memory.json"); report = JSON.parse(content);
    },
    loadFunctionalPaths: () => { throw new Error("explicit fixture paths required"); },
  });
  assert.ok(report, "runner did not emit report");
  return { report, exitCode: isolatedProcess.exitCode, now, logs };
}

test("attributes mixed HTTP responses to the actual failing route", async () => {
  for (const routeStatuses of [
    { "/healthy/": 200, "/outage/": 503 },
    { "/outage/": 503, "/healthy/": 200 },
  ]) {
    const { report, exitCode, logs } = await simulateExternalHealth({
      budget: 20000, routeStatuses,
    });
    assert.equal(exitCode, 1);
    assert.equal(report.status, "EXTERNAL_OUTAGE");
    assert.equal(report.externalOutages.length, 1);
    const [dependency] = report.dependencies;
    assert.deepEqual(dependency.responses.map(({ route, status }) => ({ route, status })),
      Object.entries(routeStatuses).map(([route, status]) => ({ route, status })));
    assert.deepEqual(dependency.routeOutcomes.map(({ route, state, responses }) => ({
      route, state, statuses: responses.map(({ status }) => status),
    })), [
      { route: "/healthy/", state: "available", statuses: [200] },
      { route: "/outage/", state: "unavailable", statuses: [503] },
    ]);
    const diagnostic = logs.find((line) => line.includes("EXTERNAL OUTAGE:"));
    assert.match(diagnostic, /HTTP error on route\(s\): \/outage\//);
    assert.doesNotMatch(diagnostic, /\/healthy\//);
  }
});

test("records the selected browser build without affecting outage classification", async () => {
  const { report, exitCode } = await simulateExternalHealth({
    budget: 20000,
    routeStatuses: { "/healthy/": 200, "/outage/": 503 },
    browserName: "firefox",
  });
  assert.equal(exitCode, 1);
  assert.deepEqual(report.browser, {
    engine: "firefox",
    version: "Synthetic browser 1.2",
  });
  assert.equal(report.status, "EXTERNAL_OUTAGE");
  assert.equal(report.summary.externalOutages, 1);
});

test("reports browser startup timeout without platform executables", async () => {
  const { report, exitCode } = await simulateExternalHealth({ budget: 500, startup: "timeout" });
  assert.equal(exitCode, 1);
  assert.equal(report.status, "TIME_BUDGET_EXCEEDED");
  assert.equal(report.browserStartupFailure.phase, "browser-startup");
  assert.equal(report.browserStartupFailure.kind, "timeout");
  assert.deepEqual(report.browser, { engine: "chromium", version: null });
  assert.equal(report.browserStartupFailure.timeoutMs, 500);
  assert.equal(report.summary.routes, 0);
  assert.equal(report.summary.budgetExceeded, true);
  assert.equal(report.timeBudget.exceeded, true);
  assert.deepEqual(report.timeBudget.routesSkipped, ["/only/"]);
  for (const field of ["dependencies", "externalOutages", "cspDiagnostics", "cspEvidence", "timeouts"]) {
    assert.deepEqual(report[field], [], field);
  }
});

test("distinguishes ordinary browser launch failure from exhausted budget", async () => {
  const { report, exitCode, logs } = await simulateExternalHealth({
    budget: 500,
    startup: "error",
  });
  assert.equal(exitCode, 1);
  assert.equal(report.status, "BROWSER_START_FAILURE");
  assert.deepEqual(report.browserStartupFailure, {
    phase: "browser-startup",
    kind: "launch-error",
    timeoutMs: 500,
    message: "synthetic missing executable",
  });
  assert.equal(report.timeBudget.elapsedMs, 0);
  assert.equal(report.timeBudget.exceeded, false);
  assert.deepEqual(report.timeBudget.routesCutShort, []);
  assert.deepEqual(report.timeBudget.routesSkipped, []);
  assert.equal(report.summary.routes, 0);
  assert.equal(report.summary.budgetExceeded, false);
  assert.equal(report.summary.routesCutShortByBudget, 0);
  assert.equal(report.summary.routesSkippedByBudget, 0);
  assert.match(logs.join("\n"), /BROWSER START FAILURE: synthetic missing executable/);
  assert.doesNotMatch(
    logs.join("\n"),
    /BROWSER START TIMEOUT|EXTERNAL HEALTH TIME BUDGET|routes? checked/i,
  );
});

test("records exhausted budget on the final route after late healthy response", async () => {
  const { report, exitCode } = await simulateExternalHealth();
  assert.equal(exitCode, 1);
  assert.equal(report.status, "TIME_BUDGET_EXCEEDED");
  assert.equal(report.timeBudget.exceeded, true);
  assert.deepEqual(report.timeBudget.routesCutShort, ["/only/"]);
  assert.equal(report.summary.available, 1);
  assert.equal(report.summary.timeouts, 1);
  assert.equal(report.summary.externalOutages, 0);
});

test("retains pending-request outage and budget exhaustion together", async () => {
  const { report, exitCode } = await simulateExternalHealth({ lateHealthy: false });
  assert.equal(exitCode, 1);
  assert.equal(report.timeBudget.exceeded, true);
  assert.deepEqual(report.timeBudget.routesCutShort, ["/only/"]);
  assert.equal(report.summary.externalOutages, 1);
  assert.equal(report.summary.timeouts, 1);
});

test("keeps late healthy response successful when observation fits budget", async () => {
  const { report, exitCode } = await simulateExternalHealth({ budget: 10000 });
  assert.equal(exitCode, 1);
  assert.equal(report.status, "EXTERNAL_TIMEOUT");
  assert.equal(report.timeBudget.exceeded, false);
  assert.equal(report.summary.available, 1);
  assert.equal(report.summary.timeouts, 1);
});

test("keeps a late HTTP 503 as an outage with its original timeout evidence", async () => {
  const { report, exitCode, now } = await simulateExternalHealth({
    budget: 10000,
    lateResponseStatus: 503,
  });
  assert.equal(exitCode, 1);
  assert.equal(report.status, "EXTERNAL_OUTAGE");
  assert.equal(report.summary.externalOutages, 1);
  assert.equal(report.summary.timeouts, 1);
  assert.equal(now, 7000, "the 1s follow-up window should remain bounded");
  assert.deepEqual(report.timeouts, [{
    route: "/only/",
    url: report.dependencies[0].url,
  }]);
  assert.equal(report.externalOutages.length, 1);
  const [dependency] = report.dependencies;
  assert.equal(dependency.state, "unavailable");
  assert.deepEqual(dependency.responses, [{
    route: "/only/",
    status: 503,
    statusText: "Service Unavailable",
  }]);
  assert.deepEqual(dependency.timeouts, report.timeouts);
  assert.deepEqual(dependency.routeOutcomes, [{
    route: "/only/",
    state: "unavailable",
    cspBlocked: false,
    responses: dependency.responses,
    failures: [],
    timeouts: report.timeouts,
    cspEvidence: [],
  }]);
});

test("accounts for page and browser close reaching the deadline", async () => {
  for (const options of [{ pageCloseMs: 1000 }, { browserCloseMs: 1000 }]) {
    const { report, exitCode } = await simulateExternalHealth({ budget: 7500, ...options });
    assert.equal(exitCode, 1);
    assert.equal(report.status, "TIME_BUDGET_EXCEEDED");
    assert.equal(report.timeBudget.exceeded, true);
    if (options.pageCloseMs) assert.deepEqual(report.timeBudget.routesCutShort, ["/only/"]);
  }
});

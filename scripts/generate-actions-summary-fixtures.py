#!/usr/bin/env python3
"""Generate deterministic report fixtures used by Actions-summary tests."""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIRECTORY = ROOT / "tests" / "fixtures" / "actions-summary"
VERIFY_PATH = ROOT / "scripts" / "verify-live-edge.py"

VERIFY_SPEC = importlib.util.spec_from_file_location("verify_live_edge", VERIFY_PATH)
if VERIFY_SPEC is None or VERIFY_SPEC.loader is None:
    raise RuntimeError("could not load scripts/verify-live-edge.py")
VERIFY = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFY)


RUN_AT = "2026-09-08T00:00:00+00:00"
BASE = "https://fixture.example"
FIXTURE_TIMEOUT = 10.0


SCENARIOS: dict[str, dict[str, Any]] = {
    "live-edge-pass.json": {
        "hosting": "strict",
        "expected_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "checks": [
            {
                "check": "release manifest",
                "status": "PASS",
                "evidence": "validated commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
            {
                "check": "route /",
                "status": "PASS",
                "evidence": "HTTP 200; text/html; charset=utf-8",
            },
            {
                "check": "route / security header x-frame-options",
                "status": "PASS",
                "evidence": "SAMEORIGIN",
            },
        ],
    },
    "live-edge-pages-blocked.json": {
        "hosting": "github-pages",
        "expected_commit": None,
        "checks": [
            {
                "check": "route /",
                "status": "PASS",
                "evidence": "HTTP 200; text/html; charset=utf-8",
            },
            {
                "check": "route / cache policy",
                "status": "BLOCKED",
                "evidence": "GitHub Pages serves this response but does not apply repository _headers; configure the custom edge proxy before treating this policy as enforced",
            },
            {
                "check": "route / security header x-frame-options",
                "status": "BLOCKED",
                "evidence": "GitHub Pages serves this response but does not apply repository _headers; configure the custom edge proxy before treating this policy as enforced",
            },
        ],
    },
    "live-edge-failure.json": {
        "hosting": "strict",
        "expected_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "checks": [
            {
                "check": "release manifest",
                "status": "FAIL",
                "evidence": "expected validated commit bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb, received 'cccccccccccccccccccccccccccccccccccccccc'",
            },
            {
                "check": "route / security header x-frame-options",
                "status": "FAIL",
                "evidence": "expected 'SAMEORIGIN', received 'ALLOWALL'",
            },
            {
                "check": "route / cache policy",
                "status": "BLOCKED",
                "evidence": "GitHub Pages serves this response but does not apply repository _headers; configure the custom edge proxy before treating this policy as enforced",
            },
        ],
    },
}

EXTERNAL_ROUTES = ["/", "/about/", "/contact/"]
EXTERNAL_SCENARIOS: dict[str, dict[str, Any]] = {
    "external-runtime-pass.json": {
        "dependencies": [
            {"url": "https://cdn.example/site.css", "route": "/", "state": "available"},
            {"url": "https://images.example/hero.webp", "route": "/", "state": "available"},
        ],
    },
    "external-runtime-degraded.json": {
        "dependencies": [
            {"url": "https://cdn.example/site.css", "route": "/", "state": "available"},
            {
                "url": "https://images.example/hero.webp",
                "route": "/",
                "state": "unavailable",
                "errorText": "net::ERR_NAME_NOT_RESOLVED",
            },
        ],
    },
    "external-runtime-local-failure.json": {
        "dependencies": [
            {"url": "https://cdn.example/site.css", "route": "/", "state": "available"},
            {"url": "https://images.example/hero.webp", "route": "/", "state": "available"},
        ],
        "localFailures": [
            {"path": "/about/", "error": "local HTTP error: 500 https://fixture.example/about/"},
        ],
    },
    "external-runtime-mixed-failure.json": {
        "dependencies": [
            {"url": "https://cdn.example/site.css", "route": "/", "state": "available"},
            {"url": "https://images.example/hero.webp", "route": "/", "state": "available"},
            {
                "url": "https://fonts.example/site.woff2",
                "route": "/about/",
                "state": "unavailable",
                "errorText": "net::ERR_CONNECTION_RESET",
            },
            {
                "url": "https://video.example/embed.js",
                "route": "/contact/",
                "state": "unavailable",
                "errorText": "net::ERR_TIMED_OUT",
            },
        ],
        "localFailures": [
            {"path": "/about/", "error": "local HTTP error: 500 https://fixture.example/about/"},
        ],
        "cspDiagnostics": [
            {"path": "/contact/", "message": "CSP: refused to load an embedded resource"},
        ],
    },
}


def external_dependency_for(scenario: dict[str, Any]) -> dict[str, Any]:
    url = scenario["url"]
    route = scenario["route"]
    state = scenario["state"]
    parsed_url = urlsplit(url)
    extension = Path(parsed_url.path).suffix.lower()
    resource_type = {
        ".css": "stylesheet",
        ".js": "script",
        ".woff": "font",
        ".woff2": "font",
        ".ttf": "font",
    }.get(extension, "image")
    responses = (
        [{"status": 200, "statusText": "OK"}]
        if state == "available"
        else []
    )
    failures = (
        [{"route": route, "errorText": scenario["errorText"], "count": 1}]
        if state == "unavailable"
        else []
    )
    outcome = {
        "route": route,
        "state": state,
        "cspBlocked": False,
        "responses": responses,
        "failures": failures,
        "timeouts": [],
        "cspEvidence": [],
    }
    return {
        "url": url,
        "origin": f"{parsed_url.scheme}://{parsed_url.netloc}",
        "routes": [route],
        "routeOutcomes": [outcome],
        "resourceTypes": [resource_type],
        "requestCount": 1,
        "responses": responses,
        "failures": failures,
        "timeouts": [],
        "cspEvidence": [],
        "cspBlocked": False,
        "state": state,
    }


def external_report_for(scenario: dict[str, Any]) -> dict[str, Any]:
    dependencies = [
        external_dependency_for(dependency)
        for dependency in scenario["dependencies"]
    ]
    external_outages = [
        dependency
        for dependency in dependencies
        if dependency["state"] in {"unavailable", "no-response"}
    ]
    local_failures = scenario.get("localFailures", [])
    csp_diagnostics = scenario.get("cspDiagnostics", [])
    csp_evidence: list[dict[str, Any]] = []
    timeouts: list[dict[str, Any]] = []
    time_budget = {
        "limitMs": 30000,
        "elapsedMs": 1250,
        "exceeded": False,
        "routesCutShort": [],
        "routesSkipped": [],
    }
    if external_outages:
        status = "EXTERNAL_OUTAGE"
    elif csp_diagnostics or csp_evidence:
        status = "CSP_BLOCKED"
    elif local_failures:
        status = "LOCAL_FAILURE"
    elif time_budget["exceeded"]:
        status = "TIME_BUDGET_EXCEEDED"
    else:
        status = "PASS"
    return {
        "version": 1,
        "mode": "external-health",
        "baseUrl": "https://fixture.example",
        "routes": EXTERNAL_ROUTES,
        "dependencies": dependencies,
        "externalOutages": external_outages,
        "cspDiagnostics": csp_diagnostics,
        "cspEvidence": csp_evidence,
        "timeouts": timeouts,
        "localFailures": local_failures,
        "timeBudget": time_budget,
        "summary": {
            "routes": len(EXTERNAL_ROUTES),
            "dependencies": len(dependencies),
            "available": sum(
                dependency["state"] == "available" for dependency in dependencies
            ),
            "externalOutages": len(external_outages),
            "failureEvents": sum(
                failure.get("count", 1)
                for dependency in dependencies
                for failure in dependency["failures"]
            ),
            "cspDiagnostics": len(csp_diagnostics),
            "cspEvidence": len(csp_evidence),
            "timeouts": len(timeouts),
            "localFailures": len(local_failures),
            "budgetExceeded": time_budget["exceeded"],
            "routesCutShortByBudget": len(time_budget["routesCutShort"]),
            "routesSkippedByBudget": len(time_budget["routesSkipped"]),
        },
        "status": status,
    }


def report_for(scenario: dict[str, Any]) -> dict[str, Any]:
    checks = scenario["checks"]
    failures = sum(item["status"] == "FAIL" for item in checks)
    blocked = sum(item["status"] == "BLOCKED" for item in checks)
    warnings = sum(item["status"] == "WARN" for item in checks)
    status = "FAILED" if failures else ("PARTIAL" if blocked or warnings else "PASS")
    report = {
        "verifier": "verify-live-edge.py",
        "run_at": RUN_AT,
        "base": BASE,
        "timeout_seconds": FIXTURE_TIMEOUT,
        "hosting": scenario["hosting"],
        "expected_commit": scenario["expected_commit"],
        "status": status,
        "summary": {
            "checks": len(checks),
            "failures": failures,
            "blocked": blocked,
            "warnings": warnings,
        },
        "checks": checks,
    }
    VERIFY.validate_report_shape(report)
    return report


def rendered_fixtures() -> dict[str, str]:
    live_edge = {
        name: json.dumps(report_for(scenario), indent=2) + "\n"
        for name, scenario in SCENARIOS.items()
    }
    external_runtime = {
        name: json.dumps(external_report_for(scenario), indent=2) + "\n"
        for name, scenario in EXTERNAL_SCENARIOS.items()
    }
    return {**live_edge, **external_runtime}


def sync_fixtures(output_directory: Path, *, write: bool) -> list[str]:
    expected = rendered_fixtures()
    problems: list[str] = []
    if write:
        output_directory.mkdir(parents=True, exist_ok=True)

    for name, content in expected.items():
        path = output_directory / name
        if write:
            path.write_text(content, encoding="utf-8")
        elif not path.is_file():
            problems.append(f"missing generated fixture: {path}")
        else:
            actual = path.read_text(encoding="utf-8")
            if actual != content:
                diff = "".join(
                    difflib.unified_diff(
                        content.splitlines(keepends=True),
                        actual.splitlines(keepends=True),
                        fromfile=f"expected/{name}",
                        tofile=f"actual/{name}",
                    )
                )
                problems.append(
                    f"generated fixture is stale: {path}\n{diff.rstrip()}"
                )

    if not write:
        expected_names = set(expected)
        generated_fixtures = [
            path
            for pattern in ("live-edge-*.json", "external-runtime-*.json")
            for path in output_directory.glob(pattern)
        ]
        for path in sorted(generated_fixtures):
            if path.name not in expected_names:
                problems.append(f"unexpected generated fixture: {path}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail when committed fixtures differ")
    mode.add_argument("--write", action="store_true", help="write the deterministic fixtures")
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="fixture directory (default: tests/fixtures/actions-summary)",
    )
    args = parser.parse_args()
    problems = sync_fixtures(args.output_directory, write=args.write)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        return 1
    print(
        f"{'wrote' if args.write else 'checked'} "
        f"{len(SCENARIOS) + len(EXTERNAL_SCENARIOS)} deterministic "
        "Actions-summary fixtures in "
        f"{args.output_directory}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
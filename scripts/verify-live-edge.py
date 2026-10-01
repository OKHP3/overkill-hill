#!/usr/bin/env python3
"""Read-only post-deploy verifier for a static site live edge.

The base URL is intentionally required.  This helper never publishes, mutates
the repository, or uses credentials. It checks the repository's sitemap,
representative noindex boundaries, security headers, release-manifest binding,
generated search index, and content-hashed CSS/JS responses.

Usage:
    python3 scripts/verify-live-edge.py --base https://example.com
    python3 scripts/verify-live-edge.py --base https://example.com \
        --expected-commit "$GITHUB_SHA" \
        --report assets/audit/live-edge-report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "sitemap.xml"
SEARCH_INDEX = ROOT / "assets" / "data" / "search-index.json"
RELEASE_MANIFEST = "/assets/audit/release-manifest.json"
TIMEOUT = 10.0
USER_AGENT = "OKHP3-live-edge-verifier/1.0 (read-only)"
GITHUB_PAGES_POLICY_NOTE = (
    "GitHub Pages serves this response but does not apply repository _headers; "
    "configure the custom edge proxy before treating this policy as enforced"
)
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "SAMEORIGIN",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(), display-capture=(), document-domain=(), encrypted-media=(), fullscreen=(self), gamepad=(), geolocation=(), gyroscope=(), hid=(), idle-detection=(), interest-cohort=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(self), publickey-credentials-get=(), screen-wake-lock=(), serial=(), sync-xhr=(), usb=(), web-share=(self), xr-spatial-tracking=()",
    "strict-transport-security": "max-age=63072000; includeSubDomains; preload",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "origin-agent-cluster": "?1",
}
GITHUB_PAGES_ACCEPTED_LIMITATIONS = {
    "cache-control": "GitHub Pages controls HTML caching at the edge, so this verifier records the observed header but does not treat the published value as enforceable here",
    "content-security-policy": "GitHub Pages cannot apply repository _headers; absence is recorded as a hosting limitation, and the CSP policy contents are not validated by this live-edge check",
}
HTML_CACHE_RE = re.compile(r"max-age=300\b", re.I)
REVALIDATE_RE = re.compile(r"\bmust-revalidate\b", re.I)
IMMUTABLE_RE = re.compile(r"\bimmutable\b", re.I)
FINGERPRINT_RE = re.compile(r"(?:^|&)v=([0-9a-f]{8})(?:&|$)", re.I)
COMMIT_RE = re.compile(r"[0-9a-f]{40}", re.I)
ASSET_CONTENT_TYPES = {
    ".css": frozenset({"text/css"}),
    ".js": frozenset({"application/javascript", "text/javascript"}),
    ".png": frozenset({"image/png"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".jpeg": frozenset({"image/jpeg"}),
    ".webp": frozenset({"image/webp"}),
    ".gif": frozenset({"image/gif"}),
    ".svg": frozenset({"image/svg+xml"}),
    ".ico": frozenset({"image/x-icon", "image/vnd.microsoft.icon"}),
    ".woff": frozenset({"font/woff"}),
    ".woff2": frozenset({"font/woff2"}),
    ".ttf": frozenset({"font/ttf"}),
    ".otf": frozenset({"font/otf"}),
    ".eot": frozenset({"application/vnd.ms-fontobject"}),
}
FINGERPRINTED_ASSET_SUFFIXES = frozenset({".css", ".js"})
FIRST_PARTY_CONTENT_TYPES = {
    RELEASE_MANIFEST: frozenset({"application/json"}),
    "/sitemap.xml": frozenset({"application/xml", "text/xml"}),
    "/assets/data/search-index.json": frozenset({"application/json"}),
}
HTML_ASSET_RE = re.compile(
    r"""(?<![A-Za-z0-9_:/])(?P<url>/assets/(?:css|js|img|fonts)/[^'"<>\s,?#]+(?:\?[^'"<>\s,]*)?)""",
    re.I,
)
CSS_ASSET_RE = re.compile(
    r"""url\(\s*['"]?(?P<url>/assets/(?:img|fonts)/[^)'"\s,?#]+(?:\?[^)'"\s,]*)?)['"]?\s*\)""",
    re.I,
)
ROBOTS_RE = re.compile(
    r"""<meta\b(?=[^>]*\bname=["']robots["'])(?=[^>]*\bcontent=["']([^"']+)["'])[^>]*>""",
    re.I,
)
LIVE_EDGE_CHECK_STATUSES = frozenset({"PASS", "FAIL", "WARN", "BLOCKED"})
LIVE_EDGE_REPORT_STATUSES = frozenset({"PASS", "PARTIAL", "FAILED"})
LIVE_EDGE_REPORT_FIELDS = (
    "verifier",
    "run_at",
    "base",
    "timeout_seconds",
    "expected_commit",
    "hosting",
    "status",
    "summary",
    "checks",
)
LIVE_EDGE_SUMMARY_FIELDS = ("checks", "failures", "blocked", "warnings")
LIVE_EDGE_CHECK_FIELDS = ("check", "status", "evidence")


def canonical_text_bytes(path: Path) -> bytes:
    """Match GitHub Pages' LF text bytes from Windows CRLF checkouts."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result(check: str, status: str, evidence: str, **extra: Any) -> dict[str, Any]:
    item = {"check": check, "status": status, "evidence": evidence}
    item.update(extra)
    return item


def validate_report_shape(report: Any) -> None:
    """Reject reports that cannot have been emitted by this verifier."""
    if not isinstance(report, dict):
        raise ValueError("live-edge report must be a JSON object")

    missing = [field for field in LIVE_EDGE_REPORT_FIELDS if field not in report]
    if missing:
        raise ValueError(
            "live-edge report is missing required field(s): " + ", ".join(missing)
        )
    if report["verifier"] != "verify-live-edge.py":
        raise ValueError("live-edge report.verifier must be 'verify-live-edge.py'")
    for field in ("run_at", "base"):
        if not isinstance(report[field], str) or not report[field]:
            raise ValueError(f"live-edge report.{field} must be a non-empty string")
    if (
        isinstance(report["timeout_seconds"], bool)
        or not isinstance(report["timeout_seconds"], (int, float))
        or report["timeout_seconds"] <= 0
    ):
        raise ValueError("live-edge report.timeout_seconds must be a positive number")
    if report["expected_commit"] is not None and not isinstance(
        report["expected_commit"], str
    ):
        raise ValueError("live-edge report.expected_commit must be a string or null")
    if (
        not isinstance(report["hosting"], str)
        or report["hosting"] not in {"strict", "github-pages"}
    ):
        raise ValueError(
            "live-edge report.hosting must be 'strict' or 'github-pages'"
        )
    if (
        not isinstance(report["status"], str)
        or report["status"] not in LIVE_EDGE_REPORT_STATUSES
    ):
        raise ValueError(
            "live-edge report.status must be one of "
            + ", ".join(sorted(LIVE_EDGE_REPORT_STATUSES))
        )

    summary = report["summary"]
    if not isinstance(summary, dict):
        raise ValueError("live-edge report.summary must be an object")
    missing = [field for field in LIVE_EDGE_SUMMARY_FIELDS if field not in summary]
    if missing:
        raise ValueError(
            "live-edge report.summary is missing required field(s): "
            + ", ".join(missing)
        )
    for field in LIVE_EDGE_SUMMARY_FIELDS:
        value = summary[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"live-edge report.summary.{field} must be a non-negative integer"
            )

    checks = report["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("live-edge report.checks must be a non-empty array")
    for index, item in enumerate(checks):
        location = f"live-edge report.checks[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{location} must be an object")
        missing = [field for field in LIVE_EDGE_CHECK_FIELDS if field not in item]
        if missing:
            raise ValueError(
                f"{location} is missing required field(s): " + ", ".join(missing)
            )
        if not isinstance(item["check"], str) or not item["check"]:
            raise ValueError(f"{location}.check must be a non-empty string")
        if (
            not isinstance(item["status"], str)
            or item["status"] not in LIVE_EDGE_CHECK_STATUSES
        ):
            raise ValueError(
                f"{location}.status must be one of "
                + ", ".join(sorted(LIVE_EDGE_CHECK_STATUSES))
            )
        if not isinstance(item["evidence"], str):
            raise ValueError(f"{location}.evidence must be a string")

    expected_counts = {
        "checks": len(checks),
        "failures": sum(item["status"] == "FAIL" for item in checks),
        "blocked": sum(item["status"] == "BLOCKED" for item in checks),
        "warnings": sum(item["status"] == "WARN" for item in checks),
    }
    for field, expected in expected_counts.items():
        if summary[field] != expected:
            raise ValueError(
                f"live-edge report.summary.{field} is {summary[field]}, "
                f"expected {expected} from checks"
            )


def transport_status(response: dict[str, Any]) -> str:
    """Keep network/timeout limits distinct from an HTTP deployment failure."""
    return "BLOCKED" if response.get("status") is None else "FAIL"


def check_content_type(
    report: list[dict[str, Any]],
    label: str,
    expected: frozenset[str],
    response: dict[str, Any],
) -> bool:
    """Require an accepted media type for a successful first-party response."""
    if not response.get("ok") or response.get("status") != 200:
        return False

    received = response["headers"].get("content-type", "")
    media_type = received.split(";", 1)[0].strip().lower()
    accepted = ", ".join(sorted(expected))
    status = "PASS" if media_type in expected else "FAIL"
    evidence = (
        f"received {received!r}; accepted: {accepted}"
        if status == "PASS"
        else f"received {received!r}; expected one of: {accepted}"
    )
    report.append(
        result(
            f"{label} content type",
            status,
            evidence,
            content_type=received,
            accepted_content_types=sorted(expected),
        )
    )
    return status == "PASS"


def check_asset_content_type(
    report: list[dict[str, Any]], path: str, response: dict[str, Any]
) -> None:
    """Require a browser-compatible MIME type for each first-party asset."""
    expected = ASSET_CONTENT_TYPES.get(Path(path).suffix.lower())
    if expected is not None:
        check_content_type(report, f"asset {path}", expected, response)


def check_first_party_content_type(
    report: list[dict[str, Any]], path: str, response: dict[str, Any]
) -> bool:
    """Require the declared media type for each first-party structured response."""
    expected = FIRST_PARTY_CONTENT_TYPES.get(path)
    if expected is None:
        return True
    label = {
        RELEASE_MANIFEST: "release manifest",
        "/sitemap.xml": "generated sitemap",
        "/assets/data/search-index.json": "generated search index",
    }[path]
    return check_content_type(report, label, expected, response)


def fetch(base: str, path: str, timeout: float = TIMEOUT) -> dict[str, Any]:
    url = urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            headers = {k.lower(): v.strip() for k, v in response.headers.items()}
            return {
                "ok": True,
                "url": response.geturl(),
                "status": response.status,
                "headers": headers,
                "body": body,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        headers = {}
        body = b""
        status = getattr(exc, "code", None)
        if isinstance(exc, urllib.error.HTTPError):
            headers = {k.lower(): v.strip() for k, v in exc.headers.items()}
            try:
                body = exc.read()
            except OSError:
                pass
        return {
            "ok": False,
            "url": url,
            "status": status,
            "headers": headers,
            "body": body,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

def path_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    return path if path.endswith("/") or path.rsplit("/", 1)[-1].find(".") >= 0 else path + "/"


def load_routes() -> tuple[list[str], str | None]:
    if not SITEMAP.is_file():
        return [], "sitemap.xml is missing"
    try:
        root = ET.fromstring(SITEMAP.read_bytes())
    except (ET.ParseError, OSError) as exc:
        return [], f"sitemap.xml is unreadable: {exc}"
    routes: list[str] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "loc" and node.text:
            routes.append(path_from_url(node.text.strip()))
    duplicate = sorted({route for route in routes if routes.count(route) > 1})
    if not routes:
        return [], "sitemap.xml contains no routes"
    if duplicate:
        return [], f"sitemap.xml contains duplicate routes: {', '.join(duplicate)}"
    return routes, None


def check_headers(
    report: list[dict[str, Any]], label: str, response: dict[str, Any], hosting: str
) -> None:
    if not response.get("ok"):
        return
    headers = response["headers"]
    for name, expected in SECURITY_HEADERS.items():
        value = headers.get(name)
        if not value:
            if hosting == "github-pages":
                report.append(
                    result(
                        f"{label} observed header {name}",
                        "WARN",
                        "absent; "
                        + GITHUB_PAGES_ACCEPTED_LIMITATIONS.get(
                            name,
                            "GitHub Pages may omit repository headers at the edge",
                        ),
                    )
                )
            else:
                report.append(result(f"{label} security header {name}", "FAIL", "header absent"))
        elif expected and value.lower() != expected.lower():
            report.append(
                result(
                    f"{label} security header {name}",
                    "FAIL",
                    f"expected {expected!r}, received {value!r}",
                )
            )
        else:
            check_name = f"{label} observed header {name}" if hosting == "github-pages" else f"{label} security header {name}"
            report.append(result(check_name, "PASS", value))

    enforcing_csp = headers.get("content-security-policy")
    report_only_csp = headers.get("content-security-policy-report-only")
    if enforcing_csp:
        report.append(
            result(
                f"{label} observed enforcing content-security-policy",
                "PASS",
                "header present; policy contents were not validated by this live-edge check",
                value=enforcing_csp,
            )
        )
    else:
        csp_status = "WARN" if hosting == "github-pages" else "FAIL"
        csp_evidence = (
            "absent; " + GITHUB_PAGES_ACCEPTED_LIMITATIONS["content-security-policy"]
            if hosting == "github-pages"
            else "enforcing header absent"
        )
        report.append(
            result(
                f"{label} enforcing content-security-policy",
                csp_status,
                csp_evidence,
            )
        )
    if report_only_csp:
        report.append(
            result(
                f"{label} observed report-only content-security-policy",
                "WARN",
                "report-only header present; it does not enforce the policy",
                value=report_only_csp,
            )
        )


def check_page(
    report: list[dict[str, Any]],
    base: str,
    path: str,
    expected_indexable: bool,
    timeout: float,
    hosting: str,
) -> tuple[dict[str, Any] | None, str]:
    response = fetch(base, path, timeout)
    label = f"route {path}"
    status = response.get("status")
    if not response.get("ok") or status != 200:
        report.append(
            result(label, transport_status(response), response.get("error", f"HTTP {status}"), http_status=status)
        )
        return None, ""
    content_type = response["headers"].get("content-type", "")
    body = response["body"].decode("utf-8", errors="replace")
    if "text/html" not in content_type.lower():
        report.append(
            result(
                label,
                "FAIL",
                f"content-type is {content_type!r}",
                http_status=status,
                response_headers=dict(sorted(response["headers"].items())),
            )
        )
    else:
        report.append(
            result(
                label,
                "PASS",
                f"HTTP 200; {content_type}",
                http_status=status,
                response_headers=dict(sorted(response["headers"].items())),
            )
        )
    robots_match = ROBOTS_RE.search(body)
    robots = robots_match.group(1).lower() if robots_match else ""
    has_noindex = "noindex" in robots
    if has_noindex == expected_indexable:
        wanted = "indexable" if expected_indexable else "noindex"
        report.append(result(f"{label} robots boundary", "FAIL", f"expected {wanted}, received {robots or 'none'}"))
    else:
        wanted = "indexable" if expected_indexable else "noindex"
        report.append(result(f"{label} robots boundary", "PASS", f"{wanted}; {robots or 'no robots meta'}"))
    cache = response["headers"].get("cache-control", "")
    cache_passed = bool(HTML_CACHE_RE.search(cache)) and bool(REVALIDATE_RE.search(cache))
    cache_status = "PASS" if cache_passed else "FAIL"
    if hosting == "github-pages":
        cache_status = "BLOCKED"
    report.append(result(f"{label} cache policy", cache_status,
                         GITHUB_PAGES_POLICY_NOTE if hosting == "github-pages" else (cache or "Cache-Control absent")))
    check_headers(report, label, response, hosting)
    return response, body


def check_hosting_path(
    report: list[dict[str, Any]],
    responses: dict[str, dict[str, Any]],
    hosting: str,
) -> None:
    """Prove that the selected hosting exception is the edge serving the site."""
    if hosting != "github-pages":
        return
    if not responses:
        report.append(result("hosting path", "FAIL", "no successful route response available"))
        return

    route, response = next(iter(responses.items()))
    headers = response.get("headers", {})
    server = headers.get("server", "")
    has_github_marker = bool(
        headers.get("x-github-edge-region")
        or headers.get("x-github-request-id")
        or headers.get("x-fastly-request-id")
    )
    has_cloudflare_marker = bool(headers.get("cf-ray") or headers.get("cf-cache-status"))
    if server.lower() == "github.com" and has_github_marker and not has_cloudflare_marker:
        report.append(
            result(
                "hosting path",
                "PASS",
                f"{route} is served directly by GitHub Pages ({server})",
            )
        )
    else:
        report.append(
            result(
                "hosting path",
                "FAIL",
                "expected direct GitHub Pages markers; "
                f"server={server or 'absent'!r}, "
                f"cloudflare={'present' if has_cloudflare_marker else 'absent'}",
            )
        )


def check_release_manifest(
    report: list[dict[str, Any]],
    base: str,
    expected_commit: str | None,
    timeout: float,
) -> None:
    """Validate the manifest against the checkout or the live artifacts."""
    response = fetch(base, RELEASE_MANIFEST, timeout)
    label = "release manifest"
    if not response.get("ok") or response.get("status") != 200:
        report.append(
            result(
                label,
                transport_status(response),
                response.get("error", f"HTTP {response.get('status')}"),
            )
        )
        return

    if not check_first_party_content_type(report, RELEASE_MANIFEST, response):
        return

    try:
        manifest = json.loads(response["body"])
    except (ValueError, UnicodeDecodeError) as exc:
        report.append(result(label, "FAIL", f"invalid JSON: {exc}"))
        return

    if not isinstance(manifest, dict):
        report.append(result(label, "FAIL", "expected a JSON object"))
        return
    commit = manifest.get("commit")
    artifacts = manifest.get("artifacts")
    if expected_commit and commit != expected_commit:
        report.append(
            result(
                label,
                "FAIL",
                f"expected validated commit {expected_commit}, received {commit!r}",
            )
        )
    elif not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        report.append(result(label, "FAIL", f"malformed deployed commit {commit!r}"))
    elif not isinstance(artifacts, dict):
        report.append(result(label, "FAIL", "artifacts map is missing"))
    else:
        evidence = (
            f"validated commit {commit}"
            if expected_commit
            else f"deployed commit {commit}"
        )
        report.append(result(label, "PASS", evidence))

    expected_artifacts = {
        "/sitemap.xml": SITEMAP,
        "/assets/data/search-index.json": SEARCH_INDEX,
    }
    if not isinstance(artifacts, dict):
        return
    for public_path, local_path in expected_artifacts.items():
        entry = artifacts.get(public_path)
        manifest_hash = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(manifest_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", manifest_hash, re.I
        ):
            report.append(
                result(
                    f"release manifest {public_path}",
                    "FAIL",
                    f"invalid artifact SHA-256 {manifest_hash!r}",
                )
            )
            continue
        if expected_commit:
            target_hash = (
                hashlib.sha256(canonical_text_bytes(local_path)).hexdigest()
                if local_path.is_file()
                else None
            )
            target_description = "validated files"
        else:
            live_artifact = fetch(base, public_path, timeout)
            if not live_artifact.get("ok") or live_artifact.get("status") != 200:
                report.append(
                    result(
                        f"release manifest {public_path}",
                        transport_status(live_artifact),
                        live_artifact.get(
                            "error", f"HTTP {live_artifact.get('status')}"
                        ),
                    )
                )
                continue
            target_hash = hashlib.sha256(live_artifact["body"]).hexdigest()
            target_description = "live artifact"
        if not manifest_hash:
            report.append(
                result(
                    f"release manifest {public_path}",
                    "FAIL",
                    "artifact SHA-256 is missing",
                )
            )
        elif target_hash is None:
            report.append(
                result(
                    f"release manifest {public_path}",
                    "FAIL",
                    f"local artifact missing: {local_path}",
                )
            )
        elif manifest_hash != target_hash:
            report.append(
                result(
                    f"release manifest {public_path}",
                    "FAIL",
                    f"manifest SHA-256 {manifest_hash[:12]} differs from "
                    f"{target_description} {target_hash[:12]}",
                )
            )
        else:
            report.append(
                result(
                    f"release manifest {public_path}",
                    "PASS",
                    f"SHA-256 {manifest_hash[:12]} matches {target_description}",
                )
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Explicit deployed origin, e.g. https://overkillhill.com")
    parser.add_argument("--timeout", type=float, default=TIMEOUT, help=f"Per-request timeout in seconds (default: {TIMEOUT:g})")
    parser.add_argument("--report", type=Path, help="Write the JSON report to this path")
    parser.add_argument(
        "--expected-commit",
        help="Require the deployed release manifest to identify this validated commit",
    )
    parser.add_argument(
        "--hosting",
        choices=("strict", "github-pages"),
        default="strict",
        help="Hosting policy to verify; GitHub Pages cannot apply repository _headers",
    )
    parser.add_argument(
        "--accept-blocked",
        action="store_true",
        help="Return success when only hosting limitations are BLOCKED",
    )
    parser.add_argument("--noindex-route", action="append", default=["/404.html", "/found-ry/"],
                        help="Additional utility/noindex route (repeatable)")
    args = parser.parse_args()
    parsed_base = urllib.parse.urlparse(args.base)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        parser.error("--base must be an explicit http(s) origin")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    report: list[dict[str, Any]] = []
    check_release_manifest(report, args.base, args.expected_commit, args.timeout)
    routes, sitemap_error = load_routes()
    if sitemap_error:
        report.append(result("local sitemap inventory", "FAIL", sitemap_error))
    else:
        report.append(result("local sitemap inventory", "PASS", f"{len(routes)} unique routes"))

    responses: dict[str, dict[str, Any]] = {}
    bodies: dict[str, str] = {}
    for route in routes:
        response, body = check_page(report, args.base, route, True, args.timeout, args.hosting)
        if response:
            responses[route] = response
            bodies[route] = body

    for route in dict.fromkeys(args.noindex_route):
        if route in responses:
            continue
        response, body = check_page(report, args.base, route, False, args.timeout, args.hosting)
        if response:
            responses[route] = response
            bodies[route] = body

    check_hosting_path(report, responses, args.hosting)

    # With an expected commit, compare against the validated checkout. Scheduled
    # monitoring intentionally accepts an older deployed release and relies on
    # the manifest-to-live-byte checks above instead.
    for path, local_path, kind in [
        ("/sitemap.xml", SITEMAP, "sitemap"),
        ("/assets/data/search-index.json", SEARCH_INDEX, "search index"),
    ]:
        response = fetch(args.base, path, args.timeout)
        if not response.get("ok") or response.get("status") != 200:
            report.append(result(f"generated {kind}", transport_status(response),
                                 response.get("error", f"HTTP {response.get('status')}")))
            continue
        check_first_party_content_type(report, path, response)
        remote_hash = hashlib.sha256(response["body"]).hexdigest()
        local_hash = (
            hashlib.sha256(canonical_text_bytes(local_path)).hexdigest()
            if local_path.is_file()
            else None
        )
        if args.expected_commit and local_hash is None:
            report.append(
                result(
                    f"generated {kind}",
                    "FAIL",
                    f"local artifact missing: {local_path}",
                    remote_sha256=remote_hash,
                )
            )
        elif args.expected_commit and remote_hash != local_hash:
            report.append(
                result(
                    f"generated {kind}",
                    "FAIL",
                    f"live SHA-256 {remote_hash[:12]} differs from local {local_hash[:12]}",
                    remote_sha256=remote_hash,
                    local_sha256=local_hash,
                )
            )
        else:
            binding = (
                f"SHA-256 {remote_hash[:12]} matches validated files"
                if args.expected_commit
                else f"SHA-256 {remote_hash[:12]} is bound by the live release manifest"
            )
            report.append(
                result(
                    f"generated {kind}",
                    "PASS", f"HTTP 200; {binding}",
                    remote_sha256=remote_hash,
                    **({"local_sha256": local_hash} if args.expected_commit else {}),
                )
            )
        if kind == "search index":
            try:
                parsed = json.loads(response["body"])
                count = parsed.get("count") if isinstance(parsed, dict) else None
                if not isinstance(parsed, dict) or not isinstance(count, int) or count <= 0:
                    report.append(result("search index shape", "FAIL", "expected a JSON object with positive integer count"))
                else:
                    report.append(result("search index shape", "PASS", f"{count} indexed pages"))
            except (ValueError, UnicodeDecodeError) as exc:
                report.append(result("search index shape", "FAIL", f"invalid JSON: {exc}"))
        cache = response["headers"].get("cache-control", "")
        if kind == "search index":
            passed = bool(cache) and not IMMUTABLE_RE.search(cache) and bool(re.search(r"max-age=(?:[0-9]|[1-2][0-9]{1,2}|300)\b", cache, re.I))
            cache_status = "PASS" if passed else "FAIL"
            if args.hosting == "github-pages":
                cache_status = "BLOCKED"
            report.append(result("search index cache policy", cache_status, GITHUB_PAGES_POLICY_NOTE if args.hosting == "github-pages" else (cache or "Cache-Control absent")))
        else:
            cache_status = "PASS" if HTML_CACHE_RE.search(cache) and REVALIDATE_RE.search(cache) else "FAIL"
            if args.hosting == "github-pages":
                cache_status = "BLOCKED"
            report.append(result("sitemap cache policy", cache_status, GITHUB_PAGES_POLICY_NOTE if args.hosting == "github-pages" else (cache or "Cache-Control absent")))
        check_headers(report, f"generated {kind}", response, args.hosting)

    # Check availability and MIME types for discovered first-party assets.
    # CSS/JS require fingerprints; verify hashes and cache policy whenever a
    # discovered asset supplies a fingerprint.
    assets: dict[str, str] = {}
    for body in bodies.values():
        for match in HTML_ASSET_RE.finditer(body):
            assets[match.group("url").split("#", 1)[0]] = match.group("url")
    if not assets:
        report.append(result("first-party assets", "FAIL", "no first-party asset references found in fetched HTML"))

    checked_assets: set[str] = set()
    while pending_assets := sorted(set(assets) - checked_assets):
        for asset_url in pending_assets:
            checked_assets.add(asset_url)
            parsed = urllib.parse.urlparse(asset_url)
            fingerprint = FINGERPRINT_RE.search(parsed.query)
            path = parsed.path
            local_path = ROOT / path.lstrip("/")
            expected_hash = (
                hashlib.sha256(canonical_text_bytes(local_path)).hexdigest()[:8]
                if local_path.is_file()
                else None
            )
            response = fetch(args.base, asset_url, args.timeout)
            if response.get("ok") and response.get("status") == 200:
                check_asset_content_type(report, path, response)
                if Path(path).suffix.lower() == ".css":
                    css_body = response["body"].decode("utf-8", errors="replace")
                    for match in CSS_ASSET_RE.finditer(css_body):
                        discovered_url = match.group("url").split("#", 1)[0]
                        assets[discovered_url] = match.group("url")
            if not fingerprint:
                if Path(path).suffix.lower() in FINGERPRINTED_ASSET_SUFFIXES:
                    report.append(result(f"asset {path}", "FAIL", "missing 8-character ?v= fingerprint"))
                elif not response.get("ok") or response.get("status") != 200:
                    report.append(result(f"asset {path}", transport_status(response),
                                         response.get("error", f"HTTP {response.get('status')}")))
                continue
            if expected_hash and fingerprint.group(1).lower() != expected_hash.lower():
                report.append(result(f"asset {path}", "FAIL", f"URL fingerprint {fingerprint.group(1)} != local {expected_hash}"))
            elif not response.get("ok") or response.get("status") != 200:
                report.append(result(f"asset {path}", transport_status(response),
                                     response.get("error", f"HTTP {response.get('status')}")))
            else:
                remote_hash = hashlib.sha256(
                    response["body"].replace(b"\r\n", b"\n")
                ).hexdigest()[:8]
                if fingerprint.group(1).lower() != remote_hash.lower():
                    report.append(
                        result(
                            f"asset {path}",
                            "FAIL",
                            f"URL fingerprint {fingerprint.group(1)} != live {remote_hash}",
                        )
                    )
                    continue
                cache = response["headers"].get("cache-control", "")
                passed = bool(IMMUTABLE_RE.search(cache)) and bool(re.search(r"max-age=(?:[0-9]{8,}|31536000)\b", cache, re.I))
                asset_status = "PASS" if passed else "FAIL"
                if args.hosting == "github-pages":
                    asset_status = "BLOCKED"
                report.append(result(f"asset {path}", asset_status, GITHUB_PAGES_POLICY_NOTE if args.hosting == "github-pages" else f"HTTP 200; {cache or 'Cache-Control absent'}"))

    failures = sum(item["status"] == "FAIL" for item in report)
    blocked = sum(item["status"] == "BLOCKED" for item in report)
    warnings = sum(item["status"] == "WARN" for item in report)
    payload = {
        "verifier": "verify-live-edge.py",
        "run_at": now(),
        "base": args.base.rstrip("/"),
        "timeout_seconds": args.timeout,
        "expected_commit": args.expected_commit,
        "hosting": args.hosting,
        "status": "FAILED" if failures else ("PARTIAL" if blocked or warnings else "PASS"),
        "summary": {"checks": len(report), "failures": failures, "blocked": blocked, "warnings": warnings},
        "checks": report,
    }
    validate_report_shape(payload)
    encoded = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    print(encoded, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    return 1 if failures or (blocked and not args.accept_blocked) or not routes else 0


if __name__ == "__main__":
    sys.exit(main())

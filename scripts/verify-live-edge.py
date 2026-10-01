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
from collections import deque
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
    ".mjs": frozenset({"application/javascript", "text/javascript"}),
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
JAVASCRIPT_SUFFIXES = frozenset({".js", ".mjs"})
MAX_JS_SOURCE_BYTES = 2 * 1024 * 1024
MAX_JS_GRAPH_SOURCE_BYTES = 8 * 1024 * 1024
MAX_JS_MODULES = 256
MAX_JS_IMPORTS_PER_MODULE = 256
MAX_JS_IMPORT_CLAUSE_TOKENS = 512
FIRST_PARTY_CONTENT_TYPES = {
    RELEASE_MANIFEST: frozenset({"application/json"}),
    "/sitemap.xml": frozenset({"application/xml", "text/xml"}),
    "/assets/data/search-index.json": frozenset({"application/json"}),
}
HTML_ASSET_RE = re.compile(
    r"""(?<![A-Za-z0-9_:/])(?P<url>/assets/(?:css|js|img|fonts|vendor)/[^'"<>\s,?#]+(?:\?[^'"<>\s,]*)?)""",
    re.I,
)
CSS_ASSET_RE = re.compile(
    r"""url\(\s*['"]?(?P<url>/assets/(?:img|fonts)/[^)'"\s,?#]+(?:\?[^)'"\s,]*)?)['"]?\s*\)""",
    re.I,
)
HTML_SCRIPT_BLOCK_RE = re.compile(
    r"""<script\b(?P<attributes>[^>]*)>(?P<source>.*?)</script\s*>""",
    re.I | re.S,
)
HTML_MODULE_TYPE_RE = re.compile(
    r"""\btype\s*=\s*(?:"module"|'module'|module(?=\s|/|$))""",
    re.I,
)
HTML_SCRIPT_SRC_RE = re.compile(r"(?:^|\s)src(?:\s|=|/?>)", re.I)
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
) -> bool:
    """Require a browser-compatible MIME type for each first-party asset."""
    expected = ASSET_CONTENT_TYPES.get(Path(path).suffix.lower())
    if expected is not None:
        return check_content_type(report, f"asset {path}", expected, response)
    return True


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


def fetch(
    base: str,
    path: str,
    timeout: float = TIMEOUT,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    url = urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
    )
    started = time.monotonic()

    def read_body(response: Any) -> tuple[bytes, bool]:
        if max_bytes is None:
            return response.read(), False
        body = response.read(max_bytes + 1)
        truncated = len(body) > max_bytes
        return body[:max_bytes], truncated

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body, truncated = read_body(response)
            headers = {k.lower(): v.strip() for k, v in response.headers.items()}
            return {
                "ok": True,
                "url": response.geturl(),
                "status": response.status,
                "headers": headers,
                "body": body,
                "truncated": truncated,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        headers = {}
        body = b""
        status = getattr(exc, "code", None)
        truncated = False
        if isinstance(exc, urllib.error.HTTPError):
            headers = {k.lower(): v.strip() for k, v in exc.headers.items()}
            try:
                body, truncated = read_body(exc)
            except OSError:
                pass
        return {
            "ok": False,
            "url": url,
            "status": status,
            "headers": headers,
            "body": body,
            "truncated": truncated,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def _read_javascript_string(source: str, start: int) -> tuple[str | None, int]:
    """Read a quoted JS string without executing it; unsupported escapes stay opaque."""
    quote = source[start]
    value: list[str] = []
    index = start + 1
    invalid = False
    while index < len(source):
        char = source[index]
        if char == quote:
            return (None if invalid else "".join(value)), index + 1
        if char in "\r\n":
            invalid = True
            index += 1
            continue
        if char != "\\":
            value.append(char)
            index += 1
            continue

        index += 1
        if index >= len(source):
            return None, index
        escaped = source[index]
        if escaped == "\r":
            index += 1
            if index < len(source) and source[index] == "\n":
                index += 1
            continue
        if escaped == "\n":
            index += 1
            continue
        if escaped in {"b", "f", "n", "r", "t", "v", "0"}:
            value.append(
                {
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                    "v": "\v",
                    "0": "\0",
                }[escaped]
            )
            index += 1
            continue
        if escaped == "x":
            digits = source[index + 1 : index + 3]
            if len(digits) == 2 and re.fullmatch(r"[0-9a-fA-F]{2}", digits):
                value.append(chr(int(digits, 16)))
                index += 3
            else:
                invalid = True
                index += 1
            continue
        if escaped == "u":
            if index + 1 < len(source) and source[index + 1] == "{":
                end = source.find("}", index + 2)
                digits = source[index + 2 : end] if end >= 0 else ""
                if (
                    digits
                    and re.fullmatch(r"[0-9a-fA-F]{1,6}", digits)
                    and int(digits, 16) <= 0x10FFFF
                ):
                    value.append(chr(int(digits, 16)))
                    index = end + 1
                else:
                    invalid = True
                    index = end + 1 if end >= 0 else len(source)
            else:
                digits = source[index + 1 : index + 5]
                if len(digits) == 4 and re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                    value.append(chr(int(digits, 16)))
                    index += 5
                else:
                    invalid = True
                    index += 1
            continue
        value.append(escaped)
        index += 1
    return None, index


def _skip_javascript_regex(source: str, start: int) -> int:
    """Skip a regular-expression literal conservatively to avoid fake import tokens."""
    index = start + 1
    in_character_class = False
    escaped = False
    while index < len(source):
        char = source[index]
        if char in "\r\n":
            return index
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "[":
            in_character_class = True
        elif char == "]":
            in_character_class = False
        elif char == "/" and not in_character_class:
            index += 1
            while index < len(source) and source[index].isalpha():
                index += 1
            return index
        index += 1
    return index


def _regex_can_start_after(previous: tuple[str, str | None] | None) -> bool:
    if previous is None:
        return True
    kind, value = previous
    if kind == "identifier":
        return value in {
            "await",
            "case",
            "delete",
            "in",
            "instanceof",
            "new",
            "of",
            "return",
            "throw",
            "typeof",
            "void",
            "yield",
        }
    return kind == "punctuation" and value in {
        "!",
        "!=",
        "!==",
        "%",
        "&",
        "&&",
        "&&=",
        "(",
        ",",
        ":",
        ";",
        "<",
        "<=",
        "=",
        "==",
        "===",
        "=>",
        ">",
        ">=",
        "?",
        "??",
        "??=",
        "[",
        "{",
        "|",
        "||",
        "||=",
        "~",
    }


def _javascript_tokens(source: str):
    """Yield bounded lexical tokens; comments, strings, templates, and regexes are opaque."""
    index = 0
    previous: tuple[str, str | None] | None = None
    operators = (
        ">>>=",
        "===",
        "!==",
        "**=",
        "&&=",
        "||=",
        "??=",
        ">>>",
        "...",
        "=>",
        "==",
        "!=",
        "<=",
        ">=",
        "++",
        "--",
        "&&",
        "||",
        "??",
        "?.",
        "**",
        "+=",
        "-=",
        "*=",
        "/=",
        "%=",
        "&=",
        "|=",
        "^=",
        "<<",
        ">>",
    )
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = len(source) if end < 0 else end + 2
            continue
        if char in {"'", '"'}:
            value, index = _read_javascript_string(source, index)
            token = ("string", value)
        elif char == "`":
            index += 1
            while index < len(source):
                if source[index] == "\\":
                    index += 2
                elif source[index] == "`":
                    index += 1
                    break
                else:
                    index += 1
            token = ("opaque", None)
        elif char == "/" and _regex_can_start_after(previous):
            index = _skip_javascript_regex(source, index)
            token = ("opaque", None)
        elif char.isalpha() or char in {"_", "$"} or ord(char) >= 128:
            end = index + 1
            while end < len(source) and (
                source[end].isalnum() or source[end] in {"_", "$"} or ord(source[end]) >= 128
            ):
                end += 1
            token = ("identifier", source[index:end])
            index = end
        elif char.isdigit():
            end = index + 1
            while end < len(source) and (
                source[end].isalnum() or source[end] in {"_", "."}
            ):
                end += 1
            token = ("other", None)
            index = end
        else:
            operator = next(
                (candidate for candidate in operators if source.startswith(candidate, index)),
                char,
            )
            token = ("punctuation", operator)
            index += len(operator)
        yield token
        previous = token


class _JavaScriptTokenStream:
    def __init__(self, source: str):
        self._tokens = iter(_javascript_tokens(source))
        self._buffer: deque[tuple[str, str | None]] = deque()

    def peek(self, offset: int = 0) -> tuple[str, str | None] | None:
        while len(self._buffer) <= offset:
            try:
                self._buffer.append(next(self._tokens))
            except StopIteration:
                return None
        return self._buffer[offset]

    def pop(self) -> tuple[str, str | None] | None:
        token = self.peek()
        return self._buffer.popleft() if token is not None else None

    def push(self, token: tuple[str, str | None]) -> None:
        self._buffer.appendleft(token)


def extract_javascript_imports(
    source: str,
    max_imports: int = MAX_JS_IMPORTS_PER_MODULE,
) -> tuple[list[str], bool]:
    """Find literal static, re-export, and dynamic imports without evaluating JavaScript."""
    tokens = _JavaScriptTokenStream(source)
    imports: list[str] = []
    seen: set[str] = set()
    exceeded = False

    def record(specifier: str | None) -> None:
        nonlocal exceeded
        if not specifier or specifier in seen:
            return
        if len(imports) >= max_imports:
            exceeded = True
            return
        seen.add(specifier)
        imports.append(specifier)

    previous: tuple[str, str | None] | None = None
    while (token := tokens.pop()) is not None:
        kind, value = token
        if kind != "identifier" or value not in {"import", "export"}:
            previous = token
            continue
        if previous is not None and previous[1] in {".", "?."}:
            previous = token
            continue

        if value == "import":
            following = tokens.peek()
            if following is not None and following[1] in {".", "?."}:
                previous = token
                continue
            if following is not None and following[0] == "string":
                record(tokens.pop()[1])
                previous = ("string", None)
                if exceeded:
                    break
                continue
            if (
                following == ("punctuation", "(")
                and tokens.peek(1) is not None
                and tokens.peek(1)[0] == "string"
                and tokens.peek(2) is not None
                and tokens.peek(2)[1] in {")", ","}
            ):
                tokens.pop()
                record(tokens.pop()[1])
                next_token = tokens.peek()
                if next_token is not None and next_token[1] == ")":
                    previous = tokens.pop()
                else:
                    depth = 1
                    previous = token
                    for _ in range(MAX_JS_IMPORT_CLAUSE_TOKENS):
                        tail = tokens.pop()
                        if tail is None:
                            break
                        if tail == ("punctuation", "("):
                            depth += 1
                        elif tail == ("punctuation", ")"):
                            depth -= 1
                            if depth == 0:
                                previous = tail
                                break
                if exceeded:
                    break
                continue
            if following == ("punctuation", "("):
                # A computed import() is deliberately outside this literal-only scan.
                previous = token
                continue
        elif tokens.peek() is None or tokens.peek()[1] not in {"*", "{"}:
            previous = token
            continue

        depth = 0
        last_token = token
        found = False
        for _ in range(MAX_JS_IMPORT_CLAUSE_TOKENS):
            clause_token = tokens.pop()
            if clause_token is None:
                break
            last_token = clause_token
            clause_kind, clause_value = clause_token
            if clause_kind == "punctuation":
                if clause_value in {"{", "[", "("}:
                    depth += 1
                elif clause_value in {"}", "]", ")"}:
                    depth = max(0, depth - 1)
                elif clause_value == ";" and depth == 0:
                    break
            if (
                clause_kind == "identifier"
                and clause_value in {"import", "export"}
                and depth == 0
            ):
                tokens.push(clause_token)
                last_token = token
                break
            if (
                clause_kind == "identifier"
                and clause_value == "from"
                and depth == 0
            ):
                source_token = tokens.peek()
                if source_token is not None and source_token[0] == "string":
                    source_token = tokens.pop()
                    last_token = source_token
                    record(source_token[1])
                    found = True
                    break
        else:
            exceeded = True
        previous = last_token
        if exceeded:
            break
        if found:
            continue

    return imports, exceeded


def _same_http_origin(left: str, right: str) -> bool:
    try:
        left_parts = urllib.parse.urlsplit(left)
        right_parts = urllib.parse.urlsplit(right)
        left_port = left_parts.port or (443 if left_parts.scheme.lower() == "https" else 80)
        right_port = right_parts.port or (443 if right_parts.scheme.lower() == "https" else 80)
    except ValueError:
        return False
    return (
        left_parts.scheme.lower() in {"http", "https"}
        and left_parts.scheme.lower() == right_parts.scheme.lower()
        and (left_parts.hostname or "").lower() == (right_parts.hostname or "").lower()
        and left_port == right_port
    )


def resolve_javascript_import(base: str, referrer: str, specifier: str) -> str | None:
    """Resolve only same-origin JS modules under /assets; ignore bare and external imports."""
    specifier = specifier.strip()
    if not specifier:
        return None
    if not (
        specifier.startswith(("/", "./", "../"))
        or specifier.startswith("//")
        or re.match(r"^https?://", specifier, re.I)
    ):
        return None

    referrer_url = urllib.parse.urljoin(base.rstrip("/") + "/", referrer.lstrip("/"))
    resolved = urllib.parse.urljoin(referrer_url, specifier)
    if not _same_http_origin(base, resolved):
        return None
    parsed = urllib.parse.urlsplit(resolved)
    decoded_path = urllib.parse.unquote(parsed.path)
    if (
        not decoded_path.startswith("/assets/")
        or "\\" in decoded_path
        or any(part in {".", ".."} for part in decoded_path.split("/"))
        or Path(decoded_path).suffix.lower() not in JAVASCRIPT_SUFFIXES
    ):
        return None
    return urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))


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

    # Check first-party assets and walk literal same-origin JavaScript imports.
    # Module sources are read as text only; this verifier never evaluates JS.
    assets: dict[str, str] = {}
    js_asset_urls: set[str] = set()
    js_limit_reported = False

    def report_js_limit(evidence: str) -> None:
        nonlocal js_limit_reported
        if not js_limit_reported:
            report.append(
                result("JavaScript dependency discovery", "BLOCKED", evidence)
            )
            js_limit_reported = True

    def add_asset(asset_url: str, source: str) -> None:
        asset_url = asset_url.split("#", 1)[0]
        if not asset_url or asset_url in assets:
            return
        suffix = Path(urllib.parse.urlsplit(asset_url).path).suffix.lower()
        if suffix in JAVASCRIPT_SUFFIXES:
            if len(js_asset_urls) >= MAX_JS_MODULES:
                report_js_limit(
                    f"stopped after {MAX_JS_MODULES} JavaScript assets; "
                    f"additional dependency {asset_url} referenced by {source}"
                )
                return
            js_asset_urls.add(asset_url)
        assets[asset_url] = asset_url

    inline_import_cache: dict[bytes, tuple[list[str], bool]] = {}
    js_source_bytes = 0
    inline_module_count = 0
    for route, body in bodies.items():
        for match in HTML_ASSET_RE.finditer(body):
            add_asset(match.group("url"), f"route {route}")
        for match in HTML_SCRIPT_BLOCK_RE.finditer(body):
            attributes = match.group("attributes")
            if (
                not HTML_MODULE_TYPE_RE.search(attributes)
                or HTML_SCRIPT_SRC_RE.search(attributes)
            ):
                continue
            inline_module_count += 1
            if inline_module_count > MAX_JS_MODULES:
                report_js_limit(
                    f"stopped after {MAX_JS_MODULES} inline module blocks"
                )
                break
            source = match.group("source")
            source_bytes = len(source.encode("utf-8"))
            source_key = hashlib.sha256(source.encode("utf-8")).digest()
            parsed_imports = inline_import_cache.get(source_key)
            if parsed_imports is None:
                if source_bytes > MAX_JS_SOURCE_BYTES:
                    report.append(
                        result(
                            f"JavaScript imports inline {route}",
                            "BLOCKED",
                            f"inline module exceeds the {MAX_JS_SOURCE_BYTES}-byte source limit",
                        )
                    )
                    continue
                if js_source_bytes + source_bytes > MAX_JS_GRAPH_SOURCE_BYTES:
                    report_js_limit(
                        f"stopped parsing after the "
                        f"{MAX_JS_GRAPH_SOURCE_BYTES}-byte JavaScript source budget"
                    )
                    continue
                js_source_bytes += source_bytes
                parsed_imports = extract_javascript_imports(source)
                inline_import_cache[source_key] = parsed_imports
            imports, import_limit_exceeded = parsed_imports
            if import_limit_exceeded:
                report.append(
                    result(
                        f"JavaScript imports inline {route}",
                        "BLOCKED",
                        f"module exceeds the {MAX_JS_IMPORTS_PER_MODULE}-import or "
                        f"{MAX_JS_IMPORT_CLAUSE_TOKENS}-token clause limit",
                    )
                )
            for specifier in imports:
                dependency = resolve_javascript_import(args.base, route, specifier)
                if dependency:
                    add_asset(dependency, f"inline module on {route}")

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
            suffix = Path(path).suffix.lower()
            is_javascript = suffix in JAVASCRIPT_SUFFIXES
            if is_javascript:
                remaining_js_budget = MAX_JS_GRAPH_SOURCE_BYTES - js_source_bytes
                if remaining_js_budget <= 0:
                    report_js_limit(
                        f"stopped fetching after the "
                        f"{MAX_JS_GRAPH_SOURCE_BYTES}-byte JavaScript source budget"
                    )
                    report.append(
                        result(
                            f"asset {path}",
                            "BLOCKED",
                            "not fetched because the JavaScript source budget is exhausted",
                        )
                    )
                    continue
                max_source_bytes = min(
                    MAX_JS_SOURCE_BYTES, remaining_js_budget
                )
            else:
                max_source_bytes = None
            response = fetch(
                args.base,
                asset_url,
                args.timeout,
                max_bytes=max_source_bytes,
            )
            if is_javascript:
                js_source_bytes += len(response.get("body", b""))
            mime_ok = True
            if response.get("ok") and response.get("status") == 200:
                mime_ok = check_asset_content_type(report, path, response)
                if suffix == ".css":
                    css_body = response["body"].decode("utf-8", errors="replace")
                    for match in CSS_ASSET_RE.finditer(css_body):
                        add_asset(match.group("url"), f"stylesheet {path}")
                if is_javascript and mime_ok and not response.get("truncated"):
                    module_source = response["body"].decode(
                        "utf-8", errors="replace"
                    )
                    imports, import_limit_exceeded = extract_javascript_imports(
                        module_source
                    )
                    if import_limit_exceeded:
                        report.append(
                            result(
                                f"JavaScript imports {path}",
                                "BLOCKED",
                                f"module exceeds the {MAX_JS_IMPORTS_PER_MODULE}-import "
                                f"or {MAX_JS_IMPORT_CLAUSE_TOKENS}-token clause limit",
                            )
                        )
                    for specifier in imports:
                        dependency = resolve_javascript_import(
                            args.base, asset_url, specifier
                        )
                        if dependency:
                            add_asset(dependency, f"module {path}")
            if response.get("truncated"):
                if max_source_bytes < MAX_JS_SOURCE_BYTES:
                    truncation_evidence = (
                        f"JavaScript source exceeds the remaining "
                        f"{max_source_bytes}-byte graph budget"
                    )
                else:
                    truncation_evidence = (
                        f"JavaScript source exceeds the per-module "
                        f"{MAX_JS_SOURCE_BYTES}-byte fetch limit"
                    )
                report.append(
                    result(
                        f"asset {path}",
                        "BLOCKED",
                        truncation_evidence,
                    )
                )
                continue
            if not fingerprint:
                if suffix in FINGERPRINTED_ASSET_SUFFIXES:
                    report.append(result(f"asset {path}", "FAIL", "missing 8-character ?v= fingerprint"))
                elif not response.get("ok") or response.get("status") != 200:
                    report.append(result(f"asset {path}", transport_status(response),
                                         response.get("error", f"HTTP {response.get('status')}")))
                elif is_javascript:
                    if not local_path.is_file():
                        report.append(
                            result(
                                f"asset {path}",
                                "FAIL",
                                f"local JavaScript module missing: {local_path}",
                            )
                        )
                    else:
                        local_bytes = canonical_text_bytes(local_path)
                        remote_bytes = response["body"].replace(b"\r\n", b"\n")
                        local_sha256 = hashlib.sha256(local_bytes).hexdigest()
                        remote_sha256 = hashlib.sha256(remote_bytes).hexdigest()
                        if local_sha256 != remote_sha256:
                            report.append(
                                result(
                                    f"asset {path}",
                                    "FAIL",
                                    "live JavaScript module SHA-256 "
                                    f"{remote_sha256[:12]} differs from local "
                                    f"{local_sha256[:12]}",
                                )
                            )
                        else:
                            report.append(
                                result(
                                    f"asset {path}",
                                    "PASS",
                                    f"HTTP 200; SHA-256 {local_sha256[:12]} matches local module",
                                )
                            )
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

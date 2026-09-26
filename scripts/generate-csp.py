#!/usr/bin/env python3
"""Generate canonical CSP policies and apply them to every HTML page."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from csp import (
    CSP_HEADER,
    CSP_REPORT_ONLY_HEADER,
    CspPageManifestError,
    POLICY_FILE,
    ROOT,
    all_pages,
    build_edge_policy,
    build_policies,
    page_class,
    render_meta,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated output is stale")
    args = parser.parse_args(argv)
    try:
        pages = all_pages()
        policies = build_policies()
    except CspPageManifestError as exc:
        print(f"CSP page manifest error: {exc}", file=sys.stderr)
        return 1
    output = json.dumps({"schema": 1, "policies": policies}, indent=2) + "\n"
    failures: list[str] = []
    headers = ROOT / "_headers"
    header_pattern = re.compile(
        rf"(?m)^\s*(?:{re.escape(CSP_HEADER)}|{re.escape(CSP_REPORT_ONLY_HEADER)}):\s*.*$"
    )
    if args.check:
        if not POLICY_FILE.exists() or POLICY_FILE.read_text(encoding="utf-8") != output:
            failures.append("config/csp-policies.json is stale. Run: python3 scripts/generate-csp.py")
        if not headers.exists():
            failures.append("_headers is missing")
        else:
            header_source = headers.read_text(encoding="utf-8")
            enforcing_headers = re.findall(
                rf"(?m)^\s*{re.escape(CSP_HEADER)}:\s*.*$", header_source
            )
            report_only_headers = re.findall(
                rf"(?m)^\s*{re.escape(CSP_REPORT_ONLY_HEADER)}:\s*.*$", header_source
            )
            if len(enforcing_headers) != 1 or report_only_headers:
                failures.append(
                    "_headers must contain exactly one enforcing "
                    f"{CSP_HEADER} header and no {CSP_REPORT_ONLY_HEADER} header"
                )
    else:
        POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        POLICY_FILE.write_text(output, encoding="utf-8")
        header_source = headers.read_text(encoding="utf-8")
        header_matches = header_pattern.findall(header_source)
        if len(header_matches) != 1:
            failures = ["_headers: expected one CSP header"]
        else:
            header_line = f"  {CSP_HEADER}: " + build_edge_policy()
            updated_headers = header_pattern.sub(header_line, header_source, count=1)
            headers.write_text(updated_headers, encoding="utf-8")

    meta_pattern = re.compile(
        rf'<meta\b(?=[^>]*\bhttp-equiv=["\']{re.escape(CSP_HEADER)}["\'])'
        r'(?=[^>]*\bcontent=(["\']))[^>]*\s*/?>',
        re.IGNORECASE,
    )
    for page in pages:
        source = page.read_text(encoding="utf-8", errors="replace")
        expected = render_meta(policies[page_class(page)])
        if args.check:
            if CSP_REPORT_ONLY_HEADER in source or source.count(
                f'http-equiv="{CSP_HEADER}"'
            ) != 1 or meta_policy(source) != policies[page_class(page)]:
                failures.append(f"{page}: CSP differs from {page_class(page)} canonical policy")
        else:
            updated, count = meta_pattern.subn(expected, source, count=1)
            if count == 0:
                continue
            if count != 1:
                failures.append(f"{page}: expected exactly one CSP meta tag")
            else:
                page.write_text(updated, encoding="utf-8", newline="")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"CSP policies verified for {len(pages)} pages.")
    return 0


def meta_policy(source: str) -> str | None:
    match = re.search(
        r'<meta\b(?=[^>]*\bhttp-equiv=["\']Content-Security-Policy["\'])'
        r'(?=[^>]*\bcontent=(["\']))[^>]*\bcontent=\1(.*?)\1',
        source,
        re.IGNORECASE,
    )
    return match.group(2) if match else None


if __name__ == "__main__":
    raise SystemExit(main())
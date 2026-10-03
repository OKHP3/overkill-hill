#!/usr/bin/env python3
"""Validate the published contract for a locale pilot.

The unpublished pilot is checked as a scaffold: its source routes must exist,
but no target pages or target sitemap/search-index entries may be present.
Once the manifest is no longer marked ``unpublished-scaffold``, every route is
checked for page metadata, reciprocal hreflang links, sitemap coverage,
locale search-index coverage, and social-card metadata when promoted.
"""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(
    os.environ.get(
        "OKHP3_VALIDATION_ROOT",
        str(Path(__file__).resolve().parents[1]),
    )
).resolve()
SITE_ORIGIN = "https://overkillhill.com"
DEFAULT_MANIFEST = ROOT / "i18n" / "pilot" / "manifest.json"
DEFAULT_SITEMAP = ROOT / "sitemap.xml"
SEARCH_INDEX_BUILDER = ROOT / "scripts" / "build-search-index.py"
VALIDATE_SITE_PATH = ROOT / "scripts" / "validate-site.py"


def load_site_validator():
    """Reuse the production social-card contract without duplicating it."""
    spec = importlib.util.spec_from_file_location("validate_site", VALIDATE_SITE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load site validator: {VALIDATE_SITE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HeadMetadata(HTMLParser):
    """Collect only the head metadata needed by this release check."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.canonical = ""
        self.og_url = ""
        self.meta: dict[str, list[str]] = {}
        self.alternates: dict[str, set[str]] = {}
        self.is_noindex = False
        self._in_html = False

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {key.lower(): value or "" for key, value in attrs_list}
        tag = tag.lower()
        if tag == "html":
            self.lang = attrs.get("lang", "").strip()
            self._in_html = True
        elif tag == "link":
            rel = set(attrs.get("rel", "").lower().split())
            href = attrs.get("href", "").strip()
            if "canonical" in rel:
                self.canonical = href
            if "alternate" in rel and attrs.get("hreflang", "").strip() and href:
                self.alternates.setdefault(attrs["hreflang"].strip().lower(), set()).add(href)
        elif tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            content = attrs.get("content", "").strip()
            if key:
                self.meta.setdefault(key, []).append(content)
            if key == "robots":
                self.is_noindex = "noindex" in content.lower()
            elif key == "og:url":
                self.og_url = content


def route_file(root: Path, route: str) -> Path:
    """Map a slash-terminated public route to its static HTML file."""
    path = root / route.lstrip("/")
    if route == "/":
        return root / "index.html"
    if route.endswith("/"):
        return path / "index.html"
    return path


def route_url(route: str) -> str:
    return f"{SITE_ORIGIN}{route}"


def read_metadata(path: Path) -> HeadMetadata:
    parser = HeadMetadata()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser


def fail(findings: list[str], message: str) -> None:
    findings.append(message)


def load_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be a JSON object")
    return manifest


def sitemap_locations(path: Path) -> list[str]:
    try:
        root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"cannot read sitemap {path}: {exc}") from exc
    return [
        element.text.strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "loc" and element.text and element.text.strip()
    ]


def sitemap_urls(path: Path) -> set[str]:
    return set(sitemap_locations(path))


def check_search_index(
    index_path: Path,
    promoted_routes: set[str],
    locale: str,
    findings: list[str],
    *,
    draft_routes: set[str],
    require_routes: bool,
) -> None:
    if not index_path.is_file():
        fail(findings, f"locale search index is missing: {index_path}")
        return
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(findings, f"locale search index is not valid JSON: {exc}")
        return
    if not isinstance(payload, dict):
        fail(findings, "locale search index must be an object")
        return
    if payload.get("locale") != locale:
        fail(findings, f"locale search index has locale {payload.get('locale')!r}, expected {locale!r}")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        fail(findings, "locale search index entries must be a list")
        return
    urls = []
    for position, entry in enumerate(entries):
        url = entry.get("url") if isinstance(entry, dict) else None
        if not isinstance(url, str) or not url.strip():
            fail(findings, f"locale search index entry {position} must have a non-empty string URL")
            continue
        urls.append(url)
    indexed_routes = set(urls)
    declared_routes = promoted_routes | draft_routes
    undeclared = sorted(indexed_routes - declared_routes)
    if undeclared:
        fail(findings, f"locale search index contains undeclared routes: {', '.join(undeclared)}")
    if require_routes:
        missing = sorted(promoted_routes - indexed_routes)
        if missing:
            fail(findings, f"locale search index is missing routes: {', '.join(missing)}")
    indexed_drafts = sorted(draft_routes & indexed_routes)
    if indexed_drafts:
        fail(findings, f"draft locale routes appear in the search index: {', '.join(indexed_drafts)}")
    if len(urls) != len(set(urls)):
        fail(findings, "locale search index contains duplicate URLs")
    if payload.get("count") != len(entries):
        fail(findings, f"locale search index count is {payload.get('count')!r}, expected {len(entries)}")


def run_index_freshness_check(index_path: Path, locale: str, findings: list[str]) -> None:
    expected = ROOT / "assets" / "data" / f"search-index.{locale}.json"
    if index_path.resolve() != expected.resolve():
        return
    result = subprocess.run(
        [sys.executable, str(SEARCH_INDEX_BUILDER), f"--locale={locale}", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        fail(findings, f"locale search index is stale: {detail[-1] if detail else 'build check failed'}")


def locale_specs(manifest: dict) -> list[dict]:
    """Normalize legacy one-locale and current multi-locale pilot manifests."""
    locale = manifest.get("target_locale")
    pages = manifest.get("pages")
    if isinstance(locale, str) and locale and isinstance(pages, list):
        return [{
            "locale": locale,
            "pages": pages,
            "status": manifest.get("status", "published"),
            "indexable": manifest.get("indexable"),
            "metadata_source": manifest.get("metadata_source"),
        }]

    target_locales = manifest.get("target_locales")
    locales = manifest.get("locales")
    if not isinstance(target_locales, list) or not target_locales:
        raise ValueError("manifest target_locale must be a non-empty string, or target_locales must be a non-empty list")
    if not isinstance(locales, dict):
        raise ValueError("multi-locale manifest locales must be an object")

    specs: list[dict] = []
    for locale in target_locales:
        entry = locales.get(locale) if isinstance(locale, str) else None
        if not isinstance(locale, str) or not locale or not isinstance(entry, dict):
            raise ValueError(f"manifest locale entry is missing or invalid: {locale!r}")
        pages = entry.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError(f"manifest locale {locale!r} pages must be a non-empty list")
        specs.append({
            "locale": locale,
            "pages": pages,
            "status": entry.get("status", ""),
            "indexable": entry.get("indexable"),
            "metadata_source": entry.get("metadata_source"),
        })
    return specs


def validate_locale(
    locale: str,
    pages: list,
    status: str,
    urls: set[str],
    sitemap_locations: list[str],
    root: Path,
    index_path: Path,
    findings: list[str],
    *,
    indexable: object,
    metadata_source: object,
) -> None:
    is_unpublished = status == "unpublished-scaffold"
    if not isinstance(indexable, bool):
        fail(findings, f"locale {locale!r} must declare boolean indexable state")
        indexable = False
    if metadata_source not in {"localized-page"}:
        fail(findings, f"locale {locale!r} must declare metadata_source='localized-page'")
    source_routes: set[str] = set()
    target_routes: set[str] = set()
    promoted_routes: set[str] = set()
    site_validator = None
    for page in pages:
        if not isinstance(page, dict):
            fail(findings, "manifest contains a non-object page entry")
            continue
        source_route = page.get("source_route")
        target_route = page.get("target_route")
        source_path = page.get("source_path")
        target_path = page.get("target_path")
        if not all(isinstance(value, str) and value for value in (source_route, target_route, source_path, target_path)):
            fail(findings, f"manifest page has incomplete route/path fields: {page!r}")
            continue
        source_routes.add(source_route)
        target_routes.add(target_route)
        page_indexable = page.get("indexable", indexable)
        page_metadata_source = page.get("metadata_source", metadata_source)
        if not isinstance(page_indexable, bool):
            fail(findings, f"locale page {target_path} must declare boolean indexable state")
            page_indexable = False
        if page_metadata_source not in {"localized-page"}:
            fail(findings, f"locale page {target_path} must declare metadata_source='localized-page'")
        if page_indexable:
            promoted_routes.add(target_route)
        source_file = root / source_path
        target_file = root / target_path
        if not source_file.is_file():
            fail(findings, f"English source page is missing: {source_path}")
        if not target_route.startswith(f"/{locale}/"):
            fail(findings, f"target route is outside /{locale}/: {target_route}")
        if is_unpublished:
            if page_indexable:
                fail(findings, f"unpublished locale page cannot be indexable: {target_path}")
            if target_file.exists():
                fail(findings, f"unpublished scaffold contains target page: {target_path}")
            if route_url(target_route) in urls:
                fail(findings, f"unpublished target route is in sitemap.xml: {target_route}")
            continue
        if not target_file.is_file():
            fail(findings, f"locale page is missing: {target_path}")
            continue
        source_meta = read_metadata(source_file)
        target_meta = read_metadata(target_file)
        expected_source = route_url(source_route)
        expected_target = route_url(target_route)
        if source_meta.canonical != expected_source:
            fail(findings, f"{source_path} canonical is {source_meta.canonical!r}, expected {expected_source!r}")
        if source_meta.og_url != expected_source:
            fail(findings, f"{source_path} og:url is {source_meta.og_url!r}, expected {expected_source!r}")
        if target_meta.canonical != expected_target:
            fail(findings, f"{target_path} canonical is {target_meta.canonical!r}, expected {expected_target!r}")
        if target_meta.og_url != expected_target:
            fail(findings, f"{target_path} og:url is {target_meta.og_url!r}, expected {expected_target!r}")
        expected_source_links = {
            "en": expected_source,
            "x-default": expected_source,
            locale: expected_target,
        }
        expected_target_links = {
            locale: expected_target,
            "en": expected_source,
            "x-default": expected_source,
        }
        for label, meta, expected in (
            (source_path, source_meta, expected_source_links),
            (target_path, target_meta, expected_target_links),
        ):
            for hreflang, href in expected.items():
                if href not in meta.alternates.get(hreflang, set()):
                    fail(findings, f"{label} is missing hreflang={hreflang!r} href={href!r}")
        if target_meta.lang.lower() != locale.lower():
            fail(findings, f"{target_path} html lang is {target_meta.lang!r}, expected {locale!r}")
        if source_meta.lang.lower() not in ("", "en"):
            fail(findings, f"{source_path} html lang is {source_meta.lang!r}, expected 'en'")
        manifest_boundary = "indexable" if page_indexable else "noindex"
        rendered_boundary = "noindex" if target_meta.is_noindex else "indexable"
        if manifest_boundary != rendered_boundary:
            fail(
                findings,
                (
                    f"{target_path}: robots indexing boundary mismatch: "
                    f"manifest={manifest_boundary}, rendered={rendered_boundary}"
                ),
            )
        if page_indexable:
            if site_validator is None:
                site_validator = load_site_validator()
            duplicate_findings = site_validator.validate_duplicate_social_card_metadata(
                target_path,
                target_meta.meta,
            )
            social_findings = site_validator.validate_indexable_social_card(
                target_path,
                {
                    f"meta:{key}": values[0] if values else ""
                    for key, values in target_meta.meta.items()
                },
            )
            for finding in duplicate_findings + social_findings:
                fail(findings, f"{finding.page}: {finding.msg}")
        else:
            if expected_target in urls:
                fail(findings, f"draft locale route is in sitemap.xml: {target_route}")

    locale_prefix = f"{SITE_ORIGIN}/{locale}/"
    locale_sitemap_routes = [
        url.removeprefix(SITE_ORIGIN)
        for url in sitemap_locations
        if url.startswith(locale_prefix)
    ]
    locale_sitemap_counts = Counter(locale_sitemap_routes)
    duplicate_sitemap_routes = sorted(
        route for route, count in locale_sitemap_counts.items() if count > 1
    )
    if duplicate_sitemap_routes:
        fail(
            findings,
            "locale sitemap contains duplicate routes: "
            + ", ".join(
                f"{route} (appears {locale_sitemap_counts[route]} times)"
                for route in duplicate_sitemap_routes
            ),
        )
    sitemap_locale_routes = {
        url.removeprefix(SITE_ORIGIN)
        for url in urls
        if url.startswith(locale_prefix)
    }
    draft_routes = target_routes - promoted_routes
    declared_routes = promoted_routes | draft_routes
    undeclared_sitemap_routes = sorted(sitemap_locale_routes - declared_routes)
    if undeclared_sitemap_routes:
        fail(
            findings,
            "locale sitemap contains undeclared routes: "
            + ", ".join(undeclared_sitemap_routes),
        )

    if is_unpublished:
        check_search_index(
            index_path,
            set(),
            locale,
            findings,
            draft_routes=target_routes,
            require_routes=False,
        )
        return

    for route in sorted(source_routes):
        if route_url(route) not in urls:
            fail(findings, f"source route is missing from sitemap.xml: {route}")
    for route in sorted(promoted_routes):
        if route_url(route) not in urls:
            fail(findings, f"indexable locale route is missing from sitemap.xml: {route}")
    check_search_index(
        index_path,
        promoted_routes,
        locale,
        findings,
        draft_routes=draft_routes,
        require_routes=bool(promoted_routes),
    )
    run_index_freshness_check(index_path, locale, findings)


def validate(
    manifest_path: Path = DEFAULT_MANIFEST,
    sitemap_path: Path = DEFAULT_SITEMAP,
    index_path: Path | None = None,
    root: Path = ROOT,
) -> list[str]:
    manifest = load_manifest(manifest_path)
    findings: list[str] = []
    try:
        locations = sitemap_locations(sitemap_path)
        urls = set(locations)
    except ValueError as exc:
        fail(findings, str(exc))
        locations = []
        urls = set()

    try:
        specs = locale_specs(manifest)
    except ValueError as exc:
        fail(findings, str(exc))
        return findings

    for spec in specs:
        locale = spec["locale"]
        locale_index = index_path or root / "assets" / "data" / f"search-index.{locale}.json"
        validate_locale(
            locale,
            spec["pages"],
            spec["status"],
            urls,
            locations,
            root,
            locale_index,
            findings,
            indexable=spec["indexable"],
            metadata_source=spec["metadata_source"],
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--sitemap", type=Path, default=DEFAULT_SITEMAP)
    parser.add_argument("--search-index", type=Path)
    args = parser.parse_args(argv)
    findings = validate(args.manifest, args.sitemap, args.search_index)
    if findings:
        print("Locale link check failed:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    labels = ", ".join(spec["locale"] for spec in locale_specs(load_manifest(args.manifest)))
    print(f"Locale link check passed: {args.manifest} ({labels})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

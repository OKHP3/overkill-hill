#!/usr/bin/env python3
"""Prove the site validator rejects committed SEO regression mutations.

The fixtures intentionally mutate only metadata or navigation.  Editorial
fields, generated body content, and indexing boundaries are asserted to stay
unchanged so this suite cannot pass by changing the content contract itself.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "seo"
FIXTURES = FIXTURE_ROOT / "regressions.json"
GENERATED_FIXTURE = FIXTURE_ROOT / "generated"
HEAT_FIXTURE = GENERATED_FIXTURE / "heat-guides"

sys.path.insert(0, str(ROOT / "scripts"))
validator_spec = importlib.util.spec_from_file_location(
    "validate_site", ROOT / "scripts" / "validate-site.py"
)
if validator_spec is None or validator_spec.loader is None:
    raise RuntimeError("could not load scripts/validate-site.py")
validator = importlib.util.module_from_spec(validator_spec)
validator_spec.loader.exec_module(validator)
locale_checker_spec = importlib.util.spec_from_file_location(
    "check_locale_links", ROOT / "scripts" / "check-locale-links.py"
)
if locale_checker_spec is None or locale_checker_spec.loader is None:
    raise RuntimeError("could not load scripts/check-locale-links.py")
locale_checker = importlib.util.module_from_spec(locale_checker_spec)
locale_checker_spec.loader.exec_module(locale_checker)


def findings_text(findings: list) -> str:
    return "\n".join(f"{finding.page}: {finding.msg}" for finding in findings)


def page_for_route(pages: list[dict], route: str) -> dict:
    return next(page for page in pages if page.get("route") == route)


def parse_html(raw: str):
    parser = validator.TagCounter()
    parser.feed(raw)
    return parser


def mutate_meta(raw: str, field: str, value: str | None) -> str:
    name_or_property, key = field.split(":", 1)
    attribute = "property" if key.startswith("og:") else "name"
    pattern = re.compile(
        rf'<meta\b(?=[^>]*\b{attribute}=["\']{re.escape(key)}["\'])[^>]*>',
        re.IGNORECASE,
    )
    if value is None:
        mutated, count = pattern.subn("", raw, count=1)
    else:
        replacement = (
            f'<meta {attribute}="{key}" content="{value}">'
        )
        mutated, count = pattern.subn(replacement, raw, count=1)
    if count != 1:
        raise AssertionError(f"fixture metadata tag not found: {field}")
    return mutated


def mutate_jsonld_field(raw: str, field: str, value: str) -> str:
    pattern = re.compile(
        rf'("{re.escape(field)}"\s*:\s*)"[^"]*"',
        re.IGNORECASE,
    )
    mutated, count = pattern.subn(rf'\1"{value}"', raw, count=1)
    if count != 1:
        raise AssertionError(f"fixture JSON-LD field not found: {field}")
    return mutated


def remove_jsonld_field(raw: str, field: str) -> str:
    pattern = re.compile(
        rf'\s*"{re.escape(field)}"\s*:\s*"[^"]*"\s*,?',
        re.IGNORECASE,
    )
    mutated, count = pattern.subn("", raw, count=1)
    if count != 1:
        raise AssertionError(f"fixture JSON-LD field not found: {field}")
    return mutated


def duplicate_article_jsonld(raw: str, field: str, value: str) -> str:
    pattern = re.compile(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(raw):
        block = match.group(0)
        if '"@type": "Article"' not in block:
            continue
        duplicate = mutate_jsonld_field(block, field, value)
        return raw[:match.end()] + duplicate + raw[match.end():]
    raise AssertionError("fixture Article JSON-LD block not found")


def article_jsonld_nodes(raw: str) -> list[dict]:
    objects, errors = validator._jsonld_objects(parse_html(raw))
    if errors:
        raise AssertionError(f"invalid fixture JSON-LD: {errors!r}")
    return [item for item in objects if item.get("@type") == "Article"]


def duplicate_article_jsonld_root_url(raw: str, value: str) -> str:
    pattern = re.compile(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(raw):
        block = match.group(0)
        open_end = block.find(">")
        close_start = block.lower().rfind("</script>")
        if open_end == -1 or close_start == -1:
            continue
        try:
            payload = json.loads(block[open_end + 1:close_start])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("@type") != "Article":
            continue
        duplicate = copy.deepcopy(payload)
        duplicate["url"] = value
        duplicate_block = (
            '<script type="application/ld+json">\n'
            + json.dumps(duplicate, ensure_ascii=False, indent=2)
            + "\n</script>"
        )
        return raw[:match.end()] + "\n" + duplicate_block + raw[match.end():]
    raise AssertionError("top-level Article JSON-LD block not found")


def article_graph_with_conflicting_modified_date(raw: str, value: str) -> str:
    pattern = re.compile(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(raw):
        block = match.group(0)
        open_end = block.find(">")
        close_start = block.lower().rfind("</script>")
        if open_end == -1 or close_start == -1:
            continue
        try:
            payload = json.loads(block[open_end + 1:close_start])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("@type") != "Article":
            continue

        first = copy.deepcopy(payload)
        article_id = first.get("@id") or f'{first["url"]}#article'
        first["@id"] = article_id
        second = copy.deepcopy(first)
        second["dateModified"] = value
        graph_payload = {
            "@context": payload.get("@context", "https://schema.org"),
            "@graph": [first, second],
        }
        graph_block = (
            block[:open_end + 1]
            + "\n"
            + json.dumps(graph_payload, ensure_ascii=False, indent=2)
            + "\n"
            + block[close_start:]
        )
        return raw[:match.start()] + graph_block + raw[match.end():]
    raise AssertionError("top-level Article JSON-LD block not found")


def mutate_navigation(raw: str, key: str, value: str) -> str:
    pattern = re.compile(
        rf'<link\b(?=[^>]*\brel=["\'][^"\']*\b{key}\b[^"\']*["\'])[^>]*>',
        re.IGNORECASE,
    )
    replacement = f'<link href="{value}" rel="{key}">'
    mutated, count = pattern.subn(replacement, raw, count=1)
    if count:
        return mutated
    return raw.replace("</head>", f'  {replacement}\n</head>', 1)


class SEOFixtureTests(unittest.TestCase):
    def test_article_date_parity_rejects_python_only_syntax_before_equality(self) -> None:
        calendar = "2026-06-12T00:00:00Z"
        for value in (
            "2026-W24-5", "2026-W24-5T00:00:00Z", "20260612", "20260612T00:00:00Z",
            "2026-06-12 00:00:00Z", "2026-06-12t00:00:00Z",
            "2026-06-12T000000Z", "2026-06-12T00:00:00+0000",
            "2026-06-12T00:00:00+00:00:00", "2026-06-12T00:00:00+00:60",
            "2026-06-12T24:00Z", "2026-06-12T24:00:00Z",
            "2026-06-12T00:60:00Z", "2026-06-12T00:00:60Z",
            "2026-02-30", "not-a-date",
        ):
            with self.subTest(value=value):
                self.assertFalse(validator._article_date_values_match(value, calendar))
                self.assertFalse(validator._article_date_values_match(calendar, value))
                self.assertFalse(validator._article_date_values_match(value, value))
        for value in ("2026-06-12T24:00Z", "2026-06-12T24:00:00Z"):
            with self.subTest(value=value):
                self.assertFalse(validator._article_date_values_match(value, "2026-06-13T00:00:00Z"))

    def test_extended_article_dates_keep_calendar_and_instant_semantics(self) -> None:
        for first, second in (
            ("2024-02-29", "2024-02-29"),
            ("2026-06-12T00:00Z", "2026-06-11T19:00-05:00"),
            ("2026-06-12T00:00:00Z", "2026-06-11T19:00:00-05:00"),
            ("2026-06-12T00:00:00.125Z", "2026-06-11T19:00:00.125-05:00"),
            ("2026-06-12T00:00:00", "2026-06-12T00:00:00"),
        ):
            with self.subTest(first=first, second=second):
                self.assertTrue(validator._article_date_values_match(first, second))

    def test_article_sitemap_rejects_week_dates_in_source_and_generated_contracts(self) -> None:
        route = "/writings/first-diagram-is-a-liar/"
        page = self.pages_by_route[route]
        fixture_path = GENERATED_FIXTURE / "article.html.fixture"
        raw = mutate_jsonld_field(fixture_path.read_text(encoding="utf-8"), "dateModified", "2026-06-12T00:00:00Z")
        parser = parse_html(raw)
        findings = validator.validate_article_sitemap_dates(str(fixture_path), parser, page["canonical"], "2026-W24-5T00:00:00Z")
        self.assert_rejected(findings, "article sitemap lastmod is not ISO 8601")
        entries = validator.load_sitemap_entries()
        entries[page["canonical"]] = "2026-W24-5T00:00:00Z"
        findings = validator.validate_article_jsonld_source(self.source_pages, entries)
        self.assert_rejected(findings, "article sitemap lastmod is not ISO 8601")
        findings = validator.validate_generated_seo(fixture_path, parser, page, sitemap_entries={page["canonical"]: "2026-W24-5T00:00:00Z"})
        self.assert_rejected(findings, "article sitemap lastmod is not ISO 8601")

    def _write_mixed_locale_fixture(
        self,
        root: Path,
        sitemap_routes: Iterable[str],
        index_routes: set[str],
    ) -> tuple[Path, Path, Path]:
        manifest_path = root / "manifest.json"
        shutil.copy2(FIXTURE_ROOT / "locale-mixed-manifest.json", manifest_path)

        for relative_path in (
            "index.html",
            "about/index.html",
            "projects/index.html",
            "contact/index.html",
        ):
            source = ROOT / relative_path
            source_target = root / relative_path
            source_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, source_target)

            locale_relative = f"fr/{relative_path}"
            target = root / locale_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = (ROOT / locale_relative).read_text(encoding="utf-8")
            if relative_path == "contact/index.html":
                raw = raw.replace(
                    'name="robots" content="index, follow"',
                    'name="robots" content="noindex, follow"',
                    1,
                )
            target.write_text(raw, encoding="utf-8")

        sitemap_path = root / "sitemap.xml"
        locs = "\n".join(
            f"    <url><loc>{locale_checker.route_url(route)}</loc></url>"
            for route in sorted(sitemap_routes)
        )
        sitemap_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{locs}\n"
            "</urlset>\n",
            encoding="utf-8",
        )

        index_path = root / "search-index.fr.json"
        entries = [{"url": route} for route in sorted(index_routes)]
        index_path.write_text(
            json.dumps(
                {
                    "site": "https://overkillhill.com",
                    "locale": "fr",
                    "generated": "fixture",
                    "count": len(entries),
                    "entries": entries,
                }
            ),
            encoding="utf-8",
        )
        return manifest_path, sitemap_path, index_path

    def _write_legacy_locale_fixture(
        self,
        root: Path,
        sitemap_routes: Iterable[str],
        index_routes: set[str],
    ) -> tuple[Path, Path, Path]:
        manifest_path, sitemap_path, index_path = self._write_mixed_locale_fixture(
            root,
            sitemap_routes,
            index_routes,
        )
        mixed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        locale_spec = mixed_manifest["locales"]["fr"]
        manifest_path.write_text(
            json.dumps({
                "target_locale": "fr",
                "status": locale_spec["status"],
                "indexable": locale_spec["indexable"],
                "metadata_source": locale_spec["metadata_source"],
                "pages": locale_spec["pages"],
            }),
            encoding="utf-8",
        )
        return manifest_path, sitemap_path, index_path

    def _write_unpublished_locale_fixture(
        self,
        root: Path,
        index_routes: set[str],
    ) -> tuple[Path, Path, Path]:
        manifest = json.loads(
            (FIXTURE_ROOT / "locale-mixed-manifest.json").read_text(encoding="utf-8")
        )
        locale_spec = manifest["locales"]["fr"]
        locale_spec["status"] = "unpublished-scaffold"
        locale_spec["indexable"] = False
        for page in locale_spec["pages"]:
            page["status"] = "unpublished-scaffold"
            page["indexable"] = False

        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        for relative_path in (
            "index.html",
            "about/index.html",
            "projects/index.html",
            "contact/index.html",
        ):
            source_target = root / relative_path
            source_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative_path, source_target)

        sitemap_path = root / "sitemap.xml"
        locs = "\n".join(
            f"    <url><loc>{locale_checker.route_url(route)}</loc></url>"
            for route in sorted(source_routes)
        )
        sitemap_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{locs}\n"
            "</urlset>\n",
            encoding="utf-8",
        )

        index_path = root / "search-index.fr.json"
        entries = [{"url": route} for route in sorted(index_routes)]
        index_path.write_text(
            json.dumps(
                {
                    "site": "https://overkillhill.com",
                    "locale": "fr",
                    "generated": "fixture",
                    "count": len(entries),
                    "entries": entries,
                }
            ),
            encoding="utf-8",
        )
        return manifest_path, sitemap_path, index_path

    def test_mixed_locale_requires_promoted_routes_and_excludes_drafts(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}
        draft_routes = {"/fr/contact/"}
        sitemap_routes = source_routes | promoted_routes

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            manifest_path, sitemap_path, index_path = self._write_mixed_locale_fixture(
                root,
                sitemap_routes,
                promoted_routes,
            )
            self.assertFalse(
                locale_checker.validate(
                    manifest_path=manifest_path,
                    sitemap_path=sitemap_path,
                    index_path=index_path,
                    root=root,
                ),
                "mixed locale fixture should pass when promoted routes have complete coverage",
            )

            _, missing_sitemap, valid_index = self._write_mixed_locale_fixture(
                root,
                sitemap_routes - {"/fr/projects/"},
                promoted_routes,
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=missing_sitemap,
                index_path=valid_index,
                root=root,
            )
            self.assertIn(
                "indexable locale route is missing from sitemap.xml: /fr/projects/",
                findings,
            )

            _, valid_sitemap, missing_index = self._write_mixed_locale_fixture(
                root,
                sitemap_routes,
                promoted_routes - {"/fr/about/"},
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=valid_sitemap,
                index_path=missing_index,
                root=root,
            )
            self.assertIn(
                "locale search index is missing routes: /fr/about/",
                findings,
            )

            _, draft_sitemap, draft_index = self._write_mixed_locale_fixture(
                root,
                sitemap_routes | draft_routes,
                promoted_routes | draft_routes,
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=draft_sitemap,
                index_path=draft_index,
                root=root,
            )
            self.assertIn(
                "draft locale route is in sitemap.xml: /fr/contact/",
                findings,
            )
            self.assertIn(
                "draft locale routes appear in the search index: /fr/contact/",
                findings,
            )

    def test_multi_locale_manifest_rejects_duplicate_target_route_within_locale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            shutil.copy2(
                FIXTURE_ROOT / "locale-duplicate-target-routes.json",
                manifest_path,
            )
            shutil.copy2(ROOT / "index.html", root / "index.html")
            sitemap_path = root / "sitemap.xml"
            sitemap_path.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<url><loc>{locale_checker.route_url('/')}</loc></url>"
                "</urlset>",
                encoding="utf-8",
            )
            index_dir = root / "assets" / "data"
            index_dir.mkdir(parents=True)
            for locale in ("fr", "de"):
                (index_dir / f"search-index.{locale}.json").write_text(
                    json.dumps({"locale": locale, "count": 0, "entries": []}),
                    encoding="utf-8",
                )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["locales"]["de"]["pages"][0]["target_route"] = "/de/"
            manifest["locales"]["fr"]["pages"].append(
                copy.deepcopy(manifest["locales"]["fr"]["pages"][0])
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                root=root,
            )

        self.assertIn(
            "locale 'fr' declares duplicate target route: /fr/",
            findings,
        )
        self.assertFalse(
            any("claimed by multiple locales" in finding for finding in findings),
            "a repeated route within one locale must not be reported as a cross-locale conflict",
        )

    def test_multi_locale_manifest_rejects_shared_target_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            shutil.copy2(
                FIXTURE_ROOT / "locale-duplicate-target-routes.json",
                manifest_path,
            )
            shutil.copy2(ROOT / "index.html", root / "index.html")
            sitemap_path = root / "sitemap.xml"
            sitemap_path.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<url><loc>{locale_checker.route_url('/')}</loc></url>"
                "</urlset>",
                encoding="utf-8",
            )
            index_dir = root / "assets" / "data"
            index_dir.mkdir(parents=True)
            for locale in ("fr", "de"):
                (index_dir / f"search-index.{locale}.json").write_text(
                    json.dumps({"locale": locale, "count": 0, "entries": []}),
                    encoding="utf-8",
                )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["locales"]["de"]["pages"][0]["target_route"] = "/de/"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertFalse(
                locale_checker.validate(
                    manifest_path=manifest_path,
                    sitemap_path=sitemap_path,
                    root=root,
                ),
                "independent locale target routes should remain valid",
            )

            shutil.copy2(
                FIXTURE_ROOT / "locale-duplicate-target-routes.json",
                manifest_path,
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                root=root,
            )
            self.assertIn(
                "locale target route is claimed by multiple locales: /fr/ (de, fr)",
                findings,
            )

    def test_legacy_locale_manifest_requires_coverage_and_distinguishes_routes(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}
        draft_route = "/fr/contact/"
        retired_route = "/fr/retired/"
        complete_sitemap = source_routes | promoted_routes

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, index_path = self._write_legacy_locale_fixture(
                root,
                complete_sitemap,
                promoted_routes,
            )
            self.assertFalse(
                locale_checker.validate(
                    manifest_path=manifest_path,
                    sitemap_path=sitemap_path,
                    index_path=index_path,
                    root=root,
                ),
                "valid legacy single-locale manifest should pass complete coverage",
            )

            _, missing_sitemap, complete_index = self._write_legacy_locale_fixture(
                root,
                complete_sitemap - {"/fr/projects/"},
                promoted_routes,
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=missing_sitemap,
                index_path=complete_index,
                root=root,
            )
            self.assertIn(
                "indexable locale route is missing from sitemap.xml: /fr/projects/",
                findings,
            )

            _, complete_sitemap_path, missing_index = self._write_legacy_locale_fixture(
                root,
                complete_sitemap,
                promoted_routes - {"/fr/about/"},
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=complete_sitemap_path,
                index_path=missing_index,
                root=root,
            )
            self.assertIn(
                "locale search index is missing routes: /fr/about/",
                findings,
            )

            _, draft_sitemap, draft_index = self._write_legacy_locale_fixture(
                root,
                complete_sitemap | {draft_route, retired_route},
                promoted_routes | {draft_route, retired_route},
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=draft_sitemap,
                index_path=draft_index,
                root=root,
            )
            self.assertIn(
                f"draft locale route is in sitemap.xml: {draft_route}",
                findings,
            )
            self.assertIn(
                f"draft locale routes appear in the search index: {draft_route}",
                findings,
            )
            self.assertIn(
                f"locale sitemap contains undeclared routes: {retired_route}",
                findings,
            )
            self.assertIn(
                f"locale search index contains undeclared routes: {retired_route}",
                findings,
            )

    def test_empty_legacy_locale_manifest_cannot_pass_coverage_vacuously(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}

        for with_locale_routes in (False, True):
            with self.subTest(with_locale_routes=with_locale_routes):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    manifest_path, sitemap_path, index_path = self._write_legacy_locale_fixture(
                        root,
                        source_routes | promoted_routes if with_locale_routes else source_routes,
                        promoted_routes if with_locale_routes else set(),
                    )
                    shutil.copy2(
                        FIXTURE_ROOT / "locale-empty-legacy-manifest.json",
                        manifest_path,
                    )
                    findings = locale_checker.validate(
                        manifest_path=manifest_path,
                        sitemap_path=sitemap_path,
                        index_path=index_path,
                        root=root,
                    )
                    self.assertEqual(
                        findings,
                        ["manifest locale 'fr' pages must be a non-empty list"],
                    )

    def test_locale_checker_reports_explicit_robots_boundary_values(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}
        sitemap_routes = source_routes | promoted_routes
        cases = (
            (
                "fr/index.html",
                "noindex, follow",
                "manifest=indexable, rendered=noindex",
            ),
            (
                "fr/contact/index.html",
                "index, follow",
                "manifest=noindex, rendered=indexable",
            ),
        )

        for relative_path, robots_value, expected_boundary in cases:
            with self.subTest(relative_path=relative_path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest_path, sitemap_path, index_path = self._write_mixed_locale_fixture(
                    root,
                    sitemap_routes,
                    promoted_routes,
                )
                target = root / relative_path
                target.write_text(
                    mutate_meta(
                        target.read_text(encoding="utf-8"),
                        "meta:robots",
                        robots_value,
                    ),
                    encoding="utf-8",
                )
                findings = locale_checker.validate(
                    manifest_path=manifest_path,
                    sitemap_path=sitemap_path,
                    index_path=index_path,
                    root=root,
                )
                self.assertIn(
                    f"{relative_path}: robots indexing boundary mismatch: {expected_boundary}",
                    findings,
                )

    def test_locale_search_index_rejects_malformed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index_path = Path(directory) / "search-index.fr.json"
            cases = (
                (None, "must be an object with a non-empty string URL"),
                ("invalid", "must be an object with a non-empty string URL"),
                ({}, "must have a non-empty string URL"),
                ({"url": None}, "must have a non-empty string URL"),
                ({"url": 7}, "must have a non-empty string URL"),
                ({"url": []}, "must have a non-empty string URL"),
                ({"url": {}}, "must have a non-empty string URL"),
                ({"url": ""}, "must have a non-empty string URL"),
                ({"url": " "}, "must have a non-empty string URL"),
            )
            for entry, expected in cases:
                with self.subTest(entry=entry):
                    index_path.write_text(json.dumps({
                        "locale": "fr", "count": 2,
                        "entries": [entry, {"url": "/fr/retired/"}],
                    }), encoding="utf-8")
                    findings = []
                    locale_checker.check_search_index(
                        index_path, set(), "fr", findings,
                        draft_routes=set(), require_routes=False,
                    )
                    self.assertIn(
                        f"locale search index entry 0 {expected}",
                        findings,
                    )
                    self.assertIn("locale search index contains undeclared routes: /fr/retired/", findings)

    def test_published_locale_rejects_search_index_entry_without_url(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, index_path = self._write_mixed_locale_fixture(
                root,
                source_routes | promoted_routes,
                promoted_routes,
            )
            index_path.write_text(json.dumps({
                "locale": "fr",
                "count": 2,
                "entries": [{}, None],
            }), encoding="utf-8")

            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                index_path=index_path,
                root=root,
            )

            self.assertIn(
                "locale search index entry 0 must have a non-empty string URL",
                findings,
            )
            self.assertIn(
                "locale search index entry 1 must be an object with a non-empty string URL",
                findings,
            )

    def test_unpublished_locale_rejects_non_object_search_index_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, index_path = (
                self._write_unpublished_locale_fixture(root, set())
            )
            index_path.write_text(json.dumps({
                "locale": "fr",
                "count": 1,
                "entries": [None],
            }), encoding="utf-8")

            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                index_path=index_path,
                root=root,
            )

            self.assertIn(
                "locale search index entry 0 must be an object with a non-empty string URL",
                findings,
            )

    def test_locale_search_index_rejects_non_object_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index_path = Path(directory) / "search-index.fr.json"
            index_path.write_text("[]", encoding="utf-8")
            findings = []
            locale_checker.check_search_index(
                index_path, set(), "fr", findings,
                draft_routes=set(), require_routes=False,
            )
            self.assertIn("locale search index must be an object", findings)

    def test_unpublished_locale_rejects_stale_search_index_routes(self) -> None:
        declared_route = "/fr/about/"
        unrelated_route = "/fr/retired/"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, valid_index = (
                self._write_unpublished_locale_fixture(root, set())
            )
            self.assertFalse(
                locale_checker.validate(
                    manifest_path=manifest_path,
                    sitemap_path=sitemap_path,
                    index_path=valid_index,
                    root=root,
                ),
                "unpublished locale fixture should pass with an empty search index",
            )

            _, _, stale_index = self._write_unpublished_locale_fixture(
                root,
                {declared_route, unrelated_route},
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                index_path=stale_index,
                root=root,
            )
            self.assertIn(
                f"draft locale routes appear in the search index: {declared_route}",
                findings,
            )
            self.assertIn(
                f"locale search index contains undeclared routes: {unrelated_route}",
                findings,
            )

    def test_unpublished_locale_rejects_generated_target_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, index_path = (
                self._write_unpublished_locale_fixture(root, set())
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            target_path = manifest["locales"]["fr"]["pages"][0]["target_path"]
            target_file = root / target_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text("<!doctype html><title>Not published</title>", encoding="utf-8")

            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                index_path=index_path,
                root=root,
            )

            self.assertIn(
                f"unpublished scaffold contains target page: {target_path}",
                findings,
            )

    def test_unpublished_locale_rejects_undeclared_generated_target_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, index_path = (
                self._write_unpublished_locale_fixture(root, set())
            )
            orphan_path = root / "fr" / "retired" / "index.html"
            orphan_path.parent.mkdir(parents=True)
            orphan_path.write_text("<!doctype html><title>Unpublished</title>", encoding="utf-8")

            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                index_path=index_path,
                root=root,
            )

            self.assertIn(
                "unpublished scaffold contains undeclared target page: fr/retired/index.html",
                findings,
            )

    def test_unpublished_locale_rejects_sitemap_target_route(self) -> None:
        target_route = "/fr/about/"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, index_path = (
                self._write_unpublished_locale_fixture(root, set())
            )
            sitemap = sitemap_path.read_text(encoding="utf-8")
            sitemap_path.write_text(
                sitemap.replace(
                    "</urlset>",
                    f"<url><loc>{locale_checker.route_url(target_route)}</loc></url>\n</urlset>",
                ),
                encoding="utf-8",
            )

            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=sitemap_path,
                index_path=index_path,
                root=root,
            )

            self.assertIn(
                f"unpublished target route is in sitemap.xml: {target_route}",
                findings,
            )

    def test_mixed_locale_rejects_undeclared_search_index_routes(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, sitemap_path, index_path = self._write_mixed_locale_fixture(
                root,
                source_routes | promoted_routes,
                promoted_routes | {"/fr/retired/"},
            )
            findings = locale_checker.validate(
                manifest_path=root / "manifest.json",
                sitemap_path=sitemap_path,
                index_path=index_path,
                root=root,
            )

            self.assertIn(
                "locale search index contains undeclared routes: /fr/retired/",
                findings,
            )

    def test_mixed_locale_rejects_undeclared_sitemap_routes_but_keeps_english_routes(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, valid_sitemap, valid_index = self._write_mixed_locale_fixture(
                root,
                source_routes | promoted_routes,
                promoted_routes,
            )
            self.assertFalse(
                locale_checker.validate(
                    manifest_path=root / "manifest.json",
                    sitemap_path=valid_sitemap,
                    index_path=valid_index,
                    root=root,
                ),
                "valid English source routes must not be treated as undeclared locale routes",
            )

            _, invalid_sitemap, invalid_index = self._write_mixed_locale_fixture(
                root,
                source_routes | promoted_routes | {"/fr/retired/"},
                promoted_routes,
            )
            findings = locale_checker.validate(
                manifest_path=root / "manifest.json",
                sitemap_path=invalid_sitemap,
                index_path=invalid_index,
                root=root,
            )

            self.assertIn(
                "locale sitemap contains undeclared routes: /fr/retired/",
                findings,
            )

    def test_mixed_locale_rejects_duplicate_localized_sitemap_routes(self) -> None:
        source_routes = {"/", "/about/", "/projects/", "/contact/"}
        promoted_routes = {"/fr/", "/fr/about/", "/fr/projects/"}
        unique_routes = sorted(source_routes | promoted_routes)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, sitemap_path, index_path = self._write_mixed_locale_fixture(
                root,
                unique_routes,
                promoted_routes,
            )
            self.assertFalse(
                locale_checker.validate(
                    manifest_path=manifest_path,
                    sitemap_path=sitemap_path,
                    index_path=index_path,
                    root=root,
                ),
                "unique mixed-locale sitemap should pass",
            )

            _, duplicate_sitemap, duplicate_index = self._write_mixed_locale_fixture(
                root,
                unique_routes + ["/fr/about/"],
                promoted_routes,
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=duplicate_sitemap,
                index_path=duplicate_index,
                root=root,
            )
            self.assertIn(
                "locale sitemap contains duplicate routes: /fr/about/ (appears 2 times)",
                findings,
            )

            _, english_duplicate_sitemap, english_duplicate_index = (
                self._write_mixed_locale_fixture(
                    root,
                    unique_routes + ["/about/"],
                    promoted_routes,
                )
            )
            findings = locale_checker.validate(
                manifest_path=manifest_path,
                sitemap_path=english_duplicate_sitemap,
                index_path=english_duplicate_index,
                root=root,
            )
            self.assertFalse(
                findings,
                "English source route duplicates must stay outside the localized check",
            )

    def test_duplicate_sitemap_locations_are_rejected_with_conflicting_dates(self) -> None:
        location = "https://overkillhill.com/writings/example/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                "<urlset>"
                f"<url><loc>{location}</loc><lastmod>2026-05-24</lastmod></url>"
                "<url><lastmod>2026-05-25</lastmod></url>"
                "<url><loc>https://overkillhill.com/about/</loc></url>"
                f"<url><loc>{location}</loc><lastmod>2026-05-28</lastmod></url>"
                "<url><loc>https://overkillhill.com/contact/</loc></url>"
                f"<url><loc>{location}</loc><lastmod>2026-05-30</lastmod></url>"
                "</urlset>",
                encoding="utf-8",
            )

            self.assertEqual(
                validator._sitemap_entries_from_path(sitemap_path),
                [
                    (location, "2026-05-24"),
                    ("https://overkillhill.com/about/", None),
                    (location, "2026-05-28"),
                    ("https://overkillhill.com/contact/", None),
                    (location, "2026-05-30"),
                ],
                "the existing sitemap parser contract must remain location/date pairs",
            )
            findings = validator.validate_sitemap_duplicates(sitemap_path)
            text = findings_text(findings)
            self.assertIn(
                (
                    f"duplicate sitemap location: {location} appears 3 times "
                    "at sitemap entry positions 1, 4, 6"
                ),
                text,
            )
            self.assertIn(
                (
                    f"conflicting duplicate sitemap lastmod values for {location}: "
                    "position 1: '2026-05-24'; position 4: '2026-05-28'; "
                    "position 6: '2026-05-30'"
                ),
                text,
            )
            self.assertIn("2026-05-24", text)
            self.assertIn("2026-05-28", text)
            self.assertEqual(
                validator.load_sitemap_entries(sitemap_path)[location],
                "2026-05-24",
                "duplicate parsing must not let a later lastmod silently win",
            )

    def test_sitemap_recovery_rejects_mismatched_element_prefixes(self) -> None:
        location = f"{validator.SITE_ORIGIN}/about/"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            for invalid_entry in (
                f"<sm:url><sm:loc>{location}</sm:loc></x:url>",
                f"<sm:url><sm:loc>{location}</x:loc></sm:url>",
            ):
                with self.subTest(entry=invalid_entry):
                    path.write_text('<sm:urlset xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:x="urn:other">' + invalid_entry + '</sm:urlset>', encoding="utf-8")
                    entries, findings = validator._sitemap_entries_with_positions_and_findings_from_path(path)
                    self.assertEqual([], entries)
                    self.assertIn("mismatched", findings_text(findings))

    def test_sitemap_recovery_rejects_mismatched_lastmod_names(self) -> None:
        location = f"{validator.SITE_ORIGIN}/about/"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sitemap.xml"
            path.write_text('<sm:urlset xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:x="urn:other"><sm:url>'
                f'<sm:loc>{location}</sm:loc><sm:lastmod>2026-01-01</x:lastmod>'
                '</sm:url></sm:urlset>', encoding="utf-8")
            entries, findings = validator._sitemap_entries_with_positions_and_findings_from_path(path)
            self.assertIn("lastmod", findings_text(findings))
            self.assertNotIn((1, location, "2026-01-01"), entries)

    def test_multiple_lastmod_values_in_one_sitemap_entry_are_reported(self) -> None:
        location = f"{validator.SITE_ORIGIN}/about/"
        first_date = "2026-05-24"
        second_date = "2026-05-28"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                "<urlset>"
                f"<url><loc>{location}</loc>"
                f"<lastmod>{first_date}</lastmod>"
                f"<lastmod>{second_date}</lastmod></url>"
                "</urlset>",
                encoding="utf-8",
            )

            self.assertEqual(
                validator._sitemap_entries_from_path(sitemap_path),
                [(location, first_date)],
                "the fixture must exercise the parser's existing first-value behavior",
            )
            findings = validator.validate_sitemap_duplicates(sitemap_path)
            self.assertEqual(len(findings), 1, findings_text(findings))
            self.assertIn(
                (
                    "sitemap URL entry at position 1 must contain at most one "
                    f"<lastmod> element; found 2 (values: '{first_date}', "
                    f"'{second_date}')"
                ),
                findings_text(findings),
            )

    def test_namespace_prefixed_sitemap_tags_preserve_entries_and_diagnostics(self) -> None:
        location = f"{validator.SITE_ORIGIN}/about/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                '<sm:urlset xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<sm:url><sm:loc>{location}</sm:loc>"
                "<sm:lastmod>2026-05-24</sm:lastmod></sm:url>"
                "<sm:url><sm:lastmod>2026-05-25</sm:lastmod></sm:url>"
                f"<sm:url><sm:loc>{location}</sm:loc>"
                "<sm:lastmod>2026-05-28</sm:lastmod></sm:url>"
                "</sm:urlset>",
                encoding="utf-8",
            )

            self.assertEqual(
                validator._sitemap_entries_with_positions_from_path(sitemap_path),
                [(1, location, "2026-05-24"), (3, location, "2026-05-28")],
            )
            text = findings_text(validator.validate_sitemap_duplicates(sitemap_path))
            self.assertIn(
                "sitemap URL entry at position 2 must contain exactly one "
                "<loc> element; found 0",
                text,
            )
            self.assertIn(
                f"duplicate sitemap location: {location} appears 2 times "
                "at sitemap entry positions 1, 3",
                text,
            )
            self.assertIn(
                f"conflicting duplicate sitemap lastmod values for {location}: "
                "position 1: '2026-05-24'; position 3: '2026-05-28'",
                text,
            )

    def test_namespace_prefixed_sitemap_tags_survive_malformed_xml_recovery(self) -> None:
        valid_before = f"{validator.SITE_ORIGIN}/about/"
        valid_after = f"{validator.SITE_ORIGIN}/contact/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                '<sm:urlset xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"<sm:url><sm:loc>{valid_before}</sm:loc></sm:url>"
                "<sm:url><sm:loc>https://overkillhill.com/broken/"
                "</sm:url>"
                f"<sm:url><sm:loc>{valid_after}</sm:loc>"
                "<sm:lastmod>2026-05-29</sm:lastmod></sm:url>"
                "</sm:urlset>",
                encoding="utf-8",
            )

            self.assertEqual(
                validator._sitemap_entries_from_path(sitemap_path),
                [(valid_before, None), (valid_after, "2026-05-29")],
            )
            text = findings_text(validator.validate_sitemap_duplicates(sitemap_path))
            self.assertIn(
                "sitemap URL entry at position 2 has malformed <loc> element structure",
                text,
            )
            self.assertEqual(text.count("sitemap URL entry"), 1, text)

    def test_identical_duplicate_sitemap_locations_are_rejected(self) -> None:
        location = "https://overkillhill.com/about/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                "<urlset>"
                f"<url><loc>{location}</loc><lastmod>2026-05-28</lastmod></url>"
                f"<url><loc>{location}</loc><lastmod>2026-05-28</lastmod></url>"
                "</urlset>",
                encoding="utf-8",
            )

            findings = validator.validate_sitemap_duplicates(sitemap_path)
            text = findings_text(findings)
            self.assertIn(
                f"duplicate sitemap location: {location} appears 2 times",
                text,
            )
            self.assertIn(
                (
                    f"duplicate sitemap location: {location} appears 2 times "
                    "at sitemap entry positions 1, 2"
                ),
                text,
            )
            self.assertNotIn("conflicting duplicate sitemap lastmod values", text)

    def test_percent_encoded_unreserved_sitemap_aliases_are_duplicates(self) -> None:
        literal_location = "https://overkillhill.com/about/"
        encoded_location = "https://overkillhill.com/%61bout/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                "<urlset>"
                f"<url><loc>{literal_location}</loc>"
                "<lastmod>2026-05-24</lastmod></url>"
                f"<url><loc>{encoded_location}</loc>"
                "<lastmod>2026-05-28</lastmod></url>"
                "</urlset>",
                encoding="utf-8",
            )

            findings = validator.validate_sitemap_duplicates(sitemap_path)
            text = findings_text(findings)
            self.assertIn(
                (
                    "duplicate sitemap location after percent-encoding "
                    "normalization: "
                    f"{literal_location} appears 2 times at sitemap entry "
                    "positions 1, 2"
                ),
                text,
            )
            self.assertIn(literal_location, text)
            self.assertIn(encoded_location, text)
            self.assertIn(
                (
                    f"conflicting duplicate sitemap lastmod values for "
                    f"{literal_location}: position 1: '2026-05-24'; "
                    "position 2: '2026-05-28'"
                ),
                text,
            )
            self.assertEqual(
                validator.load_sitemap_entries(sitemap_path),
                {
                    literal_location: "2026-05-24",
                    encoded_location: "2026-05-28",
                },
                "duplicate detection must not change the sitemap inventory API",
            )

    def test_percent_encoded_reserved_sitemap_routes_remain_distinct(self) -> None:
        literal_slash_route = "https://overkillhill.com/a/b/"
        encoded_slash_route = "https://overkillhill.com/a%2Fb/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                "<urlset>"
                f"<url><loc>{literal_slash_route}</loc></url>"
                f"<url><loc>{encoded_slash_route}</loc></url>"
                "</urlset>",
                encoding="utf-8",
            )

            self.assertEqual(
                validator.validate_sitemap_duplicates(sitemap_path),
                [],
                "an encoded slash must not be collapsed into a route separator",
            )

    def test_sitemap_url_blocks_require_exactly_one_usable_location(self) -> None:
        valid_before = f"{validator.SITE_ORIGIN}/about/"
        valid_after = f"{validator.SITE_ORIGIN}/contact/"
        invalid_blocks = (
            (
                "stray-closing-url",
                "</url>",
                "has a closing </url> without an opening <url>",
            ),
            (
                "unclosed-url-block",
                "<url><loc>https://overkillhill.com/unclosed/</loc>",
                "is missing closing </url> before the next <url>",
            ),
            (
                "unclosed-location",
                "<url><loc>https://overkillhill.com/unclosed/</url>",
                "has malformed <loc> element structure",
            ),
            (
                "reversed-location-tags",
                "<url></loc><loc>https://overkillhill.com/reversed/</url>",
                "has malformed <loc> element structure",
            ),
            (
                "missing",
                "<url><lastmod>2026-05-28</lastmod></url>",
                "must contain exactly one <loc> element; found 0",
            ),
            (
                "empty",
                "<url><loc></loc></url>",
                "has an empty <loc> value",
            ),
            (
                "whitespace-only",
                "<url><loc> \n\t </loc></url>",
                "has an empty <loc> value",
            ),
            (
                "duplicate",
                (
                    f"<url><loc>{validator.SITE_ORIGIN}/first/</loc>"
                    f"<loc>{validator.SITE_ORIGIN}/second/</loc></url>"
                ),
                "must contain exactly one <loc> element; found 2",
            ),
            (
                "nested-markup",
                (
                    f"<url><loc>{validator.SITE_ORIGIN}/nested/"
                    "<path>malformed</path></loc></url>"
                ),
                "has malformed markup inside <loc>",
            ),
        )

        for case, invalid_block, expected_detail in invalid_blocks:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                sitemap_path = Path(directory) / "sitemap.xml"
                sitemap_path.write_text(
                    "<urlset>"
                    f"<url><loc>{valid_before}</loc></url>"
                    f"{invalid_block}"
                    f"<url><loc>{valid_after}</loc></url>"
                    "</urlset>",
                    encoding="utf-8",
                )

                findings = validator.validate_sitemap_duplicates(sitemap_path)
                text = findings_text(findings)
                self.assertEqual(len(findings), 1, text)
                self.assertIn(
                    f"sitemap URL entry at position 2 {expected_detail}",
                    text,
                )
                self.assertEqual(
                    validator._sitemap_entries_from_path(sitemap_path),
                    [(valid_before, None), (valid_after, None)],
                    "invalid URL blocks must not enter the usable sitemap inventory",
                )
                self.assertEqual(
                    validator.load_sitemap_entries(sitemap_path),
                    {valid_before: None, valid_after: None},
                )

    def test_unclosed_final_sitemap_url_is_reported(self) -> None:
        valid = f"{validator.SITE_ORIGIN}/about/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                f"<urlset><url><loc>{valid}</loc></url>"
                "<url><loc>https://overkillhill.com/unclosed/</loc>",
                encoding="utf-8",
            )

            findings = validator.validate_sitemap_duplicates(sitemap_path)
            self.assertIn(
                "sitemap URL entry at position 2 is missing closing </url>",
                findings_text(findings),
            )
            self.assertEqual(
                validator._sitemap_entries_from_path(sitemap_path),
                [(valid, None)],
                "an unclosed final URL block must not enter the usable inventory",
            )

    def test_broken_sitemap_document_boundaries_are_reported(self) -> None:
        valid = f"{validator.SITE_ORIGIN}/about/"
        cases = (
            (
                "missing-opening-urlset",
                f"<url><loc>{valid}</loc></url></urlset>",
                "found 0 opening and 1 closing",
            ),
            (
                "missing-closing-urlset",
                f"<urlset><url><loc>{valid}</loc></url>",
                "found 1 opening and 0 closing",
            ),
            (
                "multiple-urlset-roots",
                (
                    f"<urlset><url><loc>{valid}</loc></url></urlset>"
                    "<urlset></urlset>"
                ),
                "found 2 opening and 2 closing",
            ),
            (
                "url-entry-outside-urlset",
                (
                    f"<urlset></urlset><url><loc>{valid}</loc></url>"
                ),
                "sitemap URL entries must be inside the <urlset> document boundaries",
            ),
            (
                "mismatched-urlset-prefixes",
                (
                    '<a:urlset xmlns:a="urn:a" xmlns:b="urn:b">'
                    f"<url><loc>{valid}</loc></url></b:urlset>"
                ),
                "sitemap document has malformed <urlset> boundaries",
            ),
            (
                "wrong-document-root",
                f"<sitemap><url><loc>{valid}</loc></url></sitemap>",
                "sitemap document root must be <urlset>",
            ),
        )

        for case, sitemap, expected_error in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                sitemap_path = Path(directory) / "sitemap.xml"
                sitemap_path.write_text(sitemap, encoding="utf-8")

                entries, findings = (
                    validator._sitemap_entries_with_positions_and_findings_from_path(
                        sitemap_path
                    )
                )
                text = findings_text(findings)
                self.assertIn(expected_error, text)
                self.assertTrue(
                    entries,
                    "the fixture should retain any recoverable entry to prove "
                    "a partial inventory cannot hide the wrapper failure",
                )
                self.assertIn(
                    expected_error,
                    findings_text(validator.validate_sitemap_duplicates(sitemap_path)),
                )

    def test_urlset_markup_in_comments_does_not_satisfy_document_boundaries(self) -> None:
        valid = f"{validator.SITE_ORIGIN}/about/"
        with tempfile.TemporaryDirectory() as directory:
            sitemap_path = Path(directory) / "sitemap.xml"
            sitemap_path.write_text(
                f"<!-- <urlset> --><url><loc>{valid}</loc></url></urlset>",
                encoding="utf-8",
            )

            findings = validator.validate_sitemap_duplicates(sitemap_path)
            self.assertIn(
                "found 0 opening and 1 closing",
                findings_text(findings),
            )
            self.assertEqual(
                validator._sitemap_entries_from_path(sitemap_path),
                [(valid, None)],
                "recoverable URLs must not make a missing document wrapper pass",
            )

    def test_public_inventory_excludes_test_fixtures(self) -> None:
        pages = validator.find_html_files()
        self.assertIn(ROOT / "index.html", pages)
        csp_fixtures = sorted((ROOT / "tests" / "fixtures" / "csp").glob("*.html"))
        self.assertTrue(csp_fixtures, "expected committed CSP fixtures for this boundary check")
        self.assertTrue(set(csp_fixtures).isdisjoint(pages))
        self.assertFalse(any("tests" in path.relative_to(ROOT).parts for path in pages))
        for name in ("audit-site", "build-search-index", "check-links"):
            spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
            if spec is None or spec.loader is None:
                self.fail(f"could not load scripts/{name}.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if name == "audit-site":
                self.assertFalse(any("tests" in path.relative_to(ROOT).parts
                                     for path in module.iter_html_files()))
            elif name == "build-search-index":
                for fixture in (ROOT / "tests" / "fixtures" / "csp").glob("*.html"):
                    self.assertEqual(module.process_file(fixture), [])
            else:
                pages = module.iter_html_files()
                self.assertTrue(set(csp_fixtures).isdisjoint(pages))
                self.assertFalse(any("tests" in path.relative_to(ROOT).parts for path in pages))

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_data = json.loads(FIXTURES.read_text(encoding="utf-8"))
        cls.source_pages, source_findings = validator.load_source_manifest()
        if source_findings:
            raise AssertionError(findings_text(source_findings))
        cls.pages_by_route = {
            page["route"]: page for page in cls.source_pages
        }
        cls.locale_contract, locale_findings = validator.load_locale_seo_contract()
        if locale_findings:
            raise AssertionError(findings_text(locale_findings))

    def test_released_locale_pages_use_social_card_contract(self) -> None:
        for relative_path, contract in self.locale_contract.items():
            if not contract["indexable"]:
                continue
            path = ROOT / relative_path
            parser = parse_html(path.read_text(encoding="utf-8"))
            self.assertFalse(
                validator.validate_generated_seo(path, parser, None, contract),
                f"released locale page has social-card drift: {relative_path}",
            )

    def test_released_locale_social_card_drift_is_rejected(self) -> None:
        path = ROOT / "fr" / "index.html"
        parser = parse_html(path.read_text(encoding="utf-8"))
        parser.meta["twitter:image:alt"] = ["different localized social preview"]
        findings = validator.validate_generated_seo(
            path,
            parser,
            None,
            self.locale_contract["fr/index.html"],
        )
        self.assert_rejected(findings, "social-card image alt mismatch")

    def test_draft_locale_social_card_drift_remains_exempt(self) -> None:
        path = ROOT / "de" / "index.html"
        parser = parse_html(path.read_text(encoding="utf-8"))
        parser.meta["twitter:image"] = ["https://example.com/drifted-card.png"]
        parser.meta["twitter:image:alt"] = ["different draft social preview"]
        self.assertFalse(
            validator.validate_generated_seo(
                path,
                parser,
                None,
                self.locale_contract["de/index.html"],
            ),
            "noindex locale pilots should remain exempt until promotion",
        )

    def test_locale_robots_boundary_mismatches_are_rejected_with_valid_controls(self) -> None:
        controls = (
            ("fr/index.html", True),
            ("de/index.html", False),
            ("es/index.html", False),
        )
        for relative_path, expected_indexable in controls:
            with self.subTest(control=relative_path):
                path = ROOT / relative_path
                contract = self.locale_contract[relative_path]
                parser = parse_html(path.read_text(encoding="utf-8"))
                self.assertEqual(contract["indexable"], expected_indexable)
                self.assertEqual(not parser.is_noindex, expected_indexable)
                self.assertFalse(
                    validator.validate_generated_seo(path, parser, None, contract),
                    f"valid locale boundary should pass: {relative_path}",
                )

        mismatch_cases = (
            (
                "fr/index.html",
                "noindex, follow",
                "manifest=indexable, rendered=noindex",
            ),
            (
                "de/index.html",
                "index, follow",
                "manifest=noindex, rendered=indexable",
            ),
        )
        for relative_path, robots_value, expected_boundary in mismatch_cases:
            with self.subTest(mismatch=relative_path):
                path = ROOT / relative_path
                raw = mutate_meta(
                    path.read_text(encoding="utf-8"),
                    "meta:robots",
                    robots_value,
                )
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(raw),
                    None,
                    self.locale_contract[relative_path],
                )
                self.assertIn(
                    f"{relative_path}: robots indexing boundary mismatch: {expected_boundary}",
                    findings_text(findings),
                )

    def test_locale_robots_boundary_mismatches_are_reported_on_pilot_subpages(self) -> None:
        manifest = json.loads(
            (ROOT / "i18n" / "pilot" / "manifest.json").read_text(encoding="utf-8")
        )
        locales = manifest["locales"]
        indexable_locale = next(
            locale for locale, entry in locales.items() if entry["indexable"]
        )
        draft_locale = next(
            locale for locale, entry in locales.items() if not entry["indexable"]
        )

        def non_home_page(locale: str) -> dict:
            entry = locales[locale]
            return next(
                page
                for page in entry["pages"]
                if page["source_route"] != "/"
                and page.get("indexable", entry["indexable"]) == entry["indexable"]
            )

        indexable_page = non_home_page(indexable_locale)
        draft_page = non_home_page(draft_locale)
        self.assertEqual(
            indexable_page["source_route"],
            draft_page["source_route"],
            "pilot mismatch cases should exercise the same non-home source route",
        )

        cases = (
            (
                indexable_page,
                True,
                "noindex, follow",
                "manifest=indexable, rendered=noindex",
            ),
            (
                draft_page,
                False,
                "index, follow",
                "manifest=noindex, rendered=indexable",
            ),
        )
        for page, declared_indexable, robots_value, expected_boundary in cases:
            relative_path = page["target_path"]
            with self.subTest(relative_path=relative_path):
                path = ROOT / relative_path
                contract = self.locale_contract[relative_path]
                self.assertEqual(contract["indexable"], declared_indexable)

                original_raw = path.read_text(encoding="utf-8")
                original_parser = parse_html(original_raw)
                self.assertEqual(not original_parser.is_noindex, declared_indexable)
                self.assertFalse(
                    validator.validate_generated_seo(path, original_parser, None, contract),
                    f"valid pilot subpage boundary should pass: {relative_path}",
                )

                if not declared_indexable:
                    self.assertTrue(
                        original_parser.is_noindex,
                        f"draft subpage control must remain noindex: {relative_path}",
                    )

                mutated_raw = mutate_meta(original_raw, "meta:robots", robots_value)
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(mutated_raw),
                    None,
                    contract,
                )
                self.assertIn(
                    f"{relative_path}: robots indexing boundary mismatch: {expected_boundary}",
                    findings_text(findings),
                )

    def test_locale_robots_use_loaded_page_indexability_override(self) -> None:
        manifest = {
            "locales": {
                "fr": {
                    "indexable": True,
                    "metadata_source": "localized-page",
                    "pages": [
                        {"target_path": "fr/index.html"},
                        {
                            "target_path": "fr/contact/index.html",
                            "indexable": False,
                        },
                    ],
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "locale-manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(validator, "LOCALE_MANIFEST", manifest_path):
                contract, load_findings = validator.load_locale_seo_contract()

        self.assertFalse(load_findings, findings_text(load_findings))
        self.assertTrue(contract["fr/index.html"]["indexable"])
        self.assertFalse(contract["fr/contact/index.html"]["indexable"])

        cases = (
            (
                "fr/index.html",
                True,
                "index, follow",
                "noindex, follow",
                "manifest=indexable, rendered=noindex",
            ),
            (
                "fr/contact/index.html",
                False,
                "noindex, follow",
                "index, follow",
                "manifest=noindex, rendered=indexable",
            ),
        )
        for relative_path, indexable, valid_robots, invalid_robots, boundary in cases:
            with self.subTest(relative_path=relative_path):
                path = ROOT / relative_path
                page_contract = contract[relative_path]
                self.assertEqual(page_contract["indexable"], indexable)

                raw = path.read_text(encoding="utf-8")
                valid_page = parse_html(mutate_meta(raw, "meta:robots", valid_robots))
                self.assertFalse(
                    validator.validate_generated_seo(path, valid_page, None, page_contract),
                    f"robots metadata should match the loaded page contract: {relative_path}",
                )

                invalid_page = parse_html(mutate_meta(raw, "meta:robots", invalid_robots))
                findings = validator.validate_generated_seo(
                    path,
                    invalid_page,
                    None,
                    page_contract,
                )
                expected_finding = (
                    f"{relative_path}: robots indexing boundary mismatch: {boundary}"
                )
                self.assertIn(expected_finding, findings_text(findings))

    def test_indexable_locale_keeps_localized_metadata_ownership(self) -> None:
        relative_path = "fr/index.html"
        path = ROOT / relative_path
        contract = copy.deepcopy(self.locale_contract[relative_path])
        contract["metadata_source"] = "source-manifest"
        findings = validator.validate_generated_seo(
            path,
            parse_html(path.read_text(encoding="utf-8")),
            None,
            contract,
        )
        self.assertIn(
            (
                f"{relative_path}: indexable locale page must own its social-card "
                "metadata as localized-page"
            ),
            findings_text(findings),
        )

    def test_unowned_en_gb_and_es_mx_pages_keep_external_boundary_exemption(self) -> None:
        for relative_path in ("en-gb/index.html", "es-mx/index.html"):
            with self.subTest(path=relative_path):
                path = ROOT / relative_path
                raw = mutate_meta(
                    path.read_text(encoding="utf-8"),
                    "meta:robots",
                    "index, follow",
                )
                self.assertFalse(
                    validator.validate_generated_seo(path, parse_html(raw), None),
                    f"unowned external locale path should keep its existing exemption: {relative_path}",
                )

    def test_noindex_article_jsonld_date_contract_remains_exempt(self) -> None:
        page = self.pages_by_route["/writings/biases-as-constants/"]
        source_path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        generated_path = ROOT / page["path"]
        self.assertFalse(
            validator.validate_article_jsonld_source([page]),
            "noindex source drafts should remain outside the published date contract",
        )
        self.assertFalse(
            validator.validate_generated_seo(
                generated_path,
                parse_html(generated_path.read_text(encoding="utf-8")),
                page,
            ),
            "noindex generated drafts should remain outside the published date contract",
        )
        self.assertIn('"@type": "Article"', source_path.read_text(encoding="utf-8"))

    def test_duplicate_article_url_conflict_uses_stable_identity(self) -> None:
        mutation = self.fixture_data["duplicate_article_url_mismatch"]
        articles = [
            {
                "@type": "Article",
                "@id": "https://overkillhill.com/writings/shared-identity/#article",
                "headline": "First representation",
                "datePublished": "2026-04-07",
                "dateModified": "2026-05-24",
                "url": "https://overkillhill.com/writings/first/",
            },
            {
                "@type": "Article",
                "@id": "https://overkillhill.com/writings/shared-identity/#article",
                "headline": "Second representation",
                "datePublished": "2026-04-07",
                "dateModified": "2026-05-24",
                "url": mutation["value"],
            },
        ]
        parser = parse_html(
            '<script type="application/ld+json">'
            + json.dumps({"@graph": articles})
            + "</script>"
        )
        findings = validator.validate_article_jsonld_dates(
            "same-article-id.fixture",
            parser,
        )
        self.assert_rejected(findings, mutation["expected"])
        diagnostic = findings_text(findings)
        self.assertIn(articles[0]["@id"], diagnostic)
        self.assertIn(articles[0]["url"], diagnostic)
        self.assertIn(mutation["value"], diagnostic)

    def test_three_duplicate_article_urls_report_all_values_by_identity(self) -> None:
        shared_id = "https://overkillhill.com/writings/shared-identity/#article"
        matching_url = "https://overkillhill.com/writings/shared-identity/"
        conflicting_url = "https://overkillhill.com/writings/conflicting/"
        distinct_url = "https://overkillhill.com/writings/distinct/"
        shared_article = {
            "@type": "Article",
            "@id": shared_id,
            "datePublished": "2026-04-07",
            "dateModified": "2026-05-24",
        }
        articles = [
            {**shared_article, "headline": "First representation", "url": matching_url},
            {**shared_article, "headline": "Second representation", "url": matching_url},
            {**shared_article, "headline": "Third representation", "url": conflicting_url},
            {
                "@type": "Article",
                "@id": "https://overkillhill.com/writings/distinct/#article",
                "headline": "Distinct article",
                "datePublished": "2026-04-07",
                "dateModified": "2026-05-24",
                "url": distinct_url,
            },
        ]
        parser = parse_html(
            '<script type="application/ld+json">'
            + json.dumps({"@graph": articles})
            + "</script>"
        )

        findings = validator.validate_article_jsonld_dates(
            "three-duplicate-articles.fixture",
            parser,
        )

        self.assertEqual(len(findings), 1, findings_text(findings))
        self.assert_rejected(
            findings,
            "conflicting duplicate Article JSON-LD url values",
        )
        diagnostic = findings_text(findings)
        self.assertIn(shared_id, diagnostic)
        self.assertIn(
            repr([matching_url, matching_url, conflicting_url]),
            diagnostic,
        )
        self.assertNotIn(distinct_url, diagnostic)

    def test_noindex_duplicate_article_url_conflict_remains_exempt(self) -> None:
        page = self.pages_by_route["/writings/biases-as-constants/"]
        source_path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        generated_path = ROOT / page["path"]
        conflict_url = self.fixture_data["duplicate_article_url_mismatch"]["value"]
        source_raw = duplicate_article_jsonld_root_url(
            source_path.read_text(encoding="utf-8"), conflict_url
        )
        generated_raw = duplicate_article_jsonld_root_url(
            generated_path.read_text(encoding="utf-8"), conflict_url
        )
        for raw in (source_raw, generated_raw):
            self.assert_rejected(
                validator.validate_article_jsonld_dates("noindex-control", parse_html(raw)),
                "conflicting duplicate Article JSON-LD url values",
            )
        original_read = Path.read_text

        def read_source(path, *args, **kwargs):
            if path == source_path:
                return source_raw
            return original_read(path, *args, **kwargs)

        with patch.object(Path, "read_text", read_source):
            self.assertFalse(validator.validate_article_jsonld_source([page]))
        self.assertTrue(parse_html(generated_raw).is_noindex)
        self.assertFalse(validator.validate_generated_seo(
            generated_path, parse_html(generated_raw), page,
        ))

    def test_distinct_article_graph_nodes_may_have_distinct_urls(self) -> None:
        articles = [
            {
                "@type": "Article",
                "@id": "https://overkillhill.com/writings/one/#article",
                "headline": "First article",
                "datePublished": "2026-04-07",
                "dateModified": "2026-05-24",
                "url": "https://overkillhill.com/writings/one/",
            },
            {
                "@type": "Article",
                "@id": "https://overkillhill.com/writings/two/#article",
                "headline": "Second article",
                "datePublished": "2026-04-07",
                "dateModified": "2026-05-24",
                "url": "https://overkillhill.com/writings/two/",
            },
        ]
        parser = parse_html(
            '<script type="application/ld+json">'
            + json.dumps({"@graph": articles})
            + "</script>"
        )
        findings = validator.validate_article_jsonld_dates(
            "distinct-article-graph.fixture",
            parser,
        )
        self.assertFalse(findings, findings_text(findings))

    def test_identical_duplicate_article_urls_remain_valid(self) -> None:
        mutation = self.fixture_data["duplicate_article_url_mismatch"]
        page = self.pages_by_route[mutation["route"]]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        original_article = article_jsonld_nodes(original_raw)[0]
        duplicated_raw = duplicate_article_jsonld(
            original_raw,
            "datePublished",
            original_article["datePublished"],
        )
        articles = article_jsonld_nodes(duplicated_raw)
        self.assertEqual(articles[0]["url"], articles[1]["url"])
        findings = validator.validate_article_jsonld_dates(
            path.relative_to(ROOT).as_posix(),
            parse_html(duplicated_raw),
            page["meta:article:published_time"],
        )
        self.assertFalse(findings, findings_text(findings))

    def test_single_article_without_url_remains_valid_including_murderbird(self) -> None:
        page = self.pages_by_route["/writings/murderbird/"]
        source_path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        generated_path = ROOT / page["path"]
        source_raw = source_path.read_text(encoding="utf-8")
        generated_raw = generated_path.read_text(encoding="utf-8")
        self.assertEqual(len(article_jsonld_nodes(source_raw)), 1)
        self.assertNotIn("url", article_jsonld_nodes(source_raw)[0])
        self.assertEqual(len(article_jsonld_nodes(generated_raw)), 1)
        self.assertNotIn("url", article_jsonld_nodes(generated_raw)[0])
        self.assertFalse(
            validator.validate_article_jsonld_source([page]),
            "a single source Article without url remains accepted",
        )
        generated_findings = validator.validate_generated_seo(
            generated_path,
            parse_html(generated_raw),
            page,
        )
        self.assertFalse(generated_findings, findings_text(generated_findings))

    def test_rendered_robots_conflicts_are_rejected_and_consistent_duplicates_pass(self) -> None:
        robots_fixture = self.fixture_data["robots_directive_conflicts"]
        index_path = GENERATED_FIXTURE / "index.html.fixture"
        index_page = self.pages_by_route["/"]
        index_raw = index_path.read_text(encoding="utf-8")
        draft_page = self.pages_by_route["/writings/biases-as-constants/"]
        draft_path = ROOT / draft_page["path"]
        draft_raw = draft_path.read_text(encoding="utf-8")

        within_tag_conflict = mutate_meta(
            draft_raw,
            "meta:robots",
            "NoIndex, INDEX, Follow",
        )
        across_tags_conflict = index_raw.replace(
            "</head>",
            f'<meta name="robots" content="{robots_fixture["noindex"]}"></head>',
            1,
        )
        unrelated_meta_across_tags_conflict = across_tags_conflict.replace(
            '<meta name="robots" content="index, follow">',
            (
                '<meta name="description" content="Unrelated metadata">\n'
                '<meta property="og:title" content="Unrelated title">\n'
                '<meta name="robots" content="index, follow">'
            ),
            1,
        )
        conflict_cases = (
            (
                "across tags on a noindex page",
                draft_path,
                draft_page,
                draft_raw.replace(
                    "</head>",
                    f'<meta name="robots" content="{robots_fixture["index"]}"></head>',
                    1,
                ),
                (robots_fixture["index"],),
            ),
            (
                "within one noindex tag",
                draft_path,
                draft_page,
                within_tag_conflict,
                ("NoIndex, INDEX, Follow",),
            ),
            (
                "across tags",
                index_path,
                index_page,
                across_tags_conflict,
                (robots_fixture["index"], robots_fixture["noindex"]),
            ),
            (
                "robots tag positions ignore unrelated metadata",
                index_path,
                index_page,
                unrelated_meta_across_tags_conflict,
                (robots_fixture["index"], robots_fixture["noindex"]),
            ),
        )
        for case, path, page, raw, expected_values in conflict_cases:
            with self.subTest(case=case):
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(raw),
                    page,
                )
                conflicts = [
                    finding for finding in findings
                    if robots_fixture["expected"] in finding.msg
                ]
                self.assertEqual(len(conflicts), 1, findings_text(findings))
                conflict = conflicts[0]
                self.assertEqual(
                    conflict.page,
                    path.relative_to(ROOT).as_posix(),
                )
                for position, value in enumerate(expected_values, start=1):
                    self.assertIn(f"robots tag #{position}=", conflict.msg)
                    self.assertIn(value, conflict.msg)

        consistent_cases = (
            (
                "duplicate index tags",
                index_path,
                index_page,
                index_raw.replace(
                    "</head>",
                    '<meta name="robots" content="INDEX, FOLLOW"></head>',
                    1,
                ),
            ),
            (
                "duplicate noindex tags",
                draft_path,
                draft_page,
                draft_raw.replace(
                    "</head>",
                    f'<meta name="robots" content="{robots_fixture["noindex"]}"></head>',
                    1,
                ),
            ),
            (
                "directive lookalikes are not indexing tokens",
                index_path,
                index_page,
                mutate_meta(
                    index_raw,
                    "meta:robots",
                    "indexifembedded, noindexing",
                ),
            ),
        )
        for case, path, page, raw in consistent_cases:
            with self.subTest(case=case):
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(raw),
                    page,
                )
                self.assertFalse(findings, findings_text(findings))

    def test_locale_robots_conflicts_are_rejected_and_consistent_duplicates_pass(self) -> None:
        fixture = self.fixture_data["robots_directive_conflicts"]
        relative_path = "de/index.html"
        path = ROOT / relative_path
        contract = self.locale_contract[relative_path]
        original_raw = path.read_text(encoding="utf-8")

        conflicting_raw = original_raw.replace(
            "</head>",
            f'<meta name="robots" content="{fixture["index"]}"></head>',
            1,
        )
        conflicting_parser = parse_html(conflicting_raw)
        findings = validator.validate_generated_seo(
            path,
            conflicting_parser,
            None,
            contract,
        )
        conflict = next(
            (
                finding
                for finding in findings
                if fixture["expected"] in finding.msg
            ),
            None,
        )
        self.assertIsNotNone(conflict, findings_text(findings))
        assert conflict is not None
        self.assertEqual(conflict.page, relative_path)
        for value in conflicting_parser.meta["robots"]:
            if validator.robots_indexing_tokens(value).intersection(
                validator.ROBOTS_INDEXING_TOKENS
            ):
                self.assertIn(value, conflict.msg)

        consistent_raw = original_raw.replace(
            "</head>",
            f'<meta name="robots" content="{fixture["noindex"]}"></head>',
            1,
        )
        consistent_findings = validator.validate_generated_seo(
            path,
            parse_html(consistent_raw),
            None,
            contract,
        )
        self.assertFalse(
            consistent_findings,
            "consistent duplicate noindex directives are explicitly accepted",
        )

    def test_crawler_robots_directives_must_match_page_wide_indexing_contract(self) -> None:
        fixture = self.fixture_data["crawler_robots_contract"]
        index_path = GENERATED_FIXTURE / "index.html.fixture"
        index_page = self.pages_by_route["/"]
        index_raw = index_path.read_text(encoding="utf-8")
        draft_page = self.pages_by_route["/writings/biases-as-constants/"]
        draft_path = ROOT / draft_page["path"]
        draft_raw = draft_path.read_text(encoding="utf-8")

        cases = (
            (
                "crawler-specific noindex cannot override page-wide index",
                index_path,
                index_page,
                index_raw.replace(
                    "</head>",
                    f'<meta name="googlebot" content="{fixture["noindex"]}"></head>',
                    1,
                ),
                ("robots tag #1=", "googlebot tag #1="),
            ),
            (
                "crawler-specific index cannot override page-wide noindex",
                draft_path,
                draft_page,
                mutate_meta(draft_raw, "meta:googlebot", fixture["index"]),
                ("robots tag #1=", "googlebot tag #1="),
            ),
        )
        for case, path, page, raw, expected_labels in cases:
            with self.subTest(case=case):
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(raw),
                    page,
                )
                conflicts = [
                    finding for finding in findings
                    if fixture["expected"] in finding.msg
                ]
                self.assertEqual(len(conflicts), 1, findings_text(findings))
                for label in expected_labels:
                    self.assertIn(label, conflicts[0].msg)

        consistent_raw = index_raw.replace(
            "</head>",
            f'<meta name="googlebot" content="{fixture["index"]}"></head>',
            1,
        )
        consistent_findings = validator.validate_generated_seo(
            index_path,
            parse_html(consistent_raw),
            index_page,
        )
        self.assertFalse(
            consistent_findings,
            "matching page-wide and crawler-specific index directives are accepted",
        )

        crawler_only_raw = index_raw.replace(
            "</head>",
            '<meta name="googlebot" content="max-snippet:0"></head>',
            1,
        )
        crawler_only_findings = validator.validate_generated_seo(
            index_path,
            parse_html(crawler_only_raw),
            index_page,
        )
        self.assertFalse(
            crawler_only_findings,
            "crawler-specific presentation directives do not conflict with indexing",
        )

    def test_draft_article_promotion_requires_article_metadata(self) -> None:
        mutation = self.fixture_data["draft_article_promotion"]
        draft_page = page_for_route(self.source_pages, mutation["route"])
        source_path = (ROOT / "site-src" / "pages" / draft_page["path"]).with_suffix(
            ".extras.html"
        )
        generated_path = ROOT / draft_page["path"]
        generated_raw = generated_path.read_text(encoding="utf-8")

        self.assertFalse(
            validator.validate_article_jsonld_source([draft_page]),
            "noindex source drafts should remain exempt before promotion",
        )
        self.assertFalse(
            validator.validate_source_seo_contract([draft_page]),
            "noindex source drafts should remain exempt from Article metadata checks",
        )
        draft_parser = parse_html(generated_raw)
        self.assertTrue(
            draft_parser.is_noindex,
            "generated Article fixture should remain noindex while it is a draft",
        )
        self.assertFalse(
            validator.validate_generated_seo(
                generated_path,
                draft_parser,
                draft_page,
            ),
            "noindex generated drafts should remain exempt before promotion",
        )
        self.assertIn('"@type": "Article"', source_path.read_text(encoding="utf-8"))

        promoted_page = copy.deepcopy(draft_page)
        promoted_page[mutation["field"]] = mutation["value"]
        self.assertTrue(
            validator.is_indexable_page(promoted_page),
            "promotion fixture must change the manifest indexing boundary",
        )
        self.assertEqual(
            draft_page.get("meta:robots"),
            "noindex, nofollow",
            "draft fixture baseline must remain noindex",
        )

        source_findings = validator.validate_article_jsonld_source([promoted_page])
        self.assert_rejected(source_findings, mutation["expected"])

        generated_findings = validator.validate_generated_seo(
            generated_path,
            draft_parser,
            promoted_page,
        )
        self.assert_rejected(generated_findings, mutation["expected"])
        self.assert_rejected(generated_findings, mutation["expected_boundary"])

        indexable_parser = parse_html(
            mutate_meta(generated_raw, mutation["field"], mutation["value"])
        )
        reverse_findings = validator.validate_generated_seo(
            generated_path,
            indexable_parser,
            draft_page,
        )
        self.assert_rejected(reverse_findings, mutation["reverse_boundary"])

        og_type = mutation["og_type"]
        promoted_page[og_type["field"]] = og_type["value"]
        self.assertEqual(
            promoted_page.get(og_type["field"]),
            og_type["value"],
            "promotion fixture must retain the draft's website-level og:type",
        )
        source_metadata_findings = validator.validate_source_seo_contract(
            [promoted_page]
        )
        self.assert_rejected(source_metadata_findings, og_type["expected_source"])

        promoted_parser = parse_html(
            mutate_meta(generated_raw, og_type["field"], og_type["value"])
        )
        generated_metadata_findings = validator.validate_generated_seo(
            generated_path,
            promoted_parser,
            promoted_page,
        )
        self.assert_rejected(
            generated_metadata_findings,
            og_type["expected_generated"],
        )

    def _promoted_article_social_image_case(self) -> tuple[dict, dict, dict]:
        fixture = self.fixture_data["article_shared_social_image"]
        draft_route = self.fixture_data["draft_article_promotion"]["route"]
        draft_page = page_for_route(self.source_pages, draft_route)
        article_page = self.pages_by_route[fixture["control_route"]]
        promoted_page = copy.deepcopy(draft_page)
        promoted_page["meta:robots"] = "index, follow"
        for key in (
            "meta:og:type",
            "meta:article:published_time",
            "meta:og:image",
            "meta:og:image:alt",
            "meta:og:image:width",
            "meta:og:image:height",
            "meta:og:image:type",
            "meta:twitter:image",
            "meta:twitter:image:alt",
        ):
            promoted_page[key] = article_page[key]
        return fixture, draft_page, promoted_page

    def test_article_specific_image_control_and_noindex_exemption(self) -> None:
        fixture, draft_page, promoted_page = self._promoted_article_social_image_case()
        draft_path = ROOT / draft_page["path"]
        draft_raw = draft_path.read_text(encoding="utf-8")
        draft_parser = parse_html(draft_raw)
        shared_asset = (
            ROOT / validator.SHARED_BRAND_SOCIAL_IMAGE.lstrip("/")
        ).resolve()

        for alias in fixture["aliases"]:
            with self.subTest(image_alias=alias["id"]):
                resolved = validator._image_asset_path(alias["value"])
                self.assertIsNotNone(resolved)
                self.assertEqual(
                    resolved.resolve(),
                    shared_asset,
                    f"_image_asset_path did not resolve alias {alias['value']!r}",
                )

        self.assertFalse(validator.is_indexable_page(draft_page))
        self.assertFalse(
            validator.validate_source_seo_contract([draft_page]),
            "noindex Article drafts using the shared brand image remain exempt",
        )
        self.assertFalse(
            validator.validate_generated_seo(draft_path, draft_parser, draft_page),
            "generated noindex Article drafts using the shared brand image remain exempt",
        )

        for alias in fixture["aliases"]:
            with self.subTest(noindex_alias=alias["id"]):
                alias_draft = copy.deepcopy(draft_page)
                alias_draft["meta:og:image"] = alias["value"]
                alias_draft["meta:twitter:image"] = alias["value"]
                self.assertFalse(
                    validator.validate_source_seo_contract([alias_draft]),
                    "noindex source Article drafts using a shared-image alias remain exempt",
                )

                alias_raw = mutate_meta(
                    mutate_meta(draft_raw, "meta:og:image", alias["value"]),
                    "meta:twitter:image",
                    alias["value"],
                )
                self.assertFalse(
                    validator.validate_generated_seo(
                        draft_path,
                        parse_html(alias_raw),
                        alias_draft,
                    ),
                    "noindex generated Article drafts using a shared-image alias remain exempt",
                )

        source_findings = validator.validate_source_seo_contract([promoted_page])
        self.assertFalse(
            source_findings,
            findings_text(source_findings),
        )

        generated_path = GENERATED_FIXTURE / "article.html.fixture"
        generated_parser = parse_html(generated_path.read_text(encoding="utf-8"))
        generated_findings = validator.validate_generated_seo(
            generated_path,
            generated_parser,
            promoted_page,
        )
        self.assertFalse(
            generated_findings,
            findings_text(generated_findings),
        )

    def test_promoted_article_shared_brand_image_rejected_in_source(self) -> None:
        fixture, _, promoted_page = self._promoted_article_social_image_case()
        for field in ("meta:og:image", "meta:twitter:image"):
            url_cases = [
                (url_kind, fixture[url_kind])
                for url_kind in ("absolute_url", "local_url")
            ] + [
                (alias["id"], alias["value"])
                for alias in fixture["aliases"]
            ]
            for url_kind, url in url_cases:
                with self.subTest(field=field, url_kind=url_kind):
                    mutated_page = copy.deepcopy(promoted_page)
                    mutated_page[field] = url
                    findings = validator.validate_source_seo_contract(
                        [mutated_page]
                    )
                    self.assert_rejected(
                        findings,
                        f"{fixture['expected_source']}: {field} "
                        f"({url})",
                    )

    def test_promoted_article_shared_brand_image_rejected_in_generated_html(self) -> None:
        fixture, _, promoted_page = self._promoted_article_social_image_case()
        generated_path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = generated_path.read_text(encoding="utf-8")
        for field in ("meta:og:image", "meta:twitter:image"):
            url_cases = [
                (url_kind, fixture[url_kind])
                for url_kind in ("absolute_url", "local_url")
            ] + [
                (alias["id"], alias["value"])
                for alias in fixture["aliases"]
            ]
            for url_kind, url in url_cases:
                with self.subTest(field=field, url_kind=url_kind):
                    mutated_raw = mutate_meta(
                        original_raw,
                        field,
                        url,
                    )
                    findings = validator.validate_generated_seo(
                        generated_path,
                        parse_html(mutated_raw),
                        promoted_page,
                    )
                    self.assert_rejected(
                        findings,
                        f"{fixture['expected_generated']}: {field} "
                        f"({url})",
                    )

    def assert_rejected(self, findings: list, expected: str) -> None:
        self.assertTrue(findings, "mutation unexpectedly passed")
        self.assertIn(expected, findings_text(findings))

    def assert_source_seo_mutation(
        self,
        mutation: dict,
        expected: str,
    ) -> None:
        original = page_for_route(self.source_pages, mutation["route"])
        mutated = copy.deepcopy(original)
        if "value" in mutation:
            mutated[mutation["field"]] = mutation["value"]
        else:
            mutated.pop(mutation["field"], None)
        self.assertEqual(
            original.get("meta:robots"),
            mutated.get("meta:robots"),
            "SEO fixture changed the source indexing boundary",
        )
        self.assertEqual(
            {key: value for key, value in original.items() if not key.startswith("meta:")},
            {key: value for key, value in mutated.items() if not key.startswith("meta:")},
            "SEO fixture changed source editorial or routing fields",
        )
        findings = validator.validate_source_seo_contract(
            [
                mutated if page is original else page
                for page in self.source_pages
            ]
        )
        self.assert_rejected(findings, expected)

    def test_retired_social_image_rejected_in_source(self) -> None:
        mutation = self.fixture_data["retired_social_image"]
        self.assert_source_seo_mutation(
            mutation,
            "indexable source page uses retired social image",
        )

    def test_mismatched_image_dimensions_rejected_in_source(self) -> None:
        mutation = self.fixture_data["image_contract"][0]
        self.assert_source_seo_mutation(
            mutation,
            "social image dimensions",
        )

    def test_mismatched_image_type_rejected_in_source(self) -> None:
        mutation = self.fixture_data["image_contract"][1]
        self.assert_source_seo_mutation(
            mutation,
            "social image type",
        )

    def test_mismatched_social_images_rejected_in_source(self) -> None:
        mutation = self.fixture_data["social_image_parity"]
        self.assert_source_seo_mutation(
            mutation,
            "social card image mismatch",
        )

    def test_missing_article_metadata_rejected_in_source(self) -> None:
        mutation = self.fixture_data["missing_article_metadata"]
        self.assert_source_seo_mutation(
            mutation,
            "article source page is missing article:published_time",
        )

    def test_malformed_article_metadata_rejected_in_source(self) -> None:
        for mutation in self.fixture_data["malformed_article_metadata"]:
            with self.subTest(mutation=mutation["id"]):
                self.assert_source_seo_mutation(
                    mutation,
                    mutation["expected_source"]
                    if "expected_source" in mutation
                    else mutation["expected"],
                )

    def test_malformed_article_jsonld_dates_rejected_in_source_extras(self) -> None:
        page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        for mutation in self.fixture_data["malformed_article_jsonld_dates"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = mutate_jsonld_field(
                    original_raw,
                    mutation["field"],
                    mutation["value"],
                )
                self.assertNotEqual(original_raw, mutated_raw)
                self.assertIn(
                    '"headline": "The First Diagram Is Usually a Liar"',
                    mutated_raw,
                )
                self.assertIn(
                    '"description": "The Final Cut: AI diagrams, structured disagreement',
                    mutated_raw,
                )
                self.assertEqual(
                    "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1",
                    page.get("meta:robots"),
                    "source fixture mutation changed the indexing boundary",
                )
                findings = validator.validate_article_jsonld_dates(
                    path.relative_to(ROOT).as_posix(),
                    parse_html(mutated_raw),
                )
                self.assert_rejected(findings, mutation["expected"])

    def test_missing_article_jsonld_dates_rejected_in_source_extras(self) -> None:
        page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        for mutation in self.fixture_data["missing_article_jsonld_dates"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = remove_jsonld_field(original_raw, mutation["field"])
                self.assertNotEqual(original_raw, mutated_raw)
                self.assertIn(
                    '"headline": "The First Diagram Is Usually a Liar"',
                    mutated_raw,
                )
                findings = validator.validate_article_jsonld_dates(
                    path.relative_to(ROOT).as_posix(),
                    parse_html(mutated_raw),
                    page["meta:article:published_time"],
                )
                self.assert_rejected(findings, mutation["expected"])

    def test_article_jsonld_og_date_mismatch_rejected_in_source_extras(self) -> None:
        mutation = self.fixture_data["article_date_mismatch"]
        page = self.pages_by_route[mutation["route"]]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = mutate_jsonld_field(
            original_raw,
            mutation["field"],
            mutation["value"],
        )
        self.assertIn(
            '"headline": "The First Diagram Is Usually a Liar"',
            mutated_raw,
        )
        self.assertIn(
            '"description": "The Final Cut: AI diagrams, structured disagreement',
            mutated_raw,
        )
        self.assertEqual(
            page.get("meta:robots"),
            "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1",
            "source fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_article_jsonld_dates(
            path.relative_to(ROOT).as_posix(),
            parse_html(mutated_raw),
            page["meta:article:published_time"],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_article_og_date_mismatch_rejected_in_source_manifest(self) -> None:
        mutation = self.fixture_data["article_og_date_mismatch"]
        original = page_for_route(self.source_pages, mutation["route"])
        mutated = copy.deepcopy(original)
        mutated[mutation["field"]] = mutation["value"]
        mutated_pages = [
            mutated if page is original else page
            for page in self.source_pages
        ]
        self.assertEqual(
            original.get("meta:robots"),
            mutated.get("meta:robots"),
            "source fixture mutation changed the indexing boundary",
        )
        self.assertEqual(
            {
                key: value
                for key, value in original.items()
                if not key.startswith("meta:")
            },
            {
                key: value
                for key, value in mutated.items()
                if not key.startswith("meta:")
            },
            "source fixture mutation changed editorial or routing fields",
        )
        source_path = (ROOT / "site-src" / "pages" / original["path"]).with_suffix(
            ".extras.html"
        )
        source_raw = source_path.read_text(encoding="utf-8")
        self.assertIn('"datePublished": "2026-04-07"', source_raw)
        self.assertFalse(
            validator.validate_source_seo_contract(mutated_pages),
            "valid ISO 8601 Open Graph mutation should reach date-parity validation",
        )
        findings = validator.validate_article_jsonld_source(mutated_pages)
        self.assert_rejected(findings, mutation["expected"])

    def test_timezone_qualified_article_dates_compare_as_documented_in_source(self) -> None:
        page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        for case_name, mutation in self.fixture_data["article_timezone_date_parity"].items():
            with self.subTest(case_name=case_name):
                mutated_raw = mutate_jsonld_field(
                    original_raw,
                    "datePublished",
                    mutation["jsonld_value"],
                )
                self.assertIn(
                    '"headline": "The First Diagram Is Usually a Liar"',
                    mutated_raw,
                )
                self.assertIn(
                    '"description": "The Final Cut: AI diagrams, structured disagreement',
                    mutated_raw,
                )
                mutated_page = copy.deepcopy(page)
                mutated_page["meta:article:published_time"] = mutation["published_time"]
                self.assertEqual(
                    page.get("meta:robots"),
                    mutated_page.get("meta:robots"),
                    "timezone fixture changed the source indexing boundary",
                )
                self.assertEqual(
                    {
                        key: value for key, value in page.items()
                        if not key.startswith("meta:")
                    },
                    {
                        key: value for key, value in mutated_page.items()
                        if not key.startswith("meta:")
                    },
                    "timezone fixture changed source editorial or routing fields",
                )
                findings = validator.validate_article_jsonld_dates(
                    path.relative_to(ROOT).as_posix(),
                    parse_html(mutated_raw),
                    mutated_page["meta:article:published_time"],
                )
                if mutation["valid"]:
                    self.assertFalse(findings, findings_text(findings))
                else:
                    self.assert_rejected(findings, mutation["expected"])

    def test_article_sitemap_lastmod_contract_rejected_in_source(self) -> None:
        route = "/writings/first-diagram-is-a-liar/"
        page = self.pages_by_route[route]
        sitemap_url = page["canonical"]
        baseline = validator.load_sitemap_entries()
        self.assertEqual(baseline[sitemap_url], "2026-09-29")
        for lastmod, expected in (
            (None, "article sitemap lastmod is missing"),
            ("", "article sitemap lastmod is missing"),
            ("not-a-date", "article sitemap lastmod is not ISO 8601"),
            ("2026-05-23", "article JSON-LD dateModified does not match sitemap lastmod"),
        ):
            with self.subTest(lastmod=lastmod):
                entries = dict(baseline)
                entries[sitemap_url] = lastmod
                findings = validator.validate_article_jsonld_source(
                    self.source_pages,
                    entries,
                )
                self.assert_rejected(findings, expected)

    def test_article_sitemap_date_parity_in_source(self) -> None:
        fixture = self.fixture_data["article_sitemap_date_parity"]
        page = self.pages_by_route[fixture["route"]]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        original_articles = article_jsonld_nodes(original_raw)
        self.assertEqual(len(original_articles), 1)
        generated_raw = (GENERATED_FIXTURE / "article.html.fixture").read_text(
            encoding="utf-8"
        )
        generated_articles = article_jsonld_nodes(generated_raw)
        self.assertEqual(len(generated_articles), 1)
        baseline_sitemap = validator.load_sitemap_entries()
        self.assertEqual(baseline_sitemap[page["canonical"]], "2026-09-29")
        self.assertTrue(validator.is_indexable_page(page))

        for case_name, mutation in fixture["cases"].items():
            with self.subTest(case_name=case_name):
                self.assertNotIn(
                    mutation["date_modified"],
                    {
                        original_articles[0]["dateModified"],
                        generated_articles[0]["dateModified"],
                    },
                    "shared date fixture must differ from both source and generated baselines",
                )
                self.assertNotEqual(
                    mutation["sitemap_lastmod"],
                    baseline_sitemap[page["canonical"]],
                    "sitemap fixture must differ from the committed sitemap baseline",
                )
                mutated_raw = mutate_jsonld_field(
                    original_raw,
                    "dateModified",
                    mutation["date_modified"],
                )
                expected_articles = copy.deepcopy(original_articles)
                expected_articles[0]["dateModified"] = mutation["date_modified"]
                self.assertEqual(expected_articles, article_jsonld_nodes(mutated_raw))
                mutated_parser = parse_html(mutated_raw)
                self.assertEqual(original_parser.meta, mutated_parser.meta)

                findings = validator.validate_article_jsonld_dates(
                    path.relative_to(ROOT).as_posix(),
                    mutated_parser,
                    page["meta:article:published_time"],
                )
                findings.extend(
                    validator.validate_article_sitemap_dates(
                        path.relative_to(ROOT).as_posix(),
                        mutated_parser,
                        page["canonical"],
                        mutation["sitemap_lastmod"],
                    )
                )
                if mutation["valid"]:
                    self.assertFalse(findings, findings_text(findings))
                else:
                    self.assert_rejected(findings, mutation["expected"])

    def test_duplicate_article_dates_accept_matching_offsets_only(self) -> None:
        page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        sources = (
            (ROOT / "site-src" / "pages" / page["path"]).with_suffix(
                ".extras.html"
            ),
            GENERATED_FIXTURE / "article.html.fixture",
        )
        cases = {
            "datePublished": (
                "2026-04-07T12:00:00Z",
                "2026-04-07T14:00:00+02:00",
                "2026-04-07T14:00:01+02:00",
            ),
            "dateModified": (
                "2026-05-24T00:00:00Z",
                "2026-05-24T05:30:00+05:30",
                "2026-05-24T05:30:01+05:30",
            ),
        }

        for path in sources:
            original_raw = path.read_text(encoding="utf-8")
            original_parser = parse_html(original_raw)
            for field, (first, same_instant, different_instant) in cases.items():
                for second, should_pass in (
                    (same_instant, True),
                    (different_instant, False),
                ):
                    with self.subTest(
                        path=path.name,
                        field=field,
                        second=second,
                    ):
                        first_raw = mutate_jsonld_field(original_raw, field, first)
                        duplicated_raw = duplicate_article_jsonld(
                            first_raw, field, second
                        )
                        parser = parse_html(duplicated_raw)
                        articles = article_jsonld_nodes(duplicated_raw)
                        self.assertEqual(len(articles), 2)
                        self.assertEqual(
                            {article[field] for article in articles},
                            {first, second},
                        )
                        self.assertEqual(
                            original_parser.meta,
                            parser.meta,
                            "duplicate-date fixture changed page metadata",
                        )
                        self.assertEqual(
                            original_parser.is_noindex,
                            parser.is_noindex,
                            "duplicate-date fixture changed the indexing boundary",
                        )

                        findings = validator.validate_article_jsonld_dates(
                            path.name,
                            parser,
                        )
                        duplicate_message = (
                            f"conflicting duplicate Article JSON-LD {field} values"
                        )
                        if should_pass:
                            self.assertNotIn(
                                duplicate_message,
                                findings_text(findings),
                            )
                        else:
                            self.assert_rejected(findings, duplicate_message)

    def test_duplicate_article_jsonld_dates_rejected_in_source_extras(self) -> None:
        mutation = self.fixture_data["duplicate_article_date_mismatch"]
        page = self.pages_by_route[mutation["route"]]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = duplicate_article_jsonld(
            original_raw, "datePublished", mutation["value"]
        )
        self.assertIn(
            '"headline": "The First Diagram Is Usually a Liar"',
            mutated_raw,
        )
        self.assertEqual(
            page.get("meta:robots"),
            "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1",
            "source fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_article_jsonld_dates(
            path.relative_to(ROOT).as_posix(),
            parse_html(mutated_raw),
            page["meta:article:published_time"],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_duplicate_article_jsonld_modified_date_rejected_in_source_extras(self) -> None:
        mutation = self.fixture_data["duplicate_article_modified_date_mismatch"]
        page = self.pages_by_route[mutation["route"]]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = duplicate_article_jsonld(
            original_raw, "dateModified", mutation["value"]
        )
        self.assertIn(
            '"headline": "The First Diagram Is Usually a Liar"',
            mutated_raw,
        )
        self.assertIn(
            '"description": "The Final Cut: AI diagrams, structured disagreement',
            mutated_raw,
        )
        self.assertEqual(
            page.get("meta:robots"),
            "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1",
            "source fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_article_jsonld_dates(
            path.relative_to(ROOT).as_posix(),
            parse_html(mutated_raw),
            page["meta:article:published_time"],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_graph_duplicate_article_modified_date_rejected_in_source_extras(self) -> None:
        mutation = self.fixture_data["duplicate_article_modified_date_mismatch"]
        page = self.pages_by_route[mutation["route"]]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        original_articles = article_jsonld_nodes(original_raw)
        self.assertEqual(len(original_articles), 1)

        mutated_raw = article_graph_with_conflicting_modified_date(
            original_raw,
            mutation["value"],
        )
        mutated_articles = article_jsonld_nodes(mutated_raw)
        self.assertEqual(len(mutated_articles), 2)
        self.assertEqual(
            mutated_articles[0]["@id"],
            mutated_articles[1]["@id"],
            "source graph fixture must duplicate the Article identity",
        )
        self.assertEqual(
            {article["dateModified"] for article in mutated_articles},
            {original_articles[0]["dateModified"], mutation["value"]},
        )
        for article in mutated_articles:
            self.assertEqual(
                article["headline"],
                original_articles[0]["headline"],
                "source graph fixture changed Article headline prose",
            )
            self.assertEqual(
                article["description"],
                original_articles[0]["description"],
                "source graph fixture changed Article description prose",
            )

        indexing_fields = {
            key: value
            for key, value in page.items()
            if key in ("meta:robots", "meta:googlebot", "meta:bingbot")
        }
        self.assertEqual(
            indexing_fields,
            {
                "meta:robots": (
                    "index, follow, max-image-preview:large, max-snippet:-1, "
                    "max-video-preview:-1"
                ),
                "meta:googlebot": "index, follow",
                "meta:bingbot": "index, follow",
            },
            "source graph fixture changed the manifest robots/indexing fields",
        )

        original_read_text = Path.read_text

        def read_source(path_to_read, *args, **kwargs):
            if path_to_read == path:
                return mutated_raw
            return original_read_text(path_to_read, *args, **kwargs)

        with patch.object(Path, "read_text", read_source):
            findings = validator.validate_article_jsonld_source([page])
        self.assert_rejected(findings, mutation["expected"])

    def test_duplicate_article_jsonld_root_url_rejected_in_source_extras(self) -> None:
        mutation = self.fixture_data["duplicate_article_url_mismatch"]
        page = self.pages_by_route[mutation["route"]]
        path = (ROOT / "site-src" / "pages" / page["path"]).with_suffix(".extras.html")
        original_raw = path.read_text(encoding="utf-8")
        original_articles = article_jsonld_nodes(original_raw)
        mutated_raw = duplicate_article_jsonld_root_url(
            original_raw, mutation["value"]
        )
        mutated_articles = article_jsonld_nodes(mutated_raw)
        self.assertEqual(len(mutated_articles), 2)
        self.assertNotEqual(original_articles[0]["url"], mutation["value"])
        self.assertEqual(mutated_articles[0]["url"], original_articles[0]["url"])
        self.assertEqual(mutated_articles[1]["url"], mutation["value"])
        self.assertEqual(
            mutated_articles[1]["author"]["url"],
            original_articles[0]["author"]["url"],
            "source fixture mutation changed nested author.url",
        )
        duplicate_block = (
            '<script type="application/ld+json">\n'
            + json.dumps(mutated_articles[1], ensure_ascii=False, indent=2)
            + "\n</script>"
        )
        self.assertEqual(
            mutated_raw.replace("\n" + duplicate_block, "", 1),
            original_raw,
            "source fixture mutation changed content outside the duplicate Article node",
        )
        self.assertIn(
            '"headline": "The First Diagram Is Usually a Liar"',
            mutated_raw,
        )
        self.assertEqual(
            page.get("meta:robots"),
            "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1",
            "source fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_article_jsonld_dates(
            path.relative_to(ROOT).as_posix(),
            parse_html(mutated_raw),
            page["meta:article:published_time"],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_same_as_drift_rejected_in_shared_head_source(self) -> None:
        mutation = self.fixture_data["organization_same_as_drift"]
        original_raw = validator.HEAD_PARTIAL.read_text(encoding="utf-8")
        mutated_raw = original_raw.replace(mutation["from"], mutation["to"], 1)
        self.assertNotEqual(original_raw, mutated_raw)
        self.assertEqual(
            mutated_raw.replace(mutation["to"], mutation["from"], 1),
            original_raw,
            "head fixture mutation changed editorial content",
        )
        findings = validator.validate_organization_nodes(
            "tests/fixtures/seo/head.html.fixture",
            parse_html(mutated_raw),
        )
        self.assert_rejected(findings, "sameAs links do not match")

    def test_generated_metadata_baseline_is_valid(self) -> None:
        root_page = self.pages_by_route["/"]
        article_page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        for fixture_name, manifest_page in (
            ("index.html.fixture", root_page),
            ("article.html.fixture", article_page),
        ):
            path = GENERATED_FIXTURE / fixture_name
            raw = path.read_text(encoding="utf-8")
            parser = parse_html(raw)
            self.assertFalse(
                validator.validate_generated_seo(path, parser, manifest_page),
                f"valid generated fixture failed: {fixture_name}",
            )
            self.assertIn("Fixture", raw)
            self.assertIn("index, follow", raw)

    def test_retired_social_image_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["retired_social_image"]
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        for field in ("meta:og:image", "meta:twitter:image"):
            with self.subTest(field=field):
                mutated_raw = mutate_meta(
                    original_raw,
                    field,
                    mutation["value"],
                )
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                    "generated fixture mutation changed editorial content",
                )
                self.assertIn('name="robots" content="index, follow"', mutated_raw)
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(mutated_raw),
                    self.pages_by_route["/"],
                )
                self.assert_rejected(findings, f"uses retired social image: {field}")

    def test_mismatched_image_metadata_rejected_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        for mutation in self.fixture_data["image_contract"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = mutate_meta(
                    original_raw,
                    mutation["field"],
                    mutation["value"],
                )
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                )
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(mutated_raw),
                    self.pages_by_route["/"],
                )
                self.assert_rejected(findings, "social image")

    def test_mismatched_social_images_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["social_image_parity"]
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = mutate_meta(
            original_raw,
            mutation["field"],
            mutation["value"],
        )
        self.assertEqual(
            original_raw.split("<body>", 1)[1],
            mutated_raw.split("<body>", 1)[1],
            "generated fixture mutation changed editorial content",
        )
        findings = validator.validate_generated_seo(
            path,
            parse_html(mutated_raw),
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, "social card image mismatch")

    def test_missing_article_metadata_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["missing_article_metadata"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = mutate_meta(original_raw, mutation["field"], None)
        self.assertEqual(
            original_raw.split("<body>", 1)[1],
            mutated_raw.split("<body>", 1)[1],
        )
        self.assertIn('name="robots" content="index, follow"', mutated_raw)
        findings = validator.validate_generated_seo(
            path,
            parse_html(mutated_raw),
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, "article generated page is missing")

    def test_malformed_article_metadata_rejected_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        for mutation in self.fixture_data["malformed_article_metadata"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = mutate_meta(
                    original_raw,
                    mutation["field"],
                    mutation["value"],
                )
                mutated_parser = parse_html(mutated_raw)
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                    "generated fixture mutation changed editorial content",
                )
                self.assertEqual(
                    original_parser.is_noindex,
                    mutated_parser.is_noindex,
                    "generated fixture mutation changed the indexing boundary",
                )
                findings = validator.validate_generated_seo(
                    path,
                    mutated_parser,
                    self.pages_by_route[mutation["route"]],
                )
                self.assert_rejected(
                    findings,
                    mutation["expected_generated"]
                    if "expected_generated" in mutation
                    else mutation["expected"],
                )

    def test_malformed_article_jsonld_dates_rejected_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        for mutation in self.fixture_data["malformed_article_jsonld_dates"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = mutate_jsonld_field(
                    original_raw,
                    mutation["field"],
                    mutation["value"],
                )
                mutated_parser = parse_html(mutated_raw)
                self.assertIn(
                    "<article>Fixture article copy remains unchanged.</article>",
                    mutated_raw,
                )
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                    "timezone fixture changed generated editorial content",
                )
                self.assertEqual(
                    original_parser.is_noindex,
                    mutated_parser.is_noindex,
                    "generated fixture mutation changed the indexing boundary",
                )
                findings = validator.validate_generated_seo(
                    path,
                    mutated_parser,
                    self.pages_by_route[mutation["route"]],
                )
                self.assert_rejected(findings, mutation["expected"])

    def test_missing_article_jsonld_dates_rejected_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        for mutation in self.fixture_data["missing_article_jsonld_dates"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = remove_jsonld_field(original_raw, mutation["field"])
                mutated_parser = parse_html(mutated_raw)
                self.assertIn(
                    "<article>Fixture article copy remains unchanged.</article>",
                    mutated_raw,
                )
                self.assertEqual(
                    original_parser.is_noindex,
                    mutated_parser.is_noindex,
                    "generated fixture mutation changed the indexing boundary",
                )
                findings = validator.validate_generated_seo(
                    path,
                    mutated_parser,
                    self.pages_by_route[mutation["route"]],
                )
                self.assert_rejected(findings, mutation["expected"])

    def test_article_jsonld_og_date_mismatch_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["article_date_mismatch"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        mutated_raw = mutate_jsonld_field(
            original_raw,
            mutation["field"],
            mutation["value"],
        )
        mutated_parser = parse_html(mutated_raw)
        self.assertIn(
            "<article>Fixture article copy remains unchanged.</article>",
            mutated_raw,
        )
        self.assertEqual(
            original_parser.is_noindex,
            mutated_parser.is_noindex,
            "generated fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_generated_seo(
            path,
            mutated_parser,
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_article_og_date_mismatch_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["article_og_date_mismatch"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        mutated_raw = mutate_meta(
            original_raw,
            mutation["field"],
            mutation["value"],
        )
        mutated_parser = parse_html(mutated_raw)
        self.assertIn('"datePublished": "2026-04-07"', mutated_raw)
        self.assertIn(
            "<article>Fixture article copy remains unchanged.</article>",
            mutated_raw,
        )
        self.assertEqual(
            original_raw.split("<body>", 1)[1],
            mutated_raw.split("<body>", 1)[1],
            "generated fixture mutation changed editorial content",
        )
        self.assertEqual(
            original_parser.is_noindex,
            mutated_parser.is_noindex,
            "generated fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_generated_seo(
            path,
            mutated_parser,
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_timezone_qualified_article_dates_compare_as_documented_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        for case_name, mutation in self.fixture_data["article_timezone_date_parity"].items():
            with self.subTest(case_name=case_name):
                mutated_raw = mutate_meta(
                    mutate_jsonld_field(
                        original_raw,
                        "datePublished",
                        mutation["jsonld_value"],
                    ),
                    "meta:article:published_time",
                    mutation["published_time"],
                )
                mutated_parser = parse_html(mutated_raw)
                self.assertIn(
                    "<article>Fixture article copy remains unchanged.</article>",
                    mutated_raw,
                )
                self.assertEqual(
                    original_parser.is_noindex,
                    mutated_parser.is_noindex,
                    "timezone fixture changed the generated indexing boundary",
                )
                findings = validator.validate_generated_seo(
                    path,
                    mutated_parser,
                    page,
                )
                if mutation["valid"]:
                    self.assertFalse(findings, findings_text(findings))
                else:
                    self.assert_rejected(findings, mutation["expected"])

    def test_article_sitemap_lastmod_contract_rejected_in_generated_metadata(self) -> None:
        route = "/writings/first-diagram-is-a-liar/"
        page = self.pages_by_route[route]
        path = GENERATED_FIXTURE / "article.html.fixture"
        baseline = validator.load_sitemap_entries()
        self.assertEqual(baseline[page["canonical"]], "2026-09-29")
        for lastmod, expected in (
            (None, "article sitemap lastmod is missing"),
            ("", "article sitemap lastmod is missing"),
            ("not-a-date", "article sitemap lastmod is not ISO 8601"),
            ("2026-05-23", "article JSON-LD dateModified does not match sitemap lastmod"),
        ):
            with self.subTest(lastmod=lastmod):
                entries = dict(baseline)
                entries[page["canonical"]] = lastmod
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(path.read_text(encoding="utf-8")),
                    page,
                    sitemap_entries=entries,
                )
                self.assert_rejected(findings, expected)

    def test_sitemap_xml_timezone_offset_survives_generated_validation(self) -> None:
        page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        raw = path.read_text(encoding="utf-8")
        sitemap_lastmod = "2026-05-24T05:30:00+05:30"

        with tempfile.TemporaryDirectory() as temporary_directory:
            sitemap_path = Path(temporary_directory) / "sitemap.xml"
            sitemap_path.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                "  <url>\n"
                f"    <loc>{page['canonical']}</loc>\n"
                f"    <lastmod>{sitemap_lastmod}</lastmod>\n"
                "  </url>\n"
                "</urlset>\n",
                encoding="utf-8",
            )
            sitemap_entries = validator.load_sitemap_entries(sitemap_path)

        self.assertEqual(sitemap_entries[page["canonical"]], sitemap_lastmod)
        for date_modified, should_pass in (
            ("2026-05-24T00:00:00Z", True),
            ("2026-05-24T00:00:01Z", False),
        ):
            with self.subTest(date_modified=date_modified):
                parser = parse_html(
                    mutate_jsonld_field(raw, "dateModified", date_modified)
                )
                findings = validator.validate_generated_seo(
                    path,
                    parser,
                    page,
                    sitemap_entries=sitemap_entries,
                )
                if should_pass:
                    self.assertFalse(findings, findings_text(findings))
                else:
                    self.assert_rejected(
                        findings,
                        "article JSON-LD dateModified does not match sitemap lastmod",
                    )

    def test_article_sitemap_date_parity_in_generated_metadata(self) -> None:
        fixture = self.fixture_data["article_sitemap_date_parity"]
        page = self.pages_by_route[fixture["route"]]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        original_articles = article_jsonld_nodes(original_raw)
        self.assertEqual(len(original_articles), 1)
        source_path = (
            ROOT / "site-src" / "pages" / page["path"]
        ).with_suffix(".extras.html")
        source_articles = article_jsonld_nodes(
            source_path.read_text(encoding="utf-8")
        )
        self.assertEqual(len(source_articles), 1)
        baseline_sitemap = validator.load_sitemap_entries()
        self.assertEqual(baseline_sitemap[page["canonical"]], "2026-09-29")
        self.assertTrue(validator.is_indexable_page(page))

        for case_name, mutation in fixture["cases"].items():
            with self.subTest(case_name=case_name):
                self.assertNotIn(
                    mutation["date_modified"],
                    {
                        source_articles[0]["dateModified"],
                        original_articles[0]["dateModified"],
                    },
                    "shared date fixture must differ from both source and generated baselines",
                )
                self.assertNotEqual(
                    mutation["sitemap_lastmod"],
                    baseline_sitemap[page["canonical"]],
                    "sitemap fixture must differ from the committed sitemap baseline",
                )
                mutated_raw = mutate_jsonld_field(
                    original_raw,
                    "dateModified",
                    mutation["date_modified"],
                )
                expected_articles = copy.deepcopy(original_articles)
                expected_articles[0]["dateModified"] = mutation["date_modified"]
                self.assertEqual(expected_articles, article_jsonld_nodes(mutated_raw))
                mutated_parser = parse_html(mutated_raw)
                self.assertEqual(original_parser.meta, mutated_parser.meta)
                self.assertEqual(
                    original_parser.is_noindex,
                    mutated_parser.is_noindex,
                    "sitemap date fixture changed the generated indexing boundary",
                )
                self.assertIn(
                    "<article>Fixture article copy remains unchanged.</article>",
                    mutated_raw,
                )

                entries = dict(baseline_sitemap)
                entries[page["canonical"]] = mutation["sitemap_lastmod"]
                findings = validator.validate_generated_seo(
                    path,
                    mutated_parser,
                    page,
                    sitemap_entries=entries,
                )
                if mutation["valid"]:
                    self.assertFalse(findings, findings_text(findings))
                else:
                    self.assert_rejected(findings, mutation["expected"])

    def test_duplicate_article_jsonld_dates_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["duplicate_article_date_mismatch"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        mutated_raw = duplicate_article_jsonld(
            original_raw, "datePublished", mutation["value"]
        )
        mutated_parser = parse_html(mutated_raw)
        self.assertIn(
            "<article>Fixture article copy remains unchanged.</article>",
            mutated_raw,
        )
        self.assertEqual(
            original_parser.is_noindex,
            mutated_parser.is_noindex,
            "generated fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_generated_seo(
            path,
            mutated_parser,
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_duplicate_article_jsonld_modified_date_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["duplicate_article_modified_date_mismatch"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        mutated_raw = duplicate_article_jsonld(
            original_raw, "dateModified", mutation["value"]
        )
        mutated_parser = parse_html(mutated_raw)
        self.assertIn(
            "<article>Fixture article copy remains unchanged.</article>",
            mutated_raw,
        )
        self.assertEqual(
            original_parser.is_noindex,
            mutated_parser.is_noindex,
            "generated fixture mutation changed the indexing boundary",
        )
        findings = validator.validate_generated_seo(
            path,
            mutated_parser,
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_graph_duplicate_article_modified_date_rejected_in_generated_metadata(self) -> None:
        baseline_path = GENERATED_FIXTURE / "article.html.fixture"
        path = GENERATED_FIXTURE / "article-graph-date-conflict.html.fixture"
        baseline_raw = baseline_path.read_text(encoding="utf-8")
        raw = path.read_text(encoding="utf-8")
        baseline_parser = parse_html(baseline_raw)
        parser = parse_html(raw)
        articles = article_jsonld_nodes(raw)

        self.assertEqual(len(articles), 2)
        self.assertEqual(
            {article["dateModified"] for article in articles},
            {"2026-05-23", "2026-05-24"},
        )
        self.assertEqual(
            baseline_raw.split("<body>", 1)[1].split("</body>", 1)[0],
            raw.split("<body>", 1)[1].split("</body>", 1)[0],
            "graph fixture changed the generated article body",
        )
        self.assertEqual(
            baseline_parser.meta,
            parser.meta,
            "graph fixture changed generated indexing or other metadata",
        )
        self.assertEqual(["index, follow"], parser.meta.get("robots"))
        self.assertEqual(
            baseline_parser.is_noindex,
            parser.is_noindex,
            "graph fixture changed the indexing boundary",
        )

        findings = validator.validate_generated_seo(
            path,
            parser,
            self.pages_by_route["/writings/first-diagram-is-a-liar/"],
        )
        self.assert_rejected(
            findings,
            "conflicting duplicate Article JSON-LD dateModified values",
        )

    def test_graph_duplicate_article_published_date_rejected_in_generated_metadata(self) -> None:
        baseline_path = GENERATED_FIXTURE / "article.html.fixture"
        path = GENERATED_FIXTURE / "article-graph-published-date-conflict.html.fixture"
        baseline_raw = baseline_path.read_text(encoding="utf-8")
        raw = path.read_text(encoding="utf-8")
        baseline_parser = parse_html(baseline_raw)
        parser = parse_html(raw)
        articles = article_jsonld_nodes(raw)

        self.assertEqual(len(articles), 2)
        self.assertEqual(
            {article["@id"] for article in articles},
            {"https://overkillhill.com/writings/first-diagram-is-a-liar/#article"},
        )
        self.assertEqual(
            {article["datePublished"] for article in articles},
            {"2026-04-07", "2026-04-08"},
        )
        self.assertEqual(
            {article["dateModified"] for article in articles},
            {"2026-05-24"},
        )
        self.assertEqual(
            baseline_raw.split("<body>", 1)[1].split("</body>", 1)[0],
            raw.split("<body>", 1)[1].split("</body>", 1)[0],
            "graph fixture changed the generated article body",
        )
        self.assertEqual(
            baseline_parser.meta,
            parser.meta,
            "graph fixture changed generated indexing or other metadata",
        )
        self.assertEqual(["index, follow"], parser.meta.get("robots"))
        self.assertEqual(
            baseline_parser.is_noindex,
            parser.is_noindex,
            "graph fixture changed the indexing boundary",
        )

        findings = validator.validate_generated_seo(
            path,
            parser,
            self.pages_by_route["/writings/first-diagram-is-a-liar/"],
        )
        self.assert_rejected(
            findings,
            "conflicting duplicate Article JSON-LD datePublished values",
        )

    def test_duplicate_article_jsonld_root_url_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["duplicate_article_url_mismatch"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        original_articles = article_jsonld_nodes(original_raw)
        mutated_raw = duplicate_article_jsonld_root_url(
            original_raw, mutation["value"]
        )
        mutated_parser = parse_html(mutated_raw)
        mutated_articles = article_jsonld_nodes(mutated_raw)
        self.assertEqual(len(mutated_articles), 2)
        self.assertNotEqual(original_articles[0]["url"], mutation["value"])
        self.assertEqual(mutated_articles[0]["url"], original_articles[0]["url"])
        self.assertEqual(mutated_articles[1]["url"], mutation["value"])
        self.assertEqual(
            mutated_articles[1]["author"]["url"],
            original_articles[0]["author"]["url"],
            "generated fixture mutation changed nested author.url",
        )
        self.assertIn(
            "<article>Fixture article copy remains unchanged.</article>",
            mutated_raw,
        )
        self.assertEqual(
            original_parser.is_noindex,
            mutated_parser.is_noindex,
            "generated fixture mutation changed the indexing boundary",
        )
        self.assertEqual(
            original_parser.meta,
            mutated_parser.meta,
            "generated fixture mutation changed robots or other metadata",
        )
        self.assertEqual(
            original_raw.split("<body>", 1)[1].split("</body>", 1)[0],
            mutated_raw.split("<body>", 1)[1].split("</body>", 1)[0],
            "generated fixture mutation changed article copy",
        )
        findings = validator.validate_generated_seo(
            path,
            mutated_parser,
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, mutation["expected"])

    def test_same_as_drift_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["organization_same_as_drift"]
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = original_raw.replace(mutation["from"], mutation["to"], 1)
        findings = validator.validate_generated_seo(
            path,
            parse_html(mutated_raw),
            self.pages_by_route["/"],
        )
        self.assert_rejected(findings, "sameAs links do not match")
        self.assertEqual(
            original_raw.split("<body>", 1)[1],
            mutated_raw.split("<body>", 1)[1],
        )

    def test_each_heat_guide_edge_rejected_in_source(self) -> None:
        for mutation in self.fixture_data["heat_guide_edges"]:
            with self.subTest(route=mutation["route"], key=mutation["key"]):
                mutated_pages = copy.deepcopy(self.source_pages)
                page = page_for_route(mutated_pages, mutation["route"])
                page[mutation["key"]] = mutation["value"]
                original = page_for_route(self.source_pages, mutation["route"])
                self.assertEqual(
                    original.get("meta:robots"),
                    page.get("meta:robots"),
                )
                findings = validator.validate_heat_guide_chain(mutated_pages)
                self.assert_rejected(findings, f"heat-guide {mutation['key']} link is")

    def test_each_heat_guide_edge_rejected_in_generated_metadata(self) -> None:
        original_pages = []
        for route in validator.HEAT_GUIDE_ROUTES:
            page = copy.deepcopy(page_for_route(self.source_pages, route))
            page["path"] = page["path"].replace(
                "index.html", "index.html.fixture"
            )
            original_pages.append(page)
        with tempfile.TemporaryDirectory(prefix="seo-fixtures-") as temp:
            generated_root = Path(temp) / "heat-guides"
            shutil.copytree(HEAT_FIXTURE, generated_root)
            for mutation in self.fixture_data["heat_guide_edges"]:
                with self.subTest(route=mutation["route"], key=mutation["key"]):
                    mutated_root = Path(temp) / (
                        f"{validator.HEAT_GUIDE_ROUTES.index(mutation['route'])}-"
                        f"{mutation['key']}"
                    )
                    shutil.copytree(generated_root, mutated_root)
                    page = page_for_route(original_pages, mutation["route"])
                    fixture_path = mutated_root / page["path"]
                    original_raw = fixture_path.read_text(encoding="utf-8")
                    mutated_raw = mutate_navigation(
                        original_raw,
                        mutation["key"],
                        mutation["value"],
                    )
                    fixture_path.write_text(mutated_raw, encoding="utf-8")
                    self.assertEqual(
                        original_raw.split("<body>", 1)[1],
                        mutated_raw.split("<body>", 1)[1],
                    )
                    findings = validator.validate_heat_guide_chain(
                        original_pages,
                        generated_root=mutated_root,
                    )
                    self.assert_rejected(
                        findings,
                        f"generated heat-guide {mutation['key']} links",
                    )

    def test_matching_social_card_metadata_passes_in_source(self) -> None:
        self.assertFalse(
            validator.validate_source_seo_contract(self.source_pages),
            "matching social-card metadata should pass",
        )

    def test_mismatched_social_card_metadata_rejected_in_source(self) -> None:
        for mutation in self.fixture_data["social_card_mismatch"]:
            with self.subTest(mutation=mutation["id"]):
                self.assert_source_seo_mutation(
                    mutation,
                    mutation["expected"],
                )

    def test_noindex_social_card_mismatch_retains_exception(self) -> None:
        mutated_pages = copy.deepcopy(self.source_pages)
        page = page_for_route(mutated_pages, self.fixture_data["noindex_social_card"]["route"])
        page["meta:twitter:image"] = self.fixture_data["noindex_social_card"]["image_value"]
        page["meta:twitter:image:alt"] = self.fixture_data["noindex_social_card"]["alt_value"]
        self.assertFalse(
            validator.validate_source_seo_contract(mutated_pages),
            "noindex pages should retain the social-card exception boundary",
        )
        generated_page = copy.deepcopy(page)
        generated_page["meta:robots"] = "noindex, nofollow"
        generated_raw = mutate_meta(
            (GENERATED_FIXTURE / "index.html.fixture").read_text(encoding="utf-8"),
            "meta:twitter:image",
            self.fixture_data["noindex_social_card"]["image_value"],
        )
        generated_raw = mutate_meta(
            generated_raw,
            "meta:twitter:image:alt",
            self.fixture_data["noindex_social_card"]["alt_value"],
        )
        generated_raw = mutate_meta(generated_raw, "meta:robots", "noindex, nofollow")
        self.assertFalse(
            validator.validate_generated_seo(
                GENERATED_FIXTURE / "index.html.fixture",
                parse_html(generated_raw),
                generated_page,
            ),
            "generated noindex pages should retain the social-card exception boundary",
        )

    def test_matching_social_card_metadata_passes_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "index.html.fixture"
        findings = validator.validate_generated_seo(
            path,
            parse_html(path.read_text(encoding="utf-8")),
            self.pages_by_route["/"],
        )
        self.assertFalse(findings, "matching social-card metadata should pass")

    def test_mismatched_social_card_metadata_rejected_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        for mutation in self.fixture_data["social_card_mismatch"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = mutate_meta(
                    original_raw,
                    mutation["field"],
                    mutation["value"],
                )
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                )
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(mutated_raw),
                    self.pages_by_route["/"],
                )
                self.assert_rejected(findings, mutation["expected"])

    def assert_rejected(self, findings: list, expected: str) -> None:
        self.assertTrue(findings, "mutation unexpectedly passed")
        self.assertIn(expected, findings_text(findings))

    def assert_source_seo_mutation(
        self,
        mutation: dict,
        expected: str,
    ) -> None:
        original = page_for_route(self.source_pages, mutation["route"])
        mutated = copy.deepcopy(original)
        if "value" in mutation:
            mutated[mutation["field"]] = mutation["value"]
        else:
            mutated.pop(mutation["field"], None)
        self.assertEqual(
            original.get("meta:robots"),
            mutated.get("meta:robots"),
            "SEO fixture changed the source indexing boundary",
        )
        self.assertEqual(
            {key: value for key, value in original.items() if not key.startswith("meta:")},
            {key: value for key, value in mutated.items() if not key.startswith("meta:")},
            "SEO fixture changed source editorial or routing fields",
        )
        findings = validator.validate_source_seo_contract(
            [
                mutated if page is original else page
                for page in self.source_pages
            ]
        )
        self.assert_rejected(findings, expected)

    def test_retired_social_image_rejected_in_source(self) -> None:
        mutation = self.fixture_data["retired_social_image"]
        self.assert_source_seo_mutation(
            mutation,
            "indexable source page uses retired social image",
        )

    def test_mismatched_image_dimensions_rejected_in_source(self) -> None:
        mutation = self.fixture_data["image_contract"][0]
        self.assert_source_seo_mutation(
            mutation,
            "social image dimensions",
        )

    def test_mismatched_image_type_rejected_in_source(self) -> None:
        mutation = self.fixture_data["image_contract"][1]
        self.assert_source_seo_mutation(
            mutation,
            "social image type",
        )

    def test_mismatched_social_images_rejected_in_source(self) -> None:
        mutation = self.fixture_data["social_image_parity"]
        self.assert_source_seo_mutation(
            mutation,
            "social card image mismatch",
        )

    def test_missing_article_metadata_rejected_in_source(self) -> None:
        mutation = self.fixture_data["missing_article_metadata"]
        self.assert_source_seo_mutation(
            mutation,
            "article source page is missing article:published_time",
        )

    def test_malformed_article_metadata_rejected_in_source(self) -> None:
        for mutation in self.fixture_data["malformed_article_metadata"]:
            with self.subTest(mutation=mutation["id"]):
                self.assert_source_seo_mutation(
                    mutation,
                    mutation["expected_source"]
                    if "expected_source" in mutation
                    else mutation["expected"],
                )

    def test_same_as_drift_rejected_in_shared_head_source(self) -> None:
        mutation = self.fixture_data["organization_same_as_drift"]
        original_raw = validator.HEAD_PARTIAL.read_text(encoding="utf-8")
        mutated_raw = original_raw.replace(mutation["from"], mutation["to"], 1)
        self.assertNotEqual(original_raw, mutated_raw)
        self.assertEqual(
            mutated_raw.replace(mutation["to"], mutation["from"], 1),
            original_raw,
            "head fixture mutation changed editorial content",
        )
        findings = validator.validate_organization_nodes(
            "tests/fixtures/seo/head.html.fixture",
            parse_html(mutated_raw),
        )
        self.assert_rejected(findings, "sameAs links do not match")

    def test_generated_metadata_baseline_is_valid(self) -> None:
        root_page = self.pages_by_route["/"]
        article_page = self.pages_by_route["/writings/first-diagram-is-a-liar/"]
        for fixture_name, manifest_page in (
            ("index.html.fixture", root_page),
            ("article.html.fixture", article_page),
        ):
            path = GENERATED_FIXTURE / fixture_name
            raw = path.read_text(encoding="utf-8")
            parser = parse_html(raw)
            self.assertFalse(
                validator.validate_generated_seo(path, parser, manifest_page),
                f"valid generated fixture failed: {fixture_name}",
            )
            self.assertIn("Fixture", raw)
            self.assertIn("index, follow", raw)

    def test_retired_social_image_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["retired_social_image"]
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        for field in ("meta:og:image", "meta:twitter:image"):
            with self.subTest(field=field):
                mutated_raw = mutate_meta(
                    original_raw,
                    field,
                    mutation["value"],
                )
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                    "generated fixture mutation changed editorial content",
                )
                self.assertIn('name="robots" content="index, follow"', mutated_raw)
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(mutated_raw),
                    self.pages_by_route["/"],
                )
                self.assert_rejected(findings, f"uses retired social image: {field}")

    def test_mismatched_image_metadata_rejected_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        for mutation in self.fixture_data["image_contract"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = mutate_meta(
                    original_raw,
                    mutation["field"],
                    mutation["value"],
                )
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                )
                findings = validator.validate_generated_seo(
                    path,
                    parse_html(mutated_raw),
                    self.pages_by_route["/"],
                )
                self.assert_rejected(findings, "social image")

    def test_mismatched_social_images_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["social_image_parity"]
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = mutate_meta(
            original_raw,
            mutation["field"],
            mutation["value"],
        )
        self.assertEqual(
            original_raw.split("<body>", 1)[1],
            mutated_raw.split("<body>", 1)[1],
            "generated fixture mutation changed editorial content",
        )
        findings = validator.validate_generated_seo(
            path,
            parse_html(mutated_raw),
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, "social card image mismatch")

    def test_missing_article_metadata_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["missing_article_metadata"]
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = mutate_meta(original_raw, mutation["field"], None)
        self.assertEqual(
            original_raw.split("<body>", 1)[1],
            mutated_raw.split("<body>", 1)[1],
        )
        self.assertIn('name="robots" content="index, follow"', mutated_raw)
        findings = validator.validate_generated_seo(
            path,
            parse_html(mutated_raw),
            self.pages_by_route[mutation["route"]],
        )
        self.assert_rejected(findings, "article generated page is missing")

    def test_malformed_article_metadata_rejected_in_generated_metadata(self) -> None:
        path = GENERATED_FIXTURE / "article.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        original_parser = parse_html(original_raw)
        for mutation in self.fixture_data["malformed_article_metadata"]:
            with self.subTest(mutation=mutation["id"]):
                mutated_raw = mutate_meta(
                    original_raw,
                    mutation["field"],
                    mutation["value"],
                )
                mutated_parser = parse_html(mutated_raw)
                self.assertEqual(
                    original_raw.split("<body>", 1)[1],
                    mutated_raw.split("<body>", 1)[1],
                    "generated fixture mutation changed editorial content",
                )
                self.assertEqual(
                    original_parser.is_noindex,
                    mutated_parser.is_noindex,
                    "generated fixture mutation changed the indexing boundary",
                )
                findings = validator.validate_generated_seo(
                    path,
                    mutated_parser,
                    self.pages_by_route[mutation["route"]],
                )
                self.assert_rejected(
                    findings,
                    mutation["expected_generated"]
                    if "expected_generated" in mutation
                    else mutation["expected"],
                )

    def test_same_as_drift_rejected_in_generated_metadata(self) -> None:
        mutation = self.fixture_data["organization_same_as_drift"]
        path = GENERATED_FIXTURE / "index.html.fixture"
        original_raw = path.read_text(encoding="utf-8")
        mutated_raw = original_raw.replace(mutation["from"], mutation["to"], 1)
        findings = validator.validate_generated_seo(
            path,
            parse_html(mutated_raw),
            self.pages_by_route["/"],
        )
        self.assert_rejected(findings, "sameAs links do not match")
        self.assertEqual(
            original_raw.split("<body>", 1)[1],
            mutated_raw.split("<body>", 1)[1],
        )

    def test_each_heat_guide_edge_rejected_in_source(self) -> None:
        for mutation in self.fixture_data["heat_guide_edges"]:
            with self.subTest(route=mutation["route"], key=mutation["key"]):
                mutated_pages = copy.deepcopy(self.source_pages)
                page = page_for_route(mutated_pages, mutation["route"])
                page[mutation["key"]] = mutation["value"]
                original = page_for_route(self.source_pages, mutation["route"])
                self.assertEqual(
                    original.get("meta:robots"),
                    page.get("meta:robots"),
                )
                findings = validator.validate_heat_guide_chain(mutated_pages)
                self.assert_rejected(findings, f"heat-guide {mutation['key']} link is")

    def test_each_heat_guide_edge_rejected_in_generated_metadata(self) -> None:
        original_pages = []
        for route in validator.HEAT_GUIDE_ROUTES:
            page = copy.deepcopy(page_for_route(self.source_pages, route))
            page["path"] = page["path"].replace(
                "index.html", "index.html.fixture"
            )
            original_pages.append(page)
        with tempfile.TemporaryDirectory(prefix="seo-fixtures-") as temp:
            generated_root = Path(temp) / "heat-guides"
            shutil.copytree(HEAT_FIXTURE, generated_root)
            for mutation in self.fixture_data["heat_guide_edges"]:
                with self.subTest(route=mutation["route"], key=mutation["key"]):
                    mutated_root = Path(temp) / (
                        f"{validator.HEAT_GUIDE_ROUTES.index(mutation['route'])}-"
                        f"{mutation['key']}"
                    )
                    shutil.copytree(generated_root, mutated_root)
                    page = page_for_route(original_pages, mutation["route"])
                    fixture_path = mutated_root / page["path"]
                    original_raw = fixture_path.read_text(encoding="utf-8")
                    mutated_raw = mutate_navigation(
                        original_raw,
                        mutation["key"],
                        mutation["value"],
                    )
                    fixture_path.write_text(mutated_raw, encoding="utf-8")
                    self.assertEqual(
                        original_raw.split("<body>", 1)[1],
                        mutated_raw.split("<body>", 1)[1],
                    )
                    findings = validator.validate_heat_guide_chain(
                        original_pages,
                        generated_root=mutated_root,
                    )
                    self.assert_rejected(
                        findings,
                        f"generated heat-guide {mutation['key']} links",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)

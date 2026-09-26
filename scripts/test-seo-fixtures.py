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

    def test_locale_search_index_rejects_malformed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            index_path = Path(directory) / "search-index.fr.json"
            for entry in (None, "invalid", {}, {"url": None}, {"url": 7},
                          {"url": []}, {"url": {}}, {"url": ""}, {"url": " "}):
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
                    self.assertIn("locale search index entry 0 must have a non-empty string URL", findings)
                    self.assertIn("locale search index contains undeclared routes: /fr/retired/", findings)

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
                f"<url><loc>{location}</loc><lastmod>2026-05-28</lastmod></url>"
                f"<url><loc>{location}</loc><lastmod>2026-05-28</lastmod></url>"
                "</urlset>",
                encoding="utf-8",
            )

            findings = validator.validate_sitemap_duplicates(sitemap_path)
            text = findings_text(findings)
            self.assertIn(
                f"duplicate sitemap location: {location} appears 3 times",
                text,
            )
            self.assertIn(
                f"conflicting duplicate sitemap lastmod values for {location}",
                text,
            )
            self.assertIn("2026-05-24", text)
            self.assertIn("2026-05-28", text)
            self.assertEqual(
                validator.load_sitemap_entries(sitemap_path)[location],
                "2026-05-24",
                "duplicate parsing must not let a later lastmod silently win",
            )

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
            self.assertNotIn("conflicting duplicate sitemap lastmod values", text)

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
                    '"description": "From AutoCAD 10 and Visio trauma',
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
            '"description": "From AutoCAD 10 and Visio trauma',
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
                    '"description": "From AutoCAD 10 and Visio trauma',
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
        self.assertEqual(baseline[sitemap_url], "2026-05-24")
        for lastmod, expected in (
            (None, "article sitemap lastmod is missing"),
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
            '"description": "From AutoCAD 10 and Visio trauma',
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
        self.assertEqual(baseline[page["canonical"]], "2026-05-24")
        for lastmod, expected in (
            (None, "article sitemap lastmod is missing"),
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

import contextlib
import importlib.util
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-i18n-release.py"
SPEC = importlib.util.spec_from_file_location("check_i18n_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

DETECTOR = ROOT / ".agents" / "skills" / "okhp3-i18n-page-sync" / "scripts" / "i18n-page-sync.py"
DETECTOR_SPEC = importlib.util.spec_from_file_location("i18n_page_sync", DETECTOR)
DETECTOR_MODULE = importlib.util.module_from_spec(DETECTOR_SPEC)
assert DETECTOR_SPEC.loader is not None
DETECTOR_SPEC.loader.exec_module(DETECTOR_MODULE)

REGIONAL_BUILDER = ROOT / "scripts" / "build-locale-drafts.py"
REGIONAL_BUILDER_SPEC = importlib.util.spec_from_file_location("build_locale_drafts", REGIONAL_BUILDER)
REGIONAL_BUILDER_MODULE = importlib.util.module_from_spec(REGIONAL_BUILDER_SPEC)
assert REGIONAL_BUILDER_SPEC.loader is not None
REGIONAL_BUILDER_SPEC.loader.exec_module(REGIONAL_BUILDER_MODULE)


class I18nReleaseTests(unittest.TestCase):
    def test_text_report_lists_current_duplicate_missing_and_superseded_records_by_route(self):
        audit = {
            "current_pairs": [
                {"locale": "de", "route": "/", "records": ["i18n/pilot/de/current-home.json"]},
                {"locale": "es", "route": "/", "records": ["i18n/pilot/es/current-home.json"]},
            ],
            "missing": [
                {"locale": "de", "route": "/about/"},
                {"locale": "es", "route": "/about/"},
            ],
            "duplicates": [
                {
                    "locale": "de", "route": "/",
                    "records": ["i18n/pilot/de/current-home.json", "i18n/pilot/de/second-home.json"],
                },
                {
                    "locale": "es", "route": "/about/",
                    "record": "i18n/pilot/es/duplicate-about.json", "entry_count": 2,
                },
            ],
            "superseded": [{
                "locale": "de", "route": "/",
                "record": "i18n/pilot/de/old-home.json",
                "superseded_by": ["i18n/pilot/de/current-home.json"],
            }],
        }

        lines = MODULE.format_advisory_review_routes(
            audit, ["de", "es"], ["/", "/about/"],
        )
        output = "\n".join(lines)

        self.assertIn(
            "/: de: i18n/pilot/de/current-home.json; duplicate: current records: "
            "i18n/pilot/de/current-home.json, i18n/pilot/de/second-home.json; "
            "superseded: i18n/pilot/de/old-home.json -> i18n/pilot/de/current-home.json "
            "| es: i18n/pilot/es/current-home.json",
            output,
        )
        self.assertIn("de: MISSING (no current review record)", output)
        self.assertIn(
            "es: MISSING (no current review record); duplicate: repeated entries in "
            "i18n/pilot/es/duplicate-about.json (2 entries)",
            output,
        )

    def test_text_report_does_not_change_check_exit_status(self):
        config = {
            "blocking_locales": ["fr"],
            "advisory_content_coverage_locales": ["de", "es"],
            "in_scope_routes": ["/"],
        }
        results = {
            "missing": [], "stale": [], "needs_baseline": [], "target_changed": [],
            "source_coverage_gaps": [],
            "advisory_review_evidence": {
                "current_pairs": [],
                "missing": [{"locale": "de", "route": "/"}, {"locale": "es", "route": "/"}],
                "duplicates": [],
                "superseded": [], "unmatched": [], "invalid_records": [],
            },
            "policy": {
                "blocking_locales": ["fr"],
                "blocking_items": [{"locale": "fr", "route": "/"}],
            },
        }
        output = io.StringIO()
        with patch.object(MODULE, "load_site_config", return_value=config), patch.object(
            MODULE, "load_results", return_value=results
        ), contextlib.redirect_stdout(output):
            status = MODULE.main(["--mode", "check", "--format", "text"])

        self.assertEqual(1, status)
        self.assertIn("/: de: MISSING (no current review record) | es: MISSING", output.getvalue())

    def test_advisory_review_audit_reports_missing_duplicate_and_superseded_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pilot = root / "i18n" / "pilot" / "de"
            pilot.mkdir(parents=True)
            state = {
                "schema_version": "1.0",
                "pages": {
                    "/": {"targets": {"de": {
                        "synced_source_sha256": "a" * 64,
                        "target_sha256": "b" * 64,
                    }}},
                    "/about/": {"targets": {"de": {
                        "synced_source_sha256": "e" * 64,
                        "target_sha256": "f" * 64,
                    }}},
                },
            }
            (root / "i18n" / "sync-state.json").write_text(json.dumps(state), encoding="utf-8")
            current = {
                "route": "/", "target_path": "de/index.html",
                "source_sha256": "a" * 64, "target_sha256": "b" * 64,
            }
            record_base = {
                "language_pair": "en-US -> de-DE",
                "review_status": "ai-reviewed",
            }
            (pilot / "current-review-2026-10-10.json").write_text(json.dumps({
                **record_base, "reviewed_on": "2026-10-10", "routes": [current, current],
            }), encoding="utf-8")
            (pilot / "old-review-2026-10-01.json").write_text(json.dumps({
                **record_base, "reviewed_on": "2026-10-01",
                "routes": [{
                    **current, "source_sha256": "c" * 64, "target_sha256": "d" * 64,
                }],
            }), encoding="utf-8")
            (pilot / "about-review-2026-10-02.json").write_text(json.dumps({
                **record_base, "reviewed_on": "2026-10-02",
                "routes": [{
                    "route": "/about/", "target_path": "de/about/index.html",
                    "source_sha256": "c" * 64, "target_sha256": "d" * 64,
                }],
            }), encoding="utf-8")
            config = {
                "state_file": "i18n/sync-state.json",
                "in_scope_routes": ["/", "/about/"],
                "advisory_content_coverage_locales": ["de"],
                "target_locales": {"de": {"locale": "de-DE", "root": "de"}},
            }
            with patch.object(MODULE, "ROOT", root):
                report = MODULE.audit_advisory_review_evidence(config)

        self.assertEqual([{"locale": "de", "route": "/about/"}], report["missing"])
        self.assertTrue(any(item.get("entry_count") == 2 for item in report["duplicates"]))
        self.assertEqual("old-review-2026-10-01.json", Path(
            report["superseded"][0]["record"]
        ).name)
        self.assertEqual("current-review-2026-10-10.json", Path(
            report["superseded"][0]["superseded_by"][0]
        ).name)
        self.assertEqual(
            "about-review-2026-10-02.json",
            Path(report["unmatched"][0]["record"]).name,
        )

    def test_advisory_review_audit_excludes_malformed_records_from_current_pairs(self):
        malformed_cases = [
            (
                "reviewed_on",
                "2026-02-30",
                "reviewed_on must be a real ISO calendar date",
            ),
            (
                "source_sha256",
                "not-a-sha256",
                "source_sha256 is missing or malformed",
            ),
            (
                "target_path",
                "de/wrong/index.html",
                "route is out of scope or target_path does not match the configured locale",
            ),
        ]

        for field, malformed_value, expected_reason in malformed_cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                pilot = root / "i18n" / "pilot" / "de"
                pilot.mkdir(parents=True)
                source_hash = "a" * 64
                target_hash = "b" * 64
                (root / "i18n" / "sync-state.json").write_text(json.dumps({
                    "schema_version": "1.0",
                    "pages": {
                        "/": {"targets": {"de": {
                            "synced_source_sha256": source_hash,
                            "target_sha256": target_hash,
                        }}},
                    },
                }), encoding="utf-8")
                record = {
                    "language_pair": "en-US -> de-DE",
                    "review_status": "ai-reviewed",
                    "reviewed_on": "2026-10-13",
                    "routes": [{
                        "route": "/",
                        "target_path": "de/index.html",
                        "source_sha256": source_hash,
                        "target_sha256": target_hash,
                    }],
                }
                if field == "reviewed_on":
                    record[field] = malformed_value
                else:
                    record["routes"][0][field] = malformed_value
                record_path = pilot / "review-2026-10-13.json"
                record_path.write_text(json.dumps(record), encoding="utf-8")
                config = {
                    "state_file": "i18n/sync-state.json",
                    "in_scope_routes": ["/"],
                    "advisory_content_coverage_locales": ["de"],
                    "target_locales": {"de": {"locale": "de-DE", "root": "de"}},
                }

                with patch.object(MODULE, "ROOT", root):
                    report = MODULE.audit_advisory_review_evidence(config)

                self.assertEqual([], report["current_pairs"])
                self.assertEqual([{"locale": "de", "route": "/"}], report["missing"])
                self.assertTrue(any(
                    item.get("record") == record_path.relative_to(root).as_posix()
                    and expected_reason in item.get("reason", "")
                    for item in report["invalid_records"]
                ), report["invalid_records"])

    def test_content_coverage_names_missing_sections_blocks_and_protected_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.html"
            target = root / "target.html"
            source.write_text(
                '<main><h2 id="intro">Introduction</h2><p>Lead.</p>'
                '<h2 id="proof">Evidence</h2><p>Details.</p><li>Source item</li>'
                '<a href="https://example.test/protected">Protected link</a></main>',
                encoding="utf-8",
            )
            target.write_text(
                '<main><h2 id="intro">Einleitung</h2><p>Einleitung.</p></main>',
                encoding="utf-8",
            )
            with patch.object(MODULE, "ROOT", root):
                result = MODULE.compare_content_coverage(
                    source,
                    target,
                    "de",
                    "/about/",
                )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(("de", "/about/"), (result["locale"], result["route"]))
        self.assertIn(
            ("heading", "Evidence"),
            [(item["kind"], item.get("heading")) for item in result["omissions"]],
        )
        self.assertIn(
            ("content_block", "li"),
            [(item["kind"], item.get("block")) for item in result["omissions"]],
        )
        self.assertIn(
            ("protected_link", "https://example.test/protected"),
            [(item["kind"], item.get("href")) for item in result["omissions"]],
        )

    def test_content_block_deficits_name_retained_shortened_sections_for_advisory_locales(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.html"
            target = root / "target.html"
            source.write_text(
                '<main><h2 id="overview">Overview</h2><p>First paragraph.</p>'
                '<p>Second paragraph.</p><h2 id="evidence">Evidence</h2>'
                '<p>Evidence paragraph.</p></main>',
                encoding="utf-8",
            )
            target.write_text(
                '<main><h2 id="overview">Übersicht</h2><p>Erster Absatz.</p>'
                '<h2 id="evidence">Evidenz</h2><p>Beleg.</p></main>',
                encoding="utf-8",
            )
            results = {}
            with patch.object(MODULE, "ROOT", root):
                for locale in ("de", "es"):
                    results[locale] = MODULE.compare_content_coverage(
                        source,
                        target,
                        locale,
                        "/about/",
                    )

        for locale, result in results.items():
            with self.subTest(locale=locale):
                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(locale, result["locale"])
                paragraph_gap = next(
                    item for item in result["omissions"]
                    if item["kind"] == "content_block" and item["block"] == "p"
                )
                self.assertEqual(1, paragraph_gap["omitted_count"])
                self.assertEqual([{
                    "heading": "Overview",
                    "heading_id": "overview",
                    "source_count": 2,
                    "target_count": 1,
                    "omitted_count": 1,
                }], paragraph_gap["sections"])
                self.assertIn(
                    "sections: Overview (2 source / 1 target)",
                    MODULE.format_coverage_omission(paragraph_gap),
                )

    def test_advisory_content_gaps_are_reported_without_changing_noindex_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "about" / "index.html"
            target = root / "de" / "about" / "index.html"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            source.write_text(
                '<main><h2 id="intro">Introduction</h2><p>Lead.</p>'
                '<h2 id="proof">Evidence</h2><p>Details.</p></main>',
                encoding="utf-8",
            )
            target_html = (
                '<meta name="robots" content="noindex, follow">'
                '<main><h2 id="intro">Einleitung</h2><p>Einleitung.</p></main>'
            )
            target.write_text(target_html, encoding="utf-8")
            config = {
                "blocking_locales": [],
                "advisory_content_coverage_locales": ["de"],
                "state_file": "i18n/sync-state.json",
            }
            report = {
                "missing": [],
                "stale": [],
                "needs_baseline": [],
                "in_sync": [{
                    "route": "/about/",
                    "locale": "de",
                    "source_path": "about/index.html",
                    "target_path": "de/about/index.html",
                }],
                "orphan": [],
            }
            with patch.object(MODULE, "ROOT", root), patch.object(
                MODULE, "run_detector", return_value=report
            ):
                result = MODULE.load_results(config)

            self.assertEqual([], result["policy"]["blocking_items"])
            self.assertTrue(any(
                item["status"] == "source_coverage_gap"
                and item["locale"] == "de"
                and item["route"] == "/about/"
                for item in result["policy"]["advisory_items"]
            ))
            self.assertEqual(target_html, target.read_text(encoding="utf-8"))

    def test_shortened_sections_in_german_and_spanish_remain_advisory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "about" / "index.html"
            source.parent.mkdir(parents=True)
            source.write_text(
                '<main><h2 id="overview">Overview</h2><p>First.</p><p>Second.</p></main>',
                encoding="utf-8",
            )
            items = []
            for locale, heading in (("de", "Übersicht"), ("es", "Resumen")):
                target = root / locale / "about" / "index.html"
                target.parent.mkdir(parents=True)
                target.write_text(
                    f'<main><h2 id="overview">{heading}</h2><p>Translated.</p></main>',
                    encoding="utf-8",
                )
                items.append({
                    "route": "/about/",
                    "locale": locale,
                    "source_path": "about/index.html",
                    "target_path": f"{locale}/about/index.html",
                })
            config = {
                "blocking_locales": ["fr"],
                "advisory_content_coverage_locales": ["de", "es"],
                "state_file": "i18n/sync-state.json",
                "in_scope_routes": ["/about/"],
                "target_locales": {
                    "de": {"locale": "de-DE", "root": "de"},
                    "es": {"locale": "es-ES", "root": "es"},
                    "fr": {"locale": "fr-FR", "root": "fr"},
                },
            }
            detector_report = {
                "missing": [],
                "stale": [],
                "needs_baseline": [],
                "in_sync": items,
                "orphan": [],
            }
            with patch.object(MODULE, "ROOT", root), patch.object(
                MODULE, "run_detector", return_value=detector_report
            ):
                result = MODULE.load_results(config)

        self.assertEqual([], result["policy"]["blocking_items"])
        self.assertEqual(
            {"de", "es"},
            {
                item["locale"] for item in result["policy"]["advisory_items"]
                if item["status"] == "source_coverage_gap"
            },
        )

    def test_coverage_dispositions_annotate_without_hiding_unresolved_report_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "about" / "index.html"
            target = root / "de" / "about" / "index.html"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            source.write_text(
                '<main><h2 id="overview">Overview</h2><p>One.</p><p>Two.</p>'
                '<h2 id="missing">Missing section</h2><p>Still source-only.</p>'
                '<a href="https://example.test/source">Source link</a></main>',
                encoding="utf-8",
            )
            target_html = (
                '<meta name="robots" content="noindex, follow">'
                '<main><h2 id="overview">Übersicht</h2><p>Ein Absatz.</p></main>'
            )
            target.write_text(target_html, encoding="utf-8")
            source_hash = MODULE.page_hash(source)
            target_hash = MODULE.page_hash(target)
            review_path = root / "i18n" / "pilot" / "de" / "content-coverage-review-2026-10-13.json"
            review_path.parent.mkdir(parents=True)
            review_path.write_text(json.dumps({
                "language_pair": "en-US -> de-DE",
                "record_type": "content-coverage-disposition",
                "review_status": "ai-reviewed",
                "reviewed_on": "2026-10-13",
                "native_or_human_approval": False,
                "release_accepted": False,
                "routes": [{
                    "route": "/about/",
                    "locale": "de",
                    "source_sha256": source_hash,
                    "target_path": "de/about/index.html",
                    "target_sha256": target_hash,
                    "coverage_dispositions": [{
                        "section_id": "overview",
                        "disposition": "intentional-abridgment",
                        "rationale": "The translated section is intentionally concise.",
                    }],
                    "unscoped_disposition": {
                        "disposition": "unresolved",
                        "rationale": "Unattributed report findings still need review.",
                    },
                }],
            }), encoding="utf-8")
            state_path = root / "i18n" / "sync-state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({
                "schema_version": "1.0",
                "pages": {
                    "/about/": {"targets": {"de": {
                        "synced_source_sha256": source_hash,
                        "target_sha256": target_hash,
                    }}},
                },
            }), encoding="utf-8")
            gaps = [{
                "locale": "de",
                "route": "/about/",
                "omissions": [
                    {
                        "kind": "heading",
                        "heading": "Missing section",
                        "heading_id": "missing",
                    },
                    {
                        "kind": "content_block",
                        "block": "p",
                        "source_count": 2,
                        "target_count": 1,
                        "omitted_count": 1,
                        "sections": [{
                            "heading": "Overview",
                            "heading_id": "overview",
                            "source_count": 2,
                            "target_count": 1,
                            "omitted_count": 1,
                        }],
                    },
                    {
                        "kind": "protected_link",
                        "href": "https://example.test/source",
                    },
                ],
            }]
            config = {
                "state_file": "i18n/sync-state.json",
                "advisory_content_coverage_locales": ["de"],
                "advisory_coverage_review_records": {
                    "de": "i18n/pilot/de/content-coverage-review-2026-10-13.json",
                },
                "target_locales": {"de": {"locale": "de-DE", "root": "de"}},
            }
            with patch.object(MODULE, "ROOT", root):
                result = MODULE.apply_coverage_dispositions(gaps, config)
                self.assertEqual(target_html, target.read_text(encoding="utf-8"))

        self.assertEqual(3, len(result[0]["omissions"]))
        self.assertEqual(2, len(result[0]["unresolved_omissions"]))
        self.assertEqual(
            "intentional-abridgment",
            result[0]["omissions"][1]["sections"][0]["review_disposition"]["disposition"],
        )
        self.assertEqual(
            "unresolved",
            result[0]["omissions"][0]["review_disposition"]["disposition"],
        )
        self.assertEqual(
            "unresolved",
            result[0]["omissions"][2]["review_disposition"]["disposition"],
        )
        self.assertIn(
            "[unresolved]",
            MODULE.format_coverage_omission(result[0]["omissions"][2]),
        )

    def test_detector_hash_is_stable_across_checkout_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf = root / "lf.html"
            crlf = root / "crlf.html"
            changed = root / "changed.html"
            spaced = root / "spaced.html"
            unspaced = root / "unspaced.html"
            lf.write_bytes(b"<p>stable</p>\n")
            crlf.write_bytes(b"<p>stable</p>\r\n")
            changed.write_bytes(b"<p>changed</p>\r\n")
            spaced.write_bytes(b"<p>a b</p>\n")
            unspaced.write_bytes(b"<p>ab</p>\n")
            self.assertEqual(DETECTOR_MODULE.sha256_file(lf), DETECTOR_MODULE.sha256_file(crlf))
            self.assertNotEqual(DETECTOR_MODULE.sha256_file(lf), DETECTOR_MODULE.sha256_file(changed))
            self.assertNotEqual(DETECTOR_MODULE.sha256_file(spaced), DETECTOR_MODULE.sha256_file(unspaced))

    def test_regional_source_hash_ignores_generated_metadata_but_not_visible_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.html"
            regenerated = root / "regenerated.html"
            changed = root / "changed.html"
            changed_asset = root / "changed-asset.html"
            original.write_text('<meta http-equiv="Content-Security-Policy" content="one"><link href="/assets/css/theme.css?v=11111111"><p>stable ?v=11111111</p>\n', encoding="utf-8")
            regenerated.write_text('<meta content="two" http-equiv="Content-Security-Policy"><link href="/assets/css/theme.css?v=22222222"><p>stable ?v=11111111</p>\r\n', encoding="utf-8", newline="")
            changed.write_text('<meta http-equiv="Content-Security-Policy" content="two"><link href="/assets/css/theme.css?v=22222222"><p>changed ?v=11111111</p>\n', encoding="utf-8")
            changed_asset.write_text('<meta http-equiv="Content-Security-Policy" content="two"><link href="/assets/css/other.css?v=22222222"><p>stable ?v=11111111</p>\n', encoding="utf-8")
            changed_visible_version = root / "changed-visible-version.html"
            changed_visible_version.write_text('<meta http-equiv="Content-Security-Policy" content="two"><link href="/assets/css/theme.css?v=22222222"><p>stable ?v=cafebabe</p>\n', encoding="utf-8")
            self.assertEqual(
                REGIONAL_BUILDER_MODULE.canonical_text_hash(original),
                REGIONAL_BUILDER_MODULE.canonical_text_hash(regenerated),
            )
            self.assertNotEqual(
                REGIONAL_BUILDER_MODULE.canonical_text_hash(original),
                REGIONAL_BUILDER_MODULE.canonical_text_hash(changed),
            )
            self.assertNotEqual(
                REGIONAL_BUILDER_MODULE.canonical_text_hash(original),
                REGIONAL_BUILDER_MODULE.canonical_text_hash(changed_asset),
            )
            self.assertNotEqual(
                REGIONAL_BUILDER_MODULE.canonical_text_hash(original),
                REGIONAL_BUILDER_MODULE.canonical_text_hash(changed_visible_version),
            )

    def test_full_report_preserves_all_pairs_and_blocks_only_french(self):
        report = {
            "missing": [{"route": f"/missing-{index}/", "locale": "fr"} for index in range(4)]
            + [{"route": f"/missing-{index}/", "locale": "de"} for index in range(4)],
            "stale": [{"route": f"/stale-{index}/", "locale": "es", "target_path": "es/index.html"} for index in range(4)],
            "needs_baseline": [],
            "in_sync": [],
            "orphan": [],
        }
        config = MODULE.load_site_config()
        with patch.object(MODULE, "run_detector", return_value=report), patch.object(MODULE, "page_hash", return_value=None):
            result = MODULE.load_results(config)
        self.assertEqual(12, sum(len(result[key]) for key in ("missing", "stale", "needs_baseline")))
        self.assertEqual(set(), {item["locale"] for item in result["policy"]["blocking_items"]})
        self.assertEqual({"de", "es", "fr"}, {item["locale"] for item in result["policy"]["advisory_items"]})
        self.assertEqual(0, len(result["policy"]["blocking_items"]))
        self.assertEqual(12, len(result["policy"]["advisory_items"]))

    def test_all_current_blocking_locale_is_not_blocked(self):
        report = {
            "missing": [],
            "stale": [{"route": "/fixture/", "locale": "de", "target_path": "de/index.html"}, {"route": "/fixture/", "locale": "es", "target_path": "es/index.html"}],
            "needs_baseline": [],
            "in_sync": [],
            "orphan": [],
        }
        config = MODULE.load_site_config()
        with patch.object(MODULE, "run_detector", return_value=report), patch.object(MODULE, "page_hash", return_value=None):
            result = MODULE.load_results(config)
        self.assertEqual([], result["policy"]["blocking_items"])
        self.assertEqual(2, len(result["policy"]["advisory_items"]))

    def test_invalid_blocking_locale_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "i18n").mkdir()
            (root / "i18n" / "sync.config.json").write_text(
                json.dumps({"schema_version": "1.0", "target_locales": {"fr": {}}, "blocking_locales": ["de"]}),
                encoding="utf-8",
            )
            with patch.object(MODULE, "ROOT", root):
                with self.assertRaises(ValueError):
                    MODULE.load_site_config()

    def test_malformed_portable_report_fails_closed(self):
        with patch.object(MODULE.subprocess, "run", return_value=MODULE.subprocess.CompletedProcess([], 0, "not json", "")):
            with self.assertRaises(ValueError):
                MODULE.run_detector(Path("missing-config.json"))

    def test_malformed_adopted_item_fails_before_field_indexing(self):
        config = {
            "schema_version": "1.0",
            "target_locales": {"fr": {"locale": "fr-FR", "root": "fr"}},
            "state_file": "i18n/sync-state.json",
        }
        with patch.object(MODULE, "load_provenance", return_value={"routes": []}), patch.object(
            MODULE, "run_detector", return_value={"adopted": [{}]}
        ):
            with self.assertRaisesRegex(ValueError, "missing or empty fields"):
                MODULE.adopt(["fr"], ["/"], Path("review.json"), config)

    def test_real_adoption_updates_only_french_ledger_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "i18n").mkdir()
            (root / "assets" / "data").mkdir(parents=True)
            (root / "fr").mkdir()
            (root / "de").mkdir()
            (root / "es").mkdir()
            (root / "index.html").write_text("<html>current source</html>", encoding="utf-8")
            (root / "about").mkdir()
            (root / "about" / "index.html").write_text("<html>about source</html>", encoding="utf-8")
            for locale in ("fr", "de", "es"):
                (root / locale / "index.html").write_text(f"<html>{locale}</html>", encoding="utf-8")
                (root / locale / "about").mkdir()
                (root / locale / "about" / "index.html").write_text(f"<html>{locale} about</html>", encoding="utf-8")
            (root / "assets" / "data" / "search-index.json").write_text(
                json.dumps({"entries": [{"url": "/"}, {"url": "/about/"}]}), encoding="utf-8"
            )
            config = {
                "schema_version": "1.0",
                "search_index": "assets/data/search-index.json",
                "state_file": "i18n/sync-state.json",
                "in_scope_routes": ["/", "/about/"],
                "blocking_locales": ["fr"],
                "target_locales": {
                    key: {"locale": f"{key}-FR" if key == "fr" else key, "root": key, "skill": "pair"}
                    for key in ("fr", "de", "es")
                },
            }
            original = {
                "schema_version": "1.0",
                "pages": {
                    route: {"targets": {
                        key: {"synced_source_sha256": f"old-{key}-{route}", "target_sha256": f"target-{key}-{route}"}
                        for key in ("fr", "de", "es")
                    }}
                    for route in ("/", "/about/")
                },
            }
            (root / "i18n" / "sync-state.json").write_text(json.dumps(original), encoding="utf-8")
            provenance = root / "review.json"
            provenance.write_text(json.dumps({
                "language_pair": "en-US -> fr-FR",
                "review_status": "ai-reviewed",
                "native_or_human_approval": False,
                "routes": [{
                    "route": "/", "locale": "fr", "target_path": "fr/index.html",
                    "source_sha256": hashlib.sha256((root / "index.html").read_bytes()).hexdigest(),
                    "target_sha256": hashlib.sha256((root / "fr" / "index.html").read_bytes()).hexdigest(),
                    "disposition": "no-semantic-delta-ai-reviewed",
                }],
            }), encoding="utf-8")
            with patch.object(MODULE, "ROOT", root):
                bad_hash = json.loads(provenance.read_text(encoding="utf-8"))
                bad_hash["routes"][0]["target_sha256"] = "wrong-target-hash"
                provenance.write_text(json.dumps(bad_hash), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.adopt(["fr"], ["/"], provenance, config)
                bad_source = json.loads(provenance.read_text(encoding="utf-8"))
                bad_source["routes"][0]["source_sha256"] = "wrong-source-hash"
                bad_source["routes"][0]["target_sha256"] = hashlib.sha256((root / "fr" / "index.html").read_bytes()).hexdigest()
                provenance.write_text(json.dumps(bad_source), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.adopt(["fr"], ["/"], provenance, config)
                bad_locale = json.loads(provenance.read_text(encoding="utf-8"))
                bad_locale["routes"][0]["target_sha256"] = hashlib.sha256((root / "fr" / "index.html").read_bytes()).hexdigest()
                bad_locale["routes"][0]["locale"] = "de"
                provenance.write_text(json.dumps(bad_locale), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.adopt(["fr"], ["/"], provenance, config)
                provenance.write_text(json.dumps({
                    "language_pair": "en-US -> fr-FR",
                    "review_status": "ai-reviewed",
                    "native_or_human_approval": False,
                    "routes": [{
                        "route": "/", "locale": "fr", "target_path": "fr/index.html",
                        "source_sha256": hashlib.sha256((root / "index.html").read_bytes()).hexdigest(),
                        "target_sha256": hashlib.sha256((root / "fr" / "index.html").read_bytes()).hexdigest(),
                        "disposition": "no-semantic-delta-ai-reviewed",
                    }],
                }), encoding="utf-8")
                self.assertEqual(0, MODULE.adopt(["fr"], ["/"], provenance, config))
            updated = json.loads((root / "i18n" / "sync-state.json").read_text(encoding="utf-8"))
            self.assertEqual(original["pages"]["/"]["targets"]["de"], updated["pages"]["/"]["targets"]["de"])
            self.assertEqual(original["pages"]["/"]["targets"]["es"], updated["pages"]["/"]["targets"]["es"])
            self.assertNotEqual(original["pages"]["/"]["targets"]["fr"], updated["pages"]["/"]["targets"]["fr"])
            for locale in ("fr", "de", "es"):
                self.assertEqual(
                    original["pages"]["/about/"]["targets"][locale],
                    updated["pages"]["/about/"]["targets"][locale],
                )


class ReviewedTargetIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            "schema_version": "1.0",
            "blocking_locales": ["fr"],
            "in_scope_routes": ["/", "/about/"],
            "target_locales": {
                locale: {"locale": pair, "root": locale, "skill": "pair"}
                for locale, pair in (("fr", "fr-FR"), ("de", "de-DE"))
            },
        }
        for route in ("index.html", "about/index.html"):
            for prefix in ("", "fr/", "de/"):
                path = self.root / (prefix + route)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    '<meta http-equiv="Content-Security-Policy" content="one">'
                    '<link href="/assets/css/theme.css?v=11111111">'
                    '<p>a b ?v=11111111</p>\n',
                    encoding="utf-8",
                )
        (self.root / "assets/data").mkdir(parents=True)
        (self.root / "assets/data/search-index.json").write_text(
            json.dumps({"entries": [{"url": "/"}, {"url": "/about/"}]}),
            encoding="utf-8",
        )
        (self.root / "i18n").mkdir()
        (self.root / "i18n" / "sync.config.json").write_text(json.dumps(self.config), encoding="utf-8")
        self.state = self.root / "i18n" / "sync-state.json"
        ledger = {"schema_version": "1.0", "pages": {}}
        DETECTOR_MODULE.adopt(self.root, self.config, ledger, None)
        self.state.write_text(json.dumps(ledger), encoding="utf-8")
        self.original = self.state.read_bytes()
        self.target = self.root / "fr" / "index.html"
        self.provenance = self.root / "review.json"
        self.patch = patch.object(MODULE, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def review(self):
        return {
            "language_pair": "en-US -> fr-FR",
            "review_status": "ai-reviewed",
            "native_or_human_approval": False,
            "routes": [
                {
                    "route": "/",
                    "locale": "fr",
                    "target_path": "fr/index.html",
                    "source_sha256": DETECTOR_MODULE.sha256_file(self.root / "index.html"),
                    "target_sha256": DETECTOR_MODULE.sha256_file(self.target),
                    "disposition": "retained-ai-reviewed",
                }
            ],
        }

    def test_advisory_adoption_reports_source_gaps_without_changing_noindex_target(self):
        self.config["advisory_content_coverage_locales"] = ["de"]
        source = self.root / "index.html"
        target = self.root / "de" / "index.html"
        source_html = (
            '<meta name="robots" content="noindex, follow"><main>'
            '<h2 id="intro">Introduction</h2><p>Lead.</p>'
            '<h2 id="evidence">Evidence</h2><p>New source content.</p>'
            '<a href="https://example.test/protected">Protected</a></main>'
        )
        target_html = (
            '<meta name="robots" content="noindex, follow"><main>'
            '<h2 id="intro">Einleitung</h2><p>Einleitung.</p></main>'
        )
        source.write_text(source_html, encoding="utf-8")
        target.write_text(target_html, encoding="utf-8")
        self.provenance.write_text(json.dumps({
            "language_pair": "en-US -> de-DE",
            "review_status": "ai-reviewed",
            "native_or_human_approval": False,
            "routes": [{
                "route": "/",
                "locale": "de",
                "target_path": "de/index.html",
                "source_sha256": DETECTOR_MODULE.sha256_file(source),
                "target_sha256": DETECTOR_MODULE.sha256_file(target),
                "disposition": "retained-ai-reviewed",
            }],
        }), encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                0,
                MODULE.adopt(["de"], ["/"], self.provenance, self.config),
            )
        result = json.loads(output.getvalue())
        self.assertTrue(any(
            gap["locale"] == "de"
            and gap["route"] == "/"
            and any(item["kind"] == "heading" for item in gap["omissions"])
            and any(item["kind"] == "protected_link" for item in gap["omissions"])
            for gap in result["source_coverage_gaps"]
        ))
        self.assertEqual(target_html, target.read_text(encoding="utf-8"))
        self.assertIn('content="noindex, follow"', target.read_text(encoding="utf-8"))

    def test_target_only_change_blocks_without_changing_source_freshness(self):
        self.target.write_text("<p>changed translation</p>", encoding="utf-8")
        result = MODULE.load_results(self.config)
        self.assertEqual(4, len(result["in_sync"]))
        self.assertEqual(1, len(result["target_changed"]))
        self.assertEqual("target_changed", result["policy"]["blocking_items"][0]["status"])
        self.assertEqual(1, MODULE.main(["--mode", "check"]))
        self.assertEqual(self.original, self.state.read_bytes())

    def test_unchanged_and_crlf_targets_pass(self):
        original = self.target.read_bytes()
        lf_target = original.replace(b"\r\n", b"\n")
        self.assertIn(b"\n", lf_target)
        self.assertNotIn(b"\r", lf_target)
        crlf_target = lf_target.replace(b"\n", b"\r\n")
        expected_target_hash = json.loads(self.original)["pages"]["/"]["targets"]["fr"]["target_sha256"]

        for line_ending, target_bytes in (("LF", lf_target), ("CRLF", crlf_target)):
            with self.subTest(line_ending=line_ending):
                if line_ending == "LF":
                    self.assertNotIn(b"\r", target_bytes)
                else:
                    self.assertIn(b"\r\n", target_bytes)
                    self.assertNotIn(b"\r\r\n", target_bytes)
                    self.assertEqual(target_bytes.count(b"\r\n"), target_bytes.count(b"\n"))
                    self.assertEqual(target_bytes.count(b"\r"), target_bytes.count(b"\r\n"))

                self.target.write_bytes(target_bytes)
                self.assertEqual(expected_target_hash, DETECTOR_MODULE.sha256_file(self.target))
                result = MODULE.load_results(self.config)
                self.assertEqual([], result["target_changed"])
                self.assertEqual([], result["policy"]["blocking_items"])
                self.assertEqual(0, MODULE.main(["--mode", "check"]))

    def test_draft_target_change_is_advisory(self):
        (self.root / "de" / "index.html").write_text("changed", encoding="utf-8")
        result = MODULE.load_results(self.config)
        self.assertEqual([], result["policy"]["blocking_items"])
        self.assertEqual("target_changed", result["policy"]["advisory_items"][0]["status"])

    def test_missing_target_hash_requires_review(self):
        ledger = json.loads(self.original)
        del ledger["pages"]["/"]["targets"]["fr"]["target_sha256"]
        self.state.write_text(json.dumps(ledger), encoding="utf-8")
        self.assertEqual("target_changed", MODULE.load_results(self.config)["policy"]["blocking_items"][0]["status"])

    def test_generated_metadata_and_semantic_edits_require_review(self):
        original = self.target.read_text(encoding="utf-8")
        for before, after in (
            ('content="one"', 'content="two"'),
            ("theme.css?v=11111111", "theme.css?v=22222222"),
            ("a b", "ab"),
            ("<p>", '<p title="new">'),
            ("?v=11111111", "?v=22222222"),
        ):
            with self.subTest(edit=after):
                self.target.write_text(original.replace(before, after), encoding="utf-8")
                self.assertEqual(1, len(MODULE.load_results(self.config)["target_changed"]))

    def test_reviewed_target_only_adoption_updates_only_selected_pair(self):
        self.target.write_text("<p>reviewed update</p>\r\n", encoding="utf-8", newline="")
        self.provenance.write_text(json.dumps(self.review()), encoding="utf-8")
        evidence = self.provenance.read_bytes()
        self.assertEqual(0, MODULE.adopt(["fr"], ["/"], self.provenance, self.config))
        updated = json.loads(self.state.read_text(encoding="utf-8"))
        expected = json.loads(self.original)
        expected["pages"]["/"]["targets"]["fr"]["target_sha256"] = DETECTOR_MODULE.sha256_file(self.target)
        self.assertEqual(expected, updated)
        self.assertEqual([], MODULE.load_results(self.config)["policy"]["blocking_items"])
        self.assertEqual(evidence, self.provenance.read_bytes())

    def test_invalid_review_never_writes_ledger(self):
        self.target.write_text("<p>changed</p>", encoding="utf-8")
        cases = [
            ("route", "/wrong/"),
            ("locale", "de"),
            ("target_path", "de/index.html"),
            ("source_sha256", "wrong"),
            ("target_sha256", "wrong"),
            ("disposition", "rejected"),
            ("review_status", "rejected"),
            ("language_pair", "en-US -> de-DE"),
            ("native_or_human_approval", True),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                record = self.review()
                target = record if field in record else record["routes"][0]
                target[field] = value
                self.provenance.write_text(json.dumps(record), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.adopt(["fr"], ["/"], self.provenance, self.config)
                self.assertEqual(self.original, self.state.read_bytes())

    def test_source_and_target_drift_are_reported_independently(self):
        (self.root / "index.html").write_text("new source", encoding="utf-8")
        self.target.write_text("new target", encoding="utf-8")
        result = MODULE.load_results(self.config)
        statuses = {item["status"] for item in result["policy"]["blocking_items"]}
        self.assertEqual({"stale", "target_changed"}, statuses)

    def test_duplicate_review_routes_are_rejected(self):
        record = self.review()
        record["routes"].append(dict(record["routes"][0]))
        self.provenance.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(ValueError):
            MODULE.adopt(["fr"], ["/"], self.provenance, self.config)
        self.assertEqual(self.original, self.state.read_bytes())

    def test_valid_review_for_unavailable_pair_is_rejected(self):
        self.provenance.write_text(json.dumps(self.review()), encoding="utf-8")
        for unavailable in ("scope", "target", "source"):
            with self.subTest(unavailable=unavailable):
                config = dict(self.config)
                if unavailable == "scope":
                    config["in_scope_routes"] = ["/about/"]
                else:
                    path = self.target if unavailable == "target" else self.root / "index.html"
                    path.unlink()
                with self.assertRaises(ValueError):
                    MODULE.adopt(["fr"], ["/"], self.provenance, config)
                self.assertEqual(self.original, self.state.read_bytes())

    def test_out_of_scope_and_missing_routes_fail_without_writes(self):
        self.provenance.write_text(json.dumps(self.review()), encoding="utf-8")
        for routes in (["/absent/"], ["/", "/about/"]):
            with self.subTest(routes=routes):
                with self.assertRaises(ValueError):
                    MODULE.adopt(["fr"], routes, self.provenance, self.config)
                self.assertEqual(self.original, self.state.read_bytes())


if __name__ == "__main__":
    unittest.main()

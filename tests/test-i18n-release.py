import importlib.util
import hashlib
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

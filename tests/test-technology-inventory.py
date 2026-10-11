"""Regression tests for release selection and trustworthy version evidence."""
import gzip
import importlib.util
import io
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("technology_inventory", ROOT / "scripts/technology-inventory.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ReleaseTests(unittest.TestCase):
    def test_supported_runtime_range_accepts_replit_and_preferred_pins(self):
        self.assertTrue(AUDIT.runtime_constraint_allows("24.13.0", ">=24.13.0 <25"))
        self.assertTrue(AUDIT.runtime_constraint_allows("24.21.0", ">=24.13.0 <25"))
        self.assertTrue(AUDIT.runtime_constraint_allows("24.21.0", "24.21.0"))
        for unsupported in ("22.19.0", "24.12.0", "25.0.0", "24.21.0rc1"):
            self.assertFalse(AUDIT.runtime_constraint_allows(unsupported, ">=24.13.0 <25"))
        self.assertFalse(AUDIT.runtime_constraint_allows("24.21.0", "*"))

    def test_numeric_sort_and_prerelease_exclusion(self):
        self.assertEqual(AUDIT.stable_max(["1.9.0", "1.10.0", "2.0.0rc1", "2.0.0-beta.2", "v1.10.1"]), "1.10.1")
        self.assertIsNone(AUDIT.version("3.15.0rc2"))

    def test_selectors_do_not_claim_exact_patch_installed(self):
        self.assertEqual(AUDIT.compare("24", "24.21.0"), "TRACKING")
        self.assertEqual(AUDIT.compare("3.11", "3.11.16"), "TRACKING")
        self.assertEqual(AUDIT.compare("3.11", "3.14.7"), "UPDATE")
        self.assertEqual(AUDIT.compare("unrecorded", "9.0.2"), "UNKNOWN")
        self.assertEqual(AUDIT.compare("1.11.0", "1.9.0"), "AHEAD")
        self.assertEqual(AUDIT.compare("1.9.0", "1.9.0"), "CURRENT")

    def test_pypi_ignores_yanked_empty_and_prerelease(self):
        payload = {"info": {"requires_python": ">=3.11"}, "releases": {
            "4.0.0rc1": [{"yanked": False}], "3.0.0": [{"yanked": True}],
            "2.9.0": [], "2.1.0": [{"yanked": False}], "1.9.0": [{"yanked": False}]}}
        with patch.object(AUDIT, "fetch", return_value=payload):
            found = AUDIT.resolve(AUDIT.row("test", "Python QA", "1.9.0", [], "pypi"))
        self.assertEqual(found["latest"], "2.1.0")

    def test_npm_prerelease_tag_uses_stable_release_and_its_metadata(self):
        metadata = {"versions": {
            "1.9.0": {"version": "1.9.0"},
            "1.10.0": {"version": "1.10.0", "engines": {"node": ">=20"}},
            "2.0.0-beta.1": {"version": "2.0.0-beta.1", "engines": {"node": ">=26"}}}}
        with patch.object(AUDIT, "fetch", side_effect=[{"version": "2.0.0-beta.1"}, metadata]) as fetch:
            found = AUDIT.resolve(AUDIT.row("test", "npm direct", "1.10.0", [], "npm"), deadline=123)
        self.assertEqual(found["latest"], "1.10.0")
        self.assertEqual(found["status"], "CURRENT")
        self.assertEqual(found["latest_tag"], "2.0.0-beta.1")
        self.assertEqual(found["requires"], {"node": ">=20"})
        self.assertEqual(found["source"], "https://registry.npmjs.org/test")
        self.assertEqual(found["additional_sources"], ["https://registry.npmjs.org/test/latest"])
        self.assertEqual([call.kwargs for call in fetch.call_args_list], [{"deadline": 123}] * 2)

    def test_stable_npm_tag_needs_no_fallback(self):
        with patch.object(AUDIT, "fetch", return_value={"version": "1.10.0", "engines": {"node": ">=20"}}) as fetch:
            found = AUDIT.resolve(AUDIT.row("test", "npm direct", "1.10.0", [], "npm"))
        self.assertEqual(found["status"], "CURRENT")
        self.assertEqual(found["requires"], {"node": ">=20"})
        self.assertNotIn("latest_tag", found)
        fetch.assert_called_once()

    def test_npm_fallback_errors_remain_unknown(self):
        item = AUDIT.row("test", "npm transitive", "1.0.0", [], "npm", owner="parent dependency")
        for response in ({"versions": {"2.0.0-beta.1": {"version": "2.0.0-beta.1"}}},
                         {"versions": {"1.0.0": {"version": "2.0.0-beta.1"}}},
                         {"versions": []}, {}, urllib.error.URLError("offline")):
            with self.subTest(response=response), patch.object(
                    AUDIT, "fetch", side_effect=[{"version": "2.0.0-beta.1"}, response]):
                found = AUDIT.enrich([item])[0]
            self.assertEqual(found["status"], "UNKNOWN")
            self.assertIsNone(found["latest"])
            self.assertIn("error", found)

    def test_invalid_npm_tag_is_not_interpreted_as_a_prerelease(self):
        with patch.object(AUDIT, "fetch", return_value={"version": "invalid"}) as fetch:
            with self.assertRaisesRegex(ValueError, "invalid version"):
                AUDIT.resolve(AUDIT.row("test", "npm direct", "1.0.0", [], "npm"))
        fetch.assert_called_once()

    def test_python_does_not_truncate_release_candidate(self):
        html = '<a>Python 3.15.0rc2</a><a>Python 3.14.7</a><a>Python 3.11.16</a>'
        with patch.object(AUDIT, "fetch", return_value=html):
            found = AUDIT.resolve(AUDIT.row("Python", "runtime", "3.11", [], "python"))
        self.assertEqual(found["latest"], "3.14.7")
        self.assertEqual(found["latest_in_current_line"], "3.11.16")

    def test_python_trials_track_line_patches_while_primary_tracks_latest_release(self):
        html = '<a>Python 3.15.0</a><a>Python 3.14.8</a><a>Python 3.11.17</a>'
        for pin, target, status in (("3.11", "3.11.17", "TRACKING"),
                                    ("3.14.8", "3.14.8", "CURRENT"),
                                    ("3.14.7", "3.14.8", "UPDATE")):
            item = {**AUDIT.row("Python (compatibility trial)", "runtime", pin, [], "python"),
                    "role": "compatibility trial"}
            with self.subTest(pin=pin), patch.object(AUDIT, "fetch", return_value=html):
                found = AUDIT.resolve(item)
            self.assertEqual(found["latest"], "3.15.0")
            self.assertEqual(found["status"], "UPDATE")
            self.assertEqual(found["target"], target)
            self.assertEqual(found["target_status"], status)
        with patch.object(AUDIT, "fetch", return_value=html):
            primary = AUDIT.resolve({**AUDIT.row("Python", "runtime", "3.11", [], "python"),
                                    "role": "primary CI"})
        self.assertEqual(primary["latest"], "3.15.0")
        self.assertEqual(primary["status"], "UPDATE")
        self.assertNotIn("target_status", primary)

    def test_node_current_and_lts_are_distinct(self):
        releases = [{"version": "v26.9.0", "lts": False, "npm": "12.0.0"},
                    {"version": "v24.21.0", "lts": "Krypton", "npm": "11.19.0"},
                    {"version": "v22.23.2", "lts": "Jod", "npm": "10.9.4"}]
        with patch.object(AUDIT, "fetch", return_value=releases):
            found = AUDIT.resolve(AUDIT.row("Node", "runtime", "24", [], "node"))
        self.assertEqual(found["status"], "UPDATE")
        self.assertEqual(found["target_status"], "TRACKING")
        self.assertEqual(found["target"], "24.21.0")

    def test_action_sha_resolves_to_specific_version(self):
        responses = [{"tag_name": "v7.0.1", "html_url": "https://github.com/actions/checkout/releases/tag/v7.0.1"},
                     [{"name": "v7", "commit": {"sha": "a" * 40}},
                      {"name": "v7.0.1", "commit": {"sha": "a" * 40}}]]
        with patch.object(AUDIT, "fetch", side_effect=responses):
            found = AUDIT.resolve(AUDIT.row("actions/checkout", "GitHub Actions", "a" * 40, [], "github-action"))
        self.assertEqual(found["resolved_current"], "7.0.1")
        self.assertEqual(found["status"], "CURRENT")

    def test_unresolved_sha_is_unknown_not_current(self):
        with patch.object(AUDIT, "fetch", side_effect=[{"tag_name": "v2.0.0", "html_url": "https://example.com"}, []]):
            found = AUDIT.enrich([AUDIT.row("actions/example", "GitHub Actions", "a" * 40, [], "github-action")])[0]
        self.assertEqual(found["status"], "UNKNOWN")
        self.assertIn("error", found)

    def test_registry_failure_preserves_other_results(self):
        items = [AUDIT.row(n, "npm direct", "1.0.0", [], "npm") for n in ("bad", "good")]
        def resolve(item, deadline=None):
            if item["name"] == "bad":
                raise urllib.error.URLError("registry unavailable")
            return {"latest": "1.0.0", "status": "CURRENT"}
        with patch.object(AUDIT, "resolve", side_effect=resolve):
            results = AUDIT.enrich(items)
        self.assertEqual([r["status"] for r in results], ["UNKNOWN", "CURRENT"])
        self.assertIn("error", results[0])

    def test_gzip_responses_are_decoded(self):
        response = io.BytesIO(gzip.compress(b'{"version":"1.2.3"}'))
        response.headers = {"Content-Encoding": "gzip"}
        with patch.object(AUDIT.urllib.request, "urlopen", return_value=response):
            self.assertEqual(AUDIT.fetch("https://registry.npmjs.org/test"), {"version": "1.2.3"})

    def test_expired_budget_does_not_start_a_request(self):
        with patch.object(AUDIT.time, "monotonic", return_value=50), \
                patch.object(AUDIT.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(TimeoutError, "budget exhausted"):
                AUDIT.fetch("https://registry.npmjs.org/test", deadline=50)
        request.assert_not_called()

    def test_stalled_registry_stops_retries_at_shared_deadline(self):
        clock = [100.0]
        def stall(request, timeout):
            clock[0] += timeout
            raise TimeoutError("registry stopped responding")
        with patch.object(AUDIT.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(AUDIT.time, "sleep"), \
                patch.object(AUDIT.urllib.request, "urlopen", side_effect=stall) as request:
            with self.assertRaisesRegex(TimeoutError, "budget exhausted"):
                AUDIT.fetch("https://registry.npmjs.org/test", deadline=107)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs["timeout"], 7)

    def test_registry_outage_writes_all_rows_and_upstream_failure_evidence(self):
        items = [AUDIT.row(str(i), "npm direct", "1.0.0", [], "npm") for i in range(120)]
        items.append(AUDIT.row("Mermaid", "browser runtime", "11.17.2", [], "npm"))
        clock = [100.0]
        def stall(request, timeout):
            clock[0] += timeout
            raise TimeoutError("registry stopped responding")
        with tempfile.TemporaryDirectory() as directory:
            targets = [Path(directory) / name for name in ("report.json", "report.md", "summary.md")]
            with patch.object(AUDIT, "inventory", return_value=(items, [])), \
                    patch.object(AUDIT.time, "monotonic", side_effect=lambda: clock[0]), \
                    patch.object(AUDIT.time, "sleep"), \
                    patch.object(AUDIT.urllib.request, "urlopen", side_effect=stall):
                code = AUDIT.main(["--lookup-budget-seconds", "7", "--json-output", str(targets[0]),
                                   "--markdown-output", str(targets[1]), "--summary-output", str(targets[2])])
            self.assertEqual(code, 1)
            rows = json.loads(targets[0].read_text())["technologies"]
            self.assertEqual(len(rows), 122)
            self.assertTrue(all(r["status"] == "UNKNOWN" and r.get("error") for r in rows))
            self.assertTrue(any(r["name"] == "Mermaid package metadata" for r in rows))
            self.assertIn("budget exhausted", targets[1].read_text())
            self.assertIn("budget exhausted", targets[2].read_text())

    def test_slow_stream_cannot_extend_the_lookup_budget(self):
        clock = [100.0]
        class SlowResponse(io.BytesIO):
            headers = {}
            chunks = 0
            def read(self, *args):
                raise AssertionError("Unbounded response.read() bypasses deadline checks")
            def read1(self, size):
                clock[0] += 3
                self.chunks += 1
                return b" "  # Never EOF; data arrives before each socket timeout.
        response = SlowResponse()
        with patch.object(AUDIT.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(AUDIT.time, "sleep"), \
                patch.object(AUDIT.urllib.request, "urlopen", return_value=response) as request:
            with self.assertRaisesRegex(TimeoutError, "budget exhausted"):
                AUDIT.fetch("https://registry.npmjs.org/test", deadline=107)
        self.assertEqual(response.chunks, 3)
        self.assertEqual(request.call_count, 1)

    def test_no_stable_release_is_error(self):
        with self.assertRaises(ValueError):
            AUDIT.stable_max(["3.15.0rc2", "nightly"])

    def test_every_lock_location_is_represented(self):
        rows, _ = AUDIT.inventory(ROOT)
        lock = json.loads((ROOT / "package-lock.json").read_text())
        found = {p.removeprefix("package-lock.json:") for r in rows
                 if r["category"].startswith("npm ") for p in r["evidence"]}
        self.assertEqual(found, set(lock["packages"]) - {""})

    def test_compatibility_matrix_inventory_tracks_actual_selectors_separately(self):
        path = ".github/workflows/runtime-compatibility.yml"
        text = (ROOT / path).read_text(encoding="utf-8")
        declared = re.search(r"^\s*python:\s*\[(.*)\]", text, re.MULTILINE)[1]
        expected = {pin.strip().strip("'\"") for pin in declared.split(",")}
        rows, _ = AUDIT.inventory(ROOT)
        trials = [row for row in rows if row.get("role") == "compatibility trial"]
        self.assertEqual({row["current"] for row in trials}, expected)
        self.assertTrue(all(row["name"] == "Python (compatibility trial)" for row in trials))
        self.assertTrue(all(all(source.startswith(path + ":") for source in row["evidence"]) for row in trials))
        self.assertTrue(any(row.get("role") == "primary CI" for row in rows))
        changed = text.replace("python: [" + declared + "]", "python: ['3.99.1']")
        changed_rows = AUDIT.compatibility_python_rows(changed, path)
        self.assertEqual([row["current"] for row in changed_rows], ["3.99.1"])
        for malformed in (text.replace("python: [" + declared + "]", "python: [3.11]"),
                          text.replace("matrix.python", "matrix.other")):
            with self.assertRaises(ValueError):
                AUDIT.compatibility_python_rows(malformed, path)

    def test_media_requirements_and_lighthouse_are_included(self):
        rows, _ = AUDIT.inventory(ROOT)
        self.assertEqual({r["name"] for r in rows if r["category"] == "Python media"},
                         {"numpy"})
        numpy = next(r for r in rows if r["name"] == "numpy")
        self.assertEqual(numpy["current"], "unrecorded")
        self.assertIn("scripts/render-murderbird-first-choice.py", numpy["evidence"])
        ffmpeg = next(r for r in rows if r["name"] == "FFmpeg")
        self.assertIn("scripts/render-murderbird-first-choice.py", ffmpeg["evidence"])
        historical = [row for row in rows if AUDIT.is_historical(row)]
        self.assertEqual({row["name"] for row in historical}, {"numpy", "FFmpeg", "Blender"})
        self.assertTrue(all(row["owner"] == "OKHP3/murderbird-uncaged" for row in historical))
        self.assertTrue(all("docs/murderbird-repository-boundary.md" in row["evidence"] for row in historical))
        self.assertFalse(any(r["name"] == "GarageBand (macOS)" for r in rows))
        self.assertFalse(any("production/audio" in evidence for row in rows for evidence in row["evidence"]))
        self.assertTrue(any(r["name"] == "lighthouse" and r["category"] == "npm direct" for r in rows))

    def test_historical_media_keeps_unknown_installations_without_obsolete_lookups(self):
        rows, _ = AUDIT.inventory(ROOT)
        historical = [row for row in rows if AUDIT.is_historical(row)]
        with patch.object(AUDIT, "resolve", side_effect=AssertionError("Historical tooling looked up")) as resolve:
            results = AUDIT.enrich(historical)
        resolve.assert_not_called()
        self.assertTrue(all(row["status"] == "HISTORICAL" and row["latest"] is None for row in results))
        self.assertEqual(next(row for row in results if row["name"] == "numpy")["current"], "unrecorded")
        self.assertEqual(next(row for row in results if row["name"] == "FFmpeg")["current"], "unrecorded")
        historical_error = {**results[0], "error": "retained external lookup error"}
        with patch.object(AUDIT, "enrich", return_value=[historical_error]):
            self.assertEqual(AUDIT.main([]), 0)
        rendered = AUDIT.markdown({"retrieved_at": "test", "source_commit": "test",
                                   "findings": [], "technologies": [historical_error]})
        self.assertIn("retained external lookup error", rendered)
        self.assertIn("Not checked (external historical tooling)", rendered)
        # Ownership alone must not hide a currently used dependency failure.
        with patch.object(AUDIT, "enrich", return_value=[{**historical_error, "scope": "website"}]):
            self.assertEqual(AUDIT.main([]), 1)

    def test_offline_run_writes_reports_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            with patch.object(AUDIT, "fetch", side_effect=AssertionError("Offline run accessed network")):
                code = AUDIT.main(["--offline", "--json-output", str(target)])
            self.assertEqual(code, 0)
            self.assertTrue(all(r["status"] == ("HISTORICAL" if AUDIT.is_historical(r) else "NOT_CHECKED")
                                for r in json.loads(target.read_text())["technologies"]))

    def test_failed_lookup_causes_nonzero_exit(self):
        with patch.object(AUDIT, "enrich", return_value=[{"status": "UNKNOWN", "error": "offline", "category": "npm", "name": "test", "current": "1", "evidence": [], "owner": "review"}]):
            self.assertEqual(AUDIT.main([]), 1)


if __name__ == "__main__":
    unittest.main()

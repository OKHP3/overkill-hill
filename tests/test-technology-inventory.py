"""Regression tests for release selection and trustworthy version evidence."""
import gzip
import importlib.util
import io
import json
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

    def test_npm_latest_prerelease_is_not_silently_accepted(self):
        with patch.object(AUDIT, "fetch", return_value={"version": "2.0.0-beta.1"}):
            with self.assertRaisesRegex(ValueError, "prerelease"):
                AUDIT.resolve(AUDIT.row("test", "npm direct", "1.0.0", [], "npm"))

    def test_python_does_not_truncate_release_candidate(self):
        html = '<a>Python 3.15.0rc2</a><a>Python 3.14.7</a><a>Python 3.11.16</a>'
        with patch.object(AUDIT, "fetch", return_value=html):
            found = AUDIT.resolve(AUDIT.row("Python", "runtime", "3.11", [], "python"))
        self.assertEqual(found["latest"], "3.14.7")
        self.assertEqual(found["latest_in_current_line"], "3.11.16")

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

    def test_media_requirements_and_lighthouse_are_included(self):
        rows, _ = AUDIT.inventory(ROOT)
        self.assertEqual({r["name"] for r in rows if r["category"] == "Python media"},
                         {"numpy"})
        numpy = next(r for r in rows if r["name"] == "numpy")
        self.assertEqual(numpy["current"], "unrecorded")
        self.assertEqual(numpy["evidence"], ["scripts/render-murderbird-first-choice.py"])
        ffmpeg = next(r for r in rows if r["name"] == "FFmpeg")
        self.assertEqual(ffmpeg["evidence"], ["scripts/render-murderbird-first-choice.py"])
        self.assertFalse(any(r["name"] == "GarageBand (macOS)" for r in rows))
        self.assertFalse(any("production/audio" in evidence for row in rows for evidence in row["evidence"]))
        self.assertTrue(any(r["name"] == "lighthouse" and r["category"] == "npm direct" for r in rows))

    def test_offline_run_writes_reports_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            with patch.object(AUDIT, "fetch", side_effect=AssertionError("Offline run accessed network")):
                code = AUDIT.main(["--offline", "--json-output", str(target)])
            self.assertEqual(code, 0)
            self.assertTrue(all(r["status"] == "NOT_CHECKED" for r in json.loads(target.read_text())["technologies"]))

    def test_failed_lookup_causes_nonzero_exit(self):
        with patch.object(AUDIT, "enrich", return_value=[{"status": "UNKNOWN", "error": "offline", "category": "npm", "name": "test", "current": "1", "evidence": [], "owner": "review"}]):
            self.assertEqual(AUDIT.main([]), 1)


if __name__ == "__main__":
    unittest.main()

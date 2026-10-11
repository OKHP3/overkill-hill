#!/usr/bin/env python3
"""Regression tests for read-only search-index freshness checks."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "scripts" / "build-search-index.py"
SPEC = importlib.util.spec_from_file_location("build_search_index", BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load scripts/build-search-index.py")
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class SearchIndexCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.index_path = self.root / "assets" / "data" / "search-index.json"
        self.index_path.parent.mkdir(parents=True)
        self.report_path = self.root / "freshness-report.json"
        self.payload = {
            "site": "https://example.test",
            "generated": "static",
            "count": 1,
            "entries": [{"url": "/about/", "title": "About", "category": "Brand"}],
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_check(self, *, unreadable: bool = False):
        stdout = io.StringIO()
        stderr = io.StringIO()
        args = ["--check", "--report", str(self.report_path)]
        with (
            patch.object(builder, "ROOT", self.root),
            patch.object(builder, "build_payload", return_value=self.payload),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            if unreadable:
                original_read_text = Path.read_text

                def fail_index_read(path, *args, **kwargs):
                    if path == self.index_path:
                        raise PermissionError("permission denied")
                    return original_read_text(path, *args, **kwargs)

                with patch.object(Path, "read_text", fail_index_read):
                    result = builder.main(args)
            else:
                result = builder.main(args)
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        return result, stdout.getvalue(), stderr.getvalue(), report

    def test_malformed_json_reports_input_problem_without_routes_or_rewrite(self) -> None:
        original = b'{"entries": [broken'
        self.index_path.write_bytes(original)

        result, _, stderr, report = self.run_check()

        self.assertEqual(result, 1)
        self.assertIn("Search index is malformed", stderr)
        self.assertIn("invalid JSON", stderr)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["inputProblem"]["kind"], "invalid_json")
        self.assertEqual(report["affectedRoutes"], [])
        self.assertEqual(self.index_path.read_bytes(), original)

    def test_missing_index_reports_missing_input_without_routes(self) -> None:
        result, _, stderr, report = self.run_check()

        self.assertEqual(result, 1)
        self.assertIn("Search index is missing", stderr)
        self.assertEqual(report["inputProblem"]["kind"], "missing")
        self.assertEqual(report["affectedRoutes"], [])
        self.assertFalse(self.index_path.exists())

    def test_unreadable_index_reports_read_error_without_routes_or_rewrite(self) -> None:
        original = b"committed bytes"
        self.index_path.write_bytes(original)

        result, _, stderr, report = self.run_check(unreadable=True)

        self.assertEqual(result, 1)
        self.assertIn("Search index is unreadable", stderr)
        self.assertEqual(report["inputProblem"]["kind"], "unreadable")
        self.assertEqual(report["affectedRoutes"], [])
        self.assertEqual(self.index_path.read_bytes(), original)

    def test_valid_stale_report_identifies_the_changed_route(self) -> None:
        committed = copy.deepcopy(self.payload)
        committed["entries"][0]["title"] = "Old title"
        original = json.dumps(committed, ensure_ascii=False, indent=2).encode("utf-8")
        self.index_path.write_bytes(original)

        result, _, stderr, report = self.run_check()

        self.assertEqual(result, 1)
        self.assertIn("Search index is stale", stderr)
        self.assertIsNone(report["inputProblem"])
        self.assertEqual(report["affectedRoutes"], ["/about/"])
        self.assertEqual(self.index_path.read_bytes(), original)

    def test_current_report_has_no_input_problem_or_affected_routes(self) -> None:
        original = json.dumps(
            self.payload, ensure_ascii=False, indent=2
        ).encode("utf-8")
        self.index_path.write_bytes(original)

        result, stdout, _, report = self.run_check()

        self.assertEqual(result, 0)
        self.assertIn("Search index is current", stdout)
        self.assertEqual(report["status"], "current")
        self.assertIsNone(report["inputProblem"])
        self.assertEqual(report["affectedRoutes"], [])
        self.assertEqual(self.index_path.read_bytes(), original)

    def test_duplicate_route_cannot_hide_a_stale_entry(self) -> None:
        committed = copy.deepcopy(self.payload)
        stale = copy.deepcopy(committed["entries"][0])
        stale["title"] = "Old title"
        committed["entries"].insert(0, stale)
        original = json.dumps(committed, ensure_ascii=False, indent=2).encode("utf-8")
        self.index_path.write_bytes(original)

        result, _, stderr, report = self.run_check()

        self.assertEqual(result, 1)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["inputProblem"]["kind"], "invalid_structure")
        self.assertIn("duplicate", stderr)
        self.assertIn("/about/", stderr)
        self.assertEqual(self.index_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)

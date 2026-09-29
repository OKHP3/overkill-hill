#!/usr/bin/env python3
"""Regression coverage for CSP public-page discovery."""

from __future__ import annotations

import importlib.util
import unittest
import json
import io
import tempfile
import sys
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CSP_PATH = ROOT / "scripts" / "csp.py"

spec = importlib.util.spec_from_file_location("csp", CSP_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load scripts/csp.py")
csp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(csp)


class CspPageDiscoveryTests(unittest.TestCase):
    def assert_manifest_route_error(self, page: dict, expected: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            manifest = root / "site-src" / "pages.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"pages": [page]}), encoding="utf-8")
            with patch.object(csp, "ROOT", root), patch.object(
                csp.subprocess, "run", return_value=SimpleNamespace(stdout="index.html\n")
            ):
                with self.assertRaisesRegex(csp.CspPageManifestError, expected):
                    csp.all_pages()

    def test_declared_untracked_route_participates_before_git_add(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "site-src").mkdir()
            (root / "tests" / "fixtures").mkdir(parents=True)
            (root / "i18n" / "pilot" / "es-mx" / "reviewed").mkdir(parents=True)
            (root / "new-story.html").write_text("<main>Story</main>", encoding="utf-8")
            (root / "tests" / "fixtures" / "declared.html").write_text(
                "<main>Fixture</main>", encoding="utf-8"
            )
            (root / "i18n" / "pilot" / "es-mx" / "reviewed" / "declared.html").write_text(
                "<main>Translation evidence</main>", encoding="utf-8"
            )
            (root / "site-src" / "pages.json").write_text(
                json.dumps(
                    {
                        "pages": [
                            {"path": "new-story.html"},
                            {"path": "tests/fixtures/declared.html"},
                            {"path": "i18n/pilot/es-mx/reviewed/declared.html"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(csp, "ROOT", root), patch.object(
                csp.subprocess, "run", return_value=SimpleNamespace(stdout="index.html\n")
            ):
                pages = {p.relative_to(root).as_posix() for p in csp.all_pages()}
            self.assertEqual(pages, {"index.html", "new-story.html"})

    def test_invalid_manifest_route_fails_with_actionable_error(self) -> None:
        self.assert_manifest_route_error(
            {}, r'pages\.json: page entry 1 must contain a non-empty string "path"'
        )
        self.assert_manifest_route_error(
            {"path": "new-story.txt"},
            r'new-story\.txt.*normalized repository-relative \.html path',
        )

    def test_missing_manifest_route_fails_with_actionable_error(self) -> None:
        self.assert_manifest_route_error(
            {"path": "new-story.html"},
            r"new-story\.html.*does not exist as a regular HTML file; generate the page",
        )

    def test_outside_root_manifest_route_fails_with_actionable_error(self) -> None:
        self.assert_manifest_route_error(
            {"path": "../outside.html"},
            r"outside\.html.*outside or could escape the repository root",
        )

    def test_generate_csp_prints_manifest_errors_without_a_traceback(self) -> None:
        generator_path = ROOT / "scripts" / "generate-csp.py"
        generator_spec = importlib.util.spec_from_file_location(
            "test_generate_csp", generator_path
        )
        if generator_spec is None or generator_spec.loader is None:
            self.fail("could not load scripts/generate-csp.py")
        generator = importlib.util.module_from_spec(generator_spec)
        generator_spec.loader.exec_module(generator)
        message = "site-src/pages.json: page entry 1 path 'new-story.html' is missing"
        with patch.object(
            generator,
            "all_pages",
            side_effect=generator.CspPageManifestError(message),
        ), patch.object(generator, "build_policies") as build_policies:
            output = io.StringIO()
            with redirect_stderr(output):
                result = generator.main(["--check"])
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue().strip(), f"CSP page manifest error: {message}")
        build_policies.assert_not_called()

    def test_test_fixtures_are_not_public_csp_pages(self) -> None:
        pages = {page.relative_to(ROOT).as_posix() for page in csp.all_pages()}

        self.assertIn("index.html", pages)
        self.assertFalse(any(page.startswith("tests/fixtures/") for page in pages))
        self.assertFalse(any(page.startswith("i18n/") for page in pages))

    def test_translation_evidence_is_not_a_live_asset_consumer(self) -> None:
        # Saved reviews retain their original hashes; actual locale routes must
        # still participate in every live-page and asset-fingerprint check.
        modules = []
        original_path = sys.path[:]
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            for filename in ("validate-site.py", "cache-bust.py"):
                module_spec = importlib.util.spec_from_file_location(filename[:-3], ROOT / "scripts" / filename)
                if module_spec is None or module_spec.loader is None:
                    raise RuntimeError(f"could not load scripts/{filename}")
                module = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(module)
                modules.append(module)
        finally:
            sys.path[:] = original_path
        validator, cache = modules
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            names = {"index.html", "es-mx/index.html", "fr/about/index.html",
                     "i18n/pilot/es-mx/reviewed/index.html"}
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("<main>Example</main>", encoding="utf-8")
            expected = names - {"i18n/pilot/es-mx/reviewed/index.html"}
            with patch.object(csp, "ROOT", root), patch.object(
                csp.subprocess, "run", return_value=SimpleNamespace(stdout="\n".join(names))
            ), patch.object(validator, "ROOT", root):
                self.assertEqual({p.relative_to(root).as_posix() for p in csp.all_pages()}, expected)
                self.assertEqual({p.relative_to(root).as_posix() for p in validator.find_html_files()}, expected)
                self.assertEqual({p.relative_to(root).as_posix() for p in cache.iter_html_files(root)}, expected)


class CspMurderbirdMediaTests(unittest.TestCase):
    def test_song_allowance_is_limited_to_murderbird_routes(self) -> None:
        self.assertEqual(csp.page_class(ROOT / "writings/murderbird/index.html"), "murderbird")
        self.assertEqual(csp.page_class(ROOT / "projects/murderbird-uncaged/index.html"), "murderbird")
        self.assertEqual(csp.page_class(ROOT / "writings/index.html"), "standard")
        self.assertEqual(csp.page_class(ROOT / "fr/index.html"), "standard")

    def test_only_murderbird_policy_allows_the_exact_published_song(self) -> None:
        policies = csp.build_policies()
        for kind, policy in policies.items():
            directives = dict(part.strip().split(" ", 1) for part in policy.split(";") if " " in part.strip())
            if kind == "murderbird":
                self.assertEqual(directives["media-src"], "'self' " + csp.MURDERBIRD_THEME_AUDIO)
                self.assertNotIn("'unsafe-inline'", directives["style-src"])
                self.assertNotIn("'unsafe-inline'", directives["script-src"])
            else:
                self.assertNotIn("media-src", directives)
                self.assertEqual(directives["default-src"], "'self'")

    def test_header_allows_the_song_without_allowing_the_whole_host(self) -> None:
        directives = dict(part.strip().split(" ", 1) for part in csp.build_edge_policy().split(";") if " " in part.strip())
        self.assertEqual(directives["media-src"], "'self' " + csp.MURDERBIRD_THEME_AUDIO)


if __name__ == "__main__":
    unittest.main(verbosity=2)

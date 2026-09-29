#!/usr/bin/env python3
"""Contract tests for the shared production-page discovery boundary."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    module_name = f"boundary_test_{name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


class PublicPageBoundaryTests(unittest.TestCase):
    def test_html_inventories_share_boundary_and_keep_narrow_exceptions(self) -> None:
        csp = load_script("csp")
        validator = load_script("validate-site")
        auditor = load_script("audit-site")
        search = load_script("build-search-index")
        links = load_script("check-links")
        cache = load_script("cache-bust")
        banner = load_script("check-banner")
        voice = load_script("lint-voice")
        font_migration = load_script("strip-google-fonts-links")
        site_builder = load_script("build-site")
        release_builder = load_script("build-release")

        with tempfile.TemporaryDirectory(prefix="public-page-boundary-") as directory:
            root = Path(directory).resolve()
            public_pages = {
                "index.html",
                "projects/generated/index.html",
                "fr/about/index.html",
                "en-gb/locale/index.html",
                "es-mx/locale/index.html",
            }
            authoring_inputs = {
                "assets/templates/template.html",
                "assets/partials/header.html",
                "site-src/pages/writings/generated.main.html",
            }
            excluded_pages = {
                "tests/fixtures/fixture.html",
                "i18n/pilot/es-mx/reviewed/translation.html",
                "site-src/evidence/review.html",
                ".local/browser-fixtures/fixture.html",
                ".agents/inbox/capture.html",
                "attached_assets/upload.html",
            }
            tracked_pages = public_pages | authoring_inputs | excluded_pages
            for relative_path in tracked_pages:
                page = root / relative_path
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text("<html><body>fixture content</body></html>", encoding="utf-8")

            # The release and CSP inventories also consume the declared routes.
            (root / "site-src").mkdir(parents=True, exist_ok=True)
            (root / "site-src" / "pages.json").write_text(
                json.dumps(
                    {
                        "pages": [
                            {"path": "index.html"},
                            {"path": "projects/generated/index.html"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (root / "sitemap.xml").write_text(
                "<urlset>"
                "<url><loc>https://example.test/</loc></url>"
                "<url><loc>https://example.test/projects/generated/</loc></url>"
                "</urlset>",
                encoding="utf-8",
            )

            def relative_inventory(paths) -> set[str]:
                result = set()
                for path in paths:
                    path = Path(path)
                    result.add(
                        path.relative_to(root).as_posix()
                        if path.is_absolute()
                        else path.as_posix()
                    )
                return result

            tracked_output = "\n".join(sorted(tracked_pages))
            with (
                patch.object(csp, "ROOT", root),
                patch.object(validator, "ROOT", root),
                patch.object(auditor, "ROOT", root),
                patch.object(search, "ROOT", root),
                patch.object(site_builder, "ROOT", root),
                patch.object(
                    csp.subprocess,
                    "run",
                    return_value=SimpleNamespace(stdout=tracked_output),
                ),
            ):
                inventories = {
                    "CSP": relative_inventory(csp.all_pages()),
                    "site validator": relative_inventory(validator.find_html_files()),
                    "site auditor": relative_inventory(auditor.iter_html_files()),
                    "search index": relative_inventory(search.iter_html_files(root)),
                    "link checker": relative_inventory(links.iter_html_files(root)),
                    "cache buster": relative_inventory(cache.iter_html_files(root)),
                    "banner checker": relative_inventory(banner.find_html_files(str(root))),
                    "voice lint": relative_inventory(voice.find_html_files(root)),
                    "site bootstrap": relative_inventory(site_builder.tracked_pages()),
                    "release builder": relative_inventory(release_builder.load_public_pages(root)),
                }
            with patch.object(
                font_migration.subprocess,
                "run",
                return_value=SimpleNamespace(stdout="\0".join(sorted(tracked_pages))),
            ):
                inventories["font migration"] = relative_inventory(
                    font_migration.find_html_files(root)
                )

            # Every scanner still sees the same representative generated public
            # routes. Voice lint intentionally applies a separate locale profile.
            for scanner, inventory in inventories.items():
                expected = public_pages - (
                    {"en-gb/locale/index.html", "es-mx/locale/index.html"}
                    if scanner == "voice lint"
                    else set()
                )
                with self.subTest(scanner=scanner):
                    self.assertTrue(expected <= inventory, f"missing public routes: {expected - inventory}")
                    self.assertTrue(
                        inventory.isdisjoint(excluded_pages),
                        f"non-public evidence entered inventory: {inventory & excluded_pages}",
                    )

            self.assertEqual(
                inventories["cache buster"] - public_pages,
                authoring_inputs,
                "cache-bust may include only its documented maintained source inputs",
            )
            self.assertEqual(
                inventories["font migration"] - public_pages,
                authoring_inputs,
                "font migration may include only its documented maintained source inputs",
            )
            self.assertEqual(
                inventories["banner checker"] - public_pages,
                {"assets/partials/header.html"},
                "banner checking may add only its source partial",
            )
            self.assertEqual(
                inventories["voice lint"],
                public_pages - {"en-gb/locale/index.html", "es-mx/locale/index.html"},
                "voice lint retains only its explicit locale-profile exception",
            )
            self.assertEqual(
                inventories["site bootstrap"],
                public_pages,
                "site bootstrap retains its tracked editorial-page scope",
            )
            self.assertEqual(
                inventories["release builder"],
                public_pages,
                "release routes remain allowlisted while using shared page eligibility",
            )

    def test_release_manifest_cannot_promote_excluded_evidence(self) -> None:
        release_builder = load_script("build-release")
        excluded_routes = (
            "tests/fixtures/declared.html",
            "site-src/evidence/source.html",
            "i18n/pilot/es-mx/reviewed/translation.html",
        )
        for route in excluded_routes:
            with self.subTest(route=route), tempfile.TemporaryDirectory(
                prefix="public-page-release-boundary-"
            ) as directory:
                root = Path(directory).resolve()
                (root / "site-src").mkdir()
                (root / "site-src" / "pages.json").write_text(
                    json.dumps({"pages": [{"path": route}]}),
                    encoding="utf-8",
                )
                (root / "sitemap.xml").write_text(
                    "<urlset><url><loc>https://example.test/</loc></url></urlset>",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    SystemExit, "outside the shared published-page boundary"
                ):
                    release_builder.load_public_pages(root)

    def test_release_sitemap_cannot_escape_shared_page_boundary(self) -> None:
        release_builder = load_script("build-release")
        with tempfile.TemporaryDirectory(prefix="public-page-sitemap-boundary-") as directory:
            root = Path(directory).resolve()
            (root / "site-src").mkdir()
            (root / "site-src" / "pages.json").write_text(
                json.dumps({"pages": [{"path": "index.html"}]}),
                encoding="utf-8",
            )
            (root / "sitemap.xml").write_text(
                "<urlset><url><loc>https://example.test/../outside.html</loc></url></urlset>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SystemExit, "outside the shared published-page boundary"
            ):
                release_builder.load_public_pages(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
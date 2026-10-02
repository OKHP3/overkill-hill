#!/usr/bin/env python3
"""Focused route and launch regressions for the Found-Ry public surface.

These checks intentionally read both authoring and generated boundaries.  The
authoring page is the source of launch URLs; the published HTML is the route
contract visitors receive.  They do not fetch the external GitHub Pages app.
"""

from pathlib import Path
import re
import os
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUTHORING = ROOT / "site-src/pages/projects/found-ry/index.main.html"
CANONICAL = ROOT / "projects/found-ry/index.html"
LEGACY = ROOT / "found-ry/index.html"
APP_URL = "https://okhp3.github.io/overkill-hill-foundry/"
CANONICAL_ROUTE = "/projects/found-ry/"
LEGACY_ROUTE = "/found-ry/"


def hrefs(markup: str):
    return re.findall(r'\bhref=["\']([^"\']+)', markup)


class FoundryLaunchRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authoring = AUTHORING.read_text(encoding="utf-8")
        cls.canonical = CANONICAL.read_text(encoding="utf-8")
        cls.legacy = LEGACY.read_text(encoding="utf-8")

    def test_legacy_route_redirects_to_canonical_route(self):
        """Optional proposal: a legacy visitor is sent onward automatically."""
        if os.environ.get("RUN_PROPOSED_REDIRECT_CHECK") != "1":
            self.skipTest("proposed hosting redirect contract; opt in with RUN_PROPOSED_REDIRECT_CHECK=1")
        redirect_markers = (
            'http-equiv="refresh"',
            "window.location.replace",
            "window.location.href",
        )
        self.assertTrue(
            any(marker in self.legacy for marker in redirect_markers),
            "legacy /found-ry/ has a notice and link but no automatic redirect",
        )
        self.assertIn(CANONICAL_ROUTE, self.legacy)

    def test_canonical_route_is_self_canonical_and_indexable(self):
        self.assertIn(f'href="https://overkillhill.com{CANONICAL_ROUTE}" rel="canonical"', self.canonical)
        self.assertIn('id="foundry-tool-iframe"', self.canonical)
        self.assertNotIn(f'href="{LEGACY_ROUTE}" rel="canonical"', self.canonical)

    def test_authoring_and_generated_pages_use_same_direct_app_url(self):
        for markup in (self.authoring, self.canonical):
            self.assertIn(APP_URL, markup)
            self.assertNotIn("okhp3.github.io/OverKill-Hill-FoundRy/index.html", markup)

    def test_direct_app_links_are_launchable_external_links(self):
        for markup in (self.authoring, self.canonical):
            matches = re.findall(r'<a\b[^>]*href="(' + re.escape(APP_URL) + r')"[^>]*>', markup)
            self.assertGreaterEqual(len(matches), 2)
            for tag in re.findall(r'<a\b[^>]*href="' + re.escape(APP_URL) + r'"[^>]*>', markup):
                self.assertIn('target="_blank"', tag)
                self.assertIn('rel="noopener noreferrer"', tag)

    def test_foundry_page_does_not_launch_confusing_legacy_studio_routes(self):
        combined = self.authoring + self.canonical
        forbidden = ("chat.openai.com/g/", "chatgpt.com/g/", "/studio/", "/found-ry/studio")
        for route in forbidden:
            self.assertNotIn(route, combined)


if __name__ == "__main__":
    unittest.main()

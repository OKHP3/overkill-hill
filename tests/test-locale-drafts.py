#!/usr/bin/env python3
"""Protect the regional locale draft generator from cross-locale drift."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build-locale-drafts.py"
SPEC = importlib.util.spec_from_file_location("build_locale_drafts", BUILDER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load locale builder: {BUILDER}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LocaleDraftBuilderTests(unittest.TestCase):
    def test_es_mx_uses_reviewed_input_and_keeps_the_reviewed_file_untouched(self):
        canonical = (ROOT / "index.html").read_text(encoding="utf-8")
        reviewed_path = ROOT / "i18n" / "pilot" / "es-mx" / "reviewed" / "index.html"
        reviewed_before = reviewed_path.read_text(encoding="utf-8")
        dictionary, _profile = MODULE.load_pair_contract("es-mx")

        rendered = MODULE.build_es_mx(reviewed_before, canonical, "/", dictionary)

        self.assertEqual(reviewed_before, reviewed_path.read_text(encoding="utf-8"))
        self.assertIn('<html lang="es-MX">', rendered)
        self.assertIn('content="noindex, follow"', rendered)
        self.assertIn('href="/writings/murderbird/" hreflang="en"', rendered)
        self.assertIn('aria-label="Language: Español (México) · Borrador"', rendered)
        self.assertIn('src="/assets/img/', rendered)
        self.assertIn('.png"', rendered)
        self.assertIn('loading="lazy"', rendered)
        self.assertIn('property="og:locale" content="es_MX"', rendered)
        self.assertIn('class="site-specials site-specials--okh"', rendered)
        production_es_mx = (ROOT / "es-mx" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-banner-release="v0.8"', production_es_mx)
        self.assertIn('data-banner-release="v0.8"', rendered)

    def test_en_gb_preserves_murderbird_copy_boundaries(self):
        canonical = (ROOT / "index.html").read_text(encoding="utf-8")
        dictionary, _profile = MODULE.load_pair_contract("en-gb")

        rendered = MODULE.build_en_gb(canonical, "/", dictionary)

        self.assertIn('<html lang="en-GB">', rendered)
        self.assertIn('content="noindex, follow"', rendered)
        self.assertIn('src="/assets/img/', rendered)
        self.assertIn('.png"', rendered)
        self.assertIn('loading="lazy"', rendered)
        self.assertIn('The MurderBird stands on two metal feet', rendered)
        self.assertNotIn('sentinel', rendered.lower())
        self.assertIn('href="/writings/murderbird/" hreflang="en"', rendered)
        self.assertIn('og:locale', rendered)
        self.assertIn('en_GB', rendered)

    def test_visible_text_adapter_leaves_brand_tokens_and_paths_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "sample.html"
            sample.write_text(
                '<p>colors /about/ MurderBird and https://overkillhill.com/writings/murderbird/</p>',
                encoding="utf-8",
            )
            dictionary = {
                "entries": [
                    {"source": "colors", "target": "colours", "handling": "adapt"},
                    {"source": "MurderBird", "target": "Never", "handling": "preserve"},
                    {"source": "/about/", "target": "/x/", "handling": "preserve"},
                ]
            }
            rendered = MODULE.adapt_visible_text(sample.read_text(encoding="utf-8"), dictionary)

            self.assertIn("colours", rendered)
            self.assertIn("MurderBird", rendered)
            self.assertIn("/about/", rendered)
            self.assertIn("https://overkillhill.com/writings/murderbird/", rendered)
            self.assertNotIn("Never", rendered)

    def test_canonical_hash_ignores_generated_metadata_but_not_visible_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.html"
            generated = root / "generated.html"
            changed = root / "changed.html"
            source.write_text(
                '<meta http-equiv="Content-Security-Policy" content="one"><link href="/assets/css/theme.css?v=11111111"><p>stable</p>',
                encoding="utf-8",
            )
            generated.write_text(
                '<meta content="two" http-equiv="Content-Security-Policy"><link href="/assets/css/theme.css?v=22222222"><p>stable</p>',
                encoding="utf-8",
            )
            changed.write_text(
                '<meta http-equiv="Content-Security-Policy" content="two"><link href="/assets/css/theme.css?v=22222222"><p>changed</p>',
                encoding="utf-8",
            )

            self.assertEqual(MODULE.canonical_text_hash(source), MODULE.canonical_text_hash(generated))
            self.assertNotEqual(MODULE.canonical_text_hash(source), MODULE.canonical_text_hash(changed))


if __name__ == "__main__":
    unittest.main()

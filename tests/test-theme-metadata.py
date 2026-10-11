#!/usr/bin/env python3
"""Regression tests for brand theme metadata in published page heads."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND_THEME_CONTRACT = json.loads(
    (ROOT / "config" / "brand-theme-contract.json").read_text(encoding="utf-8")
)["brands"]
sys.path.insert(0, str(ROOT / "scripts"))
validator_spec = importlib.util.spec_from_file_location(
    "validate_site", ROOT / "scripts" / "validate-site.py"
)
assert validator_spec and validator_spec.loader
validator = importlib.util.module_from_spec(validator_spec)
validator_spec.loader.exec_module(validator)


def parse_html(raw: str):
    parser = validator.TagCounter()
    parser.feed(raw)
    return parser


def brand_page(
    brand: str,
    light: str,
    dark: str,
    color_scheme: str,
) -> str:
    return f"""<!doctype html>
<html><head>
  <meta name="theme-color" media="(prefers-color-scheme: light)" content="{light}">
  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="{dark}">
  <meta name="color-scheme" content="{color_scheme}">
</head><body class="{brand}"></body></html>"""


class BrandThemeMetadataTests(unittest.TestCase):
    def test_reviewed_contract_shape_passes(self) -> None:
        self.assertIsNone(
            validator.validate_brand_theme_contract(
                {"brands": BRAND_THEME_CONTRACT}
            )
        )

    def test_contract_loader_rejects_duplicate_brand_object_key(self) -> None:
        glee = json.dumps(BRAND_THEME_CONTRACT["glee"], separators=(",", ":"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brand-theme-contract.json"
            path.write_text(
                f'{{"brands":{{"glee":{glee},"glee":{glee}}}}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"duplicate brand entry 'glee'"):
                validator.load_brand_theme_contract(path)

    def test_contract_loader_names_brand_with_duplicate_property_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brand-theme-contract.json"
            path.write_text(
                '{"brands":{"glee":{"name":"Glee","name":"Hidden"}}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError, r"brand 'glee' has duplicate JSON key 'name'"
            ):
                validator.load_brand_theme_contract(path)

    def test_contract_reports_missing_required_field_by_brand(self) -> None:
        contract = deepcopy(BRAND_THEME_CONTRACT)
        del contract["glee"]["storageKey"]

        with self.assertRaisesRegex(
            ValueError, r"brand 'glee'.*storageKey"
        ):
            validator.validate_brand_theme_contract({"brands": contract})

    def test_contract_rejects_invalid_color_with_brand_name(self) -> None:
        contract = deepcopy(BRAND_THEME_CONTRACT)
        contract["askjamie"]["dark"] = "#not-a-color"

        with self.assertRaisesRegex(
            ValueError, r"brand 'askjamie'.*dark.*#not-a-color"
        ):
            validator.validate_brand_theme_contract({"brands": contract})

    def test_contract_rejects_invalid_color_scheme_with_brand_name(self) -> None:
        contract = deepcopy(BRAND_THEME_CONTRACT)
        contract["glee"]["colorScheme"] = "solarized"

        with self.assertRaisesRegex(
            ValueError, r"brand 'glee'.*colorScheme.*solarized"
        ):
            validator.validate_brand_theme_contract({"brands": contract})

    def test_contract_rejects_duplicate_brand_and_body_class_identifiers(self) -> None:
        contract = deepcopy(BRAND_THEME_CONTRACT)
        contract["other"] = deepcopy(contract["glee"])

        with self.assertRaisesRegex(ValueError, r"brand 'other'.*brand name"):
            validator.validate_brand_theme_contract({"brands": contract})

        contract["other"]["name"] = "Other"
        with self.assertRaisesRegex(ValueError, r"brand 'other'.*body class"):
            validator.validate_brand_theme_contract({"brands": contract})

    def test_valid_brand_metadata_passes(self) -> None:
        for expected in BRAND_THEME_CONTRACT.values():
            with self.subTest(brand=expected["name"]):
                self.assertEqual(
                    validator.validate_brand_theme_metadata(
                        f"{expected['bodyClass']}/index.html",
                        parse_html(
                            brand_page(
                                expected["bodyClass"],
                                expected["light"],
                                expected["dark"],
                                expected["colorScheme"],
                            )
                        ),
                    ),
                    [],
                )

    def test_missing_media_variant_names_page_and_media(self) -> None:
        glee = BRAND_THEME_CONTRACT["glee"]
        raw = brand_page(
            glee["bodyClass"],
            glee["light"],
            glee["dark"],
            glee["colorScheme"],
        ).replace(
            'media="(prefers-color-scheme: dark)"', "", 1
        )
        findings = validator.validate_brand_theme_metadata(
            "projects/index.html", parse_html(raw)
        )
        self.assertTrue(
            any(
                "projects/index.html" in finding.page
                and "missing theme-color metadata" in finding.msg
                and "(prefers-color-scheme: dark)" in finding.msg
                for finding in findings
            )
        )

    def test_wrong_color_and_color_scheme_report_values(self) -> None:
        askjamie = BRAND_THEME_CONTRACT["askjamie"]
        raw = brand_page(
            askjamie["bodyClass"],
            "#wrong",
            askjamie["dark"],
            "light dark",
        )
        findings = validator.validate_brand_theme_metadata(
            "index.html", parse_html(raw)
        )
        messages = "\n".join(finding.msg for finding in findings)
        self.assertIn(
            f"is '#wrong'; expected '{askjamie['light']}'",
            messages,
        )
        self.assertIn(
            f"is 'light dark'; expected exactly '{askjamie['colorScheme']}'",
            messages,
        )

    def test_missing_color_scheme_reports_expected_value(self) -> None:
        glee = BRAND_THEME_CONTRACT["glee"]
        raw = brand_page(
            glee["bodyClass"],
            glee["light"],
            glee["dark"],
            glee["colorScheme"],
        ).replace(
            f'<meta name="color-scheme" content="{glee["colorScheme"]}">', "", 1
        )
        findings = validator.validate_brand_theme_metadata(
            "glee/index.html", parse_html(raw)
        )
        messages = "\n".join(finding.msg for finding in findings)
        self.assertIn("missing color-scheme metadata", messages)
        self.assertIn(f"expected '{glee['colorScheme']}'", messages)

    def test_duplicate_or_unexpected_theme_color_is_rejected(self) -> None:
        glee = BRAND_THEME_CONTRACT["glee"]
        raw = brand_page(
            glee["bodyClass"],
            glee["light"],
            glee["dark"],
            glee["colorScheme"],
        ).replace(
            "</head>",
            f'<meta name="theme-color" content="{glee["light"]}"></head>',
            1,
        )
        findings = validator.validate_brand_theme_metadata(
            "glee/index.html", parse_html(raw)
        )
        messages = "\n".join(finding.msg for finding in findings)
        self.assertIn("unexpected theme-color metadata", messages)


if __name__ == "__main__":
    unittest.main()
#!/usr/bin/env python3
"""Regression tests for brand theme metadata in published page heads."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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
        source = f'{{\n  "brands": {{\n    "glee": {glee},\n    "glee": {glee}\n  }}\n}}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brand-theme-contract.json"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                validator.load_brand_theme_contract(path)
        message = str(raised.exception)
        duplicate_key_offset = source.rfind('"glee"')
        duplicate_key_column = duplicate_key_offset - source.rfind(
            "\n", 0, duplicate_key_offset
        )
        self.assertIn("duplicate brand entry 'glee'", message)
        self.assertIn("JSON path /brands/glee", message)
        self.assertIn(f"line 4, column {duplicate_key_column}", message)

    def test_contract_loader_names_brand_with_duplicate_property_key(self) -> None:
        source = (
            '{\n  "brands": {\n    "glee": {\n      "name": "Glee",\n'
            '      "name": "Hidden"\n    }\n  }\n}'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brand-theme-contract.json"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                validator.load_brand_theme_contract(path)
        duplicate_key_offset = source.rfind('"name"')
        duplicate_key_column = duplicate_key_offset - source.rfind(
            "\n", 0, duplicate_key_offset
        )
        message = str(raised.exception)
        self.assertIn("brand 'glee' has duplicate JSON key 'name'", message)
        self.assertIn("JSON path /brands/glee/name", message)
        self.assertIn(f"line 5, column {duplicate_key_column}", message)

    def test_contract_reports_all_malformed_entries_and_fields_by_brand(self) -> None:
        contract = deepcopy(BRAND_THEME_CONTRACT)
        contract["glee"]["storageKey"] = ""
        contract["glee"]["light"] = "orange"
        contract["askjamie"]["colorScheme"] = "solarized"
        contract["askjamie"]["dark"] = "#bad"
        contract["broken"] = "not an object"

        with self.assertRaises(ValueError) as raised:
            validator.validate_brand_theme_contract({"brands": contract})

        message = str(raised.exception)
        expected_errors = (
            "brand 'glee' has invalid 'storageKey'",
            "brand 'glee' has invalid light color 'orange'",
            "brand 'askjamie' has invalid dark color '#bad'",
            "brand 'askjamie' has invalid 'colorScheme' value 'solarized'",
            "brand 'broken' must be a JSON object",
        )
        for expected in expected_errors:
            with self.subTest(error=expected):
                self.assertIn(expected, message)

    def test_release_validator_fails_with_aggregated_brand_errors(self) -> None:
        contract = deepcopy(BRAND_THEME_CONTRACT)
        contract["glee"]["light"] = "orange"
        contract["askjamie"]["dark"] = "#bad"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brand-theme-contract.json"
            path.write_text(json.dumps({"brands": contract}), encoding="utf-8")
            command = """
import runpy
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import brand_theme
load = brand_theme.load_brand_theme_contract
brand_theme.load_brand_theme_contract = lambda: load(Path(sys.argv[2]))
runpy.run_path(sys.argv[3], run_name="__main__")
"""
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    command,
                    str(ROOT / "scripts"),
                    str(path),
                    str(ROOT / "scripts" / "validate-site.py"),
                ],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("ERROR: Invalid brand theme contract", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("brand 'glee' has invalid light color 'orange'", result.stderr)
        self.assertIn("brand 'askjamie' has invalid dark color '#bad'", result.stderr)

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
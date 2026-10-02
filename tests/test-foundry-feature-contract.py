#!/usr/bin/env python3
"""Focused contract checks for the published FoundRy feature page.

The default suite checks claims the website can prove from its authoring and
rendered HTML.  Set ``FOUNDRY_EXPECTED_PARITY=1`` to run intentionally failing
future-parity checks for runtime capabilities the page currently describes as
roadmap or asks the visitor to provide (such as named slots and recovery
exports).  Those checks are diagnostic and are not part of the normal gate.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site-src/pages/projects/found-ry/index.main.html"
RENDERED = ROOT / "projects/found-ry/index.html"
LIVE_APP = "https://okhp3.github.io/overkill-hill-foundry/"
GITHUB = "https://github.com/OKHP3/OverKill-Hill-FoundRy"
PARITY = os.environ.get("FOUNDRY_EXPECTED_PARITY") == "1"


class FoundryFeatureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.rendered = RENDERED.read_text(encoding="utf-8")

    def test_primary_app_link_is_canonical_and_repeated(self) -> None:
        self.assertGreaterEqual(self.source.count(LIVE_APP), 8)
        self.assertIn(LIVE_APP, self.rendered)
        self.assertIn('id="foundry-tool-iframe"', self.rendered)

    def test_feature_page_keeps_source_and_rendered_contract_aligned(self) -> None:
        # The build preserves the feature-page contract fragments.  Comparing
        # selected anchors avoids treating generated whitespace as semantics.
        for fragment in (
            "Every station persists to your browser's local storage",
            "The Platform Comparison exists precisely because the right destination changes",
            "Not a prompt generator that writes the GPT for you",
            "OpenAI Custom GPTs, Gemini Gems, and Microsoft Copilot",
        ):
            self.assertIn(fragment, self.source)
            self.assertIn(fragment, self.rendered)

    def test_gpt_studio_scope_is_separate_from_the_public_workbench(self) -> None:
        self.assertIn("Custom GPT", self.source)
        self.assertIn("Not a place to run or host a Custom GPT", self.source)
        self.assertIn("specification", self.source)
        self.assertIn("There is no API connection", self.rendered)

    def test_local_storage_and_recovery_language_is_honest(self) -> None:
        self.assertRegex(self.source, r"local storage only")
        self.assertIn("Clearing site data will clear your build", self.rendered)
        self.assertIn("export the specification", self.rendered)
        self.assertNotIn("cloud backup", self.source.lower())

    def test_supported_target_kinds_are_named_without_claiming_runtime_hosting(self) -> None:
        for target in ("Custom GPT", "Gemini Gem", "Copilot declarative agent"):
            self.assertIn(target, self.source)
        self.assertIn("Not a place to run or host a Custom GPT", self.rendered)
        self.assertIn("The workbench produces a specification", self.rendered)

    def test_evidence_language_separates_specification_from_execution(self) -> None:
        self.assertIn("acceptance criteria", self.source)
        self.assertIn("red-team cases", self.source)
        self.assertIn("does not deserve to exist", self.rendered)
        self.assertNotIn("guarantees", self.source.lower())

    @unittest.skipUnless(PARITY, "opt-in future parity diagnostic")
    def test_future_named_project_slots_are_available(self) -> None:
        self.assertIn("named project slots", self.source.lower())
        self.assertRegex(self.rendered, r"data-(?:project|slot)-")

    @unittest.skipUnless(PARITY, "opt-in future parity diagnostic")
    def test_future_recovery_import_export_controls_are_available(self) -> None:
        self.assertRegex(self.rendered, r"(?:Import|Restore|Recover) (?:a )?(?:backup|project)")


if __name__ == "__main__":
    unittest.main(verbosity=2)

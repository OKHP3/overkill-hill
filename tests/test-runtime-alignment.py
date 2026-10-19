"""Protect exact Node pins and the compatible Replit major from drifting."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("stack", ROOT / "scripts/check-stack-conformance.py")
STACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STACK)


class RuntimeAlignmentTests(unittest.TestCase):
    def fixture(self, root, nvm=None, locked=None, module="24"):
        (root / ".nvmrc").write_text(nvm or STACK.NODE_VERSION)
        (root / "package.json").write_text(json.dumps({"packageManager": "npm@11.19.0"}))
        (root / "package-lock.json").write_text(json.dumps({"packages": {
            "": {"engines": {"node": locked or STACK.NODE_ENGINE, "npm": STACK.NPM_ENGINE}}}}))
        (root / ".replit").write_text(f'modules = ["nodejs-{module}"]')

    def failures(self, root):
        report = STACK.Report({})
        STACK.check_runtime_alignment(root, report)
        return [r["code"] for r in report.findings if r["level"] == STACK.FAIL]

    def test_repository_declarations_agree(self):
        self.assertEqual(self.failures(ROOT), [])
        report = STACK.Report({})
        STACK.check_node(ROOT, report)
        STACK.check_npm_deps(ROOT, report)
        self.assertEqual([r for r in report.findings if r["level"] == STACK.FAIL], [])

    def test_stale_nvm_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, nvm="22.19.0")
            self.assertIn("NODE_ALIGNMENT", self.failures(root))

    def test_stale_lock_engine_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, locked="22.19.0")
            self.assertIn("NODE_ALIGNMENT", self.failures(root))

    def test_incompatible_replit_major_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root, module="22")
            self.assertIn("REPLIT_NODE", self.failures(root))

    def test_missing_npm_selection_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root)
            (root / "package.json").write_text("{}")
            self.assertIn("NPM_SELECTION", self.failures(root))

    def test_incompatible_npm_selection_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root)
            (root / "package.json").write_text(json.dumps({"packageManager": "npm@12.2.0"}))
            self.assertIn("NPM_SELECTION", self.failures(root))

    def test_supported_npm_selection_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.fixture(root)
            self.assertEqual(self.failures(root), [])


if __name__ == "__main__":
    unittest.main()

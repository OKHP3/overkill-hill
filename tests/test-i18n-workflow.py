#!/usr/bin/env python3
"""Exercise the Pages freshness dependency and its actual command in copied sites."""

import json
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMAND = "python3 scripts/check-i18n-release.py --mode check --format json"


def job_block(workflow, name):
    """Select a top-level job in the repository's block-style workflows."""
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", workflow, re.M | re.S)
    if match is None:
        raise AssertionError(f"Missing workflow job: {name}")
    return match.group(1)


def gate_command():
    workflow = (ROOT / ".github/workflows/validate.yml").read_text()
    validation = job_block(workflow, "validate")
    steps = re.split(r"^      - name: ", validation, flags=re.M)[1:]
    gates = [step for step in steps if f"        run: {COMMAND}\n" in step]
    if len(gates) != 1:
        raise AssertionError("Reusable validation must run exactly one live i18n check")
    gate = gates[0]
    if re.search(r"^        (if|continue-on-error|working-directory|shell):", gate, re.M):
        raise AssertionError("The freshness gate must use the default blocking execution")
    return gate.split("        run: ", 1)[1].splitlines()[0]


class I18nWorkflowTests(unittest.TestCase):
    def test_pages_requires_validation_and_gate_precedes_release_artifact(self):
        pages = (ROOT / ".github/workflows/pages.yml").read_text()
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        self.assertRegex(workflow, r"(?m)^  workflow_call:")
        self.assertRegex(job_block(pages, "validate"),
                         r"(?m)^    uses: \./\.github/workflows/validate.yml$")
        self.assertNotRegex(job_block(pages, "validate"),
                            r"(?m)^    (if|continue-on-error):")
        deploy = job_block(pages, "deploy")
        self.assertRegex(deploy, r"(?m)^    needs: validate$")
        self.assertNotRegex(deploy, r"(?m)^    (if|continue-on-error):")
        validation = job_block(workflow, "validate")
        self.assertRegex(validation, r"(?m)^    if: github.event_name != 'schedule'$")
        self.assertNotRegex(validation, r"(?m)^    continue-on-error:")
        command = gate_command()
        self.assertLess(validation.index(command), validation.index("--output site-release"))
        self.assertLess(validation.index(command), validation.index("path: site-release"))
        self.assertIn("run: python3 tests/test-i18n-workflow.py", validation)

    def run_copied_site(
        self,
        stale_locales=(),
        mutate_target=None,
        mutate_targets=(),
        blocking_locales=None,
    ):
        # Copy only the detector's real inputs. No source, review, or ledger writes
        # reach the checkout, and the wrapper runs without mocks.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = json.loads((ROOT / "i18n/sync.config.json").read_text())
            paths = {
                "scripts/check-i18n-release.py",
                ".agents/skills/okhp3-i18n-page-sync/scripts/i18n-page-sync.py",
                "i18n/sync.config.json", config["state_file"], config["search_index"],
            }
            for route in config["in_scope_routes"]:
                page = (route.strip("/") + "/index.html").lstrip("/")
                paths.add(page)
                for locale in config["target_locales"].values():
                    paths.add(f"{locale['root']}/{page}")
            for relative in paths:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            if blocking_locales is not None:
                config["blocking_locales"] = list(blocking_locales)
                (root / "i18n/sync.config.json").write_text(json.dumps(config))
            ledger = root / config["state_file"]
            state = json.loads(ledger.read_text())
            for locale in stale_locales:
                state["pages"]["/about/"]["targets"][locale]["synced_source_sha256"] = "0" * 64
            ledger.write_text(json.dumps(state))
            targets = list(mutate_targets)
            if mutate_target is not None:
                targets.append(mutate_target)
            for locale, route in targets:
                page = (route.strip("/") + "/index.html").lstrip("/")
                target = root / f"{config['target_locales'][locale]['root']}/{page}"
                target.write_bytes(target.read_bytes() + b"\n<!-- reviewed target drift -->\n")
            ledger_before = ledger.read_bytes()
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            result = subprocess.run(shlex.split(gate_command()), cwd=root,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(ledger_before, ledger.read_bytes())
            self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*") if path.is_file()})
            self.assertIn(result.returncode, (0, 1), result.stderr)
            return result.returncode, json.loads(result.stdout)

    def test_current_reviewed_french_passes_actual_workflow_command(self):
        code, report = self.run_copied_site()
        self.assertEqual(0, code)
        self.assertEqual([], report["policy"]["blocking_items"])
        self.assertEqual(0, sum(item["locale"] == "fr" for item in report["policy"]["blocking_items"]))

    def test_stale_french_remains_advisory_actual_workflow_command(self):
        code, report = self.run_copied_site(("fr",))
        self.assertEqual(0, code)
        self.assertTrue(any(item["locale"] == "fr" and item["route"] == "/about/"
                            and item["status"] == "stale"
                            for item in report["policy"]["advisory_items"]))

    def test_reviewed_french_target_drift_blocks_actual_workflow_command_for_every_route(self):
        config = json.loads((ROOT / "i18n/sync.config.json").read_text())
        for route in config["in_scope_routes"]:
            with self.subTest(route=route):
                code, report = self.run_copied_site(
                    mutate_target=("fr", route),
                    blocking_locales=("fr",),
                )
                self.assertEqual(1, code)
                self.assertTrue(any(
                    item["locale"] == "fr"
                    and item["route"] == route
                    for item in report["target_changed"]
                ))
                self.assertTrue(any(
                    item["locale"] == "fr"
                    and item["route"] == route
                    and item["status"] == "target_changed"
                    for item in report["policy"]["blocking_items"]
                ))

    def test_multiple_reviewed_french_target_changes_block_in_one_report(self):
        config = json.loads((ROOT / "i18n/sync.config.json").read_text())
        routes = config["in_scope_routes"]
        code, report = self.run_copied_site(
            mutate_targets=[("fr", route) for route in routes],
            blocking_locales=("fr",),
        )

        self.assertEqual(1, code)
        for route in routes:
            with self.subTest(route=route):
                self.assertTrue(any(
                    item["locale"] == "fr" and item["route"] == route
                    for item in report["target_changed"]
                ))
                self.assertTrue(any(
                    item["locale"] == "fr"
                    and item["route"] == route
                    and item["status"] == "target_changed"
                    for item in report["policy"]["blocking_items"]
                ))

    def test_german_and_spanish_target_drift_remains_advisory_for_every_route(self):
        config = json.loads((ROOT / "i18n/sync.config.json").read_text())
        for locale in ("de", "es"):
            for route in config["in_scope_routes"]:
                with self.subTest(locale=locale, route=route):
                    code, report = self.run_copied_site(
                        mutate_target=(locale, route),
                    )
                    self.assertEqual(0, code)
                    self.assertEqual([], report["policy"]["blocking_items"])
                    self.assertTrue(any(
                        item["locale"] == locale
                        and item["route"] == route
                        for item in report["target_changed"]
                    ))
                    self.assertTrue(any(
                        item["locale"] == locale
                        and item["route"] == route
                        and item["status"] == "target_changed"
                        for item in report["policy"]["advisory_items"]
                    ))

    def test_stale_drafts_remain_advisory(self):
        code, report = self.run_copied_site(("de", "es"))
        self.assertEqual(0, code)
        self.assertEqual([], report["policy"]["blocking_items"])
        for locale in ("de", "es"):
            self.assertTrue(any(item["locale"] == locale and item["route"] == "/about/"
                                and item["status"] == "stale"
                                for item in report["policy"]["advisory_items"]))


if __name__ == "__main__":
    unittest.main()

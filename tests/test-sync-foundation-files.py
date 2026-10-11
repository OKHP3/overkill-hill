"""Disposable-repository safety tests for scripts/sync-foundation-files.py."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync-foundation-files.py"
FILES = ["assets/css/theme.css", "assets/js/app.js", "assets/js/mermaid-init.js"]


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def load_module():
    spec = importlib.util.spec_from_file_location("sync_foundation_files", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def remove_readonly(func, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


class SyncFoundationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repos = {}
        for name in ("overkill-hill", "glee-fullytools", "askjamie"):
            repo = self.root / name
            repo.mkdir()
            git(repo, "init")
            git(repo, "config", "user.email", "safety@example.test")
            git(repo, "config", "user.name", "Safety Test")
            for relpath in FILES:
                path = repo / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("base\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "base")
            self.repos[name] = repo
        # The tested script derives this layout from its own path.
        destination = self.repos["overkill-hill"] / "scripts"
        destination.mkdir()
        shutil.copy2(SCRIPT, destination / SCRIPT.name)
        git(self.repos["overkill-hill"], "add", "scripts/sync-foundation-files.py")
        git(self.repos["overkill-hill"], "commit", "-m", "add sync utility")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args: str):
        return subprocess.run([sys.executable, "scripts/sync-foundation-files.py", *args], cwd=self.repos["overkill-hill"], capture_output=True, text=True)

    def source_revision(self) -> str:
        return git(self.repos["overkill-hill"], "rev-parse", "HEAD")

    def write_release_record(self, source_revision: str, site_revisions: dict[str, str]) -> Path:
        record_path = self.root / "foundation-release.md"
        record = {
            "schema": "okhp3-shared-foundation-release-v1",
            "source": {"repository": "overkill-hill", "revision": source_revision},
            "site_revisions": site_revisions,
        }
        record_path.write_text(
            "Reviewed release record\n\n```json\n"
            + json.dumps(record, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        return record_path

    def verify_release_record(self, record_path: Path):
        return self.invoke(
            "--verify",
            "--release-record", str(record_path),
            "--repo-path", "overkill-hill=.",
            "--repo-path", f"glee-fullytools={self.repos['glee-fullytools']}",
            "--repo-path", f"askjamie={self.repos['askjamie']}",
        )

    def test_lock_is_untouched_and_blocks_writes(self):
        target = self.repos["askjamie"] / FILES[0]
        target.write_text("different\n", encoding="utf-8")
        git(self.repos["askjamie"], "add", FILES[0])
        git(self.repos["askjamie"], "commit", "-m", "different")
        lock = self.repos["glee-fullytools"] / ".git" / "index.lock"
        lock.write_text("do not move\n", encoding="utf-8")
        result = self.invoke("--apply", "--file", "theme.css", "--source-repo", "overkill-hill", "--source-revision", self.source_revision())
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(lock.exists())
        self.assertEqual(lock.read_text(encoding="utf-8"), "do not move\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "different\n")

    def test_common_git_lock_in_linked_worktree_blocks_writes(self):
        linked = self.repos["glee-fullytools"]
        # ``onerror`` is retained for the Python 3.11 CI runtime; ``onexc``
        # was introduced later and has the same callback shape here.
        shutil.rmtree(linked, onerror=remove_readonly)
        git(self.repos["overkill-hill"], "worktree", "add", "--detach", str(linked))
        linked_theme = linked / FILES[0]
        linked_theme.write_text("linked version\n", encoding="utf-8")
        git(linked, "add", FILES[0])
        git(linked, "commit", "-m", "linked variant")
        common = Path(git(linked, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        lock = common / "packed-refs.lock"
        lock.write_text("do not move\n", encoding="utf-8")
        result = self.invoke("--apply", "--file", "theme.css", "--source-repo", "overkill-hill", "--source-revision", self.source_revision())
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(lock.exists())
        self.assertEqual(lock.read_text(encoding="utf-8"), "do not move\n")
        self.assertEqual(linked_theme.read_text(encoding="utf-8"), "linked version\n")
        self.assertIn("common Git directory", result.stdout)

    def test_dirty_target_bytes_are_untouched(self):
        target = self.repos["askjamie"] / FILES[0]
        target.write_text("user work\n", encoding="utf-8")
        result = self.invoke("--apply", "--file", "theme.css", "--source-repo", "overkill-hill", "--source-revision", self.source_revision())
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(target.read_text(encoding="utf-8"), "user work\n")

    def test_write_without_approved_source_is_rejected(self):
        result = self.invoke("--apply", "--file", "theme.css")
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIn("writes require", result.stdout)

    def test_dry_run_reports_each_site_revision_and_fingerprint(self):
        result = self.invoke("--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        inspection = report["inspection"]
        self.assertEqual(len(inspection), len(FILES))
        for file_report in inspection:
            self.assertEqual(file_report["status"], "in-sync")
            self.assertEqual(set(file_report["sites"]), set(self.repos))
            for name, site in file_report["sites"].items():
                self.assertEqual(site["site"], {"overkill-hill": "OKH", "glee-fullytools": "Glee", "askjamie": "AskJamie"}[name])
                self.assertEqual(site["revision"], git(self.repos[name], "rev-parse", "HEAD"))
                self.assertEqual(len(site["sha256"]), 64)

    def test_dry_run_identifies_drift_site_and_revision(self):
        target = self.repos["askjamie"] / FILES[0]
        target.write_text("drifted\n", encoding="utf-8")
        git(self.repos["askjamie"], "add", FILES[0])
        git(self.repos["askjamie"], "commit", "-m", "drift")
        revision = git(self.repos["askjamie"], "rev-parse", "HEAD")

        result = self.invoke("--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        theme_report = next(item for item in report["inspection"] if item["file"] == FILES[0])
        self.assertEqual(theme_report["status"], "diverged")
        self.assertIn("askjamie", theme_report["groups"][theme_report["sites"]["askjamie"]["sha256"]])
        self.assertEqual(theme_report["sites"]["askjamie"]["site"], "AskJamie")
        self.assertEqual(theme_report["sites"]["askjamie"]["revision"], revision)

    def test_relative_repo_path_overrides_resolve_from_checkout_root(self):
        pins = [f"{name}={git(repo, 'rev-parse', 'HEAD')}" for name, repo in self.repos.items()]
        result = self.invoke(
            "--verify",
            "--source-repo", "overkill-hill",
            "--source-revision", git(self.repos["overkill-hill"], "rev-parse", "HEAD"),
            "--repo-path", "overkill-hill=.",
            "--repo-path", "glee-fullytools=../glee-fullytools",
            "--repo-path", "askjamie=../askjamie",
            *sum((["--site-revision", pin] for pin in pins), []),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["verification"]["status"], "passed")

    def test_verify_reads_all_assets_from_pinned_revisions(self):
        pins = [f"{name}={git(repo, 'rev-parse', 'HEAD')}" for name, repo in self.repos.items()]
        # A working-tree edit must not affect immutable revision verification.
        (self.repos["askjamie"] / FILES[0]).write_text("uncommitted drift\n", encoding="utf-8")
        result = self.invoke(
            "--verify",
            "--source-repo", "overkill-hill",
            "--source-revision", git(self.repos["overkill-hill"], "rev-parse", "HEAD"),
            *sum((["--site-revision", pin] for pin in pins), []),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["verification"]["status"], "passed")
        self.assertEqual(len(report["verification"]["fingerprints"]), len(FILES))
        for fingerprint in report["verification"]["fingerprints"]:
            self.assertEqual(set(fingerprint["sites"]), set(self.repos))
            expected = fingerprint["expected"]["sha256"]
            self.assertTrue(all(site["sha256"] == expected for site in fingerprint["sites"].values()))

    def test_release_record_is_single_source_and_detects_unreviewed_current_foundation(self):
        pins = {
            name: git(repo, "rev-parse", "HEAD")
            for name, repo in self.repos.items()
        }
        record_path = self.write_release_record(self.source_revision(), pins)

        baseline = self.verify_release_record(record_path)
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        baseline_report = json.loads(baseline.stdout)["verification"]["current_source_review"]
        self.assertEqual(baseline_report["status"], "current")
        self.assertEqual(baseline_report["changed_assets"], [])

        source = self.repos["overkill-hill"]
        (source / FILES[0]).write_text("proposed foundation change\n", encoding="utf-8")
        git(source, "add", FILES[0])
        git(source, "commit", "-m", "proposed unreviewed foundation change")

        stale = self.verify_release_record(record_path)
        self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
        report = json.loads(stale.stdout)
        review = report["verification"]["current_source_review"]
        self.assertEqual(review["status"], "stale-approval")
        self.assertEqual(review["changed_assets"], [FILES[0]])
        self.assertIn("new owner-reviewed approval is required", report["problems"][0])

    def test_release_record_loader_emits_validated_pins(self):
        pins = {
            name: git(repo, "rev-parse", "HEAD")
            for name, repo in self.repos.items()
        }
        record_path = self.write_release_record(self.source_revision(), pins)
        env_path = self.root / "github-env"
        output_path = self.root / "github-output"

        result = subprocess.run(
            [
                sys.executable, "scripts/sync-foundation-files.py",
                "--load-release-record", str(record_path),
                "--github-env-file", str(env_path),
                "--github-output-file", str(output_path),
            ],
            cwd=self.repos["overkill-hill"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"THEME_CONTROL_OKH_REVISION={pins['overkill-hill']}", env_path.read_text())
        self.assertIn(f"theme_control_glee_revision={pins['glee-fullytools']}", output_path.read_text())

    def test_verify_names_pinned_site_revision_asset_and_fingerprint(self):
        askjamie = self.repos["askjamie"]
        (askjamie / FILES[0]).write_text("diverged\n", encoding="utf-8")
        git(askjamie, "add", FILES[0])
        git(askjamie, "commit", "-m", "diverged foundation")
        pins = [f"{name}={git(repo, 'rev-parse', 'HEAD')}" for name, repo in self.repos.items()]
        result = self.invoke(
            "--verify",
            "--source-repo", "overkill-hill",
            "--source-revision", git(self.repos["overkill-hill"], "rev-parse", "HEAD"),
            *sum((["--site-revision", pin] for pin in pins), []),
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        mismatch = report["verification"]["mismatches"][0]
        self.assertEqual(mismatch["site"], "AskJamie")
        self.assertEqual(mismatch["revision"], pins[2].split("=", 1)[1])
        self.assertEqual(mismatch["asset"], FILES[0])
        self.assertNotEqual(mismatch["actual_fingerprint"], mismatch["expected_fingerprint"])
        self.assertIn("AskJamie revision", result.stdout)

    def test_failing_hook_prevents_commit_and_accounts_for_output(self):
        module = load_module()
        glee = self.repos["glee-fullytools"]
        (glee / FILES[0]).write_text("older\n", encoding="utf-8")
        git(glee, "add", FILES[0])
        git(glee, "commit", "-m", "older")
        fail = glee / "scripts" / "fail.py"
        fail.parent.mkdir(exist_ok=True)
        fail.write_text("from pathlib import Path\nPath('generated.txt').write_text('made')\nraise SystemExit(1)\n", encoding="utf-8")
        git(glee, "add", "scripts/fail.py")
        git(glee, "commit", "-m", "failing generator")
        module.POST_WRITE_HOOKS = {"glee-fullytools": {FILES[0]: [[sys.executable, "scripts/fail.py"]]}}
        before = git(glee, "rev-parse", "HEAD")
        with redirect_stdout(io.StringIO()), patch.object(module, "mirror_root", return_value=self.root), patch.object(
            sys, "argv", [str(SCRIPT), "--commit", "--file", "theme.css", "--source-repo", "overkill-hill", "--source-revision", self.source_revision()]
        ):
            self.assertEqual(module.main(), 5)
        self.assertEqual(git(glee, "rev-parse", "HEAD"), before)
        status = git(glee, "status", "--short")
        self.assertIn("M assets/css/theme.css", status)
        self.assertIn("?? generated.txt", status)


if __name__ == "__main__":
    unittest.main()

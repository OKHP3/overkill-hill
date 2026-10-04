#!/usr/bin/env python3
"""Focused regression coverage for the Pages allowlist boundary."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build-release.py"
COMMIT = "a" * 40
ARCHIVE_POLICY = "config/murderbird-source-archive.json"


def accepted_murderbird_media() -> list[str]:
    """The 25 selected still paths from PR 54, not a new art approval."""
    paths = ["assets/img/og/murderbird-story-share-2026-09-06.png"]
    for scene in ("maker-clean", "mechanic", "water", "heart", "sentinel", "master"):
        variant = "-03" if scene == "master" else ""
        paths.append(f"assets/img/library/murderbird-unified-{scene}-candidate{variant}-2026-09-06.png")
        for width in (480, 960, 1536):
            paths.append(f"assets/img/webp/murderbird-unified-{scene}{variant}-2026-09-06-{width}.webp")
    return paths


class ReleasePackageTests(unittest.TestCase):
    def test_pages_upload_preserves_allowlisted_public_dotfiles(self) -> None:
        pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        upload = pages.split("- name: Upload site artifact\n", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("path: site-release", upload)
        self.assertIn("include-hidden-files: true", upload)

    def test_retry_artifact_identity_follows_the_successful_producer(self) -> None:
        validation = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        producer = "validated-site-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}"
        self.assertIn(f"release_artifact_name: {producer}", validation)
        self.assertIn(f"name: {producer}", validation)
        self.assertIn("value: ${{ jobs.validate.outputs.release_artifact_name }}", validation)
        self.assertIn("name: ${{ needs.validate.outputs.release_artifact_name }}", pages)
        self.assertLess(pages.index('run: test -n "$RELEASE_ARTIFACT_NAME"'), pages.index("uses: actions/download-artifact"))
        package = "github-pages-${{ github.run_id }}-${{ github.run_attempt }}"
        self.assertIn(f"name: {package}", pages)
        self.assertIn(f"artifact_name: {package}", pages)
        self.assertIn("name: live-edge-report-${{ github.run_id }}-${{ github.run_attempt }}", pages)
        self.assertIn("--verify", pages)
        # No wildcard/latest fallback or rebuild may replace the trusted artifact.
        self.assertNotIn("pattern:", pages)
        self.assertEqual(pages.count("scripts/build-release.py"), 1)

    def test_committed_freshness_rejects_stale_files_without_repairing_them(self) -> None:
        validation = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        preflight = validation.split("- name: Check committed generated output before regeneration\n", 1)[1].split("\n      - name:", 1)[0]
        commands = re.findall(r"^          python3 (.+)$", preflight, re.MULTILINE)
        self.assertEqual(commands, [
            "scripts/build-site.py --check",
            "scripts/build-search-index.py --check",
            "scripts/sync-universe-map.py --check",
        ])
        for command in commands:
            self.assertLess(validation.index(command), validation.index("- name: Regenerate indexed universe navigation"))

        def text_inputs(directory, names):
            return [name for name in names if name in (
                ".git", ".local", "node_modules", "__pycache__", "img",
            ) or (Path(directory, name).is_file() and Path(name).suffix not in (
                ".py", ".html", ".json", ".css", ".js", ".mjs", ".xml", ".txt", ".md", ".mmd",
            ))]

        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(ROOT, source, ignore=text_inputs)

            def run_preflight():
                for command in commands:
                    result = subprocess.run(
                        [sys.executable, "-X", "utf8", *command.split()], cwd=source,
                        text=True, encoding="utf-8", capture_output=True,
                    )
                    if result.returncode:
                        return result
                return result

            clean = run_preflight()
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            for relative, diagnostic in (
                ("index.html", "Generated HTML is stale"),
                ("feed.xml", "Atom feed is stale"),
                ("assets/data/search-index.json", "Search index is stale"),
            ):
                with self.subTest(path=relative):
                    target = source / relative
                    original = target.read_bytes()
                    target.write_bytes(original + b"\n ")
                    before = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in source.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
                    rejected = run_preflight()
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn(diagnostic, rejected.stdout + rejected.stderr)
                    after = {p.relative_to(source): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in source.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
                    self.assertEqual(before, after, "Freshness gate must not regenerate submitted files")
                    target.write_bytes(original)

    def test_every_released_file_has_verified_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "source", Path(temporary) / "release"
            self.archive_fixture(source)
            extra = {
                "assets/css/theme.css": b"body{}",
                "assets/js/app.js": b"void 0;",
                "assets/data/search-index-fr.json": b"{}",
                "assets/vendor/runtime.mjs": b"export default 1;",
                "assets/fonts/fixture.woff2": b"wOF2-font-fixture",
                "assets/fonts/fixture-license.txt": b"Fixture font license",
            }
            for relative, data in extra.items():
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            self.assertEqual(self.build(output, source).returncode, 0)
            manifest_path = output / "assets/audit/release-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(
                manifest["artifacts"]["/feed.xml"]["sha256"],
                hashlib.sha256((output / "feed.xml").read_bytes()).hexdigest(),
            )
            integrity = manifest.get("integrity", {})
            self.assertEqual(set(integrity), set(manifest["files"]) - {"assets/audit/release-manifest.json"})
            for relative, entry in integrity.items():
                data = (output / relative).read_bytes()
                self.assertEqual(entry, {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
            self.assertEqual(self.verify(output, source).returncode, 0)
            for relative in ["index.html", "feed.xml", *extra, accepted_murderbird_media()[0]]:
                target = output / relative
                original = target.read_bytes()
                # Same-length replacement proves the digest, not just size, is checked.
                for changed in [bytes([original[0] ^ 1]) + original[1:], original + b"audit"]:
                    with self.subTest(path=relative, size=len(changed)):
                        target.write_bytes(changed)
                        rejected = self.verify(output, source)
                        self.assertNotEqual(rejected.returncode, 0)
                        self.assertIn(relative, rejected.stderr)
                target.write_bytes(original)

    def test_integrity_manifest_and_inventory_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "source", Path(temporary) / "release"
            self.archive_fixture(source)
            self.assertEqual(self.build(output, source).returncode, 0)
            path = output / "assets/audit/release-manifest.json"
            original = path.read_text()
            for change in ("missing-map", "missing-entry", "extra-entry", "wrong-size", "wrong-hash", "wrong-commit", "old-schema"):
                with self.subTest(change=change):
                    manifest = json.loads(original)
                    if change == "missing-map":
                        manifest.pop("integrity", None)
                    elif change == "missing-entry":
                        manifest.get("integrity", {}).pop("index.html", None)
                    elif change == "extra-entry":
                        manifest.setdefault("integrity", {})["../outside"] = {}
                    elif change == "wrong-size":
                        manifest.setdefault("integrity", {}).setdefault("index.html", {})["bytes"] = -1
                    elif change == "wrong-hash":
                        manifest.setdefault("integrity", {}).setdefault("index.html", {})["sha256"] = "0" * 64
                    elif change == "wrong-commit":
                        manifest["commit"] = "b" * 40
                    else:
                        manifest["schema"] = 2
                    path.write_text(json.dumps(manifest))
                    self.assertNotEqual(self.verify(output, source).returncode, 0)
            path.write_text(original)
            target = output / accepted_murderbird_media()[0]
            data = target.read_bytes()
            target.unlink()
            self.assertNotEqual(self.verify(output, source).returncode, 0)
            renamed = target.with_name("renamed.png")
            renamed.write_bytes(data)
            self.assertNotEqual(self.verify(output, source).returncode, 0)
            target.write_bytes(data)
            self.assertNotEqual(self.verify(output, source).returncode, 0)
            renamed.unlink()
            self.assertEqual(self.verify(output, source).returncode, 0)

    def test_real_selected_media_overlay_when_available(self) -> None:
        media_root = Path(os.environ.get("MURDERBIRD_MEDIA_REVIEW_SOURCE", str(ROOT)))
        register_path = media_root / "assets/audit/murderbird-still-release-register.json"
        if not register_path.is_file():
            self.skipTest("Accepted still release is a separate branch; set MURDERBIRD_MEDIA_REVIEW_SOURCE for combined proof")
        register = json.loads(register_path.read_text(encoding="utf-8"))
        records = list(register["masters"])
        for master in register["masters"]:
            records.extend(master["derivatives"])
        # The social record remains owned by the still release register.
        social = register.get("social")
        self.assertIsInstance(social, dict)
        records.append(social)
        self.assertEqual({record["path"] for record in records}, set(accepted_murderbird_media()))
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "source", Path(temporary) / "release"
            policy = self.archive_fixture(source)
            for record in records:
                original = media_root / record["path"]
                self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), record["sha256"], record["path"])
                shutil.copy2(original, source / record["path"])
            for relative in policy["excludedLibraryPngs"]:
                shutil.copy2(ROOT / relative, source / relative)
            shutil.copytree(ROOT / "assets/murderbird/v2", source / "assets/murderbird/v2", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
            built = self.build(output, source)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(self.verify(output, source).returncode, 0)
            for record in records:
                self.assertEqual(hashlib.sha256((output / record["path"]).read_bytes()).hexdigest(), record["sha256"], record["path"])
            for relative in policy["excludedLibraryPngs"] + ["assets/murderbird/v2"]:
                self.assertFalse((output / relative).exists(), relative)

    def test_archived_source_bytes_match_preservation_receipt(self) -> None:
        receipt = json.loads((ROOT / "tests/fixtures/murderbird-source-preservation.json").read_text(encoding="utf-8"))
        policy = json.loads((ROOT / ARCHIVE_POLICY).read_text(encoding="utf-8"))
        entries = {entry["path"]: entry for entry in receipt["files"]}
        actual = {path.relative_to(ROOT).as_posix() for path in (ROOT / "assets/murderbird/v2").rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store"}
        actual.update(policy["excludedLibraryPngs"])
        self.assertEqual(set(entries), actual)
        for relative, entry in entries.items():
            data = (ROOT / relative).read_bytes()
            self.assertEqual(len(data), entry["bytes"], relative)
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"], relative)

    def archive_fixture(self, source: Path) -> dict:
        """Tiny synthetic release inputs, never substitutes for production art."""
        source.mkdir()
        paths = {
            "site-src/pages.json": json.dumps({"pages": [{"path": "index.html"}]}),
            "index.html": "<!doctype html><title>Release boundary fixture</title>",
            "sitemap.xml": '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://overkillhill.com/</loc></url></urlset>',
            "feed.xml": '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><id>https://overkillhill.com/writings/</id></feed>\n',
            "assets/data/search-index.json": "{}",
            "assets/downloads/public-guide.md": "Public download fixture",
        }
        for name in (".nojekyll", "CNAME", "favicon.ico", "favicon.svg", "humans.txt", "llms.txt", "robots.txt", "site.webmanifest"):
            paths[name] = "fixture"
        policy = json.loads((ROOT / ARCHIVE_POLICY).read_text(encoding="utf-8"))
        paths[ARCHIVE_POLICY] = json.dumps(policy)
        for relative in policy["excludedLibraryPngs"] + accepted_murderbird_media():
            paths[relative] = "synthetic path-boundary fixture, not a production image"
        paths["assets/murderbird/v2/masters/01-maker.png"] = "historical fixture"
        paths["assets/img/library/unrelated-library-fixture.png"] = "unrelated fixture"
        for relative, value in paths.items():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        return policy

    def test_archive_exclusion_preserves_all_25_selected_media_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "source", Path(temporary) / "release"
            policy = self.archive_fixture(source)
            built = self.build(output, source)
            self.assertEqual(built.returncode, 0, built.stderr)
            for relative in policy["excludedLibraryPngs"]:
                self.assertFalse((output / relative).exists(), relative)
            self.assertFalse((output / "assets/murderbird/v2").exists())
            self.assertEqual(len(accepted_murderbird_media()), 25)
            for relative in accepted_murderbird_media() + ["assets/img/library/unrelated-library-fixture.png"]:
                self.assertEqual((output / relative).read_bytes(), (source / relative).read_bytes())
            self.assertEqual(self.verify(output, source).returncode, 0)

            # Even a rewritten release inventory cannot authorize archived art.
            forbidden = policy["excludedLibraryPngs"][0]
            shutil.copy2(source / forbidden, output / forbidden)
            manifest_path = output / "assets/audit/release-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = sorted(manifest["files"] + [forbidden])
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            rejected = self.verify(output, source)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("archived source file entered release", rejected.stderr)

    def test_private_music_session_archives_are_excluded_and_public_downloads_remain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "source", Path(temporary) / "release"
            self.archive_fixture(source)
            public_download = source / "assets/downloads/okh-prompt-protocol-template.md"
            public_download.parent.mkdir(parents=True, exist_ok=True)
            public_download.write_text("Public visitor download", encoding="utf-8")

            private = source / "assets/downloads/music-session-2026-09-17"
            private_file = private / "work/private-session.wav"
            private_file.parent.mkdir(parents=True)
            private_file.write_bytes(b"private fixture")

            built = self.build(output, source)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual((output / "assets/downloads/okh-prompt-protocol-template.md").read_bytes(),
                             public_download.read_bytes())
            manifest = json.loads((output / "assets/audit/release-manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(any(path.startswith("assets/downloads/music-session-")
                                 for path in manifest["files"]))
            self.assertEqual(self.verify(output, source).returncode, 0)

            released_archive = output / "assets/downloads/music-session-2026-09-17"
            target = released_archive / "outputs" / "private-session.wav"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"private fixture")
            rejected = self.verify(output, source)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("private download archive entered release package", rejected.stderr)

    def test_private_music_session_symlinks_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "source", Path(temporary) / "release"
            self.archive_fixture(source)
            public_download = source / "assets/downloads/okh-prompt-protocol-template.md"
            public_download.parent.mkdir(parents=True, exist_ok=True)
            public_download.write_text("Public visitor download", encoding="utf-8")

            private = source / "assets/downloads/music-session-2026-09-17"
            private_file = private / "work/private-session.wav"
            private_file.parent.mkdir(parents=True, exist_ok=True)
            private_file.write_bytes(b"private fixture")
            private_link = private / "outputs/private-session-link.wav"
            private_link.parent.mkdir(parents=True, exist_ok=True)
            try:
                private_link.symlink_to(private_file)
            except OSError as error:
                if os.name == "nt" and error.winerror == 1314:
                    self.skipTest("Windows symlink privilege unavailable (WinError 1314)")
                raise

            built = self.build(output, source)
            self.assertEqual(built.returncode, 0, built.stderr)
            manifest = json.loads((output / "assets/audit/release-manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(any(path.startswith("assets/downloads/music-session-")
                                 for path in manifest["files"]))

            released_link = output / "assets/downloads/music-session-2026-09-17/outputs/private-session-link.wav"
            released_link.parent.mkdir(parents=True, exist_ok=True)
            try:
                released_link.symlink_to(public_download)
            except OSError as error:
                if os.name == "nt" and error.winerror == 1314:
                    self.skipTest("Windows symlink privilege unavailable (WinError 1314)")
                raise
            rejected = self.verify(output, source)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("private download archive entered release package", rejected.stderr)

    def test_archive_policy_fails_closed_for_missing_or_unsafe_entries(self) -> None:
        invalid_entries = ["../index.html", "assets/img/library/../hero.png", "assets/img/library//held.png", "assets/img/library/./held.png", "assets/img/library/held.webp", "assets/img/hero.png", "C:/held.png", "assets\\img\\library\\held.png"]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            policy = self.archive_fixture(source)
            path = source / ARCHIVE_POLICY
            cases = [None, "not json", json.dumps({"schema": 999}), json.dumps({"schema": 1, "excludedLibraryPngs": "not a list"})]
            for entry in invalid_entries:
                cases.append(json.dumps({**policy, "excludedLibraryPngs": [entry]}))
            cases.append(json.dumps({**policy, "excludedLibraryPngs": [policy["excludedLibraryPngs"][0]] * 2}))
            for index, value in enumerate(cases):
                with self.subTest(case=index):
                    if value is None:
                        path.unlink()
                    else:
                        path.write_text(value, encoding="utf-8")
                    rejected = self.build(Path(temporary) / f"release-{index}", source)
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn("archive", rejected.stderr.lower())

    def build(self, output: Path, source: Path = ROOT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BUILDER), "--source", str(source), "--output", str(output), "--commit", COMMIT],
            text=True,
            capture_output=True,
            check=False,
        )

    def verify(self, output: Path, source: Path = ROOT) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BUILDER), "--verify", "--source", str(source), "--output", str(output), "--commit", COMMIT],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_package_includes_public_routes_and_excludes_repository_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site-release"
            result = self.build(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            pages = json.loads((ROOT / "site-src/pages.json").read_text(encoding="utf-8"))["pages"]
            for page in pages:
                self.assertTrue((output / page["path"]).is_file(), page["path"])
            self.assertTrue((output / "under-construction.html").is_file())
            self.assertTrue((output / "found-ry/index.html").is_file())
            self.assertTrue((output / "de/index.html").is_file())
            self.assertTrue((output / "es/projects/index.html").is_file())
            for locale in ("en-gb", "es-mx"):
                for route in ("index.html", "about/index.html", "projects/index.html", "contact/index.html"):
                    page = output / locale / route
                    self.assertTrue(page.is_file(), page)
                    self.assertRegex(
                        page.read_text(encoding="utf-8"),
                        r'<meta(?=[^>]*\bname="robots")(?=[^>]*\bcontent="noindex, follow")[^>]*>',
                    )
            sitemap = (output / "sitemap.xml").read_text(encoding="utf-8")
            search_index = (output / "assets/data/search-index.json").read_text(encoding="utf-8")
            self.assertNotIn("/en-gb/", sitemap)
            self.assertNotIn("/es-mx/", sitemap)
            self.assertNotIn("/en-gb/", search_index)
            self.assertNotIn("/es-mx/", search_index)
            self.assertTrue((output / "assets/downloads/okh-prompt-protocol-template.md").is_file())
            video = "assets/video/murderbird-first-choice-635f0e15.mp4"
            self.assertEqual((output / video).read_bytes(), (ROOT / video).read_bytes())
            self.assertTrue((output / "assets/img/murderbird-first-choice-poster.jpg").is_file())
            self.assertFalse((output / "assets/murderbird/production").exists())
            for forbidden in (
                "AGENTS.md", "package-lock.json", "scripts/build-site.py",
                "site-src/pages/index.main.html", "tests/csp-qa.test.mjs",
                "assets/templates/template--homepage.html",
            ):
                self.assertFalse((output / forbidden).exists(), forbidden)
            policy = json.loads((ROOT / ARCHIVE_POLICY).read_text(encoding="utf-8"))
            for forbidden in policy["excludedLibraryPngs"] + ["assets/murderbird/v2", ARCHIVE_POLICY]:
                self.assertFalse((output / forbidden).exists(), forbidden)
            manifest = json.loads((output / "assets/audit/release-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["commit"], COMMIT)
            self.assertIn("/assets/data/search-index.json", manifest["artifacts"])
            verified = self.verify(output)
            self.assertEqual(verified.returncode, 0, verified.stderr)

            manifest["artifacts"]["/sitemap.xml"]["sha256"] = "0" * 64
            (output / "assets/audit/release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            mismatched = self.verify(output)
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertIn("hash mismatch", mismatched.stderr)

    def test_rejects_unsafe_source_page_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "node_modules"))
            manifest_path = source / "site-src/pages.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["pages"][0]["path"] = "../AGENTS.md"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.build(Path(temporary) / "site-release", source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe published page path", result.stderr)

    def test_pages_workflow_deploys_only_after_reusable_validation(self) -> None:
        pages_workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        validation_workflow = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", pages_workflow)
        self.assertIn("uses: ./.github/workflows/validate.yml", pages_workflow)
        self.assertRegex(pages_workflow, r"deploy:\n[\s\S]*?needs: validate")
        self.assertRegex(pages_workflow, r"deploy:\n[\s\S]*?group: pages\n\s+cancel-in-progress: false")
        self.assertIn("path: site-release", pages_workflow)
        self.assertIn("actions/download-artifact", pages_workflow)
        self.assertNotIn("Build the explicit public release artifact", pages_workflow)
        self.assertIn("workflow_call:", validation_workflow)
        self.assertRegex(validation_workflow, r"if: github\.event_name != 'schedule'")
        self.assertIn("run: python3 tests/test-release-package.py", validation_workflow)
        self.assertIn("--output site-release", validation_workflow)
        self.assertIn("validated-site-${{ github.sha }}", validation_workflow)


if __name__ == "__main__":
    unittest.main()

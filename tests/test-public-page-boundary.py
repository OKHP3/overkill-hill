#!/usr/bin/env python3
"""Contract tests for the shared production-page discovery boundary."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from collections import Counter
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import public_page_boundary


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


def discovers_html_by_source_pattern(source: str) -> bool:
    """Recognize explicit and dynamically assembled HTML discovery patterns."""
    source = re.sub(r"\\\s*\n", " ", source)
    direct_discovery = re.compile(
        r"iter_public_html_files|is_public_page_path|"
        r"\.(?:rglob|glob)\s*\(\s*[\"'][^\"']*\.html|"
        r"git\s+ls-files[^\n]*\.html|"
        r"\bfind\b[^\n]*(?:-iname?\s+[\"'][^\"']*\.html[\"']|\.html\b)|"
        r"(?:\*\*/)?\*\.html\b|"
        r"\b(?:find|iter)_html_files\s*\(",
        re.IGNORECASE,
    )
    if direct_discovery.search(source):
        return True

    has_enumeration = re.search(
        r"\.(?:rglob|glob)\s*\(|\bglob(?:\.sync)?\s*\(|"
        r"os\.(?:walk|scandir)\s*\(",
        source,
        re.IGNORECASE,
    )
    has_html_suffix = re.search(r"[\"']\.html[\"']", source, re.IGNORECASE)
    has_suffix_check = re.search(
        r"\.suffix\b|\.endswith\s*\(", source, re.IGNORECASE
    )
    if has_enumeration and has_html_suffix and has_suffix_check:
        return True

    # An extension or glob may be assembled from fragments, kept in a named
    # extension variable, or interpolated. Do not treat arbitrary HTML markup
    # (for example, a selector named "html") as evidence of page discovery.
    has_assembled_html_literal = re.search(
        r"[\"'][^\"']*(?:\*\.|\.)[\"']\s*\+\s*[\"']html[\"']|"
        r"[\"']html[\"']\s*\+\s*[\"'][^\"']*(?:\*\.|\.)[\"']",
        source,
        re.IGNORECASE,
    )
    has_html_extension_variable = re.search(
        r"\b(?:html[_-]?(?:ext|extension|suffix)|(?:ext|extension|suffix)[_-]?html|"
        r"ext|extension|suffix)\s*=\s*[\"']\.?html[\"']",
        source,
        re.IGNORECASE,
    )
    has_html_pattern_variable = re.search(
        r"\b(?:html[_-]?pattern|glob[_-]?pattern|pattern)\s*=\s*[\"']"
        r"[^\"']*\.html[\"']",
        source,
        re.IGNORECASE,
    )
    has_html_format_pattern = re.search(
        r"[\"'][^\"']*(?:\*\.|\.)\{[^\"']*\}[^\"']*[\"']\s*\.format"
        r"\s*\([^)]*[\"']html[\"']",
        source,
        re.IGNORECASE,
    )
    has_dynamic_assembly = re.search(
        r"\+|f[\"']|`[^`]*\$\{|\.format\s*\(",
        source,
        re.IGNORECASE,
    )
    has_glob = re.search(
        r"\.(?:rglob|glob)\s*\(|\bglob(?:\.sync)?\s*\(",
        source,
        re.IGNORECASE,
    )
    if (
        has_glob
        and (
            (has_html_pattern_variable or has_html_format_pattern)
            or (
                has_dynamic_assembly
                and (
                    has_assembled_html_literal
                    or has_html_extension_variable
                )
            )
        )
    ) or (
        has_suffix_check
        and (
            has_html_extension_variable
            or has_assembled_html_literal
            or has_html_format_pattern
        )
        and has_dynamic_assembly
    ):
        return True

    # Walking is a discovery mechanism only when coupled to an HTML-specific
    # suffix check; generic walks used for JSON/assets are not page scanners.
    return bool(
        re.search(r"os\.(?:walk|scandir)\s*\(", source, re.IGNORECASE)
        and has_suffix_check
        and (
            has_assembled_html_literal
            or has_html_extension_variable
            or re.search(r"[\"']\.html[\"']", source, re.IGNORECASE)
        )
    )


def active_workflow_files(workflows_dir: Path) -> list[Path]:
    """Return active workflow files, excluding nested archive directories."""
    return sorted(
        path
        for path in Path(workflows_dir).iterdir()
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )


def workflow_run_commands(source: str) -> list[str]:
    """Extract inline and block-scalar run commands from workflow YAML."""
    lines = source.splitlines()
    commands: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)(-\s+)?run:\s*(.*)$", lines[index])
        if not match:
            index += 1
            continue

        indent = len(match.group(1)) + len(match.group(2) or "")
        value = match.group(3).strip()
        if value in {"|", "|-", "|+", ">", ">-", ">+"}:
            index += 1
            block = []
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= indent:
                    break
                block.append(line)
                index += 1
            commands.append("\n".join(block))
        else:
            commands.append(value)
            index += 1
    return commands


class ExternalArchiveRetryTests(unittest.TestCase):
    def test_transient_failure_then_success(self) -> None:
        links = load_script("check-links")
        response = MagicMock()
        response.__enter__.return_value.status = 200
        with patch.object(links, "urlopen", side_effect=[
            HTTPError("https://example.test", 503, "unavailable", {}, None), response,
        ]) as opener, patch.object(links.time, "sleep") as sleep:
            self.assertIsNone(links.archive_link_error("https://example.test"))
            self.assertEqual(opener.call_count, 2)
            sleep.assert_called_once_with(1)

    def test_missing_destination_is_not_retried(self) -> None:
        links = load_script("check-links")
        with patch.object(links, "urlopen", side_effect=HTTPError(
            "https://example.test", 404, "missing", {}, None,
        )) as opener, patch.object(links.time, "sleep") as sleep:
            self.assertEqual(links.archive_link_error("https://example.test"), "HTTP 404")
            self.assertEqual(opener.call_count, 1)
            sleep.assert_not_called()

    def test_persistent_failure_remains_blocking_and_bounded(self) -> None:
        links = load_script("check-links")
        for failure in (TimeoutError("timeout"), HTTPError(
            "https://example.test", 503, "unavailable", {}, None,
        )):
            with self.subTest(failure=str(failure)), patch.object(
                links, "urlopen", side_effect=failure,
            ) as opener, patch.object(links.time, "sleep") as sleep:
                self.assertIsNotNone(links.archive_link_error("https://example.test"))
                self.assertEqual(opener.call_count, 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])


class PublicPageBoundaryTests(unittest.TestCase):
    def test_active_html_scanners_are_registered_and_boundary_checked(self) -> None:
        registry = public_page_boundary.HTML_SCANNER_REGISTRY
        self.assertTrue(registry)

        candidates = set()
        # The active script directory is scanned one level only; archived
        # historical tools are intentionally outside this inventory.
        for path in SCRIPTS.iterdir():
            if (
                not path.is_file()
                or path.name.startswith("test-")
                or path.name == "public_page_boundary.py"
                or path.suffix not in {".py", ".js", ".mjs"}
            ):
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            if discovers_html_by_source_pattern(source):
                candidates.add(path.name)
        self.assertEqual(
            candidates,
            set(registry),
            "new or removed HTML discovery scripts must update the scanner registry",
        )

        active_scripts = {
            name
            for name in re.findall(
                r"^\| `([^`]+)` \| active \|",
                (SCRIPTS / "README.md").read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        }
        self.assertTrue(
            set(registry) <= active_scripts,
            f"registry entries must be documented as active: {set(registry) - active_scripts}",
        )
        for scanner, policy in registry.items():
            source = (SCRIPTS / scanner).read_text(encoding="utf-8")
            if policy.startswith("shared"):
                self.assertRegex(
                    source,
                    r"iter_public_html_files|is_public_page_path",
                    f"{scanner} claims the shared policy but does not use it",
                )
            elif policy == "exception: source-project-detail-inventory":
                self.assertIn("site-src/pages", source)
                self.assertIn("index.main.html", source)
                exception_test = ROOT / "tests" / "test-project-status.py"
                self.assertTrue(exception_test.is_file())
                test_source = exception_test.read_text(encoding="utf-8")
                self.assertIn("scripts/project-status.py", test_source)
                self.assertIn("test_missing_detail", test_source)
            elif policy == "exception: unpublished-locale-scaffold-inventory":
                self.assertIn('if is_unpublished:', source)
                self.assertIn("locale_dir = root / locale", source)
                self.assertIn('locale_dir.rglob("*.html")', source)
                exception_test = ROOT / "scripts" / "test-seo-fixtures.py"
                test_source = exception_test.read_text(encoding="utf-8")
                self.assertIn(
                    "test_unpublished_locale_rejects_undeclared_generated_target_page",
                    test_source,
                )
                self.assertIn(
                    "unpublished scaffold contains undeclared target page:",
                    test_source,
                )
            else:
                self.fail(f"{scanner} has an unnamed or unsupported policy: {policy}")

        readme = (SCRIPTS / "README.md").read_text(encoding="utf-8")
        registry_rows = re.findall(
            r"^\| `([^`]+)` \| ([^|]+) \|",
            readme.split("### Active HTML scanner registry", 1)[-1].split("\n### ", 1)[0],
            re.MULTILINE,
        )
        self.assertEqual(
            dict(registry_rows),
            registry,
            "README scanner inventory must match the executable registry",
        )

    def test_scanner_detection_catches_assembled_html_but_not_other_inventories(self) -> None:
        html_bypasses = (
            'pattern = "*." + "html"\nroot.glob(pattern)\n',
            'extension = "html"\nroot.glob("*." + extension)\n',
            'extension = "html"\nif path.suffix == "." + extension:\n    scan(path)\n',
            'extension = "html"\nif path.name.endswith("." + extension):\n    scan(path)\n',
            'const extension = "html";\nglob("**/*." + extension);\n',
            'const extension = "html";\nglob(`**/*.${extension}`);\n',
            'pattern = "*.{}".format("html")\nroot.glob(pattern)\n',
            'suffix = "." + "html"\nif path.suffix == suffix:\n    scan(path)\n',
            'pattern = "*.html"\nroot.glob(pattern)\n',
        )
        for source in html_bypasses:
            with self.subTest(source=source):
                self.assertTrue(discovers_html_by_source_pattern(source))

        non_html_inventories = (
            'for path in root.rglob("*.json"):\n    load(path)\n',
            'extension = "json"\nif path.suffix == "." + extension:\n    load(path)\n',
            'for path in root.glob("*.png"):\n    optimize(path)\n',
            'for path in root.rglob("*"):\n    if path.suffix in {".png", ".woff2"}:\n        process(path)\n',
            'for directory, names, files in os.walk(root):\n    inspect_json(files)\n',
        )
        for source in non_html_inventories:
            with self.subTest(source=source):
                self.assertFalse(discovers_html_by_source_pattern(source))

    def test_active_workflows_do_not_inline_discover_html_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workflow-html-inventory-") as directory:
            workflows = Path(directory)
            archived = workflows / "archive"
            archived.mkdir()
            (workflows / "active.yml").write_text(
                "steps:\n"
                "  - run: |\n"
                "      find . -type f -name '*.html' -print\n",
                encoding="utf-8",
            )
            (workflows / "assets.yaml").write_text(
                "steps:\n"
                "  - run: |\n"
                "      find assets -type f -name '*.json' -print\n",
                encoding="utf-8",
            )
            (workflows / "glob.yml").write_text(
                "steps:\n"
                "  - run: |\n"
                "      for page in **/*.html; do echo \"$page\"; done\n",
                encoding="utf-8",
            )
            (archived / "old.yml").write_text(
                "steps:\n"
                "  - run: |\n"
                "      git ls-files '*.html'\n",
                encoding="utf-8",
            )

            files = active_workflow_files(workflows)
            self.assertEqual(
                {path.name for path in files},
                {"active.yml", "assets.yaml", "glob.yml"},
            )
            active_discoveries = [
                (path.name, command)
                for path in files
                for command in workflow_run_commands(
                    path.read_text(encoding="utf-8")
                )
                if discovers_html_by_source_pattern(command)
            ]
            self.assertEqual(
                {path for path, _ in active_discoveries},
                {"active.yml", "glob.yml"},
            )

        candidates = [
            f"{path.relative_to(ROOT).as_posix()} run command"
            for path in active_workflow_files(ROOT / ".github" / "workflows")
            for command in workflow_run_commands(path.read_text(encoding="utf-8"))
            if discovers_html_by_source_pattern(command)
        ]
        self.assertEqual(
            candidates,
            [],
            "active workflows must delegate HTML discovery to a registered script "
            "or add a documented, tested exception",
        )

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

    def test_voice_locale_profiles_are_separate_from_en_us_baseline(self) -> None:
        voice = load_script("lint-voice")
        with tempfile.TemporaryDirectory(prefix="voice-locale-boundary-") as directory:
            root = Path(directory).resolve()
            fixtures = {
                "index.html": "<main><p>Please utilize the current method.</p></main>",
                "en-gb/about/index.html": (
                    "<main><p>Our favorite color is gray; a neighbor is traveling.</p></main>"
                ),
                "es-mx/about/index.html": (
                    "<main><p>Vosotros usáis el ordenador.</p></main>"
                ),
                "fr/about/index.html": "<main><p>Our favorite color is gray.</p></main>",
                "i18n/pilot/es-mx/reviewed/index.html": (
                    "<main><p>Vosotros usáis el ordenador.</p></main>"
                ),
            }
            for relative, content in fixtures.items():
                page = root / relative
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text(content, encoding="utf-8")

            with patch.object(voice, "ROOT", root):
                en_us_paths = {path.relative_to(root).as_posix() for path in voice.find_html_files(root)}
                en_gb_paths = {
                    path.relative_to(root).as_posix()
                    for path in voice.find_locale_html_files("en-gb", root)
                }
                es_mx_paths = {
                    path.relative_to(root).as_posix()
                    for path in voice.find_locale_html_files("es-mx", root)
                }
                self.assertEqual(en_us_paths, {"index.html", "fr/about/index.html"})
                self.assertEqual(en_gb_paths, {"en-gb/about/index.html"})
                self.assertEqual(es_mx_paths, {"es-mx/about/index.html"})

                en_us_findings = voice.lint_file(root / "index.html")
                en_gb_findings = voice.lint_locale_file(
                    root / "en-gb/about/index.html", "en-gb"
                )
                es_mx_findings = voice.lint_locale_file(
                    root / "es-mx/about/index.html", "es-mx"
                )
                self.assertEqual({finding.label for finding in en_us_findings}, {"utilize"})
                self.assertEqual(
                    {finding.label for finding in en_gb_findings},
                    {"US spelling: favorite", "US spelling: color", "US spelling: gray", "US spelling: neighbor", "US spelling: traveling"},
                )
                self.assertEqual(
                    {finding.label for finding in es_mx_findings},
                    {"Spain Spanish: vosotros", "Spain Spanish: ordenador"},
                )

                with tempfile.TemporaryDirectory(prefix="voice-locale-baseline-") as baseline_dir:
                    baseline_path = Path(baseline_dir) / "baseline.json"
                    voice.write_baseline(
                        baseline_path,
                        en_us_findings,
                        {"en-gb": en_gb_findings, "es-mx": es_mx_findings},
                    )
                    self.assertEqual(
                        voice.load_baseline(baseline_path),
                        Counter(finding.identity for finding in en_us_findings),
                    )
                    self.assertEqual(
                        voice.load_locale_baselines(baseline_path),
                        {
                            "en-gb": Counter(f.identity for f in en_gb_findings),
                            "es-mx": Counter(f.identity for f in es_mx_findings),
                        },
                    )

        baseline_path = SCRIPTS / "voice-lint-baseline.json"
        self.assertEqual(
            set(voice.load_locale_baselines(baseline_path)),
            {"en-gb", "es-mx"},
            "the reviewed baseline must keep both locale profiles independent",
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

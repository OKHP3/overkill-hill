#!/usr/bin/env python3
"""Focused regressions for the live-edge verifier and merge hook behavior."""

from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import shlex
import sys
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location(
    "verify_live_edge", ROOT / "scripts" / "verify-live-edge.py"
)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load scripts/verify-live-edge.py")
verify_live_edge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_live_edge)

ASSET_FORMAT_CASES: dict[str, tuple[str, tuple[str, ...]]] = {
    "image": (
        "/assets/img/favicons/murderbird-v2-icon-browser-32.png",
        ("image/png",),
    ),
    "svg": ("/assets/img/live-edge-fixture.svg", ("image/svg+xml",)),
    "ico": (
        "/assets/img/live-edge-fixture.ico",
        ("image/x-icon", "image/vnd.microsoft.icon"),
    ),
    "font": ("/assets/fonts/live-edge-fixture.woff2", ("font/woff2",)),
    "woff": ("/assets/fonts/live-edge-fixture.woff", ("font/woff",)),
    "ttf": ("/assets/fonts/live-edge-fixture.ttf", ("font/ttf",)),
    "otf": ("/assets/fonts/live-edge-fixture.otf", ("font/otf",)),
    "eot": (
        "/assets/fonts/live-edge-fixture.eot",
        ("application/vnd.ms-fontobject",),
    ),
}


class VerifyLiveEdgeTests(unittest.TestCase):
    def run_live_edge_fixture(
        self,
        *,
        expected_commit: str | None = None,
        manifest_commit: str = "a" * 40,
        manifest_body: bytes | None = None,
        manifest_content_type: str | None = "application/json",
        hosting_headers: dict[str, str] | None = None,
        asset_fingerprint: str | None = None,
        include_asset_fingerprint: bool = True,
        asset_kind: str = "css",
        asset_kinds: tuple[str, ...] | None = None,
        stale_asset_kind: str | None = None,
        asset_content_type: str | None = None,
        asset_content_types: dict[str, str | None] | None = None,
        asset_body: bytes | None = None,
        sitemap_content_type: str | None = "application/xml",
        search_index_content_type: str | None = "application/json",
        feed_content_type: str | None = "application/xml",
        css_asset_kinds: tuple[str, ...] = (),
        javascript_modules: dict[str, bytes] | None = None,
        javascript_module_content_types: dict[str, str | None] | None = None,
        javascript_response_overrides: dict[str, bytes] | None = None,
        javascript_missing_paths: set[str] | None = None,
        inline_module_source: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        """Run the full verifier against deterministic synthetic edge responses."""
        javascript_modules = javascript_modules or {}
        javascript_module_content_types = javascript_module_content_types or {}
        javascript_response_overrides = javascript_response_overrides or {}
        javascript_missing_paths = javascript_missing_paths or set()
        sitemap = verify_live_edge.canonical_text_bytes(verify_live_edge.SITEMAP)
        search_index = verify_live_edge.canonical_text_bytes(verify_live_edge.SEARCH_INDEX)
        feed = verify_live_edge.canonical_text_bytes(verify_live_edge.ATOM_FEED)
        manifest = manifest_body
        if manifest is None:
            manifest = json.dumps(
                {
                    "commit": manifest_commit,
                    "artifacts": {
                        "/feed.xml": {"sha256": hashlib.sha256(feed).hexdigest()},
                        "/sitemap.xml": {"sha256": hashlib.sha256(sitemap).hexdigest()},
                        "/assets/data/search-index.json": {
                            "sha256": hashlib.sha256(search_index).hexdigest()
                        },
                    },
                }
            ).encode("utf-8")
        html_headers = {
            "content-type": "text/html; charset=utf-8",
            "cache-control": "max-age=600",
            "server": "GitHub.com",
            "x-github-edge-region": "iad",
            "x-github-request-id": "fixture-request",
            "x-fastly-request-id": "fixture-fastly",
        }
        html_headers.update(hosting_headers or {})
        asset_catalog = {
            "css": {
                "path": "/assets/css/theme.css",
                "reference": '<link href="{url}" rel="stylesheet">',
                "content_type": "text/css",
            },
            "js": {
                "path": "/assets/js/app.js",
                "reference": '<script src="{url}"></script>',
                "content_type": "text/javascript",
            },
            "module": {
                "path": "/assets/js/mermaid-init.js",
                "reference": '<script src="{url}" type="module"></script>',
                "content_type": "text/javascript",
            },
            "image": {
                "path": ASSET_FORMAT_CASES["image"][0],
                "reference": '<img src="{url}" alt="fixture image">',
                "content_type": "image/png",
            },
            "font": {
                "path": ASSET_FORMAT_CASES["font"][0],
                "reference": '<link href="{url}" rel="preload" as="font">',
                "content_type": "font/woff2",
                "body": b"live-edge fixture font",
            },
            "svg": {
                "path": ASSET_FORMAT_CASES["svg"][0],
                "reference": '<img src="{url}" alt="fixture SVG image">',
                "content_type": "image/svg+xml",
                "body": b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            },
            "ico": {
                "path": ASSET_FORMAT_CASES["ico"][0],
                "reference": '<link rel="icon" href="{url}">',
                "content_type": "image/x-icon",
                "body": b"live-edge fixture icon",
            },
            "woff": {
                "path": ASSET_FORMAT_CASES["woff"][0],
                "reference": '<link href="{url}" rel="preload" as="font">',
                "content_type": "font/woff",
                "body": b"live-edge fixture WOFF font",
            },
            "ttf": {
                "path": ASSET_FORMAT_CASES["ttf"][0],
                "reference": '<link href="{url}" rel="preload" as="font">',
                "content_type": "font/ttf",
                "body": b"live-edge fixture TTF font",
            },
            "otf": {
                "path": ASSET_FORMAT_CASES["otf"][0],
                "reference": '<link href="{url}" rel="preload" as="font">',
                "content_type": "font/otf",
                "body": b"live-edge fixture OTF font",
            },
            "eot": {
                "path": ASSET_FORMAT_CASES["eot"][0],
                "reference": '<link href="{url}" rel="preload" as="font">',
                "content_type": "application/vnd.ms-fontobject",
                "body": b"live-edge fixture EOT font",
            },
            "css-fixture": {
                "path": "/assets/css/live-edge-fixture.css",
                "reference": '<link href="{url}" rel="stylesheet">',
                "content_type": "text/css",
            },
        }
        if javascript_modules:
            module_entry_path = next(iter(javascript_modules))
            if (
                not module_entry_path.startswith("/assets/")
                or verify_live_edge.urllib.parse.urlsplit(module_entry_path).query
                or Path(module_entry_path).suffix.lower()
                not in verify_live_edge.JAVASCRIPT_SUFFIXES
            ):
                raise ValueError("JavaScript module fixture keys must be query-free JS asset paths")
            asset_catalog["module-graph"] = {
                "path": module_entry_path,
                "reference": '<script src="{url}" type="module"></script>',
                "content_type": "text/javascript",
            }
        selected_kinds = (asset_kind,) if asset_kinds is None else asset_kinds
        all_kinds = (*selected_kinds, *css_asset_kinds)
        if not selected_kinds or any(kind not in asset_catalog for kind in all_kinds):
            raise ValueError(f"unsupported fixture asset kinds: {selected_kinds}")
        if css_asset_kinds and "css-fixture" not in selected_kinds:
            raise ValueError("CSS fixture dependencies require the css-fixture asset")
        if stale_asset_kind is not None and stale_asset_kind not in all_kinds:
            raise ValueError(f"stale asset kind is not rendered: {stale_asset_kind}")
        if stale_asset_kind is not None and asset_body is None:
            raise ValueError("stale_asset_kind requires asset_body")
        if asset_body is not None and len(all_kinds) > 1 and stale_asset_kind is None:
            raise ValueError(
                "stale_asset_kind is required when asset_body is supplied for "
                "multiple rendered assets"
            )
        asset_content_types = asset_content_types or {}
        if any(kind not in all_kinds for kind in asset_content_types):
            raise ValueError("content type override is for an unselected asset kind")

        def build_asset(kind: str) -> dict[str, object]:
            asset_details = dict(asset_catalog[kind])
            if kind in asset_content_types:
                asset_details["content_type"] = asset_content_types[kind]
            elif asset_content_type is not None and len(selected_kinds) == 1:
                asset_details["content_type"] = asset_content_type
            asset_path = asset_details["path"]
            asset_bytes = (
                javascript_modules[asset_path]
                if kind == "module-graph"
                else asset_details.pop("body", None)
            )
            if asset_bytes is None:
                asset_bytes = verify_live_edge.canonical_text_bytes(ROOT / asset_path.lstrip("/"))
            asset_hash = asset_fingerprint or hashlib.sha256(asset_bytes).hexdigest()[:8]
            asset_query = f"?v={asset_hash}" if include_asset_fingerprint else ""
            return {
                "kind": kind,
                "details": asset_details,
                "bytes": asset_bytes,
                "url": f"{asset_path}{asset_query}",
            }

        css_assets = [build_asset(kind) for kind in css_asset_kinds]
        if css_assets:
            dependency_rules = []
            for asset in css_assets:
                dependency_rules.append(
                    f'.fixture {{ background-image: url("{asset["url"]}"); }}'
                )
            asset_catalog["css-fixture"]["body"] = "\n".join(dependency_rules).encode("utf-8")
        assets = [build_asset(kind) for kind in selected_kinds]
        all_assets = assets + css_assets

        html = (
            '<!doctype html><meta name="robots" content="{robots}">'
            + "".join(
                asset["details"]["reference"].format(url=asset["url"])
                for asset in assets
            )
            + (
                f'<script type="module">{inline_module_source}</script>'
                if inline_module_source is not None
                else ""
            )
        )
        manifest_headers = (
            {"content-type": manifest_content_type}
            if manifest_content_type is not None
            else {}
        )
        sitemap_headers = {"cache-control": "max-age=600"}
        if sitemap_content_type is not None:
            sitemap_headers["content-type"] = sitemap_content_type
        search_index_headers = {"cache-control": "max-age=300"}
        if search_index_content_type is not None:
            search_index_headers["content-type"] = search_index_content_type
        feed_headers = {"cache-control": "max-age=600"}
        if feed_content_type is not None:
            feed_headers["content-type"] = feed_content_type
        responses = {
            verify_live_edge.RELEASE_MANIFEST: {
                "ok": True,
                "status": 200,
                "headers": manifest_headers,
                "body": manifest,
            },
            "/sitemap.xml": {
                "ok": True,
                "status": 200,
                "headers": sitemap_headers,
                "body": sitemap,
            },
            "/feed.xml": {
                "ok": True,
                "status": 200,
                "headers": feed_headers,
                "body": feed,
            },
            "/assets/data/search-index.json": {
                "ok": True,
                "status": 200,
                "headers": search_index_headers,
                "body": search_index,
            },
            "/": {
                "ok": True,
                "status": 200,
                "headers": html_headers,
                "body": html.replace("{robots}", "index, follow").encode("utf-8"),
            },
            "/404.html": {
                "ok": True,
                "status": 200,
                "headers": html_headers,
                "body": html.replace("{robots}", "noindex").encode("utf-8"),
            },
            "/found-ry/": {
                "ok": True,
                "status": 200,
                "headers": html_headers,
                "body": html.replace("{robots}", "noindex").encode("utf-8"),
            },
        }
        for asset in all_assets:
            asset_headers = {"cache-control": "max-age=31536000, immutable"}
            if asset["details"]["content_type"] is not None:
                asset_headers["content-type"] = asset["details"]["content_type"]
            responses[asset["url"]] = {
                "ok": True,
                "status": 200,
                "headers": asset_headers,
                "body": (
                    asset_body
                    if asset_body is not None
                    and (stale_asset_kind is None or stale_asset_kind == asset["kind"])
                    else asset["bytes"]
                ),
            }

        for module_path, module_source in javascript_modules.items():
            module_headers = {"cache-control": "max-age=31536000, immutable"}
            content_type = javascript_module_content_types.get(
                module_path, "text/javascript"
            )
            if content_type is not None:
                module_headers["content-type"] = content_type
            responses[module_path] = {
                "ok": True,
                "status": 200,
                "headers": module_headers,
                "body": module_source,
            }
        for response_url, response_body in javascript_response_overrides.items():
            module_path = verify_live_edge.urllib.parse.urlsplit(response_url).path
            if module_path not in responses:
                raise ValueError(
                    f"JavaScript response override has no source module: {response_url}"
                )
            overridden = dict(responses[module_path])
            overridden["body"] = response_body
            responses[response_url] = overridden

        # The fixture serves the real canonical theme CSS for fingerprint tests.
        # Include its self-hosted font dependencies in the synthetic response set.
        # Explicit fixture responses still control negative MIME/status cases.
        for font in (ROOT / "assets/fonts").glob("*.woff2"):
            responses.setdefault("/" + font.relative_to(ROOT).as_posix(), {
                "ok": True,
                "status": 200,
                "headers": {"content-type": "font/woff2", "cache-control": "max-age=600"},
                "body": font.read_bytes(),
            })

        if "module" in all_kinds and not javascript_modules:
            for module_file in (ROOT / "assets/vendor/mermaid").rglob("*.mjs"):
                responses.setdefault(
                    "/" + module_file.relative_to(ROOT).as_posix(),
                    {
                        "ok": True,
                        "status": 200,
                        "headers": {
                            "content-type": "text/javascript",
                            "cache-control": "max-age=31536000, immutable",
                        },
                        "body": module_file.read_bytes(),
                    },
                )

        request_counts: dict[str, int] = {}
        guarded_redirect_paths: set[str] = set()

        def fixture_fetch(
            _base: str,
            path: str,
            _timeout: float,
            max_bytes: int | None = None,
            same_origin_redirects_only: bool = False,
        ) -> dict[str, object]:
            request_counts[path] = request_counts.get(path, 0) + 1
            if same_origin_redirects_only:
                guarded_redirect_paths.add(path)
            try:
                response_key = (
                    path
                    if path in responses
                    else verify_live_edge.urllib.parse.urlsplit(path).path
                )
                response = dict(responses[response_key])
            except KeyError as exc:
                missing_path = verify_live_edge.urllib.parse.urlsplit(path).path
                if missing_path in javascript_missing_paths:
                    return {
                        "ok": False,
                        "status": 404,
                        "headers": {"content-type": "text/html"},
                        "body": b"not found",
                        "error": "HTTP Error 404: Not Found",
                    }
                raise AssertionError(f"fixture did not define a response for {path}") from exc
            if max_bytes is not None:
                body = response["body"]
                response["truncated"] = len(body) > max_bytes
                response["body"] = body[:max_bytes]
            return response

        argv = [
            "verify-live-edge.py",
            "--base",
            "https://fixture.example",
            "--hosting",
            "github-pages",
            "--accept-blocked",
        ]
        if expected_commit:
            argv.extend(["--expected-commit", expected_commit])
        with tempfile.TemporaryDirectory(prefix="live-edge-fixture-") as directory:
            report_path = Path(directory) / "report.json"
            fixture_root = ROOT
            if javascript_modules:
                fixture_root = Path(directory) / "site"
                for module_path, module_source in javascript_modules.items():
                    local_path = fixture_root / module_path.lstrip("/")
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(module_source)
            argv.extend(["--report", str(report_path)])
            output = io.StringIO()
            with (
                patch.object(verify_live_edge, "fetch", side_effect=fixture_fetch),
                patch.object(verify_live_edge, "load_routes", return_value=(["/"], None)),
                patch.object(verify_live_edge, "ROOT", fixture_root),
                patch.object(sys, "argv", argv),
                redirect_stdout(output),
            ):
                return_code = verify_live_edge.main()
            self.last_fixture_requests = request_counts
            self.last_fixture_guarded_redirect_paths = guarded_redirect_paths
            return return_code, json.loads(report_path.read_text(encoding="utf-8"))

    def test_literal_javascript_import_parser_ignores_non_code_and_computed_imports(self) -> None:
        source = r'''
// import "./comment.mjs";
const text = 'import("./string.mjs")';
import { value } from "./static.mjs";
export * from "./reexport.mjs";
void import("./dynamic.mjs");
import(variable);
import(variable || import("./nested-dynamic.mjs"));
import.meta.resolve("./meta.mjs");
const expression = /import\(["']\.\/regex\.mjs["']\)/;
'''
        imports, exceeded = verify_live_edge.extract_javascript_imports(source)

        self.assertFalse(exceeded)
        self.assertEqual(
            imports,
            [
                "./static.mjs",
                "./reexport.mjs",
                "./dynamic.mjs",
                "./nested-dynamic.mjs",
            ],
        )
        self.assertIsNone(
            verify_live_edge.resolve_javascript_import(
                "https://fixture.example",
                "/assets/js/entry.mjs",
                "https://external.example/not-followed.mjs",
            )
        )
        self.assertIsNone(
            verify_live_edge.resolve_javascript_import(
                "https://fixture.example",
                "/assets/js/entry.mjs",
                "bare-package",
            )
        )

    def test_javascript_import_limit_is_explicit(self) -> None:
        imports, exceeded = verify_live_edge.extract_javascript_imports(
            'import("./one.mjs"); import("./two.mjs");',
            max_imports=1,
        )

        self.assertEqual(imports, ["./one.mjs"])
        self.assertTrue(exceeded)

    def test_javascript_import_scanner_covers_templates_comments_options_and_regexes(self) -> None:
        source = "\n".join(
            [
                r'const template = `${await import("./template-real.mjs")}`;',
                r'const nestedText = `${`import("./nested-template-fake.mjs")`}`;',
                r'await import("./outer.mjs", { with: { type: (await import("./options-real.mjs")).type } });',
                '// import("./comment-cr-fake.mjs");\r import("./after-cr.mjs");',
                '// import("./comment-ls-fake.mjs");\u2028 import("./after-ls.mjs");',
                '// import("./comment-ps-fake.mjs");\u2029 import("./after-ps.mjs");',
                r'if (value) /import\("\.\/regex-if-fake\.mjs"\)/.test(text);',
                r'value + /import\("\.\/regex-plus-fake\.mjs"\)/.test(text);',
                r'if (value) { /import\("\.\/regex-block-body-fake\.mjs"\)/.test(text); }',
                r'if (value) {} /import\("\.\/regex-after-block-fake\.mjs"\)/.test(text);',
                'import "./after-regex.mjs";',
            ]
        )

        imports, issue = verify_live_edge.extract_javascript_imports(source)

        self.assertIsNone(issue)
        self.assertEqual(
            imports,
            [
                "./template-real.mjs",
                "./outer.mjs",
                "./options-real.mjs",
                "./after-cr.mjs",
                "./after-ls.mjs",
                "./after-ps.mjs",
                "./after-regex.mjs",
            ],
        )

    def test_statement_and_xor_regex_text_never_fetches_fake_modules(self) -> None:
        for statement in (
            r'if (value) {} else /import(".\/fake.mjs")/.test(text);',
            r'do /import(".\/fake.mjs")/.test(text); while (value);',
            r'const result = value ^ /import(".\/fake.mjs")/.test(text);',
            r'value ^= /import(".\/fake.mjs")/.test(text);',
        ):
            with self.subTest(statement=statement):
                source = statement + '\nimport "./real.mjs";'
                imports, issue = verify_live_edge.extract_javascript_imports(source)
                self.assertIsNone(issue)
                self.assertEqual(imports, ["./real.mjs"])
                modules = {
                    "/assets/js/fixture-entry.mjs": source.encode("utf-8"),
                    "/assets/js/real.mjs": b"export const real = true;\n",
                }
                return_code, report = self.run_live_edge_fixture(
                    asset_kind="module-graph",
                    javascript_modules=modules,
                )
                self.assertEqual(return_code, 0)
                self.assertNotIn("/assets/js/fake.mjs", self.last_fixture_requests)
                self.assertEqual(self.last_fixture_requests["/assets/js/real.mjs"], 1)
                checks = {item["check"]: item for item in report["checks"]}
                self.assertEqual(checks["asset /assets/js/real.mjs"]["status"], "PASS")

    def test_ambiguous_slash_after_brace_blocks_instead_of_claiming_full_coverage(self) -> None:
        imports, issue = verify_live_edge.extract_javascript_imports(
            'class Example {} /import("./regex-fake.mjs")/.test(text); '
            'import "./later-real.mjs";'
        )

        self.assertEqual(imports, [])
        self.assertIn("slash after an ambiguous brace", issue or "")

    def test_incomplete_template_scan_is_blocked_and_cannot_pass_accept_blocked(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": (
                b'const unresolved = `${await import("./before-error.mjs")}`;\n'
                b'const malformed = `${await import("./after-error.mjs")`;\n'
            ),
            "/assets/js/before-error.mjs": b"export const before = true;\n",
            "/assets/js/after-error.mjs": b"export const after = true;\n",
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "PARTIAL")
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["asset /assets/js/before-error.mjs"]["status"], "PASS")
        scan_check = checks["JavaScript imports /assets/js/fixture-entry.mjs"]
        self.assertEqual(scan_check["status"], "BLOCKED")
        self.assertIn("unterminated template", scan_check["evidence"])
        self.assertEqual(checks["asset /assets/js/after-error.mjs"]["status"], "PASS")
        self.assertEqual(self.last_fixture_requests["/assets/js/after-error.mjs"], 1)

    def test_dynamic_import_options_do_not_hide_missing_nested_dependencies(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": (
                b'const template = `${await import("./missing-template.mjs")}`;\n'
                b'const nestedText = `${`import("./nested-template-fake.mjs")`}`;\n'
                b'await import("./real-options.mjs", { with: { type: '
                b'(await import("./missing-options.mjs")).type } });\n'
                b'if (value) /import\\("\\.\\/regex-fake.mjs"\\)/.test(text);\n'
            ),
            "/assets/js/real-options.mjs": b"export const options = true;\n",
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
            javascript_missing_paths={
                "/assets/js/missing-template.mjs",
                "/assets/js/missing-options.mjs",
            },
        )

        self.assertEqual(return_code, 1)
        checks = {item["check"]: item for item in report["checks"]}
        for path in (
            "/assets/js/missing-template.mjs",
            "/assets/js/missing-options.mjs",
        ):
            self.assertEqual(checks[f"asset {path}"]["status"], "FAIL")
            self.assertEqual(self.last_fixture_requests[path], 1)
        self.assertEqual(checks["asset /assets/js/real-options.mjs"]["status"], "PASS")
        self.assertNotIn(
            "/assets/js/nested-template-fake.mjs",
            self.last_fixture_requests,
        )
        self.assertNotIn("/assets/js/regex-fake.mjs", self.last_fixture_requests)
        guarded_paths = {
            verify_live_edge.urllib.parse.urlsplit(path).path
            for path in self.last_fixture_guarded_redirect_paths
        }
        self.assertTrue(
            {
                "/assets/js/fixture-entry.mjs",
                "/assets/js/real-options.mjs",
                "/assets/js/missing-template.mjs",
                "/assets/js/missing-options.mjs",
            }.issubset(guarded_paths)
        )

    def test_query_free_imported_js_is_mime_and_sha_checked_without_entrypoint_rule(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": b'import "./plain.js";\n',
            "/assets/js/plain.js": b"export const plain = true;\n",
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
        )

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(
            checks["asset /assets/js/plain.js content type"]["status"],
            "PASS",
        )
        self.assertEqual(checks["asset /assets/js/plain.js"]["status"], "PASS")
        self.assertIn("/assets/js/plain.js", self.last_fixture_requests)
        self.assertNotIn("/assets/js/plain.js?v=", self.last_fixture_requests)

    def test_query_free_imported_js_with_stale_bytes_fails_sha_check(self) -> None:
        current = b"export const version = 'current';\n"
        modules = {
            "/assets/js/fixture-entry.mjs": b'import "./plain.js";\n',
            "/assets/js/plain.js": current,
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
            javascript_response_overrides={
                "/assets/js/plain.js": b"export const version = 'stale';\n"
            },
        )

        self.assertEqual(return_code, 1)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(
            checks["asset /assets/js/plain.js content type"]["status"],
            "PASS",
        )
        self.assertEqual(checks["asset /assets/js/plain.js"]["status"], "FAIL")
        self.assertIn("differs from local", checks["asset /assets/js/plain.js"]["evidence"])

    def test_dependency_redirect_handler_rejects_cross_origin_before_following(self) -> None:
        handler = verify_live_edge._SameOriginRedirectHandler()
        request = verify_live_edge.urllib.request.Request(
            "https://fixture.example/assets/js/entry.mjs"
        )

        with self.assertRaises(verify_live_edge.urllib.error.HTTPError) as raised:
            handler.redirect_request(
                request,
                io.BytesIO(),
                302,
                "Found",
                {},
                "https://external.example/redirected.mjs",
            )

        self.assertIn("cross-origin redirect rejected", str(raised.exception))
        same_origin = handler.redirect_request(
            request,
            io.BytesIO(),
            302,
            "Found",
            {},
            "https://fixture.example/assets/js/redirected.mjs",
        )
        self.assertEqual(
            same_origin.full_url,
            "https://fixture.example/assets/js/redirected.mjs",
        )

    def test_redirect_guard_is_opt_in_so_route_fetch_policy_stays_unchanged(self) -> None:
        class FixtureResponse(io.BytesIO):
            status = 200
            headers = {"Content-Type": "text/html"}

            def geturl(self) -> str:
                return "https://fixture.example/"

        response = FixtureResponse(b"page")
        with (
            patch.object(
                verify_live_edge.urllib.request,
                "urlopen",
                return_value=response,
            ) as standard_open,
            patch.object(
                verify_live_edge.urllib.request,
                "build_opener",
            ) as guarded_open,
        ):
            fetched = verify_live_edge.fetch("https://fixture.example", "/")

        self.assertTrue(fetched["ok"])
        standard_open.assert_called_once()
        guarded_open.assert_not_called()

    def test_javascript_source_fetch_is_byte_bounded(self) -> None:
        class FixtureResponse(io.BytesIO):
            status = 200
            headers = {"Content-Type": "text/javascript"}

            def geturl(self) -> str:
                return "https://fixture.example/assets/js/large.mjs"

        with patch.object(
            verify_live_edge.urllib.request,
            "urlopen",
            return_value=FixtureResponse(b"0123456789"),
        ):
            response = verify_live_edge.fetch(
                "https://fixture.example",
                "/assets/js/large.mjs",
                max_bytes=4,
            )

        self.assertEqual(response["body"], b"0123")
        self.assertTrue(response["truncated"])

    def test_module_count_limit_is_reported_without_fetching_extra_modules(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": (
                b'import "./first.mjs"; import "./second.mjs";\n'
            ),
            "/assets/js/first.mjs": b"export const first = true;\n",
            "/assets/js/second.mjs": b"export const second = true;\n",
        }
        with patch.object(verify_live_edge, "MAX_JS_MODULES", 2):
            return_code, report = self.run_live_edge_fixture(
                asset_kind="module-graph",
                javascript_modules=modules,
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertNotIn("/assets/js/second.mjs", self.last_fixture_requests)
        limit_check = next(
            item
            for item in report["checks"]
            if item["check"] == "JavaScript dependency discovery"
        )
        self.assertEqual(limit_check["status"], "BLOCKED")
        self.assertIn("2 JavaScript assets", limit_check["evidence"])

    def test_graph_source_budget_caps_download_and_blocks_unseen_imports(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": b'import "./child.mjs";\n',
            "/assets/js/child.mjs": b"export const child = true;\n",
        }
        with (
            patch.object(verify_live_edge, "MAX_JS_SOURCE_BYTES", 1024),
            patch.object(verify_live_edge, "MAX_JS_GRAPH_SOURCE_BYTES", 16),
        ):
            return_code, report = self.run_live_edge_fixture(
                asset_kind="module-graph",
                javascript_modules=modules,
            )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertNotIn("/assets/js/child.mjs", self.last_fixture_requests)
        checks = {item["check"]: item for item in report["checks"]}
        entry_check = checks["asset /assets/js/fixture-entry.mjs"]
        self.assertEqual(entry_check["status"], "BLOCKED")
        self.assertIn("remaining 16-byte graph budget", entry_check["evidence"])

    def test_static_dynamic_relative_and_vendor_modules_are_discovered(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": (
                b'''// import "./comment-only.mjs";
const text = 'import("./string-only.mjs")';
import { shared } from "./nested/static.mjs";
void import("./dynamic.mjs");
import "/assets/vendor/fixture/vendor-entry.mjs";
import("https://external.example/not-followed.mjs");
import(bareSpecifier);
'''
            ),
            "/assets/js/nested/static.mjs": (
                b'export { shared } from "../shared/common.mjs";\n'
            ),
            "/assets/js/shared/common.mjs": b"export const shared = true;\n",
            "/assets/js/dynamic.mjs": b"export const loaded = true;\n",
            "/assets/vendor/fixture/vendor-entry.mjs": (
                b"export const vendored = true;\n"
            ),
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
        )

        self.assertEqual(return_code, 0)
        self.assertEqual(report["summary"]["failures"], 0)
        checks = {item["check"]: item for item in report["checks"]}
        for path in (
            "/assets/js/nested/static.mjs",
            "/assets/js/shared/common.mjs",
            "/assets/js/dynamic.mjs",
            "/assets/vendor/fixture/vendor-entry.mjs",
        ):
            self.assertEqual(checks[f"asset {path}"]["status"], "PASS")
        self.assertNotIn(
            "https://external.example/not-followed.mjs",
            self.last_fixture_requests,
        )
        self.assertNotIn("/assets/js/comment-only.mjs", self.last_fixture_requests)
        self.assertNotIn("/assets/js/string-only.mjs", self.last_fixture_requests)
        self.assertNotIn("/assets/js/bareSpecifier", self.last_fixture_requests)

    def test_relative_import_cycle_fetches_each_dependency_once(self) -> None:
        modules = {
            "/assets/js/cycle-entry.mjs": b'import "./cycle/a.mjs";\n',
            "/assets/js/cycle/a.mjs": b'import "./b.mjs";\n',
            "/assets/js/cycle/b.mjs": b'import "./a.mjs";\n',
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
        )

        self.assertEqual(return_code, 0)
        self.assertEqual(self.last_fixture_requests["/assets/js/cycle/a.mjs"], 1)
        self.assertEqual(self.last_fixture_requests["/assets/js/cycle/b.mjs"], 1)
        checks = [item["check"] for item in report["checks"]]
        self.assertEqual(checks.count("asset /assets/js/cycle/a.mjs"), 1)
        self.assertEqual(checks.count("asset /assets/js/cycle/b.mjs"), 1)

    def test_inline_module_import_resolves_from_the_page_route(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": b"export const entry = true;\n",
            "/assets/js/inline-child.mjs": b"export const child = true;\n",
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
            inline_module_source=(
                'import "/assets/js/inline-child.mjs"; '
                'const fake = `${`import("/assets/js/inline-fake.mjs")`}`;'
            ),
        )

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["asset /assets/js/inline-child.mjs"]["status"], "PASS")
        self.assertNotIn("/assets/js/inline-fake.mjs", self.last_fixture_requests)
        self.assertEqual(
            self.last_fixture_requests["/assets/js/inline-child.mjs"],
            1,
        )

    def test_stale_fingerprinted_imported_module_fails(self) -> None:
        dependency = b"export const version = 'current';\n"
        fingerprint = hashlib.sha256(dependency).hexdigest()[:8]
        stale_body = b"export const version = 'stale';\n"
        modules = {
            "/assets/js/fixture-entry.mjs": (
                f'import("./stale.mjs?v={fingerprint}");\n'.encode()
            ),
            "/assets/js/stale.mjs": dependency,
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
            javascript_response_overrides={
                f"/assets/js/stale.mjs?v={fingerprint}": stale_body
            },
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        stale_check = checks["asset /assets/js/stale.mjs"]
        self.assertEqual(stale_check["status"], "FAIL")
        self.assertIn("!= live", stale_check["evidence"])

    def test_imported_module_with_wrong_mime_fails_explicitly(self) -> None:
        modules = {
            "/assets/js/fixture-entry.mjs": b'import "./wrong-type.mjs";\n',
            "/assets/js/wrong-type.mjs": b"export const value = true;\n",
        }
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module-graph",
            javascript_modules=modules,
            javascript_module_content_types={
                "/assets/js/wrong-type.mjs": "text/html"
            },
        )

        self.assertEqual(return_code, 1)
        checks = {item["check"]: item for item in report["checks"]}
        mime_check = checks["asset /assets/js/wrong-type.mjs content type"]
        self.assertEqual(mime_check["status"], "FAIL")
        self.assertIn("text/html", mime_check["evidence"])
        self.assertIn("text/javascript", mime_check["evidence"])

    def test_mixed_asset_stale_body_requires_explicit_target(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "stale_asset_kind is required when asset_body is supplied for multiple rendered assets",
        ):
            self.run_live_edge_fixture(
                asset_kinds=("css", "js"),
                asset_body=b"stale mixed asset",
            )

        with self.assertRaisesRegex(
            ValueError,
            "stale_asset_kind is required when asset_body is supplied for multiple rendered assets",
        ):
            self.run_live_edge_fixture(
                asset_kind="css-fixture",
                css_asset_kinds=("image", "font"),
                asset_body=b"stale dependency asset",
            )

    def test_stale_asset_selection_must_match_a_rendered_asset(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"unsupported fixture asset kinds: \(\)",
        ):
            self.run_live_edge_fixture(asset_kinds=())

        with self.assertRaisesRegex(
            ValueError,
            "stale asset kind is not rendered: module",
        ):
            self.run_live_edge_fixture(
                asset_kinds=("css", "js"),
                stale_asset_kind="module",
                asset_body=b"stale asset",
            )

        with self.assertRaisesRegex(ValueError, "stale_asset_kind requires asset_body"):
            self.run_live_edge_fixture(stale_asset_kind="css")

    def test_direct_github_pages_limitations_are_partial_not_failures(self) -> None:
        return_code, report = self.run_live_edge_fixture()

        self.assertEqual(return_code, 0)
        self.assertEqual(report["status"], "PARTIAL")
        self.assertEqual(report["summary"]["failures"], 0)
        self.assertGreater(report["summary"]["blocked"], 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["hosting path"]["status"], "PASS")
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_mismatched_release_manifest_fails_despite_pages_limitations(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            expected_commit="b" * 40,
            manifest_commit="c" * 40,
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        self.assertGreater(report["summary"]["failures"], 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["release manifest"]["status"], "FAIL")
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_invalid_release_manifest_json_fails_before_artifact_comparison(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            expected_commit="b" * 40,
            manifest_body=b'{"commit":',
            manifest_content_type="application/json",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["release manifest content type"]["status"], "PASS")
        release_manifest = checks["release manifest"]
        self.assertEqual(release_manifest["status"], "FAIL")
        self.assertIn("invalid JSON:", release_manifest["evidence"])
        self.assertNotIn("expected validated commit", release_manifest["evidence"])
        self.assertNotIn("SHA-256", release_manifest["evidence"])
        self.assertFalse(any(name.startswith("release manifest /") for name in checks))
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_non_object_release_manifest_json_fails_before_artifact_comparison(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            expected_commit="b" * 40,
            manifest_body=b"[]",
            manifest_content_type="application/json",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["release manifest content type"]["status"], "PASS")
        release_manifest = checks["release manifest"]
        self.assertEqual(release_manifest["status"], "FAIL")
        self.assertIn("expected a JSON object", release_manifest["evidence"])
        self.assertNotIn("expected validated commit", release_manifest["evidence"])
        self.assertNotIn("SHA-256", release_manifest["evidence"])
        self.assertFalse(any(name.startswith("release manifest /") for name in checks))
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_wrong_release_manifest_content_type_fails_before_json_parsing(self) -> None:
        for content_type in ("text/html; charset=utf-8", None):
            with self.subTest(content_type=content_type):
                return_code, report = self.run_live_edge_fixture(
                    manifest_content_type=content_type,
                )

                self.assertEqual(return_code, 1)
                self.assertEqual(report["status"], "FAILED")
                checks = {item["check"]: item for item in report["checks"]}
                content_type_check = checks["release manifest content type"]
                self.assertEqual(content_type_check["status"], "FAIL")
                self.assertIn("application/json", content_type_check["evidence"])
                if content_type is not None:
                    self.assertIn(content_type, content_type_check["evidence"])
                else:
                    self.assertIn("received ''", content_type_check["evidence"])
                self.assertNotIn("release manifest", checks)

    def test_release_manifest_accepts_parameterized_json_content_type(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            manifest_content_type="application/json; charset=utf-8",
        )

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["release manifest content type"]["status"], "PASS")
        self.assertEqual(checks["release manifest"]["status"], "PASS")
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_wrong_asset_fingerprint_still_fails(self) -> None:
        return_code, report = self.run_live_edge_fixture(asset_fingerprint="00000000")
        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        asset_check = checks["asset /assets/css/theme.css"]
        self.assertEqual(asset_check["status"], "FAIL")
        self.assertIn("!= local", asset_check["evidence"])
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_missing_asset_fingerprint_fails_despite_pages_limitations(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            include_asset_fingerprint=False
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        asset_check = checks["asset /assets/css/theme.css"]
        self.assertEqual(asset_check["status"], "FAIL")
        self.assertIn("missing 8-character", asset_check["evidence"])
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_missing_module_fingerprint_fails_despite_pages_limitations(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module",
            include_asset_fingerprint=False,
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        module_check = checks["asset /assets/js/mermaid-init.js"]
        self.assertEqual(module_check["status"], "FAIL")
        self.assertIn("missing 8-character ?v= fingerprint", module_check["evidence"])
        self.assertNotIn("asset /assets/js/app.js", checks)
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_changed_asset_response_fails_despite_pages_limitations(self) -> None:
        css_bytes = verify_live_edge.canonical_text_bytes(ROOT / "assets/css/theme.css")
        return_code, report = self.run_live_edge_fixture(
            asset_body=css_bytes + b"\n/* stale live asset */\n"
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        asset_check = checks["asset /assets/css/theme.css"]
        self.assertEqual(asset_check["status"], "FAIL")
        self.assertIn("!= live", asset_check["evidence"])
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_changed_javascript_asset_response_fails_despite_pages_limitations(self) -> None:
        js_bytes = verify_live_edge.canonical_text_bytes(ROOT / "assets/js/app.js")
        return_code, report = self.run_live_edge_fixture(
            asset_kind="js",
            asset_body=js_bytes + b"\n// stale live asset\n",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        asset_check = checks["asset /assets/js/app.js"]
        self.assertEqual(asset_check["status"], "FAIL")
        self.assertIn("!= live", asset_check["evidence"])
        self.assertNotIn("asset /assets/js/mermaid-init.js", checks)
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_changed_module_javascript_asset_response_fails_despite_pages_limitations(self) -> None:
        module_bytes = verify_live_edge.canonical_text_bytes(ROOT / "assets/js/mermaid-init.js")
        return_code, report = self.run_live_edge_fixture(
            asset_kind="module",
            asset_body=module_bytes + b"\n// stale live module asset\n",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        asset_check = checks["asset /assets/js/mermaid-init.js"]
        self.assertEqual(asset_check["status"], "FAIL")
        self.assertIn("!= live", asset_check["evidence"])
        self.assertNotIn("asset /assets/js/app.js", checks)
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_mixed_assets_report_stale_css_as_named_failure(self) -> None:
        css_bytes = verify_live_edge.canonical_text_bytes(ROOT / "assets/css/theme.css")
        return_code, report = self.run_live_edge_fixture(
            asset_kinds=("css", "js"),
            stale_asset_kind="css",
            asset_body=css_bytes + b"\n/* stale mixed-page stylesheet */\n",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["asset /assets/css/theme.css"]["status"], "FAIL")
        self.assertIn("!= live", checks["asset /assets/css/theme.css"]["evidence"])
        self.assertEqual(checks["asset /assets/js/app.js"]["status"], "BLOCKED")
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_mixed_assets_report_stale_javascript_as_named_failure(self) -> None:
        js_bytes = verify_live_edge.canonical_text_bytes(ROOT / "assets/js/app.js")
        return_code, report = self.run_live_edge_fixture(
            asset_kinds=("css", "js"),
            stale_asset_kind="js",
            asset_body=js_bytes + b"\n// stale mixed-page script\n",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["asset /assets/css/theme.css"]["status"], "BLOCKED")
        self.assertEqual(checks["asset /assets/js/app.js"]["status"], "FAIL")
        self.assertIn("!= live", checks["asset /assets/js/app.js"]["evidence"])
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_mixed_css_javascript_and_module_reports_stale_module(self) -> None:
        module_bytes = verify_live_edge.canonical_text_bytes(
            ROOT / "assets/js/mermaid-init.js"
        )
        return_code, report = self.run_live_edge_fixture(
            asset_kinds=("css", "js", "module"),
            stale_asset_kind="module",
            asset_body=module_bytes + b"\n// stale mixed-page module\n",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["asset /assets/css/theme.css"]["status"], "BLOCKED")
        self.assertEqual(checks["asset /assets/js/app.js"]["status"], "BLOCKED")
        module_check = checks["asset /assets/js/mermaid-init.js"]
        self.assertEqual(module_check["status"], "FAIL")
        self.assertIn("!= live", module_check["evidence"])
        self.assertEqual(
            checks["asset /assets/css/theme.css content type"]["status"],
            "PASS",
        )
        self.assertEqual(
            checks["asset /assets/js/app.js content type"]["status"],
            "PASS",
        )
        self.assertEqual(
            checks["asset /assets/js/mermaid-init.js content type"]["status"],
            "PASS",
        )
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_css_dependency_stale_body_only_changes_selected_asset(self) -> None:
        image_bytes = verify_live_edge.canonical_text_bytes(
            ROOT / "assets/img/favicons/murderbird-v2-icon-browser-32.png"
        )
        return_code, report = self.run_live_edge_fixture(
            asset_kind="css-fixture",
            css_asset_kinds=("image", "font"),
            stale_asset_kind="image",
            asset_body=image_bytes + b"\n/* stale image fixture */\n",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        image_check = checks[
            "asset /assets/img/favicons/murderbird-v2-icon-browser-32.png"
        ]
        self.assertEqual(image_check["status"], "FAIL")
        self.assertIn("!= live", image_check["evidence"])
        self.assertEqual(checks["asset /assets/fonts/live-edge-fixture.woff2"]["status"], "BLOCKED")
        self.assertEqual(checks["asset /assets/css/live-edge-fixture.css"]["status"], "BLOCKED")
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_wrong_css_content_type_fails_with_explicit_mime_evidence(self) -> None:
        return_code, report = self.run_live_edge_fixture(asset_content_type="text/html")

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks["asset /assets/css/theme.css content type"]
        self.assertEqual(content_type_check["status"], "FAIL")
        self.assertIn("text/html", content_type_check["evidence"])
        self.assertIn("text/css", content_type_check["evidence"])
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_wrong_javascript_content_type_fails_with_explicit_mime_evidence(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="js",
            asset_content_type="text/css",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks["asset /assets/js/app.js content type"]
        self.assertEqual(content_type_check["status"], "FAIL")
        self.assertIn("text/css", content_type_check["evidence"])
        self.assertIn("application/javascript", content_type_check["evidence"])
        self.assertIn("text/javascript", content_type_check["evidence"])
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_wrong_module_content_type_fails_with_explicit_mime_evidence(self) -> None:
        for content_type in ("text/css", "text/html"):
            with self.subTest(content_type=content_type):
                return_code, report = self.run_live_edge_fixture(
                    asset_kind="module",
                    asset_content_type=content_type,
                )

                self.assertEqual(return_code, 1)
                self.assertEqual(report["status"], "FAILED")
                checks = {item["check"]: item for item in report["checks"]}
                content_type_check = checks[
                    "asset /assets/js/mermaid-init.js content type"
                ]
                self.assertEqual(content_type_check["status"], "FAIL")
                self.assertIn(content_type, content_type_check["evidence"])
                self.assertIn("application/javascript", content_type_check["evidence"])
                self.assertIn("text/javascript", content_type_check["evidence"])
                self.assertEqual(checks["asset /assets/js/mermaid-init.js"]["status"], "BLOCKED")
                self.assertNotIn("asset /assets/js/app.js", checks)
                self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_missing_or_blank_content_type_fails_for_each_script_entry_asset(self) -> None:
        asset_paths = {
            "css": "/assets/css/theme.css",
            "js": "/assets/js/app.js",
            "module": "/assets/js/mermaid-init.js",
        }
        expected_types = {
            "css": "text/css",
            "js": "text/javascript",
            "module": "text/javascript",
        }

        for kind, path in asset_paths.items():
            for header_state, content_type in (("absent", None), ("blank", "")):
                with self.subTest(kind=kind, header_state=header_state):
                    return_code, report = self.run_live_edge_fixture(
                        asset_kinds=("css", "js", "module"),
                        asset_content_types={kind: content_type},
                    )

                    self.assertEqual(return_code, 1)
                    self.assertEqual(report["status"], "FAILED")
                    checks = {item["check"]: item for item in report["checks"]}
                    content_type_check = checks[f"asset {path} content type"]
                    self.assertEqual(content_type_check["status"], "FAIL")
                    self.assertIn("received ''", content_type_check["evidence"])
                    self.assertIn(expected_types[kind], content_type_check["evidence"])

                    for unaffected_kind, unaffected_path in asset_paths.items():
                        if unaffected_kind == kind:
                            continue
                        unaffected_check = checks[
                            f"asset {unaffected_path} content type"
                        ]
                        self.assertEqual(unaffected_check["status"], "PASS")

                    # The fixture runs with --accept-blocked for Pages policies.
                    self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_module_accepts_explicit_javascript_media_types(self) -> None:
        for content_type in (
            "application/javascript; charset=utf-8",
            "text/javascript; charset=utf-8",
        ):
            with self.subTest(content_type=content_type):
                return_code, report = self.run_live_edge_fixture(
                    asset_kind="module",
                    asset_content_type=content_type,
                )

                self.assertEqual(return_code, 0)
                checks = {item["check"]: item for item in report["checks"]}
                content_type_check = checks[
                    "asset /assets/js/mermaid-init.js content type"
                ]
                self.assertEqual(content_type_check["status"], "PASS")
                self.assertEqual(checks["asset /assets/js/mermaid-init.js"]["status"], "BLOCKED")
                self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_javascript_content_type_with_parameters_is_accepted(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="js",
            asset_content_type="application/javascript; charset=utf-8",
        )

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks["asset /assets/js/app.js content type"]
        self.assertEqual(content_type_check["status"], "PASS")

    def test_wrong_image_content_type_fails_with_explicit_mime_evidence(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="image",
            asset_content_type="text/html",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks[
            "asset /assets/img/favicons/murderbird-v2-icon-browser-32.png content type"
        ]
        self.assertEqual(content_type_check["status"], "FAIL")
        self.assertIn("text/html", content_type_check["evidence"])
        self.assertIn("image/png", content_type_check["evidence"])

    def test_missing_html_discovered_image_and_font_content_types_fail_explicitly(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kinds=("image", "font"),
            asset_content_types={"image": None, "font": None},
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        image_check = checks[
            "asset /assets/img/favicons/murderbird-v2-icon-browser-32.png content type"
        ]
        font_check = checks["asset /assets/fonts/live-edge-fixture.woff2 content type"]
        self.assertEqual(image_check["status"], "FAIL")
        self.assertIn("received ''", image_check["evidence"])
        self.assertIn("image/png", image_check["evidence"])
        self.assertEqual(font_check["status"], "FAIL")
        self.assertIn("received ''", font_check["evidence"])
        self.assertIn("font/woff2", font_check["evidence"])

    def test_unfingerprinted_image_still_reports_wrong_content_type(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="image",
            include_asset_fingerprint=False,
            asset_content_type="text/html",
        )

        self.assertEqual(return_code, 1)
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks[
            "asset /assets/img/favicons/murderbird-v2-icon-browser-32.png content type"
        ]
        self.assertEqual(content_type_check["status"], "FAIL")
        self.assertIn("text/html", content_type_check["evidence"])

    def test_wrong_font_content_type_fails_with_explicit_mime_evidence(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="font",
            asset_content_type="text/plain",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks[
            "asset /assets/fonts/live-edge-fixture.woff2 content type"
        ]
        self.assertEqual(content_type_check["status"], "FAIL")
        self.assertIn("text/plain", content_type_check["evidence"])
        self.assertIn("font/woff2", content_type_check["evidence"])

    def test_css_discovered_image_and_font_content_types_fail_explicitly(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="css-fixture",
            css_asset_kinds=("image", "font"),
            asset_content_types={"image": "text/html", "font": "text/plain"},
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        image_check = checks[
            "asset /assets/img/favicons/murderbird-v2-icon-browser-32.png content type"
        ]
        font_check = checks["asset /assets/fonts/live-edge-fixture.woff2 content type"]
        self.assertEqual(image_check["status"], "FAIL")
        self.assertEqual(font_check["status"], "FAIL")
        self.assertIn("text/html", image_check["evidence"])
        self.assertIn("text/plain", font_check["evidence"])

    def test_missing_css_discovered_image_and_font_content_types_fail_explicitly(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kind="css-fixture",
            css_asset_kinds=("image", "font"),
            asset_content_types={"image": None, "font": None},
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        image_check = checks[
            "asset /assets/img/favicons/murderbird-v2-icon-browser-32.png content type"
        ]
        font_check = checks["asset /assets/fonts/live-edge-fixture.woff2 content type"]
        self.assertEqual(image_check["status"], "FAIL")
        self.assertIn("received ''", image_check["evidence"])
        self.assertIn("image/png", image_check["evidence"])
        self.assertEqual(font_check["status"], "FAIL")
        self.assertIn("received ''", font_check["evidence"])
        self.assertIn("font/woff2", font_check["evidence"])

    def test_image_and_font_content_types_with_parameters_are_accepted(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kinds=("image", "font"),
            asset_content_types={
                "image": "image/png; charset=binary",
                "font": "font/woff2; charset=utf-8",
            },
        )

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(
            checks[
                "asset /assets/img/favicons/murderbird-v2-icon-browser-32.png content type"
            ]["status"],
            "PASS",
        )
        self.assertEqual(
            checks["asset /assets/fonts/live-edge-fixture.woff2 content type"]["status"],
            "PASS",
        )

    def test_supported_icon_and_font_extensions_accept_expected_content_types(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            asset_kinds=tuple(ASSET_FORMAT_CASES),
        )

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        for kind, (path, accepted_types) in ASSET_FORMAT_CASES.items():
            with self.subTest(kind=kind):
                content_type_check = checks[f"asset {path} content type"]
                self.assertEqual(content_type_check["status"], "PASS")
                self.assertEqual(
                    content_type_check["accepted_content_types"],
                    sorted(accepted_types),
                )

    def test_both_ico_content_type_aliases_are_accepted(self) -> None:
        path, accepted_types = ASSET_FORMAT_CASES["ico"]
        for content_type in accepted_types:
            with self.subTest(content_type=content_type):
                return_code, report = self.run_live_edge_fixture(
                    asset_kind="ico",
                    asset_content_type=content_type,
                )

                self.assertEqual(return_code, 0)
                checks = {item["check"]: item for item in report["checks"]}
                content_type_check = checks[f"asset {path} content type"]
                self.assertEqual(content_type_check["status"], "PASS")
                self.assertEqual(
                    content_type_check["accepted_content_types"],
                    sorted(accepted_types),
                )

    def test_wrong_supported_icon_and_font_content_types_are_named_failures(self) -> None:
        asset_kinds = tuple(ASSET_FORMAT_CASES)
        return_code, report = self.run_live_edge_fixture(
            asset_kinds=asset_kinds,
            asset_content_types={kind: "text/plain" for kind in asset_kinds},
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        for kind, (path, accepted_types) in ASSET_FORMAT_CASES.items():
            with self.subTest(kind=kind):
                content_type_check = checks[f"asset {path} content type"]
                self.assertEqual(content_type_check["status"], "FAIL")
                self.assertIn("text/plain", content_type_check["evidence"])
                self.assertEqual(
                    content_type_check["accepted_content_types"],
                    sorted(accepted_types),
                )

    def test_wrong_sitemap_content_type_fails_with_explicit_mime_evidence(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            sitemap_content_type="text/html; charset=utf-8",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks["generated sitemap content type"]
        self.assertEqual(content_type_check["status"], "FAIL")
        self.assertIn("text/html", content_type_check["evidence"])
        self.assertIn("application/xml", content_type_check["evidence"])
        self.assertIn("text/xml", content_type_check["evidence"])

    def test_atom_feed_is_bound_to_the_release_manifest_and_live_bytes(self) -> None:
        return_code, report = self.run_live_edge_fixture()

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["release manifest /feed.xml"]["status"], "PASS")
        self.assertEqual(checks["generated Atom feed"]["status"], "PASS")
        self.assertEqual(
            checks["generated Atom feed content type"]["status"], "PASS"
        )

    def test_missing_feed_digest_fails_the_release_manifest_check(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            manifest_body=json.dumps(
                {"commit": "a" * 40, "artifacts": {}}
            ).encode("utf-8")
        )

        self.assertEqual(return_code, 1)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["release manifest /feed.xml"]["status"], "FAIL")

    def test_wrong_or_missing_atom_feed_content_type_fails_explicitly(self) -> None:
        for content_type in ("text/html; charset=utf-8", None):
            with self.subTest(content_type=content_type):
                return_code, report = self.run_live_edge_fixture(
                    feed_content_type=content_type,
                )

                self.assertEqual(return_code, 1)
                checks = {item["check"]: item for item in report["checks"]}
                content_type_check = checks["generated Atom feed content type"]
                self.assertEqual(content_type_check["status"], "FAIL")
                self.assertIn("application/atom+xml", content_type_check["evidence"])
                self.assertIn("application/xml", content_type_check["evidence"])
                self.assertIn("text/xml", content_type_check["evidence"])
                if content_type is None:
                    self.assertIn("received ''", content_type_check["evidence"])
                else:
                    self.assertIn(content_type, content_type_check["evidence"])

    def test_missing_data_feed_content_types_fail_explicitly(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            sitemap_content_type=None,
            search_index_content_type=None,
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        sitemap_check = checks["generated sitemap content type"]
        search_index_check = checks["generated search index content type"]
        self.assertEqual(sitemap_check["status"], "FAIL")
        self.assertIn("received ''", sitemap_check["evidence"])
        self.assertIn("application/xml", sitemap_check["evidence"])
        self.assertIn("text/xml", sitemap_check["evidence"])
        self.assertEqual(search_index_check["status"], "FAIL")
        self.assertIn("received ''", search_index_check["evidence"])
        self.assertIn("application/json", search_index_check["evidence"])

    def test_wrong_search_index_content_type_fails_with_explicit_mime_evidence(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            search_index_content_type="text/html; charset=utf-8",
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        content_type_check = checks["generated search index content type"]
        self.assertEqual(content_type_check["status"], "FAIL")
        self.assertIn("text/html", content_type_check["evidence"])
        self.assertIn("application/json", content_type_check["evidence"])

    def test_data_feed_content_types_with_parameters_are_accepted(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            feed_content_type="application/atom+xml; charset=utf-8",
            sitemap_content_type="application/xml; charset=utf-8",
            search_index_content_type="application/json; charset=utf-8",
        )

        self.assertEqual(return_code, 0)
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["generated sitemap content type"]["status"], "PASS")
        self.assertEqual(checks["generated search index content type"]["status"], "PASS")
        self.assertEqual(checks["generated Atom feed content type"]["status"], "PASS")

    def test_changed_hosting_path_fails_despite_pages_limitations(self) -> None:
        return_code, report = self.run_live_edge_fixture(
            hosting_headers={"server": "cloudflare", "cf-ray": "fixture-ray"}
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(report["status"], "FAILED")
        checks = {item["check"]: item for item in report["checks"]}
        self.assertEqual(checks["hosting path"]["status"], "FAIL")
        self.assertEqual(checks["route / cache policy"]["status"], "BLOCKED")

    def test_github_pages_missing_headers_are_explicit_warnings(self) -> None:
        report: list[dict[str, object]] = []
        response = {
            "ok": True,
            "headers": {},
        }

        verify_live_edge.check_headers(report, "route /", response, "github-pages")

        observed = {item["check"]: item for item in report}
        self.assertEqual(observed["route / observed header x-content-type-options"]["status"], "WARN")
        self.assertIn("absent", observed["route / observed header x-content-type-options"]["evidence"])
        self.assertEqual(observed["route / enforcing content-security-policy"]["status"], "WARN")

    def test_matching_enforcing_csp_is_observed_without_policy_claim(self) -> None:
        policy = "default-src 'self'"
        report: list[dict[str, object]] = []

        verify_live_edge.check_headers(
            report,
            "route /",
            {"ok": True, "headers": {"content-security-policy": policy}},
            "github-pages",
        )

        csp = next(item for item in report if "enforcing content-security-policy" in item["check"])
        self.assertEqual(csp["status"], "PASS")
        self.assertEqual(csp["value"], policy)
        self.assertIn("not validated", csp["evidence"])

    def test_wrong_security_header_value_remains_a_failure(self) -> None:
        report: list[dict[str, object]] = []

        verify_live_edge.check_headers(
            report,
            "route /",
            {"ok": True, "headers": {"x-frame-options": "ALLOWALL"}},
            "github-pages",
        )

        frame_check = next(item for item in report if "x-frame-options" in item["check"])
        self.assertEqual(frame_check["status"], "FAIL")

    def test_report_only_csp_is_not_enforcing(self) -> None:
        report: list[dict[str, object]] = []

        verify_live_edge.check_headers(
            report,
            "route /",
            {"ok": True, "headers": {"content-security-policy-report-only": "default-src 'self'"}},
            "github-pages",
        )

        enforcing = next(item for item in report if item["check"].endswith("enforcing content-security-policy"))
        report_only = next(item for item in report if "observed report-only" in item["check"])
        self.assertEqual(enforcing["status"], "WARN")
        self.assertEqual(report_only["status"], "WARN")
        self.assertIn("does not enforce", report_only["evidence"])

    def test_strict_hosting_still_treats_missing_headers_as_failures(self) -> None:
        report: list[dict[str, object]] = []

        verify_live_edge.check_headers(report, "route /", {"ok": True, "headers": {}}, "strict")

        failures = [item for item in report if item["status"] == "FAIL"]
        self.assertGreaterEqual(len(failures), len(verify_live_edge.SECURITY_HEADERS))


class PostMergeTests(unittest.TestCase):
    def run_post_merge_with_python_failure(self, failure_target: str) -> subprocess.CompletedProcess[bytes]:
        with tempfile.TemporaryDirectory(prefix="post-merge-") as temp:
            shim = Path(temp) / "python3"
            shim.write_bytes(
                (
                    "#!/bin/bash\n"
                    f"case \"$*\" in *{failure_target}*) exit 1;; *) exit 0;; esac\n"
                ).encode("utf-8")
            )
            shim.chmod(0o755)
            temp_path = Path(temp).resolve()
            if temp_path.drive:
                drive = temp_path.drive.rstrip(":").lower()
                windows_path = str(temp_path).replace("\\", "/")
                posix_temp = f"/mnt/{drive}{windows_path[2:]}"
            else:
                posix_temp = str(temp_path)
            command = (
                f"export PATH={shlex.quote(posix_temp)}:/usr/bin:/bin; "
                "source scripts/post-merge.sh"
            )
            return subprocess.run(
                ["bash", "-c", command],
                cwd=ROOT,
                capture_output=True,
            )

    def test_post_merge_stops_after_early_failed_subprocess(self) -> None:
        result = self.run_post_merge_with_python_failure("check-mtb-version.py")

        self.assertNotEqual(result.returncode, 0)
        output = (result.stderr + result.stdout).decode("utf-8", errors="replace")
        self.assertIn("ERROR: MTB version check failed", output)
        self.assertNotIn("Post-merge: all checks passed.", output)

    def test_post_merge_stops_after_final_validator_failure(self) -> None:
        result = self.run_post_merge_with_python_failure("validate-site.py")

        self.assertNotEqual(result.returncode, 0)
        output = (result.stderr + result.stdout).decode("utf-8", errors="replace")
        self.assertIn("ERROR: full site validation failed.", output)
        self.assertNotIn("Post-merge: all checks passed.", output)

    def test_post_merge_stops_when_featured_release_parity_fails(self) -> None:
        result = self.run_post_merge_with_python_failure("check-banner.py")

        self.assertNotEqual(result.returncode, 0)
        output = (result.stderr + result.stdout).decode("utf-8", errors="replace")
        self.assertIn(
            "ERROR: featured article source and generated output or site banners disagree.",
            output,
        )
        self.assertNotIn("Post-merge: all checks passed.", output)

    def test_post_merge_stops_after_link_check_failure(self) -> None:
        result = self.run_post_merge_with_python_failure("check-links.py")

        self.assertNotEqual(result.returncode, 0)
        output = (result.stderr + result.stdout).decode("utf-8", errors="replace")
        self.assertIn("ERROR: internal link check failed.", output)
        self.assertNotIn("Post-merge: all checks passed.", output)

    def test_post_merge_stops_after_canonical_audit_failure(self) -> None:
        result = self.run_post_merge_with_python_failure("audit-site.py")

        self.assertNotEqual(result.returncode, 0)
        output = (result.stderr + result.stdout).decode("utf-8", errors="replace")
        self.assertIn("ERROR: canonical site audit failed.", output)
        self.assertNotIn("Post-merge: all checks passed.", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)

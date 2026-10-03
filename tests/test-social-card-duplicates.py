import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate-site.py"
SPEC = importlib.util.spec_from_file_location("validate_site", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

LOCALE_SCRIPT = ROOT / "scripts" / "check-locale-links.py"
LOCALE_SPEC = importlib.util.spec_from_file_location("check_locale_links", LOCALE_SCRIPT)
LOCALE_MODULE = importlib.util.module_from_spec(LOCALE_SPEC)
assert LOCALE_SPEC.loader is not None
LOCALE_SPEC.loader.exec_module(LOCALE_MODULE)

SOCIAL_IMAGE = "https://overkillhill.com/assets/img/etch-ai-sketch-using-a-council-to-design-at-velocity.png"
CONFLICTING_SOCIAL_IMAGE = "https://example.test/conflicting-card.png"
SOCIAL_CARD_DUPLICATE_KEYS = (
    "og:image",
    "og:image:alt",
    "og:image:width",
    "og:image:height",
    "og:image:type",
    "twitter:image",
    "twitter:image:alt",
)
CONFLICTING_SOCIAL_VALUES = {
    "og:image": CONFLICTING_SOCIAL_IMAGE,
    "og:image:alt": "Conflicting fixture social preview",
    "og:image:width": "1200",
    "og:image:height": "630",
    "og:image:type": "image/jpeg",
    "twitter:image": CONFLICTING_SOCIAL_IMAGE,
    "twitter:image:alt": "Conflicting fixture social preview",
}


def social_card_tags(*, duplicate: str | None = None) -> str:
    fields = [
        ("og:image", f'<meta property="og:image" content="{SOCIAL_IMAGE}">'),
        ("og:image:alt", '<meta property="og:image:alt" content="Fixture social preview">'),
        ("og:image:width", '<meta property="og:image:width" content="1536">'),
        ("og:image:height", '<meta property="og:image:height" content="1024">'),
        ("og:image:type", '<meta property="og:image:type" content="image/png">'),
        ("twitter:image", f'<meta name="twitter:image" content="{SOCIAL_IMAGE}">'),
        ("twitter:image:alt", '<meta name="twitter:image:alt" content="Fixture social preview">'),
    ]
    duplicate_mode = duplicate
    duplicate_key = "og:image" if duplicate in {"conflict", "identical"} else duplicate
    if duplicate_key is not None:
        keys = [key for key, _ in fields]
        if duplicate_key not in keys:
            raise ValueError(f"unknown social-card duplicate key: {duplicate_key}")
        index = keys.index(duplicate_key)
        value = (
            SOCIAL_IMAGE
            if duplicate_mode == "identical"
            else CONFLICTING_SOCIAL_VALUES[duplicate_key]
        )
        if duplicate_key.startswith("og:"):
            prefix = f'property="{duplicate_key}"'
        else:
            prefix = f'name="{duplicate_key}"'
        duplicate_tag = f'<meta {prefix} content="{value}">'
        fields.insert(index + 1, (duplicate_key, duplicate_tag))
    tags = [tag for _, tag in fields]
    return "\n".join(tags)


def site_fixture_html(*, duplicate: str | None = None, noindex: bool = False) -> str:
    robots = "noindex, follow" if noindex else "index, follow"
    theme_url = MODULE.current_content_hashed_url("/assets/css/theme.css")
    app_url = MODULE.current_content_hashed_url("/assets/js/app.js")
    assert theme_url and app_url
    return f"""<!doctype html>
<html lang="en">
<head>
  <title>Fixture page</title>
  <meta name="description" content="Fixture page">
  <meta name="robots" content="{robots}">
  <link rel="canonical" href="https://overkillhill.com/fixture/">
  <link rel="stylesheet" href="{theme_url}">
  {social_card_tags(duplicate=duplicate)}
</head>
<body>
  <h1>Fixture page</h1>
  <script src="{app_url}"></script>
</body>
</html>
"""


def locale_fixture_html(
    *,
    route: str,
    locale: str,
    duplicate: str | None = None,
    noindex: bool = False,
) -> str:
    robots = "noindex, follow" if noindex else "index, follow"
    canonical = f"https://overkillhill.com{route}"
    alternate_source = "https://overkillhill.com/"
    return f"""<!doctype html>
<html lang="{locale}">
<head>
  <title>Locale fixture</title>
  <meta name="robots" content="{robots}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:url" content="{canonical}">
  <link rel="alternate" hreflang="{locale}" href="{canonical}">
  <link rel="alternate" hreflang="en" href="{alternate_source}">
  <link rel="alternate" hreflang="x-default" href="{alternate_source}">
  {social_card_tags(duplicate=duplicate)}
</head>
<body><h1>Locale fixture</h1></body>
</html>
"""


def source_fixture_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <link rel="canonical" href="https://overkillhill.com/">
  <meta property="og:url" content="https://overkillhill.com/">
  <link rel="alternate" hreflang="en" href="https://overkillhill.com/">
  <link rel="alternate" hreflang="fr" href="https://overkillhill.com/fr/">
  <link rel="alternate" hreflang="x-default" href="https://overkillhill.com/">
</head>
<body><h1>Source fixture</h1></body>
</html>
"""


class SocialCardDuplicateTests(unittest.TestCase):
    def test_conflicting_duplicate_reports_metadata_key_and_page(self):
        findings = MODULE.validate_duplicate_social_card_metadata(
            "fr/projects/index.html",
            {
                "og:image": ["https://example.test/old.png", "https://example.test/new.png"],
                "twitter:image": ["https://example.test/card.png"],
            },
        )

        self.assertEqual(1, len(findings))
        self.assertEqual("fr/projects/index.html", findings[0].page)
        self.assertIn("meta:og:image", findings[0].msg)
        self.assertIn("old.png", findings[0].msg)
        self.assertIn("new.png", findings[0].msg)

    def test_identical_duplicate_is_not_conflicting(self):
        findings = MODULE.validate_duplicate_social_card_metadata(
            "fr/projects/index.html",
            {
                "og:image": ["https://example.test/card.png"] * 2,
                "twitter:image:alt": ["Card description"] * 2,
            },
        )

        self.assertEqual([], findings)

    def test_noindex_locale_page_does_not_enter_social_card_contract(self):
        parser = MODULE.TagCounter()
        parser.feed(
            '<meta name="robots" content="noindex, follow">'
            '<meta property="og:image" content="https://example.test/old.png">'
            '<meta property="og:image" content="https://example.test/new.png">'
        )

        findings = MODULE.validate_generated_seo(
            ROOT / "de/projects/index.html",
            parser,
            None,
            {"indexable": False},
        )

        self.assertEqual([], findings)

    def _run_site_command(
        self,
        *,
        duplicate: str | None,
        noindex: bool,
    ) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".social-card-site-") as directory:
            page = Path(directory) / "index.html"
            page.write_text(site_fixture_html(duplicate=duplicate, noindex=noindex), encoding="utf-8")
            relative_page = page.relative_to(ROOT).as_posix()
            route = MODULE.html_to_route(page)
            manifest_page = {
                "path": relative_page,
                "route": route,
                "meta:robots": "noindex, follow" if noindex else "index, follow",
                "meta:og:image": SOCIAL_IMAGE,
                "meta:og:image:alt": "Fixture social preview",
                "meta:og:image:width": "1536",
                "meta:og:image:height": "1024",
                "meta:og:image:type": "image/png",
                "meta:twitter:image": SOCIAL_IMAGE,
                "meta:twitter:image:alt": "Fixture social preview",
            }
            locale_page = (
                {
                    "indexable": False,
                    "metadata_source": "localized-page",
                }
                if noindex
                else None
            )
            sitemap_url = MODULE.SITE_ORIGIN + route
            stdout = io.StringIO()
            stderr = io.StringIO()
            patches = [
                patch.object(MODULE, "find_html_files", return_value=[page]),
                patch.object(
                    MODULE,
                    "load_sitemap_entries",
                    return_value={} if noindex else {sitemap_url: None},
                ),
                patch.object(
                    MODULE,
                    "load_source_manifest",
                    return_value=([] if noindex else [manifest_page], []),
                ),
                patch.object(
                    MODULE,
                    "load_locale_seo_contract",
                    return_value=({relative_page: locale_page} if noindex else {}, []),
                ),
                patch.object(MODULE, "validate_source_seo_contract", return_value=[]),
                patch.object(MODULE, "validate_article_jsonld_source", return_value=[]),
                patch.object(MODULE, "validate_organization_source", return_value=[]),
                patch.object(MODULE, "validate_heat_guide_chain", return_value=[]),
                patch.object(MODULE, "validate_writing_release_alignment", return_value=[]),
                patch.object(MODULE, "validate_sitemap_inventory", return_value=[]),
                patch.object(MODULE, "validate_csp_hashes", return_value=[]),
                patch.object(MODULE, "validate_mermaid_runtime", return_value=[]),
                patch.object(MODULE, "validate_mermaid_version_pin", return_value=[]),
                patch.object(MODULE, "validate_mermaid_csp_alignment", return_value=[]),
                patch.object(MODULE, "validate_brand_theme_metadata", return_value=[]),
                patch.object(MODULE, "validate_organization_nodes", return_value=[]),
                patch.object(MODULE, "run_mtb_version_check", return_value=0),
                patch.object(MODULE, "run_banner_check", return_value=0),
                patch.object(MODULE, "run_voice_lint", return_value=0),
            ]
            for active_patch in patches:
                active_patch.start()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = MODULE.main()
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()
            return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_site_release_command_reports_conflicting_duplicate_page_and_key(self):
        for key in SOCIAL_CARD_DUPLICATE_KEYS:
            with self.subTest(key=key):
                exit_code, stdout, stderr = self._run_site_command(
                    duplicate=key,
                    noindex=False,
                )

                self.assertEqual(1, exit_code)
                output = stdout + stderr
                self.assertIn("index.html", output)
                self.assertIn(f"meta:{key}", output)
                self.assertIn("conflicting duplicate social-card metadata", output)

    def test_site_release_command_allows_identical_duplicates(self):
        exit_code, stdout, stderr = self._run_site_command(
            duplicate="identical",
            noindex=False,
        )

        self.assertEqual(0, exit_code, stdout + stderr)

    def test_site_release_command_exempts_noindex_pilot_duplicate(self):
        exit_code, stdout, stderr = self._run_site_command(
            duplicate="conflict",
            noindex=True,
        )

        self.assertEqual(0, exit_code, stdout + stderr)

    def _run_locale_command(
        self,
        *,
        duplicate: str | None,
        noindex: bool,
    ) -> tuple[int, str]:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".social-card-locale-") as directory:
            root = Path(directory)
            source = root / "index.html"
            target = root / "fr" / "index.html"
            source.parent.mkdir(parents=True, exist_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(source_fixture_html(), encoding="utf-8")
            target.write_text(
                locale_fixture_html(
                    route="/fr/",
                    locale="fr",
                    duplicate=duplicate,
                    noindex=noindex,
                ),
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "target_locale": "fr",
                        "indexable": not noindex,
                        "metadata_source": "localized-page",
                        "pages": [
                            {
                                "source_route": "/",
                                "target_route": "/fr/",
                                "source_path": source.relative_to(ROOT).as_posix(),
                                "target_path": target.relative_to(ROOT).as_posix(),
                                "indexable": not noindex,
                                "metadata_source": "localized-page",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            sitemap = root / "sitemap.xml"
            sitemap.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://overkillhill.com/</loc></url>
  {target}
</urlset>
""".format(target="" if noindex else "<url><loc>https://overkillhill.com/fr/</loc></url>"),
                encoding="utf-8",
            )
            search_index = root / "search-index.json"
            search_index.write_text(
                json.dumps(
                    {
                        "locale": "fr",
                        "count": 0 if noindex else 1,
                        "entries": [] if noindex else [{"url": "/fr/"}],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = LOCALE_MODULE.main(
                    [
                        "--manifest",
                        str(manifest),
                        "--sitemap",
                        str(sitemap),
                        "--search-index",
                        str(search_index),
                    ]
                )
            return exit_code, stdout.getvalue() + stderr.getvalue()

    def test_locale_release_command_reports_conflicting_duplicate_page_and_key(self):
        for key in SOCIAL_CARD_DUPLICATE_KEYS:
            with self.subTest(key=key):
                exit_code, output = self._run_locale_command(
                    duplicate=key,
                    noindex=False,
                )

                self.assertEqual(1, exit_code)
                self.assertIn("index.html", output)
                self.assertIn(f"meta:{key}", output)
                self.assertIn("conflicting duplicate social-card metadata", output)

    def test_locale_release_command_allows_identical_duplicates(self):
        exit_code, output = self._run_locale_command(
            duplicate="identical",
            noindex=False,
        )

        self.assertEqual(0, exit_code, output)

    def test_locale_release_command_exempts_noindex_pilot_duplicate(self):
        exit_code, output = self._run_locale_command(
            duplicate="conflict",
            noindex=True,
        )

        self.assertEqual(0, exit_code, output)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_VALIDATOR = ROOT / "scripts" / "validate-site.py"
LOCALE_CHECKER = ROOT / "scripts" / "check-locale-links.py"

HELPER_SCRIPTS = (
    "csp.py",
    "brand_theme.py",
    "public_page_boundary.py",
    "generate-theme-controls.py",
    "check-mtb-version.py",
    "check-banner.py",
    "lint-voice.py",
)

SOCIAL_IMAGE = (
    "https://overkillhill.com/assets/img/og/"
    "murderbird-v2-brand-share-1200x630.png"
)
SOCIAL_ALT = "Fixture social preview"


def hashed_url(path: Path, route: str) -> str:
    digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:8]
    return f"{route}?v={digest}"


def organization_json() -> str:
    return json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "@id": "https://overkillhill.com/#organization",
            "name": "OverKill Hill P³™",
            "url": "https://overkillhill.com/",
            "logo": {
                "@type": "ImageObject",
                "url": "https://overkillhill.com/assets/img/favicons/murderbird-v2-icon-1024.png",
                "width": 1024,
                "height": 1024,
            },
            "sameAs": [
                "https://www.linkedin.com/company/overkillhillp3",
                "https://facebook.com/OverKillHillP3/",
                "https://x.com/OverKillHillP3",
                "https://www.youtube.com/@OverKillHillP3",
                "https://ko-fi.com/overkillhillp3",
                "https://pro.fiverr.com/s/VYKPpoB",
            ],
        }
    )


def site_page(*, duplicate_social_image: bool = False) -> str:
    image_tags = (
        f'<meta property="og:image" content="{SOCIAL_IMAGE}">\n'
        + (
            f'  <meta property="og:image" content="https://example.test/old.png">\n'
            if duplicate_social_image
            else ""
        )
        + f'  <meta property="og:image:alt" content="{SOCIAL_ALT}">\n'
        '  <meta property="og:image:width" content="1200">\n'
        '  <meta property="og:image:height" content="630">\n'
        '  <meta property="og:image:type" content="image/png">\n'
        f'  <meta property="twitter:image" content="{SOCIAL_IMAGE}">\n'
        f'  <meta property="twitter:image:alt" content="{SOCIAL_ALT}">\n'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta name="description" content="A release entrypoint fixture.">
  <title>Release entrypoint fixture</title>
  <link rel="canonical" href="https://overkillhill.com/">
  <meta property="og:url" content="https://overkillhill.com/">
  <meta property="og:type" content="website">
{image_tags}  <script type="application/ld+json">{organization_json()}</script>
  <link rel="stylesheet" href="{hashed_url(THEME, "/assets/css/theme.css")}">
  <script src="{hashed_url(APP, "/assets/js/app.js")}"></script>
</head>
<body><h1>Release entrypoint fixture</h1><!-- G-VJ1BKXS27H --></body>
</html>
"""


def locale_page(*, duplicate_social_image: bool = False) -> str:
    image_tags = (
        f'  <meta property="og:image" content="{SOCIAL_IMAGE}">\n'
        + (
            '  <meta property="og:image" content="https://example.test/old.png">\n'
            if duplicate_social_image
            else ""
        )
        + f'  <meta property="og:image:alt" content="{SOCIAL_ALT}">\n'
        '  <meta property="og:image:width" content="1200">\n'
        '  <meta property="og:image:height" content="630">\n'
        '  <meta property="og:image:type" content="image/png">\n'
        f'  <meta property="twitter:image" content="{SOCIAL_IMAGE}">\n'
        f'  <meta property="twitter:image:alt" content="{SOCIAL_ALT}">\n'
    )
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta name="description" content="A localized release entrypoint fixture.">
  <title>Localized release entrypoint fixture</title>
  <link rel="canonical" href="https://overkillhill.com/fr/">
  <meta property="og:url" content="https://overkillhill.com/fr/">
  <link rel="alternate" hreflang="fr" href="https://overkillhill.com/fr/">
  <link rel="alternate" hreflang="en" href="https://overkillhill.com/">
  <link rel="alternate" hreflang="x-default" href="https://overkillhill.com/">
{image_tags}  <script type="application/ld+json">{organization_json()}</script>
</head>
<body><h1>Localized release entrypoint fixture</h1><!-- G-VJ1BKXS27H --></body>
</html>
"""


def release_alignment_page(label: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta name="description" content="A release alignment fixture.">
  <meta name="robots" content="noindex, follow">
  <title>Release alignment fixture</title>
  <link rel="canonical" href="https://overkillhill.com/">
  <link rel="stylesheet" href="{hashed_url(THEME, "/assets/css/theme.css")}">
  <script src="{hashed_url(APP, "/assets/js/app.js")}"></script>
  <script type="application/ld+json">{organization_json()}</script>
</head>
<body><h1>Release alignment fixture</h1><!-- G-VJ1BKXS27H -->
<span class="writing-card-kicker--featured">{label}</span>
</body>
</html>
"""


THEME = ROOT / "assets" / "css" / "theme.css"
APP = ROOT / "assets" / "js" / "app.js"


class ReleaseEntrypointSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="release-entrypoints-")
        self.fixture = Path(self.temp.name)
        (self.fixture / "scripts").mkdir()
        (self.fixture / "config").mkdir()
        (self.fixture / "assets" / "css").mkdir(parents=True)
        (self.fixture / "assets" / "js").mkdir(parents=True)
        (self.fixture / "assets" / "img" / "og").mkdir(parents=True)
        (self.fixture / "assets" / "partials").mkdir(parents=True)
        (self.fixture / "assets" / "vendor" / "mermaid").mkdir(parents=True)
        (self.fixture / "site-src").mkdir()
        (self.fixture / "i18n" / "pilot").mkdir(parents=True)

        shutil.copy2(SITE_VALIDATOR, self.fixture / "scripts" / SITE_VALIDATOR.name)
        shutil.copy2(LOCALE_CHECKER, self.fixture / "scripts" / LOCALE_CHECKER.name)
        for name in HELPER_SCRIPTS:
            shutil.copy2(ROOT / "scripts" / name, self.fixture / "scripts" / name)
        shutil.copy2(ROOT / "config" / "brand-theme-contract.json", self.fixture / "config" / "brand-theme-contract.json")
        shutil.copy2(THEME, self.fixture / "assets" / "css" / "theme.css")
        shutil.copy2(APP, self.fixture / "assets" / "js" / "app.js")
        shutil.copy2(
            ROOT / "assets" / "js" / "mermaid-init.js",
            self.fixture / "assets" / "js" / "mermaid-init.js",
        )
        shutil.copy2(
            ROOT / "assets" / "img" / "og" / "murderbird-v2-brand-share-1200x630.png",
            self.fixture / "assets" / "img" / "og" / "murderbird-v2-brand-share-1200x630.png",
        )
        shutil.copy2(ROOT / "assets" / "partials" / "head.html", self.fixture / "assets" / "partials" / "head.html")

        (self.fixture / "scripts" / "check-mtb-version.py").write_text(
            "print('fixture MTB check skipped')\n",
            encoding="utf-8",
        )
        (self.fixture / "scripts" / "check-banner.py").write_text(
            "print('fixture banner check skipped')\n",
            encoding="utf-8",
        )
        (self.fixture / "scripts" / "lint-voice.py").write_text(
            "print('fixture voice check skipped')\n",
            encoding="utf-8",
        )
        (self.fixture / "assets" / "vendor" / "mermaid" / "mermaid.esm.min.mjs").write_text(
            "// fixture Mermaid 1.2.3\n",
            encoding="utf-8",
        )
        (self.fixture / "assets" / "vendor" / "mermaid" / "VERSION").write_text(
            "1.2.3\n",
            encoding="utf-8",
        )
        self._write_site_contract()
        self._write_locale_fixture()
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=self.fixture,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "add", "index.html", "fr/index.html"],
            cwd=self.fixture,
            check=True,
            capture_output=True,
            text=True,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_site_contract(self) -> None:
        page_metadata = {
            "path": "index.html",
            "route": "/",
            "meta:robots": "index, follow",
            "meta:description": "A release entrypoint fixture.",
            "meta:og:type": "website",
            "meta:og:url": "https://overkillhill.com/",
            "meta:og:image": SOCIAL_IMAGE,
            "meta:og:image:alt": SOCIAL_ALT,
            "meta:og:image:width": "1200",
            "meta:og:image:height": "630",
            "meta:og:image:type": "image/png",
            "meta:twitter:image": SOCIAL_IMAGE,
            "meta:twitter:image:alt": SOCIAL_ALT,
        }
        pages = [page_metadata] + [
            {
                "path": "writings/index.html",
                "route": "/writings/",
                "meta:robots": "noindex, follow",
            },
            {
                "path": "writings/first-diagram-is-a-liar/index.html",
                "route": "/writings/first-diagram-is-a-liar/",
                "meta:robots": "noindex, follow",
            },
        ]
        (self.fixture / "site-src" / "pages.json").write_text(
            json.dumps({"pages": pages}),
            encoding="utf-8",
        )
        (self.fixture / "i18n" / "pilot" / "manifest.json").write_text(
            json.dumps({"locales": {}}),
            encoding="utf-8",
        )
        (self.fixture / "site-src" / "pages" / "writings").mkdir(parents=True)
        (self.fixture / "writings" / "first-diagram-is-a-liar").mkdir(parents=True)
        for path in (
            self.fixture / "site-src" / "pages" / "writings" / "index.main.html",
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '<span class="writing-card-kicker--featured">Article v1.0:</span>',
                encoding="utf-8",
            )
        for path in (
            self.fixture / "site-src" / "pages" / "writings" / "first-diagram-is-a-liar" / "index.main.html",
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<span>Article v1.0: Fixture article</span>", encoding="utf-8")
        (self.fixture / "writings" / "index.html").write_text(
            release_alignment_page("Article v1.0:"),
            encoding="utf-8",
        )
        (self.fixture / "writings" / "first-diagram-is-a-liar" / "index.html").write_text(
            release_alignment_page("Article v1.0: Fixture article"),
            encoding="utf-8",
        )
        (self.fixture / "index.html").write_text(site_page(), encoding="utf-8")
        (self.fixture / "sitemap.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://overkillhill.com/</loc></url>
</urlset>
""",
            encoding="utf-8",
        )

    def _write_locale_fixture(self) -> None:
        (self.fixture / "fr").mkdir()
        (self.fixture / "fr" / "index.html").write_text(
            locale_page(duplicate_social_image=True),
            encoding="utf-8",
        )
        manifest = {
            "target_locales": ["fr"],
            "locales": {
                "fr": {
                    "status": "published",
                    "indexable": True,
                    "metadata_source": "localized-page",
                    "pages": [
                        {
                            "source_route": "/",
                            "target_route": "/fr/",
                            "source_path": "index.html",
                            "target_path": "fr/index.html",
                            "indexable": True,
                            "metadata_source": "localized-page",
                        }
                    ],
                }
            },
        }
        (self.fixture / "locale-manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        (self.fixture / "locale-sitemap.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://overkillhill.com/</loc></url>
  <url><loc>https://overkillhill.com/fr/</loc></url>
</urlset>
""",
            encoding="utf-8",
        )
        (self.fixture / "search-index.fr.json").write_text(
            json.dumps({"locale": "fr", "count": 1, "entries": [{"url": "/fr/"}]}),
            encoding="utf-8",
        )

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["OKHP3_VALIDATION_ROOT"] = str(self.fixture)
        environment["PYTHONUTF8"] = "1"
        return environment

    def test_validate_site_wrapper_preserves_failure_status_and_format(self) -> None:
        shutil.rmtree(self.fixture / "fr")
        subprocess.run(
            ["git", "rm", "--cached", "--quiet", "fr/index.html"],
            cwd=self.fixture,
            check=True,
            capture_output=True,
            text=True,
        )
        page = self.fixture / "index.html"
        page.write_text(site_page(duplicate_social_image=True), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(self.fixture / "scripts" / "validate-site.py")],
            cwd=self.fixture,
            env=self._environment(),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        # Missing heat-guide routes are deliberate in this small fixture.
        # Check the wrapper format and the specific social metadata error.
        self.assertRegex(output, r"ERRORS \(\d+\):")
        self.assertIn("index.html: conflicting duplicate social-card metadata", output)
        self.assertIn("meta:og:image", output)
        self.assertRegex(output, r"\d+ error\(s\), 0 warning\(s\)\.")

    def test_locale_checker_wrapper_preserves_failure_status_and_format(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.fixture / "scripts" / "check-locale-links.py"),
                "--manifest",
                str(self.fixture / "locale-manifest.json"),
                "--sitemap",
                str(self.fixture / "locale-sitemap.xml"),
                "--search-index",
                str(self.fixture / "search-index.fr.json"),
            ],
            cwd=self.fixture,
            env=self._environment(),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertEqual("", result.stdout)
        self.assertIn("Locale link check failed:\n", result.stderr)
        self.assertIn("fr/index.html: conflicting duplicate social-card metadata", result.stderr)
        self.assertIn("meta:og:image", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)

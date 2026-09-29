#!/usr/bin/env python3
"""Check unreleased regional draft routes and their publication boundary."""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ("/", "/about/", "/projects/", "/contact/")
FAILURES: list[str] = []
CSP_META_RE = re.compile(
    rb'<meta\b(?=[^>]*\bhttp-equiv=["\']Content-Security-Policy["\'])[^>]*>',
    re.I,
)
ASSET_FINGERPRINT_RE = re.compile(
    rb'(\b(?:href|src)=["\'][^"\']*/assets/[^"\']*?)\?v=[0-9a-f]{8,64}(?=["\'])',
    re.I,
)


def fail(message: str) -> None:
    FAILURES.append(message)


def normalized_translation_source(content: bytes) -> bytes:
    """Remove generated release metadata before checking editorial freshness."""
    normalized = content.replace(b"\r\n", b"\n")
    normalized = CSP_META_RE.sub(b"", normalized)
    return ASSET_FINGERPRINT_RE.sub(rb"\1", normalized)


def main() -> int:
    builder = (ROOT / "scripts/build-locale-drafts.py").read_text(encoding="utf-8")
    if "ROOT / 'es'" in builder or 'ROOT / "es"' in builder:
        fail("builder must not use the Spain Spanish tree as an input")
    if "source_path = ROOT / rel" not in builder:
        fail("builder must open canonical en-US paths for both pairs")
    source_hashes = json.loads((ROOT / "i18n/pilot/source-hashes-murderbird-stills-2026-09-06.json").read_text(encoding="utf-8"))
    shell_release = source_hashes.get("current_release_shell", {})
    current_release = shell_release.get("release")
    current_release_hashes = shell_release.get("normalized_routes", {})
    article_source = (ROOT / "site-src/pages/writings/first-diagram-is-a-liar/index.main.html").read_text(encoding="utf-8")
    article_release = re.search(
        r'<div class="article-eyebrow"[^>]*>.*?Article\s+(v\d+(?:\.\d+)+)',
        article_source,
        re.I | re.S,
    )
    if not current_release or not article_release or article_release.group(1).lower() != current_release.lower():
        fail("current release-shell record does not match the featured article")
    for name in ("index.html", "about-index.html", "projects-index.html", "contact-index.html"):
        if not (ROOT / "i18n/pilot/es-mx/reviewed" / name).exists():
            fail(f"missing reviewed es-MX source artifact: {name}")
    manifest = json.loads((ROOT / "i18n/pilot/regional-drafts-manifest.json").read_text(encoding="utf-8"))
    for locale, expected_lang, label in (("en-gb", "en-GB", "English (UK) · Draft"), ("es-mx", "es-MX", "Español (México) · Borrador")):
        entry = manifest["locales"][locale]
        if entry["status"] != "ai-reviewed-draft":
            fail(f"{locale}: status is not AI-reviewed draft")
        for route in ROUTES:
            source_rel = "index.html" if route == "/" else route.strip("/") + "/index.html"
            source_path = ROOT / source_rel
            release_hash = current_release_hashes.get(route)
            if not release_hash:
                fail(f"{route}: missing current release-shell source hash")
            elif hashlib.sha256(normalized_translation_source(source_path.read_bytes())).hexdigest() != release_hash:
                fail(f"{route}: canonical source is stale relative to the recorded release revision")
            path = ROOT / locale / ("index.html" if route == "/" else route.strip("/") + "/index.html")
            if not path.exists():
                fail(f"{locale}: missing {path.relative_to(ROOT)}")
                continue
            text = path.read_text(encoding="utf-8")
            if f'<html lang="{expected_lang}">' not in text:
                fail(f"{path.relative_to(ROOT)}: wrong html lang")
            robot_tags = re.findall(r'<meta[^>]+>', text, re.I)
            if not any(re.search(r'name=["\']robots["\']', tag, re.I) and re.search(r'content=["\']noindex, follow', tag, re.I) for tag in robot_tags):
                fail(f"{path.relative_to(ROOT)}: missing noindex")
            if label not in text:
                fail(f"{path.relative_to(ROOT)}: missing visible draft label")
            expected_home = f'/{locale}/'
            nav_match = re.search(r'<div class="logo">.*?</div>', text, re.S)
            if nav_match is None or not re.search(rf'<a\b[^>]*\bhref="{re.escape(expected_home)}"', nav_match.group(0)):
                fail(f"{path.relative_to(ROOT)}: navigation logo does not return to its locale home")
            if nav_match is None or 'class="sr-only"' not in nav_match.group(0):
                fail(f"{path.relative_to(ROOT)}: navigation logo has no accessible home label")
            if '/assets/img/murderbird-v2-icon-nav-96.png' not in text:
                fail(f"{path.relative_to(ROOT)}: navigation logo does not use the current organization identity")
            if nav_match and 'loading="eager"' not in nav_match.group(0):
                fail(f"{path.relative_to(ROOT)}: navigation logo must declare eager loading")
            if '<link' in text and 'rel="alternate"' in text[: text.find("</head>")]:
                fail(f"{path.relative_to(ROOT)}: draft head exposes public alternate links")
            if locale == "en-gb" and 'stroke="#CE1124"' not in text:
                fail(f"{path.relative_to(ROOT)}: missing St George flag")
            if locale == "en-gb" and 'stroke="#CE1124"' in text and 'stroke="#CE1124" stroke-width="4"' not in text:
                fail(f"{path.relative_to(ROOT)}: St George flag is not the upright cross contract")
            if locale == "es-mx" and 'fill="#006847"' not in text:
                fail(f"{path.relative_to(ROOT)}: missing Mexico flag")
            if locale == "es-mx" and 'Mexico coat of arms' not in text:
                fail(f"{path.relative_to(ROOT)}: Mexico flag lacks its coat of arms")
            if locale == "es-mx" and 'Español (México) · Borrador</span>' not in text:
                fail(f"{path.relative_to(ROOT)}: missing visible Mexico draft label")
            if locale == "es-mx" and '/assets/css/theme.css' not in text:
                fail(f"{path.relative_to(ROOT)}: missing canonical heading-font resource")
            if locale == "es-mx" and 'class="site-specials site-specials--okh"' not in text:
                fail(f"{path.relative_to(ROOT)}: missing localized current forge notice")
            if locale == "es-mx" and f'data-banner-release="{current_release}"' not in text:
                fail(f"{path.relative_to(ROOT)}: localized forge notice lacks its release marker")
            if locale == "es-mx" and 'property="og:locale" content="es_MX"' not in text:
                fail(f"{path.relative_to(ROOT)}: incorrect regional Open Graph locale")
            source_text = source_path.read_text(encoding="utf-8")
            for element in ("h1", "h2", "h3", "article", "figure", "img"):
                if len(re.findall(rf"<{element}\b", source_text, re.I)) != len(re.findall(rf"<{element}\b", text, re.I)):
                    fail(f"{path.relative_to(ROOT)}: {element} coverage differs from canonical source")
    for index in ("search-index.en-gb.json", "search-index.es-mx.json"):
        payload = json.loads((ROOT / "assets/data" / index).read_text(encoding="utf-8"))
        if payload.get("count") != 0 or payload.get("entries") != []:
            fail(f"{index}: draft routes must have zero public search entries")
    if FAILURES:
        print("Regional draft check failed:")
        print("\n".join(f"  - {item}" for item in FAILURES))
        return 1
    print("Regional draft check passed: en-gb and es-mx, four routes each, noindex, no public alternates, zero search entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
OverKill Hill P³™ — static site validation harness.

Phase 16 of the AUDIT_OVERKILL_HILL_REPLIT_PASS pipeline.

Checks every production HTML page for:
  - <title> present
  - meta description present
  - canonical link present
  - single <h1>
  - JSON-LD structured data present
   - sitemap inventory and inclusion (for non-noindex pages)
  - broken internal links (relative or /-rooted hrefs that resolve to no file)
  - broken asset references (CSS/JS/images)
  - external target="_blank" links missing rel="noopener" / "noreferrer"
  - placeholder hrefs ("#", "javascript:void(0)", empty href)
  - "P3" without superscript inside <title> or <meta> (brand violation)
  - old tagline "Precision. Power. Presence." anywhere (brand regression)
  - Glee and AskJamie theme-color media variants and color-scheme metadata
  - current content-hashed references to shared CSS and JavaScript
  - SEO metadata contract (Organization, article dates, social-card assets)
    and the ordered v03 heat-guide chain

Exits 0 if no errors. Exits 1 if any errors. Warnings do not fail the build.
Run from repo root:  python3 scripts/validate-site.py
"""

from __future__ import annotations

import os
import hashlib
import json
import re
import struct
import subprocess
import sys
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from csp import build_policies, page_class, sha256_source
from brand_theme import load_brand_theme_contract, validate_brand_theme_contract
from public_page_boundary import PUBLIC_PAGE_EXCLUDED_DIRS, iter_public_html_files


def configure_utf8_console() -> None:
    """Keep Windows validation output and child-tool decoding portable."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


configure_utf8_console()

ROOT = Path(
    os.environ.get(
        "OKHP3_VALIDATION_ROOT",
        str(Path(__file__).resolve().parent.parent),
    )
).resolve()
# Production-page discovery deliberately excludes checked-in test HTML.  Files
# under tests/fixtures/ are served only by their dedicated test commands; they
# are not published pages and must not inherit production SEO requirements.
SKIP_DIRS = set(PUBLIC_PAGE_EXCLUDED_DIRS)
SITEMAP = ROOT / "sitemap.xml"
SITE_ORIGIN = "https://overkillhill.com"
MANIFEST = ROOT / "site-src/pages.json"
LOCALE_MANIFEST = ROOT / "i18n/pilot/manifest.json"
HEAD_PARTIAL = ROOT / "assets/partials/head.html"
MANIFEST_EXTERNAL_PREFIXES = ("de/", "es/", "fr/", "en-gb/", "es-mx/")
THEME_STYLESHEET_PATH = "/assets/css/theme.css"
THEME_STYLESHEET = ROOT / THEME_STYLESHEET_PATH.lstrip("/")
APP_SCRIPT_PATH = "/assets/js/app.js"
MERMAID_INIT_SCRIPT_PATH = "/assets/js/mermaid-init.js"
SHARED_SCRIPT_PATHS = (APP_SCRIPT_PATH, MERMAID_INIT_SCRIPT_PATH)
BRAND_THEME_CONTRACT = {
    brand["bodyClass"]: brand
    for brand in load_brand_theme_contract().values()
}
THEME_COLOR_MEDIA = {
    "light": "(prefers-color-scheme: light)",
    "dark": "(prefers-color-scheme: dark)",
}
MERMAID_VENDOR_ROOT = ROOT / "assets/vendor/mermaid"
MERMAID_VENDOR_ENTRY = MERMAID_VENDOR_ROOT / "mermaid.esm.min.mjs"
MERMAID_VERSION_FILE = MERMAID_VENDOR_ROOT / "VERSION"
INLINE_CSP_SOURCE_ROUTES = {"projects/telling-forward/index.html"}
MERMAID_LOOSE_ROUTES = {
    "universe/index.html",
    "writings/first-diagram-is-a-liar/v03/v2-heat-a/index.html",
    "writings/first-diagram-is-a-liar/v03/v2-heat-b/index.html",
}
MERMAID_HEAT_ROUTES = {
    "writings/first-diagram-is-a-liar/v03/v2-heat-a/index.html",
    "writings/first-diagram-is-a-liar/v03/v2-heat-b/index.html",
}
MERMAID_HEAT_TARGETS = {
    ("https://mermaidchart.cello.so", "/UhVlNtC2MlS"),
    ("https://replit.com", "/refer/overkillhillp3"),
    ("https://overkillhill.com", "/writings/first-diagram-is-a-liar/"),
    ("https://overkillhill.com", "/"),
    ("https://www.linkedin.com", "/company/overkillhillp3"),
    ("https://ko-fi.com", "/T6T71HCY6A"),
}

# SEO metadata is generated from site-src/pages.json and the shared head
# partial. Keep the non-editorial contract here so a content edit cannot
# silently weaken the published head.
RETIRED_SOCIAL_IMAGE = "/assets/img/over-kill-hill-p3-sentinel-waiting-square-1024.png"
SOCIAL_CARD_META_KEYS = (
    "og:image",
    "og:image:alt",
    "og:image:width",
    "og:image:height",
    "og:image:type",
    "twitter:image",
    "twitter:image:alt",
)
ARTICLE_ROUTE_PREFIX = "/writings/"
FEATURED_WRITING_ROUTE = "/writings/first-diagram-is-a-liar/"
FEATURED_WRITING_SOURCE = ROOT / "site-src/pages/writings/index.main.html"
FEATURED_ARTICLE_SOURCE = ROOT / "site-src/pages/writings/first-diagram-is-a-liar/index.main.html"
FEATURED_WRITING_GENERATED = ROOT / "writings/index.html"
FEATURED_ARTICLE_GENERATED = ROOT / "writings/first-diagram-is-a-liar/index.html"
HEAT_GUIDE_ROUTES = (
    "/writings/first-diagram-is-a-liar/v03/v1-heat-a/",
    "/writings/first-diagram-is-a-liar/v03/v1-heat-b/",
    "/writings/first-diagram-is-a-liar/v03/v2-heat-a/",
    "/writings/first-diagram-is-a-liar/v03/v2-heat-b/",
)
EXPECTED_ORGANIZATION = {
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

# Em dash in all three forms: literal U+2014, named entity, numeric entity
EM_DASH_RE = re.compile(r"\u2014|&mdash;|&#8212;")


class TagCounter(HTMLParser):
    """Collect everything we need for one HTML page in a single pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self._in_title = False
        self._title_buf: list[str] = []
        self.h1_count = 0
        self.has_meta_description = False
        self.has_canonical = False
        self.has_jsonld = False
        self.is_noindex = False
        self.anchors: list[dict[str, str]] = []
        self.asset_refs: list[str] = []  # src/href for css/js/img/link
        self.stylesheet_refs: list[str] = []
        self.script_refs: list[str] = []
        self.meta: dict[str, list[str]] = {}
        self.body_classes: set[str] = set()
        self.theme_colors: list[dict[str, str]] = []
        self.jsonld_blocks: list[str] = []
        self.navigation_links: dict[str, list[str]] = {"prev": [], "next": []}
        self._in_jsonld = False
        self._jsonld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs_list):
        attrs = {k: (v or "") for k, v in attrs_list}
        if tag == "title":
            self._in_title = True
        elif tag == "body":
            self.body_classes = set(attrs.get("class", "").split())
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "meta":
            name = attrs.get("name", "").lower()
            prop = attrs.get("property", "").lower()
            content = attrs.get("content", "")
            key = name or prop
            if key:
                self.meta.setdefault(key, []).append(content)
            if name == "theme-color":
                self.theme_colors.append(
                    {
                        "media": attrs.get("media", ""),
                        "content": content,
                    }
                )
            if name == "description" and content.strip():
                self.has_meta_description = True
            if name == "robots" and "noindex" in content.lower():
                self.is_noindex = True
        elif tag == "link":
            rel = attrs.get("rel", "").lower()
            href = attrs.get("href", "")
            for navigation_rel in ("prev", "next"):
                if navigation_rel in rel.split() and href:
                    self.navigation_links[navigation_rel].append(href)
            if rel == "canonical" and href:
                self.has_canonical = True
            if "stylesheet" in rel.split() and href:
                self.stylesheet_refs.append(href)
                self.asset_refs.append(href)
            elif rel in ("icon", "apple-touch-icon", "manifest") and href:
                self.asset_refs.append(href)
        elif tag == "script":
            t = attrs.get("type", "").lower()
            src = attrs.get("src", "")
            if t == "application/ld+json":
                self.has_jsonld = True
                self._in_jsonld = True
                self._jsonld_buf = []
            if src:
                self.asset_refs.append(src)
                self.script_refs.append(src)
        elif tag == "img":
            src = attrs.get("src", "")
            if src:
                self.asset_refs.append(src)
        elif tag == "a":
            href = attrs.get("href", "")
            if href is not None:
                self.anchors.append(
                    {
                        "href": href,
                        "target": attrs.get("target", ""),
                        "rel": attrs.get("rel", ""),
                    }
                )

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False
            self.title = "".join(self._title_buf).strip()
            self._title_buf = []
        elif tag == "script" and self._in_jsonld:
            self.jsonld_blocks.append("".join(self._jsonld_buf).strip())
            self._in_jsonld = False
            self._jsonld_buf = []

    def handle_data(self, data: str):
        if self._in_title:
            self._title_buf.append(data)
        if self._in_jsonld:
            self._jsonld_buf.append(data)


def find_html_files() -> list[Path]:
    files: list[Path] = []
    for path in iter_public_html_files(ROOT):
        # /assets/templates/ holds stripped template scaffolds with [PLACEHOLDER]
        # tokens — not live pages. They're parsed separately by extract-templates.py.
        rel_posix = path.relative_to(ROOT).as_posix()
        if rel_posix.startswith(("assets/templates/", "assets/partials/")):
            continue
        files.append(path)
    return sorted(files)


def _sitemap_location_from_block(block: str) -> tuple[str | None, str | None]:
    """Return one plain-text sitemap location or its structural problem."""
    loc_openings = list(re.finditer(r"<loc\b[^>]*>", block, flags=re.IGNORECASE))
    loc_closings = list(re.finditer(r"</loc\s*>", block, flags=re.IGNORECASE))
    if len(loc_openings) != 1:
        return None, f"must contain exactly one <loc> element; found {len(loc_openings)}"
    if len(loc_closings) != 1:
        return None, "has malformed <loc> element structure"

    loc_opening = loc_openings[0]
    loc_closing = loc_closings[0]
    if loc_closing.start() < loc_opening.end():
        return None, "has malformed <loc> element structure"

    raw_location = block[loc_opening.end():loc_closing.start()]
    if "<" in raw_location:
        return None, "has malformed markup inside <loc>"
    location = unescape(raw_location).strip()
    if not location:
        return None, "has an empty <loc> value"
    return location, None


def _sitemap_entries_with_positions_and_findings_from_path(
    sitemap_path: Path,
) -> tuple[list[tuple[int, str, str | None]], list[Finding]]:
    """Read valid location/date entries and report unusable URL blocks."""
    if not sitemap_path.exists():
        return [], []
    text = sitemap_path.read_text(encoding="utf-8")
    entries: list[tuple[int, str, str | None]] = []
    findings: list[Finding] = []
    blocks = re.findall(
        r"<url\b[^>]*>(.*?)</url>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for position, block in enumerate(blocks, start=1):
        loc, location_error = _sitemap_location_from_block(block)
        if location_error is not None:
            findings.append(Finding(
                "ERROR",
                "sitemap.xml",
                f"sitemap URL entry at position {position} {location_error}",
            ))
            continue
        if loc is None:
            continue
        lastmod_match = re.search(
            r"<lastmod\b[^>]*>([^<]*)</lastmod>",
            block,
            flags=re.IGNORECASE,
        )
        entries.append((
            position,
            loc,
            unescape(lastmod_match.group(1).strip())
            if lastmod_match is not None
            else None,
        ))
    return entries, findings


def _sitemap_entries_with_positions_from_path(
    sitemap_path: Path,
) -> list[tuple[int, str, str | None]]:
    """Read usable sitemap entries with their one-based source positions."""
    entries, _ = _sitemap_entries_with_positions_and_findings_from_path(sitemap_path)
    return entries


def _sitemap_entries_from_path(sitemap_path: Path) -> list[tuple[str, str | None]]:
    """Read sitemap location/date pairs without collapsing duplicate locations."""
    return [
        (loc, lastmod)
        for _, loc, lastmod in _sitemap_entries_with_positions_from_path(sitemap_path)
    ]


def load_sitemap_entries(sitemap_path: Path = SITEMAP) -> dict[str, str | None]:
    """Load sitemap locations with the first date for each location.

    Duplicate locations are reported separately by
    :func:`validate_sitemap_duplicates`; retaining the first value here keeps
    callers deterministic without allowing a later duplicate to silently win.
    """
    entries: dict[str, str | None] = {}
    for loc, lastmod in _sitemap_entries_from_path(sitemap_path):
        entries.setdefault(loc, lastmod)
    return entries


def validate_sitemap_duplicates(sitemap_path: Path = SITEMAP) -> list[Finding]:
    """Reject duplicate sitemap locations before consumers build a date map."""
    entries, findings = _sitemap_entries_with_positions_and_findings_from_path(sitemap_path)
    occurrences: dict[str, list[tuple[int, str | None]]] = {}
    for position, loc, lastmod in entries:
        occurrences.setdefault(loc, []).append((position, lastmod))

    for loc in sorted(occurrences):
        entries = occurrences[loc]
        if len(entries) < 2:
            continue
        positions = ", ".join(str(position) for position, _ in entries)
        findings.append(Finding(
            "ERROR",
            "sitemap.xml",
            (
                f"duplicate sitemap location: {loc} appears {len(entries)} times "
                f"at sitemap entry positions {positions}"
            ),
        ))
        if len({lastmod for _, lastmod in entries}) > 1:
            dated_entries = "; ".join(
                f"position {position}: {lastmod!r}"
                for position, lastmod in entries
            )
            findings.append(Finding(
                "ERROR",
                "sitemap.xml",
                (
                    f"conflicting duplicate sitemap lastmod values for {loc}: "
                    f"{dated_entries}"
                ),
            ))
    return findings


def load_sitemap_urls() -> set[str]:
    """Load sitemap locations while preserving the existing inventory API."""
    return set(load_sitemap_entries())


def validate_sitemap_inventory(sitemap_urls: set[str]) -> list[Finding]:
    """Ensure every sitemap entry resolves to a production HTML page."""
    findings: list[Finding] = []
    for url in sorted(sitemap_urls):
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != urlparse(SITE_ORIGIN).netloc:
            findings.append(Finding("ERROR", "sitemap.xml", f"non-production URL in sitemap.xml: {url}"))
            continue
        route = parsed.path or "/"
        target = ROOT / route.lstrip("/")
        if route == "/":
            target = ROOT / "index.html"
        elif route.endswith("/"):
            target = target / "index.html"
        if not target.is_file():
            findings.append(Finding("ERROR", "sitemap.xml", f"sitemap URL has no HTML page: {url}"))
    return findings


def html_to_route(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def load_source_manifest() -> tuple[list[dict], list[Finding]]:
    """Load the page manifest used to render the checked-in HTML."""
    if not MANIFEST.is_file():
        return [], [Finding("ERROR", "site-src/pages.json", "source page manifest is missing")]
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [Finding("ERROR", "site-src/pages.json", f"cannot read source page manifest: {exc}")]
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        return [], [Finding("ERROR", "site-src/pages.json", "source page manifest has no pages list")]
    if any(not isinstance(page, dict) for page in pages):
        return [], [Finding("ERROR", "site-src/pages.json", "source page manifest contains a non-object page")]
    return pages, []


def is_indexable_page(page: dict) -> bool:
    return "noindex" not in page.get("meta:robots", "").lower()


def is_article_page(page: dict) -> bool:
    """Identify published articles without relying only on mutable og:type."""
    route = page.get("route", "")
    return (
        page.get("meta:og:type", "").lower() == "article"
        or route == "/manifesto/"
        or (
            is_indexable_page(page)
            and route.startswith(ARTICLE_ROUTE_PREFIX)
            and route != ARTICLE_ROUTE_PREFIX
        )
    )


def image_metadata(path: Path) -> tuple[int, int, str] | None:
    """Read dimensions and MIME type from common image headers."""
    try:
        data = path.read_bytes()
    except OSError:
        return None

    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return width, height, "image/png"

    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        if len(data) >= 10:
            width, height = struct.unpack("<HH", data[6:10])
            return width, height, "image/gif"

    if data.startswith(b"\xff\xd8"):
        # JPEG dimensions live in a Start Of Frame marker. Skip APP and
        # comment segments until one of the baseline/progressive SOFs.
        offset = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while offset + 3 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9):
                continue
            if offset + 2 > len(data):
                break
            segment_length = struct.unpack(">H", data[offset:offset + 2])[0]
            if segment_length < 2 or offset + segment_length > len(data):
                break
            if marker in sof_markers and segment_length >= 7:
                height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
                return width, height, "image/jpeg"
            offset += segment_length

    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return width, height, "image/webp"
        if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width, height = struct.unpack("<HH", data[26:30])
            return width & 0x3FFF, height & 0x3FFF, "image/webp"
        if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            bits = data[21:25]
            width = 1 + ((bits[0] | bits[1] << 8) & 0x3FFF)
            height = 1 + ((bits[1] >> 6 | bits[2] << 2 | bits[3] << 10) & 0x3FFF)
            return width, height, "image/webp"

    return None


def _image_asset_path(url: str) -> Path | None:
    """Resolve a social-image URL only when it points into this site."""
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc != urlparse(SITE_ORIGIN).netloc:
            return None
    if not parsed.path:
        return None
    return ROOT / unquote(parsed.path).lstrip("/")

def validate_social_card_consistency(location: str, values: dict[str, str]) -> list[Finding]:
    """Keep Open Graph and Twitter social-card metadata aligned."""
    findings = validate_social_image_parity(location, values)
    og_image = values.get("meta:og:image", "")
    twitter_image = values.get("meta:twitter:image", "")
    if og_image and twitter_image:
        og_alt = values.get("meta:og:image:alt", "")
        twitter_alt = values.get("meta:twitter:image:alt", "")
        if og_alt != twitter_alt:
            findings.append(Finding(
                "ERROR", location,
                "social-card image alt mismatch: "
                f"meta:og:image:alt={og_alt!r}, meta:twitter:image:alt={twitter_alt!r}",
            ))
    return findings


def validate_indexable_social_card(
    location: str,
    values: dict[str, str],
    page_label: str = "page",
) -> list[Finding]:
    """Apply the complete social-card contract to an indexable page."""
    findings: list[Finding] = []
    label = f"indexable {page_label}"
    for key in ("meta:og:image", "meta:og:image:width", "meta:og:image:height", "meta:og:image:type"):
        if not values.get(key):
            findings.append(Finding("ERROR", location, f"{label} page is missing {key}"))
    for key in ("meta:og:image", "meta:twitter:image"):
        if RETIRED_SOCIAL_IMAGE in values.get(key, ""):
            findings.append(Finding("ERROR", location, f"{label} page uses retired social image: {key}"))
    findings.extend(validate_social_card_consistency(location, values))
    findings.extend(validate_image_contract(location, values))
    return findings


def validate_image_contract(location: str, values: dict[str, str]) -> list[Finding]:
    """Check declared social-card metadata against the actual local asset."""
    findings: list[Finding] = []
    image_url = values.get("meta:og:image", "")
    if not image_url:
        return [Finding("ERROR", location, "indexable page is missing meta:og:image")]
    asset = _image_asset_path(image_url)
    if asset is None:
        findings.append(Finding("ERROR", location, f"social image is not a local production asset: {image_url}"))
        return findings
    if not asset.is_file():
        findings.append(Finding("ERROR", location, f"social image asset is missing: {image_url}"))
        return findings
    actual = image_metadata(asset)
    if actual is None:
        findings.append(Finding("ERROR", location, f"social image type or dimensions cannot be read: {image_url}"))
        return findings

    actual_width, actual_height, actual_type = actual
    declared = (
        values.get("meta:og:image:width", ""),
        values.get("meta:og:image:height", ""),
        values.get("meta:og:image:type", ""),
    )
    try:
        declared_width, declared_height = int(declared[0]), int(declared[1])
    except (TypeError, ValueError):
        findings.append(Finding(
            "ERROR", location,
            f"social image dimensions must be integers (declared {declared[0]!r} × {declared[1]!r})",
        ))
    else:
        if (declared_width, declared_height) != (actual_width, actual_height):
            findings.append(Finding(
                "ERROR", location,
                f"social image dimensions {declared_width} × {declared_height} do not match "
                f"asset {actual_width} × {actual_height}: {image_url}",
            ))
    if declared[2].lower() != actual_type:
        findings.append(Finding(
            "ERROR", location,
            f"social image type {declared[2]!r} does not match asset {actual_type!r}: {image_url}",
        ))
    return findings


def validate_social_image_parity(location: str, values: dict[str, str]) -> list[Finding]:
    """Keep Open Graph and Twitter cards pointed at the same social image."""
    og_image = values.get("meta:og:image", "")
    twitter_image = values.get("meta:twitter:image", "")
    if not twitter_image:
        return [Finding("ERROR", location, "indexable page is missing meta:twitter:image")]
    if og_image and og_image != twitter_image:
        return [
            Finding(
                "ERROR",
                location,
                "social card image mismatch: meta:og:image and meta:twitter:image must be identical",
            )
        ]
    return []


def validate_duplicate_social_card_metadata(
    location: str,
    metadata: dict[str, list[str]],
) -> list[Finding]:
    """Reject conflicting duplicate image metadata before consumers choose differently."""
    findings: list[Finding] = []
    for key in SOCIAL_CARD_META_KEYS:
        values = metadata.get(key, [])
        if len(values) > 1 and len(set(values)) > 1:
            findings.append(Finding(
                "ERROR",
                location,
                f"conflicting duplicate social-card metadata for meta:{key}: "
                f"{values!r}",
            ))
    return findings


def _jsonld_objects(parser: TagCounter) -> tuple[list[dict], list[str]]:
    objects: list[dict] = []
    errors: list[str] = []
    for block in parser.jsonld_blocks:
        try:
            value = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict):
                objects.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    objects.extend(node for node in graph if isinstance(node, dict))
    return objects, errors


def _organization_nodes(parser: TagCounter) -> tuple[list[dict], list[str]]:
    objects, errors = _jsonld_objects(parser)
    return [
        item for item in objects
        if item.get("@type") == "Organization"
    ], errors


def validate_organization_nodes(location: str, parser: TagCounter) -> list[Finding]:
    """Require the one canonical Organization node and its verified links."""
    nodes, parse_errors = _organization_nodes(parser)
    findings = [
        Finding("ERROR", location, f"invalid JSON-LD block: {error}")
        for error in parse_errors
    ]
    if len(nodes) != 1:
        findings.append(Finding(
            "ERROR", location,
            f"expected exactly one shared Organization JSON-LD node, found {len(nodes)}",
        ))
        return findings

    node = nodes[0]
    for key in ("@context", "@type", "@id", "name", "url"):
        if node.get(key) != EXPECTED_ORGANIZATION[key]:
            findings.append(Finding(
                "ERROR", location,
                f"shared Organization field {key!r} does not match the site contract",
            ))
    if node.get("logo") != EXPECTED_ORGANIZATION["logo"]:
        findings.append(Finding("ERROR", location, "shared Organization logo does not match the site contract"))
    same_as = node.get("sameAs")
    expected_same_as = EXPECTED_ORGANIZATION["sameAs"]
    if not isinstance(same_as, list) or set(same_as) != set(expected_same_as):
        findings.append(Finding(
            "ERROR", location,
            "shared Organization sameAs links do not match the verified site links",
        ))
    return findings


def _article_date_values_match(article_date: str, published_time: str) -> bool:
    """Compare Article dates without losing either calendar or instant meaning.

    Date-only values are calendar dates and must match as exact contract
    strings.  Timezone-qualified ISO 8601 date-times represent instants, so
    equivalent values with different offsets match after UTC normalization.
    A date-only value, a timezone-less date-time, and a timezone-qualified
    date-time are not interchangeable; values outside those exact or
    normalized matches fail parity.
    """
    if article_date == published_time:
        return True

    def is_date_only(value: str) -> bool:
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return "T" not in value and "t" not in value

    if is_date_only(article_date) or is_date_only(published_time):
        return False

    try:
        article_datetime = datetime.fromisoformat(article_date.replace("Z", "+00:00"))
        published_datetime = datetime.fromisoformat(published_time.replace("Z", "+00:00"))
    except ValueError:
        return False

    article_offset = article_datetime.utcoffset()
    published_offset = published_datetime.utcoffset()
    if article_offset is None or published_offset is None:
        return False

    return (
        article_datetime.astimezone(timezone.utc)
        == published_datetime.astimezone(timezone.utc)
    )


def validate_article_jsonld_dates(
    location: str,
    parser: TagCounter,
    published_time: str | None = None,
) -> list[Finding]:
    """Require complete, valid, and synchronized dates on Article JSON-LD nodes."""
    objects, parse_errors = _jsonld_objects(parser)
    findings = [
        Finding("ERROR", location, f"invalid JSON-LD block: {error}")
        for error in parse_errors
    ]
    articles = [item for item in objects if item.get("@type") == "Article"]
    published_dates = [
        article["datePublished"]
        for article in articles
        if isinstance(article.get("datePublished"), str)
        and article["datePublished"]
    ]
    if len(published_dates) > 1 and len(set(published_dates)) > 1:
        findings.append(Finding(
            "ERROR",
            location,
            "conflicting duplicate Article JSON-LD datePublished values: "
            f"{published_dates!r}",
        ))
    modified_dates = [
        article["dateModified"]
        for article in articles
        if isinstance(article.get("dateModified"), str)
        and article["dateModified"]
    ]
    if len(modified_dates) > 1 and len(set(modified_dates)) > 1:
        findings.append(Finding(
            "ERROR",
            location,
            "conflicting duplicate Article JSON-LD dateModified values: "
            f"{modified_dates!r}",
        ))
    for article in articles:
        for field in ("datePublished", "dateModified"):
            value = article.get(field)
            if field not in article or value in (None, ""):
                findings.append(Finding(
                    "ERROR",
                    location,
                    f"article JSON-LD {field} is missing",
                ))
                continue
            if not isinstance(value, str):
                findings.append(Finding(
                    "ERROR",
                    location,
                    f"article JSON-LD {field} is not ISO 8601: {value!r}",
                ))
                continue
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                findings.append(Finding(
                    "ERROR",
                    location,
                    f"article JSON-LD {field} is not ISO 8601: {value!r}",
                ))
        if (
            published_time
            and isinstance(article.get("datePublished"), str)
            and not _article_date_values_match(article["datePublished"], published_time)
        ):
            findings.append(Finding(
                "ERROR",
                location,
                "article JSON-LD datePublished does not match "
                f"article:published_time: {article['datePublished']!r} != {published_time!r}",
            ))
    return findings


def validate_article_sitemap_dates(
    location: str,
    parser: TagCounter,
    sitemap_url: str,
    sitemap_lastmod: str | None,
) -> list[Finding]:
    """Keep indexable Article JSON-LD dateModified aligned with sitemap lastmod."""
    objects, _ = _jsonld_objects(parser)
    articles = [item for item in objects if item.get("@type") == "Article"]
    if not articles:
        return []

    findings: list[Finding] = []
    if sitemap_lastmod in (None, ""):
        findings.append(
            Finding(
                "ERROR",
                location,
                f"article sitemap lastmod is missing for {sitemap_url}",
            )
        )
        return findings

    try:
        datetime.fromisoformat(sitemap_lastmod.replace("Z", "+00:00"))
    except ValueError:
        findings.append(
            Finding(
                "ERROR",
                location,
                f"article sitemap lastmod is not ISO 8601: {sitemap_lastmod!r}",
            )
        )
        return findings

    structured_dates = {
        article.get("dateModified")
        for article in articles
        if isinstance(article.get("dateModified"), str)
        and article.get("dateModified")
    }
    for structured_date in sorted(structured_dates):
        if structured_date != sitemap_lastmod:
            findings.append(
                Finding(
                    "ERROR",
                    location,
                    "article JSON-LD dateModified does not match sitemap "
                    f"lastmod: {structured_date!r} != {sitemap_lastmod!r}",
                )
            )
    return findings


def validate_organization_source() -> list[Finding]:
    """Validate the shared source head before checking rendered pages."""
    if not HEAD_PARTIAL.is_file():
        return [Finding("ERROR", "assets/partials/head.html", "shared head partial is missing")]
    parser = TagCounter()
    parser.feed(HEAD_PARTIAL.read_text(encoding="utf-8", errors="replace"))
    return validate_organization_nodes("assets/partials/head.html", parser)


def validate_article_jsonld_source(
    pages: list[dict],
    sitemap_entries: dict[str, str | None] | None = None,
) -> list[Finding]:
    """Validate Article JSON-LD dates on indexable source pages before rendering."""
    findings: list[Finding] = []
    for page in pages:
        # Noindex writing drafts are intentionally outside the published Article
        # date contract until their manifest boundary is promoted.
        if not is_indexable_page(page):
            continue
        source_path = page.get("path")
        if not isinstance(source_path, str):
            continue
        extras = (ROOT / "site-src" / "pages" / source_path).with_suffix(".extras.html")
        if not extras.is_file():
            continue
        parser = TagCounter()
        parser.feed(extras.read_text(encoding="utf-8", errors="replace"))
        findings.extend(validate_article_jsonld_dates(
            _path_location(extras),
            parser,
            (
                str(page.get("meta:article:published_time", "")) or None
                if is_article_page(page)
                else None
            ),
        ))
        if sitemap_entries is not None and is_article_page(page):
            sitemap_url = str(page.get("canonical") or SITE_ORIGIN + page.get("route", ""))
            if sitemap_url in sitemap_entries:
                findings.extend(validate_article_sitemap_dates(
                    _path_location(extras),
                    parser,
                    sitemap_url,
                    sitemap_entries[sitemap_url],
                ))
    return findings


def _manifest_metadata(page: dict) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in page.items()
        if key.startswith("meta:")
    }


def _path_location(path: Path) -> str:
    """Return a stable validator location for repository or fixture paths."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_locale_seo_contract() -> tuple[dict[str, dict], list[Finding]]:
    """Load the manifest-owned indexability boundary for localized pages."""
    if not LOCALE_MANIFEST.is_file():
        return {}, []
    try:
        manifest = json.loads(LOCALE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [Finding("ERROR", _path_location(LOCALE_MANIFEST), f"cannot read locale manifest: {exc}")]

    locales = manifest.get("locales") if isinstance(manifest, dict) else None
    if not isinstance(locales, dict):
        return {}, [Finding("ERROR", _path_location(LOCALE_MANIFEST), "locale manifest has no locales object")]

    contract: dict[str, dict] = {}
    findings: list[Finding] = []
    for locale, entry in locales.items():
        if not isinstance(entry, dict):
            findings.append(Finding("ERROR", _path_location(LOCALE_MANIFEST), f"locale entry is not an object: {locale!r}"))
            continue
        indexable = entry.get("indexable")
        metadata_source = entry.get("metadata_source")
        if not isinstance(indexable, bool):
            findings.append(Finding("ERROR", _path_location(LOCALE_MANIFEST), f"locale {locale!r} must declare boolean indexable state"))
            indexable = False
        if metadata_source != "localized-page":
            findings.append(Finding("ERROR", _path_location(LOCALE_MANIFEST), f"locale {locale!r} must declare metadata_source='localized-page'"))
        pages = entry.get("pages")
        if not isinstance(pages, list):
            findings.append(Finding("ERROR", _path_location(LOCALE_MANIFEST), f"locale {locale!r} has no pages list"))
            continue
        for page in pages:
            if not isinstance(page, dict) or not isinstance(page.get("target_path"), str):
                findings.append(Finding("ERROR", _path_location(LOCALE_MANIFEST), f"locale {locale!r} has an invalid page entry"))
                continue
            page_indexable = page.get("indexable", indexable)
            page_metadata_source = page.get("metadata_source", metadata_source)
            if not isinstance(page_indexable, bool):
                findings.append(Finding("ERROR", _path_location(LOCALE_MANIFEST), f"locale page {page['target_path']!r} must declare boolean indexable state"))
                page_indexable = False
            if page_metadata_source != "localized-page":
                findings.append(Finding("ERROR", _path_location(LOCALE_MANIFEST), f"locale page {page['target_path']!r} must declare metadata_source='localized-page'"))
            contract[page["target_path"]] = {
                "indexable": page_indexable,
                "metadata_source": page_metadata_source,
            }
    return contract, findings


def _release_matches(raw: str, pattern: re.Pattern[str]) -> list[str]:
    """Extract release labels from one semantic writing-page element."""
    matches = pattern.findall(raw)
    return [match.lower() for match in matches]


FEATURED_CARD_RELEASE_RE = re.compile(
    r"<[a-z][^>]*\bclass=[\"'][^\"']*\bwriting-card-kicker--featured\b[^\"']*[\"'][^>]*>"
    r"(.*?)</[a-z][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
ARTICLE_RELEASE_RE = re.compile(
    r"<span\b[^>]*>\s*Article\s+(v\d+(?:\.\d+)+)\s*:",
    re.IGNORECASE,
)
RELEASE_LABEL_RE = re.compile(r"\bv\d+(?:\.\d+)+\b", re.IGNORECASE)


def _featured_card_releases(raw: str) -> list[str]:
    return [
        release
        for element in FEATURED_CARD_RELEASE_RE.findall(raw)
        for release in _release_matches(element, RELEASE_LABEL_RE)
    ]


def validate_writing_release_alignment(
    writing_hub: Path,
    article: Path,
    article_route: str = FEATURED_WRITING_ROUTE,
) -> list[Finding]:
    """Keep the featured writing-card release equal to the article release.

    This is run against both source fragments and generated pages. Requiring
    exactly one semantic label on each side avoids silently accepting a
    missing or ambiguous release when the content is edited.
    """
    findings: list[Finding] = []
    hub_location = _path_location(writing_hub)
    article_location = _path_location(article)

    try:
        hub_raw = writing_hub.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding("ERROR", hub_location, f"cannot read featured writing page: {exc}")]
    try:
        article_raw = article.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding("ERROR", article_location, f"cannot read featured article page: {exc}")]

    article_releases = _release_matches(article_raw, ARTICLE_RELEASE_RE)
    if len(article_releases) != 1:
        findings.append(
            Finding(
                "ERROR",
                article_location,
                f"current article release is missing or ambiguous for {article_route}: "
                'expected exactly one "Article vN.N" label',
            )
        )
        return findings
    expected = article_releases[0]

    card_releases = _featured_card_releases(hub_raw)
    if len(card_releases) != 1:
        findings.append(
            Finding(
                "ERROR",
                hub_location,
                f"featured writing card release is missing or ambiguous for {article_route}: "
                f"expected exactly one {expected} label from the article",
            )
        )
        return findings
    found = card_releases[0]

    if found != expected:
        findings.append(
            Finding(
                "ERROR",
                hub_location,
                f"featured writing card release mismatch for {article_route}: "
                f"expected {expected} from the article, found {found}",
            )
        )
    return findings


def validate_source_seo_contract(pages: list[dict]) -> list[Finding]:
    """Validate SEO fields before the renderer turns them into HTML."""
    findings: list[Finding] = []
    seen_paths: set[str] = set()
    for page in pages:
        rel = str(page.get("path", "site-src/pages.json"))
        metadata = _manifest_metadata(page)
        if rel in seen_paths:
            findings.append(Finding("ERROR", "site-src/pages.json", f"duplicate page path in source manifest: {rel}"))
        seen_paths.add(rel)

        if is_indexable_page(page):
            findings.extend(validate_indexable_social_card(rel, metadata, "source"))

        if is_article_page(page):
            if metadata.get("meta:og:type", "").lower() != "article":
                findings.append(Finding("ERROR", rel, "article source page must use og:type=article"))
            published = metadata.get("meta:article:published_time", "")
            if not published:
                findings.append(Finding("ERROR", rel, "article source page is missing article:published_time"))
            else:
                try:
                    datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    findings.append(Finding("ERROR", rel, f"article:published_time is not ISO 8601: {published!r}"))
    return findings


def validate_generated_seo(
    path: Path,
    parser: TagCounter,
    manifest_page: dict | None,
    locale_page: dict | None = None,
    sitemap_entries: dict[str, str | None] | None = None,
) -> list[Finding]:
    """Ensure rendered metadata still agrees with the source contract."""
    path = path.resolve()
    rel = path.relative_to(ROOT).as_posix()
    if manifest_page is None:
        if locale_page is not None:
            if locale_page.get("indexable"):
                values = {
                    "meta:" + key: entries[0] if entries else ""
                    for key, entries in parser.meta.items()
                }
                findings = validate_duplicate_social_card_metadata(rel, parser.meta)
                findings.extend(validate_indexable_social_card(rel, values))
                if locale_page.get("metadata_source") != "localized-page":
                    findings.append(Finding(
                        "ERROR",
                        rel,
                        "indexable locale page must own its social-card metadata as localized-page",
                    ))
                return findings
            return []
        # The source manifest intentionally covers the English build surface;
        # localized pilot pages are maintained separately and must not acquire
        # new SEO or indexing boundaries from this check.
        if rel.startswith(MANIFEST_EXTERNAL_PREFIXES):
            return []
        return [Finding("ERROR", rel, "generated page is absent from source manifest")]
    values = {
        "meta:" + key: entries[0] if entries else ""
        for key, entries in parser.meta.items()
    }
    findings = validate_organization_nodes(rel, parser)
    manifest_boundary = "indexable" if is_indexable_page(manifest_page) else "noindex"
    rendered_boundary = "noindex" if parser.is_noindex else "indexable"
    if rendered_boundary != manifest_boundary:
        findings.append(
            Finding(
                "ERROR",
                rel,
                "robots indexing boundary mismatch: "
                f"manifest={manifest_boundary}, rendered={rendered_boundary}",
            )
        )
    if is_indexable_page(manifest_page):
        findings.extend(validate_duplicate_social_card_metadata(rel, parser.meta))
        findings.extend(validate_indexable_social_card(rel, values, "generated"))
        findings.extend(validate_article_jsonld_dates(
            rel,
            parser,
            (
                values.get("meta:article:published_time", "") or None
                if is_article_page(manifest_page)
                else None
            ),
        ))
    if is_article_page(manifest_page):
        if values.get("meta:og:type", "").lower() != "article":
            findings.append(Finding("ERROR", rel, "article generated page must use og:type=article"))
        published = values.get("meta:article:published_time", "")
        if not published:
            findings.append(Finding("ERROR", rel, "article generated page is missing article:published_time"))
        else:
            try:
                datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                findings.append(Finding("ERROR", rel, f"article:published_time is not ISO 8601: {published!r}"))
        if sitemap_entries is not None:
            sitemap_url = str(manifest_page.get("canonical") or SITE_ORIGIN + html_to_route(path))
            if sitemap_url in sitemap_entries:
                findings.extend(validate_article_sitemap_dates(
                    rel,
                    parser,
                    sitemap_url,
                    sitemap_entries[sitemap_url],
                ))
    return findings


def validate_heat_guide_chain(
    pages: list[dict],
    generated_root: Path = ROOT,
) -> list[Finding]:
    """Check the four heat guides as one ordered prev/next chain."""
    by_route = {page.get("route"): page for page in pages}
    findings: list[Finding] = []
    for index, route in enumerate(HEAT_GUIDE_ROUTES):
        page = by_route.get(route)
        if page is None:
            findings.append(Finding("ERROR", "site-src/pages.json", f"heat-guide route is missing: {route}"))
            continue
        expected_prev = HEAT_GUIDE_ROUTES[index - 1] if index else ""
        expected_next = HEAT_GUIDE_ROUTES[index + 1] if index + 1 < len(HEAT_GUIDE_ROUTES) else ""
        expected_prev_url = SITE_ORIGIN + expected_prev if expected_prev else ""
        expected_next_url = SITE_ORIGIN + expected_next if expected_next else ""
        for key, expected in (("prev", expected_prev_url), ("next", expected_next_url)):
            if page.get(key, "") != expected:
                findings.append(Finding(
                    "ERROR", str(page.get("path", "site-src/pages.json")),
                    f"heat-guide {key} link is {page.get(key, '')!r}; expected {expected!r}",
                ))

    # Rendered links are checked separately so a stale generated page cannot
    # pass just because the manifest is correct.
    for page in pages:
        route = page.get("route")
        if route not in HEAT_GUIDE_ROUTES:
            continue
        output = generated_root / page.get("path", "")
        if not output.is_file():
            continue
        parser = TagCounter()
        parser.feed(output.read_text(encoding="utf-8", errors="replace"))
        index = HEAT_GUIDE_ROUTES.index(route)
        expected = {
            "prev": SITE_ORIGIN + HEAT_GUIDE_ROUTES[index - 1] if index else "",
            "next": SITE_ORIGIN + HEAT_GUIDE_ROUTES[index + 1] if index + 1 < len(HEAT_GUIDE_ROUTES) else "",
        }
        for key, expected_url in expected.items():
            actual = parser.navigation_links.get(key, [])
            expected_links = [expected_url] if expected_url else []
            if actual != expected_links:
                findings.append(Finding(
                    "ERROR", str(page.get("path", route)),
                    f"generated heat-guide {key} links are {actual!r}; expected {expected_links!r}",
                ))
    return findings


def current_content_hashed_url(asset_path: str) -> str | None:
    """Return the canonical content-hashed URL for a shared asset."""
    asset = ROOT / asset_path.lstrip("/")
    if not asset.is_file():
        return None
    canonical = asset.read_bytes().replace(b"\r\n", b"\n")
    fingerprint = hashlib.sha256(canonical).hexdigest()[:8]
    return f"{asset_path}?v={fingerprint}"


def is_asset_ref(ref: str, asset_path: str) -> bool:
    """Identify an asset whether a page used the canonical URL or a legacy form."""
    return urlparse(ref).path.lstrip("/") == asset_path.lstrip("/")


def resolve_internal(href: str, source: Path) -> Path | None:
    """Map a /-rooted or relative href back to a filesystem path. Returns None if not local."""
    parsed = urlparse(href)
    if parsed.scheme in ("http", "https", "mailto", "tel", "javascript"):
        return None
    if not parsed.path:
        return None  # pure fragment like "#protocols"
    p = unquote(parsed.path)
    if p.startswith("/"):
        target = ROOT / p.lstrip("/")
    else:
        target = source.parent / p
    return target


def target_exists(target: Path) -> bool:
    if target.exists():
        if target.is_dir():
            return (target / "index.html").exists()
        return True
    # tolerate trailing-slash directory references
    if str(target).endswith("/") and (target / "index.html").exists():
        return True
    return False


def _csp_script_hashes(policy: str | None) -> set[str]:
    """Extract script hashes from a serialized CSP policy."""
    if not policy:
        return set()
    match = re.search(r"(?:^|;\s*)script-src\s+([^;]+)", policy)
    if not match:
        return set()
    return {
        token for token in match.group(1).split()
        if token.startswith("'sha256-") and token.endswith("'")
    }


def _csp_meta_policy(raw: str) -> str | None:
    """Read a CSP meta tag regardless of HTML attribute ordering."""
    match = re.search(
        r'<meta\b(?=[^>]*\bhttp-equiv=["\']Content-Security-Policy["\'])'
        r'(?=[^>]*\bcontent=(["\']))[^>]*\bcontent=\1(.*?)\1',
        raw,
        re.IGNORECASE,
    )
    return match.group(2) if match else None


def _source_inline_script_hashes(page: Path) -> set[str]:
    """Return hashes for inline scripts in a page's source fragments."""
    rel = page.relative_to(ROOT).as_posix()
    stem = ROOT / "site-src" / "pages" / rel
    hashes: set[str] = set()
    for suffix in (".main.html", ".extras.html"):
        source = stem.with_suffix(suffix)
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        hashes.update(
            sha256_source(match.group(1))
            for match in re.finditer(
                r"<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>",
                text,
                re.IGNORECASE,
            )
            if match.group(1).strip()
        )
    return hashes


def validate_csp_hashes(pages: list[Path]) -> list[Finding]:
    """Ensure the telling-forward source script and generated CSP stay aligned."""
    findings: list[Finding] = []
    policies = build_policies()

    for page in pages:
        rel = page.relative_to(ROOT).as_posix()
        if rel not in INLINE_CSP_SOURCE_ROUTES:
            continue
        raw = page.read_text(encoding="utf-8", errors="replace")
        actual = _csp_meta_policy(raw)
        expected = policies[page_class(page)]
        if actual != expected:
            findings.append(Finding(
                "ERROR", rel,
                "CSP policy or inline script hash list is stale; run "
                "python3 scripts/generate-csp.py",
            ))
            continue

        actual_hashes = _csp_script_hashes(actual)
        source_hashes = _source_inline_script_hashes(page)
        missing = sorted(source_hashes - actual_hashes)
        if missing:
            findings.append(Finding(
                "ERROR", rel,
                "CSP is missing inline script hash(es) from site-src: "
                + ", ".join(missing),
            ))

    return findings


def _mermaid_imports(text: str) -> list[str]:
    """Return import specifiers from static and dynamic ESM imports."""
    pattern = re.compile(
        r"""(?:\bimport\s*\(\s*|\b(?:import|export)\b[^;]*?\bfrom\s*)["']([^"']+)["']"""
    )
    return [match.group(1) for match in pattern.finditer(text)]


def _mermaid_target_is_allowed(route: str, target: str) -> bool:
    try:
        parsed = urlparse(target)
    except ValueError:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        return False
    if route in MERMAID_HEAT_ROUTES:
        return (origin, parsed.path) in MERMAID_HEAT_TARGETS
    if route == "universe/index.html":
        if origin == "https://glee-fully.tools":
            return parsed.path == "/" or parsed.path.startswith("/toolbox/")
        if origin == "https://askjamie.bot":
            return parsed.path == "/" or parsed.path.startswith("/lens-system/")
        if origin == "https://overkillhill.com":
            return (
                parsed.path == "/"
                or parsed.path.startswith("/projects/")
                or parsed.path.startswith("/writings/")
            )
    return False


def validate_mermaid_runtime(pages: list[Path]) -> list[Finding]:
    """Check the vendored graph, Mermaid sources, security, and click policies."""
    findings: list[Finding] = []

    if not MERMAID_VENDOR_ENTRY.is_file():
        findings.append(Finding("ERROR", str(MERMAID_VENDOR_ENTRY.relative_to(ROOT)),
                                "vendored Mermaid entry module is missing"))
    elif not MERMAID_VENDOR_ROOT.is_dir():
        findings.append(Finding("ERROR", "assets/vendor/mermaid",
                                "vendored Mermaid directory is missing"))

    # Every relative import in the entry module and its chunks must resolve.
    if MERMAID_VENDOR_ROOT.is_dir():
        for module in sorted(MERMAID_VENDOR_ROOT.rglob("*.mjs")):
            text = module.read_text(encoding="utf-8", errors="replace")
            for specifier in _mermaid_imports(text):
                if specifier.startswith("."):
                    target = (module.parent / specifier).resolve()
                    if not target.is_file():
                        findings.append(Finding(
                            "ERROR", module.relative_to(ROOT).as_posix(),
                            f"missing local Mermaid import: {specifier}",
                        ))
                elif specifier.startswith("/assets/vendor/mermaid/"):
                    target = ROOT / specifier.split("?", 1)[0].lstrip("/")
                    if not target.is_file():
                        findings.append(Finding(
                            "ERROR", module.relative_to(ROOT).as_posix(),
                            f"missing local Mermaid import: {specifier}",
                        ))

    # Inspect checked-in HTML/JS sources as well as generated production pages.
    source_files = [
        path for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".html", ".js", ".mjs"}
        and not (set(path.relative_to(ROOT).parts) & SKIP_DIRS)
    ]
    for path in sorted(source_files):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for specifier in _mermaid_imports(text):
            if "mermaid" in specifier.lower() and urlparse(specifier).scheme in ("http", "https"):
                findings.append(Finding("ERROR", rel,
                                        f"external Mermaid import is not allowed: {specifier}"))
            if specifier.startswith("/assets/vendor/mermaid/"):
                target = ROOT / specifier.split("?", 1)[0].lstrip("/")
                if not target.is_file():
                    findings.append(Finding("ERROR", rel,
                                            f"missing local Mermaid import: {specifier}"))
        for specifier in re.findall(r"""<script\b[^>]*\bsrc=["']([^"']+)["']""", text, re.I):
            if "mermaid" in specifier.lower() and urlparse(specifier).scheme in ("http", "https"):
                findings.append(Finding("ERROR", rel,
                                        f"external Mermaid script is not allowed: {specifier}"))

    for path in pages:
        rel = path.relative_to(ROOT).as_posix()
        raw = path.read_text(encoding="utf-8", errors="replace")
        has_loose = bool(re.search(
            r"""data-mermaid-security\s*=\s*["']loose["']|securityLevel\s*:\s*["']loose["']""",
            raw, re.I,
        ))
        if has_loose and rel not in MERMAID_LOOSE_ROUTES:
            findings.append(Finding("ERROR", rel,
                                    "Mermaid loose security is not approved for this page"))

        click_targets = re.findall(
            r"""^\s*click\s+\S+\s+"([^"]+)""", raw, re.MULTILINE
        )
        if click_targets and rel not in MERMAID_LOOSE_ROUTES:
            findings.append(Finding("ERROR", rel,
                                    "Mermaid click targets are only approved on the documented pages"))
        for target in click_targets:
            if not _mermaid_target_is_allowed(rel, target):
                findings.append(Finding("ERROR", rel,
                                        f"Mermaid click target is outside its allowlist: {target}"))

    return findings


def validate_mermaid_version_pin(pages: list[Path]) -> list[Finding]:
    """Confirm the pinned VERSION file matches the vendored runtime bundle.

    This does not check npm for a newer release -- that is the job of the
    scheduled "mermaid-version-watch" GitHub Action, which needs network
    access this local validator does not assume. This check only confirms
    internal consistency: the version this repo claims to be running is the
    version actually sitting in assets/vendor/mermaid/, so a partial or
    forgotten re-vendor step cannot silently pass validation.
    """
    findings: list[Finding] = []
    rel_version_file = MERMAID_VERSION_FILE.relative_to(ROOT).as_posix()

    if not MERMAID_VERSION_FILE.is_file():
        findings.append(Finding(
            "ERROR", rel_version_file,
            "Mermaid VERSION pin file is missing; create it with the vendored "
            "release number (see README 'Mermaid runtime trust decision')",
        ))
        return findings

    pinned = MERMAID_VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", pinned):
        findings.append(Finding(
            "ERROR", rel_version_file,
            f"Mermaid VERSION pin {pinned!r} is not a plain semver string (X.Y.Z)",
        ))
        return findings

    if not MERMAID_VENDOR_ENTRY.is_file():
        # Already reported by validate_mermaid_runtime(); avoid duplicating.
        return findings

    bundle_text = MERMAID_VENDOR_ENTRY.read_text(encoding="utf-8", errors="replace")
    if pinned not in bundle_text:
        findings.append(Finding(
            "ERROR", rel_version_file,
            f"Mermaid VERSION pin ({pinned}) was not found inside "
            f"{MERMAID_VENDOR_ENTRY.relative_to(ROOT).as_posix()}; the pin file "
            "and the vendored runtime have drifted out of sync",
        ))

    return findings


def _page_renders_mermaid(raw: str) -> bool:
    return bool(re.search(r"""class=["\'][^"\']*\bmermaid\b""", raw, re.IGNORECASE))


def validate_mermaid_csp_alignment(pages: list[Path]) -> list[Finding]:
    """Flag pages whose CSP class cannot legally style Mermaid's own output.

    Mermaid renders inline style="..." attributes and <style> blocks at
    runtime, per diagram, per page load. scripts/csp.py computes the
    style-src / style-src-attr hash allowlists by statically scanning built
    HTML, so a hash allowlist can never cover output Mermaid only generates
    in the browser. Until a page class carries 'unsafe-inline' for style
    directives (or diagrams are pre-rendered at build time instead), Mermaid
    diagrams on that page class will lose their theme styling and the
    browser console will show real CSP violations -- even though the
    diagram still parses correctly and the vendored bundle is current.

    This is WARN, not ERROR: it is a known, open architecture decision, not
    a regression this validator should block commits over by itself.
    Promote the affected branch to ERROR once a fix lands and is the
    intended permanent state.
    """
    findings: list[Finding] = []
    policies = build_policies()
    for path in pages:
        raw = path.read_text(encoding="utf-8", errors="replace")
        if not _page_renders_mermaid(raw):
            continue
        rel = path.relative_to(ROOT).as_posix()
        kind = page_class(path)
        policy = policies.get(kind, "")
        style_attr_directive = next(
            (part.strip() for part in policy.split(";")
             if part.strip().startswith("style-src-attr")),
            "",
        )
        if "unsafe-inline" not in style_attr_directive:
            findings.append(Finding(
                "WARN", rel,
                f"page renders live Mermaid diagrams under the {kind!r} CSP "
                "class, which only allow-lists static style hashes; Mermaid's "
                "runtime-generated inline styles will be blocked and diagrams "
                "will render without theme styling (open architecture "
                "decision, not yet fixed)",
            ))
    return findings


# Single class for all findings; severity drives behavior.
class Finding:
    __slots__ = ("severity", "page", "msg")

    def __init__(self, severity: str, page: str, msg: str):
        self.severity = severity
        self.page = page
        self.msg = msg


def check_em_dashes(path: Path, raw: str) -> list[Finding]:
    """
    Scan for em dashes (U+2014, &mdash;, &#8212;) outside allowed contexts.

    Allowed contexts (no finding raised):
      - HTML comments          (<!-- ... -->)
      - <script> blocks        (code / JS comments are not user-facing copy)
      - <style> blocks
      - <pre> blocks
      - <div class="mermaid"> / <pre class="mermaid"> blocks
      - Lines containing an <h1>–<h6> tag  (heading separator is brand-approved)
      - Lines containing a <title> tag
      - Lines with og:title / twitter:title / og:image:alt / twitter:image:alt
      - Lines containing the builder-sig class
    """
    rel = path.relative_to(ROOT).as_posix()
    findings: list[Finding] = []
    lines = raw.splitlines()

    in_comment = False
    in_script = False
    in_pre = False
    in_style = False
    in_mermaid = False

    for lineno, line in enumerate(lines, 1):
        # Update block-open state BEFORE evaluating the line so that the
        # opening tag line itself is treated as part of the block.
        if not in_comment and "<!--" in line:
            in_comment = True
        if not in_script and re.search(r"<script[\s>]", line, re.IGNORECASE):
            in_script = True
        if not in_pre and re.search(r"<pre[\s>]", line, re.IGNORECASE):
            in_pre = True
        if not in_style and re.search(r"<style[\s>]", line, re.IGNORECASE):
            in_style = True
        if not in_mermaid and re.search(r'class="[^"]*\bmermaid\b', line, re.IGNORECASE):
            in_mermaid = True

        # Is this line inside a block where em dashes are structurally expected?
        in_block = in_comment or in_script or in_pre or in_style or in_mermaid

        # Per-line tag patterns that permit an em dash regardless of block state
        line_allowed = (
            in_block
            or re.search(r"</?h[1-6][\s>]", line, re.IGNORECASE)
            or re.search(r"<title[\s>]", line, re.IGNORECASE)
            or re.search(
                r'property="og:title"|property="twitter:title"'
                r'|name="twitter:title"'
                r'|property="og:image:alt"|name="og:image:alt"'
                r'|property="twitter:image:alt"|name="twitter:image:alt"',
                line, re.IGNORECASE,
            )
            or "builder-sig" in line
        )

        if not line_allowed and EM_DASH_RE.search(line):
            findings.append(
                Finding(
                    "ERROR", rel,
                    f"em dash in body copy at line {lineno}: {line.strip()[:100]}",
                )
            )

        # Update block-close state AFTER evaluating the line
        if in_comment and "-->" in line:
            in_comment = False
        if in_script and re.search(r"</script>", line, re.IGNORECASE):
            in_script = False
        if in_pre and re.search(r"</pre>", line, re.IGNORECASE):
            in_pre = False
        if in_style and re.search(r"</style>", line, re.IGNORECASE):
            in_style = False
        if in_mermaid and re.search(r"</div>|</pre>", line, re.IGNORECASE):
            in_mermaid = False

    return findings


def validate_brand_theme_metadata(location: str, parser: TagCounter) -> list[Finding]:
    """Validate the head metadata used by the Glee and AskJamie controls."""
    brand_classes = sorted(set(parser.body_classes) & set(BRAND_THEME_CONTRACT))
    if not brand_classes:
        return []

    findings: list[Finding] = []
    if len(brand_classes) > 1:
        findings.append(
            Finding(
                "ERROR",
                location,
                "conflicting brand body classes: " + ", ".join(brand_classes),
            )
        )
        return findings

    brand_class = brand_classes[0]
    contract = BRAND_THEME_CONTRACT[brand_class]
    brand_name = contract["name"]
    expected_by_media = {
        THEME_COLOR_MEDIA["light"]: contract["light"],
        THEME_COLOR_MEDIA["dark"]: contract["dark"],
    }
    entries_by_media: dict[str, list[dict[str, str]]] = {}
    for entry in parser.theme_colors:
        entries_by_media.setdefault(entry["media"].strip(), []).append(entry)

    for media in THEME_COLOR_MEDIA.values():
        entries = entries_by_media.get(media, [])
        if not entries:
            findings.append(
                Finding(
                    "ERROR",
                    location,
                    f"{brand_name} page missing theme-color metadata for media={media!r}",
                )
            )
            continue
        if len(entries) > 1:
            findings.append(
                Finding(
                    "ERROR",
                    location,
                    f"{brand_name} page has {len(entries)} theme-color metadata entries for media={media!r}; expected exactly one",
                )
            )
        expected = expected_by_media[media]
        actual = entries[0]["content"].strip()
        if actual.lower() != expected:
            findings.append(
                Finding(
                    "ERROR",
                    location,
                    f"{brand_name} theme-color for media={media!r} is {actual!r}; expected {expected!r}",
                )
            )

    unexpected_media = sorted(set(entries_by_media) - set(expected_by_media))
    for media in unexpected_media:
        for entry in entries_by_media[media]:
            findings.append(
                Finding(
                    "ERROR",
                    location,
                    f"{brand_name} has unexpected theme-color metadata media={media!r} value={entry['content'].strip()!r}",
                )
            )

    color_scheme_values = parser.meta.get("color-scheme", [])
    if not color_scheme_values:
        findings.append(
            Finding(
                "ERROR",
                location,
                f"{brand_name} page missing color-scheme metadata; expected {contract['colorScheme']!r}",
            )
        )
    else:
        normalized_schemes = [" ".join(value.split()) for value in color_scheme_values]
        if len(normalized_schemes) != 1 or normalized_schemes[0] != contract["colorScheme"]:
            actual = ", ".join(repr(value) for value in color_scheme_values)
            findings.append(
                Finding(
                    "ERROR",
                    location,
                    f"{brand_name} color-scheme metadata is {actual}; expected exactly {contract['colorScheme']!r}",
                )
            )

    return findings


def validate_page(
    path: Path,
    sitemap_urls: set[str],
    sitemap_entries: dict[str, str | None],
    expected_theme_url: str | None,
    expected_script_urls: dict[str, str | None],
    manifest_page: dict | None = None,
    locale_page: dict | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    rel = path.relative_to(ROOT).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")

    # --- raw-string brand checks (don't need parsed DOM) ---
    if "Precision. Power. Presence" in raw or "Precision · Power · Presence" in raw:
        findings.append(Finding("ERROR", rel, "old tagline 'Power. Presence.' found — must be 'Precision · Protocol · Promptcraft'"))

    # A malformed closing annotation such as `</div> /container` is parsed as
    # visible body text. Keep these template labels inside HTML comments.
    for match in re.finditer(
        r"</[a-z][\w:-]*>\s+/(?:[.#])?[A-Za-z][\w.-]*(?=\s|$)",
        raw,
        re.IGNORECASE,
    ):
        findings.append(
            Finding(
                "ERROR",
                rel,
                f"leaked closing annotation rendered as body text: {match.group(0).strip()!r}",
            )
        )

    # A malformed section-marker comment such as `</section>\nLABEL TEXT\n<section`
    # is parsed as visible orphaned body text between sections (the opening-side
    # counterpart to the closing-annotation check above -- same root cause,
    # different flavor: `<!-- LABEL -->` losing its comment delimiters). Keep
    # these template labels inside HTML comments.
    for match in re.finditer(
        r"</section>\s*\n[ \t]*([^\s<][^\n]*?)[ \t]*\n\s*<",
        raw,
    ):
        findings.append(
            Finding(
                "ERROR",
                rel,
                f"leaked section-marker annotation rendered as body text: {match.group(1)!r}",
            )
        )

    # P3 (no superscript) inside <title> or <meta ...>
    for m in re.finditer(r"<(title|meta)[^>]*>", raw):
        chunk = m.group(0)
        if re.search(r"\bP3\b", chunk) and "P³" not in chunk:
            # ignore github.com/OKHP3 path occurrences (legitimate org handle)
            if "github.com/OKHP3" not in chunk and "OKHP3" not in chunk:
                findings.append(Finding("ERROR", rel, f"'P3' without superscript in {m.group(1)} tag — brand violation"))

    # footer brand name: must be OverKill&nbsp;Hill&nbsp;P³™ (not missing ™ or prefixed with "The ")
    if re.search(r"<h3>OverKill&nbsp;Hill&nbsp;P³</h3>", raw):
        findings.append(Finding("ERROR", rel, "footer brand name missing ™ — should be 'OverKill&nbsp;Hill&nbsp;P³™'"))
    if re.search(r"<h3>The OverKill&nbsp;Hill&nbsp;P³", raw):
        findings.append(Finding("WARN", rel, "footer brand name has 'The ' prefix — canonical form has no 'The'"))

    # GA4 tag presence
    if "G-VJ1BKXS27H" not in raw:
        findings.append(Finding("WARN", rel, "GA4 tag (G-VJ1BKXS27H) not found"))

    # og:title comma-separator (brand standard is middot · or pipe |, not comma)
    m_og = re.search(r'property="og:title"\s+content="([^"]+)"', raw)
    if m_og:
        og_val = m_og.group(1)
        # only flag if it looks like the middot terms but uses comma between them
        if re.search(r"Precision,\s*Protocol", og_val):
            findings.append(Finding("ERROR", rel, f"og:title uses comma between brand terms — use middot · (found: {og_val!r})"))

    # placeholder hrefs
    for m in re.finditer(r'href="(#|javascript:[^"]*|)"', raw):
        # bare "#" anchor used as a placeholder (not a real fragment) — flag.
        # but allow href="#main" / href="#protocols" etc (fragments to real ids)
        href = m.group(1)
        if href in ("", "#"):
            findings.append(Finding("WARN", rel, f"placeholder href={href!r}"))
        elif href.startswith("javascript:"):
            findings.append(Finding("ERROR", rel, f"javascript: href found ({href!r})"))

    # --- em dash voice check ---
    findings.extend(check_em_dashes(path, raw))

    # --- parsed DOM checks ---
    parser = TagCounter()
    try:
        parser.feed(raw)
    except Exception as exc:  # html.parser is forgiving but be defensive
        findings.append(Finding("WARN", rel, f"HTML parser exception: {exc}"))
        return findings

    findings.extend(validate_brand_theme_metadata(rel, parser))
    findings.extend(validate_generated_seo(
        path,
        parser,
        manifest_page,
        locale_page,
        sitemap_entries,
    ))

    if not parser.title:
        findings.append(Finding("ERROR", rel, "missing <title>"))
    if not parser.has_meta_description:
        findings.append(Finding("ERROR", rel, "missing meta description"))
    if not parser.has_canonical:
        findings.append(Finding("WARN", rel, "missing canonical link"))
    if parser.h1_count == 0:
        findings.append(Finding("ERROR", rel, "no <h1> found"))
    elif parser.h1_count > 1:
        findings.append(Finding("WARN", rel, f"{parser.h1_count} <h1> elements (should be 1)"))
    if not parser.has_jsonld:
        findings.append(Finding("WARN", rel, "no JSON-LD structured data"))

    # Shared stylesheet cache-busting. A content hash changes whenever theme.css
    # changes, making browsers request the responsive rules released with it.
    theme_refs = [href for href in parser.stylesheet_refs if is_asset_ref(href, THEME_STYLESHEET_PATH)]
    if expected_theme_url is None:
        findings.append(Finding("ERROR", rel, "shared stylesheet file is missing"))
    elif len(theme_refs) != 1:
        findings.append(
            Finding(
                "ERROR",
                rel,
                f"expected exactly one shared stylesheet reference, found {len(theme_refs)}",
            )
        )
    elif theme_refs[0] != expected_theme_url:
        findings.append(
            Finding(
                "ERROR",
                rel,
                f"stale stylesheet reference {theme_refs[0]!r}; expected {expected_theme_url!r}",
            )
        )

    # Shared script cache-busting. app.js is site-wide and must have exactly
    # one current reference on every page. Mermaid is loaded only on diagram
    # pages, but any reference must likewise use its current content hash.
    for script_path in SHARED_SCRIPT_PATHS:
        script_refs = [
            src for src in parser.script_refs if is_asset_ref(src, script_path)
        ]
        expected_script_url = expected_script_urls[script_path]
        script_name = Path(script_path).name

        if expected_script_url is None:
            findings.append(Finding("ERROR", rel, f"shared script file is missing: {script_name}"))
        elif script_path == APP_SCRIPT_PATH and len(script_refs) != 1:
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    f"expected exactly one shared app.js reference, found {len(script_refs)}",
                )
            )
        elif len(script_refs) > 1:
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    f"expected at most one shared {script_name} reference, found {len(script_refs)}",
                )
            )
        elif script_refs and script_refs[0] != expected_script_url:
            findings.append(
                Finding(
                    "ERROR",
                    rel,
                    f"stale shared script reference {script_refs[0]!r}; expected {expected_script_url!r}",
                )
            )

    # sitemap inclusion (non-noindex, non-utility pages only)
    canonical_url = SITE_ORIGIN + html_to_route(path)
    if not parser.is_noindex and rel not in ("404.html", "under-construction.html"):
        if canonical_url not in sitemap_urls:
            findings.append(Finding("ERROR", rel, f"missing from sitemap.xml ({canonical_url})"))

    # noindex pages must NOT be in sitemap
    if parser.is_noindex and canonical_url in sitemap_urls:
        findings.append(Finding("ERROR", rel, f"noindex page listed in sitemap.xml — remove it ({canonical_url})"))

    # internal link + asset existence
    for ref in parser.asset_refs:
        target = resolve_internal(ref, path)
        if target is not None and not target_exists(target):
            findings.append(Finding("ERROR", rel, f"broken asset reference: {ref}"))

    for a in parser.anchors:
        href = a["href"]
        target = resolve_internal(href, path)
        if target is not None and not target_exists(target):
            # ignore pure-fragment hrefs (no path)
            if not href.startswith("#"):
                findings.append(Finding("ERROR", rel, f"broken internal link: {href}"))

        # external target=_blank must carry rel=noopener (or noreferrer)
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and "overkillhill.com" not in parsed.netloc:
            if a["target"] == "_blank" and "noopener" not in a["rel"]:
                findings.append(Finding("ERROR", rel, f"external target=_blank without rel=noopener: {href}"))

    return findings


def run_mtb_version_check() -> int:
    """Run check-mtb-version.py and stream its output. Returns its exit code."""
    script = Path(__file__).resolve().parent / "check-mtb-version.py"
    print("── MTB Version Check ──────────────────────────────────────────────")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.returncode


def run_banner_check() -> int:
    """Run check-banner.py and stream its output. Returns its exit code."""
    script = Path(__file__).resolve().parent / "check-banner.py"
    print("\u2500\u2500 Banner Consistency Check \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.returncode


def run_voice_lint() -> int:
    """Run the voice-lint baseline gate and stream its output."""
    script = Path(__file__).resolve().parent / "lint-voice.py"
    baseline = Path(__file__).resolve().parent / "voice-lint-baseline.json"
    print("\u2500\u2500 Voice Lint \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    result = subprocess.run(
        [sys.executable, str(script), "--baseline", str(baseline)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.returncode


def validate_generated_theme_controls() -> list[Finding]:
    """Ensure the checked-in browser constants match the reviewed contract."""
    script = ROOT / "scripts" / "generate-theme-controls.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return []
    detail = (result.stdout + result.stderr).strip()
    return [
        Finding(
            "ERROR",
            "assets/js/app.js",
            detail or "generated browser theme constants are stale",
        )
    ]


def main() -> int:
    sitemap_entries = load_sitemap_entries()
    sitemap_urls = set(sitemap_entries)
    if not sitemap_urls:
        print("WARN: sitemap.xml not found or empty.")

    pages = find_html_files()
    print(f"Validating {len(pages)} HTML pages…\n")

    manifest_pages, manifest_findings = load_source_manifest()
    locale_contract, locale_findings = load_locale_seo_contract()
    manifest_by_path = {
        page.get("path"): page
        for page in manifest_pages
        if isinstance(page.get("path"), str)
    }
    all_findings: list[Finding] = []
    all_findings.extend(validate_generated_theme_controls())
    all_findings.extend(manifest_findings)
    all_findings.extend(locale_findings)
    all_findings.extend(validate_sitemap_duplicates())
    all_findings.extend(validate_source_seo_contract(manifest_pages))
    all_findings.extend(validate_article_jsonld_source(manifest_pages, sitemap_entries))
    all_findings.extend(validate_organization_source())
    all_findings.extend(validate_heat_guide_chain(manifest_pages))
    all_findings.extend(
        validate_writing_release_alignment(
            FEATURED_WRITING_SOURCE,
            FEATURED_ARTICLE_SOURCE,
        )
    )
    all_findings.extend(
        validate_writing_release_alignment(
            FEATURED_WRITING_GENERATED,
            FEATURED_ARTICLE_GENERATED,
        )
    )
    all_findings.extend(validate_sitemap_inventory(sitemap_urls))
    all_findings.extend(validate_csp_hashes(pages))
    all_findings.extend(validate_mermaid_runtime(pages))
    all_findings.extend(validate_mermaid_version_pin(pages))
    all_findings.extend(validate_mermaid_csp_alignment(pages))
    expected_theme_url = current_content_hashed_url(THEME_STYLESHEET_PATH)
    expected_script_urls = {
        script_path: current_content_hashed_url(script_path)
        for script_path in SHARED_SCRIPT_PATHS
    }
    if expected_theme_url is None:
        all_findings.append(
            Finding(
                "ERROR",
                "assets/css/theme.css",
                "shared stylesheet is missing; cannot validate cache fingerprint",
            )
        )
    for script_path, expected_script_url in expected_script_urls.items():
        if expected_script_url is None:
            all_findings.append(
                Finding(
                    "ERROR",
                    script_path.lstrip("/"),
                    "shared script is missing; cannot validate cache fingerprint",
                )
            )
    for path in pages:
        all_findings.extend(
            validate_page(
                path,
                sitemap_urls,
                sitemap_entries,
                expected_theme_url,
                expected_script_urls,
                manifest_by_path.get(path.relative_to(ROOT).as_posix()),
                locale_contract.get(path.relative_to(ROOT).as_posix()),
            )
        )

    errors = [f for f in all_findings if f.severity == "ERROR"]
    warnings = [f for f in all_findings if f.severity == "WARN"]

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for f in errors:
            print(f"  ✖ {f.page}: {f.msg}")
        print()
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for f in warnings:
            print(f"  ! {f.page}: {f.msg}")
        print()

    if not errors and not warnings:
        print("✓ all clean.")
    elif not errors:
        print(f"✓ no errors ({len(warnings)} warnings).")
    else:
        print(f"✖ {len(errors)} error(s), {len(warnings)} warning(s).")

    print()
    mtb_exit = run_mtb_version_check()

    print()
    banner_exit = run_banner_check()

    print()
    voice_exit = run_voice_lint()

    return 1 if (errors or mtb_exit != 0 or banner_exit != 0 or voice_exit != 0) else 0


if __name__ == "__main__":
    sys.exit(main())

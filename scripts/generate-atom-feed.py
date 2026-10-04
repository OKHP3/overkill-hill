#!/usr/bin/env python3
"""Generate a standalone Atom feed from published English Article sources."""

from __future__ import annotations

import argparse
import json
import re
import runpy
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# The site builder owns the published Article route boundary. Load only its
# import-safe definitions; its __main__ build path is not invoked here.
BUILD_SITE = runpy.run_path(str(SCRIPT_DIR / "build-site.py"))
is_indexable_article = BUILD_SITE["is_indexable_article"]
SITE_ORIGIN = BUILD_SITE["SITE_ORIGIN"].rstrip("/")

ATOM_NS = "http://www.w3.org/2005/Atom"
XML_NS = "http://www.w3.org/XML/1998/namespace"
ATOM = f"{{{ATOM_NS}}}"
FEED_ID = f"{SITE_ORIGIN}/writings/"
FEED_TITLE = "OverKill Hill P³™ — Writings"
ORGANIZATION_ID = f"{SITE_ORIGIN}/#organization"
SOURCE_LANGUAGES = frozenset({"en", "en-us"})
# Locale page roots present in the published and draft site tree.
SITE_LOCALE_ROUTE_PREFIXES = frozenset({"de", "en-gb", "es", "es-mx", "fr"})

DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
RFC3339 = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


class FeedSourceError(ValueError):
    """Raised when a feed source is missing or does not meet its contract."""


def _has_locale_route_prefix(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.strip().replace("\\", "/")
    path = urlsplit(normalized).path
    first_segment = next((part for part in path.split("/") if part), "")
    return first_segment.casefold() in SITE_LOCALE_ROUTE_PREFIXES


@dataclass(frozen=True)
class ParsedDate:
    atom_value: str
    instant: datetime


@dataclass(frozen=True)
class AtomAuthor:
    name: str
    uri: str | None = None


@dataclass(frozen=True)
class AtomEntry:
    canonical: str
    title: str
    published: ParsedDate
    updated: ParsedDate
    authors: tuple[AtomAuthor, ...]
    summary: str | None


def _valid_xml_text(value: str, context: str) -> str:
    allowed = (
        codepoint in (0x9, 0xA, 0xD)
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
        for codepoint in map(ord, value)
    )
    if not all(allowed):
        raise FeedSourceError(f"{context} contains a character forbidden by XML 1.0")
    return value


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeedSourceError(f"{context} is missing or is not text")
    return _valid_xml_text(value.strip(), context)


def _parse_atom_date(value: Any, field: str, route: str) -> ParsedDate:
    context = f"{route}: Article JSON-LD {field}"
    if not isinstance(value, str) or not value.strip():
        raise FeedSourceError(f"{context} is missing")

    raw = value.strip()
    if DATE_ONLY.fullmatch(raw):
        try:
            parsed_date = date.fromisoformat(raw)
        except ValueError as exc:
            raise FeedSourceError(f"{context} is not a valid calendar date: {raw!r}") from exc
        # Atom requires an RFC3339 date-time. Keep the authored calendar date
        # unchanged and use UTC midnight only as the required time encoding.
        instant = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
        return ParsedDate(f"{parsed_date.isoformat()}T00:00:00Z", instant)

    if not RFC3339.fullmatch(raw):
        raise FeedSourceError(f"{context} is not an RFC3339 timestamp or YYYY-MM-DD date: {raw!r}")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise FeedSourceError(f"{context} is malformed: {raw!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FeedSourceError(f"{context} must include a timezone: {raw!r}")
    return ParsedDate(raw, parsed.astimezone(timezone.utc))


def is_feed_candidate(page: dict[str, Any]) -> bool:
    """Apply the Article, source-language, locale-route, and status gates."""
    if any(
        _has_locale_route_prefix(page.get(field))
        for field in ("route", "path", "canonical")
    ):
        return False
    lang = str(page.get("lang", "")).strip().casefold()
    if lang not in SOURCE_LANGUAGES:
        return False
    if "status" in page and str(page["status"]).strip().lower() != "published":
        return False
    return bool(is_indexable_article(page))


def _canonical_id(page: dict[str, Any]) -> str:
    route = str(page.get("route") or "<unknown route>")
    canonical = _required_text(page.get("canonical"), f"{route}: canonical URL")
    parsed = urlsplit(canonical)
    site = urlsplit(SITE_ORIGIN)
    if (
        parsed.scheme != "https"
        or parsed.netloc != site.netloc
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        raise FeedSourceError(
            f"{route}: canonical URL must be an absolute HTTPS URL on {site.netloc} "
            f"without a query or fragment: {canonical!r}"
        )
    return canonical


def _source_extras_path(root: Path, page: dict[str, Any]) -> Path:
    route = str(page.get("route") or "<unknown route>")
    raw_path = page.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise FeedSourceError(f"{route}: source manifest path is missing")
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise FeedSourceError(f"{route}: source manifest path is not repository-relative: {raw_path!r}")

    pages_root = (root / "site-src" / "pages").resolve()
    extras = (pages_root / relative.with_suffix(".extras.html")).resolve()
    try:
        extras.relative_to(pages_root)
    except ValueError as exc:
        raise FeedSourceError(f"{route}: Article source resolves outside site-src/pages") from exc
    return extras


def _is_article_node(value: dict[str, Any]) -> bool:
    node_type = value.get("@type")
    return node_type == "Article" or (
        isinstance(node_type, list) and "Article" in node_type
    )


def _walk_article_nodes(value: Any):
    if isinstance(value, dict):
        if _is_article_node(value):
            yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _walk_article_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_article_nodes(child)


def _identity_values(article: dict[str, Any]) -> set[str]:
    identities: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            identities.add(value.strip())
        elif isinstance(value, dict):
            for key in ("@id", "url"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    identities.add(candidate.strip())

    for key in ("@id", "url", "mainEntityOfPage"):
        add(article.get(key))
    return identities


def _article_authors(article: dict[str, Any], page: dict[str, Any]) -> tuple[AtomAuthor, ...]:
    source_authors = article.get("author")
    authors = source_authors if isinstance(source_authors, list) else [source_authors]
    if not authors or authors == [None]:
        raise FeedSourceError(f"{page.get('route')}: Article JSON-LD author is missing")

    result: list[AtomAuthor] = []
    for index, source in enumerate(authors, start=1):
        context = f"{page.get('route')}: Article JSON-LD author {index}"
        if isinstance(source, str):
            name_value = source
            uri_value = None
        elif isinstance(source, dict):
            name_value = source.get("name")
            uri_value = source.get("url") or source.get("@id")
            if not name_value and source.get("@id") == ORGANIZATION_ID:
                name_value = page.get("meta:author")
        else:
            raise FeedSourceError(f"{context} is not a named author")

        name = _required_text(name_value, f"{context} name")
        uri = None
        if uri_value is not None:
            uri = _required_text(uri_value, f"{context} URI")
        result.append(AtomAuthor(name=name, uri=uri))
    return tuple(result)


def article_entry_from_extras(page: dict[str, Any], extras_html: str) -> AtomEntry:
    """Parse the Article JSON-LD whose identity matches the page canonical."""
    route = str(page.get("route") or "<unknown route>")
    canonical = _canonical_id(page)
    soup = BeautifulSoup(extras_html, "html.parser")
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    if not scripts:
        raise FeedSourceError(f"{route}: source extras contain no JSON-LD")

    article_nodes: list[dict[str, Any]] = []
    for index, script in enumerate(scripts, start=1):
        raw = script.string or script.get_text()
        try:
            document = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise FeedSourceError(f"{route}: JSON-LD block {index} is malformed") from exc
        article_nodes.extend(_walk_article_nodes(document))

    matches = [node for node in article_nodes if canonical in _identity_values(node)]
    if len(matches) != 1:
        raise FeedSourceError(
            f"{route}: expected one Article JSON-LD node for canonical {canonical!r}; "
            f"found {len(matches)}"
        )
    article = matches[0]

    language = article.get("inLanguage")
    if isinstance(language, str) and language.strip():
        normalized_language = language.strip().casefold()
        if normalized_language not in SOURCE_LANGUAGES:
            raise FeedSourceError(
                f"{route}: Article JSON-LD language is not English: {language!r}"
            )

    title = _required_text(article.get("headline"), f"{route}: Article headline")
    published = _parse_atom_date(article.get("datePublished"), "datePublished", route)
    updated = _parse_atom_date(article.get("dateModified"), "dateModified", route)
    authors = _article_authors(article, page)

    summary_value = article.get("description") or page.get("meta:description")
    summary = None
    if summary_value is not None:
        summary = _required_text(summary_value, f"{route}: Article summary")

    return AtomEntry(
        canonical=canonical,
        title=title,
        published=published,
        updated=updated,
        authors=authors,
        summary=summary,
    )


def load_entries(root: Path = ROOT) -> list[AtomEntry]:
    root = Path(root).resolve()
    manifest_path = root / "site-src" / "pages.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FeedSourceError(f"cannot read source page manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise FeedSourceError(f"unsupported or malformed source page manifest: {manifest_path}")
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise FeedSourceError(f"source page manifest has no pages list: {manifest_path}")

    entries: list[AtomEntry] = []
    seen_ids: set[str] = set()
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            raise FeedSourceError(f"source page manifest record {index} is not an object")
        if not is_feed_candidate(page):
            continue

        canonical = _canonical_id(page)
        if canonical in seen_ids:
            raise FeedSourceError(f"duplicate canonical Article ID in source manifest: {canonical}")
        seen_ids.add(canonical)

        extras_path = _source_extras_path(root, page)
        try:
            extras_html = extras_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FeedSourceError(
                f"{page.get('route')}: cannot read Article source extras: {extras_path}"
            ) from exc
        entries.append(article_entry_from_extras(page, extras_html))

    if not entries:
        raise FeedSourceError("source manifest contains no published, indexable English Articles")

    # Stable recency ordering: latest publication first, canonical ID breaks ties.
    entries.sort(key=lambda entry: entry.canonical)
    entries.sort(key=lambda entry: entry.published.instant, reverse=True)
    return entries


def _atom_child(parent: ET.Element, name: str, text: str) -> ET.Element:
    child = ET.SubElement(parent, ATOM + name)
    child.text = text
    return child


def _validate_atom_tree(feed: ET.Element) -> None:
    if feed.tag != ATOM + "feed":
        raise FeedSourceError("generated document root is not an Atom feed")
    for name in ("id", "title", "updated"):
        if len(feed.findall(ATOM + name)) != 1 or not (feed.findtext(ATOM + name) or "").strip():
            raise FeedSourceError(f"generated Atom feed must have exactly one non-empty {name}")

    entries = feed.findall(ATOM + "entry")
    if not entries:
        raise FeedSourceError("generated Atom feed contains no entries")
    identifiers: set[str] = set()
    for entry in entries:
        for name in ("id", "title", "updated"):
            if len(entry.findall(ATOM + name)) != 1 or not (
                entry.findtext(ATOM + name) or ""
            ).strip():
                raise FeedSourceError(f"generated Atom entry must have exactly one non-empty {name}")
        identifier = entry.findtext(ATOM + "id", "")
        if identifier in identifiers:
            raise FeedSourceError(f"generated Atom feed contains duplicate entry ID: {identifier}")
        identifiers.add(identifier)
        if not entry.findall(ATOM + "author"):
            raise FeedSourceError(f"generated Atom entry has no author: {identifier}")


def render_atom_feed(entries: list[AtomEntry]) -> bytes:
    if not entries:
        raise FeedSourceError("cannot render an Atom feed without entries")
    latest = max(entries, key=lambda entry: (entry.updated.instant, entry.canonical))

    ET.register_namespace("", ATOM_NS)
    feed = ET.Element(ATOM + "feed", {f"{{{XML_NS}}}lang": "en"})
    _atom_child(feed, "id", FEED_ID)
    _atom_child(feed, "title", FEED_TITLE)
    _atom_child(feed, "updated", latest.updated.atom_value)
    ET.SubElement(
        feed,
        ATOM + "link",
        {"rel": "alternate", "href": f"{SITE_ORIGIN}/writings/"},
    )

    for entry in entries:
        element = ET.SubElement(feed, ATOM + "entry")
        _atom_child(element, "id", entry.canonical)
        title = _atom_child(element, "title", entry.title)
        title.set("type", "text")
        ET.SubElement(
            element,
            ATOM + "link",
            {"rel": "alternate", "href": entry.canonical},
        )
        _atom_child(element, "published", entry.published.atom_value)
        _atom_child(element, "updated", entry.updated.atom_value)
        for author in entry.authors:
            author_element = ET.SubElement(element, ATOM + "author")
            _atom_child(author_element, "name", author.name)
            if author.uri:
                _atom_child(author_element, "uri", author.uri)
        if entry.summary is not None:
            summary = _atom_child(element, "summary", entry.summary)
            summary.set("type", "text")

    _validate_atom_tree(feed)
    return ET.tostring(feed, encoding="utf-8", xml_declaration=True) + b"\n"


def generate_atom_feed(root: Path = ROOT) -> bytes:
    return render_atom_feed(load_entries(root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="write Atom XML to this path (default: write to stdout)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare generated bytes with --output without writing",
    )
    args = parser.parse_args(argv)
    if args.check and not args.output:
        parser.error("--check requires --output")

    try:
        atom_xml = generate_atom_feed()
    except FeedSourceError as exc:
        print(f"Atom feed generation failed: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            current = args.output.read_bytes()
        except OSError as exc:
            print(f"Atom feed is stale: cannot read {args.output}: {exc}", file=sys.stderr)
            return 1
        if current != atom_xml:
            print(f"Atom feed is stale: {args.output}", file=sys.stderr)
            return 1
        print(f"Atom feed verified: {args.output}")
        return 0

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(atom_xml)
    else:
        sys.stdout.buffer.write(atom_xml)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
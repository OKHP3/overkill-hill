"""Shared XML parsing for locale and site-wide sitemap validation."""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree


@dataclass(frozen=True)
class SitemapUrlEntry:
    """One URL record, retaining source position and any location defect."""

    position: int
    location: str | None
    lastmod: str | None
    issue: str | None


@dataclass(frozen=True)
class SitemapDocument:
    """Parsed sitemap locations and URL records without collapsing duplicates."""

    locations: tuple[str, ...]
    entries: tuple[SitemapUrlEntry, ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap_xml(text: str) -> SitemapDocument:
    """Parse a well-formed sitemap, preserving duplicate order and first lastmod."""
    root = ElementTree.fromstring(text)
    locations = tuple(
        element.text.strip()
        for element in root.iter()
        if _local_name(element.tag) == "loc"
        and element.text
        and element.text.strip()
    )

    entries: list[SitemapUrlEntry] = []
    url_nodes = [
        element for element in root.iter()
        if _local_name(element.tag) == "url"
    ]
    for position, url_node in enumerate(url_nodes, start=1):
        loc_nodes = [
            element for element in url_node.iter()
            if element is not url_node and _local_name(element.tag) == "loc"
        ]
        if len(loc_nodes) != 1:
            entries.append(SitemapUrlEntry(
                position,
                None,
                None,
                f"must contain exactly one <loc> element; found {len(loc_nodes)}",
            ))
            continue

        loc_node = loc_nodes[0]
        if list(loc_node):
            entries.append(SitemapUrlEntry(
                position, None, None, "has malformed markup inside <loc>"
            ))
            continue
        location = (loc_node.text or "").strip()
        if not location:
            entries.append(SitemapUrlEntry(position, None, None, "has an empty <loc> value"))
            continue

        lastmod_nodes = [
            element for element in url_node.iter()
            if element is not url_node and _local_name(element.tag) == "lastmod"
        ]
        lastmod_node = lastmod_nodes[0] if lastmod_nodes else None
        lastmod = (
            lastmod_node.text.strip()
            if lastmod_node is not None
            and not list(lastmod_node)
            and lastmod_node.text
            else None
        )
        entries.append(SitemapUrlEntry(position, location, lastmod, None))

    return SitemapDocument(locations, tuple(entries))

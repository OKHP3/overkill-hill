from __future__ import annotations

import importlib.util
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

GENERATOR_PATH = ROOT / "scripts" / "generate-atom-feed.py"
GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "atom_feed_generator", GENERATOR_PATH
)
if GENERATOR_SPEC is None or GENERATOR_SPEC.loader is None:
    raise ImportError(f"cannot load Atom feed generator: {GENERATOR_PATH}")
atom_feed = importlib.util.module_from_spec(GENERATOR_SPEC)
sys.modules[GENERATOR_SPEC.name] = atom_feed
GENERATOR_SPEC.loader.exec_module(atom_feed)


ATOM = "{http://www.w3.org/2005/Atom}"


def article_page(
    *,
    route: str = "/writings/example/",
    canonical: str = "https://overkillhill.com/writings/example/",
    lang: str = "en",
    robots: str = "index, follow",
    status: str | None = None,
) -> dict[str, str]:
    page = {
        "route": route,
        "canonical": canonical,
        "path": route.strip("/") + "/index.html",
        "lang": lang,
        "meta:og:type": "article",
        "meta:robots": robots,
        "meta:author": "OverKill Hill P³™",
        "meta:description": "A source description.",
    }
    if status is not None:
        page["status"] = status
    return page


def article_html(
    canonical: str = "https://overkillhill.com/writings/example/",
    *,
    published: str | None = "2026-05-01",
    modified: str | None = "2026-05-02",
    language: str | None = None,
) -> str:
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "url": canonical,
        "headline": "A title with <markup> & punctuation",
        "description": "A summary with <markup> & punctuation.",
        "datePublished": published,
        "dateModified": modified,
        "author": {"@type": "Person", "name": "Jamie Hill"},
    }
    if language is not None:
        article["inLanguage"] = language
    return (
        '<script type="application/ld+json">'
        + json.dumps(article, ensure_ascii=False)
        + "</script>"
    )


class AtomFeedGeneratorTests(unittest.TestCase):
    def test_candidate_filter_uses_indexability_english_and_publication_status(self) -> None:
        self.assertTrue(atom_feed.is_feed_candidate(article_page()))
        self.assertTrue(atom_feed.is_feed_candidate(article_page(lang="en-US")))
        self.assertFalse(
            atom_feed.is_feed_candidate(article_page(robots="noindex, follow"))
        )
        self.assertFalse(atom_feed.is_feed_candidate(article_page(lang="fr")))
        self.assertFalse(
            atom_feed.is_feed_candidate(article_page(status="draft"))
        )
        self.assertTrue(
            atom_feed.is_feed_candidate(article_page(status="published"))
        )

    def test_candidate_filter_rejects_en_gb_language_and_route(self) -> None:
        page = article_page(
            route="/en-gb/writings/example/",
            canonical="https://overkillhill.com/en-gb/writings/example/",
            lang="en-GB",
        )
        self.assertFalse(atom_feed.is_feed_candidate(page))

    def test_candidate_filter_rejects_localized_route_with_english_metadata(self) -> None:
        page = article_page(
            route="/fr/writings/example/",
            canonical="https://overkillhill.com/fr/writings/example/",
            lang="en",
        )
        self.assertFalse(atom_feed.is_feed_candidate(page))

    def test_candidate_filter_rejects_localized_source_path_with_english_metadata(self) -> None:
        page = article_page()
        page["path"] = "fr/writings/example/index.html"
        self.assertFalse(atom_feed.is_feed_candidate(page))

    def test_candidate_filter_rejects_localized_canonical_path_with_english_metadata(self) -> None:
        page = article_page(
            canonical="https://overkillhill.com/fr/writings/example/"
        )
        self.assertFalse(atom_feed.is_feed_candidate(page))

    def test_date_only_preserves_calendar_date_and_emits_atom_timestamp(self) -> None:
        parsed = atom_feed._parse_atom_date(
            "2026-05-01", "datePublished", "/writings/example/"
        )
        self.assertEqual(parsed.atom_value, "2026-05-01T00:00:00Z")
        self.assertEqual(parsed.instant.isoformat(), "2026-05-01T00:00:00+00:00")

    def test_malformed_or_missing_authored_dates_fail_explicitly(self) -> None:
        for value in (None, "", "2026-02-30", "2026-05-01T09:00:00"):
            with self.subTest(value=value):
                with self.assertRaises(atom_feed.FeedSourceError):
                    atom_feed._parse_atom_date(
                        value, "datePublished", "/writings/example/"
                    )

    def test_timezone_timestamp_is_preserved_and_compared_as_an_instant(self) -> None:
        parsed = atom_feed._parse_atom_date(
            "2026-05-01T09:30:00-05:00",
            "dateModified",
            "/writings/example/",
        )
        self.assertEqual(parsed.atom_value, "2026-05-01T09:30:00-05:00")
        self.assertEqual(parsed.instant.isoformat(), "2026-05-01T14:30:00+00:00")

    def test_matching_canonical_article_is_selected_from_nested_graph(self) -> None:
        page = article_page()
        primary = json.loads(
            article_html().removeprefix('<script type="application/ld+json">').removesuffix(
                "</script>"
            )
        )
        parent = {
            "@type": "Article",
            "url": "https://overkillhill.com/writings/parent/",
        }
        document = {"@graph": [primary, {"@type": "WebPage", "isPartOf": parent}]}
        html = (
            '<script type="application/ld+json">'
            + json.dumps(document, ensure_ascii=False)
            + "</script>"
        )

        entry = atom_feed.article_entry_from_extras(page, html)
        self.assertEqual(entry.canonical, page["canonical"])
        self.assertEqual(entry.title, "A title with <markup> & punctuation")
        self.assertEqual(entry.authors[0].name, "Jamie Hill")

    def test_missing_and_malformed_dates_in_article_jsonld_are_rejected(self) -> None:
        page = article_page()
        for field, value in (
            ("datePublished", None),
            ("dateModified", None),
            ("datePublished", "2026-02-30"),
            ("dateModified", "2026-02-30"),
            ("datePublished", "yesterday"),
        ):
            with self.subTest(field=field, value=value):
                dates = {"datePublished": "2026-05-01", "dateModified": "2026-05-02"}
                dates[field] = value
                with self.assertRaises(atom_feed.FeedSourceError):
                    atom_feed.article_entry_from_extras(
                        page,
                        article_html(
                            published=dates["datePublished"],
                            modified=dates["dateModified"],
                        ),
                    )

    def test_article_jsonld_rejects_en_gb_even_with_an_english_page_label(self) -> None:
        with self.assertRaises(atom_feed.FeedSourceError):
            atom_feed.article_entry_from_extras(
                article_page(), article_html(language="en-GB")
            )

    def test_rendered_document_is_well_formed_atom_and_escapes_source_text(self) -> None:
        entry = atom_feed.article_entry_from_extras(article_page(), article_html())
        output = atom_feed.render_atom_feed([entry])
        tree = ET.fromstring(output)
        self.assertEqual(tree.tag, ATOM + "feed")
        item = tree.find(ATOM + "entry")
        self.assertIsNotNone(item)
        self.assertEqual(item.findtext(ATOM + "title"), entry.title)
        self.assertEqual(item.findtext(ATOM + "summary"), entry.summary)
        self.assertEqual(item.findtext(ATOM + "id"), entry.canonical)
        self.assertEqual(item.findtext(ATOM + "published"), "2026-05-01T00:00:00Z")
        self.assertEqual(item.findtext(ATOM + "updated"), "2026-05-02T00:00:00Z")
        self.assertIsNotNone(item.find(ATOM + "author"))

    def test_repository_feed_is_deterministic_and_matches_eligible_manifest_pages(self) -> None:
        manifest = json.loads(
            (ROOT / "site-src" / "pages.json").read_text(encoding="utf-8")
        )
        expected_ids = {
            page["canonical"]
            for page in manifest["pages"]
            if atom_feed.is_feed_candidate(page)
        }

        first = atom_feed.generate_atom_feed(ROOT)
        second = atom_feed.generate_atom_feed(ROOT)
        self.assertEqual(first, second)

        source_entries = atom_feed.load_entries(ROOT)
        tree = ET.fromstring(first)
        rendered_entries = {
            entry.findtext(ATOM + "id"): entry
            for entry in tree.findall(ATOM + "entry")
        }
        actual_ids = set(rendered_entries)
        self.assertEqual(actual_ids, expected_ids)
        self.assertTrue(actual_ids)
        for source_entry in source_entries:
            rendered = rendered_entries[source_entry.canonical]
            self.assertEqual(
                rendered.findtext(ATOM + "published"),
                source_entry.published.atom_value,
            )
            self.assertEqual(
                rendered.findtext(ATOM + "updated"),
                source_entry.updated.atom_value,
            )
        latest = max(
            source_entries,
            key=lambda entry: (entry.updated.instant, entry.canonical),
        )
        self.assertEqual(tree.findtext(ATOM + "updated"), latest.updated.atom_value)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""
Build /assets/data/search-index.json from every indexable HTML page on the site.

- Walks the project root for *.html files.
- Skips files whose <meta name="robots"> contains "noindex".
- Skips known utility pages (404, under-construction).
- Extracts title, description, canonical URL, headings, and a plaintext body excerpt.
- For the article /writings/first-diagram-is-a-liar/ it also creates one entry
  per <section id="..."> and per <h2 id="..."> so deep links inside the article
  become independently searchable.

Re-run any time content changes:
    python3 scripts/build-search-index.py

Verify that the committed index is current without writing it:
    python3 scripts/build-search-index.py --check
"""

from __future__ import annotations

import json
import runpy
import os
import re
import subprocess
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from public_page_boundary import iter_public_html_files, is_public_page_path

PROJECT_STATUS = runpy.run_path(str(ROOT / "scripts/project-status.py"))
OUT = ROOT / "assets" / "data" / "search-index.json"
SITE = "https://overkillhill.com"

SKIP_FILES = {
    "404.html",
    "under-construction.html",
}

CATEGORY_RULES = [
    ("/writings/first-diagram-is-a-liar/v03/", "Field Guide"),
    ("/writings/first-diagram-is-a-liar/", "Article"),
    ("/writings/", "Writing"),
    ("/projects/", "Project"),
    ("/skillz-forge/", "Project"),
    ("/manifesto/", "Brand"),
    ("/universe/", "Brand"),
    ("/about/", "Brand"),
    ("/contact/", "Brand"),
    ("/legal/", "Brand"),
    ("/found-ry/", "Brand"),
    ("/prompt-forge/", "Brand"),
    ("/vault/", "Brand"),
]


def categorise(url_path: str) -> str:
    if url_path in ("/", ""):
        return "Home"
    for prefix, label in CATEGORY_RULES:
        if url_path.startswith(prefix):
            return label
    return "Page"


def iter_html_files(scan_root: Path | None = None):
    """Yield index candidates inside the shared published-page boundary."""
    scan_root = Path(scan_root) if scan_root is not None else ROOT
    yield from iter_public_html_files(scan_root)


class TextExtractor(HTMLParser):
    """Strip script/style/nav/footer/header and collect main-body text + headings."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe"}
    DROP_BY_CLASS = {"site-header", "site-footer", "primary-nav", "sub-nav",
                     "skip-link", "okh-skip-link", "sr-only", "okh-search-overlay",
                     "footer-bottom", "site-banner", "universe-generated"}

    # Self-closing / void HTML elements — never push to drop stack
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []   # stack of skipped (script/style/etc) tag names
        self._drop_stack: list[str] = []   # stack of dropped (header/nav/etc) tag names
        self._text_parts: list[str] = []
        self._h2_parts: list[tuple[str, str]] = []  # (id, text)
        self._h3_parts: list[str] = []
        self._current_heading: list[str] | None = None
        self._current_heading_id: str = ""
        self._current_heading_level: int = 0
        self.title: str = ""
        self._in_title = False

    @property
    def _skip_depth(self) -> int:
        return len(self._skip_stack)

    @property
    def _drop_depth(self) -> int:
        return len(self._drop_stack)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrd = dict(attrs)
        cls = attrd.get("class", "")
        cls_set = set(cls.split())

        if tag in self.VOID_TAGS:
            return

        if tag in self.SKIP_TAGS:
            self._skip_stack.append(tag)
            return
        if cls_set & self.DROP_BY_CLASS:
            self._drop_stack.append(tag)
            return
        if self._drop_depth:
            self._drop_stack.append(tag)
            return
        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = True
        elif tag in ("h2", "h3"):
            self._current_heading = []
            self._current_heading_id = attrd.get("id", "")
            self._current_heading_level = 2 if tag == "h2" else 3

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.VOID_TAGS:
            return
        # Pop matching skip frame (handle close of script/style/etc)
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            return
        # Keep nested markup inside dropped regions balanced so an inner div
        # cannot expose the remainder of the header or navigation.
        if self._drop_stack:
            if tag in self._drop_stack:
                while self._drop_stack:
                    if self._drop_stack.pop() == tag:
                        break
            return
        if self._drop_depth or self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        elif tag in ("h2", "h3") and self._current_heading is not None:
            text = re.sub(r"\s+", " ", "".join(self._current_heading)).strip()
            if text:
                if self._current_heading_level == 2:
                    self._h2_parts.append((self._current_heading_id, text))
                else:
                    self._h3_parts.append(text)
            self._current_heading = None

    def handle_data(self, data):
        if self._skip_depth or self._drop_depth:
            return
        if self._in_title:
            self.title += data
            return
        if self._current_heading is not None:
            self._current_heading.append(data)
        self._text_parts.append(data)

    def collected_text(self) -> str:
        text = " ".join(self._text_parts)
        return re.sub(r"\s+", " ", text).strip()


META_TAG_RE = re.compile(r"<meta\b([^>]*)/?>", re.I | re.S)
LINK_TAG_RE = re.compile(r"<link\b([^>]*)/?>", re.I | re.S)
ATTR_RE = re.compile(r"""([a-zA-Z][\w:-]*)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""")


def parse_attrs(attr_str: str) -> dict:
    out = {}
    for m in ATTR_RE.finditer(attr_str):
        key = m.group(1).lower()
        val = m.group(3) if m.group(3) is not None else (
            m.group(4) if m.group(4) is not None else m.group(5))
        out[key] = (val or "").strip()
    return out


def read_meta(html: str, key: str) -> str:
    """Attribute-order-agnostic meta/link reader.

    `key` is one of: "description", "robots", "canonical", "ogtype".
    """
    if key in ("description", "robots", "ogtype"):
        target_attr = "og:type" if key == "ogtype" else key
        match_key = "property" if key == "ogtype" else "name"
        for m in META_TAG_RE.finditer(html):
            attrs = parse_attrs(m.group(1))
            if attrs.get(match_key, "").lower() == target_attr.lower():
                return attrs.get("content", "").strip()
        return ""
    if key == "canonical":
        for m in LINK_TAG_RE.finditer(html):
            attrs = parse_attrs(m.group(1))
            rel = attrs.get("rel", "").lower().split()
            if "canonical" in rel:
                return attrs.get("href", "").strip()
        return ""
    return ""


def is_noindex(html: str) -> bool:
    """Return True if any robots-style meta tag declares noindex."""
    targets = {"robots", "googlebot", "bingbot", "slurp", "duckduckbot",
               "applebot", "yandex"}
    for m in META_TAG_RE.finditer(html):
        attrs = parse_attrs(m.group(1))
        name = attrs.get("name", "").lower()
        if name in targets and "noindex" in attrs.get("content", "").lower():
            return True
    return False


def url_for(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel.endswith("/index.html"):
        rel = rel[: -len("index.html")]
    if not rel.startswith("/"):
        rel = "/" + rel
    if rel == "/index.html":
        rel = "/"
    return rel


def excerpt(text: str, limit: int = 600) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Try to end on a sentence boundary
    last_period = cut.rfind(". ")
    if last_period > limit * 0.6:
        return cut[: last_period + 1]
    last_space = cut.rfind(" ")
    if last_space > 0:
        return cut[:last_space] + "…"
    return cut + "…"


def extract_article_sections(html: str, base_url: str, base_title: str) -> list[dict]:
    """For the long-form article, emit one entry per <section id="..."> with an h2 inside,
    plus per top-level <h2 id="...">."""
    out: list[dict] = []
    # Match sections with id
    for m in re.finditer(
        r'<section[^>]*\sid=["\']([^"\']+)["\'][^>]*>(.*?)</section>',
        html, re.S | re.I,
    ):
        sec_id = m.group(1)
        body = m.group(2)
        # Pull a title — first h2/h3 inside
        title_match = re.search(r"<h[23][^>]*>(.*?)</h[23]>", body, re.S | re.I)
        if title_match:
            sec_title = re.sub(r"<[^>]+>", "", title_match.group(1))
            sec_title = unescape(re.sub(r"\s+", " ", sec_title).strip())
        else:
            sec_title = sec_id.replace("-", " ").title()
        # Strip tags
        plain = re.sub(r"<script.*?</script>", " ", body, flags=re.S | re.I)
        plain = re.sub(r"<style.*?</style>", " ", plain, flags=re.S | re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = unescape(re.sub(r"\s+", " ", plain).strip())
        if len(plain) < 60:
            continue
        out.append({
            "url": f"{base_url}#{sec_id}",
            "title": f"{sec_title} — {base_title}",
            "category": "Article Section",
            "description": excerpt(plain, 220),
            "headings": [],
            "body": excerpt(plain, 800),
            "parent": base_url,
        })
    # Also catch standalone <h2 id="..."> not inside a <section id="...">
    for m in re.finditer(
        r'<h2[^>]*\sid=["\']([^"\']+)["\'][^>]*>(.*?)</h2>',
        html, re.S | re.I,
    ):
        h_id = m.group(1)
        # If we already produced this anchor as a section, skip
        if any(e["url"].endswith(f"#{h_id}") for e in out):
            continue
        h_title = re.sub(r"<[^>]+>", "", m.group(2))
        h_title = unescape(re.sub(r"\s+", " ", h_title).strip())
        if not h_title:
            continue
        # Grab the text immediately following the heading until the next h2
        rest = html[m.end():]
        next_h2 = re.search(r"<h2", rest, re.I)
        chunk = rest[: next_h2.start()] if next_h2 else rest[:4000]
        plain = re.sub(r"<script.*?</script>", " ", chunk, flags=re.S | re.I)
        plain = re.sub(r"<style.*?</style>", " ", plain, flags=re.S | re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = unescape(re.sub(r"\s+", " ", plain).strip())
        if len(plain) < 80:
            continue
        out.append({
            "url": f"{base_url}#{h_id}",
            "title": f"{h_title} — {base_title}",
            "category": "Article Section",
            "description": excerpt(plain, 220),
            "headings": [],
            "body": excerpt(plain, 800),
            "parent": base_url,
        })
    return out


class SectionFragments(HTMLParser):
    """Locate complete elements using parser events, including nested blocks."""

    def __init__(self, html: str, tag: str):
        super().__init__(convert_charrefs=True)
        self.html = html
        self.tag = tag.lower()
        self.offsets = [0]
        for line in html.split("\n"):
            self.offsets.append(self.offsets[-1] + len(line) + 1)
        self.stack = []
        self.fragments = {}
        self.feed(html)

    def source_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == self.tag:
            self.stack.append((dict(attrs), self.source_offset() + len(self.get_starttag_text())))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag == self.tag and self.stack:
            attrs, start = self.stack.pop()
            if attrs.get("id"):
                self.fragments.setdefault(attrs["id"], (attrs, self.html[start:self.source_offset()]))


def extract_div_sections(html: str, base_url: str, base_title: str,
                          section_ids: list[str], tag: str = "div",
                          category: str = "Project") -> list[dict]:
    """Emit one search entry per named block element with the given id.

    `tag` controls which HTML element to match (default "div"; also accepts
    "section", "article", etc.).  `category` sets the search result category
    label (default "Project").

    Used for project pages that organize sections as divs rather than <section>,
    and for Prompt Forge pages that use <section> / <article> elements.
    Only the IDs listed in `section_ids` are extracted.
    """
    out: list[dict] = []
    fragments = SectionFragments(html, tag).fragments

    for sec_id in section_ids:
        if sec_id not in fragments:
            continue
        attrs, body = fragments[sec_id]
        parser = TextExtractor()
        parser.feed(body)

        # Pull the first h2 (or h3) as the section title
        title_match = re.search(r"<h[23][^>]*>(.*?)</h[23]>", body, re.S | re.I)
        if title_match:
            sec_title = re.sub(r"<[^>]+>", "", title_match.group(1))
            sec_title = unescape(re.sub(r"\s+", " ", sec_title).strip())
        else:
            # Fall back to aria-labelledby: find the referenced element in the
            # full HTML and use its text (strips <br>/<small> siblings cleanly).
            label_id = attrs.get("aria-labelledby", "").strip()
            if label_id:
                label_el = re.search(
                    r'id=["\']' + re.escape(label_id) + r'["\'][^>]*>(.*?)</',
                    html, re.S | re.I,
                )
                if label_el:
                    raw = re.sub(r"<[^>]+>", " ", label_el.group(1))
                    sec_title = unescape(re.sub(r"\s+", " ", raw).strip())
                else:
                    sec_title = sec_id.replace("-", " ").title()
            else:
                sec_title = sec_id.replace("-", " ").title()

        # Plaintext
        plain = parser.collected_text()
        if len(plain) < 60:
            continue

        out.append({
            "url": f"{base_url}#{sec_id}",
            "title": f"{sec_title} — {base_title}",
            "category": category,
            "description": excerpt(plain, 220),
            "headings": [],
            "body": excerpt(plain, 800),
            "parent": base_url,
        })
    return out


def discover_sentinel_sections(html: str) -> list[tuple[str, str]]:
    """Return (tag, id) for every element marked with data-search-index that has an id.

    Page authors add ``data-search-index`` to any content-block div (or section /
    article) they want surfaced as an independent search result.  The script
    discovers them automatically — no manual dict maintenance required.

    Convention: add the attribute to the opening tag of the section you want indexed:
        <div class="content-block" id="features" data-search-index>

    The attribute value is ignored; its presence is the signal.
    """
    sentinel_re = re.compile(r"<(\w+)\b([^>]*)>", re.I)
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in sentinel_re.finditer(html):
        attrs_str = m.group(2)
        if "data-search-index" not in attrs_str.lower():
            continue
        id_m = re.search(r"""\bid\s*=\s*["']([^"']+)["']""", attrs_str, re.I)
        if not id_m:
            continue
        sec_id = id_m.group(1)
        if sec_id in seen:
            continue
        seen.add(sec_id)
        results.append((m.group(1).lower(), sec_id))
    return results


def process_file(path: Path, locale: str = "") -> list[dict]:
    rel = path.relative_to(ROOT).as_posix()
    if path.name in SKIP_FILES:
        return []
    if not is_public_page_path(path, ROOT):
        return []

    html = path.read_text(encoding="utf-8", errors="replace")
    if is_noindex(html):
        return []

    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[warn] parse failed for {rel}: {exc}", file=sys.stderr)
        return []

    title = re.sub(r"\s+", " ", parser.title).strip() or rel
    description = read_meta(html, "description")
    canonical = read_meta(html, "canonical")
    url_path = canonical.replace(SITE, "") if canonical.startswith(SITE) else url_for(path)
    body = parser.collected_text()
    if categorise(url_path) == "Project" and not locale:
        record = next((r for r in PROJECT_STATUS["load_registry"](ROOT) if r["route"] == url_path), None)
        if record:
            body = PROJECT_STATUS["summary"](record) + " " + body

    category_path = url_path
    if locale and category_path.startswith(f"/{locale}/"):
        category_path = category_path[len(locale) + 1:]
        if not category_path.startswith("/"):
            category_path = "/" + category_path

    entry = {
        "url": url_path,
        "title": title,
        "category": categorise(category_path),
        "description": description,
        "headings": [t for _id, t in parser._h2_parts] + parser._h3_parts,
        "body": excerpt(body, 700),
    }
    out = [entry]

    # Article deep-link entries
    if url_path == "/writings/first-diagram-is-a-liar/":
        out.extend(extract_article_sections(html, url_path, title))

    # Project page deep-link entries — auto-detected via data-search-index attribute.
    # To index a new section, add data-search-index to its opening tag in the HTML:
    #   <div class="content-block" id="my-section" data-search-index>
    # No script edit is required.
    if categorise(category_path) == "Project":
        sentinels = discover_sentinel_sections(html)
        by_tag: dict[str, list[str]] = {}
        for stag, sec_id in sentinels:
            by_tag.setdefault(stag, []).append(sec_id)
        for stag, ids in by_tag.items():
            out.extend(extract_div_sections(html, url_path, title, ids, tag=stag))

    # Prompt Forge section deep-links
    # Sections are <section id="..."> elements; system cards are <article id="...">
    if url_path == "/prompt-forge/":
        pf_section_ids = [
            "thesis", "protocols", "flagship-systems", "anatomy",
            "operating-model", "vault", "council", "boundary",
        ]
        out.extend(extract_div_sections(
            html, url_path, title, pf_section_ids, tag="section", category="Brand",
        ))
        pf_card_ids = [
            "scaffrosto", "arcsyntrixo", "gpt-audit", "promptascend", "flowpilot",
        ]
        out.extend(extract_div_sections(
            html, url_path, title, pf_card_ids, tag="article", category="Brand",
        ))

    return out


def build_payload(scan_root: Path = ROOT, locale: str = "") -> dict:
    """Build the deterministic search-index payload without writing to disk."""
    entries: list[dict] = []
    for path in iter_html_files(scan_root):
        entries.extend(process_file(path, locale=locale))

    # Stable sort: Home → Brand → Writing/Article → Article Section → Project → Page
    cat_order = {"Home": 0, "Brand": 1, "Writing": 2, "Article": 3,
                 "Article Section": 4, "Field Guide": 5, "Project": 6, "Page": 7}
    entries.sort(key=lambda e: (cat_order.get(e["category"], 99), e["url"]))

    return {
        "site": SITE,
        **({"locale": locale} if locale else {}),
        "generated": "static",
        "count": len(entries),
        "entries": entries,
    }


def print_summary(payload: dict, action: str, output: Path = OUT) -> None:
    """Print the entry count and category breakdown for a built payload."""
    print(f"{action} {output.relative_to(ROOT)} — {payload['count']} entries")
    by_cat: dict[str, int] = {}
    for e in payload["entries"]:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat}: {n}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    locale_args = [arg for arg in args if arg.startswith("--locale=")]
    unknown_args = [
        arg for arg in args
        if arg != "--check" and not arg.startswith("--locale=")
    ]
    if unknown_args:
        print(
        "Usage: python3 scripts/build-search-index.py [--check] [--locale=fr|en-gb|es-mx]",
            file=sys.stderr,
        )
        return 2

    locale = locale_args[0].split("=", 1)[1].strip() if locale_args else ""
    if len(locale_args) > 1 or (locale and not re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", locale)):
        print("Locale must be a lowercase language tag, such as fr, en-gb, or es-mx.", file=sys.stderr)
        return 2
    output = ROOT / "assets" / "data" / (
        f"search-index.{locale}.json" if locale else "search-index.json"
    )
    scan_root = ROOT / locale if locale else ROOT
    if locale and not scan_root.exists():
        print(
            f"Locale source directory is missing: {scan_root.relative_to(ROOT)}. "
            "Create the translated pages before building its index.",
            file=sys.stderr,
        )
        return 1

    if not check and not locale:
        subprocess.run([sys.executable, str(ROOT / "scripts/build-site.py")], check=True)
    payload = build_payload(scan_root=scan_root, locale=locale)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)

    if check:
        if not output.exists():
            print(
                f"Search index is missing: {output.relative_to(ROOT)}. "
                "Run the matching build-search-index command.",
                file=sys.stderr,
            )
            return 1
        current = output.read_text(encoding="utf-8")
        if current != rendered:
            print(
                f"Search index is stale: {output.relative_to(ROOT)}. "
                "Run the matching build-search-index command, review the diff, "
                "then run this command again.",
                file=sys.stderr,
            )
            return 1
        print_summary(payload, "Search index is current:", output)
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print_summary(payload, "Wrote", output)
    if not locale:
        subprocess.run([sys.executable, str(ROOT / "scripts/sync-universe-map.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "scripts/build-site.py")], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

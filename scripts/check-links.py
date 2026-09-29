#!/usr/bin/env python3
"""
check-links.py — Internal link validator
=========================================
Walks every HTML file and validates every internal href against the
filesystem. Cross-references the result with `sitemap.xml`.

The optional ``--external-archives`` mode performs a deliberately narrow
network check for the GitHub archive destinations linked from the article
``first-diagram-is-a-liar``. It does not turn the normal internal-link audit
into a check of every external service used by the site.

Outputs:
  assets/audit/links-report-YYYY-MM-DD.json

Usage:
    python3 scripts/check-links.py
    python3 scripts/check-links.py --external-archives
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from public_page_boundary import iter_public_html_files

# Link reports intentionally cover site pages, not the asset tree. All other
# directory eligibility comes from the shared published-page boundary.
SKIP_DIRS = {"assets"}
SITE = "https://overkillhill.com"
REPORT_DATE = date.today().isoformat()
ARTICLE_ARCHIVE_PAGE = (
    "site-src/pages/writings/first-diagram-is-a-liar/index.main.html"
)
ARCHIVE_REPOSITORY = "https://github.com/OKHP3/first-diagram-is-a-liar"
ARCHIVE_REPOSITORY_PATH = urlsplit(ARCHIVE_REPOSITORY).path
ARCHIVE_LINK_TIMEOUT = 15


class PageIndexingMeta(HTMLParser):
    """Read the robots and refresh metadata that determines sitemap eligibility."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.is_noindex = False
        self.redirect_target: str | None = None

    def handle_starttag(self, tag: str, attrs_list) -> None:
        if tag.lower() != "meta":
            return
        attrs = {key.lower(): (value or "") for key, value in attrs_list}
        if (
            attrs.get("name", "").lower() == "robots"
            and "noindex" in attrs.get("content", "").lower()
        ):
            self.is_noindex = True
        if attrs.get("http-equiv", "").lower() == "refresh":
            match = re.search(
                r"(?:^|;)\s*url\s*=\s*(.+?)\s*$",
                attrs.get("content", ""),
                re.I,
            )
            if match:
                self.redirect_target = match.group(1).strip("'\" ")


class ArticleArchiveLinkParser(HTMLParser):
    """Collect labeled GitHub archive links from the canonical article."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._label: list[str] = []

    def handle_starttag(self, tag: str, attrs_list) -> None:
        if tag.lower() != "a" or self._href is not None:
            return
        attrs = {key.lower(): (value or "") for key, value in attrs_list}
        href = attrs.get("href", "")
        if is_article_archive_url(href):
            self._href = href
            self._label = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._label.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        label = " ".join("".join(self._label).split()).strip(" →↗")
        self.links.append({"label": label or "Unlabeled archive link",
                           "href": self._href})
        self._href = None
        self._label = []


def is_article_archive_url(href: str) -> bool:
    """Return whether href is an archive destination in the linked repo."""
    parsed = urlsplit(href)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and parsed.path.startswith(f"{ARCHIVE_REPOSITORY_PATH}/")
        and "/archive/" in parsed.path
        and parsed.path.count("/") >= 5
    )


def check_external_archive_links() -> int:
    """Check only the article's GitHub archive URLs."""
    article = ROOT / ARTICLE_ARCHIVE_PAGE
    if not article.is_file():
        print(f"External archive link check: FAIL")
        print(f"  ! Article source not found: {ARTICLE_ARCHIVE_PAGE}")
        return 1

    parser = ArticleArchiveLinkParser()
    parser.feed(article.read_text(encoding="utf-8", errors="replace"))
    if not parser.links:
        print("External archive link check: FAIL")
        print(f"  ! No GitHub archive links found in {ARTICLE_ARCHIVE_PAGE}")
        return 1

    links_by_url: dict[str, list[str]] = {}
    for link in parser.links:
        links_by_url.setdefault(link["href"], []).append(link["label"])

    failures: list[dict[str, str]] = []
    for href, labels in links_by_url.items():
        request = Request(
            href,
            method="HEAD",
            headers={"User-Agent": "OverKill-Hill-archive-link-check/1.0"},
        )
        try:
            with urlopen(request, timeout=ARCHIVE_LINK_TIMEOUT) as response:
                status = response.status
                if not 200 <= status < 400:
                    failures.extend(
                        {"label": label, "href": href, "error": f"HTTP {status}"}
                        for label in labels
                    )
        except HTTPError as error:
            failures.extend(
                {"label": label, "href": href, "error": f"HTTP {error.code}"}
                for label in labels
            )
        except (URLError, TimeoutError, OSError) as error:
            failures.extend(
                {"label": label, "href": href, "error": str(error)}
                for label in labels
            )

    if failures:
        print("External archive link check: FAIL")
        for failure in failures:
            print(
                f"  ! {failure['label']}: {failure['href']} "
                f"({failure['error']})"
            )
        return 1

    print(
        "External archive link check: PASS "
        f"({len(parser.links)} article links, {len(links_by_url)} destinations)"
    )
    return 0


def is_external(href: str) -> bool:
    return href.startswith((
        "http://", "https://", "mailto:", "tel:",
        "javascript:", "data:", "#"
    ))


def resolves(href: str, source_dir: Path) -> bool:
    """Does this internal href resolve to a real file or dir/index.html?"""
    clean = href.split("#")[0].split("?")[0]
    if not clean:
        return True
    if clean.startswith("/"):
        target = ROOT / clean.lstrip("/")
    else:
        target = (source_dir / clean).resolve()
    if target.is_file():
        return True
    if target.is_dir() and (target / "index.html").is_file():
        return True
    if (Path(str(target).rstrip("/")) / "index.html").is_file():
        return True
    return False


def route_for_index(path: Path) -> str:
    """Return the public route represented by an index.html file."""
    rel = path.relative_to(ROOT)
    if rel.as_posix() == "index.html":
        return "/"
    return f"/{'/'.join(rel.parts[:-1])}/"


def sitemap_exclusion(path: Path) -> dict | None:
    """Describe a noindex page intentionally excluded from sitemap coverage."""
    html = path.read_text(encoding="utf-8", errors="replace")
    meta = PageIndexingMeta()
    meta.feed(html)
    if not meta.is_noindex:
        return None

    reason = "robots meta declares noindex"
    if meta.redirect_target:
        reason = f"noindex redirect to {meta.redirect_target}"
    return {
        "page": path.relative_to(ROOT).as_posix(),
        "url": f"{SITE}{route_for_index(path)}",
        "reason": reason,
    }


def iter_html_files(scan_root: Path | None = None):
    """Yield site pages after shared and link-audit-specific exclusions."""
    scan_root = Path(scan_root) if scan_root is not None else ROOT
    for path in iter_public_html_files(scan_root):
        relative = path.relative_to(scan_root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external-archives",
        action="store_true",
        help="check the article's GitHub archive destinations only",
    )
    args = parser.parse_args()
    if args.external_archives:
        return check_external_archive_links()

    pages = []
    all_internal = 0
    all_external = 0
    broken: list[dict] = []
    style_issues: list[dict] = []

    for path in iter_html_files():
        rel = path.relative_to(ROOT)
        html = path.read_text(encoding="utf-8", errors="replace")
        n_int = n_ext = 0
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html):
            href = m.group(1)
            if is_external(href):
                n_ext += 1
                continue
            n_int += 1
            if not resolves(href, path.parent):
                broken.append({"page": rel.as_posix(), "href": href})
            # style: directory URLs ought to end in trailing /
            clean = href.split("#")[0].split("?")[0]
            if (clean and not clean.endswith(("/", ".html", ".png", ".jpg",
                                               ".jpeg", ".svg", ".gif",
                                               ".webp", ".ico", ".pdf",
                                               ".xml", ".json", ".webmanifest",
                                               ".css", ".js", ".txt"))
                    and "?" not in href and "#" not in href.split("?")[0]):
                # Could be a directory missing slash; only flag if a dir exists.
                clean_path = (ROOT / clean.lstrip("/")
                              if clean.startswith("/")
                              else (path.parent / clean).resolve())
                if clean_path.is_dir():
                    style_issues.append({
                        "page": rel.as_posix(),
                        "href": href,
                        "issue": "missing trailing slash",
                    })
        pages.append({"path": rel.as_posix(),
                      "internal_links": n_int,
                      "external_links": n_ext})
        all_internal += n_int
        all_external += n_ext

    # Sitemap coverage
    sitemap = ROOT / "sitemap.xml"
    sitemap_urls: set[str] = set()
    if sitemap.exists():
        sitemap_urls = {m.group(1)
                        for m in re.finditer(r"<loc>([^<]+)</loc>",
                                             sitemap.read_text(encoding="utf-8"))}

    file_urls = set()
    excluded_from_sitemap: list[dict] = []
    for p in iter_html_files():
        if p.name != "index.html":
            continue
        rel = p.relative_to(ROOT)
        exclusion = sitemap_exclusion(p)
        if exclusion:
            excluded_from_sitemap.append(exclusion)
            continue
        file_urls.add(f"{SITE}{route_for_index(p)}")

    missing_from_sitemap = sorted(file_urls - sitemap_urls
                                   - {f"{SITE}/under-construction.html",
                                      f"{SITE}/404.html"})
    extra_in_sitemap = sorted(sitemap_urls - file_urls)

    audit_dir = ROOT / "assets" / "audit"
    audit_dir.mkdir(exist_ok=True)
    out = audit_dir / f"links-report-{REPORT_DATE}.json"
    out.write_text(json.dumps({
        "generated": REPORT_DATE,
        "pages_scanned": len(pages),
        "internal_links": all_internal,
        "external_links": all_external,
        "broken_links": broken,
        "style_issues": style_issues,
        "sitemap": {
            "total_urls": len(sitemap_urls),
            "missing_from_sitemap": missing_from_sitemap,
            "extra_in_sitemap": extra_in_sitemap,
            "intentionally_excluded": excluded_from_sitemap,
        },
        "by_page": pages,
    }, indent=2), encoding="utf-8")

    print(f"Pages scanned:    {len(pages)}")
    print(f"Internal links:   {all_internal}")
    print(f"External links:   {all_external}")
    print(f"Broken links:     {len(broken)}")
    for b in broken[:20]:
        print(f"  ! {b['page']}: {b['href']}")
    print(f"Style issues:     {len(style_issues)}")
    print(f"Sitemap URLs:     {len(sitemap_urls)}  "
          f"(file pages without sitemap: {len(missing_from_sitemap)}, "
          f"sitemap entries without files: {len(extra_in_sitemap)})")
    if missing_from_sitemap:
        for u in missing_from_sitemap:
            print(f"  + missing in sitemap: {u}")
    if extra_in_sitemap:
        for u in extra_in_sitemap:
            print(f"  - sitemap entry has no file: {u}")
    print(f"Noindex exclusions: {len(excluded_from_sitemap)}")
    for excluded in excluded_from_sitemap:
        print(f"  = excluded from sitemap: {excluded['url']} ({excluded['reason']})")
    print(f"Detail: {out.relative_to(ROOT)}")
    return 1 if broken or missing_from_sitemap or extra_in_sitemap else 0


if __name__ == "__main__":
    sys.exit(main())

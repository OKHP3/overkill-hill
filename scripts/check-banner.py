#!/usr/bin/env python3
"""
check-banner.py — verify the site-wide "Hot off the Forge" banner text is
consistent across all HTML pages and follows the featured article release.

The canonical banner text is defined once here (CANONICAL_BANNER). Any future
wording change only needs to happen in this file; running the script with
--update will propagate it to every HTML file on the site. The release prefix
is checked against the current featured article in both the source partial and
generated pages, so changing an article release cannot leave the banner behind.

Usage:
    python3 scripts/check-banner.py              # check only (exits 1 on mismatch)
    python3 scripts/check-banner.py --update     # update all files to match canonical
    python3 scripts/check-banner.py --dry-run    # preview --update without writing

The script matches the banner link text inside .site-specials-link anchors. It
detects both the current canonical string and any prior version listed in
OLD_BANNERS so the diff is always legible.
"""

import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from public_page_boundary import iter_public_html_files

# ── Single source of truth ────────────────────────────────────────────────────
FEATURED_ARTICLE_ROUTE = "/writings/first-diagram-is-a-liar/"
FEATURED_ARTICLE_SOURCE = "site-src/pages/writings/first-diagram-is-a-liar/index.main.html"
FEATURED_ARTICLE_GENERATED = "writings/first-diagram-is-a-liar/index.html"
SOURCE_BANNER = "assets/partials/header.html"

CANONICAL_BANNER = (
    "v0.5 is live: the Council of AIs scored each other, every model was harder"
    " on itself than the architect was. Read it \u2192"
)

# Known prior versions — used for detection only, never written.
OLD_BANNERS = [
    # em-dash version (original)
    (
        "v0.5 is live: the Council of AIs scored each other \u2014 every model was harder"
        " on itself than the architect was. Read it \u2192"
    ),
]

# Banner text patterns that are intentionally NOT the canonical council-scoring
# banner and should not be flagged as mismatches. This includes:
#   - Template placeholder tokens (never rendered by users)
#   - Other articles' banners on pages that announce a different piece of content
ALLOWED_OTHER_PATTERNS = [
    "[[SPECIALS-COPY]]",   # template placeholder token
]
# ─────────────────────────────────────────────────────────────────────────────

# Matches whitespace-normalised content of a .site-specials-link anchor.
# The banner text may be indented / wrapped across lines in the source.
_LINK_RE = re.compile(
    r'(<a\s[^>]*class="[^"]*site-specials-link[^"]*"[^>]*>)'  # opening tag
    r"([\s\S]*?)"                                              # content
    r"(</a>)",                                                 # closing tag
    re.MULTILINE,
)
_HREF_RE = re.compile(r'\bhref="([^"]+)"', re.IGNORECASE)
_LOCALIZED_BANNER_RE = re.compile(
    r"\bdata-banner-localized\s*=\s*(['\"])true\1", re.IGNORECASE
)
_BANNER_RELEASE_ATTR_RE = re.compile(r'\bdata-banner-release="(v\d+(?:\.\d+)+)"', re.IGNORECASE)
# The release label is semantic content, not a dependency on the template's
# choice of inline element.  Keep the opening-tag boundary so incidental
# prose is not counted, while allowing the template to add attributes or
# change the label element.
_ARTICLE_RELEASE_RE = re.compile(
    r"<[a-z][a-z0-9:-]*\b[^>]*>\s*Article\s+(v\d+(?:\.\d+)+)\s*:",
    re.IGNORECASE,
)
_BANNER_RELEASE_RE = re.compile(
    r"^v(\d+(?:\.\d+)+)\s+is\s+live\s*:",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    """Collapse internal whitespace for comparison."""
    return " ".join(text.split())


def find_html_files(root: str):
    root_path = Path(root)
    pages = set(iter_public_html_files(root_path))
    # This source partial is the banner's authoring input and must be checked
    # and repairable alongside generated public pages. Other source/evidence
    # HTML stays outside this inventory.
    source_banner = root_path / SOURCE_BANNER
    if source_banner.is_file():
        pages.add(source_banner)
    yield from (str(path) for path in sorted(pages))


def _featured_article_release(root: str, relative_path: str):
    """Return the sole current article release, or a readable validation error."""
    path = os.path.join(root, relative_path)
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        return None, (
            f"current featured article release is unavailable for "
            f"{FEATURED_ARTICLE_ROUTE}: {relative_path}: {exc}"
        )

    releases = [match.lower() for match in _ARTICLE_RELEASE_RE.findall(content)]
    if len(releases) != 1:
        return None, (
            f"current featured article release is missing or ambiguous for "
            f"{FEATURED_ARTICLE_ROUTE}: expected exactly one "
            f'"Article vN.N" label in {relative_path}'
        )
    return releases[0], None


def _banner_release_issue(raw_text: str, opening_tag: str, expected_release: str):
    """Return a route-aware release mismatch, if this banner targets the article."""
    href_match = _HREF_RE.search(opening_tag)
    if not href_match:
        return f"banner release is missing a link for {FEATURED_ARTICLE_ROUTE}: expected {expected_release}"

    href = href_match.group(1)
    if not href.startswith(FEATURED_ARTICLE_ROUTE):
        return None

    release_attr = _BANNER_RELEASE_ATTR_RE.search(opening_tag)
    if release_attr:
        found = release_attr.group(1).lower()
    else:
        normalised = _normalise(raw_text)
        release_match = _BANNER_RELEASE_RE.match(normalised)
        found = f"v{release_match.group(1).lower()}" if release_match else None
    if found != expected_release:
        found_label = found if found is not None else "missing"
        return (
            f"banner release mismatch for {FEATURED_ARTICLE_ROUTE}: "
            f"expected {expected_release} from the article, found {found_label}"
        )
    return None


def _plan_file(
    path: str,
    update: bool = False,
    dry_run: bool = False,
    expected_release: str | None = None,
):
    """Return (status, message, planned_content) without changing ``path``."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    matches = list(_LINK_RE.finditer(content))
    if not matches:
        return "skip", None, content

    issues = []
    release_issues = []
    new_content = content

    for m in matches:
        raw_text = m.group(2)
        normalised = _normalise(raw_text)
        href_match = _HREF_RE.search(m.group(1))
        is_featured_banner = bool(
            href_match and href_match.group(1).startswith(FEATURED_ARTICLE_ROUTE)
        )
        is_localized_featured_banner = bool(
            is_featured_banner and _LOCALIZED_BANNER_RE.search(m.group(1))
        )

        if expected_release is not None:
            release_issue = _banner_release_issue(raw_text, m.group(1), expected_release)
            if release_issue:
                release_issues.append(release_issue)

        # Already canonical?
        if normalised == _normalise(CANONICAL_BANNER):
            continue

        # Localized notices retain an explicit release marker for validation,
        # but intentionally have visitor-facing copy different from English.
        if is_localized_featured_banner:
            continue

        # Intentionally different banner (template token or other article)?
        if any(_normalise(p) == normalised for p in ALLOWED_OTHER_PATTERNS):
            continue
        # Also allow any banner that doesn't look like a stale council-scoring
        # copy — i.e. it doesn't start with the same "v0.5 is live:" prefix at all.
        # Those are intentionally different banners for other articles.
        if not is_featured_banner and not normalised.startswith("v0.5 is live:"):
            continue

        # Known old version?
        known_old = any(_normalise(old) == normalised for old in OLD_BANNERS)
        if known_old:
            issues.append(("old", m, raw_text))
        else:
            issues.append(("unknown", m, raw_text))

    if not issues and not release_issues:
        return "ok", None, content

    # --update can safely repair known wording drift, but it cannot invent the
    # new article copy when the article has moved to a new release.
    if release_issues:
        messages = [f"  [RELEASE] {issue}" for issue in release_issues]
        if issues:
            messages.extend(
                f"  [{('old' if kind == 'old' else 'UNKNOWN')}] {_normalise(raw_text)!r}"
                for kind, _, raw_text in issues
            )
        return "mismatch", "\n".join(messages), content

    if any(kind != "old" for kind, _, _ in issues):
        messages = [
            f"  [{('old' if kind == 'old' else 'UNKNOWN')}] {_normalise(raw_text)!r}"
            for kind, _, raw_text in issues
        ]
        return "mismatch", "\n".join(messages), content

    if update or dry_run:
        for kind, m, raw_text in issues:
            if kind == "old":
                # Preserve surrounding whitespace/indentation pattern — just
                # replace the text portion, keeping lead/trail whitespace.
                lead = len(raw_text) - len(raw_text.lstrip())
                trail = len(raw_text) - len(raw_text.rstrip())
                indent = raw_text[:lead]
                suffix = raw_text[len(raw_text.rstrip()):]
                replacement = indent + CANONICAL_BANNER + suffix
                new_content = new_content.replace(m.group(2), replacement, 1)

        return "fixed", f"{len(issues)} banner(s) updated", new_content

    # Report only
    msgs = []
    for kind, _, raw_text in issues:
        label = "old" if kind == "old" else "UNKNOWN"
        msgs.append(f"  [{label}] {_normalise(raw_text)!r}")
    return "mismatch", "\n".join(msgs), content


def check_file(
    path: str,
    update: bool = False,
    dry_run: bool = False,
    expected_release: str | None = None,
):
    """Return (status, message) without changing ``path``."""
    status, message, _ = _plan_file(
        path,
        update=update,
        dry_run=dry_run,
        expected_release=expected_release,
    )
    return status, message


def main():
    update = "--update" in sys.argv
    dry_run = "--dry-run" in sys.argv

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ok = fixed = mismatch = skip = 0
    planned_updates = []

    source_release, source_error = _featured_article_release(root, FEATURED_ARTICLE_SOURCE)
    generated_release, generated_error = _featured_article_release(root, FEATURED_ARTICLE_GENERATED)
    if source_error or generated_error:
        if source_error:
            print(f"  MISMATCH: {source_error}")
        if generated_error:
            print(f"  MISMATCH: {generated_error}")
        sys.exit(1)
    if source_release != generated_release:
        print(
            f"  MISMATCH: featured article release disagreement for "
            f"{FEATURED_ARTICLE_ROUTE}: {FEATURED_ARTICLE_SOURCE} has "
            f"{source_release}, but {FEATURED_ARTICLE_GENERATED} has "
            f"{generated_release}"
        )
        sys.exit(1)

    for path in find_html_files(root):
        rel = os.path.relpath(path, root)
        expected_release = source_release if rel == SOURCE_BANNER else generated_release
        status, msg, planned_content = _plan_file(
            path,
            update=update,
            dry_run=dry_run,
            expected_release=expected_release,
        )
        if status == "ok":
            ok += 1
        elif status == "fixed":
            fixed += 1
            if dry_run:
                print(f"  [dry-run] would fix: {rel} — {msg}")
            elif update:
                planned_updates.append((path, rel, msg, planned_content))
            else:
                print(f"  Fixed: {rel} — {msg}")
        elif status == "mismatch":
            mismatch += 1
            print(f"  MISMATCH: {rel}\n{msg}")
        else:
            skip += 1

    print()
    if dry_run:
        print(f"Dry run: would fix {fixed}, already ok {ok}, no banner {skip}.")
    else:
        if update and mismatch:
            for _, rel, msg, _ in planned_updates:
                print(f"  NOT FIXED (validation failed): {rel} — {msg}")
            print(
                f"Update aborted: would fix {fixed}, but validation found "
                f"{mismatch} mismatch(es); no files were changed."
            )
        elif update:
            for path, rel, msg, planned_content in planned_updates:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(planned_content)
                print(f"  Fixed: {rel} — {msg}")
        print(f"OK: {ok}  Fixed: {fixed if not (update and mismatch) else 0}  "
              f"Mismatch: {mismatch}  No banner: {skip}")

    if mismatch:
        print("\nRun with --update to fix, or --dry-run to preview.")
        sys.exit(1)


if __name__ == "__main__":
    main()

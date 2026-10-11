"""Shared production-page discovery policy for site scanners.

The directories in ``PUBLIC_PAGE_EXCLUDED_DIRS`` are repository content that
may contain HTML but is never a published page.  Dedicated commands may add
their own exclusions for tool-specific inputs; they must not remove these
shared exclusions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator


# Keep this policy about page publication, not about every directory a tool
# might need to skip.  For example, check-links.py additionally skips all of
# assets/ because its link report is only for site pages.
PUBLIC_PAGE_EXCLUDED_DIRS = frozenset(
    {
        "_replit",
        ".agents",
        ".cache",
        ".canvas",
        ".ci",
        ".config",
        ".github",
        ".git",
        ".local",
        ".pr-head",
        ".pythonlibs",
        ".vscode",
        "attached_assets",
        "dist",
        "i18n",
        "node_modules",
        "partials",
        "site-src",
        "templates",
        "tests",
    }
)

# Active scripts that discover HTML pages or source-page inputs. The policy
# values name the shared boundary and any deliberate, tested extension.
HTML_SCANNER_REGISTRY = {
    "audit-site.py": "shared",
    "build-release.py": "shared",
    "build-search-index.py": "shared",
    "build-site.py": "shared",
    "cache-bust.py": "shared + maintained-source-inputs",
    "check-banner.py": "shared + source-banner-partial",
    "check-links.py": "shared",
    "csp.py": "shared",
    "lint-voice.py": "shared",
    "project-status.py": "exception: source-project-detail-inventory",
    "strip-google-fonts-links.py": "shared + declared-source-inputs",
    "validate-site.py": "shared",
}


def is_public_page_path(path: Path, root: Path) -> bool:
    """Return whether an HTML path belongs to the published-page boundary."""
    try:
        relative = Path(path).relative_to(Path(root))
    except ValueError:
        return False
    if ".." in relative.parts:
        return False
    return not any(part in PUBLIC_PAGE_EXCLUDED_DIRS for part in relative.parts)


def iter_public_html_files(root: Path) -> Iterator[Path]:
    """Yield HTML files in the shared published-page boundary."""
    root = Path(root)
    for path in sorted(root.rglob("*.html")):
        if is_public_page_path(path, root):
            yield path

#!/usr/bin/env python3
"""Canonical CSP policies and page classification for the static site."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from public_page_boundary import is_public_page_path

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "config" / "csp-policies.json"
MURDERBIRD_THEME_AUDIO = "https://okhp3.github.io/murderbird-uncaged/audio/iron-verdict-v3/full-song.mp3"
CSP_HEADER = "Content-Security-Policy"
CSP_REPORT_ONLY_HEADER = f"{CSP_HEADER}-Report-Only"
META_RE = re.compile(
    rf'<meta\s+http-equiv=["\']{re.escape(CSP_HEADER)}["\']\s+content=(["\'])(.*?)\1\s*/?>',
    re.IGNORECASE,
)


def page_class(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel in {"404.html", "under-construction.html", "search/index.html", "vault/index.html"}:
        return "utility"
    if rel == "writings/murderbird/index.html":
        return "murderbird"
    source = path.read_text(encoding="utf-8", errors="replace")
    # Pages that host another application need an explicit frame destination.
    is_embed = 'id="tool-iframe"' in source or 'id="skillz-iframe"' in source or "<iframe" in source
    # Mermaid renders its own inline styles and <style> blocks at runtime, per
    # diagram, per page load. A build-time hash allowlist can never cover
    # that, so pages with a live diagram get a scoped style-src relaxation
    # instead of silently losing their theme styling under a hash-only
    # policy. script-src is unaffected -- these pages stay just as
    # hash-locked for scripts as every other page. The two conditions are
    # independent (projects/found-ry hosts both an iframe and a diagram),
    # so a page can need both allowances at once.
    is_diagram = _renders_live_mermaid(source)
    if is_embed and is_diagram:
        return "embed-diagram"
    if is_embed:
        return "embed"
    if is_diagram:
        return "diagram"
    return "standard"


def _renders_live_mermaid(source: str) -> bool:
    return bool(re.search(r"""class=["\'][^"\']*\bmermaid\b""", source, re.IGNORECASE))


def sha256_source(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def inline_sources(path: Path) -> tuple[set[str], set[str]]:
    source = path.read_text(encoding="utf-8", errors="replace")
    script_hashes = {
        sha256_source(match.group(1))
        for match in re.finditer(r"<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", source, re.I)
        if match.group(1).strip()
    }
    style_attr_hashes = {
        sha256_source(html.unescape(match.group(2)))
        for match in re.finditer(r'\bstyle=(["\'])(.*?)\1', source, re.I)
    }
    return script_hashes, style_attr_hashes


def all_pages() -> list[Path]:
    """Return published pages plus manifest-declared generated routes.

    The manifest is a deliberate CSP-specific addition to the shared public
    page boundary: a generated route must receive a CSP before it is tracked
    by git.  Every tracked and manifest candidate still passes
    ``is_public_page_path`` so source templates, fixtures, and translation
    evidence cannot become CSP pages by accident.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*.html"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    # Newly built routes must participate before git add, so local validation
    # and a fresh CI checkout compute the same policy inventory.
    names = set(tracked.stdout.splitlines())
    manifest = ROOT / "site-src" / "pages.json"
    if manifest.exists():
        for page in json.loads(manifest.read_text(encoding="utf-8"))["pages"]:
            candidate = (ROOT / page["path"]).resolve()
            if candidate.is_relative_to(ROOT) and candidate.is_file():
                names.add(candidate.relative_to(ROOT).as_posix())
    return sorted(
        ROOT / name
        for name in names
        if is_public_page_path(ROOT / name, ROOT)
    )


def build_policies() -> dict[str, str]:
    classes = ("standard", "embed", "utility", "diagram", "embed-diagram", "murderbird")
    hashes: dict[str, set[str]] = {kind: set() for kind in classes}
    style_hashes: dict[str, set[str]] = {kind: set() for kind in classes}
    for page in all_pages():
        scripts, styles = inline_sources(page)
        kind = page_class(page)
        # Preserve the existing standard script allowlist when separating the story policy.
        if kind == "murderbird":
            hashes["standard"].update(scripts)
        hashes[kind].update(scripts)
        style_hashes[kind].update(styles)

    common = (
        "default-src 'self'; "
        "script-src 'self' https://www.googletagmanager.com "
        + " ".join(sorted(hashes["standard"]))
        + "; script-src-attr 'none'; "
        "style-src 'self' "
        + " ".join(sorted(style_hashes["standard"]))
        + "; style-src-attr 'unsafe-hashes' "
        + " ".join(sorted(style_hashes["standard"]))
        + "; font-src 'self' data:; "
        "img-src 'self' data: https://overkillhill.com https://*.github.io https://avatars.githubusercontent.com https://www.googletagmanager.com; "
        "connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com https://www.googletagmanager.com https://okhp3.github.io; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; "
        "manifest-src 'self'; upgrade-insecure-requests"
    )

    # Keep each class explicit even where it currently shares most directives.
    # This prevents an embed allowance from silently spreading to ordinary pages.
    #
    # "diagram_style" is a scoped style-src/style-src-attr relaxation for
    # page classes that render a live Mermaid diagram: Mermaid generates its
    # inline styles and <style> blocks at render time in the browser, so a
    # build-time hash allowlist can never cover them. Hashes and
    # 'unsafe-inline' must not appear together in the same directive --
    # CSP ignores 'unsafe-inline' whenever a hash-source is present -- so
    # the style hashes are omitted entirely for these classes rather than
    # added alongside it. script-src is identical in rigor across every
    # class regardless of diagram_style.
    policies = {"standard": common}
    class_config = (
        ("embed", "https://okhp3.github.io", False),
        ("utility", "", False),
        ("diagram", "", True),
        ("embed-diagram", "https://okhp3.github.io", True),
        ("murderbird", "", False),
    )
    for kind, frame, diagram_style in class_config:
        if diagram_style:
            style_directives = (
                "style-src 'self' 'unsafe-inline'; "
                "style-src-attr 'unsafe-inline'; "
            )
        else:
            style_directives = (
                "style-src 'self' "
                + " ".join(sorted(style_hashes[kind]))
                + "; style-src-attr 'unsafe-hashes' "
                + " ".join(sorted(style_hashes[kind]))
                + "; "
            )
        policy = (
            "default-src 'self'; "
            "script-src 'self' https://www.googletagmanager.com "
            + " ".join(sorted(hashes[kind]))
            + "; script-src-attr 'none'; "
            + style_directives
            + "font-src 'self' data:; "
            "img-src 'self' data: https://overkillhill.com https://*.github.io https://avatars.githubusercontent.com https://www.googletagmanager.com; "
            "connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com https://www.googletagmanager.com https://okhp3.github.io; "
            + (f"media-src 'self' {MURDERBIRD_THEME_AUDIO}; " if kind == "murderbird" else "")
            + (f"frame-src 'self' {frame}; " if frame else "")
            + "object-src 'none'; base-uri 'self'; form-action 'self'; "
            "manifest-src 'self'; upgrade-insecure-requests"
        )
        policies[kind] = policy
    return policies


def build_edge_policy() -> str:
    """Build the enforcing header policy, broad enough for every page class.

    Page meta policies remain the tighter class-specific policies. Browsers
    intersect the header and meta policies, so this header must permit the
    union while never adding a destination absent from the page policies.
    """
    scripts: set[str] = set()
    styles: set[str] = set()
    for page in all_pages():
        page_scripts, page_styles = inline_sources(page)
        scripts.update(page_scripts)
        styles.update(page_styles)
    # style-src stays 'unsafe-inline' here rather than hash-only: this
    # envelope has to be broad enough to cover the "diagram" and
    # "embed-diagram" page classes too (see build_policies), and a
    # hash-source alongside 'unsafe-inline' in the same directive causes
    # browsers to ignore 'unsafe-inline' entirely. Per-page meta policies
    # remain the real, tighter enforcement for every other page; this
    # header is only ever meant to be a permissive outer bound (see the
    # module docstring above).
    return (
        "default-src 'self'; script-src 'self' https://www.googletagmanager.com "
        + " ".join(sorted(scripts))
        + "; script-src-attr 'none'; style-src 'self' 'unsafe-inline'; "
        "style-src-attr 'unsafe-inline'; "
        "font-src 'self' data:; "
        "img-src 'self' data: https://overkillhill.com https://*.github.io https://avatars.githubusercontent.com https://www.googletagmanager.com; "
        "connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com "
        "https://www.googletagmanager.com https://okhp3.github.io; "
        f"media-src 'self' {MURDERBIRD_THEME_AUDIO}; "
        "frame-src 'self' https://okhp3.github.io; frame-ancestors 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; manifest-src 'self'; "
        "upgrade-insecure-requests; report-uri /__csp-report"
    )


def load_policies() -> dict[str, str]:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))["policies"]


def meta_policy(path: Path) -> str | None:
    source = path.read_text(encoding="utf-8", errors="replace")
    match = META_RE.search(source)
    return match.group(2) if match else None


def render_meta(policy: str) -> str:
    return f'<meta http-equiv="Content-Security-Policy" content="{policy}" />'

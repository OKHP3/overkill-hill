#!/usr/bin/env python3
"""Focused regression checks for localized construction-banner validation."""

from __future__ import annotations

import importlib.util
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_banner", ROOT / "scripts" / "check-banner.py")
if SPEC is None or SPEC.loader is None:
    raise SystemExit("Unable to load scripts/check-banner.py")
check_banner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_banner)


def check_case(
    name: str,
    anchor: str,
    expected_status: str,
    *,
    expected_release: str = "v0.5",
    relative_path: str = "index.html",
    expected_message_parts: tuple[str, ...] = (),
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        page = Path(temp_dir) / relative_path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(f"<main>{anchor}</main>", encoding="utf-8")
        status, message = check_banner.check_file(str(page), expected_release=expected_release)
    if status != expected_status:
        raise AssertionError(f"{name}: expected {expected_status}, got {status}")
    for part in expected_message_parts:
        if message is None or part not in message:
            raise AssertionError(f"{name}: expected {part!r} in {message!r}")


def check_article_release_variations() -> None:
    valid_labels = (
        (
            "span with attributes, whitespace, and mixed casing",
            '<SPAN class="article-release" data-version="current">\n'
            "  ARTICLE \n V0.5 \n : Council-Assisted Scoring\n"
            "</SPAN>",
        ),
        (
            "changed label element with attributes",
            '<div data-role="article-release" class="eyebrow-label">'
            "\n\tArticle\tv0.5: Council-Assisted Scoring\n"
            "</div>",
        ),
    )
    for name, label in valid_labels:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            article = root / "article.html"
            article.write_text(label, encoding="utf-8")
            release, error = check_banner._featured_article_release(
                str(root), "article.html"
            )
        if release != "v0.5" or error is not None:
            raise AssertionError(
                f"{name}: expected v0.5 without an error, got {release!r}, {error!r}"
            )


def check_main_case(
    name: str,
    banner_path: str,
    anchor: str,
    expected_message_parts: tuple[str, ...],
    *,
    source_article: str | None = None,
    generated_article: str | None = None,
    mode: str | None = None,
    expect_files_unchanged: bool = False,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        valid_article = "<span>Article v0.6: Council-Assisted Scoring</span>"
        source_article = valid_article if source_article is None else source_article
        generated_article = (
            valid_article if generated_article is None else generated_article
        )
        for relative_path, article in (
            (check_banner.FEATURED_ARTICLE_SOURCE, source_article),
            (check_banner.FEATURED_ARTICLE_GENERATED, generated_article),
        ):
            article_path = root / relative_path
            article_path.parent.mkdir(parents=True, exist_ok=True)
            article_path.write_text(article, encoding="utf-8")

        banner = root / banner_path
        banner.parent.mkdir(parents=True, exist_ok=True)
        banner_content = (
            generated_article if banner_path == check_banner.FEATURED_ARTICLE_GENERATED else ""
        )
        banner.write_text(banner_content + anchor, encoding="utf-8")
        before = {
            path: path.read_text(encoding="utf-8")
            for path in root.rglob("*.html")
        }

        output = StringIO()
        with (
            patch.object(check_banner, "__file__", str(root / "scripts/check-banner.py")),
            patch("sys.argv", ["check-banner.py"] + ([mode] if mode else [])),
            redirect_stdout(output),
        ):
            try:
                check_banner.main()
            except SystemExit as exc:
                if exc.code != 1:
                    raise AssertionError(f"{name}: expected exit 1, got {exc.code}")
            else:
                raise AssertionError(f"{name}: expected a mismatch")

        if expect_files_unchanged:
            after = {
                path: path.read_text(encoding="utf-8")
                for path in root.rglob("*.html")
            }
            if after != before:
                changed = sorted(
                    str(path.relative_to(root))
                    for path in set(before) | set(after)
                    if before.get(path) != after.get(path)
                )
                raise AssertionError(
                    f"{name}: expected no files to change, changed {changed}"
                )

    report = output.getvalue().replace("\\", "/")
    for part in expected_message_parts:
        if part not in report:
            raise AssertionError(f"{name}: expected {part!r} in {report!r}")


def check_update_is_atomic() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        valid_article = "<span>Article v0.5: Council-Assisted Scoring</span>"
        for relative_path in (
            check_banner.FEATURED_ARTICLE_SOURCE,
            check_banner.FEATURED_ARTICLE_GENERATED,
        ):
            article_path = root / relative_path
            article_path.parent.mkdir(parents=True, exist_ok=True)
            article_path.write_text(valid_article, encoding="utf-8")

        featured = "/writings/first-diagram-is-a-liar/#council-scoring"
        source_banner = root / check_banner.SOURCE_BANNER
        source_banner.parent.mkdir(parents=True, exist_ok=True)
        source_banner.write_text(
            f'<a class="site-specials-link" href="{featured}">'
            f"{check_banner.OLD_BANNERS[0]}</a>",
            encoding="utf-8",
        )
        later_page = root / "later.html"
        later_page.write_text(
            f'<a class="site-specials-link" href="{featured}">'
            "v0.5 is live: unexpected wording</a>",
            encoding="utf-8",
        )
        before = {
            path: path.read_text(encoding="utf-8")
            for path in root.rglob("*.html")
        }

        output = StringIO()
        with (
            patch.object(check_banner, "__file__", str(root / "scripts/check-banner.py")),
            patch("sys.argv", ["check-banner.py", "--update"]),
            redirect_stdout(output),
        ):
            try:
                check_banner.main()
            except SystemExit as exc:
                if exc.code != 1:
                    raise AssertionError(f"atomic update: expected exit 1, got {exc.code}")
            else:
                raise AssertionError("atomic update: expected a mismatch")

        after = {
            path: path.read_text(encoding="utf-8")
            for path in root.rglob("*.html")
        }
        if after != before:
            changed = sorted(
                str(path.relative_to(root))
                for path in set(before) | set(after)
                if before.get(path) != after.get(path)
            )
            raise AssertionError(
                f"atomic update: expected no files to change, changed {changed}"
            )
        report = output.getvalue().replace("\\", "/")
        if "NOT FIXED (validation failed)" not in report:
            raise AssertionError(f"atomic update: missing deferred repair report: {report}")
        if "later.html" not in report:
            raise AssertionError(f"atomic update: missing later mismatch: {report}")


def check_update_and_dry_run_preserve_repair_behavior() -> None:
    for mode in ("--dry-run", "--update"):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid_article = "<span>Article v0.5: Council-Assisted Scoring</span>"
            for relative_path in (
                check_banner.FEATURED_ARTICLE_SOURCE,
                check_banner.FEATURED_ARTICLE_GENERATED,
            ):
                article_path = root / relative_path
                article_path.parent.mkdir(parents=True, exist_ok=True)
                article_path.write_text(valid_article, encoding="utf-8")

            featured = "/writings/first-diagram-is-a-liar/#council-scoring"
            banner = root / check_banner.SOURCE_BANNER
            banner.parent.mkdir(parents=True, exist_ok=True)
            banner.write_text(
                f'<a class="site-specials-link" href="{featured}">'
                f"{check_banner.OLD_BANNERS[0]}</a>",
                encoding="utf-8",
            )
            before = banner.read_text(encoding="utf-8")
            output = StringIO()
            with (
                patch.object(check_banner, "__file__", str(root / "scripts/check-banner.py")),
                patch("sys.argv", ["check-banner.py", mode]),
                redirect_stdout(output),
            ):
                check_banner.main()

            report = output.getvalue()
            after = banner.read_text(encoding="utf-8")
            if mode == "--dry-run":
                if after != before:
                    raise AssertionError("dry-run changed the banner file")
                if "[dry-run] would fix" not in report:
                    raise AssertionError(f"dry-run omitted repair preview: {report}")
            else:
                if check_banner.CANONICAL_BANNER not in after:
                    raise AssertionError("update did not apply the canonical banner")
                if check_banner.OLD_BANNERS[0] in after:
                    raise AssertionError("update left the old banner in place")


def main() -> int:
    featured = "/writings/first-diagram-is-a-liar/#council-scoring"
    stale_release = "v0.6"
    check_article_release_variations()
    release_failure = (
        f"banner release mismatch for {check_banner.FEATURED_ARTICLE_ROUTE}",
        f"expected {stale_release}",
        "found v0.7",
    )
    release_drift_failure = release_failure[:2] + ("found v0.5",)
    stale_source_failure = release_failure + (check_banner.SOURCE_BANNER,)
    check_main_case(
        "stale source partial reports featured route and expected release",
        check_banner.SOURCE_BANNER,
        f'<a class="site-specials-link" href="{featured}">{check_banner.CANONICAL_BANNER}</a>',
        stale_source_failure,
    )
    stale_generated_failure = release_failure + (check_banner.FEATURED_ARTICLE_GENERATED,)
    check_main_case(
        "stale generated banner reports featured route and expected release",
        check_banner.FEATURED_ARTICLE_GENERATED,
        f'<a class="site-specials-link" href="{featured}">{check_banner.CANONICAL_BANNER}</a>',
        stale_generated_failure,
    )
    for mode in ("--update", "--dry-run"):
        for banner_path, label in (
            (check_banner.SOURCE_BANNER, "source partial"),
            (check_banner.FEATURED_ARTICLE_GENERATED, "generated article"),
        ):
            check_main_case(
                f"{mode} preserves {label} release drift",
                banner_path,
                f'<a class="site-specials-link" href="{featured}">'
                f"{check_banner.OLD_BANNERS[1]}</a>",
                release_drift_failure + (banner_path,),
                mode=mode,
                expect_files_unchanged=True,
            )
    malformed_article_cases = (
        (
            "missing source article label reports route and source path",
            check_banner.SOURCE_BANNER,
            check_banner.FEATURED_ARTICLE_SOURCE,
            {"source_article": ""},
        ),
        (
            "ambiguous source article labels report route and source path",
            check_banner.SOURCE_BANNER,
            check_banner.FEATURED_ARTICLE_SOURCE,
            {
                "source_article": (
                    "<span>Article v0.6: Council-Assisted Scoring</span>"
                    "<strong>Article v0.7: Council-Assisted Scoring</strong>"
                )
            },
        ),
        (
            "missing generated article label reports route and generated path",
            check_banner.FEATURED_ARTICLE_GENERATED,
            check_banner.FEATURED_ARTICLE_GENERATED,
            {"generated_article": ""},
        ),
        (
            "ambiguous generated article labels report route and generated path",
            check_banner.FEATURED_ARTICLE_GENERATED,
            check_banner.FEATURED_ARTICLE_GENERATED,
            {
                "generated_article": (
                    "<span>Article v0.6: Council-Assisted Scoring</span>"
                    "<strong>Article v0.7: Council-Assisted Scoring</strong>"
                )
            },
        ),
    )
    for name, banner_path, article_path, malformed_fixture in malformed_article_cases:
        check_main_case(
            name,
            banner_path,
            f'<a class="site-specials-link" href="{featured}">{check_banner.CANONICAL_BANNER}</a>',
            (
                "current featured article release is missing or ambiguous",
                check_banner.FEATURED_ARTICLE_ROUTE,
                article_path,
            ),
            **malformed_fixture,
        )
        for mode in ("--update", "--dry-run"):
            check_main_case(
                f"{mode} {name}",
                banner_path,
                f'<a class="site-specials-link" href="{featured}">{check_banner.OLD_BANNERS[0]}</a>',
                (
                    "current featured article release is missing or ambiguous",
                    check_banner.FEATURED_ARTICLE_ROUTE,
                    article_path,
                ),
                mode=mode,
                expect_files_unchanged=True,
                **malformed_fixture,
            )
    disagreement_parts = (
        "featured article release disagreement",
        check_banner.FEATURED_ARTICLE_ROUTE,
        check_banner.FEATURED_ARTICLE_SOURCE,
        check_banner.FEATURED_ARTICLE_GENERATED,
        "v0.6",
        "v0.7",
    )
    for mode in (None, "--update", "--dry-run"):
        check_main_case(
            f"{mode or 'check'} rejects source/generated release disagreement",
            check_banner.SOURCE_BANNER,
            f'<a class="site-specials-link" href="{featured}">{check_banner.OLD_BANNERS[0]}</a>',
            disagreement_parts,
            source_article="<span>Article v0.6: Council-Assisted Scoring</span>",
            generated_article="<span>Article v0.7: Council-Assisted Scoring</span>",
            mode=mode,
            expect_files_unchanged=True,
        )
    check_case(
        "other article banner retains the allow-list behavior",
        '<a class="site-specials-link" href="/writings/another-article/">'
        "v0.4 is live: Another article"
        "</a>",
        "ok",
        expected_release=stale_release,
    )
    check_case(
        "localized marker matches release",
        f'<a class="site-specials-link" data-banner-localized="true" data-banner-release="v0.5" href="{featured}">La versión 0.5 ya está en línea</a>',
        "ok",
    )
    check_case(
        "localized marker accepts valid quoting, spacing, and casing",
        f'<a class="site-specials-link" DATA-BANNER-LOCALIZED = \'TRUE\' data-banner-release="v0.5" href="{featured}">La versión 0.5 ya está en línea</a>',
        "ok",
    )
    check_case(
        "localized marker without release fails",
        f'<a class="site-specials-link" data-banner-localized="true" href="{featured}">La versión 0.5 ya está en línea</a>',
        "mismatch",
    )
    check_case(
        "localized marker with wrong release fails",
        f'<a class="site-specials-link" data-banner-localized="true" data-banner-release="v0.4" href="{featured}">La versión 0.4 ya está en línea</a>',
        "mismatch",
    )
    check_case(
        "ordinary English mismatch still fails",
        f'<a class="site-specials-link" href="{featured}">v0.5 is live: unrelated copy</a>',
        "mismatch",
    )
    check_update_and_dry_run_preserve_repair_behavior()
    check_update_is_atomic()
    print("check-banner localized regression checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

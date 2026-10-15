#!/usr/bin/env python3
"""Focused regression checks for localized construction-banner validation."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_banner", ROOT / "scripts" / "check-banner.py")
if SPEC is None or SPEC.loader is None:
    raise SystemExit("Unable to load scripts/check-banner.py")
check_banner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_banner)

BUILD_SITE_SPEC = importlib.util.spec_from_file_location(
    "build_site", ROOT / "scripts" / "build-site.py"
)
if BUILD_SITE_SPEC is None or BUILD_SITE_SPEC.loader is None:
    raise SystemExit("Unable to load scripts/build-site.py")
build_site = importlib.util.module_from_spec(BUILD_SITE_SPEC)
BUILD_SITE_SPEC.loader.exec_module(build_site)

VALIDATE_SITE_SPEC = importlib.util.spec_from_file_location(
    "validate_site", ROOT / "scripts" / "validate-site.py"
)
if VALIDATE_SITE_SPEC is None or VALIDATE_SITE_SPEC.loader is None:
    raise SystemExit("Unable to load scripts/validate-site.py")
validate_site = importlib.util.module_from_spec(VALIDATE_SITE_SPEC)
VALIDATE_SITE_SPEC.loader.exec_module(validate_site)


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
            "escaped markup remains a text example",
            "&lt;span&gt;Article v9.9: example&lt;/span&gt;"
            "<span>Article v0.5: Council-Assisted Scoring</span>",
        ),
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


def check_hidden_article_release_decoys() -> None:
    route = check_banner.FEATURED_ARTICLE_ROUTE
    visible = "<span>Article v0.5: Council-Assisted Scoring</span>"
    hidden_decoy = (
        "<script>Article v0.7: decoy</script>"
        "<style>.label::after { content: 'Article v0.8: decoy'; }</style>"
        "<template><strong>Article v0.9: decoy</strong></template>"
        "<!-- <b>Article v1.0: decoy</b> -->"
        '<div hidden>Article v1.1: decoy</div>'
    )
    hub_markup = (
        '<div class="writing-card-kicker--featured">'
        f"{visible}</div>"
    )
    with tempfile.TemporaryDirectory(dir=ROOT / "tests" / "fixtures") as temp_dir:
        root = Path(temp_dir)
        hub = root / "hub.html"
        hub.write_text(hub_markup, encoding="utf-8")

        decoy_article = root / "article-with-hidden-decoy.html"
        decoy_article.write_text(hidden_decoy + visible, encoding="utf-8")
        release, error = check_banner._featured_article_release(
            str(root), decoy_article.name
        )
        findings = validate_site.validate_writing_release_alignment(
            hub, decoy_article, route
        )
        if release != "v0.5" or error is not None or findings:
            raise AssertionError(
                "hidden decoys must not change a visible release: "
                f"banner={(release, error)!r}, shared={findings!r}"
            )

        hidden_only = root / "article-hidden-only.html"
        hidden_only.write_text(
            "<template><span>Article v0.5: hidden only</span></template>",
            encoding="utf-8",
        )
        relative_path = hidden_only.relative_to(ROOT).as_posix()
        release, error = check_banner._featured_article_release(
            str(root), hidden_only.name
        )
        findings = validate_site.validate_writing_release_alignment(
            hub, hidden_only, route
        )
        if release is not None or error is None:
            raise AssertionError(
                f"hidden-only label must fail banner check: {(release, error)!r}"
            )
        if route not in error or hidden_only.name not in error:
            raise AssertionError(f"banner error lacks route/path: {error!r}")
        if (
            len(findings) != 1
            or route not in findings[0].msg
            or relative_path not in findings[0].page
        ):
            raise AssertionError(
                f"hidden-only label must fail shared check with route/path: {findings!r}"
            )


def check_shared_article_release_contract() -> None:
    valid_labels = (
        '<SPAN class="article-release" data-version="current">\n'
        "  ARTICLE \n V0.5 \n : Council-Assisted Scoring\n"
        "</SPAN>",
        '<article-release data-role="article-release" class="eyebrow-label">'
        "\n\tArticle\tv0.5: Council-Assisted Scoring\n"
        "</article-release>",
    )
    route = validate_site.FEATURED_WRITING_ROUTE
    with tempfile.TemporaryDirectory(dir=ROOT / "tests" / "fixtures") as temp_dir:
        root = Path(temp_dir)
        hub = root / "hub.html"
        hub.write_text(
            '<div class="writing-card-kicker--featured">'
            "<span>Article v0.5: Council-Assisted Scoring</span>"
            "</div>",
            encoding="utf-8",
        )

        for index, label in enumerate(valid_labels):
            article = root / f"valid-{index}.html"
            article.write_text(label, encoding="utf-8")
            release, error = check_banner._featured_article_release(
                str(root), article.name
            )
            findings = validate_site.validate_writing_release_alignment(
                hub, article, route
            )
            if release != "v0.5" or error is not None or findings:
                raise AssertionError(
                    "both release validators must accept the same semantic label "
                    f"variation; banner={(release, error)!r}, shared={findings!r}"
                )

        malformed_labels = (
            ("source", ""),
            (
                "generated",
                "<span>Article v0.5: First label</span>"
                "<strong>Article v0.6: Second label</strong>",
            ),
        )
        for label_kind, content in malformed_labels:
            article = root / f"{label_kind}-article.html"
            article.write_text(content, encoding="utf-8")
            relative_path = article.relative_to(ROOT).as_posix()
            release, error = check_banner._featured_article_release(
                str(root), article.name
            )
            findings = validate_site.validate_writing_release_alignment(
                hub, article, route
            )
            if release is not None or error is None:
                raise AssertionError(
                    f"banner validator must reject {label_kind} label set: "
                    f"{(release, error)!r}"
                )
            if route not in error or article.name not in error:
                raise AssertionError(
                    f"banner diagnostic must identify route and path: {error!r}"
                )
            if len(findings) != 1:
                raise AssertionError(
                    f"shared validator must produce one finding for {label_kind}: "
                    f"{findings!r}"
                )
            finding = findings[0]
            if route not in finding.msg or relative_path not in finding.page:
                raise AssertionError(
                    f"shared diagnostic must identify route and path: {finding!r}"
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
            f"{check_banner.OLD_BANNERS[2]}</a>",
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
    repair_target = "v0.6 is live: refreshed copy →"
    for mode in ("--dry-run", "--update"):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid_article = "<span>Article v0.6: Council-Assisted Scoring</span>"
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
                f"{check_banner.OLD_BANNERS[1]}</a>",
                encoding="utf-8",
            )
            before = banner.read_text(encoding="utf-8")
            output = StringIO()
            with (
                patch.object(check_banner, "__file__", str(root / "scripts/check-banner.py")),
                patch.object(check_banner, "CANONICAL_BANNER", repair_target),
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
                if repair_target not in after:
                    raise AssertionError("update did not apply the canonical banner")
                if check_banner.OLD_BANNERS[1] in after:
                    raise AssertionError("update left the old banner in place")


def check_generated_build_blocks_release_disagreement() -> None:
    for check in (False, True):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / check_banner.FEATURED_ARTICLE_SOURCE
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_content = "<span>Article v0.6: Source release</span>"
            source_path.write_text(source_content, encoding="utf-8")

            generated_path = root / check_banner.FEATURED_ARTICLE_GENERATED
            generated_path.parent.mkdir(parents=True, exist_ok=True)
            previous_output = "<span>Article v0.5: Previously generated release</span>"
            generated_path.write_text(previous_output, encoding="utf-8")
            feed_path = root / "feed.xml"
            previous_feed = "<feed>Previously generated feed</feed>"
            feed_path.write_text(previous_feed, encoding="utf-8")
            manifest = root / "site-src" / "pages.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps({"pages": [{"path": check_banner.FEATURED_ARTICLE_GENERATED}]}),
                encoding="utf-8",
            )

            namespace = build_site.build.__globals__
            with (
                patch.dict(
                    namespace,
                    {
                        "ROOT": root,
                        "MANIFEST": manifest,
                        "SITEMAP": root / "sitemap.xml",
                        "ATOM_FEED": feed_path,
                        "policies": lambda: ({}, lambda _path: "document"),
                        "render_page": lambda *_args: (
                            "<span>Article v0.7: Newly rendered release</span>"
                        ),
                    },
                ),
                patch.object(
                    namespace["subprocess"],
                    "run",
                    return_value=SimpleNamespace(returncode=0),
                ),
            ):
                result = build_site.build(check=check)

            mode = "--check" if check else "generation"
            if result != 1:
                raise AssertionError(
                    f"build-site {mode} accepted source/generated release disagreement: {result}"
                )
            if source_path.read_text(encoding="utf-8") != source_content:
                raise AssertionError(f"build-site {mode} changed source release evidence")
            if generated_path.read_text(encoding="utf-8") != previous_output:
                raise AssertionError(
                    f"build-site {mode} overwrote generated release evidence after parity failed"
                )
            if feed_path.read_text(encoding="utf-8") != previous_feed:
                raise AssertionError(
                    f"build-site {mode} changed the Atom feed after parity failed"
                )


def check_build_blocks_missing_or_ambiguous_featured_release() -> None:
    source_relative = check_banner.FEATURED_ARTICLE_SOURCE
    generated_relative = check_banner.FEATURED_ARTICLE_GENERATED
    route = check_banner.FEATURED_ARTICLE_ROUTE
    source_content = "<span>Article v0.6: Source release</span>"
    previous_output = "<span>Article v0.5: Previously generated release</span>"
    sitemap_content = "<urlset><url><loc>preserved</loc></url></urlset>"
    feed_content = "<feed>Previously generated feed</feed>"
    scenarios = (
        (
            "missing manifest route",
            [{"path": "about/index.html"}],
            {"about/index.html": "<main>Other page</main>"},
            generated_relative,
        ),
        (
            "missing rendered label",
            [{"path": generated_relative}],
            {generated_relative: "<main>No release label</main>"},
            generated_relative,
        ),
        (
            "ambiguous rendered labels",
            [{"path": generated_relative}],
            {
                generated_relative: (
                    "<span>Article v0.6: First release</span>"
                    "<strong>Article v0.7: Second release</strong>"
                )
            },
            generated_relative,
        ),
    )
    checker_data = {
        "FEATURED_ARTICLE_SOURCE": source_relative,
        "FEATURED_ARTICLE_GENERATED": generated_relative,
        "FEATURED_ARTICLE_ROUTE": route,
        "_ARTICLE_RELEASE_RE": check_banner._ARTICLE_RELEASE_RE,
        "_featured_article_release": check_banner._featured_article_release,
        "visible_html_markup": check_banner.visible_html_markup,
    }

    for check in (False, True):
        for name, pages, rendered_by_path, expected_path in scenarios:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                source_path = root / source_relative
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_text(source_content, encoding="utf-8")
                generated_path = root / generated_relative
                generated_path.parent.mkdir(parents=True, exist_ok=True)
                generated_path.write_text(previous_output, encoding="utf-8")
                sitemap = root / "sitemap.xml"
                sitemap.write_text(sitemap_content, encoding="utf-8")
                feed = root / "feed.xml"
                feed.write_text(feed_content, encoding="utf-8")
                manifest = root / "site-src" / "pages.json"
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(json.dumps({"pages": pages}), encoding="utf-8")

                output = StringIO()
                errors = StringIO()
                namespace = build_site.build.__globals__
                with (
                    patch.dict(
                        namespace,
                        {
                            "ROOT": root,
                            "MANIFEST": manifest,
                            "SITEMAP": sitemap,
                            "ATOM_FEED": feed,
                            "policies": lambda: ({}, lambda _path: "document"),
                            "render_page": lambda page, *_args: rendered_by_path[
                                page["path"]
                            ],
                        },
                    ),
                    patch.object(
                        namespace["runpy"], "run_path", return_value=checker_data
                    ),
                    patch.object(
                        namespace["subprocess"],
                        "run",
                        return_value=SimpleNamespace(returncode=0),
                    ),
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    result = build_site.build(check=check)

                mode = "--check" if check else "generation"
                diagnostic = errors.getvalue()
                if result != 1:
                    raise AssertionError(
                        f"build-site {mode} accepted {name}: {output.getvalue()}"
                    )
                if route not in diagnostic or expected_path not in diagnostic:
                    raise AssertionError(
                        f"build-site {mode} {name} lacks route/path diagnostic: "
                        f"{diagnostic}"
                    )
                if source_path.read_text(encoding="utf-8") != source_content:
                    raise AssertionError(
                        f"build-site {mode} {name} changed source evidence"
                    )
                if generated_path.read_text(encoding="utf-8") != previous_output:
                    raise AssertionError(
                        f"build-site {mode} {name} overwrote generated evidence"
                    )
                if sitemap.read_text(encoding="utf-8") != sitemap_content:
                    raise AssertionError(
                        f"build-site {mode} {name} changed sitemap evidence"
                    )
                if feed.read_text(encoding="utf-8") != feed_content:
                    raise AssertionError(
                        f"build-site {mode} {name} changed Atom feed evidence"
                    )


def check_successful_parity_run_generates_feed() -> None:
    source_relative = check_banner.FEATURED_ARTICLE_SOURCE
    generated_relative = check_banner.FEATURED_ARTICLE_GENERATED
    source_content = "<span>Article v0.6: Source release</span>"
    rendered_content = "<span>Article v0.6: Rendered release</span>"
    generated_feed = "<feed>Generated after successful parity</feed>"
    checker_data = {
        "FEATURED_ARTICLE_SOURCE": source_relative,
        "FEATURED_ARTICLE_GENERATED": generated_relative,
        "FEATURED_ARTICLE_ROUTE": check_banner.FEATURED_ARTICLE_ROUTE,
        "_ARTICLE_RELEASE_RE": check_banner._ARTICLE_RELEASE_RE,
        "_featured_article_release": check_banner._featured_article_release,
        "visible_html_markup": check_banner.visible_html_markup,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source_path = root / source_relative
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(source_content, encoding="utf-8")
        generated_path = root / generated_relative
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = root / "site-src" / "pages.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({"pages": [{"path": generated_relative}]}), encoding="utf-8"
        )
        feed = root / "feed.xml"
        feed.write_text("<feed>Previous feed</feed>", encoding="utf-8")
        feed_generator = root / "scripts" / "generate-atom-feed.py"
        commands = []

        def run(command, cwd):
            commands.append(command)
            if str(feed_generator) in command and "--check" not in command:
                feed.write_text(generated_feed, encoding="utf-8")
            return SimpleNamespace(returncode=0)

        namespace = build_site.build.__globals__
        with (
            patch.dict(
                namespace,
                {
                    "ROOT": root,
                    "MANIFEST": manifest,
                    "SITEMAP": root / "sitemap.xml",
                    "ATOM_FEED": feed,
                    "ATOM_FEED_GENERATOR": feed_generator,
                    "policies": lambda: ({}, lambda _path: "document"),
                    "render_page": lambda *_args: rendered_content,
                },
            ),
            patch.object(namespace["runpy"], "run_path", return_value=checker_data),
            patch.object(namespace["subprocess"], "run", side_effect=run),
        ):
            for check in (False, True):
                commands.clear()
                result = build_site.build(check=check)

                if result != 0:
                    mode = "--check" if check else "generation"
                    raise AssertionError(
                        f"build-site {mode} rejected matching featured releases: {result}"
                    )
                feed_commands = [
                    command for command in commands if str(feed_generator) in command
                ]
                if len(feed_commands) != 1 or (("--check" in feed_commands[0]) != check):
                    raise AssertionError(
                        f"successful parity run used the wrong feed mode: {feed_commands}"
                    )
                if feed.read_text(encoding="utf-8") != generated_feed:
                    raise AssertionError(
                        "successful parity run did not preserve expected feed behavior"
                    )


def main() -> int:
    featured = "/writings/first-diagram-is-a-liar/#council-scoring"
    stale_release = "v0.6"
    check_article_release_variations()
    check_shared_article_release_contract()
    check_hidden_article_release_decoys()
    release_failure = (
        f"banner release mismatch for {check_banner.FEATURED_ARTICLE_ROUTE}",
        f"expected {stale_release}",
        "found v1.0",
    )
    release_drift_failure = release_failure[:2] + ("found v0.5",)
    stale_source_failure = release_failure + (check_banner.SOURCE_BANNER,)
    check_main_case(
        "stale source partial reports featured route and expected release",
        check_banner.SOURCE_BANNER,
        f'<a class="site-specials-link" data-banner-release="v1.0" href="{featured}">{check_banner.CANONICAL_BANNER}</a>',
        stale_source_failure,
    )
    stale_generated_failure = release_failure + (check_banner.FEATURED_ARTICLE_GENERATED,)
    check_main_case(
        "stale generated banner reports featured route and expected release",
        check_banner.FEATURED_ARTICLE_GENERATED,
        f'<a class="site-specials-link" data-banner-release="v1.0" href="{featured}">{check_banner.CANONICAL_BANNER}</a>',
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
                f"{check_banner.OLD_BANNERS[2]}</a>",
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
                f'<a class="site-specials-link" href="{featured}">{check_banner.OLD_BANNERS[1]}</a>',
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
            f'<a class="site-specials-link" href="{featured}">{check_banner.OLD_BANNERS[1]}</a>',
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
    check_generated_build_blocks_release_disagreement()
    check_build_blocks_missing_or_ambiguous_featured_release()
    check_successful_parity_run_generates_feed()
    print("check-banner localized regression checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

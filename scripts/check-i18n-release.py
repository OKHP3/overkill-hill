#!/usr/bin/env python3
"""Apply this site's published-locale gate around the portable i18n detector."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DETECTOR_PATH = ROOT / ".agents" / "skills" / "okhp3-i18n-page-sync" / "scripts" / "i18n-page-sync.py"


class ContentCoverageParser(HTMLParser):
    """Collect visible main-content structure without comparing translated prose."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_depth = 0
        self.headings: list[dict[str, str]] = []
        self.heading_counts: dict[str, int] = {}
        self.content_blocks: dict[str, int] = {}
        self.protected_links: set[str] = set()
        self.current_heading: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "main":
            self.main_depth += 1
        if not self.main_depth:
            return
        if tag in {f"h{level}" for level in range(1, 7)}:
            self.heading_counts[tag] = self.heading_counts.get(tag, 0) + 1
            self.current_heading = {
                "level": tag,
                "id": attributes.get("id") or "",
                "ordinal": str(self.heading_counts[tag]),
                "text": "",
            }
        elif tag in {"p", "li", "blockquote", "figure", "table"}:
            self.content_blocks[tag] = self.content_blocks.get(tag, 0) + 1
        elif tag == "a":
            href = (attributes.get("href") or "").strip()
            if urlsplit(href).scheme.lower() in {"http", "https", "mailto", "tel"}:
                self.protected_links.add(href)

    def handle_data(self, data: str) -> None:
        if self.main_depth and self.current_heading is not None:
            self.current_heading["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag in {f"h{level}" for level in range(1, 7)} and self.current_heading:
            self.current_heading["text"] = " ".join(self.current_heading["text"].split())
            self.headings.append(self.current_heading)
            self.current_heading = None
        if tag == "main" and self.main_depth:
            self.main_depth -= 1


def compare_content_coverage(
    source_path: Path,
    target_path: Path,
    locale: str,
    route: str,
) -> dict[str, Any] | None:
    """Report structural content absent from a locale page, without gating it."""
    source = ContentCoverageParser()
    target = ContentCoverageParser()
    source.feed(source_path.read_text(encoding="utf-8"))
    target.feed(target_path.read_text(encoding="utf-8"))

    omissions: list[dict[str, Any]] = []
    target_heading_ids = {heading["id"] for heading in target.headings if heading["id"]}
    for heading in source.headings:
        if heading["id"] and heading["id"] not in target_heading_ids:
            omissions.append({
                "kind": "heading",
                "heading": heading["text"],
                "heading_id": heading["id"],
                "detail": f"source {heading['level']} is absent from the locale page",
            })
    for level, source_count in source.heading_counts.items():
        target_count = target.heading_counts.get(level, 0)
        if source_count > target_count:
            omissions.append({
                "kind": "heading_coverage",
                "level": level,
                "source_count": source_count,
                "target_count": target_count,
                "omitted_count": source_count - target_count,
            })
    for block, source_count in source.content_blocks.items():
        target_count = target.content_blocks.get(block, 0)
        if source_count > target_count:
            omissions.append({
                "kind": "content_block",
                "block": block,
                "source_count": source_count,
                "target_count": target_count,
                "omitted_count": source_count - target_count,
            })
    for href in sorted(source.protected_links - target.protected_links):
        omissions.append({"kind": "protected_link", "href": href})
    if not omissions:
        return None
    return {
        "locale": locale,
        "route": route,
        "source_path": source_path.relative_to(ROOT).as_posix(),
        "target_path": target_path.relative_to(ROOT).as_posix(),
        "omissions": omissions,
    }


def collect_source_coverage(
    items: list[dict[str, Any]],
    config: Dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare existing source/target pairs for configured advisory locales."""
    locales = set(config.get("advisory_content_coverage_locales", []))
    gaps = []
    for item in items:
        if item.get("locale") not in locales:
            continue
        source_relative = item.get("source_path")
        target_relative = item.get("target_path")
        if not isinstance(source_relative, str) or not isinstance(target_relative, str):
            continue
        source_path = ROOT / source_relative
        target_path = ROOT / target_relative
        if not source_path.is_file() or not target_path.is_file():
            continue
        gap = compare_content_coverage(
            source_path,
            target_path,
            item["locale"],
            item["route"],
        )
        if gap is not None:
            gaps.append(gap)
    return gaps


def load_site_config() -> Dict[str, Any]:
    path = ROOT / "i18n" / "sync.config.json"
    if not path.is_file():
        raise ValueError(f"missing site i18n policy: {path}")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid site i18n policy: {exc}") from exc
    if not isinstance(config, dict) or config.get("schema_version") != "1.0":
        raise ValueError("site i18n policy must declare schema_version 1.0")
    blocking = config.get("blocking_locales")
    targets = config.get("target_locales", {})
    if not isinstance(blocking, list) or not all(isinstance(item, str) for item in blocking):
        raise ValueError("blocking_locales must be a list of locale keys")
    unknown = sorted(set(blocking) - set(targets))
    if unknown:
        raise ValueError(f"blocking_locales contains unconfigured locales: {unknown}")
    coverage_locales = config.get("advisory_content_coverage_locales", [])
    if not isinstance(coverage_locales, list) or not all(
        isinstance(item, str) for item in coverage_locales
    ):
        raise ValueError("advisory_content_coverage_locales must be a list of locale keys")
    unknown_coverage = sorted(set(coverage_locales) - set(targets))
    if unknown_coverage or set(coverage_locales).intersection(blocking):
        raise ValueError("content coverage locales must be configured and advisory")
    return config


def run_detector(config_path: Path, mode: str = "report") -> Dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(DETECTOR_PATH), "--root", str(ROOT), "--config", str(config_path), "--mode", mode, "--format", "json"],
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise ValueError(f"portable i18n detector failed ({completed.returncode}): {completed.stderr.strip()}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"portable i18n detector returned malformed JSON: {exc}") from exc
    if mode == "report" and (not isinstance(result, dict) or not all(key in result for key in ("missing", "stale", "needs_baseline", "in_sync", "orphan"))):
        raise ValueError("portable i18n detector returned an incomplete report")
    return result


def page_hash(path: Path) -> str:
    """Match ledger v1 hashes after only CRLF-to-LF normalization."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_state(config: Dict[str, Any]) -> Dict[str, Any]:
    path = ROOT / config.get("state_file", "i18n/sync-state.json")
    if not path.exists():
        return {"schema_version": "1.0", "pages": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("schema_version") != "1.0" or not isinstance(state.get("pages"), dict):
        raise ValueError("site i18n ledger must declare schema_version 1.0 and pages")
    return state


def load_results(config: Dict[str, Any]) -> Dict[str, Any]:
    config_path = ROOT / "i18n" / "sync.config.json"
    results = run_detector(config_path)
    state = load_state(config)
    results["target_changed"] = []
    for status in ("stale", "in_sync"):
        for item in results[status]:
            if "target_path" not in item:
                raise ValueError("portable i18n report is missing target_path")
            recorded = state["pages"].get(item["route"], {}).get("targets", {}).get(item["locale"], {})
            current_hash = page_hash(ROOT / item["target_path"])
            if recorded.get("target_sha256") != current_hash:
                results["target_changed"].append(
                    {
                        **item,
                        "reviewed_target_sha256": recorded.get("target_sha256"),
                        "current_target_sha256": current_hash,
                    }
                )
    coverage_items = [
        item
        for status in ("stale", "in_sync", "needs_baseline")
        for item in results.get(status, [])
    ]
    results["source_coverage_gaps"] = collect_source_coverage(
        coverage_items,
        config,
    )
    blocking = set(config["blocking_locales"])
    blocking_items: List[Dict[str, Any]] = []
    advisory_items: List[Dict[str, Any]] = []
    for status in ("missing", "stale", "needs_baseline", "target_changed"):
        for item in results[status]:
            (blocking_items if item["locale"] in blocking else advisory_items).append(
                {"status": status, **item}
            )
    advisory_items.extend(
        {"status": "source_coverage_gap", **item}
        for item in results["source_coverage_gaps"]
    )
    return {
        **results,
        "policy": {
            "blocking_locales": sorted(blocking),
            "blocking_items": blocking_items,
            "advisory_items": advisory_items,
        },
    }


def load_provenance(path: Path, locales: List[str], routes: List[str], config: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"reviewed provenance is missing: {path}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid reviewed provenance: {exc}") from exc
    if not isinstance(record, dict):
        raise ValueError("reviewed provenance must be an object")
    if len(locales) != 1:
        raise ValueError("adoption requires exactly one selected locale per provenance record")
    selected_locale = locales[0]
    configured = set(config["target_locales"])
    if not set(locales) <= configured:
        raise ValueError("adoption locales must be configured target locales")
    expected_pair = f"en-US -> {config['target_locales'][selected_locale]['locale']}"
    if record.get("language_pair") != expected_pair:
        raise ValueError(f"reviewed provenance must declare {expected_pair}")
    if record.get("review_status") not in {"ai-reviewed", "approved"}:
        raise ValueError("reviewed provenance must be ai-reviewed or approved")
    if record.get("native_or_human_approval") is True and record.get("review_status") == "ai-reviewed":
        raise ValueError("ai-reviewed provenance cannot claim human or native approval")
    record_routes = record.get("routes")
    if not isinstance(record_routes, list) or not all(isinstance(item, dict) and isinstance(item.get("route"), str) for item in record_routes):
        raise ValueError("reviewed provenance routes must be route records")
    entries = {item["route"]: item for item in record_routes}
    if len(entries) != len(record_routes):
        raise ValueError("reviewed provenance has duplicate routes")
    for route in routes:
        entry = entries.get(route)
        expected_target = f"{config['target_locales'][selected_locale]['root'].strip('/')}/{route.strip('/')}/index.html" if route.strip('/') else f"{config['target_locales'][selected_locale]['root'].strip('/')}/index.html"
        if entry is None or entry.get("locale") != selected_locale or entry.get("target_path") != expected_target:
            raise ValueError(f"reviewed provenance does not cover selected locale route: {route}")
        if entry.get("disposition") not in {"retained-ai-reviewed", "approved", "no-semantic-delta-ai-reviewed"}:
            raise ValueError(f"reviewed provenance does not cover route: {route}")
    return record


def adopt(locales: List[str], routes: List[str], provenance: Path, config: Dict[str, Any]) -> int:
    if not locales or not routes:
        raise ValueError("adoption requires explicit --locales and --routes")
    record = load_provenance(provenance, locales, routes, config)
    reduced = dict(config)
    reduced["target_locales"] = {key: config["target_locales"][key] for key in locales}
    with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
        temp_dir_path = Path(temp_dir)
        temp_state = temp_dir_path / "sync-state.json"
        reduced["state_file"] = str(temp_state)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(reduced, handle, indent=2, ensure_ascii=False)
            temp_config = Path(handle.name)
        try:
            outcome = run_detector(temp_config, mode="adopt")
            if not isinstance(outcome, dict) or not isinstance(outcome.get("adopted"), list):
                raise ValueError("portable i18n detector returned malformed adopt output")
            adopted = outcome["adopted"]
            required_fields = ("route", "locale", "source_path", "target_path")
            if not all(
                isinstance(item, dict)
                and all(isinstance(item.get(field), str) and item[field].strip() for field in required_fields)
                for item in adopted
            ):
                raise ValueError("portable i18n detector returned adopted items with missing or empty fields")
            adopted_routes = [item["route"] for item in adopted]
            if len(set(adopted_routes)) != len(adopted_routes):
                raise ValueError("portable i18n detector returned duplicate adopted routes")
            if any(item["locale"] != locales[0] for item in adopted):
                raise ValueError("portable i18n detector returned an unexpected adopted locale")
            if not set(routes) <= set(adopted_routes):
                raise ValueError("portable i18n detector did not adopt every requested route")
            by_route = {item["route"]: item for item in record["routes"]}
            state = json.loads(temp_state.read_text(encoding="utf-8"))
            for route in routes:
                adopted = state["pages"].get(route, {}).get("targets", {}).get(locales[0])
                if adopted is None:
                    raise ValueError(f"selected route must have existing source and target in configured scope: {route}")
                entry = by_route[route]
                if entry.get("source_sha256") != adopted.get("synced_source_sha256") or entry.get("target_sha256") != adopted.get("target_sha256"):
                    raise ValueError(f"reviewed provenance hashes do not match current files: {route}")
        finally:
            temp_config.unlink(missing_ok=True)
    source_coverage_gaps = collect_source_coverage(outcome["adopted"], config)
    ledger = load_state(config)
    adopted_items = []
    by_route = {item["route"]: item for item in outcome["adopted"]}
    for route in dict.fromkeys(routes):
        target = state["pages"][route]["targets"][locales[0]]
        item = by_route[route]
        if page_hash(ROOT / item["source_path"]) != target["synced_source_sha256"] or page_hash(ROOT / item["target_path"]) != target["target_sha256"]:
            raise ValueError(f"files changed during reviewed adoption: {route}")
        page = ledger["pages"].setdefault(route, {"targets": {}})
        page.setdefault("targets", {}).setdefault(locales[0], {}).update(target)
        adopted_items.append(item)
    state_path = ROOT / config.get("state_file", "i18n/sync-state.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=state_path.parent, delete=False) as handle:
        pending = Path(handle.name)
        try:
            json.dump(ledger, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        finally:
            handle.close()
    try:
        pending.replace(state_path)
    finally:
        pending.unlink(missing_ok=True)
    print(json.dumps({
        "adopted": adopted_items,
        "source_coverage_gaps": source_coverage_gaps,
    }, ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("report", "check", "adopt"), default="report")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--locales", nargs="*", default=None)
    parser.add_argument("--routes", nargs="*", default=None)
    parser.add_argument("--provenance", type=Path)
    args = parser.parse_args(argv)
    try:
        config = load_site_config()
        if args.mode == "adopt":
            if args.provenance is None:
                raise ValueError("--provenance is required for adoption")
            return adopt(args.locales or [], args.routes or [], args.provenance.resolve(), config)
        results = load_results(config)
        if args.format == "json":
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"i18n release policy: blocking locales={','.join(results['policy']['blocking_locales'])}")
            for status in ("missing", "stale", "needs_baseline", "target_changed"):
                for item in results[status]:
                    label = "BLOCKING" if item["locale"] in config["blocking_locales"] else "ADVISORY"
                    print(f"{label:9} {status:14} {item['route']:20} -> {item['locale']}")
            for item in results["source_coverage_gaps"]:
                detail = "; ".join(
                    gap.get("heading")
                    or gap.get("href")
                    or f"{gap.get('kind')}: {gap.get('block') or gap.get('level') or ''} "
                    f"({gap.get('source_count')} source / {gap.get('target_count')} target)"
                    for gap in item["omissions"][:3]
                )
                print(
                    f"ADVISORY  source_coverage_gap {item['route']:20} -> "
                    f"{item['locale']}: {detail}"
                )
        if args.mode == "check" and results["policy"]["blocking_items"]:
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

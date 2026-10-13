#!/usr/bin/env python3
"""Apply this site's published-locale gate around the portable i18n detector."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
from html.parser import HTMLParser
import json
import re
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
        self.section_headings: dict[str, dict[str, str]] = {}
        self.section_content_blocks: dict[str, dict[str, int]] = {}
        self.protected_links: set[str] = set()
        self.current_heading: dict[str, str] | None = None
        self.active_section_id = ""

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
            if self.current_heading["id"]:
                self.active_section_id = self.current_heading["id"]
                self.section_headings[self.active_section_id] = self.current_heading
        elif tag in {"p", "li", "blockquote", "figure", "table"}:
            self.content_blocks[tag] = self.content_blocks.get(tag, 0) + 1
            if self.active_section_id:
                section_blocks = self.section_content_blocks.setdefault(self.active_section_id, {})
                section_blocks[tag] = section_blocks.get(tag, 0) + 1
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
            omission = {
                "kind": "content_block",
                "block": block,
                "source_count": source_count,
                "target_count": target_count,
                "omitted_count": source_count - target_count,
            }
            section_deficits = []
            for heading_id, heading in source.section_headings.items():
                section_source_count = source.section_content_blocks.get(
                    heading_id, {}
                ).get(block, 0)
                section_target_count = target.section_content_blocks.get(
                    heading_id, {}
                ).get(block, 0)
                if section_source_count > section_target_count:
                    section_deficits.append({
                        "heading": heading["text"],
                        "heading_id": heading_id,
                        "source_count": section_source_count,
                        "target_count": section_target_count,
                        "omitted_count": section_source_count - section_target_count,
                    })
            if section_deficits:
                omission["sections"] = section_deficits
            omissions.append(omission)
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


def load_coverage_dispositions(config: Dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Load only current-hash route decisions for advisory coverage gaps."""
    record_paths = config.get("advisory_coverage_review_records", {})
    if not isinstance(record_paths, dict):
        raise ValueError("advisory_coverage_review_records must map locale keys to review files")
    ledger = load_state(config)
    target_locales = config.get("target_locales", {})
    dispositions: dict[tuple[str, str], dict[str, Any]] = {}

    for locale in config.get("advisory_content_coverage_locales", []):
        relative_record = record_paths.get(locale)
        if relative_record is None:
            continue
        if not isinstance(relative_record, str) or not relative_record.strip():
            raise ValueError(f"coverage review record path is invalid for {locale}")
        path = ROOT / relative_record
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid coverage review record for {locale}: {exc}") from exc
        locale_config = target_locales.get(locale, {})
        expected_pair = f"en-US -> {locale_config.get('locale')}"
        reviewed_on = record.get("reviewed_on") if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or record.get("record_type") != "content-coverage-disposition"
            or record.get("language_pair") != expected_pair
            or record.get("review_status") not in {"ai-reviewed", "approved"}
            or record.get("native_or_human_approval") is not False
            or record.get("release_accepted") is not False
            or not isinstance(reviewed_on, str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed_on)
            or not isinstance(record.get("routes"), list)
        ):
            raise ValueError(f"coverage review record for {locale} has invalid review or release status")
        try:
            date.fromisoformat(reviewed_on)
        except ValueError as exc:
            raise ValueError(f"coverage review record for {locale} has an invalid review date") from exc
        record_name = path.relative_to(ROOT).as_posix()
        expected_root = locale_config.get("root", "").strip("/")
        seen_routes: set[str] = set()
        for entry in record["routes"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("route"), str):
                raise ValueError(f"coverage review record for {locale} has an invalid route entry")
            route = entry["route"]
            if route in seen_routes:
                raise ValueError(f"coverage review record for {locale} repeats route {route}")
            seen_routes.add(route)
            expected_target = (
                f"{expected_root}/{route.strip('/')}/index.html"
                if route.strip("/")
                else f"{expected_root}/index.html"
            )
            if (
                entry.get("locale") != locale
                or entry.get("target_path") != expected_target
                or not all(
                    isinstance(entry.get(field), str)
                    and re.fullmatch(r"[0-9a-f]{64}", entry[field])
                    for field in ("source_sha256", "target_sha256")
                )
            ):
                raise ValueError(
                    f"coverage review record for {locale} has invalid route hashes or target for {route}"
                )
            section_entries = entry.get("coverage_dispositions")
            if not isinstance(section_entries, list):
                raise ValueError(f"coverage review route {route} for {locale} needs coverage_dispositions")
            sections: dict[str, dict[str, str]] = {}
            for section in section_entries:
                if (
                    not isinstance(section, dict)
                    or not isinstance(section.get("section_id"), str)
                    or not section["section_id"].strip()
                    or section.get("disposition") not in {"intentional-abridgment", "unresolved"}
                    or not isinstance(section.get("rationale"), str)
                    or not section["rationale"].strip()
                ):
                    raise ValueError(
                        f"coverage review route {route} for {locale} has an invalid section disposition"
                    )
                section_id = section["section_id"]
                if section_id in sections:
                    raise ValueError(
                        f"coverage review route {route} for {locale} repeats section {section_id}"
                    )
                sections[section_id] = {
                    "disposition": section["disposition"],
                    "rationale": section["rationale"],
                }
            route_disposition = entry.get("unscoped_disposition")
            if (
                not isinstance(route_disposition, dict)
                or route_disposition.get("disposition") not in {"intentional-abridgment", "unresolved"}
                or not isinstance(route_disposition.get("rationale"), str)
                or not route_disposition["rationale"].strip()
            ):
                raise ValueError(f"coverage review route {route} for {locale} needs an unscoped disposition")

            ledger_target = (
                ledger.get("pages", {}).get(route, {}).get("targets", {}).get(locale, {})
            )
            current = (
                entry["source_sha256"] == ledger_target.get("synced_source_sha256")
                and entry["target_sha256"] == ledger_target.get("target_sha256")
            )
            dispositions[(locale, route)] = {
                "record": record_name,
                "current": current,
                "sections": sections if current else {},
                "unscoped": (
                    {
                        "disposition": route_disposition["disposition"],
                        "rationale": route_disposition["rationale"],
                    }
                    if current
                    else {
                        "disposition": "unresolved",
                        "rationale": "The review hashes do not match the current sync ledger; its decisions are not applied.",
                    }
                ),
            }
    return dispositions


def apply_coverage_dispositions(
    gaps: list[dict[str, Any]],
    config: Dict[str, Any],
) -> list[dict[str, Any]]:
    """Annotate findings without removing intentional or unresolved gaps."""
    records = load_coverage_dispositions(config)
    annotated: list[dict[str, Any]] = []
    for gap in gaps:
        review = records.get((gap["locale"], gap["route"]))
        section_decisions = review["sections"] if review else {}
        unscoped = (
            review["unscoped"]
            if review
            else {
                "disposition": "unresolved",
                "rationale": "No current-hash route review disposition is recorded.",
            }
        )
        unresolved_omissions: list[dict[str, Any]] = []
        omissions: list[dict[str, Any]] = []
        for original in gap["omissions"]:
            omission = dict(original)
            if omission.get("kind") == "heading" and omission.get("heading_id"):
                decision = section_decisions.get(omission["heading_id"], unscoped)
                omission["review_disposition"] = decision
            if isinstance(omission.get("sections"), list):
                sections = []
                for original_section in omission["sections"]:
                    section = dict(original_section)
                    decision = section_decisions.get(section.get("heading_id"), unscoped)
                    section["review_disposition"] = decision
                    sections.append(section)
                omission["sections"] = sections
                if sections:
                    omission["review_disposition"] = {
                        "disposition": (
                            "intentional-abridgment"
                            if all(
                                section["review_disposition"]["disposition"]
                                == "intentional-abridgment"
                                for section in sections
                            )
                            else "unresolved"
                        ),
                        "rationale": "See the route-and-section decisions attached to each section.",
                    }
            if "review_disposition" not in omission:
                omission["review_disposition"] = unscoped
            if omission["review_disposition"]["disposition"] == "unresolved":
                unresolved_omissions.append({
                    "kind": omission.get("kind", ""),
                    "section_ids": [
                        section.get("heading_id", "")
                        for section in omission.get("sections", [])
                        if section.get("review_disposition", {}).get("disposition") == "unresolved"
                    ],
                    "detail": omission.get("heading") or omission.get("href") or omission.get("block") or omission.get("level") or "",
                })
            omissions.append(omission)
        annotated.append({
            **gap,
            "review_record": review["record"] if review else None,
            "omissions": omissions,
            "unresolved_omissions": unresolved_omissions,
        })
    return annotated


def format_coverage_omission(omission: dict[str, Any]) -> str:
    """Format a structural coverage finding for the human-readable report."""
    if omission.get("heading"):
        detail = omission["heading"]
    elif omission.get("href"):
        detail = omission["href"]
    else:
        detail = (
            f"{omission.get('kind')}: {omission.get('block') or omission.get('level') or ''} "
            f"({omission.get('source_count')} source / {omission.get('target_count')} target)"
        )
    sections = omission.get("sections", [])
    if sections:
        section_details = ", ".join(
            f"{section.get('heading') or section.get('heading_id')} "
            f"({section.get('source_count')} source / {section.get('target_count')} target) "
            f"[{section.get('review_disposition', {}).get('disposition', 'unresolved')}]"
            for section in sections
        )
        detail += f"; sections: {section_details}"
    disposition = omission.get("review_disposition", {}).get("disposition", "unresolved")
    detail += f" [{disposition}]"
    return detail


def audit_advisory_review_evidence(config: Dict[str, Any]) -> dict[str, Any]:
    """Cross-check dated advisory review route hashes against the shared ledger."""
    locales = config.get("advisory_content_coverage_locales", [])
    routes = config.get("in_scope_routes", [])
    ledger = load_state(config)
    route_evidence: dict[tuple[str, str], list[dict[str, Any]]] = {}
    report: dict[str, Any] = {
        "records_checked": 0,
        "current_pairs": [],
        "missing": [],
        "duplicates": [],
        "superseded": [],
        "unmatched": [],
        "invalid_records": [],
    }
    target_locales = config.get("target_locales", {})

    for locale in locales:
        locale_config = target_locales.get(locale)
        if not isinstance(locale_config, dict):
            report["invalid_records"].append({
                "locale": locale, "reason": "advisory locale has no target configuration",
            })
            continue
        expected_root = locale_config["root"].strip("/")
        expected_pair = f"en-US -> {locale_config['locale']}"
        for path in sorted((ROOT / "i18n" / "pilot" / locale).glob("*-????-??-??.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                report["invalid_records"].append({
                    "locale": locale, "record": path.relative_to(ROOT).as_posix(),
                    "reason": f"invalid JSON: {exc}",
                })
                continue
            if isinstance(record, dict) and record.get("record_type") == "content-coverage-disposition":
                continue
            if not isinstance(record, dict) or not isinstance(record.get("routes"), list):
                report["invalid_records"].append({
                    "locale": locale, "record": path.relative_to(ROOT).as_posix(),
                    "reason": "dated record must contain a routes list",
                })
                continue
            report["records_checked"] += 1
            record_name = path.relative_to(ROOT).as_posix()
            reviewed_on = record.get("reviewed_on", "")
            entries: dict[str, list[dict[str, Any]]] = {}
            review_status = record.get("review_status")
            if (
                record.get("language_pair") != expected_pair
                or not isinstance(review_status, str)
                or review_status not in {"ai-reviewed", "approved"}
            ):
                report["invalid_records"].append({
                    "locale": locale, "record": record_name,
                    "reason": "review status or language pair is not valid for this advisory locale",
                })
            if not isinstance(reviewed_on, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed_on):
                report["invalid_records"].append({
                    "locale": locale, "record": record_name,
                    "reason": "reviewed_on must be an ISO calendar date",
                })
                reviewed_on = ""
            else:
                try:
                    date.fromisoformat(reviewed_on)
                except ValueError:
                    report["invalid_records"].append({
                        "locale": locale, "record": record_name,
                        "reason": "reviewed_on must be a real ISO calendar date",
                    })
                    reviewed_on = ""
            for entry in record["routes"]:
                if not isinstance(entry, dict) or not isinstance(entry.get("route"), str):
                    report["invalid_records"].append({
                        "locale": locale, "record": record_name,
                        "reason": "route entries must include a string route",
                    })
                    continue
                route = entry["route"]
                entries.setdefault(route, []).append(entry)
                expected_target = (
                    f"{expected_root}/{route.strip('/')}/index.html"
                    if route.strip("/") else f"{expected_root}/index.html"
                )
                if route not in routes or entry.get("target_path") != expected_target:
                    report["invalid_records"].append({
                        "locale": locale, "route": route, "record": record_name,
                        "reason": "route is out of scope or target_path does not match the configured locale",
                    })
                for field in ("source_sha256", "target_sha256"):
                    if not isinstance(entry.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", entry[field]):
                        report["invalid_records"].append({
                            "locale": locale, "route": route, "record": record_name,
                            "reason": f"{field} is missing or malformed",
                        })
            for route, route_entries in entries.items():
                if len(route_entries) != 1:
                    report["duplicates"].append({
                        "locale": locale, "route": route, "record": record_name,
                        "entry_count": len(route_entries),
                    })
                for entry in route_entries:
                    ledger_target = ledger.get("pages", {}).get(route, {}).get("targets", {}).get(locale, {})
                    is_current = (
                        entry.get("source_sha256") == ledger_target.get("synced_source_sha256")
                        and entry.get("target_sha256") == ledger_target.get("target_sha256")
                    )
                    evidence = {
                        "locale": locale,
                        "route": route,
                        "record": record_name,
                        "reviewed_on": reviewed_on,
                        "source_sha256": entry.get("source_sha256"),
                        "target_sha256": entry.get("target_sha256"),
                        "ledger_match": is_current,
                    }
                    route_evidence.setdefault((locale, route), []).append(evidence)

    for locale in locales:
        for route in routes:
            entries = route_evidence.get((locale, route), [])
            current = [item for item in entries if item["ledger_match"]]
            if not current:
                report["missing"].append({"locale": locale, "route": route})
            else:
                report["current_pairs"].append({
                    "locale": locale, "route": route,
                    "records": [item["record"] for item in current],
                })
                if len(current) > 1:
                    report["duplicates"].append({
                        "locale": locale, "route": route,
                        "records": [item["record"] for item in current],
                    })
            for item in entries:
                if item["ledger_match"]:
                    continue
                replacements = [
                    candidate for candidate in current
                    if candidate["reviewed_on"] > item["reviewed_on"]
                ]
                if replacements:
                    report["superseded"].append({
                        **item,
                        "superseded_by": [candidate["record"] for candidate in replacements],
                    })
                else:
                    report["unmatched"].append(item)
    return report


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
    results["source_coverage_gaps"] = apply_coverage_dispositions(
        collect_source_coverage(coverage_items, config),
        config,
    )
    results["advisory_review_evidence"] = audit_advisory_review_evidence(config)
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
                    format_coverage_omission(gap)
                    for gap in item["omissions"]
                )
                print(
                    f"ADVISORY  source_coverage_gap {item['route']:20} -> "
                    f"{item['locale']} "
                    f"(unresolved findings: {len(item['unresolved_omissions'])}): {detail}"
                )
            audit = results["advisory_review_evidence"]
            print(
                "Advisory review evidence: "
                f"{len(audit['current_pairs'])} current route pairs, "
                f"{len(audit['missing'])} missing, "
                f"{len(audit['duplicates'])} duplicate, "
                f"{len(audit['superseded'])} superseded, "
                f"{len(audit['unmatched'])} unmatched, "
                f"{len(audit['invalid_records'])} invalid"
            )
        if args.mode == "check" and results["policy"]["blocking_items"]:
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

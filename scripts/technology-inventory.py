#!/usr/bin/env python3
"""Inventory repository pins and compare them with publisher stable releases.

Standard library only. Read-only except for the explicitly named reports.
Registry errors remain UNKNOWN and exit nonzero; outdated versions do not.
This never installs packages, changes pins, or rewrites preserved media.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STABLE = re.compile(r"v?(\d+(?:\.\d+){0,3})\Z")


def version(value):
    match = STABLE.fullmatch(value)
    return tuple(map(int, match[1].split("."))) if match else None


def compare(current, latest):
    old, new = version(current), version(latest)
    if old is None or new is None:
        return "UNKNOWN"
    if len(old) < len(new) and old == new[:len(old)]:
        return "TRACKING"  # A release selector is not an observed installed patch.
    return "UPDATE" if old < new else "AHEAD" if old > new else "CURRENT"


def stable_max(values):
    candidates = [v for v in values if version(v) is not None]
    if not candidates:
        raise ValueError("Publisher response contained no stable release")
    return max(candidates, key=version).removeprefix("v")


def runtime_constraint_allows(pin, constraint):
    """Accept exact pins or the explicit bounded-major syntax used by this repo."""
    parsed = version(pin)
    if not parsed:
        return False
    if constraint == pin:
        return True
    match = re.fullmatch(r">=(\d+\.\d+\.\d+) <(\d+)", constraint or "")
    return bool(match and version(match[1]) <= parsed < (int(match[2]), 0, 0))


def fetch(url, json_response=True, *, deadline=None):
    headers = {"User-Agent": "OKHP3-technology-inventory/1.0"}
    token = None
    # Never send the GitHub token to package registries or redirected hosts.
    if urllib.parse.urlparse(url).hostname == "api.github.com":
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    for attempt in range(3):
        timeout = 25
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Version lookup time budget exhausted")
            timeout = min(timeout, remaining)
        try:
            request = urllib.request.Request(url, headers=headers)
            if token:
                request.add_unredirected_header("Authorization", "Bearer " + token)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                # read() can keep waiting forever on a slowly streaming body.
                # read1() performs at most one underlying read, so each chunk
                # returns control for a deadline check (or a socket timeout).
                chunks = []
                while True:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError("Version lookup time budget exhausted")
                    chunk = response.read1(64 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                payload = b"".join(chunks)
                if response.headers.get("Content-Encoding") == "gzip" or payload.startswith(b"\x1f\x8b"):
                    payload = gzip.decompress(payload)
                raw = payload.decode("utf-8")
            return json.loads(raw) if json_response else raw
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        delay = attempt + 1
        if deadline is not None:
            delay = min(delay, max(0, deadline - time.monotonic()))
        time.sleep(delay)


def row(name, category, current, evidence, provider, key=None, owner="review"):
    return dict(name=name, category=category, current=current, evidence=evidence,
                provider=provider, key=key or name, owner=owner)


def inventory(root):
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    direct = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    rows = []
    grouped = {}
    for path, data in lock["packages"].items():
        if not path:
            continue
        name = data.get("name") or path.rsplit("node_modules/", 1)[1]
        key = (name, data["version"])
        grouped.setdefault(key, []).append("package-lock.json:" + path)
    for (name, pin), paths in sorted(grouped.items()):
        is_direct = name in direct and "package-lock.json:node_modules/" + name in paths
        rows.append(row(name, "npm direct" if is_direct else "npm transitive", pin,
                        paths, "npm", owner="dependabot" if is_direct else "parent dependency"))
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    for path in tracked:
        if not re.search(r"(^|/)requirements[^/]*\.txt$", path):
            continue
        requirements_path = root / path
        if not requirements_path.is_file():
            continue
        for line in requirements_path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            match = re.fullmatch(r"([\w.-]+)==([\w.+-]+)", line)
            if not match:
                raise ValueError(f"Unrecognized requirement in {path}: {line}")
            rows.append(row(match[1], "Python QA", match[2], [path], "pypi", owner="dependabot"))
    actions = {}
    python = {}
    for path in sorted((root / ".github/workflows").glob("*.y*ml")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            source = f"{path.relative_to(root).as_posix()}:{number}"
            match = re.search(r"\buses:\s*([\w.-]+/[\w./-]+)@([\w.-]+)", line)
            if match:
                actions.setdefault(match.groups(), []).append(source)
            match = re.search(r"python-version:\s*['\"]?([\d.]+)", line)
            if match:
                python.setdefault(match[1], []).append(source)
    for (name, ref), paths in sorted(actions.items()):
        rows.append(row(name, "GitHub Actions", ref, paths, "github-action", owner="dependabot"))
    for pin, paths in python.items():
        rows.append(row("Python", "runtime", pin, paths, "python"))
    node = (root / ".nvmrc").read_text().strip()
    rows.append(row("Node.js", "runtime", node, [".nvmrc", ".node-version",
                    "package.json:engines.node", "package-lock.json:packages[''].engines.node"], "node"))
    rows.append(row("npm", "runtime", "bundled with Node " + node,
                    ["README.md:use npm bundled with Node"], "npm-bundled", key=node, owner="Node.js"))
    replit = (root / ".replit").read_text(encoding="utf-8")
    for name, provider, expression in [("Node.js (Replit)", "node", r'"nodejs-([\d.]+)"'),
                                       ("Python (Replit)", "python", r'"python-([\d.]+)"')]:
        match = re.search(expression, replit)
        if match:
            rows.append(row(name, "runtime", match[1], [".replit:modules"], provider))
    rows.append(row("Mermaid", "browser runtime", (root / "assets/vendor/mermaid/VERSION").read_text().strip(),
                    ["assets/vendor/mermaid/VERSION"], "npm", key="mermaid", owner="Mermaid Version Watch"))
    verification = root / "assets/murderbird/v2/production/scale-stage-verification.json"
    if verification.exists():
        pin = json.loads(verification.read_text())["blender_version"].split()[0]
        rows.append(row("Blender", "media tool", pin, [verification.relative_to(root).as_posix()], "blender"))
    renderer = "scripts/render-murderbird-first-choice.py"
    rows.append(row("numpy", "Python media", "unrecorded", [renderer], "pypi", owner="review"))
    rows.append(row("FFmpeg", "media tool", "unrecorded", [renderer], "ffmpeg"))
    host_file = root / "config/technology-host-versions.json"
    if host_file.exists():
        records = json.loads(host_file.read_text(encoding="utf-8"))
        for item in rows:
            if item["category"] != "media tool" or item["name"] not in records:
                continue
            record = records[item["name"]]
            if (version(record.get("version", "")) is None or
                    not record.get("evidence") or not record.get("verified_at")):
                raise ValueError("Host version record needs version, evidence and verified_at: " + item["name"])
            datetime.fromisoformat(record["verified_at"])
            item["current"] = record["version"]
            item["evidence"] = ["config/technology-host-versions.json", record["evidence"],
                                "verified_at=" + record["verified_at"]]
    # Source-level declarations are distinct from workstation-installed packages.
    findings = []
    node_values = {".nvmrc": node, ".node-version": (root / ".node-version").read_text().strip(),
                   "package.json": package.get("engines", {}).get("node"),
                   "package-lock.json": lock["packages"][""].get("engines", {}).get("node")}
    engine = node_values["package.json"]
    if (node_values[".node-version"] != node or
            node_values["package-lock.json"] != engine or
            not runtime_constraint_allows(node, engine)):
        findings.append("Node selectors disagree: " + json.dumps(node_values, sort_keys=True))
    npm_engine = package.get("engines", {}).get("npm")
    npm_locked_engine = lock["packages"][""].get("engines", {}).get("npm")
    if npm_engine != npm_locked_engine:
        findings.append(f"npm engine declarations disagree: manifest {npm_engine}; lock {npm_locked_engine}.")
    replit_node = re.search(r'"nodejs-(\d+)"', replit)
    if replit_node and node.split(".")[0] != replit_node[1]:
        findings.append(f"Repository Node {node} disagrees with Replit nodejs-{replit_node[1]}.")
    for name, declared in direct.items():
        locked = lock["packages"].get("node_modules/" + name, {}).get("version")
        if declared != locked:
            findings.append(f"{name}: manifest {declared} differs from lock {locked}.")
    return rows, findings


def resolve(item, deadline=None):
    provider, key = item["provider"], item["key"]
    extra = {}
    if provider == "npm":
        source = "https://registry.npmjs.org/" + urllib.parse.quote(key, safe="@/") + "/latest"
        data = fetch(source, deadline=deadline)
        latest = data["version"]
        if version(latest) is None:
            raise ValueError("npm latest tag points at a prerelease; review required")
        extra["requires"] = data.get("engines", {})
    elif provider == "pypi":
        source = "https://pypi.org/pypi/" + key + "/json"
        data = fetch(source, deadline=deadline)
        # Ignore prereleases and releases with no downloadable, non-yanked file.
        latest = stable_max(v for v, files in data["releases"].items()
                            if files and any(not f.get("yanked", False) for f in files))
        extra["requires_python"] = data["info"].get("requires_python")
    elif provider in ("node", "npm-bundled"):
        source = "https://nodejs.org/dist/index.json"
        data = fetch(source, deadline=deadline)
        releases = [d for d in data if version(d["version"]) is not None]
        latest = stable_max(d["version"] for d in releases)
        lts = stable_max(d["version"] for d in releases if d.get("lts"))
        extra["latest_lts"] = lts
        if provider == "npm-bundled":
            found = next((d for d in releases if d["version"].removeprefix("v") == key), None)
            extra["resolved_current"] = found["npm"] if found else None
            npm_source = "https://registry.npmjs.org/npm/latest"
            latest = fetch(npm_source, deadline=deadline)["version"]
            extra["additional_sources"] = [npm_source]
            extra["latest_lts_bundled_npm"] = next(d["npm"] for d in releases if d["version"] == "v" + lts)
            extra["target"] = extra["latest_lts_bundled_npm"]
        else:
            extra["target"] = lts
            train = str(version(item["current"])[0]) if version(item["current"]) else item["current"]
            extra["latest_in_current_line"] = stable_max(d["version"] for d in releases
                                                          if d["version"].startswith("v" + train + "."))
    elif provider == "python":
        source = "https://www.python.org/downloads/"
        page = fetch(source, False, deadline=deadline)
        # Anchor text must end after X.Y.Z. Never truncate 3.15.0rc2 to 3.15.0.
        releases = re.findall(r">Python (\d+\.\d+\.\d+)</a>", page)
        latest = stable_max(releases)
        train = ".".join(item["current"].split(".")[:2])
        extra["latest_in_current_line"] = stable_max(v for v in releases if v.startswith(train + "."))
    elif provider == "github-action":
        source = f"https://api.github.com/repos/{key}/releases/latest"
        release = fetch(source, deadline=deadline)
        if release.get("prerelease") or release.get("draft") or version(release["tag_name"]) is None:
            raise ValueError("Latest action release is not a stable version")
        latest = release["tag_name"].removeprefix("v")
        extra["release_url"] = release["html_url"]
        tags_url = f"https://api.github.com/repos/{key}/tags?per_page=100"
        tags = fetch(tags_url, deadline=deadline)
        matches = [t["name"] for t in tags if t["commit"]["sha"] == item["current"] and version(t["name"])]
        if not matches and re.fullmatch(r"[0-9a-f]{40}", item["current"]):
            raise ValueError("Pinned action SHA was not found among the first 100 publisher tags")
        extra["resolved_current"] = stable_max(matches) if matches else None
        extra["additional_sources"] = [tags_url]
    elif provider == "blender":
        source = "https://download.blender.org/release/"
        trains = re.findall(r'href="Blender(\d+\.\d+)/"', fetch(source, False, deadline=deadline))
        train = stable_max(trains)
        source += "Blender" + train + "/"
        latest = stable_max(re.findall(r"blender-(\d+\.\d+\.\d+)-", fetch(source, False, deadline=deadline)))
    elif provider == "ffmpeg":
        source = "https://ffmpeg.org/releases/"
        latest = stable_max(re.findall(r'href="ffmpeg-(\d+\.\d+(?:\.\d+)?).tar', fetch(source, False, deadline=deadline)))
    else:
        raise ValueError("Unknown release provider: " + provider)
    if version(latest) is None:
        raise ValueError("Release is not a numeric stable version: " + latest)
    current = extra.get("resolved_current") or item["current"]
    if extra.get("target"):
        extra["target_status"] = compare(current, extra["target"])
    return dict(latest=latest, source=source, status=compare(current, latest), **extra)


def enrich(rows, deadline=None):
    def one(item):
        try:
            return {**item, **resolve(item, deadline=deadline)}
        except Exception as exc:
            # Do not include HTTP response bodies, which could contain credentials.
            return {**item, "latest": None, "status": "UNKNOWN", "error": str(exc)}
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(one, rows))


def upstream_inventory(rows, deadline=None):
    """Expose unresolvable bundle pins without pretending ranges are installed versions."""
    additions = []
    mermaid = next(r for r in rows if r["name"] == "Mermaid")
    source = "https://registry.npmjs.org/mermaid/" + mermaid["current"]
    try:
        package = fetch(source, deadline=deadline)
        for name, constraint in sorted(package["dependencies"].items()):
            item = row(name, "Mermaid publisher requirements", "unrecorded (" + constraint + ")",
                       [source], "npm", owner="parent dependency")
            item["declared_constraint"] = constraint
            additions.append(item)
    except Exception as exc:
        additions.append({**row("Mermaid package metadata", "Mermaid publisher requirements",
                               "unrecorded", [source], "npm", owner="parent dependency"),
                          "error": str(exc), "latest": None, "status": "UNKNOWN"})
    enriched = enrich([r for r in additions if "error" not in r], deadline=deadline)
    enriched.extend(r for r in additions if "error" in r)
    return enriched


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(report, concise=False):
    lines = ["# Technology version inventory", "", f"Retrieved: {report['retrieved_at']}.",
             f"Source commit: `{report['source_commit']}`. Working-tree files were read.", "",
             "CURRENT compares declared pins with publisher releases. TRACKING means a release-line selector, "
             "not a verified installed patch. UNKNOWN is not a pass. Latest does not mean compatible.", ""]
    if report["findings"]:
        lines += ["## Configuration findings", ""] + ["- " + f for f in report["findings"]] + [""]
    categories = list(dict.fromkeys(r["category"] for r in report["technologies"]))
    for category in categories:
        if concise and category in ("npm transitive", "Mermaid publisher requirements"):
            continue
        lines += ["## " + category, "", "| Technology | In place | Latest stable | Result | Evidence and update owner |",
                  "| --- | --- | --- | --- | --- |"]
        for r in report["technologies"]:
            if r["category"] != category:
                continue
            pin = r["current"]
            if r.get("resolved_current"):
                pin = r["resolved_current"] + " (" + pin + ")"
            latest = str(r.get("latest") or "UNKNOWN")
            if r.get("source"):
                latest = f"[{latest}]({r['source']})"
            if r.get("latest_lts") and r["provider"] == "node":
                latest += f"; LTS {r['latest_lts']}"
            if r.get("latest_in_current_line"):
                latest += f"; current line {r['latest_in_current_line']}"
            evidence = ", ".join("`" + e + "`" for e in r["evidence"])
            lines.append("| " + " | ".join(map(cell, [r["name"], pin, latest, r["status"], evidence + "; " + r["owner"]])) + " |")
            if r.get("error"):
                lines += ["", "Lookup error: " + cell(r["name"]) + ": " + cell(r["error"]), ""]
        lines.append("")
    lines += ["## Reading this report", "",
              "All npm lock entries are included, including duplicates at different versions. "
              "Update transitive dependencies through their parent and lockfile, never by replacing nested pins with arbitrary latest versions.", "",
              "Python requirements are declarations, not a complete resolved environment. "
              "Mermaid publisher requirements show the upstream package's constraints, not proven versions "
              "inside this vendored bundle; the package also lists build/type dependencies. "
              "Further nested bundle dependencies cannot be recovered exactly without the publisher's build lock/SBOM. "
              "Media-native libraries, hosted services and standards are covered by the companion audit and update plan. "
              "Browser binaries follow Playwright's own browser manifest.", "",
              "See `docs/technology-update-policy.md` for ownership, activation, validation, rollback and limitations.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--offline", action="store_true", help="Inventory declarations without network access")
    parser.add_argument("--lookup-budget-seconds", type=float, default=600,
                        help="Shared network lookup budget; unfinished lookups remain UNKNOWN (default: 600)")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args(argv)
    if not 0 < args.lookup_budget_seconds <= 600:
        parser.error("--lookup-budget-seconds must be greater than zero and no more than 600")
    rows, findings = inventory(args.root)
    # One deadline covers both phases and every worker, including queued rows.
    # Leave five minutes of the workflow budget for evidence upload/reporting.
    deadline = time.monotonic() + args.lookup_budget_seconds
    rows = ([{**r, "latest": None, "status": "NOT_CHECKED"} for r in rows]
            if args.offline else enrich(rows, deadline=deadline))
    if not args.offline and any(r.get("name") == "Mermaid" for r in rows):
        rows += upstream_inventory(rows, deadline=deadline)
    report = dict(schema_version=1, retrieved_at=datetime.now(timezone.utc).isoformat(),
                  source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.root, text=True).strip(),
                  technologies=rows, findings=findings)
    for path, content in [(args.json_output, json.dumps(report, indent=2) + "\n"),
                          (args.markdown_output, markdown(report)),
                          (args.summary_output, markdown(report, concise=True))]:
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    counts = {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})}
    print(json.dumps(dict(technologies=len(rows), statuses=counts, findings=findings), indent=2))
    return 1 if any("error" in r for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())

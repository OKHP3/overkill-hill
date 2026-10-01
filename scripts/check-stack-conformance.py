#!/usr/bin/env python3
"""Assert (and optionally repair) the canonical OKHP3 static-site stack, ADR 0007.

Standard library only, by design: this runs before any dependency is
installed, and a conformance checker that needs the toolchain it checks is
not a conformance checker.

Usage:
    python3 scripts/check-stack-conformance.py
    python3 scripts/check-stack-conformance.py --json
    python3 scripts/check-stack-conformance.py --warn-only
    python3 scripts/check-stack-conformance.py --fix
    python3 scripts/check-stack-conformance.py --fix --dry-run

Exit codes:
    0  conformant, or --warn-only
    1  one or more FAIL findings remain
    2  the checker itself could not run

--fix repairs only mechanical, reversible items: writing .node-version,
appending .gitignore entries,
bumping the deploy-pages action major, and untracking forbidden paths with
`git rm -r --cached` (which leaves the working tree untouched). It never
edits dependency versions, never creates a missing script, and never deletes
a file from disk. Those stay MANUAL on purpose: they are judgment calls, and
an auto-fixer that makes judgment calls is how the drift started.

Documented exemptions live in .stack-conformance.json at the repository root:

    {"exempt": ["NODE_ENGINES"], "reason": "ADR 0009, pending Node 24 migration"}

An exemption downgrades a FAIL to EXEMPT and is always reported, never hidden.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --- Canonical values (ADR 0007) --------------------------------------------

NODE_VERSION = "24.21.0"
NODE_ENGINE = ">=24.13.0 <25"
NPM_ENGINE = ">=11.6.2 <12"

# Exact pins, matching docs/dependency-policy.md in the reference repo.
NPM_REQUIRED = {
    "playwright": "1.63.0",
    "lighthouse": "13.5.0",
}

NPM_FORBIDDEN = ("puppeteer", "puppeteer-core")

# Universal Python QA pin: all three sites parse HTML from Python.
PIP_REQUIRED = {
    "beautifulsoup4": "4.15.0",
}

# Pinned only where the repo actually uses it: Pillow where an image pipeline
# exists, python-playwright where Python (not Node) drives the browser. Never
# added by this checker; if present it must match.
PIP_IF_PRESENT = {
    "Pillow": "12.3.0",
    "playwright": "1.60.0",
}

DEPLOY_ACTION = "actions/deploy-pages@v5"

DEV_SERVER = "scripts/serve-site.py"

FORBIDDEN_TRACKED = (
    "scripts/archive/",
    "skills/",
    "dist-pages/",
    "assets/audit/",
)

FORBIDDEN_TRACKED_SUFFIX = (".pyc",)

FORBIDDEN_FILES = ("replit.md",)

REQUIRED_FILES = ("AGENTS.md", "CLAUDE.md", ".node-version", "package.json")

# Always required.
GITIGNORE_ALWAYS = ("__pycache__/", "*.pyc")
# Required only when the directory actually exists in this repo.
GITIGNORE_IF_PRESENT = ("assets/audit/", "dist-pages/")

CLAUDE_MD_MAX_BYTES = 512  # a pointer, not a second authority file


# --- Finding plumbing --------------------------------------------------------

FAIL, WARN, EXEMPT, OK, FIXED = "FAIL", "WARN", "EXEMPT", "OK", "FIXED"


class Report:
    def __init__(self, exemptions):
        self.exemptions = set(exemptions)
        self.findings = []

    def add(self, level, code, message, fix=None):
        if level == FAIL and code in self.exemptions:
            level, fix = EXEMPT, None
        self.findings.append(
            {"level": level, "code": code, "message": message, "_fix": fix}
        )

    def ok(self, code, message):
        self.add(OK, code, message)

    def fail(self, code, message, fix=None):
        self.add(FAIL, code, message, fix)

    def warn(self, code, message):
        self.add(WARN, code, message)

    @property
    def failures(self):
        return [f for f in self.findings if f["level"] == FAIL]

    def public(self):
        return [{k: v for k, v in f.items() if not k.startswith("_")} for f in self.findings]


# --- Helpers -----------------------------------------------------------------


def read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_json(path: Path):
    raw = read_text(path)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def git(root: Path, *args, read_only=False):
    """Run git. Read commands pass --no-optional-locks so no index.lock appears."""
    cmd = ["git"]
    if read_only:
        cmd.append("--no-optional-locks")
    cmd.extend(args)
    return subprocess.run(
        cmd, cwd=str(root), capture_output=True, timeout=120, check=True
    )


def git_tracked_files(root: Path):
    try:
        out = git(root, "ls-files", "-z", read_only=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


# --- Checks ------------------------------------------------------------------


def check_node(root: Path, rep: Report):
    nv_path = root / ".node-version"
    nv = read_text(nv_path)

    def write_node_version():
        nv_path.write_text(NODE_VERSION + "\n", encoding="utf-8")
        return "wrote .node-version = %s" % NODE_VERSION

    if nv is None:
        rep.fail("NODE_VERSION_FILE", ".node-version is missing", write_node_version)
    elif nv.strip() != NODE_VERSION:
        rep.fail(
            "NODE_VERSION_FILE",
            ".node-version is %r, expected %r" % (nv.strip(), NODE_VERSION),
            write_node_version,
        )
    else:
        rep.ok("NODE_VERSION_FILE", ".node-version pins %s" % NODE_VERSION)

    pkg_path = root / "package.json"
    pkg = read_json(pkg_path)
    if pkg is None:
        rep.fail("NODE_ENGINES", "package.json missing or unparseable")
        return
    for name, expected in (("node", NODE_ENGINE), ("npm", NPM_ENGINE)):
        actual = (pkg.get("engines") or {}).get(name)
        if actual != expected:
            rep.fail("NODE_ENGINES", f"package.json engines.{name} is {actual!r}, expected {expected!r}")
        else:
            rep.ok("NODE_ENGINES", f"engines.{name} supports {actual}")


def check_runtime_alignment(root: Path, rep: Report):
    """Catch the pin drift that makes clean installs fail on another host."""
    nvm = read_text(root / ".nvmrc")
    lock = read_json(root / "package-lock.json") or {}
    locked = lock.get("packages", {}).get("", {}).get("engines", {})
    declarations = ((".nvmrc", nvm.strip() if nvm else None, NODE_VERSION),
                    ("package-lock.json engines.node", locked.get("node"), NODE_ENGINE),
                    ("package-lock.json engines.npm", locked.get("npm"), NPM_ENGINE))
    for source, actual, expected in declarations:
        if actual != expected:
            rep.fail("NODE_ALIGNMENT", f"{source} is {actual!r}, expected {expected!r}")
        else:
            rep.ok("NODE_ALIGNMENT", f"{source} declares {actual}")
    replit = read_text(root / ".replit") or ""
    selector = re.search(r'"nodejs-(\d+)"', replit)
    if not selector or selector[1] != NODE_VERSION.split(".")[0]:
        rep.fail("REPLIT_NODE", "Replit Node module must match the repository Node major")
    else:
        rep.ok("REPLIT_NODE", f"Replit selects Node {selector[1]}; verify its installed patch separately")


def check_npm_deps(root: Path, rep: Report):
    pkg = read_json(root / "package.json")
    if pkg is None:
        return
    declared = {}
    for field in ("dependencies", "devDependencies"):
        declared.update(pkg.get(field) or {})

    present = [n for n in NPM_FORBIDDEN if n in declared]
    for name in present:
        rep.fail(
            "NPM_FORBIDDEN",
            "%s is declared; ADR 0007 standardizes on Playwright alone. "
            "Remove it and its usages by hand, then `npm install`" % name,
        )
    if not present:
        rep.ok("NPM_FORBIDDEN", "no forbidden browser-automation packages")

    for name, want in NPM_REQUIRED.items():
        got = declared.get(name)
        if got is None:
            rep.fail("NPM_REQUIRED", "%s is not declared (expected %s)" % (name, want))
        elif got != want:
            rep.fail("NPM_REQUIRED", "%s is %r, expected %r" % (name, got, want))
        else:
            rep.ok("NPM_REQUIRED", "%s pinned at %s" % (name, want))


def check_pip_deps(root: Path, rep: Report):
    raw = read_text(root / "requirements-qa.txt")
    if raw is None:
        rep.fail("PIP_REQUIRED", "requirements-qa.txt is missing")
        return
    pins = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, _, version = line.partition("==")
            pins[name.strip().lower()] = version.strip()
    for name, want in PIP_REQUIRED.items():
        got = pins.get(name.lower())
        if got is None:
            rep.fail("PIP_REQUIRED", "%s is not pinned (expected %s)" % (name, want))
        elif got != want:
            rep.fail("PIP_REQUIRED", "%s==%s, expected %s" % (name, got, want))
        else:
            rep.ok("PIP_REQUIRED", "%s==%s" % (name, want))

    for name, want in PIP_IF_PRESENT.items():
        got = pins.get(name.lower())
        if got is None:
            continue  # not needed by this repo; the checker never adds it
        if got != want:
            rep.fail("PIP_IF_PRESENT", "%s==%s, expected %s" % (name, got, want))
        else:
            rep.ok("PIP_IF_PRESENT", "%s==%s" % (name, want))


def check_dev_server(root: Path, rep: Report):
    if (root / DEV_SERVER).is_file():
        rep.ok("DEV_SERVER", "%s present" % DEV_SERVER)
    else:
        rep.fail(
            "DEV_SERVER",
            "%s is missing; rename the existing dev-server script by hand" % DEV_SERVER,
        )


def check_deploy_action(root: Path, rep: Report):
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        rep.fail("DEPLOY_ACTION", ".github/workflows/ is missing")
        return
    pattern = re.compile(r"actions/deploy-pages@v(\d+)")
    found, stale = [], []
    for wf in sorted(wf_dir.glob("*.y*ml")):
        text = read_text(wf) or ""
        for match in pattern.finditer(text):
            ref = "actions/deploy-pages@v%s" % match.group(1)
            (found if ref == DEPLOY_ACTION else stale).append((wf, ref))

    for wf, ref in stale:

        def bump(wf=wf):
            raw = read_text(wf)
            new = pattern.sub(DEPLOY_ACTION, raw)
            wf.write_text(new, encoding="utf-8")
            return "%s: %s -> %s" % (wf.name, ref, DEPLOY_ACTION)

        rep.fail(
            "DEPLOY_ACTION",
            "%s uses %s, expected %s" % (wf.name, ref, DEPLOY_ACTION),
            bump,
        )
    if found and not stale:
        rep.ok("DEPLOY_ACTION", "%s in %s" % (DEPLOY_ACTION, found[0][0].name))
    elif not found and not stale:
        rep.warn("DEPLOY_ACTION", "no deploy-pages action found in any workflow")


def check_forbidden_files(root: Path, rep: Report):
    hits = [f for f in FORBIDDEN_FILES if (root / f).exists()]
    for f in hits:
        rep.fail(
            "FORBIDDEN_FILE",
            "%s exists; AGENTS.md is the sole authority file under ADR 0007. "
            "Diff and merge it into AGENTS.md, then delete by hand" % f,
        )
    if not hits:
        rep.ok("FORBIDDEN_FILE", "no superseded authority files")


def check_required_files(root: Path, rep: Report):
    missing = [f for f in REQUIRED_FILES if not (root / f).exists()]
    for f in missing:
        rep.fail("REQUIRED_FILE", "%s is missing" % f)
    if not missing:
        rep.ok("REQUIRED_FILE", "all required root files present")

    claude = root / "CLAUDE.md"
    if claude.is_file():
        size = claude.stat().st_size
        text = (read_text(claude) or "").upper()
        if size > CLAUDE_MD_MAX_BYTES:
            rep.fail(
                "CLAUDE_POINTER",
                "CLAUDE.md is %d bytes (max %d); it must point to AGENTS.md, "
                "not restate it" % (size, CLAUDE_MD_MAX_BYTES),
            )
        elif "AGENTS.MD" not in text:
            rep.fail("CLAUDE_POINTER", "CLAUDE.md does not reference AGENTS.md")
        else:
            rep.ok("CLAUDE_POINTER", "CLAUDE.md is a %d-byte pointer" % size)


def check_tracked_paths(root: Path, rep: Report):
    tracked = git_tracked_files(root)
    if tracked is None:
        rep.warn(
            "TRACKED_PATHS",
            "git unavailable; could not verify that forbidden paths are untracked",
        )
        return

    offenders = {}
    for path in tracked:
        norm = path.replace(os.sep, "/")
        for prefix in FORBIDDEN_TRACKED:
            if norm == prefix.rstrip("/") or norm.startswith(prefix):
                offenders.setdefault(prefix, []).append(norm)
        if "/__pycache__/" in norm or norm.startswith("__pycache__/"):
            offenders.setdefault("__pycache__/", []).append(norm)
        elif norm.endswith(FORBIDDEN_TRACKED_SUFFIX):
            offenders.setdefault("*.pyc", []).append(norm)

    for label, paths in sorted(offenders.items()):

        def untrack(paths=paths, label=label):
            # --cached leaves the working tree alone: reversible, and it never
            # unlinks a file, which matters on restricted bridges.
            for i in range(0, len(paths), 200):
                git(root, "rm", "-r", "--cached", "--quiet", "--", *paths[i : i + 200])
            return "untracked %d file(s) under %s (still on disk)" % (len(paths), label)

        rep.fail(
            "TRACKED_PATHS", "%d tracked file(s) under %s" % (len(paths), label), untrack
        )

    if not offenders:
        rep.ok("TRACKED_PATHS", "no forbidden paths tracked in git")


def check_gitignore(root: Path, rep: Report):
    path = root / ".gitignore"
    raw = read_text(path)
    if raw is None:
        raw = ""
    entries = {line.strip().lstrip("/") for line in raw.splitlines()}
    required = list(GITIGNORE_ALWAYS) + [
        p for p in GITIGNORE_IF_PRESENT if (root / p.rstrip("/")).is_dir()
    ]
    # *.py[cod] is the common equivalent of *.pyc; accept either.
    equivalents = {"*.pyc": ("*.py[cod]",)}

    def covered(pattern):
        if pattern in entries or pattern.rstrip("/") in entries:
            return True
        return any(alt in entries for alt in equivalents.get(pattern, ()))

    missing = [p for p in required if not covered(p)]
    if not missing:
        rep.ok("GITIGNORE", ".gitignore covers all generated output")
        return

    def append_entries():
        current = read_text(path) or ""
        if current and not current.endswith("\n"):
            current += "\n"
        block = "\n# ADR 0007: generated output is not tracked\n" + "\n".join(missing) + "\n"
        path.write_text(current + block, encoding="utf-8")
        return "appended to .gitignore: %s" % ", ".join(missing)

    for p in missing:
        rep.fail("GITIGNORE", ".gitignore does not cover %s" % p, append_entries)


CHECKS = (
    check_runtime_alignment,
    check_node,
    check_npm_deps,
    check_pip_deps,
    check_dev_server,
    check_deploy_action,
    check_required_files,
    check_forbidden_files,
    check_tracked_paths,
    check_gitignore,
)


def run_checks(root: Path, exemptions):
    rep = Report(exemptions)
    for check in CHECKS:
        try:
            check(root, rep)
        except Exception as exc:  # a broken check must not mask the others
            rep.warn("CHECKER_ERROR", "%s raised %s" % (check.__name__, exc))
    return rep


# --- Entry point -------------------------------------------------------------


def load_exemptions(root: Path):
    data = read_json(root / ".stack-conformance.json") or {}
    return [str(c) for c in (data.get("exempt") or [])], data.get("reason", "")


LEVEL_ORDER = {FAIL: 0, FIXED: 1, EXEMPT: 2, WARN: 3, OK: 4}


def print_findings(findings):
    for f in sorted(findings, key=lambda f: (LEVEL_ORDER[f["level"]], f["code"])):
        print("%-6s %-18s %s" % (f["level"], f["code"], f["message"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Assert the ADR 0007 canonical stack.")
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit JSON findings")
    parser.add_argument(
        "--warn-only", action="store_true", help="always exit 0; for phased adoption"
    )
    parser.add_argument(
        "--fix", action="store_true", help="repair mechanical items, then re-check"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --fix, list what would be repaired and change nothing",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print("not a directory: %s" % root, file=sys.stderr)
        return 2

    exemptions, reason = load_exemptions(root)
    rep = run_checks(root, exemptions)

    fix_log = []
    if args.fix:
        seen = set()
        for finding in rep.failures:
            fixer = finding["_fix"]
            if fixer is None:
                fix_log.append(("MANUAL", finding["code"], finding["message"]))
                continue
            key = (finding["code"], id(fixer))
            if key in seen:
                continue
            seen.add(key)
            if args.dry_run:
                fix_log.append(("WOULD-FIX", finding["code"], finding["message"]))
                continue
            try:
                fix_log.append(("FIXED", finding["code"], fixer()))
            except Exception as exc:
                fix_log.append(("FIX-FAILED", finding["code"], str(exc)))
        if not args.dry_run:
            rep = run_checks(root, exemptions)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "adr": "0007",
                    "exempt": exemptions,
                    "exempt_reason": reason,
                    "fixes": [
                        {"result": r, "code": c, "message": m} for r, c, m in fix_log
                    ],
                    "findings": rep.public(),
                    "pass": not rep.failures,
                },
                indent=2,
            )
        )
    else:
        if fix_log:
            for result, code, message in fix_log:
                print("%-10s %-18s %s" % (result, code, message))
            print()
        print_findings(rep.public())
        print()
        if rep.failures:
            print("ADR 0007: %d failure(s)" % len(rep.failures))
        else:
            print("ADR 0007: conformant")
        if exemptions:
            print(
                "exemptions: %s (%s)"
                % (", ".join(exemptions), reason or "no reason recorded")
            )
        if args.fix and not args.dry_run:
            print("note: --fix untracks files, it never deletes them from disk")

    if args.warn_only:
        return 0
    return 1 if rep.failures else 0


if __name__ == "__main__":
    sys.exit(main())

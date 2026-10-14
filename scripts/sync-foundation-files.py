#!/usr/bin/env python3
"""Safely synchronize and verify the three byte-identical cross-site foundation files.

This tool is deliberately an audit by default. It never chooses a winner from
commit dates, file mtimes, or the hub repository. To write, name both a source
checkout and the exact 40-character source commit:

    python3 scripts/sync-foundation-files.py
    python3 scripts/sync-foundation-files.py --verify --source-repo overkill-hill --source-revision <full-commit-sha> \
        --site-revision overkill-hill=<full-commit-sha> \
        --site-revision glee-fullytools=<full-commit-sha> \
        --site-revision askjamie=<full-commit-sha>
    python3 scripts/sync-foundation-files.py --apply --source-repo overkill-hill --source-revision <full-commit-sha>
    python3 scripts/sync-foundation-files.py --commit --source-repo overkill-hill --source-revision <full-commit-sha>

Verification reads every foundation asset from the named immutable revisions and
fails when any pinned site differs from the approved source fingerprint. Use
--repo-path name=path when CI checks out a site outside the default sibling
layout. Verification and the default audit never write sibling repositories.

Before any write it fails closed when any sibling checkout is dirty, staged,
untracked, or has a Git lock. Locks are reported only; this script never
renames or deletes them. Source bytes come from the named commit, not its
working tree. Post-write hooks run by default; generated paths are recorded.
A failed hook prevents all commits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

FOUNDATION_FILES = ["assets/css/theme.css", "assets/js/app.js", "assets/js/mermaid-init.js"]
FOUNDATION_CONTRACT = "byte-identical compatible superset (ADR-0001)"
REPO_DIRS = ["overkill-hill", "glee-fullytools", "askjamie"]
SITE_LABELS = {
    "overkill-hill": "OKH",
    "glee-fullytools": "Glee",
    "askjamie": "AskJamie",
}
POST_WRITE_HOOKS = {"glee-fullytools": {"assets/css/theme.css": [["python3", "scripts/sync-css-version.py"], ["python3", "scripts/sync-portfolio-stats.py"]]}}
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
RELEASE_RECORD_SCHEMA = "okhp3-shared-foundation-release-v1"
RELEASE_RECORD_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def run(repo: Path, command: list[str], timeout: int = 30):
    return subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=timeout)


def mirror_root() -> Path:
    return Path(__file__).resolve().parents[2]


def discover_repos(root: Path) -> dict[str, Path]:
    return {name: root / name for name in REPO_DIRS}


def parse_named_value(value: str, option: str) -> tuple[str, str]:
    name, separator, setting = value.partition("=")
    if not separator or name not in REPO_DIRS or not setting:
        raise ValueError(f"{option} must use name=value for one of: {', '.join(REPO_DIRS)}")
    return name, setting


def configured_repos(root: Path, overrides: list[str]) -> dict[str, Path]:
    repos = discover_repos(root)
    for value in overrides:
        name, path = parse_named_value(value, "--repo-path")
        candidate = Path(path)
        # Explicit relative paths are CLI paths and therefore resolve from the
        # current checkout, as in CI's ``--repo-path overkill-hill=.``. The
        # default sibling layout continues to resolve from ``mirror_root()``.
        repos[name] = candidate if candidate.is_absolute() else Path.cwd() / candidate
    return repos


def git_dir(repo: Path) -> Path | None:
    result = run(repo, ["git", "rev-parse", "--absolute-git-dir"])
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def git_metadata_dirs(repo: Path) -> list[tuple[str, Path]]:
    """Return the worktree and common Git dirs, without assuming .git is a directory."""
    worktree_dir = git_dir(repo)
    common = run(repo, ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"])
    if worktree_dir is None or common.returncode:
        return []
    common_dir = Path(common.stdout.strip())
    directories = [("worktree Git directory", worktree_dir.resolve())]
    if common_dir.resolve() != worktree_dir.resolve():
        directories.append(("common Git directory", common_dir.resolve()))
    return directories


def git_locks(repo: Path) -> list[tuple[str, Path]]:
    """Find every lock in resolved Git metadata, including linked-worktree common state."""
    locks: dict[Path, str] = {}
    for label, directory in git_metadata_dirs(repo):
        for lock in directory.rglob("*.lock"):
            locks.setdefault(lock.resolve(), label)
    return [(label, lock) for lock, label in sorted(locks.items(), key=lambda item: str(item[0]))]


def validate_repos(repos: dict[str, Path]) -> list[str]:
    return [f"{name}: not a usable git checkout at {repo}" for name, repo in repos.items() if not repo.is_dir() or git_dir(repo) is None]


def safety_problems(repos: dict[str, Path]) -> list[str]:
    """Inspect every mutable-state hazard without changing any checkout."""
    problems = []
    for name, repo in repos.items():
        metadata_dirs = git_metadata_dirs(repo)
        if not metadata_dirs:
            continue
        locks = [f"{label}: {lock}" for label, lock in git_locks(repo)]
        if locks:
            problems.append(f"{name}: Git lock present ({', '.join(locks)})")
        status = run(repo, ["git", "status", "--porcelain=v1", "--untracked-files=all"])
        if status.returncode:
            problems.append(f"{name}: cannot inspect git status: {status.stderr.strip()}")
        elif status.stdout.strip():
            problems.append(f"{name}: working tree is not clean ({status.stdout.strip().splitlines()[0]})")
    return problems


def read_worktree(repo: Path, relpath: str) -> bytes | None:
    path = repo / relpath
    return path.read_bytes() if path.is_file() else None


def git_revision(repo: Path) -> str:
    """Return the checkout revision, or an explicit unavailable marker."""
    result = run(repo, ["git", "rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def source_bytes(repo: Path, revision: str, relpath: str) -> tuple[bytes | None, str | None]:
    result = subprocess.run(["git", "show", f"{revision}:{relpath}"], cwd=repo, capture_output=True, timeout=30)
    return (result.stdout, None) if result.returncode == 0 else (None, result.stderr.decode(errors="replace").strip() or f"{relpath} absent from source revision")


def resolve_revision(repo: Path, revision: str) -> tuple[str | None, str | None]:
    if not SHA_RE.fullmatch(revision):
        return None, "--source-revision must be an explicit full 40-character commit SHA"
    result = run(repo, ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"])
    if result.returncode:
        return None, result.stderr.strip() or "source revision is not a commit in the selected source repository"
    resolved = result.stdout.strip()
    return (resolved, None) if resolved.lower() == revision.lower() else (None, "source revision did not resolve exactly")


def load_release_record(path: Path) -> dict:
    """Read the single fenced JSON approval record from the release audit."""
    text = path.read_text(encoding="utf-8")
    matches = RELEASE_RECORD_RE.findall(text)
    if len(matches) != 1:
        raise ValueError(f"{path}: expected exactly one fenced JSON release record")

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{path}: duplicate JSON key {key!r} in foundation release record")
            result[key] = value
        return result

    record = json.loads(matches[0], object_pairs_hook=unique_object)
    if not isinstance(record, dict) or record.get("schema") != RELEASE_RECORD_SCHEMA:
        raise ValueError(f"{path}: unsupported or missing release-record schema")
    source = record.get("source")
    pins = record.get("site_revisions")
    if not isinstance(source, dict) or source.get("repository") not in REPO_DIRS:
        raise ValueError(f"{path}: source.repository must name a configured site")
    if not isinstance(source.get("revision"), str) or not SHA_RE.fullmatch(source["revision"]):
        raise ValueError(f"{path}: source.revision must be a full 40-character commit SHA")
    if not isinstance(pins, dict) or set(pins) != set(REPO_DIRS):
        raise ValueError(f"{path}: site_revisions must pin exactly {', '.join(REPO_DIRS)}")
    for name, revision in pins.items():
        if not isinstance(revision, str) or not SHA_RE.fullmatch(revision):
            raise ValueError(f"{path}: site_revisions.{name} must be a full 40-character commit SHA")
    return record


def emit_release_record(record: dict, github_env: Path | None, github_output: Path | None) -> None:
    """Expose validated immutable pins to later Actions steps."""
    values = {
        "THEME_CONTROL_SOURCE_REPOSITORY": record["source"]["repository"],
        "THEME_CONTROL_SOURCE_REVISION": record["source"]["revision"],
        "THEME_CONTROL_OKH_REVISION": record["site_revisions"]["overkill-hill"],
        "THEME_CONTROL_GLEE_REVISION": record["site_revisions"]["glee-fullytools"],
        "THEME_CONTROL_ASKJAMIE_REVISION": record["site_revisions"]["askjamie"],
    }
    if github_env:
        with github_env.open("a", encoding="utf-8") as stream:
            for name, value in values.items():
                stream.write(f"{name}={value}\n")
    if github_output:
        with github_output.open("a", encoding="utf-8") as stream:
            for name, value in values.items():
                stream.write(f"{name.lower()}={value}\n")


def approved_source_drift(repo: Path, approved_revision: str, candidate_revision: str = "HEAD") -> list[str]:
    """List foundation files changed since the explicitly approved source."""
    drift = []
    for relpath in FOUNDATION_FILES:
        approved, approved_error = source_bytes(repo, approved_revision, relpath)
        candidate, candidate_error = source_bytes(repo, candidate_revision, relpath)
        if approved_error or candidate_error:
            drift.append(f"{relpath} (could not compare immutable revisions)")
        elif approved != candidate:
            drift.append(relpath)
    return drift


def status_paths(repo: Path) -> list[str]:
    result = run(repo, ["git", "status", "--porcelain=v1", "--untracked-files=all"])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return [line[3:] for line in result.stdout.splitlines() if len(line) >= 4]


def inspect(files: list[str], repos: dict[str, Path]) -> list[dict]:
    report = []
    for relpath in files:
        groups: dict[str, list[str]] = {}
        sites: dict[str, dict] = {}
        for name, repo in repos.items():
            content = read_worktree(repo, relpath)
            fingerprint = "missing" if content is None else hashlib.sha256(content).hexdigest()
            groups.setdefault(fingerprint, []).append(name)
            sites[name] = {
                "site": SITE_LABELS.get(name, name),
                "revision": git_revision(repo),
                "sha256": fingerprint,
                "bytes": len(content) if content is not None else None,
            }
        report.append({
            "file": relpath,
            "status": "in-sync" if len(groups) == 1 and "missing" not in groups else "diverged",
            "groups": groups,
            "sites": sites,
        })
    return report


def verify_revisions(
    files: list[str],
    repos: dict[str, Path],
    source_name: str,
    source_revision: str,
    site_revisions: dict[str, str],
) -> tuple[dict, list[str]]:
    """Compare pinned revision bytes without consulting any working tree files."""
    report = {
        "source": {
            "site": SITE_LABELS[source_name],
            "repository": source_name,
            "revision": source_revision,
        },
        "sites": {},
        "fingerprints": [],
        "mismatches": [],
    }
    problems: list[str] = []
    resolved_revisions: dict[str, str] = {}

    for name in REPO_DIRS:
        revision = site_revisions.get(name)
        if revision is None:
            error = "missing pinned commit revision"
            problems.append(f"{SITE_LABELS[name]}: {error}")
            report["sites"][name] = {
                "site": SITE_LABELS[name],
                "revision": None,
                "pinned_revision": None,
                "status": "unavailable",
                "error": error,
                "files": {},
            }
            continue
        resolved, error = resolve_revision(repos[name], revision)
        if error:
            problems.append(f"{SITE_LABELS[name]} revision {revision}: {error}")
            report["sites"][name] = {
                "site": SITE_LABELS[name],
                "revision": None,
                "pinned_revision": revision,
                "status": "unavailable",
                "error": error,
                "files": {},
            }
            continue
        resolved_revisions[name] = resolved
        report["sites"][name] = {
            "site": SITE_LABELS[name],
            "revision": resolved,
            "pinned_revision": revision,
            "files": {},
        }

    source_resolved, source_error = resolve_revision(repos[source_name], source_revision)
    if source_error:
        problems.append(f"approved source {SITE_LABELS[source_name]} revision {source_revision}: {source_error}")
        return report, problems
    report["source"]["revision"] = source_resolved

    for relpath in files:
        content, error = source_bytes(repos[source_name], source_resolved, relpath)
        if error:
            problems.append(
                f"approved source {SITE_LABELS[source_name]} revision {source_resolved}: "
                f"{relpath}: {error}"
            )
            continue
        expected_fingerprint = hashlib.sha256(content).hexdigest()
        fingerprint_report = {
            "asset": relpath,
            "expected": {
                "site": SITE_LABELS[source_name],
                "revision": source_resolved,
                "sha256": expected_fingerprint,
                "bytes": len(content),
            },
            "sites": {},
        }
        for name in REPO_DIRS:
            site_report = report["sites"].get(name)
            if site_report is None:
                continue
            if site_report.get("status") == "unavailable":
                fingerprint_report["sites"][name] = {
                    "site": SITE_LABELS[name],
                    "revision": None,
                    "pinned_revision": site_report["pinned_revision"],
                    "status": "unavailable",
                    "sha256": None,
                    "bytes": None,
                    "error": site_report["error"],
                }
                continue
            pinned_content, read_error = source_bytes(repos[name], resolved_revisions[name], relpath)
            if read_error:
                actual_fingerprint = "missing"
                problems.append(
                    f"{SITE_LABELS[name]} revision {resolved_revisions[name]} asset {relpath}: "
                    f"{read_error}"
                )
                bytes_count = None
            else:
                actual_fingerprint = hashlib.sha256(pinned_content).hexdigest()
                bytes_count = len(pinned_content)
            site_report["files"][relpath] = {
                "sha256": actual_fingerprint,
                "bytes": bytes_count,
            }
            fingerprint_report["sites"][name] = {
                "site": SITE_LABELS[name],
                "revision": resolved_revisions[name],
                "sha256": actual_fingerprint,
                "bytes": bytes_count,
            }
            if actual_fingerprint != expected_fingerprint:
                mismatch = {
                    "site": SITE_LABELS[name],
                    "revision": resolved_revisions[name],
                    "asset": relpath,
                    "expected_fingerprint": expected_fingerprint,
                    "actual_fingerprint": actual_fingerprint,
                }
                report["mismatches"].append(mismatch)
                problems.append(
                    f"{mismatch['site']} revision {mismatch['revision']} asset {mismatch['asset']} "
                    f"fingerprint {mismatch['actual_fingerprint']} diverges from "
                    f"{mismatch['expected_fingerprint']}"
                )
        report["fingerprints"].append(fingerprint_report)

    report["status"] = "passed" if not problems and not report["mismatches"] else "diverged"
    return report, problems


def apply(files: list[str], repos: dict[str, Path], source_name: str, revision: str, hooks: bool) -> tuple[dict, list[str]]:
    selected, errors = {}, []
    for relpath in files:
        content, error = source_bytes(repos[source_name], revision, relpath)
        if error:
            errors.append(f"{relpath}: {error}")
        else:
            selected[relpath] = content
    if errors:
        return {}, errors
    account = {name: {"foundation_writes": [], "generated_changes": [], "hook_results": []} for name in repos}
    for name, repo in repos.items():
        for relpath, content in selected.items():
            if read_worktree(repo, relpath) != content:
                (repo / relpath).write_bytes(content)
                account[name]["foundation_writes"].append(relpath)
        if hooks:
            for relpath in account[name]["foundation_writes"]:
                for command in POST_WRITE_HOOKS.get(name, {}).get(relpath, []):
                    result = run(repo, command, timeout=90)
                    account[name]["hook_results"].append({"command": command, "returncode": result.returncode, "stderr": result.stderr.strip()})
                    if result.returncode:
                        errors.append(f"{name}: hook {' '.join(command)} failed ({result.returncode})")
        changed = status_paths(repo)
        account[name]["all_changes"] = changed
        account[name]["generated_changes"] = sorted(set(changed) - set(account[name]["foundation_writes"]))
    return account, errors


def commit(repo: Path, paths: list[str], message: str) -> tuple[bool, str]:
    if not paths:
        return True, "no changes"
    locks = git_locks(repo)
    if locks:
        return False, "Git lock present; refusing to stage or commit"
    added = run(repo, ["git", "add", "--", *paths])
    if added.returncode:
        return False, added.stderr.strip() or "git add failed"
    if set(status_paths(repo)) != set(paths):
        return False, "refusing commit: accounted paths differ from status"
    result = run(repo, ["git", "commit", "-m", message])
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def emit(report: dict, report_file: Path | None = None) -> None:
    output = json.dumps(report, indent=2)
    if report_file:
        report_file.write_text(output + "\n", encoding="utf-8")
    print(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true", help="verify pinned immutable revisions without reading or writing working-tree files")
    parser.add_argument("--apply", action="store_true", help="write from an explicitly selected immutable source commit")
    parser.add_argument("--commit", action="store_true", help="write and commit every accounted change (implies --apply)")
    parser.add_argument("--source-repo", choices=REPO_DIRS, help="checkout containing the approved source commit")
    parser.add_argument("--source-revision", help="approved full 40-character source commit SHA")
    parser.add_argument("--site-revision", action="append", default=[], help="pinned site revision as name=full-commit-sha; repeat for all three sites")
    parser.add_argument("--repo-path", action="append", default=[], help="checkout path as name=path; repeat to override sibling layout")
    parser.add_argument("--release-record", type=Path, help="use the owner-reviewed JSON record embedded in a foundation release audit")
    parser.add_argument("--load-release-record", type=Path, help="validate a release record and emit its immutable pins for CI")
    parser.add_argument("--github-env-file", type=Path, help="append validated release pins to a GitHub Actions environment file")
    parser.add_argument("--github-output-file", type=Path, help="append validated release pins to a GitHub Actions output file")
    parser.add_argument("--report-file", type=Path, help="write the verification JSON report to this file as well as stdout")
    parser.add_argument("--no-hooks", action="store_true", help="explicitly skip configured post-write generators")
    parser.add_argument("--file", action="append", dest="requested_files", help="foundation basename or path; repeatable")
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = parser.parse_args()
    if args.report_file and not args.verify:
        parser.error("--report-file requires --verify")
    if args.load_release_record:
        try:
            record = load_release_record(args.load_release_record)
            emit_release_record(record, args.github_env_file, args.github_output_file)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(json.dumps({"error": "invalid foundation release record", "detail": str(error)}, indent=2))
            return 4
        print(json.dumps({"status": "loaded", "source": record["source"], "site_revisions": record["site_revisions"]}, indent=2))
        return 0
    writing = args.apply or args.commit
    if args.verify and writing:
        parser.error("--verify cannot be combined with --apply or --commit")
    root = mirror_root()
    try:
        repos = configured_repos(root, args.repo_path)
        if args.release_record:
            record = load_release_record(args.release_record)
            if args.source_repo or args.source_revision or args.site_revision:
                parser.error("--release-record cannot be combined with explicit source or site revisions")
            source_name = record["source"]["repository"]
            source_revision = record["source"]["revision"]
            site_revisions = record["site_revisions"]
        else:
            source_name = args.source_repo
            source_revision = args.source_revision
            site_revisions = dict(parse_named_value(value, "--site-revision") for value in args.site_revision)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    problems = validate_repos(repos)
    if problems:
        emit({"error": "invalid repository configuration", "problems": problems}, args.report_file)
        return 3
    files = FOUNDATION_FILES
    if args.requested_files:
        wanted = set(args.requested_files)
        files = [path for path in FOUNDATION_FILES if path in wanted or Path(path).name in wanted]
        if not files:
            parser.error("--file did not match a foundation file")
    mode = "verify" if args.verify else "commit" if args.commit else "apply" if args.apply else "dry-run"
    report = {"mirror_root": str(root), "mode": mode, "foundation_contract": FOUNDATION_CONTRACT}
    if args.verify:
        if not source_name or not source_revision:
            report["error"] = "--verify requires --source-repo and --source-revision"
            emit(report, args.report_file)
            return 4
        verification, verification_problems = verify_revisions(
            files, repos, source_name, source_revision, site_revisions
        )
        if args.release_record and source_name == "overkill-hill":
            drift = approved_source_drift(repos[source_name], source_revision)
            verification["current_source_review"] = {
                "candidate_revision": git_revision(repos[source_name]),
                "approved_revision": source_revision,
                "changed_assets": drift,
                "status": "stale-approval" if drift else "current",
            }
            if drift:
                verification_problems.append(
                    "current shared foundation differs from the approved release record "
                    f"at {source_revision}: {', '.join(drift)}; a new owner-reviewed approval is required"
                )
        report["verification"] = verification
        if verification_problems:
            report.update({"error": "pinned foundation verification failed", "problems": verification_problems})
            emit(report, args.report_file)
            return 1
        emit(report, args.report_file)
        return 0
    report["inspection"] = inspect(files, repos)
    if not writing:
        report["next_step"] = "Audit only. Supply --apply/--commit with --source-repo and an approved full --source-revision SHA to write."
        emit(report, args.report_file)
        return 0
    if not args.source_repo or not args.source_revision:
        report["error"] = "writes require --source-repo and --source-revision"
        emit(report, args.report_file)
        return 4
    revision, error = resolve_revision(repos[args.source_repo], args.source_revision)
    if error:
        report["error"] = error
        emit(report, args.report_file)
        return 4
    hazards = safety_problems(repos)
    if hazards:
        report.update({"error": "refusing to write because sibling repositories are not safe", "safety_problems": hazards})
        emit(report, args.report_file)
        return 2
    account, errors = apply(files, repos, args.source_repo, revision, not args.no_hooks)
    report.update({"source": {"repo": args.source_repo, "revision": revision}, "change_account": account})
    if errors:
        report.update({"error": "post-write validation/generation failed; no commits were attempted", "problems": errors})
        emit(report)
        return 5
    if args.commit:
        commits = {}
        for name, repo in repos.items():
            ok, detail = commit(repo, account[name]["all_changes"], f"Sync foundation files from {args.source_repo}@{revision[:12]}")
            commits[name] = {"ok": ok, "detail": detail}
        report["commits"] = commits
        if not all(item["ok"] for item in commits.values()):
            report["error"] = "one or more commits failed; see change_account for recoverable written paths"
            emit(report, args.report_file)
            return 5
    emit(report, args.report_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())

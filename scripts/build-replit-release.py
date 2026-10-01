#!/usr/bin/env python3
"""Stage a verified Replit package; preserve prior/failed bytes privately."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".local" / "site-release"
BUILDER = ROOT / "scripts" / "build-release.py"


def refuse_link(path: Path) -> None:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise RuntimeError(f"refusing linked release path: {path}")


def accepted_commit() -> str:
    value = os.environ.get("REPLIT_RELEASE_SHA", "")
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value.lower()):
        raise RuntimeError("REPLIT_RELEASE_SHA must be the accepted full 40-character SHA")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if actual != value.lower():
        raise RuntimeError(f"REPLIT_RELEASE_SHA does not match HEAD: expected {value.lower()}, actual {actual}")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True).strip()
    if dirty:
        raise RuntimeError("checkout must be clean before static publication: " + dirty)
    return value.lower()


def main() -> int:
    root = ROOT.resolve(strict=True)
    private = ROOT / ".local"
    refuse_link(private)
    private.mkdir(exist_ok=True)
    if private.resolve().parent != root:
        raise RuntimeError("private staging must stay within the workspace")
    if OUTPUT.parent.resolve() != private.resolve() or OUTPUT.name != "site-release":
        raise RuntimeError("release output must be the workspace .local/site-release directory")
    refuse_link(OUTPUT)
    if OUTPUT.exists() and not OUTPUT.is_dir():
        raise RuntimeError("release output is not a directory")
    staging = Path(tempfile.mkdtemp(prefix="replit-release-", dir=private))
    staged_output = staging / "site-release"
    # Invalidate stale publishable output before any fallible validation/build.
    # A unique private location preserves it without overwriting unknown work.
    if OUTPUT.exists():
        OUTPUT.rename(staging / "previous")
    commit = accepted_commit()
    subprocess.run(
        [sys.executable, str(BUILDER), "--output", str(staged_output), "--commit", commit],
        cwd=ROOT, check=True,
    )
    subprocess.run(
        [sys.executable, str(BUILDER), "--verify", "--source", str(ROOT),
         "--output", str(staged_output), "--commit", commit],
        cwd=ROOT, check=True,
    )
    # Detect tracked changes made during the build before promotion.
    if accepted_commit() != commit:
        raise RuntimeError("accepted source changed during the build")
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise RuntimeError("release output appeared concurrently; refusing replacement")
    staged_output.rename(OUTPUT)
    print(f"Verified Replit package ready for {commit}; private recovery: {staging}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

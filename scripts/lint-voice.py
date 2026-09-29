#!/usr/bin/env python3
"""
scripts/lint-voice.py — Voice lint for overkillhill.com static site.

Flags AI-sounding / corporate-buzzword phrases and passive-heavy sentences
in HTML body copy.  All findings are WARNs — this check never fails the
build on its own.

Phrase patterns are sourced from the "User preferences" section of replit.md:
  - Conventional American English; avoid trendy/AI-sounding phrasing.
  - "custom GPT" must not appear as headline/lead technology.
  - Words like "utilize", "leverage", "delve" are AI-register red flags.

Skipped contexts (same logic as check_em_dashes in validate-site.py):
  - HTML comments
  - <script> blocks
  - <style> blocks
  - <pre> / <code> blocks  (code examples are not prose)

Run standalone:
    python3 scripts/lint-voice.py
    python3 scripts/lint-voice.py --baseline scripts/voice-lint-baseline.json

Or called by validate-site.py. The baseline mode exits non-zero only when a
change introduces a warning not represented in the reviewed baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from public_page_boundary import iter_public_html_files

# These maintained locale routes use pair-specific editorial profiles rather
# than the en-US voice baseline. All other eligibility comes from the shared
# published-page boundary.
VOICE_EXCLUDED_LOCALES = frozenset({"en-gb", "es-mx"})


@dataclass(frozen=True)
class VoiceFinding:
    """One advisory voice finding with a stable, content-based identity."""

    path: str
    lineno: int
    label: str
    suggestion: str
    excerpt: str

    @property
    def identity(self) -> str:
        """Hash path, rule, and normalized visible text; line numbers may move."""
        source = "\x1f".join((self.path, self.label, self.excerpt.casefold()))
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @property
    def message(self) -> str:
        if self.label == "passive-heavy":
            return (
                f"{self.path}:{self.lineno}: passive-heavy line ({self.suggestion}) "
                f"· …{self.excerpt}…"
            )
        return (
            f"{self.path}:{self.lineno}: voice [{self.label}] - {self.suggestion} "
            f"· …{self.excerpt}…"
        )

# ---------------------------------------------------------------------------
# Configurable phrase patterns
# Each entry: (label, compiled_regex, suggestion)
# Word-boundary anchors prevent partial matches (e.g. "utilization" catches
# "utiliz" but we want to flag it too, so some are prefix patterns).
# ---------------------------------------------------------------------------

# fmt: off
PHRASE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # --- AI-register verbs ---
    ("utilize",
     re.compile(r"\butiliz\w*\b", re.IGNORECASE),
     "use 'use' instead"),
    ("leverage (verb)",
     re.compile(r"\bleverag(e|es|ed|ing)\b", re.IGNORECASE),
     "be specific: 'use', 'apply', 'draw on'"),
    ("delve",
     re.compile(r"\bdelv(e|es|ed|ing)\b", re.IGNORECASE),
     "use 'explore', 'examine', 'look at'"),
    ("unlock (figurative)",
     re.compile(r"\bunlock(s|ed|ing)?\b", re.IGNORECASE),
     "say what specifically becomes possible"),
    # --- Hedging / throat-clearing ---
    ("it's worth noting",
     re.compile(r"\bit'?s worth noting\b", re.IGNORECASE),
     "say the thing directly, drop the preamble"),
    ("it is worth noting",
     re.compile(r"\bit is worth noting\b", re.IGNORECASE),
     "say the thing directly, drop the preamble"),
    ("it's important to note",
     re.compile(r"\bit'?s important to note\b", re.IGNORECASE),
     "say the thing directly"),
    ("it is important to note",
     re.compile(r"\bit is important to note\b", re.IGNORECASE),
     "say the thing directly"),
    ("note that",
     re.compile(r"\bnote that\b", re.IGNORECASE),
     "say the thing directly"),
    ("in order to",
     re.compile(r"\bin order to\b", re.IGNORECASE),
     "use plain 'to'"),
    # --- AI-positioning / headline tech ---
    ("custom GPT (lead copy)",
     re.compile(r"\bcustom\s+GPT\b", re.IGNORECASE),
     "lead copy must foreground protocol-first AI systems; 'custom GPT' only for factual past work"),
    # --- Corporate buzzwords ---
    ("going forward",
     re.compile(r"\bgoing forward\b", re.IGNORECASE),
     "use 'from now on', 'next', or be specific about the time frame"),
    ("touch base",
     re.compile(r"\btouch base\b", re.IGNORECASE),
     "use 'check in', 'follow up', 'talk'"),
    ("deep dive",
     re.compile(r"\bdeep[- ]dive?\b", re.IGNORECASE),
     "use 'close look', 'detailed examination', or just describe what you're doing"),
    ("synergy",
     re.compile(r"\bsynerg(y|ies|ize[sd]?|izing)\b", re.IGNORECASE),
     "describe the actual benefit"),
    ("robust",
     re.compile(r"\brobust\b", re.IGNORECASE),
     "say what specific quality you mean: reliable, thorough, detailed, etc."),
    ("seamless",
     re.compile(r"\bseamless(ly)?\b", re.IGNORECASE),
     "describe the actual experience"),
    ("cutting-edge",
     re.compile(r"\bcutting[- ]edge\b", re.IGNORECASE),
     "name the specific capability"),
    ("state-of-the-art",
     re.compile(r"\bstate[- ]of[- ]the[- ]art\b", re.IGNORECASE),
     "name the specific capability"),
    ("game changer",
     re.compile(r"\bgame[- ]changer?\b", re.IGNORECASE),
     "describe the actual impact"),
    ("pain point",
     re.compile(r"\bpain[- ]point\b", re.IGNORECASE),
     "name the actual problem"),
    ("revolutionize",
     re.compile(r"\brevolution(ize[sd]?|izing|ary)\b", re.IGNORECASE),
     "describe what actually changes"),
    ("transformative",
     re.compile(r"\btransformative\b", re.IGNORECASE),
     "describe what actually changes"),
]
# fmt: on

# ---------------------------------------------------------------------------
# Passive voice heuristic
# Pattern: be-verb + optional adverb(s) + past participle ending in -ed
# This catches the most common English passive constructions.
# Flags a line only when 2+ passive constructions appear (passive-heavy).
# ---------------------------------------------------------------------------

_BE_VERBS = r"(?:is|are|was|were|be|been|being)"
_OPT_ADV = r"(?:\s+\w+ly)?"  # optional single adverb (e.g. "was quickly built")
PASSIVE_RE = re.compile(
    rf"\b{_BE_VERBS}{_OPT_ADV}\s+([a-z]+ed)\b",
    re.IGNORECASE,
)

PASSIVE_PER_LINE_THRESHOLD = 2  # flag a line with this many passive hits


def find_html_files(root: Path | None = None) -> list[Path]:
    scan_root = Path(root) if root is not None else ROOT
    return sorted(
        path
        for path in iter_public_html_files(scan_root)
        if not (set(path.relative_to(scan_root).parts) & VOICE_EXCLUDED_LOCALES)
    )


def strip_tags(text: str) -> str:
    """Remove all HTML tags from a line, leaving only visible text."""
    return re.sub(r"<[^>]+>", " ", text)


def lint_file(path: Path) -> list[VoiceFinding]:
    """
    Return advisory voice findings for the file.
    """
    rel = path.relative_to(ROOT).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    findings: list[VoiceFinding] = []

    in_comment = False
    in_script = False
    in_pre = False
    in_style = False
    in_mermaid = False

    for lineno, line in enumerate(lines, 1):
        # ── update block-open state BEFORE evaluating ──────────────────────
        if not in_comment and "<!--" in line:
            in_comment = True
        if not in_script and re.search(r"<script[\s>]", line, re.IGNORECASE):
            in_script = True
        if not in_pre and re.search(r"<(?:pre|code)[\s>]", line, re.IGNORECASE):
            in_pre = True
        if not in_style and re.search(r"<style[\s>]", line, re.IGNORECASE):
            in_style = True
        if not in_mermaid and re.search(r'class="[^"]*\bmermaid\b', line, re.IGNORECASE):
            in_mermaid = True

        skip = in_comment or in_script or in_pre or in_style or in_mermaid

        if not skip:
            text = strip_tags(line)
            if not text.strip():
                pass  # nothing to check

            else:
                # ── phrase checks ─────────────────────────────────────────
                for label, pattern, suggestion in PHRASE_PATTERNS:
                    if pattern.search(text):
                        findings.append(VoiceFinding(
                            path=rel,
                            lineno=lineno,
                            label=label,
                            suggestion=suggestion,
                            excerpt=text.strip()[:90],
                        ))

                # ── passive-heavy check ───────────────────────────────────
                passive_hits = PASSIVE_RE.findall(text)
                if len(passive_hits) >= PASSIVE_PER_LINE_THRESHOLD:
                    findings.append(VoiceFinding(
                        path=rel,
                        lineno=lineno,
                        label="passive-heavy",
                        suggestion=f"{len(passive_hits)} passive constructions",
                        excerpt=text.strip()[:90],
                    ))

        # ── update block-close state AFTER evaluating ──────────────────────
        if in_comment and "-->" in line:
            in_comment = False
        if in_script and re.search(r"</script>", line, re.IGNORECASE):
            in_script = False
        if in_pre and re.search(r"</(?:pre|code)>", line, re.IGNORECASE):
            in_pre = False
        if in_style and re.search(r"</style>", line, re.IGNORECASE):
            in_style = False
        if in_mermaid and re.search(r"</(?:div|pre)>", line, re.IGNORECASE):
            in_mermaid = False

    return findings


def load_baseline(path: Path) -> Counter[str]:
    """Load a reviewed warning baseline, rejecting malformed policy files."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read baseline {path}: {error}") from error

    if data.get("schema_version") != 1 or not isinstance(data.get("finding_counts"), dict):
        raise ValueError(f"baseline {path} must contain schema_version 1 and finding_counts")

    counts = Counter()
    for identity, count in data["finding_counts"].items():
        if not isinstance(identity, str) or not isinstance(count, int) or count < 1:
            raise ValueError(f"baseline {path} has an invalid finding count")
        counts[identity] = count
    return counts


def write_baseline(path: Path, findings: list[VoiceFinding]) -> None:
    """Write a deterministic baseline after a human has reviewed lint output."""
    counts = Counter(finding.identity for finding in findings)
    data = {
        "schema_version": 1,
        "generated_by": "python3 scripts/lint-voice.py --write-baseline",
        "finding_counts": dict(sorted(counts.items())),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def find_new_warnings(findings: list[VoiceFinding], baseline: Counter[str]) -> list[VoiceFinding]:
    """Return findings whose content-based occurrence exceeds the baseline."""
    seen: Counter[str] = Counter()
    new_findings: list[VoiceFinding] = []
    for finding in findings:
        seen[finding.identity] += 1
        if seen[finding.identity] > baseline[finding.identity]:
            new_findings.append(finding)
    return new_findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint static-site voice and guard against new warnings.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="reviewed baseline JSON; fail only for warnings beyond it",
    )
    parser.add_argument(
        "--write-baseline",
        type=Path,
        metavar="PATH",
        help="write the current findings as a reviewed-baseline candidate",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.baseline and args.write_baseline:
        print("ERROR: choose --baseline or --write-baseline, not both.", file=sys.stderr)
        return 2

    pages = find_html_files()
    all_findings: list[VoiceFinding] = []
    for path in pages:
        all_findings.extend(lint_file(path))

    warnings = all_findings

    if warnings:
        print(f"Voice lint — {len(warnings)} warning(s):")
        for finding in warnings:
            print(f"  ! {finding.message}")
    else:
        print("Voice lint — ✓ no voice warnings.")

    if args.write_baseline:
        write_baseline(args.write_baseline, warnings)
        print(f"Wrote reviewed-baseline candidate: {args.write_baseline}")
        return 0

    if args.baseline:
        try:
            baseline = load_baseline(args.baseline)
        except ValueError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        new_warnings = find_new_warnings(warnings, baseline)
        if new_warnings:
            print(f"ERROR: {len(new_warnings)} new voice warning(s) beyond reviewed baseline:")
            for finding in new_warnings:
                print(f"  ✖ {finding.message}")
            return 1
        print("✓ no new voice warnings beyond reviewed baseline.")

    # Without a baseline, voice lint remains advisory for editorial review.
    return 0


if __name__ == "__main__":
    sys.exit(main())

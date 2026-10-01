#!/bin/bash
set -u

# OverKill Hill P³™ - post-merge setup
# Static HTML site - no build step required.
# Validates that the Python server module is importable and key files exist.

echo "Post-merge: verifying static site integrity..."

# Confirm server entry point exists
if [ ! -f "server.py" ]; then
  echo "ERROR: server.py not found" >&2
  exit 1
fi

# Confirm core HTML files are present
for f in index.html writings/first-diagram-is-a-liar/index.html assets/css/theme.css assets/js/app.js; do
  if [ ! -f "$f" ]; then
    echo "ERROR: required file missing: $f" >&2
    exit 1
  fi
done

run_step() {
  error_message="$2"
  shift 2
  if ! "$@"; then
    echo "ERROR: ${error_message}" >&2
    exit 1
  fi
}

echo "Post-merge: running MTB version consistency check..."
run_step "MTB version check" "MTB version check failed. Stale version strings or roadmap drift detected." python3 scripts/check-mtb-version.py

echo "Post-merge: running full site validator..."
echo "Post-merge: rebuilding generated HTML..."
run_step "site rebuild" "site rebuild failed." python3 scripts/build-site.py
echo "Post-merge: regenerating CSP policies and page metadata..."
run_step "CSP regeneration" "CSP regeneration failed." python3 scripts/generate-csp.py
echo "Post-merge: rebuilding HTML with canonical CSP policies..."
run_step "site rebuild after CSP regeneration" "site rebuild after CSP regeneration failed." python3 scripts/build-site.py
echo "Post-merge: checking featured article release and banner parity..."
run_step "featured article release parity" \
  "featured article source and generated output or site banners disagree." \
  python3 scripts/check-banner.py
echo "Post-merge: synchronizing shared asset fingerprints..."
run_step "cache-busting synchronization" "shared asset fingerprints are stale." python3 scripts/cache-bust.py
run_step "generated HTML check" "generated HTML is out of sync with site sources." python3 scripts/build-site.py --check
run_step "cache-bust check" "shared asset fingerprints are out of sync." python3 scripts/cache-bust.py --check
run_step "CSP policy check" "CSP policies are out of sync with published pages." python3 scripts/check-csp.py

run_step "full site validator" "full site validation failed." python3 scripts/validate-site.py

echo "Post-merge: running internal link check..."
run_step "internal link check" "internal link check failed." python3 scripts/check-links.py

audit_report="$(mktemp "${TMPDIR:-/tmp}/overkillhill-audit.XXXXXX.md")" || {
  echo "ERROR: could not create temporary audit report." >&2
  exit 1
}
trap 'rm -f "$audit_report"' EXIT
echo "Post-merge: running canonical site audit..."
run_step "canonical site audit" "canonical site audit failed." \
  python3 scripts/audit-site.py --quiet --report "$audit_report"

echo "Post-merge: all checks passed."

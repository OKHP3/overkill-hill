# Atom-feed generator pilot

The generator reads canonical English Article authoring records from
`site-src/pages.json` and their source JSON-LD. It excludes noindex, draft,
and localized records, uses canonical URLs as entry IDs, and rejects missing
or malformed publication and modification dates. Output is deterministic.

Run `python scripts/generate-atom-feed.py --output .local/atom-feed.xml`.
Run `python tests/test-atom-feed-generator.py` for its regression suite.
The normal site validation workflow runs this suite too. Use
`python3 scripts/build-site.py` to regenerate the public root `feed.xml`; use
`python3 scripts/build-site.py --check` to compare expected feed bytes without
rewriting the file.

Date-only authoring values are encoded at UTC midnight because Atom requires
a timestamp. This encoding preserves the calendar date; it does not claim
an authored time. Timezone-qualified timestamps retain their source form.

English pages advertise the feed from the shared head. Localized pages do not.
The feed remains outside the sitemap and HTML page inventory. The protected
GitHub Pages release allowlists `feed.xml`, records its SHA-256 in the release
manifest, and verifies its live bytes and response media type. The live-edge
check accepts `application/atom+xml` and the explicit generic XML types
`application/xml` and `text/xml`; missing or non-XML content types fail.
Replit remains development and preview only.

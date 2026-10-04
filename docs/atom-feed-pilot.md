# Atom-feed generator pilot

The generator reads canonical English Article authoring records from
`site-src/pages.json` and their source JSON-LD. It excludes noindex, draft,
and localized records, uses canonical URLs as entry IDs, and rejects missing
or malformed publication and modification dates. Output is deterministic.

Run `python scripts/generate-atom-feed.py --output .local/atom-feed.xml`.
Run `python tests/test-atom-feed-generator.py` for its regression suite.
The normal site validation workflow runs this suite too.

Date-only authoring values are encoded at UTC midnight because Atom requires
a timestamp. This encoding preserves the calendar date; it does not claim
an authored time. Timezone-qualified timestamps retain their source form.

This pilot does not publish a feed or change page discovery, the sitemap,
release allowlists, or generated HTML. Public subscription support requires
a separate reviewed integration into the protected GitHub Pages release,
including a stable feed URL, discovery links, freshness checks, and release
artifact verification. Replit remains development and preview only.

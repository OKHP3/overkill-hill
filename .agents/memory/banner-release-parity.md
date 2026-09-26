---
name: Banner release parity
description: Cross-artifact release validation required before repairing site-wide featured-article banners.
---

The banner checker must reject a source/generated featured-article release disagreement before scanning or writing any banner file.

Generated-site builds must also compare the authoritative source label with the newly rendered featured page before writing generated HTML or the sitemap. A failed parity gate must leave both article files available as evidence.

**Why:** Repairing against each artifact's local release can make source and generated pages advertise different featured releases while reporting both representations as individually valid. A build that overwrites a split before comparing it can also hide the evidence needed to diagnose the mismatch.

**How to apply:** Use the shared article-release parser to validate exactly one release label in both source and generated content, compare normalized releases, and report both paths and the featured route. Run this before banner repair or generated-output writes, then keep it in every release path that generates or packages the public site.
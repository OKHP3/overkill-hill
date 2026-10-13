---
name: Robots metadata policy
description: The indexing relationship between page-wide and crawler-specific robots metadata
---

Page-wide robots metadata defines the page's indexing contract. Crawler-specific metadata (for example, `googlebot` or `bingbot`) must not declare the opposite `index`/`noindex` state. Crawler-specific directives that do not set indexing, such as snippet or preview limits, may differ.

**Why:** Crawler-specific indexing directives can override page-wide metadata for an individual crawler, silently breaking a page's declared indexing boundary.

**How to apply:** When validating rendered SEO metadata, compare indexing tokens across page-wide and crawler-specific tags; keep other crawler-specific controls valid and independent.

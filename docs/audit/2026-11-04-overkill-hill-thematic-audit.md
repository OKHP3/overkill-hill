# OverKill Hill P³™: thematic audit and brand operating guidelines

**Review date:** 2026-11-04 (America/Chicago)  
**Thread key:** `okh-website-thematic-audit-2025-origin` (ChatGPT's exact thread ID was not exposed)  
**Repository:** [OKHP3/overkill-hill](https://github.com/OKHP3/overkill-hill), `main` baseline `f0cc88d77bdf3102308f9b203edc7499e904f650`  
**Site:** <https://overkillhill.com/>  
**Status:** Source-backed thematic review and proposed guidance, **not a design approval, release, accessibility certification, or authorization to edit sibling brands**.

## Executive judgment

**Keep the brand's tension. Control its placement.** OverKill Hill P³ has a defensible differentiated identity: an industrial, sometimes eccentric forge for protocol-first AI systems, where craft means pressure-testing ideas and publishing the evidence. The 2026 site now provides tool-entry, proof-entry, and collaboration journeys rather than merely describing custom GPTs. The brand's two voices—precise systems engineer and provocative maker/storyteller—are both authentic; their transitions need clearer context so newcomers can understand why the same site includes Agent Skills, diagrams, the MurderBird, a family-origin manifesto, and project inquiries.

**Positioning proposition (PROPOSED):** *OverKill Hill P³ turns ambitious AI ideas into inspectable systems, with the methods, evidence, and creative persistence needed to make the work hold up in reality.*

This is an editorial recommendation, not replacement approved copy.

## Coverage and evidence limits

The canonical [sitemap](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/sitemap.xml) contains **35 indexed URLs**, of which **31 are base-language routes and 4 are localized entries** at the inspected revision. Sitemap inclusion establishes a published route inventory, not that every route was separately rendered or its behavior verified. The audit assessed the current live home, projects, manifesto, universe, about, contact, and legal page family; sampled project descriptions (Skillz Forge, Found-Rᵧ, Mermaid Theme Builder, BPMN for Mermaid, Diagram Truth and related portfolio entries); and inspected [AGENTS.md](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/AGENTS.md), [README.md](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/README.md), [index.html](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/index.html), [theme.css](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/assets/css/theme.css), [the active brand profile](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/brand-styles/profiles/overkill-hill.yaml), current [contact HTML](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/contact/index.html), [legal HTML](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/legal/index.html), the [publishing runbook](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/docs/publishing.md), and the source page inventory.

**Confirmed** means directly observed in live content or repository files as of this review; **inferred** means an editorial interpretation; **proposed** means a future decision. Thematic judgments do not substitute for visual screenshot comparison, mobile navigation tests, measured conversion, WCAG conformance, product operation, or locale-translation QA. Individual public URLs may be cached, so canonical `main` source is the primary evidence for discrepancies.

## Identity to preserve

| Dimension | Established identity | Implication |
|---|---|---|
| Name | **OverKill Hill P³™** | The public wordmark, not an excuse to normalize technical ASCII aliases |
| Tagline | **Precision · Protocol · Promptcraft** | Three pillars; stable in header/title |
| Method | **Protocol-Driven Power Prompts** | Separate canonical expansion of P³ |
| Metaphor | Forge, blueprint, tempered material | Systems are built and tested, not magicked into existence |
| Personality | Exacting, curious, impish, candid | Warmth must not imply uncontrolled process |
| Proof | Source, maturity, limits, operational status | Claim only what the linked evidence establishes |
| Parent brand | Engineering spine across projects and siblings | Keep AskJamie and Glee-fully autonomous in their own domains |

The [living manifesto](https://overkillhill.com/manifesto/) explicitly distinguishes the tagline from the methodology. Its original statements and origin/visual canon are described as locked; changing them is **not** part of this audit. The [universe](https://overkillhill.com/universe/) describes three related sites rather than a single visual system that must look identical.

### Emotional progression (proposed)

1. **Curiosity:** unmistakable mechanical creature, unusual name and provocative principle.
2. **Orientation:** immediate explanation of what the Hill builds, for whom, and why it differs.
3. **Confidence:** visible project status, sources, limitations and representative work.
4. **Affinity:** optional manifesto, origin story, process experiments and humor.
5. **Agency:** a clear choice to use, inspect or discuss without sales pressure.

The mistake to avoid is using lore as an entrance exam. Show the doorway, then offer the rabbit hole.

## Visual language: actual current contract

The [canonical CSS tokens](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/assets/css/theme.css) declare `#1c3a34` teal, `#676a2c` olive, `#a06e28` ochre, `#5b3a27` rust, `#2a2320` espresso, `#c46a2c` orange, `#e6a03c` amber, and `#f6f2ee` paper. Dark surfaces include `#111827` and `#181f26`; the foreground is `#e5e7eb`. These are source-token values, **not independently measured visual contrast**.

- **Color rule:** Espresso/teal/dark surfaces form the structural field; orange/amber signal action, heat and precision. Olive/ochre/rust are atmosphere and taxonomy, not competing CTA systems. Use semantic contrast tokens for text, not raw pigment blindly.
- **Contrast-specific correction:** current CSS documents a lighter muted text token (`#9ca3af`) and a link-hover token (`#df8a4f`) because the prior raw gray and orange did not meet the stated normal-text targets on all dark surfaces. Existing source comments are historical measurements, not a fresh WCAG pass. Preserve the repo's actual contrast checks.
- **Typography:** `Alfa Slab One` for decisive display moments; `DM Sans` for prose/UI; `JetBrains Mono` for code, evidence and technical metadata. These fonts are now **self-hosted WOFF2** in `assets/fonts/`; the 2025 report's Google Fonts framing and the brand profile's remaining Google Fonts sentence are stale.
- **Form:** steel/blueprint geometry, deliberate grid, constrained width, visible status marks, and measured whitespace. Avoid generic neon cyberpunk, gradient-driven SaaS gloss, and competing novelty effects.
- **Image system:** The MurderBird is a *visual doctrine*, not interchangeable generic crow clip art. The current hero description presents an armored, grounded, orange-eyed creature beside a workshop/CRT scene. Preserve the distinction between mascot, sigil/mark, narrative illustration, favicon, and project thumbnail. Do not use a friendly raven substitute when visual menace is intentionally part of the canon.
- **Motion:** Reuse site tokens, respect reduced motion, keyboard focus and content-first rendering. No animations should be required to discover navigation, evidence or CTAs.

The [project-owned brand profile](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/brand-styles/profiles/overkill-hill.yaml) is the correct design-system companion. Updating its stale font provenance should follow the owner review process rather than creating another global CSS source.

## Voice control: three purposeful registers

| Surface | Default voice | Keep / avoid |
|---|---|---|
| Home, tools, portfolio | Evidence-first technical guide | Specific outcomes / unproven superlatives |
| Manifesto, writings | First-person maker and storyteller | Protected origin canon / generic corporate flattening |
| About, contact, inquiry | Human expert, direct and inviting | Warm candor / long pre-CTA detours |

**Editorial rules:** Use active, concrete verbs; distinguish *published page* from *working tool* and *verified result*; use a source and date for changing platform claims; acknowledge uncertainty without making the user feel at fault; give the reader one relevant next action. Humor earns its space when it illuminates a design choice, not when it delays a necessary answer. Do not add emoji as the sole carrier of meaning. Favor `I` when the founder directly speaks and `OverKill Hill` when explaining the branded practice; avoid switching between `I`, `we`, and third-person founder bio inside the same paragraph without an editorial purpose.

**Cross-brand rule:** Say that AskJamie is a voice/helpdesk experience and Glee-fully is an everyday tool ecosystem built in the wider family; link to those domains for their own promises. They may keep distinct palettes. Do not copy their color systems into OKH's global navigation or make their maturity claims on their behalf.

## Findings and corrective priorities

| Priority | Finding and evidence tier | Recommended action |
|---|---|---|
| P1 | **CONFIRMED:** [About](https://overkillhill.com/about/) alternates first-person consulting language with a third-person founder biography. | Choose an explicit narrator per section and smooth the transitions; retain factual evidence. |
| P1 | **CONFIRMED:** [Projects](https://overkillhill.com/projects/) features Skillz Forge in both “Selected work” and “Built at the Hill.” | Differentiate editorial feature from inventory row or consolidate repeated cards. |
| P1 | **INFERRED:** Nested desktop project navigation now exposes many specialist destinations, while newcomers may only know the top-level promise. | Test discovery and keyboard/mobile navigation before pruning; keep stable clean routes. |
| P1 | **CONFIRMED:** [Brand profile](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/brand-styles/profiles/overkill-hill.yaml) states JetBrains Mono uses Google Fonts, but [CSS](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/assets/css/theme.css) declares self-hosted fonts. | Correct profile provenance after owner review; do not reintroduce external font loads. |
| P2 | **CONFIRMED:** Project cards carry evidence dates, many from September 2026, alongside newer “Hot off the Forge” editorial updates. | Clarify “reviewed as of” versus “published recently”; recheck evidence before reasserting readiness. |
| P2 | **INFERRED:** Personal origin, MurderBird myth, family context, and practical service copy serve different visitor intentions. | Add contextual links/intro labels rather than rewriting the locked manifesto or stripping personality. |
| P2 | **PROPOSED:** The site would benefit from an explicit visual-role catalog and voice register in the existing brand profile. | Record sanctioned mascot/mark/image roles and copy examples, then test representative pages. |
| P2 | **CONFIRMED:** The current [home](https://overkillhill.com/) shows the upcoming Custom GPT retirement and capability transition. [OpenAI's FAQ](https://help.openai.com/en/articles/20001519-custom-gpt-retirement-and-migration-faq) confirms standard retirement planned for 2026-12-11, with eligible exceptions. | Link official change notice and periodically verify date and replacement readiness; avoid claiming all successors are already operational. |
| P2 | **PROPOSED:** Long public origin sections may contain personal biographical disclosures. | Conduct a consent/privacy review before promoting those details elsewhere; do not republish private evidence here. |

### Historical audit corrections, not open defects

The earlier `thematic_report.md` was a useful **2025-era draft**, but its browser-generated citation markers are not portable references. As of the inspected 2026 canonical source:

- The main contact CTA and [contact page](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/contact/index.html) point to `contact@overkillhill.com`; the old `sales@` inconsistency is **retired as a current finding**.
- The [legal page](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/legal/index.html) now includes site-specific privacy, terms, cookies/analytics, accessibility and usage material; it is **not solely an AskJamie disclaimer**.
- The homepage's old “Example: Protocol Library outline published” placeholder has been replaced by featured writing and evidence-qualified projects.
- The prior “one exact spelling everywhere” recommendation is too aggressive. **P³** in public brand copy, **OKHP³** as a display shorthand, and **OKHP3** for ASCII identifiers have legitimate different roles. Govern usage by context.
- The old claim that all orange-accent text is contrast-safe lacked a fresh contrast measurement and conflicts with the current hover-color remediation. Do not repeat it as verified.

## Proposed operating guidelines and acceptance gates

1. **Brand hierarchy:** The parent site must say what it does in one screen; subsidiary brands retain separate identities; any new cross-brand visual uses an existing sanctioned role.
2. **Copy governance:** Each page declares audience, narrator, desired feeling, evidence tier, and primary visitor action. Review high-traffic entry pages first.
3. **Proof discipline:** For project rows distinguish availability, maturity, observed operation, source date, and known limits. Keep claims tied to the specific item, not adjacent cards.
4. **Visual QA:** Test representative desktop/mobile widths, dark/light themes, font loads, link contrast, focus order, hover states and reduced motion against existing CI gates.
5. **Narrative integrity:** The manifesto's locked origin/canon remains immutable absent explicit owner direction. Improvements belong in the living portion or its navigation.
6. **Accessibility & performance:** Preserve semantic static pages, native links, visible focus, small JS, canonical clean folder routes, and Pages-only publishing. No framework migration is implied.
7. **Ownership:** Site changes go through `site-src/` and existing generators as required. Shared CSS/runtime changes require coordination with their owner and the sibling-site foundation workflow; proposals here grant no permission to change them.
8. **Release evidence:** Any future patch must pass `scripts/build-site.py --check`, `scripts/validate-site.py`, search/universe freshness checks and applicable browser QA; use review PRs and [Pages publication policy](https://github.com/OKHP3/overkill-hill/blob/f0cc88d77bdf3102308f9b203edc7499e904f650/docs/publishing.md). A document audit alone does not prove runtime quality.

## Decision boundaries and next stage

**Recommended first implementation tranche:** tidy About narrator transitions, clarify duplicate portfolio merchandising, refresh the brand-profile font evidence, and add a one-page voice/asset-role rubric within the existing governed brand documentation. These are scoped **future proposals**, not edits completed by this audit.

**Deliberately out of scope:** changing protected site UI/HTML in this report, changing global CSS or sibling repos, rewriting historical manifesto passages, transferring private records, creating new route families, Replit publishing, and merging/deploying to GitHub Pages.

**Source index:** [live homepage](https://overkillhill.com/), [projects](https://overkillhill.com/projects/), [manifesto](https://overkillhill.com/manifesto/), [universe](https://overkillhill.com/universe/), [about](https://overkillhill.com/about/), [contact](https://overkillhill.com/contact/), [legal](https://overkillhill.com/legal/); linked immutable repository files above. Research checked 2026-11-04; source SHA is pinned to make later drift visible.
---
title: "MurderBird Visual Canon and Generation Brief"
primary_topic: "MurderBird visual canon brief for next-generation image regeneration"
source_platform: "multi-source synthesis"
capture_mode: "derived"
completeness: "complete for the assessed inputs"
extraction_depth: "comprehensive"
requested_extraction_depth: "high quality and very detailed"
source_title: "Synthesis of two Microsoft Copilot threads, the published manifesto, two Notion pages, and the repository image tree"
source_date: "inputs dated 2025-12-06 through 2026-07-30"
source_time_context: "Notion snapshots 2026-06-18 and 2026-05-28; public manifesto and repository assets inspected 2026-07-30"
source_locator: "see the provenance section; private workspace URLs deliberately not committed"
retention_decision: "public-safe"
source_independence: "pass"
generated_at: "2026-07-30T00:00:00Z"
schema_version: "2.0"
artifact_type: visual-canon-brief
status: "historical; superseded for authority 2026-11-18"
related_artifacts:
  - "murderbird-sigil-material-canon-and-prompt-lineage.md"
  - "bronze-patina-behavior-for-murderbird-metal-finish.md"
---

# MurderBird Visual Canon and Generation Brief

> **Status, 2026-11-18: historical.** Current authority is [`docs/murderbird-unified-direction.md`](../../docs/murderbird-unified-direction.md) and, for the 3D production, the v1.0 closeout recorded in the `murderbird-uncaged` repository (`goal.md`, 2026-11-13: frozen at v1.0, likeness parked, not accepted). The published origin story, "What the Water Kept", fixes the canon chronology: a human Bronze Age Maker, an 1853 excavation and 1873 Mechanic repair, and a 2025 Builder awakening. Read this brief for the measured asset audit, the patina reconciliation and the correction history. Do not use its 2026-07-30 canon revision or its open-decision list as current direction.

> **No image was generated in this pass.** This artifact accumulates and reconciles the context required to generate images at higher fidelity while staying faithful to the original vision. It is the input to a generation pass, not the output of one.

## Introduction

The MurderBird was specified in December 2025 across two Microsoft Copilot conversations, published in partial form on the OverKill Hill P³ manifesto, and shipped into the repository as roughly a dozen image variants. This brief reconciles those three records and finds that they do not agree. The manifesto publishes the December ITER-03 prompt and calls it canonical, but the same session continued for four more corrections that the manifesto never captured, ending on a specific and unusual material target: hand-forged bronze, retrofitted in the 1870s, given a cybernetic brain in 2025, and aged to the color of a penny at the bottom of a wishing well for a hundred years. The shipped assets reflect none of that. Direct inspection and color sampling of the repository image tree shows a grey-green and olive-drab bird with no copper register, no blue register, and in the most recently deployed asset family, no metal at all. The original vision was more specific than what got built, and the specificity is recoverable. That is the case for a regeneration, and this document is the spec.

## What the canon actually is

Five layers, in the order they were established. Layers 1 and 2 are published. Layers 3 through 5 are not, and they are the reason a regeneration is worth doing.

| Layer | Established | Content | Published in manifesto |
|---|---|---|---|
| 1. Species and posture | ITER-01 failure, ITER-02 | Phorusrhacidae, not corvid. Axe beak, heavy running legs, clawed wings. Occupies rather than perches. | Yes |
| 2. Composition and field | ITER-03 | Aggressive perch on retro CRT. Horizontal stripe strata. Blueprint grid and schematic line work. Staggered stencil wordmark, bottom right. | Yes |
| 3. Isolation | Correction 1 | The bird must survive removal of the background, the wordmark, and the computer. The subject is the primitive; the badge is derived. | No |
| 4. Three-epoch fabrication | Correction 2 | Bronze Age hand-forge, 1870s Victorian retrofit, 2025 cybernetic brain. Three ages of metal on one body. | No |
| 5. Submerged patina | Corrections 3 and 4 | Not fresh bronze. Not bright verdigris. A hundred-year submerged penny: darkened greens, blues, greys. | No |

### The symbolic contract, which does not change

From the manifesto, and it constrains the visual as hard as any color value:

- The blueprint grid is the protocol layer.
- The horizontal stripes are categorical strata: physics, design, emotion, myth, madness, stacked in visible order.
- The mechanical body is the tinkerer's instinct to disassemble and reconstruct.
- The CRT is the old interface repurposed rather than replaced.
- The orange glow is the only warmth in the frame, which the manifesto notes is accurate.
- The bird does not sit. It occupies. The talons grip the way a pit-bull mind grips a problem it decided to understand before letting go.

The three-epoch fabrication canon is not a departure from this contract. It is the strongest expression of it: an object that was disassembled and reconstructed twice before anyone got to the cybernetics.

## Asset audit: measured, not remembered

Twelve repository assets were inspected directly and sampled programmatically on 2026-07-30. Values below are measured RGB from the shipped WebP files unless marked as an estimate.

### Stripe field, measured from `assets/img/library/over-kill-hill-p3-background-square-1024.webp`

Sampled at the vertical centerline, top to bottom.

| Band | Measured representative | Range observed | Manifesto name | Match assessment |
|---|---|---|---|---|
| 1 | `#1F3D2E` | `#112F20` to `#365445` | "slate teal" | Reads deep forest teal. Much darker and greener than "slate" implies. |
| 2 | `#45501A` | `#374008` to `#6A713A` | "carbon green" | Reads olive drab, not carbon. |
| 3 | `#6B6420` | `#5F5814` to `#938C43` | "faded mustard" | Closest match of the six. |
| 4 | `#6E4B0B` | `#6E4A0D` to `#917737` | "rust orange" | Reads burnt ochre. Less red than "rust orange." |
| 5 | `#47341A` | `#47341A` to `#7E5A20` | "dark plum" | Reads brown, not plum. No violet component. |
| 6 | `#1C3729` | `#142F23` to `#3B5749` | "slate teal" (repeat) | Same as band 1. |

**Finding:** the shipped stripe field is materially darker and more desaturated than the named palette, and two of the five named hues (plum, rust orange) are not present as named. The blueprint grid and schematic line work are present and correctly subtle. The stripe field itself is good work and worth preserving; the naming is what drifted. Lock hex values, retire the color names, or align the names to the measurements.

### Bird metal, measured across `bird-crucible`, `bird-perch`, and `bird-patrol` assets

| Role | Measured | Notes |
|---|---|---|
| Deepest shadow | `#0A1A0E`, `#0C1E11` | Near-black green. Correct value range. |
| Oxidized mid tone | `#103226`, `#143427` | Green with a slight cool cast. |
| Plate and beak mid | `#2A523B`, `#39614B`, `#3D634B` | Oxidized green-grey. This is the dominant read. |
| Neutral plate highlight | `#585652`, `#5B5C57` | Grey-neutral, from the sentinel family. |
| Cybernetic eye lens | `#B9721D`, `#BE7419`, `#D7802C` | Amber-orange. Bezel visible in the crucible, perch, and patrol assets. |

### Warm accent inconsistency

| Asset family | Measured warm accent | Reads as |
|---|---|---|
| `bird-patrol`, `bird-perch`, `bird-crucible` | `#B9721D` to `#D7802C` | Amber-orange, lens-like, with a bezel |
| `sentinel-waiting`, `sentinel-warning` | `#D69F3F` | Flat gold, almond-shaped, no lens, no bezel |

**Finding:** the single warm accent that the manifesto calls the only warmth in the frame is two different colors and two different objects across the shipped set. One is a machine lens. The other is an animal eye. This is the clearest measurable drift in the entire asset tree.

### Drift assessment by asset family

| Family | Canon compliance | Specifics |
|---|---|---|
| `title-right-low-bird-crucible-square-1024` | **Highest.** Closest to canon. | Plate-form feathers with visible rivet studs, oxidized green-grey metal, glowing orange lens with bezel, stripe field, blueprint grid, wordmark. Missing: copper hue, blue register, differential aging, the 1870s mechanism layer. |
| `title-low-right-bird-perch-comp-square-1024` | High. | Same bird, canonical CRT perch, talons gripping the monitor. Same gaps as crucible. |
| `bird-patrol-comp-left-wide-1536` | High for narrative use. | Bird stalking toward the CRT rather than perched on it. Strong lens eye. Good editorial asset. Same material gaps. |
| `sentinel-waiting`, `sentinel-attacking`, `sentinel-warning` | **Lowest, and these are the deployed ones.** | Organic feathers with soft edges and only faint stud marks. Olive drab `#48502D` and `#2B3718`, no oxidized copper, no blue. Flat almond eye `#D69F3F`, no lens, no bezel. Reads as a bird, not as a machine that was forged, retrofitted, and rewired. This is the ITER-01 failure mode returning: not the wrong species this time, but the wrong substance. |
| `logo-*`, CRT-only assets | Neutral. | The computer is rendered as grey-green stone-textured plastic rather than aged tech casing. Consistent with the bird's grey-green, inconsistent with "aged tech casing" from the wordmark spec. |
| Wordmark, baked into image | Spec divergence. | Rendered as a rounded slab serif, not the specified "bold retro stencil." Staggered two-row bottom-right placement is correct. Warm ochre is in family. |

### Two constraints from the repository's own documentation

Both come from files already in the tree and both point the same direction.

1. `assets/img/readme.md`: "the blueprint grid is rendered via CSS using the `.stripe-bg` class and background gradients." The field is code, not artwork. The bird only needs to be a transparent subject.
2. `assets/img/readme.md`: "Avoid embedding text within images; instead use HTML/CSS for live, accessible text." Every current badge asset violates this by baking the wordmark in.

**Production consequence:** the primary deliverable of a regeneration is a set of transparent-background bird states. Composed badges are derived outputs for social cards and previews, where baked text is acceptable because the surface requires a flat image.

Also relevant: `assets/img/library/readme.md` records that everything in `library/` was moved out of the live tree on 2026-05-03 by `scripts/move-orphans-to-library.py` and that none of those files are referenced by any production page. The three canon-closest assets, crucible, perch, and patrol, are all in `library/`. The three least canon-compliant assets, the sentinel set, are the ones still in the live tree. The repository is currently shipping its weakest interpretation.

## The reconciliation: what the two threads together actually specify

The sigil thread supplied the aesthetic target. The bronze thread supplied the physics. Neither alone is sufficient, and together they resolve an ambiguity that has been sitting in the canon since December.

**The ambiguity:** the word "verdigris" was used to mean both the bright chalky turquoise of an air-exposed monument and the dark submerged tone the user actually asked for. Those are different environments producing different chemistry.

**The resolution:** the wishing-well referent specifies still fresh water, submerged, low oxygen, low chloride, minerals present. Mapped onto the bronze thread's environment logic, that produces a thin, tight, adherent patina in darkened malachite green and azurite blue with grey-black mineral staining. Not bright. Not chalky. Not flaking.

| Spec element | From the sigil thread | Governed by the bronze thread | Resolved instruction |
|---|---|---|---|
| Base metal | Hammered bronze and copper plate | 88 to 90 percent copper, 10 to 12 percent tin | Copper-dominant alloy. Every color decision is a copper corrosion decision. |
| Green | "darkened greens" | Malachite, a copper carbonate | Deep malachite green, in recesses and across plate faces |
| Blue | "blues" | Azurite, a copper carbonate | Azurite blue interleaved with the green, not zoned separately. Physically justified, not decorative. |
| Grey | "grey" | Copper oxides and mineral staining | Grey-black in undercuts and as mineral deposit, supplying the value range |
| Patina thickness | "thousands of years of patina" | Patina is thin and protective, not heavy scaling | Thin, tight, adherent. Plate edges, rivets, and hammer facets read through it. |
| Flaking | not requested | Chloride-driven, marine, and a bronze-disease symptom | **Exclude.** No powder, no flake, no scale. |
| Brightness | "brighten without losing industrial depth" | not addressed | Achieve contrast through value separation between plate faces, not global brightness lift. |

## Generation spec

Model-agnostic. Written to be pasted, adapted, and diffed rather than treated as sacred text.

### Non-negotiables

Six things. If a render misses any of them it has failed regardless of how good it looks.

1. **Phorusrhacidae silhouette.** Axe-profile beak, heavy ground-running legs, clawed wings held as weapons, large body mass, ground-dominant stance. Any drift toward corvid proportions is the ITER-01 failure.
2. **Occupying posture.** Talons grip. The bird does not rest, roost, or pose. Weight is forward.
3. **Three ages of metal, differentiated.** Hand-forged bronze, machined 1870s retrofit, unaged 2025 insert. All three visible and distinguishable.
4. **Thin submerged patina.** Darkened malachite green, azurite blue, grey-black mineral staining. Plate geometry legible through the finish. No flaking.
5. **One warm element.** The cybernetic eye. Sole light source on the subject. No warm rim light, no warm bounce, no second glowing component.
6. **Transparent background for subject deliverables.** No baked field, no baked wordmark, on any primitive asset.

### Prompt, isolated subject

```text
A highly detailed 2D digital illustration in blueprint-infused steampunk
style. Subject only, on a transparent background.

SUBJECT
A mechanical bird derived from prehistoric terror birds (Phorusrhacidae) and
raptors. Massive hatchet-profile beak. Heavy ground-running legs. Clawed
wings held as weapons, not for flight. Aggressive occupying posture, weight
forward, talons gripping. Ground-dominant, predatory, unbothered.

FABRICATION HISTORY, three visible layers
(1) BRONZE AGE. The body shell, feather plates, beak sheath, and talon
    armor were hand-forged by a Bronze Age artisan from hammered bronze and
    copper plate. Irregular plate thickness, visible hammer facets,
    asymmetric overlap, no machine tolerance anywhere in this layer.
(2) 1870s VICTORIAN RETROFIT. Joints, leg armature, and wing pivots were
    rebuilt with machined hardware: gears, rivets at regular pitch, turned
    fittings, pressure valves. Steel and brass introduced alongside the
    original bronze, visibly newer than the forged layer.
(3) 2025 CYBERNETIC INSERT. A modern brain and ocular lens were installed.
    Clean, precise, deliberately foreign to both older layers. Unaged. The
    only luminous element on the body.

SURFACE AGE
Approximately a century submerged in still fresh water. Thin, tight,
adherent patina. Not a thick crust. Plate edges, rivet heads, and hammer
facets read clearly through the finish. High points, beak ridge, talon tips,
and leading plate edges are worn back toward exposed alloy. Recesses and
undercuts hold the darkest, greenest deposit. Grey-black mineral staining
throughout.

DIFFERENTIAL AGING
Bronze goes deep malachite green and azurite blue. Steel goes black and
rust. Brass goes brown-gold. The 2025 insert has not aged at all.

PALETTE
The color of a copper penny left at the bottom of a wishing well for a
hundred years. Darkened greens, blues, and greys. Deep malachite green,
azurite blue, grey-black. NOT bright verdigris. NOT chalky turquoise. NOT
Statue-of-Liberty green. Dark, submerged, mineral.

WARMTH BUDGET
The cybernetic ocular lens is the only warm element in the entire frame.
Amber-orange, roughly #C0761E core with a hotter center, set in a machined
bezel. It is the only light source on the subject. No other warm accent, no
warm rim light, no warm bounce.

RENDERING
2D digital illustration. Distressed texture. Contrast achieved through value
separation between plate faces, not through global brightness. Engineered
and legible, industrial depth preserved. Clean silhouette suitable for
compositing.

OUTPUT
Subject only. Transparent background. No background field, no stripe
pattern, no wordmark, no computer, no ground shadow.
```

### Prompt extension, composed badge

Append to the isolated-subject prompt when a flat composed image is required, for social cards and previews only.

```text
STAGING
The bird perches aggressively on top of a retro CRT computer: glowing
monitor, detailed wiring, classic keyboard. Talons grip the casing, they do
not rest on it. The CRT is aged tech casing, worn plastic and painted metal,
not stone.

FIELD
Wide horizontal stripes, bottom to top: deep forest teal #1C3729, dark plum
brown #47341A, burnt ochre #6E4B0B, faded mustard olive #6B6420, olive drab
#45501A, deep forest teal #1F3D2E. Over the full frame, a clean visible
blueprint grid with faint schematic line work. Engineered, not overwhelming.

WORDMARK
Bottom right, two staggered rows, bold retro military stencil with visible
letterform bridges: "OverKill" with "Hill P3" indented beneath. Distressed
blood-orange with slight metallic flake, as if screen-printed onto aged
tech casing.

INTENT
Structured, militant, industrial. A badge for a rogue prompt-engineer's
personal OS.
```

Note on the wordmark: the shipped assets use a rounded slab serif, not a stencil. If stencil is still the intent, the phrase "with visible letterform bridges" is the instruction that produces it, because "stencil" alone has repeatedly failed. If the slab serif is now preferred, update the manifesto so the spec matches the shipped brand rather than leaving the divergence undocumented.

### Deliverable matrix

| Asset | State | Format | Background | Purpose |
|---|---|---|---|---|
| Sentinel, waiting | Standing, front-facing, alert | 2048 square, PNG plus WebP | Transparent | Primary mascot, replaces the current organic sentinel |
| Sentinel, warning | Wings partly spread, beak open | 2048 square | Transparent | Warning and 404 states |
| Sentinel, attacking | Full aggression, wings out, talon raised | 2048 square | Transparent | Error and explosion states |
| Perch | Gripping a CRT, three-quarter view | 2048 square | Transparent | Composed badge source |
| Patrol | Stalking profile, approaching left or right | 2048 by 1152 | Transparent | Wide editorial and hero use |
| Schematic breakdown | Exploded technical view, the three fabrication layers called out | 2048 square | Transparent or blueprint field | Brand governance reference; documents the canon visually. This was offered in December and never built, and it is the highest-value unbuilt item in the backlog. |
| Composed badge | Perch plus field plus wordmark | 1200 by 1200 and 1200 by 630 | Baked | Social and Open Graph, per `assets/img/readme.md` |

Naming should follow the existing convention: `over-kill-hill-p3-{subject}-{state}-{shape}-{longedge}`. Consider a generation marker, for example a `-g2` suffix, so the new set is distinguishable from the December 2025 set during transition rather than silently replacing it.

### Acceptance tests

Run these against every candidate before it enters the tree. Each is a reject condition, not a preference.

| Test | Reject if |
|---|---|
| Species | The silhouette reads corvid, eagle, or generic raptor rather than terror bird |
| Posture | The bird looks like it is resting, posing, or waiting politely |
| Substance | The feathers read organic. Soft edges, no plate boundaries, no fasteners |
| Layer count | Fewer than three distinguishable fabrication ages are visible |
| Patina thickness | The finish buries plate edges, rivets, or hammer facets |
| Corrosion type | Any powder, flake, or crust is present |
| Hue | Bright verdigris, chalky turquoise, or a pure grey-green with no copper origin |
| Blue register | Azurite blue is absent entirely |
| Warmth budget | More than one warm element, or any warm light other than the ocular lens |
| Wear logic | High points and handled surfaces show no exposure to bare alloy |
| Background | Any baked field or wordmark on a primitive asset |
| Accessibility | The subject silhouette is unreadable at 192 pixels |

The last one matters more than it sounds. The tree already ships a 192-pixel favicon variant, and a bird that only works at 1024 is not a mascot, it is an illustration.

### What the 16-month capability gap actually buys

The user's premise for this overhaul is that models have improved substantially since December 2025. Specifically, here is what a regeneration can now hold that the original could not, which is the argument for redoing rather than retouching.

| Capability | Why it was out of reach in the original set | What it enables now |
|---|---|---|
| Differential material aging | The original renders averaged competing palette instructions into a single grey-green | Bronze, steel, brass, and unaged modern insert can coexist and read distinctly on one body |
| Long, ordered, multi-clause instructions | The December prompts were single paragraphs, and later clauses lost to earlier ones | The three-epoch layer structure can be specified as a hierarchy rather than a list of adjectives |
| Sustained material logic across a surface | Patina was applied as a color wash | Wear, deposit, and staining can follow the object's geometry and use history |
| Reliable transparent-background isolation | Achieved, but with soft and inconsistent edges across the set | Clean compositing-ready alpha at high resolution |
| Legible text in image | Stencil was requested repeatedly and never delivered | Still the weakest area. Keep the wordmark in CSS per the repository's own guidance rather than betting on it. |
| Pose consistency across a set | Each render was independently generated and the set drifted | A locked reference plus per-state prompts can hold one bird across many poses |

**The internal contradiction to fix before generating anything:** the December one-shot prompt retains "metallic gray and olive" from ITER-03 while simultaneously demanding bronze under submerged patina. Those instructions compete, and averaging them produces exactly the grey-green that the shipped assets show. The measured `#2A523B` to `#3D634B` plate range in the current tree is that average. Delete the grey-and-olive clause. It is a fossil of an earlier iteration, and it is the specific reason the copper never arrived.

## Canon revision, 2026-07-30: xeno origin and automaton kinematics

> **Superseded, 2026-11-18.** The xeno-origin chronology below (a non-human maker, a roughly two-century loss, a near-future reawakening around the 2070s) was not adopted. The published story keeps a human Maker and a 2025 Builder. The automaton kinematics rules (pinned plates, rub-wear polish, legible joints, asymmetric weighted pose, no motion effects) and the differential-aging idea remain useful rendering guidance and are not contradicted by the story.

Supplied directly by the user during this session. This **supersedes** the three-epoch fabrication stack in the section above, which it strengthens rather than contradicts. Claim class: `stated` for the narrative, `proposal` for the rendering consequences derived below.

### Revised provenance

| Era | Actor | Event | Surface evidence |
|---|---|---|---|
| Deep antiquity, eons before its time | A non-human or near-extraterrestrial intelligence | Original fabrication, impossibly advanced for its epoch | Geometry with no business existing in ancient metal: perfect radii, tolerances tighter than hand tools allow, joinery with no visible fastener, seams that shouldn't close that cleanly. **This is the tell, and it must be visible.** |
| Roughly the 1870s, Wellsian | Victorian engineers | First rediscovery and partial reconstruction. They did not understand it. They repaired it with what they had. | Brass, steel, and leather patchwork that is visibly cruder than the substrate it is bolted to. Rivets at regular pitch, gears, pressure valves, gaskets. Honest, competent, and wrong. |
| Roughly 1880s to the near future | nobody | Lost again for about two centuries | The Victorian additions carry the heavier corrosion. They are younger metal but worse metal. |
| Near future, slightly ahead of now | Modern or near-future intellect | Second rediscovery and cybernetic reawakening | One ocular lens, cleanly mounted. No cable harness, no bolt-on bulk. The modern hand knows better than to improve it. |

**The inversion is the best detail available in this entire brief.** The 1870s repair should look older and sicker than the ancient original. Nineteenth-century steel rusts and pits; the xeno substrate does not fail the same way. That single reversal communicates the whole four-part timeline in one glance, and it is not a thing image models have typically been asked to do. It is also the strongest possible expression of the manifesto's own doctrine: the thing built with real protocol outlasted the competent people who tried to patch it.

**Tone reference:** late-Victorian scientific romance. H.G. Wells, not Jules Verne whimsy and not modern steampunk cosplay. Brass, glass, leather, riveted plate, and engineering that is confident and mistaken.

**Palette consequence:** the submerged-penny target still governs the ancient substrate. The Victorian layer diverges: iron oxide reds and blacks, tarnished brass browns, darkened leather. That divergence is the differential-aging payoff, and it widens the palette without breaking the warmth budget, because none of it is luminous.

### Automaton kinematics: making a still frame imply motion

The requirement is not motion. It is *capacity* for motion, with the specific quality of a heavy ancient automaton: deliberate, weighted, mechanically constrained, arriving slightly late. Ten rules, ordered by how much each one buys.

1. **Feather plates are individually pivoted, not a fused shell.** Roughly two hundred discrete armored elements, each on its own pin, capable of raising and closing like a hackle. This is the single strongest signal that the object can move, and its absence is exactly why the shipped sentinel assets read inert.
2. **Wear is motion evidence.** Bare polished alloy exactly where parts rub each other: pivot collars, the swept arc a feather plate traces across its neighbor, the inside of the ankle hinge, the neck race. Patina survives everywhere the machine does not touch itself. This proves the thing has been moving for millennia and is the highest-value single detail in the brief.
3. **Every articulation is a named mechanism.** Ball-and-socket at the hip, hinge at the ankle, universal joint at the neck base, layered pivot at the wing root. If a viewer cannot tell how a part bends, it does not read as able to bend.
4. **Show running clearance.** Real mechanisms need gaps. The dark line between overlapping plates, the crescent void where a plate rotates past its neighbor, the slot a tendon rides in. Zero-clearance surfaces read as carving.
5. **Actuation is visible.** Tendon cables, push rods, or worm drives running body to limb, routed the way a mechanic would route them: shortest path, anchored, with a tensioner.
6. **Counterweight logic.** Terror birds are front-heavy. An automaton solving that needs visible mass at the tail or a heavy pelvic casting. Show the engineering that makes the pose stable.
7. **Asymmetric mid-motion pose.** Weight on one leg, the other mid-lift with the ankle already flexing for the next contact. Head rotated off the body axis. Bilateral symmetry reads as parked.
8. **Lag in the silhouette.** The body committed to a direction, the head not yet caught up. Heavy things arrive late, and that delay is what separates automaton from animal.
9. **One element caught in transition.** A single plate half-raised, a valve mid-stroke, a lens iris partly stopped down. One frozen inconsistency implies a next frame.
10. **No motion blur, no speed lines, no dust, no effects.** Movement is implied by mechanism and pose only. Effects would reduce it to an action figure.

### Additional non-negotiables

Replacing item 3 of the original six, and extending the list.

- **Four visible eras, not three.** Xeno substrate, Victorian repair, two centuries of neglect, minimal modern insert.
- **The ancient work must out-engineer the Victorian work.** Visibly. This is a hard requirement, not a nuance.
- **Articulated, not sculpted.** The object must read as a machine at rest between movements.

### Additional acceptance tests

| Test | Reject if |
|---|---|
| Articulation | The bird reads as a solid sculpture with no visible joints or mechanism |
| Plate independence | Feather plates read as a fused shell rather than individually pinned |
| Pose | Bilaterally symmetric, evenly weighted, or otherwise parked |
| Rub wear | No bare-alloy polish at pivots, sweep arcs, or hinge interiors |
| Effects | Motion blur, speed lines, dust plume, or any motion effect present |
| Era inversion | The Victorian repair looks newer, cleaner, or healthier than the ancient substrate |
| Era count | Fewer than four distinguishable eras readable on the body |
| Modern restraint | The cybernetic insert is bulky, cabled, or competes with the ancient work |
| Origin tell | The ancient fabrication looks hand-made rather than impossibly precise for its epoch |

### Prompt delta

Replace the `FABRICATION HISTORY` block in the isolated-subject prompt with the following. Everything else in that prompt stands.

```text
FABRICATION HISTORY, four readable eras
(1) DEEP ANTIQUITY, NON-HUMAN ORIGIN. The core body, feather plates, beak,
    and talons were fabricated eons before their time by an intelligence that
    was not human. Impossibly precise for the epoch: perfect radii,
    tolerances no hand tool could hold, seamless joinery with no visible
    fasteners. It does not look hand-made. It looks manufactured by something
    that had no business existing yet.
(2) 1870s VICTORIAN RECONSTRUCTION. Rediscovered and partially repaired by
    Victorian engineers who did not understand it. Brass, steel, and leather
    patchwork bolted onto the ancient substrate, visibly cruder than what it
    repairs: rivets at regular pitch, gears, pressure valves, gaskets,
    turned fittings. Confident, competent, and wrong.
(3) TWO CENTURIES LOST. The Victorian additions have corroded far worse than
    the ancient original. Iron oxide reds and blacks, tarnished brass, dark
    cracked leather. The ancient substrate carries only thin, tight,
    submerged patina and has aged with dignity. The 19th-century repair looks
    older and sicker than the thing it was repairing.
(4) NEAR-FUTURE REAWAKENING. A single cybernetic ocular lens, cleanly and
    minimally mounted. No cable harness, no bulk. Restrained, reverent,
    unaged. The only luminous element on the body.

KINEMATICS, the bird must read as capable of movement
Approximately two hundred individually pinned feather plates, each able to
raise and close like a hackle. Every joint is a legible mechanism:
ball-and-socket hip, hinged ankle, universal joint at the neck base, layered
wing-root pivot. Visible running clearance between overlapping plates.
Visible actuation: tendon cables and push rods, anchored and tensioned.
Visible counterweight mass at the tail balancing a front-heavy body. Bare
polished alloy exactly where parts rub: pivot collars, plate sweep arcs,
ankle hinge interiors. Asymmetric mid-motion pose, weight on one leg, the
other mid-lift with the ankle flexing. Head rotated off the body axis, the
body already committed to a direction the head has not caught up to. One
element caught mid-transition. Heavy, deliberate, mechanically constrained.
NO motion blur, NO speed lines, NO dust, NO motion effects of any kind.

TONE
Late-Victorian scientific romance. H.G. Wells. Not Verne whimsy, not modern
steampunk cosplay.
```

## Open decisions before generation

> **Resolved or retired, 2026-11-18.** These questions were overtaken by the unified direction brief, the September story and exhibit work, and the November 13 v1.0 closeout. They are kept as history, not as a pending checklist.

These are the user's calls. Generation should not begin until at least the first three are answered.

1. **Publish or hold the material canon.** The manifesto currently stops at ITER-03 and describes the bird as metallic gray and olive. Adding the three-epoch fabrication history and submerged patina as ITER-04 through ITER-06 would make the public sigil section match the actual vision. Holding it keeps the public page simpler but leaves it describing a bird that is about to be replaced.
2. **Retire, replace, or keep the sentinel set.** They are the deployed assets and the least canon-compliant. Replacing them is the whole point of the overhaul, but they are currently referenced by production pages.
3. **Stencil or slab serif.** The spec says stencil. Every shipped asset says slab serif. One of the two records is wrong.
4. **Lock one warm-accent hex.** `#B9721D`, `#D7802C`, and `#D69F3F` are all in the tree. Pick one.
5. **Retire or realign the stripe color names.** Measured bands do not match "carbon green," "rust orange," or "dark plum." Either lock hex tokens and drop the names, or rename to what actually shipped.
6. **Build the schematic breakdown or not.** It is the highest-leverage unbuilt asset, because it makes the canon self-documenting and gives future generation passes a visual reference rather than a prose one.

## Provenance

| Source | Type | Access | Date |
|---|---|---|---|
| "Terror Birds Explained" | Microsoft Copilot thread, user-supplied full paste | Pasted into this session | Sessions 2025-12-06 and 2026-06-14 |
| "Copper Content in Bronze" | Microsoft Copilot thread, user-supplied full paste | Pasted into this session | Session 2025-12-06 |
| OverKill Hill P³ Manifesto, public | Web page | Fetched | 2026-07-30 |
| "OverKill Hill P³ — Manifesto" | Notion page | Read via connector; private locator withheld | Snapshot 2026-06-18 |
| "Thread Archive — Manifesto Rewrite + Visual Sigils" | Notion page | Read via connector; private locator withheld | Snapshot 2026-06-18 |
| `assets/img/` tree | Repository, 12 assets inspected and color-sampled | Local mirror | 2026-07-30 |
| `assets/img/readme.md`, `assets/img/library/readme.md` | Repository documentation | Local mirror | 2026-07-30 |
| `context/threads/three-generation-*.md` | Prior extract, used as format precedent | Local mirror | 2026-07-30 |

**Claim classes.** The canon layers, symbolic contract, and prompt history are `stated`, sourced to the Copilot threads and the manifesto. All measured hex values are `stated` and reproducible from the named files. The drift assessment, the submerged-freshwater environment mapping, the differential-aging strategy, the deliverable matrix, the acceptance tests, and the capability-gap analysis are `inferred` or `proposal`, produced during this synthesis. The five Copilot renders and the one bronze-thread render are `referenced-not-supplied` and were never available as files. Whether any repository asset descends from any specific Copilot render is `unknown`.

**Retention:** public-safe. No employer material, no client material, no secrets, no personal identifiers beyond a first name. Two private Notion workspace URLs were supplied as inputs and are deliberately not committed; they are described by title only.

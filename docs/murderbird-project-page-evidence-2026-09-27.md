# MurderBird project-page editorial record

Date: September 27, 2026.
Page: `/projects/murderbird-uncaged/`.
Authoring source: `site-src/pages/projects/murderbird-uncaged/index.main.html`.
Website baseline: `3b2b8507f417a1dd0f707419d2aedf4b1038466b`.
Production reference: `OKHP3/murderbird-uncaged` at `4b1c726f5d9bbd1ba1048f89049a5b422001c506`.

## Purpose and owner authority

The owner requested a project account about the creative progression: revisiting
older artwork, second-generation images, motion experiments, assessing Apple
Music favorites, writing lyrics and composing an AI-generated song, and finally
imagining a modern school science-fair exhibit. The page explains decisions,
methods, tools, and developing skills. The fiction, manifesto, and application
implementation retain their separate homes.

The final owner correction in this chat supersedes the first attribution:
"many of the 2ndgen images were created with OpenAI's latest image tool....the
videos were created in Adobe Firefly". The earlier reply identifies GPT-5.6 SOL
as driving Firefly. The page associates that combination with the video workflow,
not with all second-generation images. Exact OpenAI image-model version and
Firefly video-model selection are not established. Do not invent a version or
attribute every retained image to a single generation pass.

The initial project description establishes the Apple Music assessment and the
science-fair motivation. No private library history, profile, or archive was
copied into the page. The owner explicitly states that none of the vocals are
their voice. The page preserves that distinction.

## Reference review

Reviewed the following supplied pages and their repositories on September 27:

- [Skillz Forge](https://overkillhill.com/skillz-forge/) and [repository](https://github.com/OKHP3/skillz): purpose, method, inspectable artifacts, companion application.
- [Skillz Shield](https://overkillhill.com/skillz-forge/skillz-shield/) and [repository](https://github.com/OKHP3/skillz-shield): bounded tool roles and explicit limits.
- [Chai Chasers](https://overkillhill.com/projects/glee-fully-chai-chasers/) and [repository](https://github.com/OKHP3/glee-fully-chai-chasers): personal motivation, actual experiments, development beyond the original idea.
- [Local AI Workbench](https://overkillhill.com/projects/mac-studio-local-ai-workbench/) and [repository](https://github.com/OKHP3/mac-studio-local-ai-workbench): progress journal, decisions, named tools, dated evidence.
- [The First Diagram Is Usually a Liar](https://overkillhill.com/writings/first-diagram-is-a-liar/) and [repository](https://github.com/OKHP3/first-diagram-is-a-liar): first-person experimentation, corrections, prompts, results.

Read the live GitHub Pages application surfaces for Forge, Shield, Chai Chasers,
and MurderBird. Some web-reader fetches failed; the applications were then read
through the browser. Read current repository READMEs directly. Consulted the
published [MurderBird story](https://overkillhill.com/writings/murderbird/) and
[manifesto](https://overkillhill.com/manifesto/) to keep this page's scope distinct.
The requested project route was absent from the website checkout and its current
remote main. This change creates that route in the existing static generator.

## Production evidence

All paths below belong to the MurderBird repository at the reference above.

| Claim | Supporting source | Limit |
| --- | --- | --- |
| Reference-specific image briefs and controlled revisions | `context/threads/murderbird-reference-master-generation-record-2026-07-30.md` | Earlier native OpenAI image generation; not proof of a particular modern model version. |
| Retained generation and correction prompts | `assets/murderbird/v2/manifest.json` | Preserve candidate and review labels; not blanket approval. |
| Rejected or held motion pilots and stand correction | `assets/docs/murderbird-video-migration-2026-09-08.md` | Owner identifies Firefly; historical ledger itself does not name the video model. |
| Original instrumental, D-centered minor, 104 BPM, MIDI, stems, GarageBand interpretation | `assets/murderbird/production/audio/iron-verdict/production-notes.md` | Instrumental and GarageBand render are distinct from the later sung production. |
| Notated vocal direction and guide | `assets/murderbird/production/audio/iron-verdict/vocal-score-v2/performance-sheet.md` | Guide is not a singer's take. |
| Accepted AI-sung v3; ACE-Step 1.5; Demucs; finishing and loop | `provenance/iron-verdict-v3-release.json` | Exact code/model revisions remain in the source record; no third-party voice clone claimed. |
| Editable Blender studies, rigid parts, GLB delivery, artistic review | `docs/production-workflow.md`, `docs/production-handoff.md`, `README.md` | Published for assessment; final likeness acceptance remains pending. |

The page reuses the website's existing published artwork and eight-second MP4.
The song streams from its existing approved public MurderBird URL. No new
creative source file, private session, model binary, or production archive was
copied into the website. The app repository was not edited.

## Integration and verification

- Existing OverKill Hill brand profile v1.1.0; shared typography, colors, layout,
  navigation, theme controls, and table components. No new stylesheet, package,
  application framework, or custom JavaScript.
- Registered the route, project shelf, primary navigation, sitemap, status
  record, search data, and generated universe map. Other generated English pages
  receive the shared navigation link; their editorial bodies are unchanged.
- The song uses the existing exact-URL MurderBird media policy. Added the new
  route to that policy and updated its regression test. No broader media host
  allowance was introduced.
- PASS: site generation and freshness; search freshness; project registry;
  universe map freshness; CSP generation and verification; six CSP regression
  tests; cache fingerprints; internal links; whitespace checks.
- PASS: structural validator, with 32 existing locale analytics/structured-data
  warnings. Voice baseline passes with no new warnings.
- PASS: browser checks for loaded artwork, valid in-page anchors, native media
  controls, no autoplay, eight-second video playback and 147.75-second song
  playback, keyboard expansion of the prompt disclosure and visible focus.
- PASS: no page overflow at desktop and narrow phone widths; the tools table was
  corrected to fit within the 320-pixel viewport.
- Publication was authorized by the owner after the initial local review.
  Remote CI and deployment must be verified against the merged revision; local
  checks alone do not establish publication. Artistic acceptance of the working
  3D study remains separate.
- Added page-specific WebPage, CreativeWork, and BreadcrumbList structured data,
  canonical and social metadata, and explicit OpenAI/Firefly/music/exhibit tags.
- Refreshed the complete 175-entry search catalog and universe navigation. The
  new project has eight indexed entries (page plus seven sections), classified as
  Project. All 17 search tests and 52 SEO fixture tests passed; the local search
  interface returned the new entries.

Preview: `http://127.0.0.1:5067/projects/murderbird-uncaged/` while the local
preview server is running. Private local review screenshots are under
`.local/murderbird-project-page/` and are not publication assets.

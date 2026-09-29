# MurderBird repository boundary

The owner established this boundary on September 26, 2026.

| Repository | Owns |
|---|---|
| `OKHP3/overkill-hill` | Public brand, portfolio, published stories, static page shells, and the assets needed to serve them. |
| `OKHP3/overkill-hill-foundry` | The OverKill capability workbench for prompts, Agent Skills, workflows, and software starters. It can incubate work that graduates into a separate project. |
| `OKHP3/murderbird-uncaged` | All MurderBird creative production and its interactive exhibit: images, video, music, lyrics, model studies, source material, and app code. |

## Transfer and retained copies

The migration copied the relevant tracked media, historical creative notes,
art direction, review records, and story-source snapshots into the sibling
`murderbird-uncaged` clone. Its
`provenance/overkill-hill-import-2026-09-26.json` records original paths, source
commit, destination paths, byte counts, and SHA-256 hashes. Run
`python3 scripts/verify-media-import.py` there to verify that snapshot.

The music and video production trees were relocated from
`assets/murderbird/production/audio/` and `assets/murderbird/production/video/`
to those same paths in the sibling repository. Private music-session archives
and ignored production work were copied and verified separately under the
sibling's ignored `.local/archives/` tree before their originals were removed.
Private file details and verification receipts remain local. They must not
be committed or published.

The website keeps `/writings/murderbird/`, its English authoring source,
localization records, `assets/img/` delivery paths, and its public motion clip
under `assets/video/`. It also retains `assets/murderbird/v2/`,
`assets/murderbird/production/images/`, and historical image/context records
where the existing builders, preservation tests, or source links depend on
them. These are compatibility snapshots. Their matching imported originals
now belong to the creative repository. Replacing these remaining build
dependencies with a versioned delivery package is a separate refactor.

Do not use retained snapshots as permission to resume creative production in
this website repository. Update public delivery copies only as a deliberate
site change, with provenance and the existing validation gates.

The first path component `assets/downloads/music-session-*` is reserved for
private archives and is excluded from release, whether it is a directory,
file, or symlink. Public visitor downloads must use another descriptive name.

## Story and rights

The [published origin story](https://overkillhill.com/writings/murderbird/)
remains an editorial publication on the main website. The exhibit receives
an exact source snapshot for creative context. The story is fiction; the
museum-like presentation does not make the creature or its history real.
Preserve the existing content rights and production-status labels.

## Recovery and verification

Git history preserves the removed tracked production files at source commit
`f1142a02f1e73cd45e46e981022aef27f1c6e095`. Restore only the required paths
from that revision if rollback is necessary. Private material can be restored
from its sibling archive using the local migration receipt and recorded
source paths, after verifying the original path is vacant.

Website verification includes the release-package tests, generated HTML and
search freshness, structural/link checks, and the MurderBird asset checks.
Exhibit verification includes imported file hashes and a production build
whose output excludes source archives. Local results, GitHub CI, Pages
deployment, and Replit checkout synchronization are separate evidence.

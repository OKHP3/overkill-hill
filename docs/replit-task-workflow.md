# External execution of Replit plans

Use the project-local
[okhp3-replit-task-executor](../.agents/skills/okhp3-replit-task-executor/SKILL.md)
with a coding-capable Codex, Claude, or GitHub Copilot session when Replit has
planned a task that should be implemented externally.

Select the task, capture its acceptance criteria, resolve overlapping writers,
and record a shared ownership handoff before editing. Keep one implementation
owner for each affected file set. Work on a feature branch, validate the scoped
change, and use the protected GitHub PR process. A board status is not proof
that a change reached GitHub or production.

For this repository:

- English authoring is under `site-src/`; the published site is generated
  static HTML, shared CSS, and browser JavaScript. Do not introduce a Vite or
  TypeScript application pipeline because a generic Replit plan assumes one.
- Discover the relevant validation from `scripts/README.md` and
  `.github/workflows/validate.yml`. Run the checks appropriate to the change
  and preserve the required CI gates.
- GitHub Pages publication is handled by `.github/workflows/pages.yml`, which
  consumes the validated artifact for the exact commit. Observe that pipeline
  when an authorized merge triggers it.
- `.replit` retains the Free webview preview, Node/Python runtime, and QA
  workflows, but defines no Replit publication route. The standalone
  `scripts/build-replit-release.py` helper and its release/recovery safeguards
  remain tested without being wired to Replit publishing.
- Reconcile Replit's local commits explicitly before synchronizing it. Keep
  Windows source parity, Replit source parity, connector authentication, task
  disposition, CI, and live deployment evidence separate.
- Keep private task packets and investigation output in an ignored `.local/`
  location unless a shared, access-appropriate issue or ledger is authorized.
  A private local packet by itself does not coordinate other agents.

Example invocation:

> Use okhp3-replit-task-executor for the selected Replit task. Inspect its plan,
> dependencies, existing output, and overlapping writers. Prepare the ownership
> handoff, then implement the authorized change using this repository's tools
> and validation rules. Return separate source, board, CI, and deployment
> evidence. Do not send implementation prompts to Replit Agent.

The package is a draftable candidate. Structural validation and document review
do not establish measured cost savings or verified operation on every host.
Its dated [source ledger](../.agents/skills/okhp3-replit-task-executor/references/replit-semantics.md)
records official Replit guidance and observed interface differences.

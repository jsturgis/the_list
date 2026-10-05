## Agent skills

### Issue tracker

Issues live in GitHub Issues; use the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` at root + `docs/adr/`. See `docs/agents/domain.md`.

### Design

Before any UI work, read `DESIGN.md` (repository root): colours by semantic token (no Tailwind palette colours or
`dark:` colour variants), Figtree, the type scale and the component styles. If you add a colour token, add it to both
`frontend/src/styles/globals.css` and `DESIGN.md`; a test fails until they match. For visible changes, take before and
after screenshots with `npm run screenshots -- <dir>` in `frontend/`.

# Game Tuning/Ops dashboards stay on the stock ArxAdminSite with django-htmx, not django-unfold

The #1221 spec named `django-unfold` for the Game Tuning/Ops dashboards, but by build time
`ArxAdminSite` already carried #1333's stock-admin template overrides (grouped index, pinned
models, export/import, the Game Setup hub); unfold replaces the admin template tree wholesale
for zero functional gain here (`autocomplete_fields` is stock Django, not an unfold feature), so
adopting it would clobber that surface. We built both dashboards as plain admin views on the
existing `ArxAdminSite` using `django-htmx` + a vendored `htmx.min.js`, narrowing ADR-0022's
"admin-hosted, not React" decision (which still stands) away from the unfold implementation
detail it named. We also rejected a React staff hub for this surface, for the same reason
ADR-0022 gave: it would forgo admin's per-model RBAC and form machinery for no real gain, and
rejected auto-seeding tuning defaults on boot, re-affirming that seeding stays a manual,
superuser-triggered action (mirroring the "Load sane defaults" button). The Monte Carlo
simulator (`world.combat.simulation`) drives the real `resolve_round` combat pipeline rather
than a hand-rolled probability model, honoring the standing no-parallel-implementations rule.

> Status: accepted · Source: #1220, #1221, ADR-0022, CLAUDE.md (Anti-Reinvention)

# Content dependencies are declared in one central table and reported by a live-DB registry

Several live code paths hard-depend on a specific authored database row - a named
`ConditionTemplate`, a `CheckType`, a tuning config singleton - existing, and either
raise `DoesNotExist` deep in the call stack or silently no-op when the row is absent
(#3444). The ruling was that missing authored content does not get defensive guards
sprinkled around the lookups: the fix for unauthored content is to author it, not to
teach every call site to survive its absence. So `src/web/admin/tuning/required_content.py`
holds one central `_declarations()` table - 54 rows, tiered REQUIRED (50, a code path
a player or staff member can hit today breaks or goes silently inert) or TUNING (4, a
config singleton the game runs without, just with worse numbers) - and
`collect_required_content()` probes each declared row directly against the live
database, batching every same-model `NamedRowsProbe` onto one `values_list` query per
label. `ops_required_content_fragment` renders the result as a sixth panel on the
Game Ops dashboard
(`docs/adr/0093-admin-hosted-tuning-dashboard-htmx-without-unfold.md`), gated by the
same `superuser_required` decorator as every other panel there.

**Rejected: try/except guards at each lookup.** Wrapping every hard-dependent lookup
in a try/except would let the game run silently inert wherever content is missing -
exactly the failure mode this feature exists to surface instead of hide. A missing
row is a staff gap, not a runtime condition to tolerate.

**Rejected: a repo-side manifest or a seeder audit.** `world/seeds/` is
clone-bootstrap and E2E scaffolding only, and the database is the master copy of
authored content
(`docs/adr/0238-content-repo-retired-database-is-the-authoring-surface.md`).
`world/seeds/game_content/combat.py:203-221` seeding `StakesEscalationModifier` rows
proves nothing about whether those rows exist in production - a fresh clone's seed
run and a live game database are different databases with different history. Only
the database actually being asked can answer the question, so the probe has to run
live, not against anything checked into the repo.

**Rejected: a Django system check.** `src/web/admin/checks.py`'s two existing checks
(`web_admin.W001`, `web_admin.E001`) are structural - they inspect
`admin.site._registry` and never query a table. Django's check framework runs at
startup, before or without a usable database connection in some deploy paths, so a
question that requires querying live content rows does not belong there.

**Rejected: per-package declaration files.** A `content_dependencies.py` under each
`world/<pkg>/` was considered and rejected in favor of the single central table,
deliberately to hold the file count down (ruled 2026-08-30) rather than scatter 48
rows across dozens of small files a staff member would have to know to go looking
for.

> Status: accepted · Source: #3444

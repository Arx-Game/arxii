# ADR-0235: Alpha is durable - the production database is the only master copy of authored content

**Status:** Accepted (2026-08-26, Tehom in-session). **Supersedes
[ADR-0013](0013-schema-only-migrations-pre-production.md)** outright: its premise
("the dev database is disposable and holds no meaningful rows to preserve")
expires the moment the first alpha row is authored into prod, and a directive
whose premise has expired is worse than no directive, because agents still obey it.

Durability from 2026-08-26 forward is **two-tier, split by what created the row**:

- **Authored content is durable and irreplaceable.** Codex entries, lore prose,
  techniques, traditions, conditions, check types, catalogs, grid rooms -
  everything staff writes - exists in exactly one place: the production database.
  Fixtures are gitignored repo-wide (`**/fixtures/**/*.json`), the content repo is
  retired in favor of authoring directly in the database (ADR-0236), and the seed
  data that *is* in the repo is clone-bootstrap and E2E-test scaffolding, not a
  copy of the corpus. There is no second copy in version control to reload from.
  Dropping a column of authored text is losing the text.
- **Alpha play state is resettable, and players are told so.** Characters, sheets,
  XP, scenes, encounters and the rest of what play generates may be wiped before
  open beta. That is a stated alpha condition, not an accident, and it is the only
  reason this ADR is a two-tier rule rather than a blanket one.

The consequence that governs every PR: **a migration that drops or renames a
column, model or row holding authored content must carry a `RunPython` backfill in
the same migration.** ADR-0013's delete-instead-of-backfill shortcut is withdrawn
for authored-content tables; it survives only for play-state tables, whose rows
alpha already declares expendable. This is not advisory. Deploy runs
`python -m django migrate --noinput` unattended on every converge
(`infra/ansible/roles/app_deploy/tasks/main.yml`), so **the merged migration is
itself the destructive act** - no operator stands between a merge and a dropped
production column, and the review of the diff is the only gate there is. The same
reasoning narrows "No Backwards Compatibility in Dev": it governs code, wire
formats and APIs, never a persisted column that holds authored rows.

There is no escape hatch. A schema change whose old column genuinely cannot be
backfilled needs the content re-authored first, or an explicit ruling from Tehom
recorded on the PR before it merges.

**Rejected:** *Keeping ADR-0013 with a "be careful once we launch" caveat* - the
rule as written tells agents backfill code is untested ballast, which is precisely
inverted for an alpha database; a directive that has to be mentally negated on
every read is a bug, not a nuance. *A blanket "all data is sacred" rule* - it would
force backfill ceremony onto play-state churn that alpha explicitly declares
resettable, and a rule that is visibly over-strict in the common case gets ignored
in the rare one. *Gating production migrations behind a manual operator step* -
rejected for now: the unattended converge is what keeps deploys boring and
recoverable, and the guard belongs at review time, where the destructive operation
is legible in the diff, rather than at the console during a deploy. Revisit if a
lossy migration ever actually reaches prod.

> Status: accepted · Source: Tehom in-session 2026-08-26 · Supersedes ADR-0013 ·
> Related: ADR-0236 (the content repo is retired; the DB is the master copy),
> ADR-0201 (credited rows are frozen against loads), ADR-0140 (grid bundles are
> content snapshots, never live-game backups), ADR-0012 (PostgreSQL only)

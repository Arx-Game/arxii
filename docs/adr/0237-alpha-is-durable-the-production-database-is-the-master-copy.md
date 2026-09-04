# ADR-0237: Alpha is durable - the production database is the only master copy of authored content

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
  retired in favor of authoring directly in the database (ADR-0238), and the seed
  data that *is* in the repo is clone-bootstrap and E2E-test scaffolding, not a
  copy of the corpus. There is no second copy in version control to reload from.
  Dropping a column of authored text is losing the text.
- **Alpha play state is resettable, and players are told so.** Characters, sheets,
  XP, scenes, encounters and the rest of what play generates may be wiped before
  open beta. That is a stated alpha condition, not an accident, and it is the only
  reason this ADR is a two-tier rule rather than a blanket one.

The consequence that governs every PR concerns the operations that actually destroy
information: **`RemoveField` and `DeleteModel`** (and a `RunSQL`/`RunPython` that
deletes). `RenameField`/`RenameModel` are *not* in scope here - the data survives the
rename intact - though they remain flagged on the separate old-code/new-schema
compatibility axis (`docs/operations/observability-baseline.md` §4.5), which is a
different concern from this ADR's.

A destructive operation on an authored-content table is exactly one of three things,
and the author must say which in the PR:

1. **Restructure** - the information survives in a different shape (split, merge,
   retarget). A `RunPython` in the *same PR* carries it across, in **its own
   migration** - never the one holding the schema change. Mandatory; this is the
   case ADR-0013 used to wave through. See the amendment below for why the
   migration has to be separate.
2. **Deliberate discard** - we have decided the data is not worth keeping. No
   backfill exists or is wanted. What makes this safe is that it was decided rather
   than defaulted into, and that the rows are recoverable from a backup taken before
   the migration, not that any code preserved them.
3. **Empty in production** - the table holds no authored rows. Legitimate, and the
   most common case for a young model; it is a claim about production that has to be
   *checked* against production, not assumed from a dev database.

The failure mode this ADR exists to stop is (3) assumed when it is really (1), which
is indistinguishable from a correct removal by reading the diff alone. Hence the
declaration: the classifier can mechanically confirm that a `migrated` claim really
does carry a `RunPython`, but "is this data worth keeping" is a human judgment and
the gate's job is to force it to be stated and reviewed, never to compute it.

## Amendment, 2026-09-04: the backfill goes in its own migration

The original wording said "a `RunPython` in the *same* migration," and #3617's
`0220_upbringings` followed it literally: a backfill that wrote `OriginTemplate`
rows, then an `AddConstraint` on that same table. Django runs one migration in one
transaction; PostgreSQL queues a deferred FK trigger event for every row a
transaction writes and refuses `ALTER TABLE` on a table with events still pending.
The deploy died on

```
psycopg.errors.ObjectInUse: cannot ALTER TABLE "arxii_origintemplate"
because it has pending trigger events
```

after `migrate --noinput` had already applied 0213-0219, leaving production on a
release whose code expected 0220's columns.

Nothing catches this before production. A freshly migrated test database has no
rows for the backfill to touch, so the trigger queue is empty and the `ALTER TABLE`
succeeds; CI was green. The bug is only reachable with authored data present -
which is to say, only on the one database this ADR exists to protect.

So the requirement is now structural, and it is not conditional on whether *this*
particular backfill looks like it writes enough rows to matter: **a migration is
schema-only or data-only, never both.** Where data has to move, use
expand/migrate/contract - add the new columns in one migration, copy in the next,
drop in a third - so every `ALTER TABLE` gets a transaction with an empty trigger
queue. Reverse migrations replay operations backwards, so schema-then-data is
broken running down exactly as data-then-schema is running up; both are rejected.
`tools/lint_migration_ddl_dml.py` (`migration-ddl-dml` pre-commit hook) enforces
it, and its grandfather list records the eight already-applied migrations that
mix the two and survived only because the rows they wrote happened to be absent.

The ADR's own gate is unchanged in substance: a restructure still must carry the
data across in the same PR, and the classifier can still confirm mechanically that
the claim is backed by a real `RunPython`. It now looks for that `RunPython` in an
adjacent migration rather than the same file.

And check first whether there is data to carry at all. 0220's backfill turned out
to be reading a column that held `True` on all 15 rows: a constant, not
information, and therefore a column default (`AddField(default=True,
preserve_default=False)`) rather than a data migration. A restructure backfill
that carries a constant is not a restructure.

This is not advisory. Deploy runs
`python -m django migrate --noinput` unattended on every converge
(`infra/ansible/roles/app_deploy/tasks/main.yml`), so **the merged migration is
itself the destructive act** - no operator stands between a merge and a dropped
production column, and the review of the diff is the only gate there is. The same
reasoning narrows "No Backwards Compatibility in Dev": it governs code, wire
formats and APIs, never a persisted column that holds authored rows.

**The one mechanical guard that exists is a net, not a gate.** `roles/app_deploy`
takes a verified local `pg_dump` immediately before `migrate`, gated on
`migrate --check` so code-only deploys pay nothing, and fails closed: a dump that
cannot be written, verified, or fitted on disk aborts the play with the migration
unapplied, and an unverified dump file is deleted rather than left looking
legitimate. It makes a destructive migration *recoverable*; it does not stop one.
It is deliberately the guard that does not depend on anyone having anticipated the
failure mode, which is why it was built before the classifier: a declaration gate
can only catch operation classes someone thought to enumerate.

The declaration itself is still enforced by review alone. The expand/contract
classifier that would check it mechanically is designed in
`docs/operations/observability-baseline.md` §4.5 and **not built** - that doc's
claim to the contrary, and a comment in `app_deploy` asserting the gate "lives in
the release-safety classifier upstream," were both corrected when this ADR landed.

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
> Related: ADR-0238 (the content repo is retired; the DB is the master copy),
> ADR-0201 (credited rows are frozen against loads), ADR-0140 (grid bundles are
> content snapshots, never live-game backups), ADR-0012 (PostgreSQL only)

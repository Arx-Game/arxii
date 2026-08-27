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

The consequence that governs every PR concerns the operations that actually destroy
information: **`RemoveField` and `DeleteModel`** (and a `RunSQL`/`RunPython` that
deletes). `RenameField`/`RenameModel` are *not* in scope here - the data survives the
rename intact - though they remain flagged on the separate old-code/new-schema
compatibility axis (`docs/operations/observability-baseline.md` §4.5), which is a
different concern from this ADR's.

A destructive operation on an authored-content table is exactly one of three things,
and the author must say which in the PR:

1. **Restructure** - the information survives in a different shape (split, merge,
   retarget). A `RunPython` in the *same* migration carries it across. Mandatory;
   this is the case ADR-0013 used to wave through.
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
> Related: ADR-0236 (the content repo is retired; the DB is the master copy),
> ADR-0201 (credited rows are frozen against loads), ADR-0140 (grid bundles are
> content snapshots, never live-game backups), ADR-0012 (PostgreSQL only)

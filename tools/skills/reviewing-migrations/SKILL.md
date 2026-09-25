---
name: reviewing-migrations
compatibility: polytoken
description: Use whenever a Django migration is generated, hand-written, edited or reviewed — immediately after `arx manage makemigrations`, before committing a branch that adds one, and when reviewing a PR whose diff touches `src/world/migrations/`. Covers the schema/data split that broke a production deploy, checking whether a backfill has anything to carry, ADR-0237 data disposition, and max_migration.txt collisions.
---

# Reviewing Migrations

`migrate --noinput` runs unattended on every production converge
(`infra/ansible/roles/app_deploy/tasks/main.yml`). **The merged migration is
itself the act** — no operator stands between the merge queue and the
production database, and PR review is the only gate there is. A migration that
CI passes is not a migration that works: CI runs against a database with no
authored rows, and the failures that matter are the data-dependent ones.

Read the generated file. Every time. `makemigrations` writes what the model
state implies, not what is safe to run.

## 1. Schema-only or data-only. Never both.

**This is the one that broke a deploy** (2026-09-04, `0220_upbringings`).

Django runs one migration in one transaction. PostgreSQL queues a deferred FK
trigger event for every row a transaction writes, and refuses `ALTER TABLE` on
a table that still has events pending:

```
psycopg.errors.ObjectInUse: cannot ALTER TABLE "arxii_origintemplate"
because it has pending trigger events
```

So a `RunPython` that writes rows, followed by *any* schema operation, aborts —
after `migrate` has already applied the earlier migrations in the plan, leaving
production on a release whose code expects columns that do not exist.

It passes every local run and every CI run, because a freshly migrated database
has no rows for the data operation to touch, so the trigger queue is empty and
the `ALTER TABLE` succeeds. **The bug is only reachable with authored data
present** — that is, only on production.

Reverse migrations replay operations backwards, so schema-then-data is broken
running down exactly as data-then-schema is running up. Both are rejected.

**Where data has to move, use expand/migrate/contract:** add the new columns in
one migration, copy in the next, drop in a third. Every `ALTER TABLE` then gets
a transaction with an empty trigger queue.

`tools/lint_migration_ddl_dml.py` (`migration-ddl-dml` pre-commit hook) enforces
this. **Its grandfather list is closed.** Those eight entries are already applied
to production and can no longer be restructured; every one of them survived by
luck, because the rows it wrote happened to be absent. A new violation gets
split, never listed.

## 2. Check whether the backfill carries anything at all

Before writing a `RunPython`, look at what the column actually holds. **A column
that holds the same value on every row is a constant, not information** — it is
an `AddField(default=<that value>, preserve_default=False)`, which is pure DDL,
not a data migration.

`arxiidev` on the `db` host is a dump of production. Query it:

```bash
PGPASSWORD=arxii psql -h db -U arxii -d arxiidev \
  -c "select the_column, count(*) from the_table group by 1"
```

`0220_upbringings` shipped a backfill that read `Beginnings.family_known`,
which was `True` on all 15 rows. It carried a constant, and cost a deploy.

Two further traps this check catches:

- **A `get_or_create` in a migration is seed data**, which the repo bans
  (`tools/check_migration_seed_data.py`). Content rows belong in the admin or
  the seeds path.
- **Rows the migration *invents*** — creating a starter row for every parent
  that has none — is authoring, not migrating. A missing must-exist content row
  gets a dashboard sentinel and a human author, never migration logic.

## 3. Declare the data disposition for every destructive operation

Per ADR-0237, a `RemoveField`/`DeleteModel` on an **authored-content** table is
exactly one of three things, stated in the PR body:

1. **Restructure** — the data survives in a different shape. A `RunPython`
   carries it across, in the same PR and its own migration (rule 1).
2. **Deliberate discard** — stated and signed off; recoverable only from the
   pre-migrate `pg_dump`.
3. **Empty in production** — a claim about *production*, checked against the
   dump above, never assumed from a dev database.

`RenameField` is not data loss. Alpha play-state tables (characters, sheets, XP,
scenes, encounters) need none of this.

## 4. Check `max_migration.txt` against main's tip before enqueueing

Since #2906 there is exactly one sentinel repo-wide
(`src/world/migrations/max_migration.txt`), so **any two migration-bearing PRs
collide**. Compare against main's tip before enqueueing; fix a collision with
`arx manage rebase_migration arxii` (resolve the sentinel to main's tip first),
push, re-enqueue. **Never hand-renumber.**

A chain-regeneration PR (ADR-0276, `just regenerate-migrations`) has one more
gate: **the commit it was cut from must already be deployed to production.** Its
`_generations.py` snapshots every migration on `main` at the cut as the outgoing
generation; one production has not recorded makes that generation partially
recorded, and the `migrate` guard refuses the deploy (2026-09-06, `227 of 228`).
Compare `COMMITS[N]` in `src/world/migrations/_generations.py` against the last
successful "Stand up infra" run:

```bash
gh run list --workflow=standup.yml --status success --limit 1 --json headSha --jq '.[0].headSha'
git merge-base --is-ancestor <COMMITS[N]> <that sha> && echo deployed
```

If it is not an ancestor, press the button before enqueueing. If the deploy has
already failed, recovery is two presses of the button's `ref` input
(`infra/README.md`, "Recovering a guard-refused database").

## 5. Prove it against real data

CI proves the migration runs on an empty database. That is the case that cannot
fail. To prove the case that can, run it against a copy with rows in it:

Clone the dump into a scratch database and migrate *that*. Do not build one
from scratch - replaying the whole history takes hours, and the empty database
it produces is the case that cannot fail anyway.

```bash
export PGPASSWORD=arxii
psql -h db -U arxii -d postgres -c "DROP DATABASE IF EXISTS arx_migcheck"
psql -h db -U arxii -d postgres -c "CREATE DATABASE arx_migcheck"
pg_dump -h db -U arxii -d arxiidev --no-owner --no-privileges \
  | psql -h db -U arxii -d arx_migcheck -q -v ON_ERROR_STOP=1

cd src && DATABASE_URL='postgres://arxii:arxii@db:5432/arx_migcheck' \
  DJANGO_SETTINGS_MODULE=server.conf.settings \
  ../.venv/bin/python -m django migrate --noinput arxii
```

`pg_dump` reads only, so the dump itself never touches `arxiidev`. A failed
migration rolls back, so the scratch database stays on the previous migration
and you can re-run after a fix - which makes it cheap to run the *old* version
first and watch it fail, then the fix and watch it pass. Do both: a migration
you have only seen succeed is a migration whose test you have not verified.

Then check the resulting rows, not just the exit code: the constraint exists,
the column is gone, the row count is what you expected, and
`migrate <previous_migration>` reverses cleanly.

Never migrate `arxiidev` itself, and never point any of this at production.
`CREATE DATABASE ... TEMPLATE arxiidev` fails whenever anything holds a
connection to it; the `pg_dump` pipe above has no such problem.

### Do not test a backfill by replaying the migration graph

A unit test that rewinds the schema with `MigrationExecutor` to the migration
before a backfill, builds rows through historical models, and migrates forward
again costs the whole chain's DDL twice per test, and that cost grows with every
migration anyone adds afterwards. `test_offers_migration.py` (#3684) did this for
0110: by 2026-09-24 its two tests took 1043 s and 992 s on `main`, 34 minutes of a
shard budgeted at ~344 s, and on a branch seven migrations further along they died
with `MemoryError` and hung the parallel runner until the 4-hour cancel (#3998). It
was also doomed by design: ADR-0276 regenerates the chain from a deployed commit,
which deletes the very nodes such a test names.

Prove a backfill the way section 5 says, against a database with rows in it, and
keep any unit test on the backfill's own function: call `forwards(apps, editor)`
with `django.apps.apps` and factory rows when the source models still exist, or
skip the unit test when the same PR's contract migration removes them. A test
that still needs historical models is a sign the expand/migrate/contract split
put the contract too early.

## 6. A constraint on a column added in the same migration

`AddField(null=True)` leaves every existing row NULL. A CHECK constraint on that
column alone can never fail - SQL treats a NULL check as satisfied - but a CHECK
that ties it to a column that already existed ("both null or both set") is
violated by every row that has the old column set, and PostgreSQL validates the
whole table at `ADD CONSTRAINT`. `0149_partitioned_metadata_integrity` added
`posesubmission.timestamp` and, in the same migration, a check pairing it with
`interaction`; production had one submission with an interaction, and the
2026-09-24 deploy died with:

```
IntegrityError: check constraint "pose_submission_interaction_timestamp_pair"
of relation "arxii_posesubmission" is violated by some row
```

CI cannot see this (no rows). The fix is the same expand/backfill/contract
sequence as section 1: the column in one migration, a data migration that fills
it from the row it denormalizes, the constraint in a third. A column added with a
`default` and `preserve_default=False` is filled on every row and needs none of
this. `tools/lint_migration_constraint_on_new_column.py` (the
`migration-constraint-on-new-column` hook) flags the shape; its grandfather list
is closed.

## Checklist

- [ ] Read every operation in the generated file
- [ ] No `RunPython`/`RunSQL` sharing a migration with a schema operation
- [ ] No CHECK constraint pairing a column added nullable in this migration with an old one
- [ ] Backfill (if any) carries real per-row information, verified against the dump
- [ ] No `create`/`get_or_create` of content rows
- [ ] Every `RemoveField`/`DeleteModel` on authored content has a stated disposition
- [ ] `max_migration.txt` matches main's tip
- [ ] Regeneration PR only: `COMMITS[N]` is an ancestor of the last successful deploy
- [ ] Ran against a database that has rows in the affected tables

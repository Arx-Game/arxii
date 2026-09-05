# ADR-0272: The migration chain regenerates to its floor and crosses generations with `replaces`

**Date:** 2026-09-05
**Status:** Accepted (amends ADR-0195; relates to ADR-0083, ADR-0237)
**Issue:** #3656

## Decision

The `arxii` migration chain is periodically **regenerated** from model state by
`arx manage squashmigrations arxii` (`just regenerate-migrations`), a
`core_management` command that replaces Django's `squashmigrations` outright, the
same override mechanism `makemigrations` already uses (#2885; it displaces
django-linear-migrations' subclass too). Each regeneration is a numbered
*generation*: its files are stamped (`NNNN_g<N>_initial`, `NNNN_g<N>_part_<K>`,
then three tails), every one carries `replaces` naming the whole previous
generation (imported from the generated `world/migrations/_generations.py`), and
the chain it produces is the schema's floor: one `CreateModel` per model in
topological order with every non-cycle FK inlined
(`tools/optimize_initial_migration.py`), auto-through M2M fields inlined the same
way (`CreateModel` creates the through table itself), each model's constraints,
indexes and `unique_together` folded into its `CreateModel`, only the back edges
of each FK cycle and the explicit-`through` M2Ms deferred (14 + 19 today, where
deferring every intra-cycle edge would have cost 82), and three rendered tails for the raw SQL both
schema paths share (`tools/migration_tails.py`: partition rewrite, the
database-only re-add of the columns the frozen partition SQL omits, materialized
views). Every `RunPython` of the outgoing generation is dropped; nothing in a
generated chain produces rows.

Every chunk made only of `CreateModel`s subclasses
`core_management.batched_migration.BatchedCreateModelMigration`, which runs the
chunk's `state_forwards` without rendered apps, renders the project state once,
and only then runs the DDL. Stock `Migration.apply` re-renders the transitive
closure of related models after every `CreateModel`; profiled on 2026-09-05 that
was 248 of 259 seconds of a twelve-chunk partial replay, and the same twelve
chunks under the batched base took 29 seconds. This, not the operation count, is
where a fresh replay's time goes on a schema this connected.

Databases cross generations with Django's own `replaces` semantics: a database
that has the previous generation fully recorded treats the new one as applied and
records it on its next real `migrate`, which the deploy role runs unconditionally
on every deploy. The generated files *partition* the previous generation
(`replaced_slice(k, total)` in `_generations.py`, one interleaved slice per file)
rather than each replacing all of it: Django records a replacing migration's
`replaces` when it applies it, not its own name, so a shared list would insert
every old name once per file (23,484 recorder rows on the first attempt). No `--fake`, no row deletion, no schema touch. A `migrate`
override in `core_management` refuses the two states Django handles badly, before
any schema is touched: a partially recorded previous generation (Django would
silently apply nothing and exit 0) and a skipped generation (Django would try to
`CREATE` every table). It names the last commit at the missing generation
(`COMMITS` in `_generations.py`) as the recovery. A lint
(`tools/lint_migration_generations.py`) refuses any migration whose name or
dependency belongs to an earlier generation, since production records every
applied name forever and would skip a repeat silently, and any module outside
the package that still names a dropped migration (a test of a dropped
`RunPython` has no subject left; two such tests went with generation 1).

**Trigger:** regenerate when the nightly replay workflow reports more than 30
minutes (it now records wall time and emits a warning past that), or before any
release that will replay on a fresh environment. A regeneration PR is
regenerated on the tip of `main` in a fresh worktree before it is enqueued, never
rebased: a migration that lands after the branch was cut would depend on a node
the branch deleted. Its review unit is the inliner's `--check` counts, the three
tails read in full, the drop report, and the `just verify-regeneration` output,
not the hundred generated chunk files.

## Why

Replay cost is `O(operations x models-in-state)` (ADR-0195) and the operation
count only climbs: 27 minutes on 2026-08-04, 48 minutes and 2.6 GB on 2026-09-05,
about 20 minutes a month, almost all of it relational `AddField`s that a fresh
chain expresses inside `CreateModel`. ADR-0083 and ADR-0195 both rejected
periodic squashing, and both rejections rested on the pre-collapse 46-app
dependency cycle that forced 1,153 deferred FKs regardless of squashing. The
collapse removed that cycle; the floor is now the schema's own 49 cycle edges, so
regeneration is structural, not transitory. That reverses ADR-0195's rejected
alternative on this one point and nothing else in it.

Django's `squashmigrations` cannot do this, for reasons in its own source. Its
optimizer merges an operation into a later one only if every operation between
them can be "optimized through"; `CreateModel(A)` reports that it references `A`,
so a deferred `AddField(B.fk -> A)` can never fold back past its target's
`CreateModel`: the optimizer never reorders models, and the deferred-FK count
after a squash is whatever order the chain already had. `Operation.references_model`
returns `True` "if in doubt" and neither `IndexOperation` nor `AddConstraint`
overrides it, so any of the 831 index/constraint operations between two
operations blocks the fold, and 554 of them sit in one block between the initial
models and every incremental. Measured on the 2026-09-05 chain: 531 s to produce
one 2 MB file with 3% fewer operations (2,682 of ~2,770) that did not compile
(`SyntaxError: invalid decimal literal` at a `RunPython` reference through a
digit-leading module), consistent with #1801's pre-collapse measurement in
ADR-0083. What is kept from Django is the half that works: `replaces`, the loader,
the executor's `check_replacements`, the writer, and the custom `makemigrations`
that produces the minimal fresh initial.

**Rejected:** (a) skipping the per-operation `ProjectState.clone` in
`Migration.apply` (#2978): measured 1.4% slower with a higher peak, and its
37-minute "baseline" was a run OOM-killed at migration 105; the clone was never
the cost, the closure re-render was, and the batched base removes that for the
one operation shape where no intermediate render is observable.
(b) Moving the raw SQL out of migrations into a deploy-time step: changes
production's schema contract (ADR-0083) for a modest simplification. (c) A hand
`--fake` on production: a manual step against the only copy of the content
(ADR-0237) where Django already has a mechanism that touches nothing. (d) A
seed-twin check for row-creating `RunPython`: row creation inside a migration is
already forbidden by ADR-0013 and refused by `tools/check_migration_seed_data.py`;
the drop report lists what it drops, and seed rows keep coming from the seed
functions.

**Measured, 2026-09-05, same dev box, nothing else running** (`just
verify-regeneration`, empty `compare_schemas` diff in every case):

| chain | full replay | peak RSS | files | operations |
|---|---|---|---|---|
| generation 1 (stock `Migration.apply`) | 48m 06s | 2.6 GB | 227 | ~2,770 |
| generation 2, regenerated only | 49m 43s | 418 MB | 103 | ~1,250 |
| generation 2 + batched chunks | 13m 55s | 415 MB | 103 | ~1,250 |
| generation 2 + batched chunks + M2M inlining | **7m 03s** | 433 MB | 103 | ~1,150 |

The second row is the lesson: operation count alone bought nothing on wall
time, because the closure re-render dominated. About four of the remaining seven
minutes are Django's post-migrate work (content types and permissions for 1,100
models), which every schema-construction path pays and this ADR does not touch.

## Consequences

- A dev database behind the old tip must `migrate` to it before pulling a
  regeneration; the guard says so and names the commit to visit
  (`ARX_SKIP_GENERATION_GUARD=1` bypasses it for someone who knows better).
- Generation-1 rows stay in every `django_migrations` forever; `migrate --prune`
  exists if anyone ever wants them gone. They are harmless.
- `GENERATIONS` in `_generations.py` grows by one list per regeneration and is
  never trimmed: generation N+1's `replaces` needs N, and the guard needs all of
  them to name where a stranded database stands. `_generations.py` is generated
  and underscore-prefixed (Django's loader imports every non-underscore module of
  a migrations package as a migration).
- Any two migration-bearing PRs still collide on `max_migration.txt` (ADR-0195);
  a regeneration PR collides with every one of them, which is why it is
  regenerated on the tip of `main` rather than rebased.
- The filename-keyed lint lists (`tools/lint_migration_ddl_dml.py`,
  `tools/check_migration_seed_data.py`) lose the entries whose files a
  regeneration deletes; their "nothing may be added" rule stands.

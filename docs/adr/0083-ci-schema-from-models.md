# CI and test databases build schema from model state; migration replay runs nightly only

**Decision:** CI and local test databases (both the SQLite fast tier and the Postgres parity
tier) build their schema directly from current model state via `tools/build_schema.py` —
`migrate --run-syncdb` plus the standalone partition/composite-FK/materialized-view SQL and the
idempotent seed functions that replaced the RunPython seed migrations (ADR-0013) — instead of
replaying the full migration chain. Full migration replay (`arx manage migrate` from an empty
database) now runs only in a nightly scheduled workflow
(`.github/workflows/nightly-migration-replay.yml`); per-PR CI keeps a `makemigrations`-based
drift gate (`tools/check_missing_migrations.py`, scoped to first-party apps) so a model change
without a matching migration still fails fast, without paying for full replay on every push.

**Why:** measured 12.5-14 minutes per backend shard spent on migration replay, roughly 99% of it
Python-side migration-state re-rendering rather than real DDL — each `AddField`-class operation
costs about 0.5-0.6s regardless of what it actually does to the schema, and cross-app FK cycles
alone add up to roughly 1,200 of these AddField/AlterField/AddIndex-class operations within the
chain's ~1,860-1,940 total. Squashing the migration chain (the approach
`docs/architecture/migration-nuke-and-rebuild-plan.md` proposed) doesn't fix this: a direct
squash/reset measurement (PR #1801) cut the chain from 507 files to 123 but only trimmed the op
count from ~1,940 to ~1,860, with migrate time unchanged to slightly worse — the cross-app FK
cycles force the same AddField wiring regardless of how many files it's spread across, so op
count barely moves.

**Rejected:** (a) squash/reset chains — measured directly (above) and found no meaningful
wall-clock improvement since the op count survives a squash; PR #1801 was closed for this
reason. (b) CI schema caching keyed on migration-file hashes — GitHub Actions' `restore-keys`
fallback means an exact-key cache miss (e.g. any PR that adds a migration file, changing the
aggregate hash) falls back to the nearest prior partial-match cache, which holds a schema built
from an earlier version of a same-named-but-since-edited migration; Django's migration recorder
sees that name as already applied and silently skips the edited version, so the cache goes stale
undetected, and a merge-queue history reset forces a full rebuild regardless since the cache key
changes every time. (c) merging all apps into one mega-app — high development churn on a single
giant app, and Evennia's own vendored migration chain remains in the replay path either way.
**Trade-offs:** per-PR CI no longer exercises real migration replay — the nightly workflow
covers that instead, an acceptable gap pre-production given ADR-0013's no-data-migration rule
(no production data at risk if replay silently regresses between nightly runs). The drift gate
needs a reachable Postgres even though it is nominally a static check: the vendored
`evennia/objects/migrations/0007_objectdb_db_account.py` calls `connection.cursor()` at
module-import time, so any code path that loads the migration graph — `MigrationLoader`,
`makemigrations --check`, `showmigrations` — needs a live DB connection even for what looks like
an offline check (see `docs/evennia-quirks.md`). At production launch, migration validation must
move into the deploy pipeline itself (restore the latest prod backup to staging, migrate,
smoke-test before deploy) — nightly replay against a synthetic dev-model database does not
substitute for that, and this is recorded here as the explicit launch-era follow-through. Separately,
a plain `arx manage migrate`-built environment does not invoke the idempotent seed functions
(`world/progression/seeds.py`, `world/magic/seeds_soul_tether.py`) either — only
`tools/build_schema.py` does — so a deploy pipeline must call them explicitly, or lookups like
`scenes/action_services._get_social_engagement_category()` hard-fail on the missing row.

**Update (#2977):** the devcontainer's `post-create.sh` joined this path too, closing
the last environment still replaying the full chain on every fresh build (measured
~5-9 minutes via `build_schema.py` versus ~27-29 minutes for `arx manage migrate`
replay on this box). Unlike a throwaway test database, a devcontainer database is
long-lived, so `build_schema.py` alone isn't enough - it disables migrations while it
runs and leaves no `django_migrations` table at all, which would make the next real
`arx manage migrate` try to recreate every table from scratch. `post-create.sh`
follows it with `arx manage migrate --fake`, which records every migration in the
chain as applied without touching the schema, so a later incremental migration
applies normally instead of colliding. `post-create.sh` also refuses to bootstrap
into a database that is non-empty and wasn't built by this path (detect and refuse,
never auto-drop - see `docs/devcontainer-setup.md`).

**Update (#2982):** splitting per-PR CI off the migration chain meant nothing per-PR
inspected the migrated schema, and the nightly workflow's drift gate compares models to
migrations rather than to the resulting schema - so a lost `RunSQL` (#2906's squash
silently dropped the `arxii_interaction` partition rewrite) was invisible to every gate
at once. Per-PR coverage is now the structural `standalone-sql-wiring` hook
(`tools/check_standalone_sql_wiring.py`); nightly coverage is a full `pg_catalog` diff
between the two paths (`tools/compare_schemas.py`).

**Update (2026-08-23, CI speed-up):** `build_schema.py`'s 5-6.5 minute "Build schema"
step was ~98% Django's `migrate` command running the migration **autodetector +
optimizer** after syncdb - at `verbosity >= 1` it diffs the (empty, migrations-disabled)
graph against all ~1,200 models to print the "changes not yet reflected in a migration"
hint, feeding ~1,200 `CreateModel` ops to an O(n^2) optimizer (187M `reduce()` calls).
The real DDL + SQL files + seeds take ~30s. `build_schema.py` now calls `migrate` with
`verbosity=0`; the SQLite tier never hit this because Django's `create_test_db` passes
`verbosity - 1`. The per-job fixed cost is now small enough that caching a `pg_dump` of
the built schema (rejected alternative (b) above) is not worth its staleness risk.

> Status: accepted · Source: CI-speedup branch, task 5 · Related: ADR-0013 (schema-only
> migrations pre-production), ADR-0021 (merge queue + single-leaf migration guard)

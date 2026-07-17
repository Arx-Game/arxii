# Evennia Quirks

Evennia-specific quirks and integration patterns. Consult when touching migrations, makemigrations, or evennia_extensions.

### Evennia makemigrations Solution
**FIXED: Custom makemigrations command prevents phantom Evennia library migrations**

We have a custom `makemigrations` command that prevents Django from creating problematic migrations in Evennia's library when our models have ForeignKeys to Evennia models.

```bash
# SAFE - our custom command prevents phantom Evennia migrations
arx manage makemigrations

# Still works - specify specific apps when needed  
arx manage makemigrations traits
```

**Details**: See `core_management/CLAUDE.md` for full technical documentation of the solution.

### makemigrations in a fresh worktree (no local dev DB)

`arx manage makemigrations <app>` can fail in a freshly created worktree: the
Evennia launcher requires `Account#1` (superuser) to exist before running *any*
command — even schema-only ones — and worktrees don't carry over the main
checkout's untracked local DB/`.env`, so `DATABASE_URL` falls back to the shared
devcontainer Postgres (which may carry an unrelated `InconsistentMigrationHistory`).

**Workaround (never touch the main dev DB):** create a disposable scratch
Postgres DB on the same `db` host, run `python -m django migrate` and then
`python -m django makemigrations <app>` directly against it (bypassing the
`evennia` launcher's superuser pre-check), copy the generated migration file,
and drop the scratch DB. Often the worktree's own `.venv` + SQLite fallback also
works — try `arx manage makemigrations <app>` first; reach for the scratch DB
only when the launcher blocks it.

### Evennia Integration Strategy
- **Use Evennia Models**: Keep using Evennia's Account, ObjectDB, etc. - don't reinvent the wheel
- **Extend via evennia_extensions**: Use the evennia_extensions app pattern for data storage that extends Evennia models
- **No Attributes**: Replace all Evennia attribute usage with proper Django models through evennia_extensions
- **Item Data System**: Consider reusing ArxI's item_data descriptor system for routing data to different storage models

### Migration Management for New Apps
**IMPORTANT: When working on a new app, avoid multiple migrations during development**
django_notes.md gives a more in-depth explanation of this strategy.

### loaddata Cannot UPDATE SharedMemoryModel Rows (#946)

**Natural-key `loaddata` INSERTS fine but silently no-ops UPDATES on every
SharedMemoryModel** (= every concrete model in this repo). Django's
deserializer resolves the existing pk via `get_by_natural_key` — which loads
the row into the idmapper identity map — then constructs `Model(**data)` with
that pk, and the identity map intercepts construction-by-pk and returns the
**cached old instance**, discarding the fixture's new field values. No error
is raised. Verified cross-process during #944; flushing the cache around
`loaddata` doesn't help because `get_by_natural_key` itself re-primes the
cache mid-deserialization.

**Rules:**

- Fixture JSON is valid for **fresh-database seeding only** (pure inserts).
- Never rely on re-loading an edited fixture to update existing rows — use an
  explicit upsert: `core_management.content_fixtures.load_entries` (the #944
  content pipeline, `just load-content`) or `update_or_create` keyed on the
  natural fields.
- Don't build cache-flush workarounds; upsert is the standing answer (the
  identity map is load-bearing — see the `sharedmemory-model` skill).

**Grid bundles follow the same upsert discipline, sequenced after content
fixtures (#2436/#2448):** `core_management.grid_import.load_grid_bundles()`
upserts areas/rooms/exits by their permanent `slug`/`fixture_key` identity,
never `loaddata`. Because a content fixture (e.g. `StartingArea`) can name a
room by natural key before the grid bundle that creates it has loaded, the
combined driver `core_management.content_fixtures.load_world_content()` loads
content fixtures first with an unresolved-natural-key FK **deferred** (not
fatal), then the grid bundles, then retries the deferred entries — see
`docs/systems/INDEX.md`'s "Grid content export/import" entry and ADR-0137.

### Migration-number collisions on sync-with-main

When `sync-with-main.sh` conflicts on `migrations/max_migration.txt` for an app, both branches added an independent field-add migration at the same sequence number. Resolve by keeping HEAD's stable and renumbering main's:

1. `git mv` main's colliding migration to the next number.
2. Edit its `dependencies` to chain on HEAD's migration (the one that kept the colliding number), not the shared parent.
3. Write `max_migration.txt` to the new higher number.
4. **Check for inbound cross-app deps** — grep the whole `src/` tree for the old migration's name; another app's migration may depend on it (e.g. `achievements/0004` depending on `mechanics/0006_...` after `mechanics` got renumbered to `0007`). Miss this and `migrate --plan` raises `NodeNotFound` on CI only.
5. Verify with `uv run arx manage migrate --plan` (grep for error/NodeNotFound/inconsistent) — a clean linear plan is the green light. `makemigrations --check --dry-run` reporting phantom Evennia-**library** migrations (under `.venv/site-packages/evennia/...`) is a known false-positive for this repo's own apps — ignore those.

`models.py` content conflicts in the same app during the same sync are usually both-keep (disjoint field/branch additions from each side), not competing edits.

If the merge commit itself times out on pre-commit (ty/ruff over hundreds of files), complete with `git commit --no-verify` and then run `uv run pre-commit run --all-files` explicitly before push — `--no-verify` skips `ty` and the custom linters, so they must be re-run by hand.

### Phantom `objects` migration dependency (CI-only, invisible locally)

**Symptom:** `NodeNotFoundError: Migration <app>.NNNN dependencies reference nonexistent parent node ('objects', '0014_defaultobject_...')`. Backend shards and `api-types-drift` build their schema from model state (`tools/build_schema.py`, migrations disabled entirely) so they don't hit this; it now surfaces at the `ty` job's "Check migrations match models" step, `pre-commit`'s "Check Django migrations" hook, and the nightly migration-replay workflow's migrate/check steps. Local SQLite tests pass because the dev venv happens to have the phantom migration.

**Cause:** `.venv/.../evennia/objects/migrations/0012-0014` are venv-only phantoms (not git-tracked — a stray `makemigrations` once generated them into the Evennia library dir). Regenerating a project migration can bake a dependency on the latest *local* phantom objects migration even though the `arx manage` wrapper suppresses phantom migration *files*. CI's clean Evennia install only ships `objects` migrations up to **0013**, so the dependency dangles.

**Fix:** find the canonical CI-present dep with `git grep "('objects'," origin/main` (currently `0013_defaultobject_alter_objectdb_id_defaultcharacter_and_more`) and repoint the bad dependency line to it — a one-line edit in the new migration's `dependencies`.

**Sibling failure mode, same root cause:** adding migrations perturbs the global topological sort, which can expose an *existing* migration's missing cross-app dependency — e.g. a `RunSQL` step in one app's migration reading a column that another app's later migration adds, without an explicit dependency between them. The ordering held by luck before; any new migration can break it. Rule: a migration whose `RunSQL` reads another app's table/column must explicitly depend on the migration that creates it.

### Vendored objects migration opens a real DB connection at import time

`evennia/objects/migrations/0007_objectdb_db_account.py` (vendored, not
git-tracked in this repo) calls `connection.cursor()` at **module-import
time**, not inside its migration `RunPython`/`RunSQL` operations. Any code
path that loads Django's migration graph — `MigrationLoader`,
`makemigrations` (including `--check --dry-run`), `showmigrations`,
`tools/check_missing_migrations.py` — imports every migration module on disk
to build the dependency graph, which means it needs a **reachable** database
even when the check is nominally offline/static. There's no way to make this
check truly DB-free without patching Evennia's vendored migration; CI jobs
that only run `ty`/`makemigrations --check` still need a `postgres:` service
container for this reason (see the `ty` job in `.github/workflows/ci.yml` and
the nightly migration-replay workflow). See ADR-0083 for how this interacts
with the CI schema-from-models decision.

### A new standalone-SQL migration must be mirrored into `tools/build_schema.py`

Per-PR CI and the local PG parity tier (`just test-parity`) build their schema from current
model state via `tools/build_schema.py`, not migration replay (ADR-0083); the SQLite fast tier
(`just test-fast`) builds from model state too (Django syncdb) but never runs `build_schema.py`,
so it never has these SQL-defined objects at all — its PG-only helpers are no-op'd instead. See
the note above on the vendored `objects` migration for how ADR-0083 interacts with the drift
gate. `build_schema.py`
applies exactly the standalone SQL files listed in its `SQL_FILES` constant (the partition
rewrite, composite FKs, materialized views) plus the idempotent seed functions; it does not
replay migrations, so it has no way to discover a new standalone SQL artifact on its own.

**Rule: a migration that adds `RunSQL` DDL for a materialized view, a range partition, a custom
constraint, or any other object that can't be expressed as a plain model field must add the
matching `.sql` file to `SQL_FILES` in `tools/build_schema.py`, in the same PR.** Nightly full
migration replay (`nightly-migration-replay.yml`) exercises the real migration and will build the
object correctly; CI and local test/dev DBs built via `build_schema.py` will not, and — unless a
test actually exercises that object — the omission fails silently rather than loudly: no error,
just an object that's simply never there in any schema-from-models DB.

### Fuzzy/partial object search is broken on PostgreSQL

Evennia's `ObjectDB.objects.get_objs_with_key_or_alias(exact=False)` (the path `caller.search(name)` takes when there's no exact match) builds a `\b`-anchored regex (`r"\bBo.*"` for "Bo") and queries `db_key__iregex`. **On PostgreSQL, `\b` is a literal backspace character (POSIX BRE/ERE), not a word boundary** — word boundaries are a PCRE/Python-`re` extension. So the regex never matches a real key like "Bob" on Postgres. On the SQLite tier, Evennia registers a Python `re`-based `REGEXP` function where `\b` IS a word boundary, so partial matching works there and the divergence is invisible until CI's Postgres shard runs.

This is an Evennia library bug, not repo code — don't try to "fix" it in the command layer. Any telnet command or test relying on partial/prefix name resolution will pass locally and fail on PG. Resolve targets by **full name** (`db_key__iexact`, the exact-match path) instead, and don't write tests asserting partial-name search works.

### Partitioned `scenes_interaction` traps (Postgres-only, invisible on SQLite)

`scenes_interaction` is a Postgres range-partitioned table built by raw SQL at `scenes/0004_partition_interaction`. The `check_partition_sql_drift.py` pre-commit hook forces the partition SQL's CREATE TABLE + INSERT column lists to match the current `Interaction` model. Two traps:

1. **A new column that can only be added by a later migration** (e.g. an FK to a model created after the partition migration) does not exist on the pre-partition `_old` table, so the partition SQL's `INSERT ... SELECT <col> ... FROM _old` fails with `UndefinedColumn`. All backend shards + `api-types-drift` fail at the `migrate` step; the SQLite fast tier never runs the partition SQL, so it's invisible locally. Fix: keep the post-partition column OUT of both partition SQL files (forward and reverse) so they represent the schema *at partition time*; the late `AddField` cascades via `ALTER TABLE` to all partitions. Add the column name to the `POST_PARTITION_COLUMNS` exclusion set in `tools/check_partition_sql_drift.py`.
2. **A new FK on another model referencing `scenes.Interaction`** fails Postgres `migrate` with `InvalidForeignKey: there is no unique constraint matching given keys` — a FK to a partitioned table can't reference the plain PK. Counter-intuitively, "a FK *to* the partitioned table is the safe direction" is wrong on PG. Fix: add `db_constraint=False` to the field (mirror `SceneActionRequest.result_interaction`) — the ORM relation is unaffected, and `db_constraint=False` fields don't trip the drift hook.

Always verify a migration touching `Interaction` on a real throwaway Postgres DB (host `db`, user/pass `arxii`/`arxii`) before pushing.

**Related runtime trap (not migration-time):** annotating a per-row aggregate onto the partitioned `Interaction` queryset — e.g. `.annotate(reaction_count=Count("reactions"))` — 500s on Postgres (the full-row SELECT forces a `GROUP BY` PG rejects, since PG's real PK is composite `(id, timestamp)` while Django groups by `id` alone) but passes the SQLite fast tier, which doesn't enforce `GROUP BY` strictness. Fix: don't aggregate on the partitioned model directly — pull visible row ids with `.values_list("pk", "timestamp")`, aggregate counts on the **child** table grouped by its plain FK column, and rank in Python. Verify any reel/ranking/aggregate query touching a partitioned table with `just test-parity` on real Postgres before pushing.

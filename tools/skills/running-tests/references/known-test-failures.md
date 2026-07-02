# Known Test Failures & Situational Gotchas

Symptom-keyed reference for specific test failures — consult this when you hit one of these exact symptoms, not as general reading.

## Pre-existing SQLite-fast-tier failures (not your regression)

Two app-level patterns produce SQLite-tier errors that are pre-existing and PG-only — verify the failing test file is untouched by your branch before treating either as a regression, and lean on CI's Postgres shard as the real gate:

- **`world.areas.tests`** — ~15 "no such table: areas_areaclosure" errors. `AreaClosure` is `managed = False`, backed by a Postgres materialized view (`RunSQL` in `areas/migrations/0002_create_areaclosure_view.py`); SQLite can't create it. Run `arx test world.areas.positioning` instead (doesn't touch the view) — CI's PG shard covers the rest.
- **`world.magic` / `world.vitals` / `world.mechanics`** (and others) — ~29 `NotSupportedError: DISTINCT ON fields is not supported by this database backend`. Any test that calls `apply_condition` reaches `world/conditions/services.py::_build_bulk_context`'s PG-only `.distinct("condition_id")` — soul_tether, fury/berserk, soulfray, non_clash_strain, nonlethal_cap, plus the death/knockout consequence-pool tests. These are not `@tag("postgres")` but are effectively PG-only.

## Parallel-session Postgres test-DB contention

**Symptom:** "database is being accessed by other users" when two worktree sessions run Postgres tests concurrently — both default to `test_arxiidev`.

The `--sqlite` tier sidesteps this, but doesn't cover apps the fast tier excludes (`roster`, `character_sheets`, `magic`, `codex`, `areas`, `societies`). Fix — give the worktree its own DB (the worktree's `src/.env` is gitignored, so this never touches the shared dev DB):

1. Edit `src/.env`: `DATABASE_URL=postgres://arxii:arxii@db:5432/arxiidev_<N>` (Django loads `.env` with overwrite, so a shell env var alone is ignored).
2. `PGPASSWORD=arxii psql -h db -U arxii -d postgres -c "CREATE DATABASE arxiidev_<N> OWNER arxii;"`
3. `cd src && uv run arx manage migrate` — migrate the **base** DB first, or Evennia's test setup queries `server_serverconfig` on the default connection before the test DB exists.
4. Clone it: `psql ... -d postgres -c "CREATE DATABASE test_arxiidev_<N> TEMPLATE arxiidev_<N>;"`
5. Always run with `--keepdb`: `echo "no" | uv run arx test --keepdb <dotted.path>` (reuses the prebuilt DB and applies any new migrations, so it stays correct across syncs).

## `setUpTestData` + Evennia objects → `DbHolder` copy errors

**Symptom:** `copy.Error: un(deep)copyable object of type DbHolder`, but only in multi-app CI shard runs — the same test passes when its app runs alone.

Django deepcopies class-level test data per test, and Evennia objects (ObjectDB / RoomProfile / typeclassed rows) acquire un-deepcopyable typeclass internals once the full suite has loaded. Order-dependent: the idmapper identity map persists across the shard process, and a factory's `django_get_or_create` can return a contaminated cached instance from an earlier app's tests. Cost two CI rounds on PR #922 — reproduce with the exact shard app list from `.github/workflows/ci.yml`, not a solo run.

**Fix:** create Evennia fixtures in `setUp`, not `setUpTestData`. If the class does use `setUpTestData`, call `evennia.utils.idmapper.models.flush_cache()` at its top.

## `EvenniaTest` breaks in this repo

**Symptom:** `TypeError: ServerSession.at_login() missing ... 'account'` in `setUp`.

`evennia.utils.test_resources.EvenniaTest`'s session-login path hits the custom `accounts.py::at_post_login` and breaks. Use plain `django.test.TestCase` + `evennia_extensions.factories.CharacterFactory` instead (see `world/items/tests/test_handlers.py`) for any test needing a real character.

## Frontend: never run bare `pnpm test`

**Symptom:** a subagent told to "run pnpm test" hangs / gets killed without committing.

`pnpm test` is `vitest` in watch mode and never exits. Use `pnpm exec vitest run <path>` (or bare `pnpm exec vitest run` for everything). For the full frontend gate: `pnpm exec vitest run`, `pnpm typecheck`, `pnpm lint`, `pnpm build` (the build's `tsc -b` project-reference mode type-checks test files that `typecheck`/vitest miss).

## Stray `src/.venv` breaks `shard-coverage`

**Symptom:** the `shard-coverage` pre-commit hook fails, listing `.venv.*` dotted names as "backend apps not in any CI shard."

If any command was ever run as `cd src && uv run ...` (including the MODEL_MAP regen command, `uv run python tools/introspect_models.py`), `uv` creates a venv inside `src/`, and the hook rglobs its site-packages as unsharded Django apps.

**Fix:** `rm -rf src/.venv` (gitignored, safe) and always run `uv`/`just`/`arx` from the **worktree root**.

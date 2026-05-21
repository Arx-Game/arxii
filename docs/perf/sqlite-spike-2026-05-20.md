# SQLite spike — 2026-05-20

Branch: `feature/test-speedups`. Settings: `server.conf.sqlite_test_settings`
(SQLite in-memory, `MIGRATION_MODULES = _DisableMigrations()` so the schema
builds from current model state with no migration replay).

## Per-app results

| App | Tests | SQLite outcome | PG baseline | Speedup |
|---|---:|---|---:|---:|
| `world.missions` | 246 | **242 pass, 4 fail, 1 skipped** in **10.394s** | 18.841s | **45% faster** |

(More apps to follow as the spike expands.)

## Missions failure analysis

All 4 failures are **test-design issues, not SQLite incompatibilities**:

| Test | Assertion | Cause |
|---|---|---|
| `test_joint_per_attempt_does_not_emit_rewards` | `1 != 50` | Picks `line.amount` from queryset without `order_by` — SQLite returns insertion order, PG returns physical-storage order, so `lines[0]` differs |
| `test_joint_terminal_emits_rewards_once_on_holder_deed` | `[2, 3] != [1, 2]` | Compares character IDs directly. SQLite starts auto-increment IDs differently (no Account #1 / Limbo seed); the IDs differ but the test logic is correct |
| `test_branch_terminal_via_null_route_emits_authored_rewards` | `100 != 200` | Same first-row-from-queryset issue |
| `test_check_terminal_route_emits_authored_reward_line` | `100 != 750` | Same |

Fix shape: replace `lines[0].amount` with `sum(l.amount for l in lines)` or
`assertCountEqual([l.amount for l in lines], expected_amounts)`. Replace
`assertEqual(recipient_ids, [1, 2])` with `assertEqual(set(recipient_ids), {char.id for char in chars})`. These tests would also be flaky on PG with
different sequence states; the SQLite spike just surfaced the latent issue.

## Architecture

- **`src/server/conf/sqlite_test_settings.py`**: inherits from `test_settings`,
  overrides `DATABASES['default']` to SQLite `:memory:`, sets
  `MIGRATION_MODULES = _DisableMigrations()` so the test DB schema builds from
  current model state.
- **`src/sqlite_test_settings.py`**: Windows parallel-worker shim
  (`from server.conf.sqlite_test_settings import *`), mirrors the existing
  `src/test_settings.py` pattern.
- **`src/cli/arx.py`**: `--sqlite` flag switches `--settings=sqlite_test_settings`.
- **`src/core_management/migration_utils.py`**: `PostgresOnlyRunSQL` subclass
  that skips on non-PG backends. Defensive — not strictly required when
  `MIGRATION_MODULES = _DisableMigrations()` skips ALL migrations on SQLite,
  but documents intent and keeps the PG-only RunSQL operations honest.

The 5 raw-RunSQL migrations (materialized views in
`societies`/`codex`/`areas`, range-partitioning in `scenes`, covenant
mat-view in `societies/0003`) were wrapped with `PostgresOnlyRunSQL`. They
behave identically on PG and noop on SQLite — defensive even though the
DisableMigrations sentinel means they don't get a chance to run on SQLite
anyway.

## Caveats / known limitations

- **RunPython data seeds don't run.** Per `docs/perf/squash-audit-2026-05-20.md`,
  `world.progression.migrations.0002_social_engagement_kudos_category` seeds a
  `KudosSourceCategory(name="social_engagement")` row. If a test relies on
  it being present, that test needs either explicit seeding in
  `setUpTestData` or `@tag("postgres")`. Watch for failures during the
  broader app survey.
- **Materialized views don't exist on SQLite.** Tests that query
  `CharacterLegendSummary`, `PersonaLegendSummary`, `CovenantLegendSummary`,
  `SubjectBreadcrumb`, `AreaClosure` will fail with "no such table" on
  SQLite. They need `@tag("postgres")`.
- **`Interaction` is unpartitioned on SQLite.** Tests don't care about the
  partitioning specifically (it's a physical-storage optimization), so they
  should work.

## Next steps

1. **Phase 2.2** — full-suite SQLite run. Count failures + skips, capture
   wall-clock.
2. **Phase 3.1-3.2** — for each failure: classify as test-design issue (fix
   in-place) vs PG-required (decorate with `@tag("postgres")`).
3. Fix the 4 missions test-design issues found here.

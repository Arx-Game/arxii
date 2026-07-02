---
name: running-tests
compatibility: polytoken
description: Use when running or writing tests in this repo — choosing the SQLite fast tier vs Postgres parity tier, the just test recipes, @tag("postgres") decisions, --keepdb pitfalls, or diagnosing SQLite-vs-PG test failures.
---

# Running Tests

## Overview

Tests run in a **two-tier model**: a fast SQLite in-memory inner loop and a Postgres parity tier (what CI runs). **IMPORTANT: Always use `arx test` (or its `just` wrappers) to run tests.** Never use `uv run python -m`, `python manage.py test`, sourcing venvs to find binaries, or any other method.

## Testing philosophy

Prefer big **E2E user-journey integration tests** over many fine-grained unit tests. A single telnet-driven journey test that drives command → action → service → DB end-to-end is worth more than a dozen unit tests of individual layers. Don't create marginal unit tests that duplicate what the E2E already covers — they add maintenance cost without adding safety, and will be retired when E2E coverage matures anyway.

Write focused unit tests only when logic is genuinely fiddly and wouldn't be observable from the E2E happy path: e.g. a parsing helper with multiple lookup branches, error-path exception mapping, or a pure-function edge case. When in doubt, skip the unit test and let the integration test carry the weight.

**Don't assume player omniscience.** E2E journey tests should assert that the game tells the player what to do next, not just that the underlying state changed. If the game should emit a prompt ("use `flourish <resonance>` to declare your entrance"), assert that the caller received it. A journey test that only checks DB state leaves a gap: the player could be left with no idea what action is available to them, and the test wouldn't catch it.

## Two-tier model: SQLite for the inner loop, Postgres for parity

Production runs Postgres exclusively. Tests run in TWO tiers:

1. **Fast tier — SQLite in-memory.** `just test-fast <app>` / `arx test --sqlite <app>`. Schema built from current model state with NO migration replay (`MIGRATION_MODULES = DisableMigrations()` in `server.conf.sqlite_test_settings`). Tests decorated with `@tag("postgres")` are auto-skipped. Inner-loop speed: a typical app runs in 1-15s vs 5-30s on PG.
2. **Parity tier — Postgres.** `just test-parity <app>` / `arx test` (no flag — PG is the default). Runs the same migration chain CI runs. **Do NOT run this locally in the devcontainer** — Postgres test DB rebuilds are too slow and will time out (10+ minutes for a single app, 30+ for the full suite). Let CI be the parity gate. The only exception is reproducing a specific CI failure that the SQLite tier can't surface; in that case use `--keepdb` to avoid the rebuild. CI's 4-shard matrix (`.github/workflows/ci.yml:46-76`) runs every PR on this tier.

### Local testing rule

**Always use the SQLite fast tier (`just test-fast`) for local iteration.** Never run `just test-parity` or bare `arx test` (PG) locally in the devcontainer — it will time out. The PG parity tier is exclusively CI's job. If the app you're testing is PG-only (magic, scenes, etc.), run the SQLite tier anyway to catch logic errors — CI will catch PG-specific issues. The only time you should run PG locally is to reproduce a specific CI failure, and only with `--keepdb`.

### Working app set for `--sqlite`

| Tier | Apps |
|---|---|
| **SQLite-clean** | action_points, forms, achievements, game_clock, skills, relationships, flows, checks, events, missions, journals, mechanics, progression, conditions |
| **SQLite with caveats** (5-15% broken, partial tagging) | combat, items, vitals, actions |
| **PG only — `just test-parity` required** | roster, character_sheets, magic, scenes, codex, areas, societies |

For the PG-only apps, `--sqlite` either fails immediately (carved out via `MIGRATION_MODULES = None` in settings) or the fixture chain hits PG-vs-SQLite FK timing differences.

## Recipes

```bash
# Inner-loop (SQLite tier — fast, excludes @tag("postgres")):
just test-fast <app>                     # one app
just test-fast <app>.tests.test_module   # one module

# Parity tier (PG, parallel; what CI runs):
just test-parity <app>                   # one app
just test-parity                         # full suite, ~30+ min

# Generic pass-through (PG, no parallel):
just test <args>

# Full-suite parity gate (matches CI exactly):
just regression                          # echo "yes" | arx test
```

```bash
# Direct arx test (when you need exact CLI control):
arx test <app>                                 # PG, serial (default)
arx test --sqlite <app>                        # SQLite inner loop
arx test --parallel <app>                      # PG, parallel — use for large suites
arx test --exclude-tag postgres --sqlite ...   # skip @tag("postgres") explicitly on SQLite
```

## Invocation & tooling gotchas (#756)

Recurring stumbles, all avoidable:

- **Non-interactive runs go through `just`, never raw `arx test`.** The
  Postgres tier prompts "database test_arxiidev already exists — recreate?"
  which `EOFError`s in a non-interactive shell; the `just` recipes wrap it
  with `echo "yes" |`. (Raw runs also leave a stale `test_arxiidev` behind
  when killed — the next run's prompt is exactly that leftover.)
- **Dotted test paths need the `world.` prefix:**
  `just test-fast world.covenants.tests.test_rites`, not
  `covenants.tests.test_rites` (the latter →
  `ModuleNotFoundError: No module named 'covenants'`).
- **`arx test` rejects `-v`** (it's a typer CLI, not Django's manage.py) —
  grep the output instead.
- **`ruff` and `pre-commit` are not on PATH** — use `uv run ruff` /
  `uv run pre-commit` (same as `uv run arx`).
- **Bare `arx` is not on PATH either** for the main Bash tool's non-interactive
  shell (or `run_in_background` shells) — subagents get it via their profile,
  but the controller doesn't. Always invoke via `uv run arx test ...` or the
  `just` recipes, never bare `arx`.
- **Don't store Evennia objects (ObjectDB / RoomProfile / typeclassed rows)
  in `setUpTestData`.** Django deepcopies class-level test data per test,
  and these objects acquire un-deepcopyable typeclass internals once the
  full suite has loaded — tests then pass standalone but error under
  `arx test` with `un(deep)copyable object: DbHolder` **only in multi-app CI
  shard runs**, never when the app's tests run alone (order-dependent: the
  idmapper identity map persists across the shard process, and a factory's
  `django_get_or_create` can return a contaminated cached instance from an
  earlier app's tests). Create Evennia fixtures in `setUp` instead, and call
  `evennia.utils.idmapper.models.flush_cache()` at the top of `setUpTestData`
  when the class does use one. Cost two CI rounds on PR #922 — reproduce with
  the exact shard app list from `.github/workflows/ci.yml`, not a solo run.
- **`evennia.utils.test_resources.EvenniaTest` breaks in this repo** — its
  session-login path hits the custom `accounts.py::at_post_login` and raises
  `TypeError: ServerSession.at_login() missing ... 'account'`. Use plain
  `django.test.TestCase` + `evennia_extensions.factories.CharacterFactory`
  instead (see `world/items/tests/test_handlers.py`) for any test needing a
  real character.
- **Frontend: never run bare `pnpm test`** — it's `vitest` in watch mode and
  never exits. Use `pnpm exec vitest run <path>` (or bare `pnpm exec vitest run`
  for everything). For the full frontend gate: `pnpm exec vitest run`,
  `pnpm typecheck`, `pnpm lint`, `pnpm build` (the build's `tsc -b` project-
  reference mode type-checks test files that `typecheck`/vitest miss).
- **Watch for a stray `src/.venv`.** If a command was ever run as `cd src &&
  uv run ...` (including the MODEL_MAP regen command,
  `uv run python tools/introspect_models.py`), `uv` creates a venv inside
  `src/`, and the `shard-coverage` pre-commit hook then rglobs its
  site-packages as unsharded Django apps and fails the commit. Fix:
  `rm -rf src/.venv` (gitignored, safe) and always run `uv`/`just`/`arx` from
  the **worktree root**.

## When tests fail on SQLite but pass on PG

The two-tier model exposes a small set of patterns:

- **Tag with `@tag("postgres")`** when the failure is genuinely PG-required: queries a materialized view, uses `DISTINCT ON`, uses raw `REFRESH MATERIALIZED VIEW`, or hits Evennia-internal `DbHolder` copy issues. The PG tier still runs them.
- **Fix the test** when the failure is a test-design issue PG happened to mask: `assertEqual(queryset[0].field, expected)` without `order_by`, direct ID comparison (`[2, 3] != [1, 2]`), or SharedMemoryModel identity-map pollution from other tests in the class. Fix via `order_by("pk")`, set comparison, or `from evennia.utils.idmapper.models import SharedMemoryModel; SharedMemoryModel.flush_instance_cache()` in setUp. (See the `sharedmemory-model` skill for identity-map / cache-flushing details.)

See `src/world/checks/tests/test_legend_award_handler.py:189-195` for the canonical `@tag("postgres")` pattern.

### Known pre-existing SQLite-fast-tier failures (not your regression)

Two app-level patterns produce SQLite-tier errors that are pre-existing and PG-only — verify the failing test file is untouched by your branch before treating either as a regression, and lean on CI's Postgres shard as the real gate:

- **`world.areas.tests`** — ~15 "no such table: areas_areaclosure" errors. `AreaClosure` is `managed = False`, backed by a Postgres materialized view (`RunSQL` in `areas/migrations/0002_create_areaclosure_view.py`); SQLite can't create it. Run `arx test world.areas.positioning` instead (doesn't touch the view) — CI's PG shard covers the rest.
- **`world.magic` / `world.vitals` / `world.mechanics`** (and others) — ~29 `NotSupportedError: DISTINCT ON fields is not supported by this database backend`. Any test that calls `apply_condition` reaches `world/conditions/services.py::_build_bulk_context`'s PG-only `.distinct("condition_id")` — soul_tether, fury/berserk, soulfray, non_clash_strain, nonlethal_cap, plus the death/knockout consequence-pool tests. These are not `@tag("postgres")` but are effectively PG-only.

### Parallel-session Postgres test-DB contention

When two worktree sessions run Postgres tests concurrently, both default to `test_arxiidev` and one gets "database is being accessed by other users." The `--sqlite` tier sidesteps this, but doesn't cover apps the fast tier excludes (`roster`, `character_sheets`, `magic`, `codex`, `areas`, `societies`). Fix — give the worktree its own DB (the worktree's `src/.env` is gitignored, so this never touches the shared dev DB):

1. Edit `src/.env`: `DATABASE_URL=postgres://arxii:arxii@db:5432/arxiidev_<N>` (Django loads `.env` with overwrite, so a shell env var alone is ignored).
2. `PGPASSWORD=arxii psql -h db -U arxii -d postgres -c "CREATE DATABASE arxiidev_<N> OWNER arxii;"`
3. `cd src && uv run arx manage migrate` — migrate the **base** DB first, or Evennia's test setup queries `server_serverconfig` on the default connection before the test DB exists.
4. Clone it: `psql ... -d postgres -c "CREATE DATABASE test_arxiidev_<N> TEMPLATE arxiidev_<N>;"`
5. Always run with `--keepdb`: `echo "no" | uv run arx test --keepdb <dotted.path>` (reuses the prebuilt DB and applies any new migrations, so it stays correct across syncs).

## CI is the full-regression gate

Run the fast SQLite tier for the apps you changed (`just test-fast <app>`), then push and **monitor the PR**. CI runs the full Postgres parity suite on every PR — let it catch regressions and fix what it reports there. Run a local `just regression` only to reproduce a CI failure the fast tier doesn't surface.

## `--keepdb` and faithful local repro

CI always starts from a fresh DB. To reproduce a CI failure locally, run without `--keepdb` so Evennia setup objects (Limbo room #2, default Account #1) and prior-run state don't leak in:

```
just regression                        # echo "yes" | arx test — fresh DB, matches CI
```

`--keepdb` speeds local iteration but hides bugs that depend on a fresh DB — migrations, factories, service functions that call `create_object`, typeclass initialization, test settings. Drop it for the repro run.

## Never rely on Evennia defaults in service functions

**Never rely on Evennia defaults in service functions.** When calling `create_object`, always either pass explicit `home=`, `location=`, etc., or pass `nohome=True` / `nolocation=True`. The implicit fallback to `settings.DEFAULT_HOME` (Limbo #2) only works when Evennia's initial setup has run — CI test DBs do not run initial setup, so FK violations fire before any graceful fallback. Same caution for `DEFAULT_SCRIPT_HOME`, Account #1 references, and anything else that assumes "Evennia will figure out the default."

## Use `just` for task runners, not raw `bash`/`python`

**Use `just` for task runners, not raw `bash`/`python`.** The repo has a `justfile` at the root with recipes for common dev tasks (test, lint, manage, etc.). `just` is pinned in `mise.toml` and covered by a single `Bash(just:*)` allowlist entry, so any recipe invocation auto-approves.

```bash
just                        # list recipes
just test flows --keepdb    # arx test pass-through
just test-fast world.foo    # SQLite inner loop
just test-parity world.foo  # PG parity tier (parallel)
just regression             # full no-keepdb regression run
just lint                   # ruff check
just manage migrate flows   # arx manage pass-through
```

Prefer `just <recipe>` over raw `bash <script>`, `python <script>`, `sh <script>` — these invoke "can do anything" interpreters and trigger per-command approval every time. Never give `Bash(bash:*)` blanket approval.

**When no recipe exists:** add one to `justfile` rather than running raw scripts or accumulating per-path allowlist entries.

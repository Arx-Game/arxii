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

1. **Fast tier — SQLite in-memory.** `just test-fast <app>` / `arx test --sqlite <app>`. Schema built from current model state with NO migration replay (`MIGRATION_MODULES = DisableMigrations()` in `server.conf.sqlite_test_settings`), and cached: `SqliteTestRunner` saves the built test DB to `src/.test_schema_cache/` keyed by a model-state fingerprint and restores it on later runs, so only the first run after a model change pays the schema build (~15s extra). Tests decorated with `@tag("postgres")` are auto-skipped. Inner-loop speed: ~6-10s of fixed per-invocation overhead (imports, discovery, cached-schema restore) plus the tests themselves. `ARX_SCHEMA_CACHE=0` bypasses the cache if you suspect it.
2. **Parity tier — Postgres.** `just test-parity <app>` / `arx test` (no flag — PG is the default). Uses the same schema-from-models build CI uses: the test DB is pre-built by `tools/build_schema.py` (via `just build-test-schema`) and reused across runs with `--keepdb`, not rebuilt from migration replay per run. Migration replay only happens in the nightly `nightly-migration-replay.yml` workflow (ADR-0083). Building the test DB once (`just build-test-schema`, or automatically on the first `just test-parity`/`just regression` run) takes seconds, not the 10+ minutes the old migration-replay path cost — parity runs are fast locally afterward. Go through `just test-parity <app>` / `just regression` (or `build-test-schema --rebuild` after a model change), not bare `arx test`/`arx test --keepdb` — only the `just` recipes probe that the pre-built schema (partition, matviews, seeds) is actually complete before reusing it; a bare Django-created test DB is syncdb-only and missing all three. CI's 6-shard matrix (`.github/workflows/ci.yml`) runs every PR on this tier.

### Local testing rule

**Use the SQLite fast tier (`just test-fast`) for the inner loop.** For PG-only apps (magic, scenes, etc.), or before pushing, run `just test-parity <app>` — the pre-built test DB makes this fast locally now, not the multi-minute rebuild the old migration-replay path required. Always go through the `just` recipes (`test-parity`/`regression`/`build-test-schema`) rather than bare `arx test`/`arx test --keepdb` against Postgres, so the schema-completeness probe runs before reuse.

### Per-invocation overhead dominates — batch, don't narrow

Most of a fast-tier run's wall time is **fixed per-invocation cost** (interpreter + Django/Evennia imports, test discovery, schema restore), not test execution — 109 tests execute in ~3s inside a ~10s invocation. Two consequences:

- **Batch apps into one invocation.** `just test-fast app1 app2 app3` pays the overhead once (and auto-enables `--parallel`); three separate runs pay it three times.
- **Don't narrow the selection to save time.** Running one module instead of the whole app saves almost nothing — select by what you want to *see*, not for speed.
- **Run from an ext4 worktree.** The 9p-mounted main checkout adds ~25s of import stat-storm per invocation; the `just` test recipes warn when you're on 9p. Worktrees under `.claude/worktrees/` don't pay it.

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
just test-fast <app>                     # one app (serial)
just test-fast <app>.tests.test_module   # one module (serial)
just test-fast <app1> <app2>             # multiple apps (auto --parallel)
just test-fast-par <app>                 # force --parallel on one large app

# Change-impact-aware (recommended for PR work — runs only apps your branch
# touches PLUS apps that import from them):
just test-affected                       # diff vs origin/main
just test-affected --keepdb              # extra args passed to arx test

# Parity tier (PG, serial by default — pass --parallel yourself if you want it):
just test-parity <app>                   # one app
just test-parity                         # full suite (avoid locally — see below)

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

Five more specific failure signatures (DbHolder/`setUpTestData` copy errors,
`EvenniaTest` login breakage, `pnpm test` watch-mode hangs, a stray
`src/.venv` failing `shard-coverage`, parallel-session Postgres DB
contention) are in
[`references/known-test-failures.md`](references/known-test-failures.md) —
look there when you actually hit one of those symptoms.

## When tests fail on SQLite but pass on PG

The two-tier model exposes a small set of patterns:

- **Tag with `@tag("postgres")`** when the failure is genuinely PG-required: queries a materialized view, uses `DISTINCT ON`, uses raw `REFRESH MATERIALIZED VIEW`, or hits Evennia-internal `DbHolder` copy issues. The PG tier still runs them.
- **Fix the test** when the failure is a test-design issue PG happened to mask: `assertEqual(queryset[0].field, expected)` without `order_by`, direct ID comparison (`[2, 3] != [1, 2]`), or SharedMemoryModel identity-map pollution from other tests in the class. Fix via `order_by("pk")`, set comparison, or `from evennia.utils.idmapper.models import SharedMemoryModel; SharedMemoryModel.flush_instance_cache()` in setUp. (See the `sharedmemory-model` skill for identity-map / cache-flushing details.)

See `src/world/checks/tests/test_legend_award_handler.py:189-195` for the canonical `@tag("postgres")` pattern.

**A test failing only on the SQLite fast tier is not automatically your bug.** Two whole apps (`world.areas`, and `world.magic`/`world.vitals`/`world.mechanics` via `apply_condition`) have known pre-existing PG-only failure patterns, and parallel worktree sessions can contend over the shared Postgres test DB. See [`references/known-test-failures.md`](references/known-test-failures.md) before spending time chasing either.

## CI is the full-regression gate

**For PR work, prefer `just test-affected`** — it diffs your branch against `origin/main` and runs only the apps you touched plus apps that import from them, so you don't waste time running unrelated suites. For a single app, use `just test-fast <app>`.

Then push and **monitor the PR**. CI runs the full Postgres parity suite on every PR (6 parallel shards, ~2,500 tests each) — let it catch regressions and fix what it reports there. Run a local `just regression` only to reproduce a CI failure the fast tier doesn't surface.

## Background-run lifecycle (kills, hangs, branch switches)

A background `arx test` run holds live shared state; three recurring traps:

- **After killing a run, reset the test DB before relaunching.** A killed run
  can leave a stale PG session on `test_arxiidev`; the next run then blocks at
  the destroy/create step or errors "database is being accessed by other
  users." Fix: `pg_terminate_backend` the `test_arxiidev` sessions and
  `DROP DATABASE IF EXISTS test_arxiidev` via psql, then relaunch.
- **"Creating test database..." silence up to ~5 minutes is NORMAL on PG** —
  it's ~80 migrations applying with no streamed output, not a hang. Check
  `pg_stat_activity` before killing: an active/committing session is healthy;
  an idle blocked session is the stale-session trap above.
- **Never `git checkout` while a background run is live.** Runs read source
  files live from the shared tree; a mid-run branch switch makes modules
  inconsistent and produces bogus import tracebacks. Finish or kill the run
  first (then see the reset step above).
- **Runaway allocations die at a 4GB/process ceiling (`ARX_TEST_MEM_LIMIT_GB`).**
  The runner sets `RLIMIT_AS` so a memory runaway — classic cause: a bare
  `MagicMock` fed into a `while node is not None: node = node.parent` walk,
  where the mock fabricates `.parent` forever (#2386) — fails as an ordinary
  test ERROR with a `MemoryError` traceback naming the loop, instead of
  swap-thrashing the devcontainer or OOM-killing the CI runner. Diagnostic
  corollary: a CI shard dying with "runner received a shutdown signal" and
  zero test failures printed is an OOM suspect first, infra second. Raise the
  env var only if a suite legitimately exceeds 4GB; `0` disables.

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
just test-fast world.foo    # SQLite inner loop (serial)
just test-fast-par world.foo # SQLite inner loop (forced parallel)
just test-affected          # only apps your branch touches + importers
just test-parity world.foo  # PG parity tier (serial; pass --parallel yourself if you want it)
just regression             # full no-keepdb regression run
just lint                   # ruff check
just manage migrate flows   # arx manage pass-through
```

Prefer `just <recipe>` over raw `bash <script>`, `python <script>`, `sh <script>` — these invoke "can do anything" interpreters and trigger per-command approval every time. Never give `Bash(bash:*)` blanket approval.

**When no recipe exists:** add one to `justfile` rather than running raw scripts or accumulating per-path allowlist entries.

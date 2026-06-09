---
name: running-tests
description: Use when running or writing tests in this repo — choosing the SQLite fast tier vs Postgres parity tier, the just test recipes, @tag("postgres") decisions, --keepdb pitfalls, or diagnosing SQLite-vs-PG test failures.
---

# Running Tests

## Overview

Tests run in a **two-tier model**: a fast SQLite in-memory inner loop and a Postgres parity tier (what CI runs). **IMPORTANT: Always use `arx test` (or its `just` wrappers) to run tests.** Never use `uv run python -m`, `python manage.py test`, sourcing venvs to find binaries, or any other method.

## Two-tier model: SQLite for the inner loop, Postgres for parity

Production runs Postgres exclusively. Tests run in TWO tiers:

1. **Fast tier — SQLite in-memory.** `just test-fast <app>` / `arx test --sqlite <app>`. Schema built from current model state with NO migration replay (`MIGRATION_MODULES = DisableMigrations()` in `server.conf.sqlite_test_settings`). Tests decorated with `@tag("postgres")` are auto-skipped. Inner-loop speed: a typical app runs in 1-15s vs 5-30s on PG.
2. **Parity tier — Postgres.** `just test-parity <app>` / `arx test` (no flag — PG is the default). Runs the same migration chain CI runs. Use before pushing, and for apps the SQLite tier can't cover. CI's 4-shard matrix (`.github/workflows/ci.yml:46-76`) runs every PR on this tier.

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

## When tests fail on SQLite but pass on PG

The two-tier model exposes a small set of patterns:

- **Tag with `@tag("postgres")`** when the failure is genuinely PG-required: queries a materialized view, uses `DISTINCT ON`, uses raw `REFRESH MATERIALIZED VIEW`, or hits Evennia-internal `DbHolder` copy issues. The PG tier still runs them.
- **Fix the test** when the failure is a test-design issue PG happened to mask: `assertEqual(queryset[0].field, expected)` without `order_by`, direct ID comparison (`[2, 3] != [1, 2]`), or SharedMemoryModel identity-map pollution from other tests in the class. Fix via `order_by("pk")`, set comparison, or `from evennia.utils.idmapper.models import SharedMemoryModel; SharedMemoryModel.flush_instance_cache()` in setUp. (See the `sharedmemory-model` skill for identity-map / cache-flushing details.)

See `src/world/checks/tests/test_legend_award_handler.py:189-195` for the canonical `@tag("postgres")` pattern.

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

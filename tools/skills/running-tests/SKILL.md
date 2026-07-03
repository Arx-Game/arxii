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
2. **Parity tier — Postgres.** `just test-parity <app>` / `arx test` (no flag — PG is the default). Uses the same schema-from-models build CI uses: the test DB is pre-built by `tools/build_schema.py` (via `just build-test-schema`) and reused across runs with `--keepdb`, not rebuilt from migration replay per run. Migration replay only happens in the nightly `nightly-migration-replay.yml` workflow (ADR-0083). **Do NOT run this locally in the devcontainer** — Postgres test DB rebuilds are too slow and will time out (10+ minutes for a single app, 30+ for the full suite). Let CI be the parity gate. The only exception is reproducing a specific CI failure that the SQLite tier can't surface; in that case use `--keepdb` to avoid the rebuild. CI's 6-shard matrix (`.github/workflows/ci.yml`) runs every PR on this tier.

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
just test-fast <app>                     # one app (serial)
just test-fast <app>.tests.test_module   # one module (serial)
just test-fast <app1> <app2>             # multiple apps (auto --parallel)
just test-fast-par <app>                 # force --parallel on one large app

# Change-impact-aware (recommended for PR work — runs only apps your branch
# touches PLUS apps that import from them):
just test-affected                       # diff vs origin/main
just test-affected --keepdb              # extra args passed to arx test

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
just test-parity world.foo  # PG parity tier (parallel)
just regression             # full no-keepdb regression run
just lint                   # ruff check
just manage migrate flows   # arx manage pass-through
```

Prefer `just <recipe>` over raw `bash <script>`, `python <script>`, `sh <script>` — these invoke "can do anything" interpreters and trigger per-command approval every time. Never give `Bash(bash:*)` blanket approval.

**When no recipe exists:** add one to `justfile` rather than running raw scripts or accumulating per-path allowlist entries.

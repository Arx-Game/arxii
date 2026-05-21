# Test-speed improvements: two-tier (SQLite fast + Postgres parity)

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute
> this plan task-by-task on a fresh branch off `main` (already done: `feature/test-speedups`).
> **Pivot note:** this plan was revised on 2026-05-20 from a Postgres-only speedup plan to a
> two-tier model after senior-dev pushback. The earlier draft is in git history; the
> baseline numbers it captured (33 min 55s full-suite serial on PG) are still useful for the
> PG-tier comparison.

**Goal:** Drop the inner-loop test-gate time from 33 minutes (full-suite serial PG) to ~30
seconds via SQLite-in-memory for the bulk of unit tests, while keeping the existing Postgres
shard matrix in CI for parity (and making *it* as fast as possible too).

**Architecture (two-tier testing):**
1. **Fast tier — SQLite in-memory.** Default for `arx test` / `just test`. Almost all
   tests. Inner-loop speed.
2. **Postgres parity tier — existing CI shards (`ci.yml:46-76`).** Runs on every PR,
   unchanged in CI. Catches PG-specific reality (recursive CTEs, JSONB operators, NULL
   ordering, DISTINCT ON, window functions), migration realities, and silent SQLite
   discrepancies. Decorate PG-required tests with `@tag("postgres")` so the SQLite tier
   skips them cleanly.

**Tech stack:** Django 5.2 test runner, Evennia test runner (`arx test` wraps it), Postgres
17 local + Postgres 15 in CI, SQLite 3 (stdlib), `uv`, `arx` CLI, `just` recipes.

**Branch:** `feature/test-speedups` (already created, two commits landed: `596ffa65` shard-1
adds missions; `44509d49` lint_shard_coverage.py + 7 more apps placed in shards).

---

## Reality check — what's already in place

- **`arx.py:21,104,146-147`** — `--parallel` is a Typer bool flag that appends `--parallel`
  to Django's command (auto-detect CPUs). Already works locally and in CI.
- **`ci.yml:114-118`** — CI already runs `uv run arx test --parallel ${{ matrix.shard.apps }}`.
- **`ci.yml:80-91`** — CI's Postgres service uses `--tmpfs /var/lib/postgresql/data` (data
  dir in RAM). Major speedup already in place CI-side.
- **`ci.yml:33-73`** — 4-way sharded by app. After commits `596ffa65` and `44509d49`, ALL
  apps with `apps.py` on disk are placed in some shard (verified by
  `tools/lint_shard_coverage.py` as a pre-commit guard).
- **Postgres-only baseline captured at `docs/perf/test-baseline-2026-05-20.md`:**
  - `world.missions` (246 tests): 18.8s serial / 23.5s --parallel (parallel REGRESSED for
    small suites due to per-worker DB-clone overhead — expected).
  - Full suite (7,529 tests): **2,035.236s serial** (33 min 55s). Full-suite --parallel
    capture was aborted; the SQLite tier makes it less interesting.
- **RunPython audit captured at `docs/perf/squash-audit-2026-05-20.md`:** 10 RunPython
  migrations. 1 critical (`progression.0002` seeds a `KudosSourceCategory` lookup row); 9
  no-op on fresh DB (backfills/wipes/conditional skips).

---

## Phase 1 — Shard hygiene ✅ DONE

- **Task 1.1** ✅ `world.missions` added to shard-1 (commit `596ffa65`).
- **Task 1.2** ✅ `tools/lint_shard_coverage.py` + pre-commit hook (commit `44509d49`); also
  surfaced 7 additional unsharded apps and placed them.

---

## Phase 2 — SQLite spike (NEW, replaces "baseline measurement")

**Goal:** prove the SQLite tier works for the easy 80% of tests; identify the PG-required
remainder; measure the inner-loop time.

### Task 2.1: `sqlite_test_settings.py` + missions spike

**Files:**
- `src/server/conf/sqlite_test_settings.py` (NEW) — imports from the existing
  `test_settings.py` shim and overrides `DATABASES["default"]` to `{"ENGINE":
  "django.db.backends.sqlite3", "NAME": ":memory:"}`.
- Possibly `src/cli/arx.py` (MODIFY) — add a `--sqlite` flag that swaps the
  `--settings=test_settings` arg to `--settings=sqlite_test_settings`. Keep `test_settings`
  (the existing PG flavor) as the default for THIS task; switching the default belongs in
  Task 4.1 once the SQLite tier is proven.

**Step 1:** Create the SQLite settings file. Inherit from the existing PG `test_settings`
so all other settings (apps, middleware, ROOT_URLCONF, etc.) stay identical — only DATABASES
flips. Verify there's no per-DB-engine logic baked into other settings (`grep "postgresql"
src/server/conf/`).

**Step 2:** Try `arx test --sqlite world.missions`. Expected outcomes:
- **Best case:** all 246 missions tests pass. Inner-loop ~5-10s vs 18.8s on PG.
- **Likely case:** some tests fail because they rely on PG-specific query behavior. Collect
  them.
- **Worst case:** the test DB won't even build because a migration uses PG-only operations
  (e.g. raw SQL `CREATE INDEX CONCURRENTLY`, `ArrayField`, `pg_trgm`). Inventory before
  declaring the spike dead.

**Step 3:** If the spike works, expand to `world.stories` (DAG queries — high PG-feature
risk), `world.magic` (recursive CTE shape per memory — high risk), and a slow-CT-heavy app
like `world.checks`. These three exercise the most PG-dependent code paths in the codebase.

**Step 4:** Record findings in `docs/perf/sqlite-spike-2026-05-20.md`:
```markdown
| Scope | Tests | SQLite outcome | Notes |
|---|---:|---|---|
| world.missions | 246 | PASS ?s | ... |
| world.stories | 759 | N failed | DAG CTE-shaped query fails on ... |
| world.magic | 887 | N failed | Resonance recursive walk; ArrayField at ... |
| ... | ... | ... | ... |
```

**Step 5:** Commit:
```
perf(test): spike SQLite in-memory test tier

Senior dev's correction: a two-tier testing model (SQLite for fast inner
loop + Postgres for CI parity) should drop full-suite from 34 min serial
to seconds. This commit lands the SQLite settings shim + initial spike
measurements; subsequent tasks decorate PG-required tests and switch the
default test runner over.

See docs/perf/sqlite-spike-2026-05-20.md for per-app outcomes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

**Gate:** if the spike reveals more than ~10% of tests fail or skip on SQLite — and the
failures cluster in apps with deep PG dependencies — the two-tier model is still worth it,
but Phase 3 (PG-only inventory) becomes the long-pole. If less than 10% fail, the inventory
is small and quick.

### Task 2.2: full-suite SQLite measurement

**Files:** none (measurement).

**Step 1:** `echo "yes" | uv run arx test --sqlite > .claude/scratch/sqlite-full.log 2>&1`.
Expect failures from tests not yet tagged `@tag("postgres")`. Capture both the failure
count AND the wall-clock time.

**Step 2:** Update `docs/perf/test-baseline-2026-05-20.md` with the SQLite full-suite number.

**Step 3:** Commit (or fold into Task 2.1's commit if same session).

**Gate:** wall-clock ≤60s = inner-loop goal hit even with failures. ≤300s = good. Above 600s
= something's structurally wrong; investigate before tagging.

---

## Phase 3 — PG-only test inventory + `@tag("postgres")` decoration

**Goal:** for every test that genuinely needs PG (not just "happens to fail on SQLite due to
a minor query shape difference"), decorate with `@tag("postgres")` so the SQLite tier
cleanly skips it. The PG tier in CI still runs them.

### Task 3.1: structural code-path inventory

Grep the codebase for patterns that **structurally** require PG:

- `from django.contrib.postgres` (ArrayField, JSONField with PG-specific lookups,
  `pg_trgm`, etc.)
- Raw SQL using PG-only syntax: `DISTINCT ON`, recursive CTEs (`WITH RECURSIVE`), window
  functions used in `.raw()` calls, `ILIKE`, `~` regex operators.
- `.extra(...)` calls with PG-specific snippets.
- Use of `RunSQL` operations in migrations with PG-specific syntax (per the squash audit;
  most are AddField shape and PG-safe).
- Any test using `connection.vendor` checks.

For each hit, categorize:
- **Test that exercises the PG-specific code** → tag with `@tag("postgres")`.
- **Production code with no test coverage of the PG-specific path** → leave alone; the SQLite
  tier won't exercise it, the PG tier will catch regressions.
- **Test that uses Django ORM only but happens to fail on SQLite** → fix the ORM query if
  possible (e.g., `__contains` works differently on JSONField; sometimes a rewrite to a
  uniform query is cleaner).

Record findings in `docs/perf/pg-tests-inventory-2026-05-20.md`.

### Task 3.2: decorate tests + iterate

For each app the Task 2.1 spike found failing on SQLite:

**Step 1:** Read the failure list. For each failed test, decide via Task 3.1's inventory
whether it needs `@tag("postgres")` (most common) or can be rewritten ORM-uniform.

**Step 2:** Decorate with `from django.test import tag` + `@tag("postgres")`. Match the
project's existing convention if any (`grep "@tag" src/` to confirm shape).

**Step 3:** Re-run `arx test --sqlite world.<app>` and confirm the suite is clean (the
remaining tests all pass on SQLite).

**Step 4:** Commit per app, e.g.:
```
test(world.magic): tag PG-required tests for two-tier runner

N tests decorated with @tag("postgres") — they exercise <pattern>
which requires PG. The Postgres CI shard continues to run them; the
SQLite inner-loop tier skips cleanly.
```

**Gate:** after all apps decorated, `arx test --sqlite` exits 0 with `skipped=N` where N is
the PG-only count. Capture the final wall-clock time.

---

## Phase 4 — Default switch + just recipes

### Task 4.1: `arx test` default → SQLite, opt-in `--postgres`

**Files:** `src/cli/arx.py`.

**Step 1:** Add a `--postgres` flag mirroring `--sqlite`. Wire the settings selection:
- Default → SQLite settings.
- `--postgres` → existing PG settings.

**Step 2:** Update the `arx test` docstring + examples.

**Step 3:** Verify CI is unaffected — CI's `ci.yml:118` calls `uv run arx test --parallel
${{ matrix.shard.apps }}` (no `--sqlite` / `--postgres` flag). Decide:
- **Option A:** CI's invocation explicitly passes `--postgres`. Cleanest.
- **Option B:** CI sets an environment variable (`ARX_TEST_DB=postgres`) that `arx.py`
  reads. Slightly more flexible but more state.
- **Recommended:** Option A. Edit `ci.yml:118` to `uv run arx test --postgres --parallel ${{ matrix.shard.apps }}`.

**Step 4:** Commit.

### Task 4.2: `just test-fast` + `just test-parity` recipes

**Files:** `justfile` (root).

**Step 1:** Read the existing recipes (already shown in plan history; `just test` is a
pass-through to `arx test`).

**Step 2:** Add:
```just
# Inner-loop test runner: SQLite, excludes postgres tag, parallel.
test-fast *args:
    echo "yes" | uv run arx test --parallel --exclude-tag postgres {{args}}

# CI-parity test runner: Postgres, includes everything.
test-parity *args:
    echo "yes" | uv run arx test --postgres --parallel {{args}}
```

(Verify `--exclude-tag` is the right Django flag — Django's test runner accepts
`--exclude-tag <name>` for tag-based exclusion; check via `arx test --help`.)

**Step 3:** Update `just regression` to be explicitly PG-parity, or document it stays as-is.

**Step 4:** Commit.

---

## Phase 5 — Postgres-tier squashing (kept, lower priority)

**Why kept:** the PG parity tier still runs on every PR. Migration playback on a fresh DB
is the dominant non-test cost there too. Cutting from ~30+ migrations per app to 1 squashed
+ N post-squash deltas is still worth ~minutes off the PG tier per run, even though the
inner loop bypasses it entirely.

**Why lower priority:** the inner loop is now via SQLite, so squashing no longer blocks the
day-to-day developer experience. Can land after Phases 2-4.

### Task 5.1: per-app squash (topological order)

Same approach as in the previous plan revision (per-app squash, fresh-DB gate per app, full
PG-tier gate after each app, delete replaced migrations). See the RunPython audit at
`docs/perf/squash-audit-2026-05-20.md` for the one critical case (`progression.0002`).

**Step 1-6:** unchanged from prior plan revision. Per-app `arx manage squashmigrations`,
verify, fresh-DB gate, delete originals, commit.

### Task 5.2: measure PG-tier post-squash delta

Update `docs/perf/test-baseline-2026-05-20.md` with a "PG tier post-squash" column.

**Gate:** PG tier delta ≥30% = ship the squashes. <30% = the maintenance cost (lost
per-migration history) isn't justified; revert.

---

## Phase 6 — Optional PG-tier polish

Lower priority than ever — the inner loop is fast already.

### Task 6.1: setUpTestData audit

Same as prior plan revision — convert read-only `setUp` fixtures to class-level
`setUpTestData`. Spike one app, measure, sweep if it pays off.

### Task 6.2: local tmpfs Postgres (optional)

Spin up a `docker-compose.test.yml` with the same tmpfs Postgres CI uses, gated by env var.
Only if local PG-parity runs (`just test-parity`) are still painful after Phase 5.

### Task 6.3: persistent template DB (optional)

Pre-build the migrated schema once into `test_arxii_template`; subsequent runs clone via
`CREATE DATABASE ... TEMPLATE ...`. Only if Phase 5 + 6.2 isn't enough.

---

## Phase 7 — Docs + PR

### Task 7.1: rewrite the CLAUDE.md `PostgreSQL Only` rule

**Files:** `CLAUDE.md` (root).

**Step 1:** Rewrite the existing "PostgreSQL Only" subsection to clarify:
- **Production code:** still Postgres-only. Use PG-specific features freely. Don't write
  dual-SQL queries.
- **Test infrastructure:** two-tier. SQLite for the fast inner loop; Postgres parity in CI.
  Tests that exercise PG-specific paths must carry `@tag("postgres")` so the SQLite tier
  skips them.

**Step 2:** Update the "Running Tests" section:
- `just test-fast <app>` — inner loop (SQLite, parallel, excludes postgres tag).
- `just test-parity <args>` — CI parity (Postgres, parallel).
- `echo "yes" | uv run arx test --postgres` — explicit CI-parity gate before pushing.

**Step 3:** Document the `tools/lint_shard_coverage.py` regression guard from Phase 1.

**Step 4:** Commit.

### Task 7.2: final dual-tier gate + PR

**Step 1:** Run BOTH tiers as the final pre-push gate:
- `just test-fast` — must exit 0.
- `echo "yes" | uv run arx test --postgres --parallel` — must exit 0.

**Step 2:** Push, open PR. Title: `perf(test): two-tier testing (SQLite fast + PG parity)`.
PR body: the baseline → final timings, the two-tier model, the count of tests now decorated
`@tag("postgres")`, and links to `docs/perf/`.

---

## Decision points and STOP gates

- **End of Task 2.1:** if SQLite spike on missions fails STRUCTURALLY (test DB won't build),
  STOP and audit. Some migration is using a PG-only operation that needs a SQLite-safe
  alternative or `connection.vendor` guard.
- **End of Task 2.2:** if SQLite full-suite is >300s, something is structurally slow on
  SQLite (most likely: per-test setup creating too many DB rows, since SQLite is faster on
  reads but slower on bulk writes). Investigate before tagging.
- **End of Phase 3:** if more than ~25% of tests end up `@tag("postgres")`, the two-tier
  model's inner-loop benefit is diluted. Consider whether some of those tests can be
  refactored to ORM-uniform queries instead.
- **End of Phase 5.2:** if PG-tier squashing delta is <30%, revert.

## Out of scope (explicitly)

- **Dual-SQL production code.** The "PostgreSQL Only" production rule still holds. SQLite
  is for the test tier ONLY.
- **Restructuring the Evennia test runner.** Extend `arx.py` instead.
- **CI infrastructure rewrites.** The 4-shard PG matrix stays; CI's invocation gets the
  `--postgres` flag explicitly. Nothing else changes.
- **Test-level refactors** beyond Phase 6.1 — major test rewrites belong in their own
  branch.

## Execution handoff

When ready: continue on `feature/test-speedups`, use `superpowers:subagent-driven-development`
for the substantive tasks (Phase 2 SQLite spike, Phase 3 PG-inventory). Mechanical work
(Phase 4 just recipes, Phase 7 docs) is fine to drive directly.

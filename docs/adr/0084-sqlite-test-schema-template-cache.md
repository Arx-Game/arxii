# SQLite fast tier restores a cached schema template instead of rebuilding per run

**Decision:** the SQLite inner-loop test runner (`server.conf.sqlite_test_runner.SqliteTestRunner`)
caches the fully-built in-memory test database — schema plus the `post_migrate`-seeded rows
(content types, permissions, sites) — as a file under `src/.test_schema_cache/`, keyed by a
fingerprint of current model state (every non-proxy model's deconstructed fields, `Meta` options
and bases, plus the Django/Evennia versions, with set-iteration order and memory-address reprs
canonicalized; proxy models are excluded because Evennia typeclasses register lazily on first
import and would make the key depend on which test modules discovery imported). On a fingerprint
match, `call_command("migrate")` inside `create_test_db` is swapped for a SQLite backup-API
restore of the template; on a mismatch the schema builds normally and is re-cached.
Relatedly, `TimedEvenniaTestRunner.setup_databases` (both tiers) disconnects Evennia's
idmapper `flush_cache` from `post_migrate` for the duration of test-DB creation and flushes once
at the end — Django emits `post_migrate` once per installed app (90+), and each handler call ran
a full `gc.collect()` (~0.4s), ~29s of pure GC per invocation.

**Why:** measured on `world.game_clock` (109 tests, ~3s of actual test execution): a fast-tier
invocation cost 35-60s of wall clock, ~90% of it fixed per-invocation overhead — ~29s the
`gc.collect` storm, ~20s building an identical 775-table schema every run, the rest
imports/discovery. With both fixes a warm run is ~10s. Since the overhead is per-invocation, no
amount of test-selection narrowing could recover it, and agents' edit→test loops were paying it
dozens of times per session.

**Rejected:** (a) a warm test-daemon (preforked process holding Django + schema) — largest
possible win but a new moving part to babysit; unnecessary once the invocation floor is ~10s.
(b) keying the cache on migration-file hashes — the staleness trap ADR-0083 documents; model-state
fingerprinting has no migration recorder involvement (the fast tier runs `DisableMigrations`) and
a false mismatch merely rebuilds (~15s), never reuses stale schema. Fingerprint variants with
byte-identical schemas were observed (schema-irrelevant repr drift), which is why the runner keeps
several templates and treats misses as cheap. **Trade-offs:** on a cache hit, `post_migrate`
receivers do not fire during DB creation — their row side-effects are baked into the template and
the one semantic in-process receiver (Evennia's `flush_cache`) is invoked explicitly by the
runner; a future receiver with per-process in-memory side effects would need the same treatment.
`ARX_SCHEMA_CACHE=0` bypasses the cache entirely.

> Status: accepted · Related: ADR-0083 (CI/test schema from model state), ADR-0013 (schema-only
> migrations pre-production)

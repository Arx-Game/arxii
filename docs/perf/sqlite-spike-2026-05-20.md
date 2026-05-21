# SQLite spike — per-app survey

Branch: `feature/test-speedups`. Settings: `server.conf.sqlite_test_settings`
(SQLite `:memory:`, `MIGRATION_MODULES = _DisableMigrations()` so schema builds
from current model state).

After the full-suite SQLite run revealed cross-test contamination is the
dominant failure mode (tests pass in isolation, break in suite), the spike
pivoted to **per-app SQLite as a per-app inner-loop tool**. The full suite
stays on the Postgres parity tier.

## Per-app survey (with REFRESH vendor guards landed at `e3b718e7`)

| App | Tests | SQLite time | Broken | % broken | Tier |
|---|---:|---:|---:|---:|---|
| **Clean — SQLite works perfectly** ||||||
| `world.action_points` | 60 | 0.760s | 0 | 0% | SQLite |
| `world.forms` | 48 | 0.690s | 0 | 0% | SQLite |
| `world.achievements` | 53 | 1.056s | 0 | 0% | SQLite |
| `world.game_clock` | 104 | 1.231s | 0 | 0% | SQLite |
| `world.skills` | 79 | 1.488s | 0 | 0% | SQLite |
| `world.relationships` | 88 | 3.039s | 0 | 0% | SQLite |
| `flows` | 253 | 7.974s | 0 (4 skip) | 0% | SQLite |
| **Mostly clean — SQLite viable, ≤5% need `@tag("postgres")`** ||||||
| `world.checks` | 97 | 1.136s | 1 | 1.0% | SQLite |
| `world.events` | 94 | 3.946s | 1 | 1.1% | SQLite |
| `world.missions` | 246 | 5.278s | 4 | 1.6% | SQLite |
| `world.journals` | 56 | 1.890s | 1 | 1.8% | SQLite |
| `world.mechanics` | 255 | 3.956s | 5 | 2.0% | SQLite |
| `world.progression` | 255 | 7.413s | 6 | 2.4% | SQLite |
| `world.conditions` | 235 | 14.713s | 8 | 3.4% | SQLite |
| **Partial — SQLite has noticeable rough edges (5-15%)** ||||||
| `world.combat` | 343 | 27.735s | 19 | 5.5% | SQLite (with caveats) |
| `world.items` | 248 | 11.818s | 20 | 8.1% | SQLite (with caveats) |
| `world.vitals` | 35 | 0.334s | 3 | 8.6% | SQLite (with caveats) |
| `actions` | 203 | 5.131s | 21 | 10.3% | SQLite (with caveats) |
| **Broken — falls back to PG-only** ||||||
| `world.roster` | 112 | 9.367s | 50 | 44.6% | PG only |
| `world.character_sheets` | 202 | 6.850s | 190 | 94.1% | PG only |
| **Carved out at the settings level (migrations disabled)** ||||||
| `world.magic` | — | — | — | — | PG only |
| `world.scenes` | — | — | — | — | PG only |
| `world.codex` | — | — | — | — | PG only |
| `world.areas` | — | — | — | — | PG only |
| `world.societies` | — | — | — | — | PG only |

## Time savings per tier

- **14 SQLite-clean / mostly-clean apps** sum to **2,070 tests in ~54.6s** on
  SQLite. On Postgres these would be roughly 2-3× that (extrapolating from
  missions: 5.3s SQLite → 18.8s PG). So the SQLite path saves **~80-120s
  per inner-loop invocation** when working in this set of apps.
- **Single-app SQLite typical case: 1-15s.** Compare to PG single-app: 5-30s
  including DB setup. Roughly 2-4× faster per invocation.
- **Full-suite Postgres still required** as the parity gate (CI shards, local
  `arx test --postgres` before push). Phase 5 squashing + Phase 6.2 optional
  tmpfs will speed that up too.

## Pattern: which apps work on SQLite, which don't

**Works cleanly:** engine-style apps with shallow fixture graphs. Their tests
create objects via factory directly, don't depend on Evennia's initial-setup
side effects, and use minimal cross-app FK chains. Examples: missions, flows,
game_clock, achievements, action_points, skills, relationships.

**Fails on SQLite:** apps whose fixtures recursively pull in the full
character graph (Character → CharacterSheet → Persona → RosterEntry →
RosterTenure → Account → ...). PG defers FK checks until commit and silently
accepts intermediate states; SQLite enforces immediately and catches dangling
references at teardown. The biggest offender (`character_sheets` itself) is
the source-of-truth anchor every other app FKs into — its tests assume the
PG migration chain has set up scaffolding that the SQLite tier skips.

**Carved out at settings level:** apps with raw `REFRESH MATERIALIZED VIEW`,
table partitioning, or complex schema-evolution histories that SQLite can't
replay (magic, scenes, codex, areas, societies). Their migrations are
disabled in `sqlite_test_settings`; their tests can't be run with `--sqlite`.

## Recommendation

Ship `arx test --sqlite <app>` as a developer convenience for the 14 known-
clean apps. Document the working set in CLAUDE.md. For apps not in the set,
the developer falls back to `arx test --postgres <app>`. Full-suite testing
(both inner-loop and pre-push gate) stays on Postgres.

## Next work

1. **Phase 3.2** — decorate the ~50 SQLite failures across the 7 mostly-clean
   apps with `@tag("postgres")`. After that, those apps should be 0% broken
   on SQLite.
2. **Phase 4.1+4.2** — wire `just test-fast <app>` to default to `--sqlite`,
   `just test-parity` to default to `--postgres`. Document in CLAUDE.md.
3. **Phase 5** — PG-tier squashing. Still valuable: the PG tier is the
   parity gate for every PR and the only option for character_sheets/roster
   work.

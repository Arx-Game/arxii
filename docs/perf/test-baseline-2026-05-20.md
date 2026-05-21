# Test baseline — 2026-05-20

Branch: `feature/test-speedups` (HEAD `44509d49`).
Machine: Windows 11 Home, local PostgreSQL 17 on disk (NOT tmpfs).

## Captures

| Scope | Tests | Serial fresh-DB | --parallel (8 workers) | --keepdb |
|---|---:|---:|---:|---:|
| `world.missions` | 246 | **18.841s** | **23.539s** | _TBD_ |
| Full suite | 7,529 | **2,035.236s** (33m 55s) | _capture in flight_ | _TBD_ |
| `world.stories` | _TBD_ | _TBD_ | n/a | n/a |
| `world.checks + world.mechanics` | _TBD_ | _TBD_ | n/a | n/a |

## Migration-playback share

| Scope | Total | Migrate block | Migrate share |
|---|---:|---:|---:|
| `world.missions` | _TBD_ | _TBD_ | _TBD_ |

## Observations against plan gates

### Gate 1: --parallel must give ≥2x local speedup → "investigate runner config" if not

- **Missions only:** serial 18.841s vs --parallel 23.539s — parallel is **25% SLOWER**.
- **Not a runner bug.** For 246 tests across 8 workers, per-worker DB-clone overhead + worker startup cost exceeds the parallelism gain. Each worker only owns ~31 tests after splitting; the Django docs explicitly note that small suites can regress under --parallel.
- The gate's real test is the **full suite** (~7,000+ tests) where the per-worker cost amortizes. Full-suite numbers below will determine whether `just test-fast` should default to --parallel.

### Gate 2: migration playback share ≥20% of total fresh-DB → squashing worthwhile

- _TBD_ — needs the -v 2 capture.

### Gate 3: full-suite delta after each subsequent phase ≥30%

- _Baseline pending._

## CI-side reference (for comparison)

CI runs each shard with `arx test --parallel <shard apps>` against a tmpfs Postgres
(`ci.yml:80-91`). Local does NOT have tmpfs; this baseline therefore represents the
worst-case (disk-bound) local-dev path.

Shard test counts as of `44509d49` (per `ci.yml:46-76`):
- shard-1: ~1,461 (magic 887 + combat 328 + missions 246)
- shard-2: ~1,465 (stories 759 + mechanics 258 + conditions 190 + items 198 + areas 39 + instances 21)
- shard-3: ~1,604 (flows 259 + progression 255 + scenes 227 + character_sheets 202 + character_creation 200 + gm 120 + actions 115 + locations 187 + traits 39)
- shard-4: ~1,447 (all remaining apps; see ci.yml:67-76)

# Pre-squash audit — RunPython data migrations (2026-05-20)

Branch: `feature/test-speedups` (HEAD `44509d49`). Scans `src/world`, `src/evennia_extensions`,
`src/typeclasses`, `src/flows`. 10 RunPython migrations found.

**Methodology:** "critical for fresh-DB tests" = the RunPython performs work that affects
DB state a fresh test DB will rely on (e.g., seeds a lookup-table row tests reference by
name). "No-op on fresh DB" = the RunPython operates on existing rows that don't exist in a
fresh test DB (backfills, wipes-before-alter, conditional seeds that silently skip when
prerequisites are absent).

## Findings

| App | Migration | Purpose | Critical? | Squash action |
|---|---|---|---|---|
| `world.progression` | `0002_social_engagement_kudos_category` | Seeds `KudosSourceCategory(name="social_engagement")` lookup row | **YES** | **Preserve as RunPython in squashed migration** |
| `world.magic` | `0058_migrate_roomresonance_to_cascade` | Copies legacy `RoomResonance` rows → `LocationStatModifier` cascade rows | No | Drop — no rows on fresh DB |
| `world.magic` | `0059_backfill_resonancegrant_source_room_profile` | Backfills `ResonanceGrant.source_room_profile` from legacy FK | No | Drop — no rows on fresh DB |
| `world.magic` | `0052_accept_soul_tether_placeholder_grants` | Grants `accept_soul_tether` Ritual to all Paths | No | Drop — explicit `try: Ritual.objects.get(...); except: return` makes it a no-op on fresh DB; seeding happens via `wire_soul_tether_content()` at fixture time |
| `world.magic` | `0048_alter_pendingstageadvanceoffer_scene` | Deletes `PendingStageAdvanceOffer` rows with null `scene` before AlterField | No | Drop — no rows on fresh DB |
| `world.covenants` | `0005_charactercovenantrole_covenant_fk_and_engaged` | Wipes `CharacterCovenantRole` rows before AlterField to non-null FK | No | Drop — no rows on fresh DB |
| `world.conditions` | `0007_remove_treatmentattempt_unique_treatment_attempt_per_helper_scene_and_more` | Backfills `TreatmentAttempt.once_per_scene_guard` from related template | No | Drop — no rows on fresh DB |
| `world.conditions` | `0005_soulfray_retrofit` | Sets Soulfray condition's resist parameters (conditional on template existence) | No | Drop — explicit `if soulfray is None: return` makes it a no-op on fresh DB |
| `world.vitals` | `0002_charactervitals_base_max_health_and_more` | Backfills `base_max_health` from `max_health` via bulk UPDATE | No | Drop — no rows on fresh DB |
| `flows` | `0003_trigger_scope_source` | Wipes `Trigger` rows before adding non-null fields | No | Drop — no rows on fresh DB; pre-Phase-4 historical wipe |

## Summary

- **1 critical RunPython** (`progression.0002`) — must be preserved verbatim (or inlined into a
  data-only squashed migration) for fresh-DB tests that reference the
  `social_engagement` KudosSourceCategory by name.
- **9 no-op on fresh DB** — operate on existing rows that don't exist in a fresh test DB.
  These can be dropped at squash time.

**No fixtures found** in version control (per project convention — fixtures are gitignored;
`MEMORY.md` confirms).

## Squash strategy

Per the plan's "Per app, repeat" loop:

1. When squashing `world.progression`, `arx manage squashmigrations` will fold migrations into
   `0001_squashed_<date>.py`. **Manually verify** the seed RunPython is preserved — Django
   keeps RunPython in squashes by default, but it's worth confirming the migration file has
   it before deleting the originals.
2. When squashing the other 9 apps, the RunPython operations can be dropped from the squashed
   migration since they're no-ops on a fresh DB. Django's `squashmigrations` keeps them by
   default; the developer can manually edit the squashed file to remove the no-op ones for
   cleanliness, OR leave them (they cost nothing on a fresh DB since they no-op anyway).
   Recommendation: **leave them in** — manual editing risks human error. The squash benefit
   is in collapsing the AlterField/AddField/RemoveField/CreateModel chain, not in pruning
   data migrations.

## Gate result

Per the plan's gate: **no critical RunPython is >20 lines or has complex deps**. The single
critical case (`progression.0002`) is 13 lines of straightforward `update_or_create` against
a stable `KudosSourceCategory` schema. **Phase 3 squashing can proceed** when its
prerequisites (baseline + post-squash measurement) say so.

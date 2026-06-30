# Progression App

XP, kudos, development points, unlock system, and class-level advancement receipts.

**System doc:** `docs/systems/progression.md`

---

## Class-Level Advancement (advancement.py + models/advancement.py)

Every class-level step — whether a within-tier advance (Ritual of the Durance) or a
tier crossing (Audere Majora) — writes through one shared spine:

```
apply_class_level_advance(sheet, *, level_after)
```

This is the **in-play advancement** level-write spine shared by the Ritual of the
Durance and Audere Majora. A separate path exists for CG/setup time:
`world.classes.set_primary_class_level` is an independent upsert that also calls
`recompute_max_health_with_threads` but does **not** delegate to
`apply_class_level_advance`. Never mutate `CharacterClassLevel` rows directly
outside these two sanctioned paths.

### AbstractClassLevelAdvancement (abstract model)

Abstract base shared by `ClassLevelAdvancement` (this app) and
`AudereMajoraCrossing` (`world/magic/audere_majora.py`). Carries:

- `scene` (FK → `scenes.Scene`, SET_NULL)
- `declaration_interaction` (FK → `scenes.Interaction`, soft FK — partitioned table)
- `level_before`, `level_after` (PositiveSmallIntegerField)
- `created_at` (auto timestamp)

### ClassLevelAdvancement (concrete — within-tier receipts)

Written by `advance_class_level_via_session` for each inductee in a Ritual of the
Durance session. Additional fields beyond the abstract base:

- `character_sheet` FK → `CharacterSheet` (CASCADE; `related_name="class_level_advancements"`)
- `character_class` FK → `CharacterClass` (PROTECT; `related_name="durance_advancements"`)
- `officiant` FK → `CharacterSheet` (SET_NULL; the trainer who inducted the advance)
- `ritual` FK → `Ritual` (PROTECT; the `Ritual` row that fired the session)

---

## Ritual of the Durance — service contract

`advance_class_level_via_session(*, session: RitualSession) -> list[ClassLevelAdvancement]`

Called by `fire_session` as `fn(session=locked)` **inside the session's transaction**.
Raises `ClassLevelAdvancementError` subclasses on failure — the transaction rolls back
and the session survives for retry.

Per inductee (ACCEPTED participants who are not the initiator):

1. Resolve primary class level → `target_level = level + 1`.
2. Refuse tier boundaries via `TierBoundaryRequiresCrossing` (those belong to Audere Majora).
3. Officiant guard — `assert_can_officiate(officiant_sheet, inductee_sheet, target_level)`.
4. Authored `ClassLevelUnlock` check — `AdvancementRequirementsNotMet` when absent or unmet.
5. Post testament oration (+ cited deeds) as a POSE via `_post_testament`.
6. `apply_class_level_advance`, then the **POTENTIAL semi-crossing** (step 6b), then
   `ClassLevelAdvancement.objects.create(...)`.

6b. **Level-3 POTENTIAL semi-crossing (#1579).** When the advance enters a new path
   stage (past the step-2 tier-boundary refusal, that is only the PROSPECT→POTENTIAL
   transition at level 3) and the inductee has declared an eligible advanced path
   (`participant_kwargs["path_id"]`, else their `PathIntent`),
   `_maybe_semi_cross_into_potential_path` switches them onto it and grants its
   gift+techniques via the shared `cross_into_path` seam (`advancement.py`) — the
   **same machinery an Audere Majora crossing uses, but with no crossing ceremony**.
   Optional + non-breaking: a 2→3 advance with no declared path is level-only.

### Narrative ↔ mechanical mapping

| Narrative term | Mechanical term | Notes |
|----------------|-----------------|-------|
| "the Durance" | A character's life-arc | Backend stays Class/Level-named |
| "Ritual of the Durance" | `Ritual` (SERVICE / INDUCTION) | Seeded by `RitualOfTheDuranceFactory` |
| tier crossing (5→6, 10→11, …) | Audere Majora (`cross_threshold`) | True crossings; ceremony + deed |
| **semi-crossing (2→3, PROSPECT→POTENTIAL)** | Durance + `cross_into_path` (#1579) | Switches path + grants gift/techniques; **no** Audere Majora |
| within-tier advance (1→2 … 4→5, 6→7 …) | `ClassLevelAdvancement` receipt | This module |
| officiant | trainer / `ClassLevelAdvancement.officiant` | Same Path lineage, higher level |
| testament | `participant_kwargs["testament"]` | Player-composed oration; no deed minted |
| chosen Potential path | `participant_kwargs["path_id"]` / `PathIntent` | Drives the level-3 semi-crossing target |

---

## Exceptions (exceptions.py)

All carry `user_message` for safe 400 API responses.

| Exception | Raised by |
|-----------|-----------|
| `ClassLevelAdvancementError` | base |
| `TierBoundaryRequiresCrossing` | `advance_class_level_via_session` (boundary levels) |
| `AdvancementRequirementsNotMet` | `advance_class_level_via_session` (unlock/requirements) |
| `OfficiantIneligibleError` | `assert_can_officiate` (level or lineage gate) |

---

## Key rules

- **Never hardcode advancement logic in commands.** All level-write logic lives in
  `apply_class_level_advance`; receipt creation lives in `advance_class_level_via_session`.
- **Legend qualifies; it is never spent.** `LegendRequirement` + `ClassLevelUnlock` gate
  advancement; no legend rows are consumed or minted for within-tier advances.
- **No boons, no resonance grants.** A Durance session is just a Scene — normal
  social-scene benefits apply (pose endorsements, entry endorsements, etc.) but the
  advancement service adds no special grants.
- **Telnet follow-up open (#1700).** `RitualSession` dispatch is REST-only today; telnet
  drivability of the Ritual of the Durance (a `CmdRitual` adapter mirroring
  `CovenantInductionAdapter`/`BannerCallAdapter`, passing `testament` + the #1579
  `path_id`) is tracked in **#1700** (under the telnet-E2E umbrella #1328).

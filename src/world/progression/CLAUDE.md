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

This is the *only* code path that mutates `CharacterClassLevel.level`
(`world.classes.set_primary_class_level` delegates to it). Never mutate
`CharacterClassLevel` rows directly.

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
6. `apply_class_level_advance` + `ClassLevelAdvancement.objects.create(...)`.

### Narrative ↔ mechanical mapping

| Narrative term | Mechanical term | Notes |
|----------------|-----------------|-------|
| "the Durance" | A character's life-arc | Backend stays Class/Level-named |
| "Ritual of the Durance" | `Ritual` (SERVICE / INDUCTION) | Seeded by `RitualOfTheDuranceFactory` |
| tier crossing (5→6, 10→11, …) | Audere Majora (`cross_threshold`) | Never handled by the Durance rite |
| within-tier advance (1→2 … 4→5, 6→7 …) | `ClassLevelAdvancement` receipt | This module |
| officiant | trainer / `ClassLevelAdvancement.officiant` | Same Path lineage, higher level |
| testament | `participant_kwargs["testament"]` | Player-composed oration; no deed minted |

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
- **Telnet follow-up open.** `RitualSession` dispatch is REST-only today; telnet
  drivability (session-layer `action.run` / `CmdRitual` convergence) is a tracked
  follow-up issue.

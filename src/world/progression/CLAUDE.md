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
- `witnesses` M2M → `scenes.Persona` (`related_name="witnessed_advancements"`); populated
  by `_record_witnesses` inside `advance_class_level_via_session` via `scene_witness_personas`,
  excluding the inductee and officiant. Applies to both REST and telnet paths (shared service).

### DuranceTrainingSite [BUILT & WIRED — #1700]

A room registered as a training site, bound to a trainer-of-record (`officiant`). Lets
an inductee self-conduct their Durance at that room without a live higher-level PC present —
the eligibility gate (`assert_can_officiate`) runs unchanged on the stored trainer.

Fields:
- `room_profile` FK → `evennia_extensions.RoomProfile` (PROTECT; `related_name="durance_training_sites"`)
- `officiant` FK → `CharacterSheet` (PROTECT; `related_name="durance_training_roles"`)
- `training_path` FK → `classes.Path` (SET_NULL, nullable; display/filtering hint only —
  the real gate is `assert_can_officiate`). Named `training_path`, **not** `path` — the
  Evennia idmapper metaclass shadows a bare `path` attribute.
- `is_active` Bool (default True)
- Unique constraint on `(room_profile, officiant)`.

Factory: `DuranceTrainingSiteFactory`.

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
4b. **Purchased XP unlock check** — `_assert_unlock_purchased` requires a `CharacterUnlock`
   receipt for this exact (class, target_level), raising `AdvancementUnlockNotPurchasedError`
   (names the unlock + its XP cost) when missing. This is an *additional* gate stacked
   alongside step 4, not a replacement for it — see "Multi-gate rule" below.
5. Post testament oration (+ cited deeds) as a POSE via `_post_testament`.
6. `apply_class_level_advance`, then the **POTENTIAL semi-crossing** (step 6b), then
   `ClassLevelAdvancement.objects.create(...)`.
7. `_record_witnesses(receipt, scene, ...)` — records scene personas (excluding inductee +
   officiant) into `receipt.witnesses` via `scene_witness_personas`.

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
| training site | `DuranceTrainingSite` — room + trainer-of-record | Enables site-convened sessions (#1700) |
| trainer-of-record | `DuranceTrainingSite.officiant` | Provides automated officiant in a site-convened session |

---

## Exceptions (exceptions.py)

All carry `user_message` for safe 400 API responses.

| Exception | Raised by |
|-----------|-----------|
| `ClassLevelAdvancementError` | base |
| `TierBoundaryRequiresCrossing` | `advance_class_level_via_session` (boundary levels) |
| `AdvancementRequirementsNotMet` | `advance_class_level_via_session` (unlock/requirements) |
| `OfficiantIneligibleError` | `assert_can_officiate` (level or lineage gate) |
| `NoDuranceSiteError` | `convene_durance_at_site` (no active site with eligible trainer in room) |

---

## Selectors (selectors.py) [BUILT & WIRED — #1700]

Two new selectors support the telnet Durance surface:

- `eligible_advanced_paths_for(sheet)` — returns active child `Path` objects the character
  can semi-cross into at their next level's stage (mirrors the gate in
  `advance_class_level_via_session`). Empty when not at a stage boundary or no current path.
- `resolve_advanced_path_by_name(sheet, name)` — case-insensitive match of a name string
  against `eligible_advanced_paths_for(sheet)`; returns the matched `Path` or `None`.

## Service — site-convened sessions [BUILT & WIRED — #1700]

`convene_durance_at_site(*, inductee_sheet, room) -> RitualSession`

One-shot drafts a Durance `RitualSession` with the site's trainer-of-record as initiator
(officiant). Does **not** fire — the inductee's subsequent `ritual join` auto-fires the
session (detected by `DuranceAdapter.should_auto_fire`). Raises `NoDuranceSiteError` when
no active `DuranceTrainingSite` with an eligible trainer exists in the room.

## Telnet commands [BUILT & WIRED — #1700]

### CmdDurance (`durance`, Progression cmdset)

Readiness hub + site-convene surface. Mirrors `CmdSanctum` for subverb dispatch.

```
durance [status]                      — show level, unlock gate, eligible paths, intent, site
durance intent <path name or id>      — declare path intent (reuses SetPathIntentAction)
durance intent clear                  — clear path intent (reuses ClearPathIntentAction)
durance convene                       — open a site-convened Durance session at this room
```

`durance convene` calls `convene_durance_at_site`; the returned session pk is echoed back
so the inductee can issue `ritual join <id> testament=<oration> path=<name>`.

### DuranceAdapter (in `commands/ritual_adapters.py`)

Registered on the `advance_class_level_via_session` service path. Translates:

- `parse_join`: `testament=<oration>` → `participant_kwargs["testament"]`;
  `path=<name>` → `participant_kwargs["path_id"]` via `resolve_advanced_path_by_name`.
- `should_auto_fire`: returns `True` when `session.session_kwargs["site_convened"] == "1"` —
  the marker set by `convene_durance_at_site` at draft time. Returns `False` for any session
  opened via plain `ritual draft`, including sessions where the officiant also happens to be a
  `DuranceTrainingSite` trainer-of-record at another room. The check is on the session-level
  marker only; no `DuranceTrainingSite` DB query is made here.
- `parse_draft`: no-op (base `RitualDraftAdapter` behaviour — the officiant supplies
  nothing extra at draft time).

## Key rules

- **Never hardcode advancement logic in commands.** All level-write logic lives in
  `apply_class_level_advance`; receipt creation lives in `advance_class_level_via_session`.
- **Legend qualifies; it is never spent.** `LegendRequirement` + `ClassLevelUnlock` gate
  advancement; no legend rows are consumed or minted for within-tier advances.
- **Multi-gate rule — XP unlocks, never grants.** The Durance gate is not a single
  check: `check_requirements_for_unlock` (authored `Requirement` rows — Legend,
  Relationships, Traits, …) AND the purchased XP unlock (`CharacterUnlock`, bought via
  `progression unlock class=<id>`) must **both** pass. XP buys a gate, not the
  advance itself — removing either gate to "fix" a stuck character is the wrong
  move; wire the missing purchase instead. See the "XP unlocks, never grants — major
  acquisitions stack gates" ADR.
- **No boons, no resonance grants.** A Durance session is just a Scene — normal
  social-scene benefits apply (pose endorsements, entry endorsements, etc.) but the
  advancement service adds no special grants.
- **Telnet Durance is built (#1700).** Both a live-officiant ceremony (initiated by the
  trainer with `ritual draft`, completed by `ritual fire`) and a site-convened session
  (`durance convene` → `ritual join`) are supported. The rite always runs through the
  `ritual` session lifecycle; `CmdDurance` is setup + status only.

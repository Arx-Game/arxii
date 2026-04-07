# Combat Review Refactor Design

**Date:** 2026-04-07
**Context:** Code review feedback on combat PR from TehomCD, addressing denormalization, NPC linkage, ephemeral vs persistent state, and health ownership.

## Design Principles Applied

- **No denormalization unless genuinely per-instance.** Data derivable from relationships should not be copied into local fields. Data integrity over join savings.
- **Combat is the encounter, not the character.** Health, status, and speed belong to the character (or their vitals/covenant role). Combat records what happened, not who the character is.
- **History matters for narrative.** Round actions stay in the DB so scene viewers can reconstruct combat flow — "how did I get this scar?" needs an answer.

## Model Changes

### CombatParticipant — Strip to Join Table

**Remove:**
- `health` / `max_health` — move to CharacterVitals (combat reads/writes there directly)
- `status` — move to CharacterVitals (already partially there)
- `dying_final_round` — move to CharacterVitals
- `base_speed_rank` — derivable from `covenant_role.speed_rank`
- `speed_modifier` — should come from active conditions (`turn_order_modifier` already exists on conditions)
- `health_percentage` property — moves to CharacterVitals
- `wound_description` property — moves to CharacterVitals

**Keeps:**
- `encounter` (FK to CombatEncounter)
- `character_sheet` (FK to CharacterSheet)
- `covenant_role` (FK to CovenantRole, nullable)
- Unique constraint on (encounter, character_sheet)

CombatParticipant becomes a lightweight join table: "this PC is in this fight with this role."

### CombatEncounter — Remove Derivable FKs

**Remove:**
- `story` (FK) — derivable from scene → episode → story
- `episode` (FK) — derivable from scene → episode

**Keeps:**
- `encounter_type`, `scene`, `round_number`, `status`, `risk_level`, `stakes_level`, `created_at`

Risk and stakes stay because they're genuinely per-encounter values set by the GM. Two combats in the same scene could have different risk/stakes. These may eventually be inherited from a story-level model when GM tooling is built, but that's future work.

### CombatOpponent — Add Persona Linkage

**Add:**
- `persona` (FK to `scenes.Persona`, nullable, blank) — links to a story NPC's identity when the opponent is a named character rather than generic fodder

**Keeps all existing fields** — NPCs don't have CharacterVitals yet. Their health/stats are genuinely per-encounter combat state. When NPC character sheets are built in the future, health may migrate to their own vitals model, but that's not this refactor.

### CharacterVitals — Becomes Health Authority

**Add:**
- `health` (IntegerField) — current health
- `max_health` (PositiveIntegerField) — stored, recalculated when inputs change (level up, new covenant role, etc.)
- `dying_final_round` (BooleanField, default=False)

**Add properties** (moved from CombatParticipant):
- `health_percentage` — `health / max_health`
- `wound_description` — maps percentage to descriptive text

Combat services write damage directly to CharacterVitals. No sync step needed.

### Round Action Models — Keep As-Is

**CombatRoundAction** and **CombatOpponentAction** remain persistent Django models. They record what each participant chose and what happened — valuable for scene history and narrative context. All fields are references (FKs to techniques, opponents, etc.), not denormalized copies.

## Service Changes

### Remove
- `sync_vitals_from_combat()` — no longer needed; vitals is the source of truth, not a sync target

### Modify
- `add_participant()` — drop `max_health` parameter; participant is just encounter + character_sheet + optional covenant_role
- `apply_damage_to_participant()` — write to `character_sheet.vitals.health` instead of `participant.health`; status checks read from vitals
- `resolve_round()` / resolution order — read `participant.covenant_role.speed_rank` directly instead of `participant.base_speed_rank`; speed modifiers come from condition queries
- All health threshold checks — read from vitals instead of participant

### Speed Resolution
- Base speed: `participant.covenant_role.speed_rank` (join, not denormalized)
- Speed modifiers: query active conditions with `turn_order_modifier` on the character
- No-role default: `NO_ROLE_SPEED_RANK` (20) when `covenant_role is None`
- NPC speed: `NPC_SPEED_RANK` constant (15) as before

## Migration Notes

- Squash combat migrations (still in dev, single migration preferred)
- Add new fields to CharacterVitals
- Data migration: if any dev data exists in CombatParticipant health fields, it doesn't need preserving (dev/test data only)

## What This Does NOT Change

- ThreatPool / ThreatPoolEntry / BossPhase — NPC behavior definitions are content, not denormalized
- ComboDefinition / ComboSlot / ComboLearning — combo system is clean
- Round action models — kept for historical narrative value
- Asymmetrical combat design — unchanged, story NPCs as Persona-linked opponents still act as automated foes

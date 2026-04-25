# Magic App

The magic system for Arx II. Power flows from identity and connection.

## Core Concepts

- **Affinity**: Three magical sources (Celestial, Primal, Abyssal) - proper domain models with optional ModifierTarget link
- **Aura**: A character's soul-state as percentages across affinities
- **Resonance**: Style tags that define magical identity - proper domain models with FK to Affinity and optional ModifierTarget link
- **Motif**: Character-level magical aesthetic containing resonances and facets
- **Facet**: Hierarchical imagery/symbolism (Spider, Silk, Fire) assigned to resonances
- **Threads**: Per-character attachments anchored to a trait/technique/item/room/
  relationship-track/relationship-capstone. Each Thread channels a single
  Resonance (currency) and accrues `developed_points` → `level` via the Imbuing
  ritual. The legacy 5-axis Thread family was removed and replaced in Phase 4
  of the resonance pivot.
- **Resonance currency**: `CharacterResonance.balance` is spendable currency
  earned via `grant_resonance` (Spec C surfaces will write here) and spent
  via `spend_resonance_for_imbuing` (advances Thread level) or
  `spend_resonance_for_pull` (activates tier-1/2/3 pull effects during an
  action or combat round). `lifetime_earned` is monotonic audit.
- **ThreadWeaving**: Acquisition layer. `ThreadWeavingUnlock` is the authored
  catalog (per anchor scope); `CharacterThreadWeavingUnlock` is the per-character
  purchase record; `ThreadWeavingTeachingOffer` is the teacher-facing offer
  (mirrors `CodexTeachingOffer`).
- **Ritual**: Authored magical procedures with dual dispatch —
  `execution_kind=SERVICE` invokes a registered service function path;
  `execution_kind=FLOW` invokes a `FlowDefinition`. Imbuing is the first
  SERVICE-dispatched ritual and wraps `spend_resonance_for_imbuing`.

## Models

### Domain Models
- `Affinity` - Three magical affinities (Celestial, Primal, Abyssal) with optional OneToOne to ModifierTarget
- `Resonance` - Magical identity tags with FK to Affinity, optional opposite (self OneToOne), optional OneToOne to ModifierTarget

### Character State
- `CharacterAura` - Tracks a character's affinity percentages (celestial/primal/abyssal)
- `CharacterResonance` - Per-character per-resonance row. Identity anchor AND
  spendable currency bucket. Fields: `character_sheet` FK, `resonance` FK,
  `balance` (spendable), `lifetime_earned` (monotonic audit), `claimed_at`,
  `flavor_text`. Unified per Spec A §2.2 — the old `scope`/`strength`/`is_active`
  shape was dropped; row existence replaces `is_active`.
- `CharacterAnima` - Magical resource (anima) tracking

### Gifts & Techniques
- `Gift` - Thematic collections of magical techniques (M2M to Resonance)
- `TechniqueStyle` - How magic manifests (Manifestation, Subtle, Performance, Prayer, Incantation) with `allowed_paths` M2M
- `EffectType` - Types of magical effects (Attack, Defense, Movement, etc.)
- `Restriction` - Limitations that grant power bonuses (Touch Range, etc.)
- `IntensityTier` - Configurable thresholds for power intensity (Minor, Moderate, Major)
- `Technique` - Player-created magical abilities with level, style, effect type
- `CharacterGift` - Links characters to known Gifts
- `CharacterTechnique` - Links characters to known Techniques

### Anima Recovery
- `CharacterAnimaRitual` - Personalized recovery ritual (stat + skill + resonance)
- `AnimaRitualPerformance` - Historical record of ritual performances

**Note:** During character creation, the magic stage uses a simplified cantrip selection
system. Anima rituals are set up post-CG. CharacterAnimaRitual references Resonance directly.

### Cantrips (Character Creation)
- `Cantrip` - Staff-curated technique templates for CG magic stage selection
- A cantrip IS a baby technique — at CG finalization it creates a real Technique
- Fields: archetype (display grouping), effect_type, style, base_intensity, base_control, base_anima_cost
- Mechanical fields are hidden from the player; they only see name/description/archetype/facets
- Cantrips are filtered by character's Path via `?path_id=` query param (style must be in Path's allowed_styles)
- New players see only their path's cantrips; returning players (advanced mode) see all cantrips
- 5 styles map 1:1 to 5 Prospect paths: Manifestation→Steel, Subtle→Whispers, Performance→Voice, Prayer→Chosen, Incantation→Tome

### Motif System
- `Motif` - Character-level magical aesthetic
- `MotifResonance` - Resonances in a motif (from gifts or optional)
- `Facet` - Hierarchical imagery/symbolism (Category > Subcategory > Specific)
- `CharacterFacet` - Links characters to facets with resonance assignments
- `MotifResonanceAssociation` - Links resonances to facets in a motif

### Thread System (Resonance Pivot Spec A)

**Authored catalogs (lookup, SharedMemoryModel):**
- `ThreadPullCost` - Per-tier pull cost knobs (tier 1/2/3: `resonance_cost`,
  `anima_per_thread`, `label`). Tuning surface — values here are data; cost
  *shape* lives in `spend_resonance_for_pull`.
- `ThreadXPLockedLevel` - XP-locked boundary price list (`level` on the
  internal 10/20/30... scale, `xp_cost`). Mirrors skills' XP locks.
- `ThreadPullEffect` - Authored pull-effect template keyed
  `(target_kind, resonance, tier, min_thread_level)`. `effect_kind` chooses
  payload column: `FLAT_BONUS` / `INTENSITY_BUMP` / `VITAL_BONUS` (+ `vital_target`) /
  `CAPABILITY_GRANT` (FK to `CapabilityType`) / `NARRATIVE_ONLY`. Tier 0 is
  always-on passive; tiers 1–3 are paid pulls. `clean()` + CheckConstraints
  enforce payload/effect_kind shape.
- `ThreadWeavingUnlock` - Authored catalog of "you can weave threads on X"
  unlocks. Same discriminator + typed-FK pattern as Thread: `unlock_trait`,
  `unlock_gift`, `unlock_item_typeclass_path`, `unlock_room_property`,
  `unlock_track`. `xp_cost` + M2M to `Path` (in-band) + `out_of_path_multiplier`.
- `ImbuingProseTemplate` - Fallback prose for the Imbuing ritual keyed on
  `(resonance, target_kind)`. The row with both NULL is the universal fallback.
- `Ritual` - Authored magical procedure with dual dispatch
  (`execution_kind=SERVICE` → `service_function_path`; `execution_kind=FLOW` →
  FK to `FlowDefinition`). `site_property` optionally gates where it can be
  performed.
- `RitualComponentRequirement` - FK to `Ritual` + FK to `ItemTemplate` with
  `quantity` and optional `min_quality_tier`. Consumed during ritual dispatch.

**Per-thread and per-character records:**
- `Thread` - The thread row. Discriminator (`target_kind`) + typed FKs:
  `target_trait`, `target_technique`, `target_object` (ITEM and ROOM),
  `target_relationship_track`, `target_capstone`. Fields: `owner` (FK
  CharacterSheet), `resonance` (FK Resonance), `name`, `description`,
  `developed_points`, `level`, timestamps, `retired_at` (soft-retire).
  All typed FKs use `on_delete=PROTECT`. Three layers of integrity: `clean()`,
  per-kind CheckConstraints, per-kind partial UniqueConstraints.
- `ThreadLevelUnlock` - Per-thread XP-locked-boundary receipt. Unique per
  `(thread, unlocked_level)`. Records that a thread paid XP to cross a
  specific boundary (20, 30, ...).
- `CharacterThreadWeavingUnlock` - Per-character purchase record linking a
  CharacterSheet to a ThreadWeavingUnlock. Captures actual `xp_spent`
  (in-band uses unlock.xp_cost; out-of-band multiplies by
  `out_of_path_multiplier`) and optional `teacher` (FK RosterTenure).
- `ThreadWeavingTeachingOffer` - Teacher-side offer. FK to RosterTenure +
  ThreadWeavingUnlock. Mirrors `CodexTeachingOffer` shape (pitch, gold_cost,
  banked_ap). Path multiplier computed at acceptance time, not stored.

**Combat-side models (live in `world/combat`, not magic):**
- `CombatPull` - Per-(participant, round) commit envelope for a thread pull.
  Unique per (participant, round_number). M2M to Thread for the threads
  pulled; `resonance_spent` / `anima_spent` for audit.
- `CombatPullResolvedEffect` - Frozen snapshot of one resolved effect from
  a pull. Captures `kind`, `authored_value`, `level_multiplier`, `scaled_value`,
  `vital_target`, `source_thread`, `source_thread_level`, `source_tier`,
  `granted_capability`, `narrative_snippet`. Cascades from CombatPull;
  edits to authoring or Thread.level mid-round cannot retroactively alter
  what a committed pull granted.

**Note:** Affinity and Resonance are proper domain models in this app, each with an
optional OneToOne FK back to ModifierTarget for modifier system integration.

### Resonance Gain Surfaces (Resonance Pivot Spec C)

**Models (new):**
- `ResonanceGainConfig` - Singleton tuning config (pk=1). Fields: `weekly_pot_per_character`,
  `scene_entry_grant`, `residence_daily_trickle_per_resonance`, etc. Lazy-created via
  `get_resonance_gain_config()`.
- `PoseEndorsement` - Unsettled endorsement of a pose; settles at weekly tick. FK to
  `endorser_sheet`, M2M to `Resonance`. Unique per `(endorser_sheet, interaction)`.
  Captures `persona_snapshot` (CharField) for masquerade audit. Fields: `created_at`,
  `settled_at` (NULL until weekly settlement).
- `SceneEntryEndorsement` - Immediate flat grant for endorsing a character's scene entry
  pose. FK `endorser_sheet`, FK `endorsee_sheet`, FK `scene`, M2M `resonance`. Unique per
  `(endorser_sheet, endorsee_sheet, scene)`. Fires `grant_resonance` synchronously on creation.
- `ResonanceGrant` - Universal audit ledger. Discriminator `source` (TextChoice: POSE_ENDORSEMENT,
  SCENE_ENTRY, ROOM_RESIDENCE, OUTFIT_ITEM, STAFF_GRANT) + typed FKs: `source_room_aura_profile`,
  `source_staff_account`, `source_pose_endorsement`, `source_scene_entry_endorsement`. FK
  `character_sheet`, FK `resonance`, `amount`. CheckConstraints enforce shape per source.
- `RoomAuraProfile` - OneToOne extension of RoomProfile; hosts magical-character metadata.
  Non-magical rooms have no row. FK `room_profile`, M2M `resonances` (through RoomResonance).
- `RoomResonance` - Through-model for RoomAuraProfile ↔ Resonance M2M. Unique per
  `(profile, resonance)`. Tracks set-by timestamp for audit.

**Services (`services/gain.py` — new module):**
- `grant_resonance(sheet, resonance, amount, *, source, typed_fk_kwargs)` - Typed-FK signature.
  Writes CharacterResonance + ResonanceGrant atomically. `source` is a GainSource TextChoice.
  Matching typed FK kwarg required per source: ROOM_RESIDENCE → `room_aura_profile=`,
  POSE_ENDORSEMENT → `pose_endorsement=`, SCENE_ENTRY → `scene_entry_endorsement=`,
  STAFF_GRANT → optional `staff_account=`, OUTFIT_ITEM reserved.
- `create_pose_endorsement(endorser_sheet, interaction, resonance)` - 8 preconditions
  (self, alt, whisper, private, participation, unclaimed resonance, duplicate). Raises
  `EndorsementValidationError` on failure.
- `create_scene_entry_endorsement(endorser_sheet, endorsee_sheet, scene, resonance)` -
  Immediate-grant sibling with participation + alt checks.
- `settle_weekly_pot(endorser_sheet)` - Settles all unsettled PoseEndorsement rows for one
  endorser. Distributes `ceil(weekly_pot_per_character / N)` resonance per endorsement.
  Idempotent.
- `residence_trickle_tick()` - Daily pass: for each sheet with residence, grant per matching
  (aura-tagged ∩ sheet-claimed) resonance. Per-character atomic.
- `resonance_daily_tick()` - Master daily tick (residence trickle + outfit stub).
- `resonance_weekly_settlement_tick()` - Master weekly tick (settle all endorsers).
- `tag_room_resonance(room_profile, resonance, set_by=None)` / `untag_room_resonance(room_profile, resonance)` -
  Idempotent room aura management.
- `set_residence(sheet, room_profile | None)` / `get_residence_resonances(sheet) -> set[Resonance]` -
  Residence declaration + resonance intersection query.
- `account_for_sheet(sheet) -> AccountDB | None` - Walks CharacterSheet → RosterEntry →
  current RosterTenure → PlayerData → Account. Single source of truth for alt-guard.
- `get_resonance_gain_config() -> ResonanceGainConfig` - Lazy-create singleton (pk=1).

**Ticks registered in `game_clock/tasks.py`:**
- `magic.resonance_daily` - 24h
- `magic.resonance_weekly_settlement` - 7d

**API surfaces (`views.py`):**
- `PoseEndorsementViewSet` - POST /api/magic/pose-endorsements/ + DELETE-if-unsettled
- `SceneEntryEndorsementViewSet` - POST-only (delete deferred with ResonanceGrantReversal)
- `ResonanceGrantViewSet` - Read-only, user-scoped. FilterSet on source/resonance/date range.

**Related changes:**
- `CharacterSheet.current_residence` FK to RoomProfile (narrative declaration; mechanical
  trickle fires only on RoomAuraProfile match)
- `Interaction.pose_kind` CharField - STANDARD / ENTRY / DEPARTURE
- `GainSource` TextChoice - POSE_ENDORSEMENT / SCENE_ENTRY / ROOM_RESIDENCE / OUTFIT_ITEM / STAFF_GRANT

## Removed Models (deprecated)

The following models have been removed and replaced:
- `Power` - Replaced by `Technique` (player-created abilities)
- `CharacterPower` - Replaced by `CharacterTechnique`
- `AnimaRitualType` - Replaced by freeform stat+skill+resonance system
- `ResonanceAssociation` - Replaced by hierarchical `Facet` model
- `Thread` (legacy 5-axis model), `ThreadType`, `ThreadJournal`,
  `ThreadResonance` - Legacy 5-axis thread family. Replaced by the new
  `Thread` discriminator + typed-FK model and supporting catalogs
  (`ThreadPullCost` / `ThreadXPLockedLevel` / `ThreadPullEffect` /
  `ThreadWeavingUnlock` / `ThreadLevelUnlock` / `CharacterThreadWeavingUnlock` /
  `ThreadWeavingTeachingOffer`). See "Thread System (Resonance Pivot Spec A)"
  above.
- `CharacterResonanceTotal` - Aura recompute now reads `CharacterModifier` rows
  whose target category is `resonance` directly (no denormalized aggregate)

## Design Docs

- `docs/plans/2026-01-20-magic-system-design.md` - original system design
- `docs/plans/2026-03-02-cantrip-technique-alignment.md` - cantrip/technique alignment + spell mechanics
- `docs/plans/2026-03-04-path-cantrip-filtering-design.md` - path-based cantrip filtering design
- `docs/superpowers/specs/2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md` - Resonance Pivot Spec A (Threads + Currency + Rituals + Mage Scars rename)
- `docs/superpowers/plans/2026-04-19-resonance-pivot-spec-a-threads-and-currency.md` - 19-phase implementation plan for Spec A
- `docs/superpowers/specs/2026-04-22-resonance-pivot-spec-c-gain-surfaces-design.md` - Resonance Pivot Spec C (Endorsements + Room Aura + Residence Trickle)

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Affinities and Resonances are proper models in this app, not ModifierTarget entries
- FKs to affinities/resonances point directly to Affinity/Resonance models (type-safe)
- Use SharedMemoryModel for lookup tables (via mechanics.ModifierTarget)
- Technique has intensity (power) and control (safety/precision) as base stats
- Technique tier is derived from level (1-5=T1, 6-10=T2, etc.)
- Cantrip is a technique template — creates a real Technique at CG finalization
- No healing mechanics — shielding yes, restoration no (counter to tension design)

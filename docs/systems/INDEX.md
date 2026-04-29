# Arx II Systems Index

> Quick reference for AI agents and developers. For each system: what it does,
> key models, key functions/methods, and what it connects to.
>
> **For detailed documentation**, follow the links to individual system docs.

---

## Game Systems

### Magic
Powers, affinities, auras, resonances, threads-as-currency, rituals, and Mage Scars.

- **Models:**
  - **Identity/aura/techniques:** `Affinity`, `Resonance`, `CharacterAura`,
    `CharacterResonance` (reshaped Spec A §2.2 — `balance` + `lifetime_earned`),
    `Gift`, `CharacterGift`, `Technique`, `CharacterTechnique`, `Cantrip`,
    `TechniqueStyle`, `EffectType`, `Restriction`, `IntensityTier`,
    `TechniqueCapabilityGrant`
  - **Anima / rituals:** `CharacterAnima`, `CharacterAnimaRitual`,
    `AnimaRitualPerformance`, `SoulfrayConfig`, `MishapPoolTier`,
    `TechniqueOutcomeModifier`
  - **Mage Scars (renamed from Magical Scars — display-only, §7.2):**
    `MagicalAlterationTemplate`, `PendingAlteration`, `MagicalAlterationEvent`
  - **Spec A Thread + Currency (NEW):** `Thread` (discriminator + typed FKs:
    `target_trait` / `target_technique` / `target_object` / `target_relationship_track`
    / `target_capstone` / `target_facet` / `target_covenant_role` — last two added in
    Spec D PR1), `ThreadLevelUnlock`, `ThreadPullCost`,
    `ThreadXPLockedLevel`, `ThreadPullEffect`, `ImbuingProseTemplate`,
    `Ritual`, `RitualComponentRequirement`, `ThreadWeavingUnlock`,
    `CharacterThreadWeavingUnlock`, `ThreadWeavingTeachingOffer`
  - **Combat-side Spec A surface (in `world/combat`):** `CombatPull`,
    `CombatPullResolvedEffect`
- **Handlers:**
  - `character.threads` (`CharacterThreadHandler`) — cached thread list,
    `passive_vital_bonuses(vital_target)` for tier-0 VITAL_BONUS
    aggregation
  - `character.resonances` (`CharacterResonanceHandler`) —
    `balance(resonance)`, `lifetime(resonance)`, `get_or_create(resonance)`,
    `most_recently_earned()` (used by Mage Scars)
  - `character.combat_pulls` (`CharacterCombatPullHandler` in `world/combat`)
    — `active()`, `active_for_encounter()`, `active_pull_vital_bonuses()`
- **Key Services:**
  - Economy: `grant_resonance(character_sheet, resonance, amount, source, source_ref=None)`,
    `spend_resonance_for_imbuing(character_sheet, thread, amount) -> ThreadImbueResult`,
    `spend_resonance_for_pull(...)`, `preview_resonance_pull(...) -> PullPreviewResult`,
    `resolve_pull_effects(...)`, `cross_thread_xp_lock(character_sheet, thread, level)`
  - Thread lifecycle: `weave_thread(...)`, `update_thread_narrative(...)`,
    `imbue_ready_threads(character_sheet)`, `near_xp_lock_threads(...)`,
    `threads_blocked_by_cap(character_sheet)`
  - ThreadWeaving acquisition: `compute_thread_weaving_xp_cost(character_sheet, unlock) -> int`,
    `accept_thread_weaving_unlock(character_sheet, unlock, teacher=None)`
  - Cap helpers: `compute_anchor_cap(thread) -> int` (Spec D PR1: FACET uses
    `lifetime_earned // DIVISOR` capped at `path_stage × HARD_MAX_PER_STAGE`;
    COVENANT_ROLE uses `current_level × 10`),
    `compute_path_cap(character_sheet) -> int`, `compute_effective_cap(thread) -> int`
  - VITAL_BONUS routing: `recompute_max_health_with_threads(character_sheet) -> int`,
    `apply_damage_reduction_from_threads(character, damage_amount) -> int`
  - Outfit trickle (Spec D PR1): `outfit_daily_trickle_for_character(sheet) -> int` —
    issues `ResonanceGrant` rows (source=OUTFIT_TRICKLE, `outfit_item_facet` typed FK)
    for each worn item with matching facets; `resonance_daily_tick()` now calls this
    alongside residence trickle
- **Key Methods:** `CharacterAura.dominant_affinity`,
  `Thread.target` (populated FK), `Thread.display_name`,
  `ThreadWeavingUnlock.display_name`
- **Enums:** `AffinityType`, `TargetKind` (Thread discriminator — Spec D PR1 added
  `FACET` and `COVENANT_ROLE`), `EffectKind` (ThreadPullEffect), `VitalBonusTarget`,
  `RitualExecutionKind`, `AnimaRitualCategory`,
  `PendingAlterationStatus`, `AlterationTier`
- **Exceptions (used by services + views):** `AnchorCapExceeded`,
  `AnchorCapNotImplemented`, `InvalidImbueAmount`, `ResonanceInsufficient`,
  `WeavingUnlockMissing`, `XPInsufficient`, `RitualComponentError`,
  `NoMatchingWornFacetItemsError` (FACET thread pull with no worn matching item) —
  all with `user_message` properties for safe API responses.
- **Integrates with:** traits (thread anchor kind TRAIT), progression (XP
  spend for ThreadWeaving and XP-lock crossings), relationships (soul tether,
  magical_flavor; thread anchors RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE),
  journals (`JournalEntry.related_threads` M2M), combat (CombatPull,
  DamagePreApply for DAMAGE_TAKEN_REDUCTION), vitals
  (MAX_HEALTH recompute), conditions (CAPABILITY_GRANT effects + Mage Scars),
  mechanics (Property via Thread ROOM anchor + Ritual site_property),
  items (RitualComponentRequirement FKs ItemTemplate / QualityTier),
  flows (Ritual FLOW dispatch via FlowDefinition)
- **API endpoints (Spec A §4.5):**
  - `GET/POST/DELETE /api/magic/threads/`,
    `GET /api/magic/threads/{id}/` — list/create/soft-retire owned threads;
    requires `character_sheet_id` on create
  - `GET /api/magic/character-resonances/` — per-character balance +
    lifetime_earned rows
  - `POST /api/magic/thread-pull-preview/` — read-only preview of a pull's
    resonance/anima cost and resolved effects
  - `POST /api/magic/rituals/perform/` — dispatches PerformRitualAction
    (resolves primitive `thread_id` → Thread instance for Imbuing)
  - `GET /api/magic/teaching-offers/` — ThreadWeavingTeachingOffer listing
- **Source:** `src/world/magic/`
- **Details:** [magic.md](magic.md)

### Traits
Character statistics and dice rolling mechanics.

- **Models:** `Trait`, `CharacterTraitValue`, `PointConversionRange`, `CheckRank`, `ResultChart`, `ResultChartOutcome`
- **Handlers:** `TraitHandler` (via `character.traits`), `StatHandler` (via `character.stats`)
- **Key Functions:**
  - `character.traits.get_trait_value(name)` — with modifiers applied
  - `character.traits.get_base_trait_value(name)` — raw, no modifiers
  - `character.traits.get_trait_display_value(name)` — 1.0-10.0 scale
  - `character.traits.get_traits_by_type(type)` — dict[name → value]
  - `character.traits.calculate_check_points(trait_names)` — weighted points
  - `character.stats.get_stat(name)` — internal value
  - `character.stats.get_stat_display(name)` — display value (1-5)
- **9 Primary Stats:** strength, agility, stamina, charm, presence, perception, intellect, wits, willpower
- **Trait Types:** stat, skill, modifier, other
- **Trait Categories:** physical, social, mental, magic, combat, general, crafting, war, other
- **Integrates with:** magic (intensity calculations), skills (bonuses), mechanics (modifier stacking), checks (point calculation)
- **Source:** `src/world/traits/`
- **Details:** [traits.md](traits.md)
### Skills
Character abilities with parent skills and specializations.

- **Models:** `Skill`, `Specialization`, `CharacterSkillValue`, `CharacterSpecializationValue`
- **Integrates with:** traits (skill checks), character_creation (skill selection)
- **Source:** `src/world/skills/`
- **Details:** [skills.md](skills.md)
### Distinctions
Character advantages and disadvantages (CG Stage 6: Traits).

- **Models:** `DistinctionCategory`, `Distinction`, `DistinctionEffect`, `CharacterDistinction`
- **Key Methods:** `Distinction.calculate_total_cost()`, `Distinction.get_mutually_exclusive()`
- **Enums:** `DistinctionOrigin`, `OtherStatus`
- **Integrates with:** character_creation (draft storage), traits (stat modifiers)
- **Source:** `src/world/distinctions/`
- **Details:** [distinctions.md](distinctions.md)

### Checks
Check resolution engine — converts trait values to ranks and rolls against result charts.

- **Models:** `CheckCategory`, `CheckType`, `CheckTypeTrait`, `CheckTypeAspect`
- **Key Functions:** `perform_check(character, check_type, target_difficulty, extra_modifiers) -> CheckResult`, `get_rollmod(character) -> int`
- **Key Types:** `CheckResult` (outcome, chart, roller_rank, target_rank, trait_points, aspect_bonus)
- **Pipeline:** trait points (weighted via CheckTypeTrait) + aspect bonus (path level) + modifiers → CheckRank → ResultChart → roll+rollmod → outcome
- **Integrates with:** traits (lookup tables), skills (check bonuses), conditions (check modifiers), goals (bonuses)
- **Source:** `src/world/checks/`
- **Details:** [checks.md](checks.md)

### Conditions
Persistent states that modify capabilities, checks, and resistances with stage progression and interactions.

- **Models:** `ConditionCategory`, `ConditionTemplate`, `ConditionStage`, `ConditionInstance`, `ConditionCapabilityEffect`, `ConditionCheckModifier`, `ConditionResistanceModifier`, `ConditionDamageOverTime`, `ConditionDamageInteraction`, `ConditionConditionInteraction`
- **Lookup Tables:** `CapabilityType`, `CheckType`, `DamageType`
- **Key Functions:** `apply_condition()`, `remove_condition()`, `get_capability_status()`, `get_check_modifier()`, `get_resistance_modifier()`, `process_round_start()`, `process_round_end()`, `process_damage_interactions()`
- **Integrates with:** combat (DoT, capability blocking), magic (power sources), progression (interactions)
- **Source:** `src/world/conditions/`
- **Details:** [conditions.md](conditions.md)
### Species
Species/race definitions with stat bonuses and language assignments.

- **Models:** `Species`, `SpeciesStatBonus`, `Language`
- **Key Methods:** `Species.get_stat_bonuses_dict()`, `Species.is_subspecies`
- **Integrates with:** character_creation (Beginnings.allowed_species), forms (physical traits)
- **Source:** `src/world/species/`
- **Details:** [species.md](species.md)
### Forms
Physical appearance options (height, build, hair/eye colors).

- **Models:** `HeightBand`, `Build`, `FormTrait`, `FormTraitOption`, `CharacterForm`
- **Enums:** `TraitType` (color/style)
- **Integrates with:** character_sheets (appearance), species (height bands per species)
- **Source:** `src/world/forms/`
- **Details:** [forms.md](forms.md)
### Classes (Paths)
Character paths with evolution hierarchy through stages of power.

- **Models:** `Path`, `CharacterClass`
- **Enums:** `PathStage` (Prospect, Potential, Puissant, True, Grand, Transcendent)
- **Key Methods:** `Path.parent_paths`, `Path.child_paths` (evolution hierarchy)
- **Integrates with:** progression (level requirements), character_creation (Prospect selection)
- **Source:** `src/world/classes/`
- **Details:** [classes.md](classes.md)
### Areas
Spatial hierarchy for organizing rooms into regions, districts, and neighborhoods.

- **Models:** `Area`, `AreaClosure` (unmanaged, materialized view)
- **Enums:** `AreaLevel` (Region, District, Neighborhood)
- **Key Functions:** `get_ancestry()`, `get_descendant_areas()`, `get_rooms_in_area()`, `reparent_area()`
- **Pattern:** Postgres materialized view with recursive CTE for hierarchy queries
- **Integrates with:** realms (Area.realm FK), evennia_extensions (RoomProfile.area FK)
- **Source:** `src/world/areas/`
- **Details:** [areas.md](areas.md)
### Instances
Temporary instanced rooms spawned on demand for missions, GM events, and tutorials.

- **Models:** `InstancedRoom`
- **Enums:** `InstanceStatus` (Active, Completed)
- **Key Functions:** `spawn_instanced_room()`, `complete_instanced_room()`
- **Pattern:** Lifecycle record attached to regular Room via OneToOneField; rooms with scene history are preserved
- **Integrates with:** character_sheets (owner FK), scenes (preservation check), evennia_extensions (ObjectDisplayData for description)
- **Source:** `src/world/instances/`
- **Details:** [instances.md](instances.md)
### Realms
Game world realms (Arx, Luxan, etc.) for geographical/political organization.

- **Models:** `Realm`
- **Integrates with:** societies (Society.realm FK), character_creation (StartingArea)
- **Source:** `src/world/realms/`
- **Details:** [realms.md](realms.md)
### Societies
Social structures, organizations, reputation, and legend tracking.

- **Models:** `Society`, `OrganizationType`, `Organization`, `OrganizationMembership`, `SocietyReputation`, `OrganizationReputation`, `LegendEntry`, `LegendSpread`
- **Enums:** `ReputationTier`
- **Principle Axes:** mercy, method, status, change, allegiance, power (-5 to +5)
- **Integrates with:** realms (Society.realm FK), character_sheets (Guise for identity)
- **Source:** `src/world/societies/`
- **Details:** [societies.md](societies.md)
### Goals
Goal domain allocation and journal-based XP progression.

- **Models:** `CharacterGoal`, `GoalJournal`, `GoalRevision`
- **Goal Domains:** Stored as `ModifierTarget(category='goal')` in mechanics system
- **Six Domains:** Standing, Wealth, Knowledge, Mastery, Bonds, Needs
- **Integrates with:** progression (XP rewards), mechanics (goal domains use ModifierTarget)
- **Source:** `src/world/goals/`
- **Details:** [goals.md](goals.md)
### Action Points
Time/effort resource economy with regeneration via cron. The most complete gate pattern in the codebase.

- **Models:** `ActionPointConfig`, `ActionPointPool`
- **Key Methods:**
  - `ActionPointPool.get_or_create_for_character(character)` — safe accessor
  - `pool.can_afford(amount) -> bool` — check before spending
  - `pool.spend(amount) -> bool` — atomic via `select_for_update`
  - `pool.bank(amount) -> bool`, `pool.unbank(amount) -> int`
  - `pool.get_effective_maximum() -> int` — base + distinction modifiers
  - `pool.apply_daily_regen()`, `pool.apply_weekly_regen()`
- **Pattern:** Fully integrated with mechanics modifier system via `get_modifier_total(sheet, modifier_target)` for regen rates and pool max. Uses `select_for_update` for race-condition safety.
- **Integrates with:** codex (teaching costs AP), mechanics (AP modifiers from distinctions), cron (daily/weekly regeneration)
- **Source:** `src/world/action_points/`
- **Details:** [action_points.md](action_points.md)

### Codex
Lore storage and character knowledge tracking.

- **Models:** `CodexCategory`, `CodexSubject`, `CodexEntry`, `CharacterCodexKnowledge`
- **Key Methods:** Character learning from starting choices or teaching
- **Integrates with:** action_points (teaching costs), consent (visibility), character_creation (starting knowledge)
- **Source:** `src/world/codex/`
- **Details:** [codex.md](codex.md)
### Consent
OOC visibility groups for player-controlled content sharing.

- **Models:** `ConsentGroup`, `ConsentGroupMember`, `VisibilityMixin`
- **Key Methods:** `VisibilityMixin.is_visible_to()`
- **Pattern:** RosterTenure-based (player's tenure, not character)
- **Integrates with:** roster (RosterTenure), codex (visibility), any model using VisibilityMixin
- **Source:** `src/world/consent/`
- **Details:** [consent.md](consent.md)
### Progression
XP, kudos, development points, and unlock system. Contains the most explicit prerequisite framework.

- **Models:** `ExperiencePointsData`, `XPTransaction`, `CharacterXP`, `DevelopmentPoints`, `DevelopmentTransaction`, `KudosPointsData`, `KudosTransaction`, `CharacterUnlock`, `XPCostChart`, `XPCostEntry`, `CharacterPathHistory`
- **Unlock Requirements** (all have `is_met_by_character(character) -> tuple[bool, str]`):
  - `TraitRequirement` — checks CharacterTraitValue
  - `LevelRequirement` — checks character_class_levels
  - `ClassLevelRequirement` — checks specific class level
  - `MultiClassRequirement` — multiple class levels
  - `TierRequirement` — tier 1 vs tier 2
  - `AchievementRequirement` — **stub**, checks `character.db` attribute
  - `RelationshipRequirement` — **stub**, always returns False
- **Key Functions:**
  - `check_requirements_for_unlock(character, unlock) -> tuple[bool, list[str]]`
  - `get_available_unlocks_for_character(character) -> AvailableUnlocks`
  - `ExperiencePointsData.can_spend(amount) -> bool`
  - `CharacterXP.can_spend(amount) -> bool`
- **Pattern:** `AbstractClassLevelRequirement` base class with polymorphic `is_met_by_character()` — extend this for new prerequisite types (society, relationship, etc.)
- **Integrates with:** traits (unlock requirements), classes (path unlocks), goals (XP rewards)
- **Source:** `src/world/progression/`
- **Details:** [progression.md](progression.md)

### Character Sheets
Character identity, appearance, demographics, and guise system.

- **Models:** `CharacterSheet`, `Heritage`, `Characteristic`, `CharacteristicValue`, `Guise`
- **Integrates with:** roster (character management), character_creation (sheet setup)
- **Source:** `src/world/character_sheets/`
- **Details:** [character_sheets.md](character_sheets.md)
### Character Creation
Multi-stage character creation flow with draft system.

- **Models:** `CharacterDraft`, `StartingArea`, `Beginnings`
- **Key Functions:** Stage validation, draft progression
- **Integrates with:** All character-related systems (traits, skills, magic, sheets)
- **Source:** `src/world/character_creation/`
- **Details:** [character_creation.md](character_creation.md)
### Roster
Character lifecycle management with web-first applications and player anonymity.

- **Models:** `Roster`, `RosterEntry`, `RosterTenure`, `RosterApplication`, `PlayerMail`
- **Integrates with:** accounts, character_sheets, scenes
- **Source:** `src/world/roster/`
- **Details:** [roster.md](roster.md)
### Scenes
Roleplay session recording with participant tracking and message logging.

- **Models:** `Scene`, `SceneParticipation`, `Persona`, `SceneMessage`, `SceneMessageSupplementalData`, `SceneMessageReaction`
- **Key Fields:** `SceneMessage.mode` (pose/emit/say/whisper/ooc), `SceneMessage.context` (public/tabletalk/private), `SceneMessage.sequence_number` (ordered), `SceneMessage.receivers` (M2M, empty=everyone)
- **Key Functions:** `broadcast_scene_message(scene, action)` — pushes scene state to participants via websocket
- **Pattern:** Messages are flat (ordered by sequence_number), no threading. `SceneMessageSupplementalData.data` (JSONField) exists as escape hatch for rich metadata without bloating main table.
- **Note:** No `parent` FK for threading, no `message_type` beyond mode/context, no action-block concept yet. Auto-logging from in-game commands happens via `message_location()` flow service function.
- **Integrates with:** roster (characters), stories (EpisodeScene join), instances (preservation check), flows (auto-logging via message_location)
- **Source:** `src/world/scenes/`
- **Details:** [scenes.md](scenes.md)
### Stories
Player-driven narrative campaign system with hierarchical structure and task-gated progression.

- **Models:** `Story`, `Chapter`, `Episode`, `Transition`, `Beat`, `BeatCompletion`, `EpisodeResolution`, `StoryProgress`, `GroupStoryProgress`, `GlobalStoryProgress`, `AggregateBeatContribution`, `AssistantGMClaim`, `SessionRequest`, `Era`, `StoryParticipation`, `PlayerTrust`, `TrustCategory`
- **Reactivity entry points (Phase 3):** `stories.services.reactivity.on_character_level_changed` / `on_achievement_earned` / `on_condition_applied` / `on_condition_expired` / `on_codex_entry_unlocked` / `on_story_advanced`
- **Key Services:** `evaluate_auto_beats`, `record_gm_marked_outcome`, `record_aggregate_contribution`, `get_eligible_transitions`, `resolve_episode`, `create_character_progress` / `create_group_progress` / `create_global_progress`, `catch_up_character_stories` (called from `Character.at_post_puppet`)
- **Integrates with:** scenes (episode content), roster (participants), achievements / conditions / codex / classes (predicate evaluation + reactivity hooks fire from their services), narrative (beat completions and episode resolutions emit NarrativeMessages)
- **Source:** `src/world/stories/`
- **Details:** [stories.md](stories.md)

### Narrative
General-purpose IC message delivery — GM/Staff/automated messages to characters. Used by stories for beat and episode-resolution informs; also available for atmosphere, visions, happenstance.

- **Models:** `NarrativeMessage` (body, ooc_note, category, sender_account, optional related_story / related_beat_completion / related_episode_resolution FKs), `NarrativeMessageDelivery` (message + recipient_character_sheet, delivered_at, acknowledged_at)
- **Categories:** STORY, ATMOSPHERE, VISIONS, HAPPENSTANCE, SYSTEM
- **Key Services:**
  - `send_narrative_message(recipients, body, category, ...)` — atomic create + fan-out + real-time push to puppeted recipients via `character.msg()` with `|R[NARRATIVE]|n` color tag; offline recipients stay queued
  - `deliver_queued_messages(sheet)` — drains queued deliveries at login (called from `at_post_puppet` via stories login service)
- **Pattern:** One message fans out to many recipients via NarrativeMessageDelivery rows (e.g., GM sends covenant message to 5 of 8 members — one message, five delivery rows). Messages are immutable; delivery rows track per-recipient state.
- **API Endpoints:** `GET /api/narrative/my-messages/` (paginated, filterable by category / related_story / acknowledged), `POST /api/narrative/deliveries/{id}/acknowledge/`
- **Integrates with:** stories (beat completions + episode resolutions emit messages via `stories.services.narrative`), character_sheets (recipient), accounts (sender)
- **Source:** `src/world/narrative/`
### Mechanics
Unified modifier system — categories, types, sources, and per-character modifier values.

- **Models:** `ModifierCategory`, `ModifierTarget`, `ModifierSource`, `CharacterModifier`, `ConsequenceEffect`, `ObjectProperty`, `ChallengeTemplateProperty`
- **Key Functions:**
  - `get_modifier_total(sheet, modifier_target) -> int` — Spec D PR1: invokes equipment
    walk (`passive_facet_bonuses` + `covenant_role_bonus`) when category is in
    `EQUIPMENT_RELEVANT_CATEGORIES`
  - `get_modifier_breakdown(sheet, modifier_target) -> ModifierBreakdown` — with sources, immunity, amplification
  - `create_distinction_modifiers(char_distinction) -> list[CharacterModifier]`
  - `delete_distinction_modifiers(char_distinction) -> int`
  - `passive_facet_bonuses(sheet, target) -> int` (Spec D §5.2) — sums tier-0 FACET
    `ThreadPullEffect` contributions per worn item; called by `get_modifier_total`
  - `covenant_role_bonus(sheet, target) -> int` (Spec D §5.6) — per-equipped-item
    additive (compat role) or max (incompat); PR3 wires `role_base_bonus_for_target`
    and `item_mundane_stat_for_target` (return 0 until PR3)
  - `resolve_challenge(character, challenge_instance, approach, capability_source) -> ChallengeResolutionResult` — resolve a character's action against a challenge
  - `select_consequence(character, check_type, difficulty, consequences) -> PendingResolution` — generic: perform check + select weighted consequence (in `checks/consequence_resolution.py`)
  - `apply_resolution(pending, context) -> list[AppliedEffect]` — generic: dispatch ConsequenceEffects (in `checks/consequence_resolution.py`)
- **Categories:** stat, magic, affinity, resonance, action_points, development, height_band,
  condition_control_percent, condition_intensity_percent, condition_penalty_percent, goal
- **Constants (Spec D PR1):**
  `EQUIPMENT_RELEVANT_CATEGORIES = frozenset({"stat", "magic", "affinity", "resonance"})`
  — gates the equipment modifier walk in `get_modifier_total`
- **Pattern:** `DistinctionEffect` → `ModifierSource` → `CharacterModifier`. Equipment
  bonuses flow through `passive_facet_bonuses` + `covenant_role_bonus` (called inline
  by `get_modifier_total`, not stored as `CharacterModifier` rows).
- **Integrates with:** distinctions (modifier sources), conditions (modifier sources), traits (stat modifiers), action_points (AP modifiers), goals (goal domains)
- **Source:** `src/world/mechanics/`
- **Details:** [mechanics.md](mechanics.md)

### Items & Equipment
Items, equipment, inventory, and currency. Spec D PR1 shipped facets, equip/unequip
services, and equipment-modifier integration.

- **Models:**
  - `QualityTier`, `InteractionType`, `ItemTemplate`, `TemplateSlot`, `ItemInstance`,
    `TemplateInteraction`, `EquippedItem`, `OwnershipEvent`, `CurrencyBalance`
  - `ItemFacet` (Spec D §4.2) — through-model linking `ItemInstance` ↔ `Facet` with
    `attachment_quality_tier`; unique per (item_instance, facet)
- **New fields on `ItemTemplate` (Spec D PR1):** `facet_capacity` (max attachable facets,
  default 0), `gear_archetype` (CharField, `GearArchetype` enum choices)
- **Enums:** `BodyRegion` (17 body regions), `EquipmentLayer` (skin/under/base/over/outer/
  accessory), `OwnershipEventType` (created/given/stolen/transferred), `GearArchetype`
- **Handlers:**
  - `character.equipped_items` (`CharacterEquipmentHandler`) — `iter()`,
    `iter_item_facets()`, `item_facets_for(facet)`, `invalidate()`
- **Key Services:**
  - `equip_item(*, character_sheet, item_instance, body_region, equipment_layer) -> EquippedItem`
    — raises `SlotConflict` / `SlotIncompatible`
  - `unequip_item(*, equipped_item) -> None`
  - `attach_facet_to_item(*, crafter, item_instance, facet, attachment_quality_tier) -> ItemFacet`
    — raises `FacetAlreadyAttached` / `FacetCapacityExceeded`
  - `remove_facet_from_item(*, item_facet) -> None`
- **Exceptions:** `FacetAlreadyAttached`, `FacetCapacityExceeded`, `SlotConflict`,
  `SlotIncompatible` — all in `world.items.exceptions`
- **API Endpoints:**
  - `/api/items/quality-tiers/`, `/api/items/interaction-types/`, `/api/items/templates/`
    (read-only catalog)
  - `GET/POST /api/items/item-facets/` — list/attach (owner-or-staff perm);
    `DELETE /api/items/item-facets/{id}/` — remove
  - `GET/POST /api/items/equipped-items/` — list/equip (current-tenure perm);
    `DELETE /api/items/equipped-items/{id}/` — unequip
- **Pattern:** Templates define archetypes; instances hold per-item state. Equipment uses
  region + layer grid (unique constraint per character). Facets attach up to `facet_capacity`
  per item; worn facets feed the mechanics modifier walk (see Mechanics §EQUIPMENT_RELEVANT).
- **Integrates with:** mechanics (equipment modifier walk via `passive_facet_bonuses` +
  `covenant_role_bonus`), magic (outfit trickle, `outfit_item_facet` ResonanceGrant FK),
  covenants (gear archetype compatibility), crafting (future: crafting recipes)
- **Source:** `src/world/items/`
- **Details:** [items.md](items.md)

### Covenants
Magically-empowered group oaths with roles and gear compatibility. Spec D PR1 shipped
the role-assignment and gear-compatibility data layer.

- **Models:**
  - `CharacterCovenantRole` — per-character record of a covenant role assignment;
    `left_at IS NULL` = currently active (Spec D §4.4)
  - `GearArchetypeCompatibility` — existence-only join: which `CovenantRole`s are
    compatible with which `GearArchetype` values (read-only authored content)
- **Handlers:**
  - `character.covenant_roles` (`CharacterCovenantRoleHandler`) — `has_ever_held(role)`,
    `currently_held()`, `invalidate()`
- **Key Services:**
  - `assign_covenant_role(sheet, role) -> CharacterCovenantRole`
  - `end_covenant_role(role_assignment) -> None`
  - `is_gear_compatible(role, archetype) -> bool` — existence-only join lookup
- **Exceptions:** `CovenantRoleNeverHeldError` (raised by `weave_thread` when
  `target_kind=COVENANT_ROLE` and character never held the role) — in
  `world.covenants.exceptions`
- **API Endpoints:**
  - `GET /api/covenants/gear-compatibilities/` — read-only authored content
  - `GET /api/covenants/character-roles/` — read-only; non-staff scoped to own
    currently-played sheets
- **Integrates with:** magic (COVENANT_ROLE Thread anchor cap = `current_level × 10`),
  mechanics (`covenant_role_bonus` in modifier walk), items (`gear_archetype` on
  `ItemTemplate`)
- **Source:** `src/world/covenants/`

### Relationships
Character-to-character opinions, conditions, and situational modifier gating.

- **Models:** `RelationshipCondition` (SharedMemoryModel), `CharacterRelationship`
- **Key Fields:** `CharacterRelationship.reputation` (-1000 to 1000), `conditions` (M2M to RelationshipCondition)
- **Pattern:** `RelationshipCondition.gates_modifiers` (M2M to ModifierTarget) — conditions activate/deactivate situational modifiers
- **Examples:** "Attracted To" gates Allure modifier, "Fears" gates Intimidation bonus
- **Integrates with:** mechanics (modifier gating), character_sheets (CharacterSheet FK)
- **Source:** `src/world/relationships/`

---

## Core Infrastructure

### Actions
Self-contained game actions that own prerequisites, execution, and events.

- **Key Classes:** `Action` (base dataclass), `Prerequisite`, `ActionResult`, `ActionAvailability`
- **Registry:** `get_action(key)`, `get_actions_for_target_type(target_type)`, `ACTIONS_BY_KEY`
- **Target Types:** `SELF`, `SINGLE`, `AREA`, `FILTERED_GROUP`
- **Concrete Actions:** `LookAction`, `InventoryAction`, `SayAction`, `PoseAction`, `WhisperAction`, `GetAction`, `DropAction`, `GiveAction`, `TraverseExitAction`, `HomeAction`
- **Pattern:** `action.run(actor, **kwargs)` → checks prerequisites → executes → returns `ActionResult`
- **Integrates with:** service functions (direct calls), commands (telnet compatibility), flows (future: complex triggers)
- **Not Yet Built:** `ActionEnhancement` model, `SyntheticAction` model, event emission, `CharacterCapabilities` facade, on-demand availability endpoint
- **Source:** `src/actions/`

### Flows
Database-driven game logic engine for complex branching sequences, plus the reactive layer that powers triggers/scars/wards.

- **Models:** `FlowDefinition`, `FlowStepDefinition`, `FlowStack`, `Event`, `TriggerDefinition`, `Trigger`, `TriggerData`
- **Trigger fields:** `obj` (typeclass owner), `source_condition` (required — room-owned triggers use a pseudo-instance whose target is the room), `source_stage` (optional stage gate), `additional_filter_condition` (JSON DSL), `priority`. **No `scope` field** — self-vs-target-vs-bystander is expressed via filters
- **Key Classes:** `FlowStack` (with depth cap + cancellation), `FlowExecution`, `FlowEvent`, `SceneDataManager`, `TriggerHandler` (per-owner cached_property; pure provider — its sole public method is `triggers_for(event_name) -> list[Trigger]`)
- **Reactive Entry Points:**
  - `emit_event(event_name, payload, location, *, parent_stack=None)` (`flows/emit.py`) — **single unified dispatch path**. Walks `[location, *location.contents]`, calls `triggers_for(event_name)` on each owner, priority-sorts the combined list globally (descending), dispatches synchronously on one `FlowStack`, stops on `CANCEL_EVENT`. Used by service functions, typeclass hooks, and `EMIT_FLOW_EVENT` flow steps alike
  - `EventNames` (`flows/events/names.py`) — canonical string constants for the 18 MVP events
  - `PAYLOAD_FOR_EVENT` (`flows/events/payloads.py`) — event-name → payload dataclass map; PRE payloads are mutable, POST payloads frozen. AE payloads use `targets: list`
  - `evaluate_filter(spec, payload, *, self_ref)` (`flows/filters/evaluator.py`) — JSON filter DSL: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `contains`, `has_property`, plus `and`/`or`/`not`. Bare `"self"` (and `self.<attr>`) resolves to the trigger's owner
  - **Filter idioms** (see `docs/systems/flows.md` for details): `{"path": "target", "op": "==", "value": "self"}` = self-only (replaces `scope=SELF`); `{"path": "target", "op": "!=", "value": "self"}` = bystander-only; no target filter = room-wide (replaces `scope=ROOM`/`ANY`)
  - `register_pending_prompt`, `resolve_pending_prompt`, `timeout_pending_prompt` (`flows/execution/prompts.py`) — Twisted Deferred-backed player prompts (no DB rows)
  - `classify_source(obj) -> DamageSource` (`world/combat/damage_source.py`) — discriminated union for damage attribution
- **New Flow Action Steps:** `CANCEL_EVENT`, `MODIFY_PAYLOAD`, `PROMPT_PLAYER`, `EMIT_FLOW_EVENT` (routes through `emit_event()`), `EMIT_FLOW_EVENT_FOR_EACH` (in `FlowActionChoices`). `DEAL_DAMAGE` / `REMOVE_CONDITION` steps are deferred — emit a flow event that calls the relevant service function instead.
- **Typeclass Hooks:** `Character.at_attacked`, `Character/Room/Object.at_pre_move`/`at_post_move`, `Object.at_examined` — wired in `typeclasses/` to call `emit_event`. The `trigger_handler` cached property is installed via `ObjectParent` mixin.
- **Object States:** `BaseState`, `CharacterState`, `RoomState`, `ExitState` — ephemeral wrappers with permission methods (`can_move`, `can_traverse`) and appearance rendering
- **Service Functions:** `send_message`, `message_location`, `send_room_state`, `move_object`, `check_exit_traversal`, `traverse_exit`, `get_formatted_description`, `show_inventory` — accept `BaseState` directly (no `FlowExecution` dependency)
- **Where events are emitted:** `world/combat/services.py` (damage/attack/incap/death), `world/conditions/services.py` (apply/stage-change/remove), `world/magic/services.py` (technique pre-cast/cast/affected), and the typeclass move/examine hooks
- **Critical Note:** No `FlowDefinition` records exist in the database yet. The reactive layer ships the plumbing; authoring trigger content (e.g., retaliation scars, environmental wards) happens against `ConditionTemplate.reactive_triggers` and similar M2Ms in later scopes.
- **Source:** `src/flows/`
- **Details:** [flows.md](flows.md)

### Commands
Thin telnet compatibility layer that delegates to Actions.

- **Key Classes:** `ArxCommand` (base with `action` + `resolve_action_args()`), `FrontendMetadataMixin` (for non-action commands)
- **Pattern:** Telnet text → `command.func()` → `resolve_action_args()` → `action.run()`. Web bypasses commands entirely.
- **Frontend Integration:** `ArxCommand.to_payload()` builds descriptors from action metadata. `serialize_cmdset()` aggregates for room state.
- **Non-action commands:** CmdIC, CmdCharacters, CmdAccount, CmdSheet, CmdPage, builder commands
- **Source:** `src/commands/`
- **Details:** [commands.md](commands.md)
### Behaviors
Database-driven behavior attachment for dynamic object customization.

- **Key Classes:** `BehaviorPackageDefinition`, `BehaviorPackageInstance`
- **Pattern:** Attach behaviors to objects without code changes
- **Integrates with:** typeclasses (objects), flows (behavior triggers)
- **Source:** `src/behaviors/`
- **Details:** [behaviors.md](behaviors.md)
### Typeclasses
Core Evennia object definitions (Character, Room, Exit, Account).

- **Key Classes:** `Character`, `Room`, `Exit`, `Account`, `Object`
- **Pattern:** Inherit from Evennia base classes, add Arx-specific behavior
- **Integrates with:** All systems (typeclasses are the foundation)
- **Source:** `src/typeclasses/`
- **Details:** [typeclasses.md](typeclasses.md)
### Evennia Extensions
Extensions to Evennia models for additional data storage.

- **Key Classes:** `PlayerData`, data handlers, integration adapters
- **Pattern:** Extend Evennia models without modifying library code
- **Integrates with:** accounts, characters, Evennia core
- **Source:** `src/evennia_extensions/`
- **Details:** [evennia_extensions.md](evennia_extensions.md)
---

## Frontend

### Character Creation UI
React components for the multi-stage character creation flow.

- **Key Components:** `CharacterCreationPage`, stage components (`OriginStage`, `MagicStage`, etc.)
- **Hooks:** `useDraft()`, `useAffinities()`, `useResonances()`, `useGifts()`
- **Source:** `frontend/src/character-creation/`

### Game Client
WebSocket-based game interface for MUD interaction.

- **Key Components:** `GamePage`, `CommandInput`, `OutputDisplay`
- **Hooks:** `useWebSocket()`, `useGameState()`
- **Source:** `frontend/src/game/`

### Roster UI
Character browsing and management interface.

- **Key Components:** `RosterListPage`, `CharacterSheetPage`
- **Source:** `frontend/src/roster/`

---

## Quick Reference: "Can This Character Do X?"

These are the existing patterns for querying character capabilities across all systems.

| Question | System | How to Check |
|----------|--------|-------------|
| What is a capability's value? | conditions | `get_capability_value(target, capability_type)` (0 = effectively blocked) |
| All capability values for a character? | conditions | `get_all_capability_values(target)` → `dict[str, int]` |
| What check modifier from conditions? | conditions | `get_check_modifier(target, check_type).total_modifier` |
| What resistance to damage type? | conditions | `get_resistance_modifier(target, damage_type)` |
| Does character have a condition? | conditions | `has_condition(target, condition_template)` |
| Can character afford AP cost? | action_points | `pool.can_afford(amount)` (atomic: `pool.spend(amount)`) |
| Can character afford XP cost? | progression | `xp_data.can_spend(amount)` |
| Does character meet unlock reqs? | progression | `check_requirements_for_unlock(character, unlock)` → `tuple[bool, list[str]]` |
| What trait/stat value? | traits | `character.traits.get_trait_value(name)` (with modifiers) |
| What is character's check rank? | checks | `perform_check(character, check_type, difficulty)` → `CheckResult` |
| What distinctions does char have? | distinctions | `CharacterDistinction.objects.filter(character=char)` |
| What techniques does char know? | magic | `char.sheet_data.character_techniques.select_related("technique")` |
| What gifts does char have? | magic | `char.sheet_data.character_gifts.select_related("gift")` |
| What's char's anima pool? | magic | `character.anima.current`, `.maximum` |
| Is char in an organization? | societies | `OrganizationMembership.objects.filter(guise=guise, organization=org)` |
| What's char's reputation tier? | societies | `SocietyReputation.objects.get(guise=guise, society=society).get_tier()` |
| What relationship to target? | relationships | `CharacterRelationship.objects.filter(source=sheet_a, target=sheet_b)` |
| Does relationship have condition? | relationships | `.filter(conditions__name="Trusts").exists()` |
| What modifier from distinctions? | mechanics | `get_modifier_total(sheet, modifier_target)` |
| Full modifier breakdown? | mechanics | `get_modifier_breakdown(sheet, modifier_target)` |
| Is content visible to player? | consent | `content.is_visible_to(tenure)` |
| Resolve a challenge | mechanics | `resolve_challenge(character, instance, approach, source)` |

**Established prerequisite pattern:** `AbstractClassLevelRequirement.is_met_by_character(character) -> tuple[bool, str]` in progression — extend this for new prerequisite types.

**Complete gate example:** `CodexTeachingOffer.can_accept()` in `src/world/codex/models.py` — checks identity, knowledge state, prerequisites, and AP cost in sequence.

## Quick Reference: Common Tasks

| Task | System | Entry Point |
|------|--------|-------------|
| Check character's trait value | traits | `character.traits.get_trait_value(trait_name)` |
| Get character's dominant affinity | magic | `character.aura.dominant_affinity` |
| Check if character has a gift | magic | `CharacterGift.objects.filter(character=char, gift__name=name).exists()` |
| Get character's skills | skills | `CharacterSkillValue.objects.filter(character=char)` |
| Get character's distinctions | distinctions | `CharacterDistinction.objects.filter(character=char)` |
| Check mutual exclusion | distinctions | `distinction.get_mutually_exclusive()` |
| Apply a condition | conditions | `apply_condition(target, condition_template, severity=2)` |
| Process round damage | conditions | `process_round_start(target)`, `process_round_end(target)` |
| Get character's goal points | goals | `CharacterGoal.objects.filter(character=char)` |
| Get goal bonus for domain | goals | `get_goal_bonus(character_sheet, "Standing")` |
| Spend action points | action_points | `ActionPointPool.get_or_create_for_character(char).spend(cost)` |
| Check character knowledge | codex | `CharacterCodexKnowledge.objects.filter(character=char, entry__name=name).exists()` |
| Get organization membership | societies | `OrganizationMembership.objects.filter(guise=guise)` |
| Get reputation tier | societies | `SocietyReputation.objects.get(guise=guise, society=society).get_tier()` |
| Get species stat bonuses | species | `species.get_stat_bonuses_dict()` |
| Get character's unlocks | progression | `CharacterUnlock.objects.filter(character=char)` |
| Get available unlocks | progression | `get_available_unlocks_for_character(character)` |
| Sum modifiers for target | mechanics | `get_modifier_total(sheet, modifier_target)` |
| Full modifier breakdown | mechanics | `get_modifier_breakdown(sheet, modifier_target)` |
| Get area ancestry | areas | `get_ancestry(area)` |
| Get rooms in area | areas | `get_rooms_in_area(area)` |
| Spawn instanced room | instances | `spawn_instanced_room(name, desc, owner, return_loc)` |
| Complete instanced room | instances | `complete_instanced_room(room)` |
| Resolve challenge action | mechanics | `resolve_challenge(character, instance, approach, source)` |
| Standalone roll + consequences | checks | `select_consequence(char, check_type, diff, pool)` + `apply_resolution(pending, ctx)` |
| Get runtime properties on object | mechanics | `ObjectProperty.objects.filter(object=obj)` |

---

## Adding New Systems

When adding a new system, create a doc at `docs/systems/<system>.md` following the template in [magic.md](magic.md), then add an entry to this index.

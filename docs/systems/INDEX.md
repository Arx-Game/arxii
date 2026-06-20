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
    `target_trait` / `target_technique` / `target_facet` / `target_relationship_track`
    / `target_capstone` / `target_covenant_role` / `target_sanctum_details` — bare
    `ROOM` removed; SANCTUM is the leveled room anchor, cap = sanctum level × 10,
    in-sanctum pull boost), `ThreadLevelUnlock`, `ThreadPullCost`,
    `ThreadXPLockedLevel`, `ThreadPullEffect`, `ImbuingProseTemplate`,
    `Ritual` (`service_function_path` dispatches the ritual at fire time;
    `draft_validator_path` — new CharField, blank — is called inside `draft_session`
    before the session row is created, letting domain code gate who may initiate the
    ritual without coupling magic to any specific domain),
    `RitualComponentRequirement`, `ThreadWeavingUnlock`,
    `CharacterThreadWeavingUnlock`, `ThreadWeavingTeachingOffer`,
    `SoulTetherConfig` (singleton pk=1, rescue + sineating tuning knobs),
    `ThreadSurvivabilityTuning` (per-`VitalBonusTarget` tuning row for the
    universal thread survivability baseline — `vital_target` unique choice,
    `coefficient`, `cap`, `half_saturation`; one row each for DR and MAX_HEALTH;
    seeded via `seed_thread_survivability_tuning()`, staff-tunable in admin, #1175)
  - **Combat-side Spec A surface (in `world/combat`):** `CombatPull`,
    `CombatPullResolvedEffect`
  - **Dramatic moment tagging (#545 / #1139):**
    `DramaticMomentType` (inherits `RenownAwardConfig`; staff-authored catalog —
    `label`, `resonance` FK, `resonance_amount`, `per_scene_cap`),
    `DramaticMomentTag` (per-event tag — `moment_type`, `character_sheet`,
    `scene`, `tagged_by` AccountDB, `interaction` pose anchor with
    `db_constraint=False` + `interaction_timestamp` denormalized, `tagged_at`)
  - **Entry-flourish declaration (#1140):** `PendingEntryFlourishOffer`
    (`entry_flourish.py`; one per character, nullable `scene` FK),
    `EntryFlourishRecord` (`models/endorsement.py`; actor self-grant receipt with
    partial UniqueConstraint `(character_sheet, scene) WHERE scene IS NOT NULL`).
    `ResonanceGainConfig.entry_flourish_grant` (default 10). The #904
    reaction-window framework is peer-only and was rejected for this use.
  - **Audere Majora + legend-deed minting (#953):**
    `RenownAwardConfig` (abstract base — `models/renown_config.py`; shared by
    `AudereMajoraThreshold` and `DramaticMomentType`; carries `magnitude` /
    `risk` / `reach` / `archetypes`; provides `as_renown_award_kwargs()`),
    `AudereMajoraThreshold` (inherits `RenownAwardConfig`; adds `deed_title`
    public field),
    `AudereMajoraCrossing.legend_entry` (OneToOneField → `societies.LegendEntry`,
    related_name `audere_majora_crossing`; null when `risk == NONE` or no primary
    persona). Deed minting fires via `_mint_crossing_deed` in `cross_threshold`.
  - **Resonance-environment interaction (2026-05-16):** `AffinityInteraction` (9-row
    tuning table; gains `consequence_pool` FK), `ResonanceEnvironmentConfig` (singleton),
    `ResonanceAlignmentBoonTier` (authored ALIGNED boon tiers per affinity/magnitude band)
  - **Spec C Resonance Gain (endorsements + audit — #1138):** `ResonanceGainConfig`
    (singleton pk=1 tuning surface), `PoseEndorsement` (weekly deferred; `endorser_sheet`
    FK, `resonance` FK (PROTECT), `persona_snapshot` FK to `scenes.Persona` (SET_NULL),
    unique `(endorser_sheet, interaction)`), `SceneEntryEndorsement` (immediate flat
    grant; same FK shape, unique `(endorser_sheet, endorsee_sheet, scene)`),
    `ResonanceGrant` (universal audit ledger — discriminator `source` + typed source FKs).
    Read surface: `InteractionListSerializer` now nests `pose_kind`, `endorsee_sheet_id`,
    `endorsable_resonances`, `pose_endorsers`/`my_pose_endorsement`,
    `entry_endorsers`/`entry_endorsed_by_me` on every `GET /api/interactions/?scene=<id>`
    row. Frontend: `EndorsementControl` in `PoseUnit` (`frontend/src/scenes/components/`).
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
  - Cap helpers: `compute_anchor_cap(thread) -> int` (FACET uses
    `lifetime_earned // DIVISOR` capped at `path_stage × HARD_MAX_PER_STAGE`;
    COVENANT_ROLE uses `current_level × 10`; SANCTUM uses
    `sanctum.feature_instance.level × 10`),
    `compute_path_cap(character_sheet) -> int`, `compute_effective_cap(thread) -> int`
  - Soul Tether config: `get_soul_tether_config() -> SoulTetherConfig` (lazy pk=1 singleton)
  - Soul Tether events: `SOUL_TETHER_DISSOLVED` emitted by `dissolve_soul_tether`
  - Soul Tether strain: `CharacterSheet.get_tether_strain_stage() -> int` (current Sineater
    Strain stage for the active resonance; used in sineating offer payloads)
  - VITAL_BONUS routing: `recompute_max_health_with_threads(character_sheet) -> int`,
    `apply_damage_reduction_from_threads(character, damage_amount) -> int`.
    `recompute_max_health_with_threads` calls `world.vitals.services.recompute_max_health`,
    which derives the base from `derive_base_max_health` when `base_max_health IS NULL`.
  - **Level-derived health (#1256, `world.vitals.services`):**
    - `derive_base_max_health(character_sheet) -> int` — base = class_term + stamina_term +
      covenant_term. Reads `effective_combat_level`; class_term sums
      `ClassStageHealthRate.health_per_level` per level via `stage_for_level`; stamina_term =
      `stamina × VitalsConsequenceConfig.stamina_to_health_weight`; covenant_term via
      `covenant_role_health`. Used when `CharacterVitals.base_max_health IS NULL`.
    - `covenant_role_health(character, level) -> int` — sum of
      `level × CovenantRoleBonus.bonus_per_level` over ENGAGED roles targeting the
      `max_health` ModifierTarget; one DB query, no query-in-loop.
  - Thread survivability baseline (#1175): `survivability_baseline(character, vital_target) -> int`
    (soft-capped formula `round(cap × S / (S + half_saturation))` keyed by
    `ThreadSurvivabilityTuning`; injected into DR and MAX_HEALTH paths above),
    `get_thread_survivability_tuning(vital_target) -> ThreadSurvivabilityTuning | None`,
    `seed_thread_survivability_tuning()` (idempotent; called by dev seed)
  - Resonance-environment (2026-05-16): `magical_profile(character_sheet) -> CharacterAura | None`
    (derived magic-capability gate; None = Quiescent);
    `resonance_environment_for_cast(*, caster_sheet, room_profile, technique)` (OPPOSED
    backfire, called as "Step 10" in the technique-use orchestrator);
    `refresh_resonance_alignment(*, character_sheet)` / `clear_resonance_alignment(*,
    character_sheet)` (ALIGNED presence buff, wired to `Character.at_post_move` /
    `at_pre_move` / `at_post_unpuppet`)
  - Outfit trickle (Spec D PR1): `outfit_daily_trickle_for_character(sheet) -> int` —
    issues `ResonanceGrant` rows (source=OUTFIT_TRICKLE, `outfit_item_facet` typed FK)
    for each worn item with matching facets; `resonance_daily_tick()` now calls this
    alongside residence trickle
  - Dramatic moment tagging (#1139):
    `create_dramatic_moment_tag(*, character_sheet, moment_type, tagged_by, scene, interaction=None) -> DramaticMomentTag`
    — validates resonance claim + per-scene cap; atomically creates tag, calls
    `grant_resonance(source=DRAMATIC_MOMENT)`, and calls `fire_renown_award` for the
    primary persona (skipped if none)
- **Key Methods:** `CharacterAura.dominant_affinity`,
  `Thread.target` (populated FK), `Thread.display_name`,
  `ThreadWeavingUnlock.display_name`
- **Enums:** `AffinityType`, `TargetKind` (Thread discriminator — values: TRAIT,
  TECHNIQUE, FACET, RELATIONSHIP_TRACK, RELATIONSHIP_CAPSTONE, COVENANT_ROLE,
  MANTLE, SANCTUM; bare ROOM removed), `EffectKind` (ThreadPullEffect),
  `VitalBonusTarget`, `RitualExecutionKind`, `AnimaRitualCategory`,
  `PendingAlterationStatus`, `AlterationTier`
- **Exceptions (used by services + views):** `AnchorCapExceeded`,
  `InvalidImbueAmount`, `ResonanceInsufficient`, `WeavingUnlockMissing`,
  `XPInsufficient`, `RitualComponentError`,
  `NoMatchingWornFacetItemsError` (FACET thread pull with no worn matching item) —
  all with `user_message` properties for safe API responses.
- **Integrates with:** traits (thread anchor kind TRAIT), progression (XP
  spend for ThreadWeaving and XP-lock crossings), relationships (soul tether,
  magical_flavor; thread anchors RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE),
  journals (`JournalEntry.related_threads` M2M), combat (CombatPull,
  DamagePreApply for DAMAGE_TAKEN_REDUCTION), vitals
  (MAX_HEALTH recompute), conditions (CAPABILITY_GRANT effects + Mage Scars),
  mechanics (Property via Ritual site_property),
  items (RitualComponentRequirement FKs ItemTemplate / QualityTier),
  flows (Ritual FLOW dispatch via FlowDefinition),
  covenants (`draft_validator_path` on Covenant Induction ritual → `assert_initiator_can_induct`)
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
  - `POST /api/magic/pose-endorsements/` + `DELETE .../pose-endorsements/{id}/` — create/retract pose endorsement (Spec C)
  - `POST /api/magic/scene-entry-endorsements/` — create entry endorsement; fires `grant_resonance` synchronously (Spec C)
  - `GET /api/magic/resonance-grants/` — paginated audit ledger (Spec C)
- **API endpoints (dramatic moment tagging — #1139):**
  - `GET /api/magic/dramatic-moment-types/` — unpaginated catalog for the tag-picker
  - `POST /api/magic/dramatic-moment-tags/` — create tag; `IsSceneGMOrOwnerOrStaff` gated
  - `GET /api/magic/dramatic-moment-tags/` — list tags; filterable by `character_sheet`/`scene`
- **API endpoints (entry-flourish declaration — #1140):**
  - `GET /api/magic/entry-flourish/pending/` + `GET .../pending/<id>/` — account-scoped
    pending entry-flourish offer inbox (#1140)
  - `POST /api/magic/entry-flourish/respond/` — body `{offer_id, resonance_id}`; resolves
    offer via `resolve_entry_flourish_offer` and fires the self-grant (#1140)
- **Source:** `src/world/magic/`
- **Details:** [magic.md](magic.md) · cast lifecycle (How Magic Works):
  [technique-use-pipeline.md](../architecture/technique-use-pipeline.md) · power ledger +
  penetration contest: [power-derivation.md](../architecture/power-derivation.md)

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
- **Handlers:** `obj.conditions` (`ConditionHandler` / `CharacterConditionHandler` in
  `world/conditions/handlers.py`, installed as `@cached_property` on `ObjectParent`).
  `CharacterConditionHandler.active` mirrors `get_active_conditions`. `.invalidate()`
  wired into all `world/conditions/services.py` mutation sites.
- **Key Functions:** `apply_condition()`, `remove_condition()`, `get_capability_status()`, `get_check_modifier()`, `get_resistance_modifier()`, `process_round_start()`, `process_round_end()`, `process_damage_interactions()`
- **Integrates with:** combat (DoT, capability blocking), magic (power sources, resonance-environment boon/injury application), progression (interactions)
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
### Appearance & Identity (architecture)
How Persona (identity), Form (real body), disguise/illusion (fake overlay), and the
true-form/natural baseline compose into what a viewer sees — plus the per-persona
descriptor overlay, cosmetic editing, and shapeshift slots.

- **Spans:** forms (body), scenes (Persona), character_sheets (anchor)
- **Key ideas:** four-question model; `(Persona × FormTrait)` descriptor; single
  render composition (viewer-gated); real-vs-fake truth ledger; cosmetic vs disguise
- **Status:** design (slices); depends on #1044
- **Details:** [appearance_and_identity.md](appearance_and_identity.md)
### Classes (Paths)
Character paths with evolution hierarchy through stages of power; also owns the
per-class, per-stage health rate authoring and the primary-class level service.

- **Models:** `Path`, `CharacterClass`, `CharacterClassLevel`,
  `ClassStageHealthRate` (authored per `(CharacterClass, PathStage)`;
  `health_per_level` SmallInt — the HP gained per level while in that stage band;
  unique `(character_class, stage)`)
- **Enums:** `PathStage` (Prospect L1, Potential L3, Puissant L6, True L11,
  Grand L16, Transcendent L21)
- **Key Services (`world.classes.services`):**
  - `stage_for_level(level) -> PathStage` — maps a class level to its PathStage band
    (breakpoints L1/3/6/11/16/21; clamps <1 to PROSPECT).
  - `set_primary_class_level(character, character_class, level) -> CharacterClassLevel`
    — upserts the primary class level and triggers a full `recompute_max_health_with_threads`
    so vitals reflect the new level immediately. **Always use this, never mutate
    `CharacterClassLevel` rows directly.**
- **Key Methods:** `Path.parent_paths`, `Path.child_paths` (evolution hierarchy)
- **Integrates with:** progression (level requirements), character_creation (Prospect
  selection), vitals (`derive_base_max_health` reads `ClassStageHealthRate` + `stage_for_level`)
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

### Positioning (#530 + #1017 + #1018)
Room-anchored spatial graph: named position nodes, traversable edges, per-object
occupancy, capability-gated movement, GM terrain blueprints, non-combat scene
positioning UI, and dynamic battlefield reshaping (aerial layer, chasms, consequence
effects for graph mutation and flight).

- **Models:** `Position` (`PositionKind` discriminator; `elevation_anchor` self-FK —
  the ground node an AERIAL or CHASM node is anchored to), `PositionEdge` (optional
  `gating_challenge` FK + `is_passable`), `ObjectPosition` (OneToOne occupancy);
  **abstract bases** `PositionNodeBase` / `PositionEdgeBase` shared by live and blueprint
  layers; **blueprint models** `PositionBlueprint` (reusable GM-authored layout),
  `BlueprintPosition`, `BlueprintEdge`; `RoomProfile.default_blueprint` FK
  (`evennia_extensions`) links a room to its preferred layout.
- **Key Services:** `create_position` / `remove_position` / `connect_positions` /
  `disconnect_positions` / `edge_between` / `place_in_position` /
  `move_to_position` (adjacency + passability + MOVEMENT capability + active-gating) /
  `force_move_to_position` / `position_of` / `reachable_positions` /
  `adjacent_open_positions`; **blueprint authoring** `create_blueprint` /
  `add_blueprint_position` / `connect_blueprint_positions` / `remove_blueprint`;
  **staging** `instantiate_blueprint(blueprint, room, *, replace=False)`;
  **aerial layer** `materialize_aerial_layer(room)` / `teardown_aerial_layer(room)` /
  `enter_aerial(objectdb)` / `leave_aerial(objectdb)`;
  **fall seam** `maybe_emit_fall(objectdb, position)` — emits `EventName.FELL` when entering a CHASM
- **Enums:** `PositionKind` (PRIMARY / FEATURE / ELEVATED / AERIAL / BARRIER_SIDE / CHASM);
  `PositionDestination` in `world/checks/constants.py`
  (ACTOR_POSITION / GATING_FAR_SIDE / NAMED) — governs `MOVE_TO_POSITION` effect destination
- **Seed factory:** `AerialPropertyFactory` (`world/mechanics/factories.py`) — get-or-create
  factory for the `"aerial"` `Property` tag used to track airborne objects
- **Shared serializers** (`positioning/serializers.py`): `PositionSummarySerializer`,
  `PositionAdjacencyItemSerializer`, `PersonaPositionSerializer` (used by both combat
  and scenes layers)
- **Actions:** `MoveToPositionAction` (`registry_key="move_to_position"`) + staff-only
  `SetTheStageAction` (`registry_key="set_the_stage"`, `StaffOnlyPrerequisite`)
- **Scene API:** `SceneDetailSerializer` exposes `positions`, `position_adjacency`,
  `persona_positions`
- **Frontend:** `MovementActions` (shared, in `frontend/src/combat/components/`) +
  `RoomPositionsPanel` (scene detail, in `frontend/src/scenes/components/`)
- **Pattern:** Spatial obstacles reuse `mechanics.ChallengeInstance` — no parallel obstacle model;
  aerial edges mirror ground adjacency but are always passable/ungated (flight bypasses obstacles)
- **Deferred:** gated blueprint edges (requires absent `instantiate_situation()` service);
  reactive fall consumer (catch/plummet tied to #520)
- **Integrates with:** combat (`CombatParticipant.current_position` / `CombatOpponent.current_position`),
  mechanics (Challenge/gating + `ConsequenceEffect` reshape handlers),
  flows (`EventName.FELL` reactive seam),
  actions (`MoveToPositionAction` / `SetTheStageAction`)
- **Source:** `src/world/areas/positioning/`
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
- **Legend deed from crossing:** `LegendEntry.audere_majora_crossing` — reverse
  OneToOne to `AudereMajoraCrossing` (magic app); set when `cross_threshold` mints
  a deed via `fire_renown_award` + `_mint_crossing_deed`.
- **Integrates with:** realms (Society.realm FK), character_sheets (Guise for identity), magic (Audere Majora crossing deed via `AudereMajoraCrossing.legend_entry`)
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

### Investigation & Discovery
The mystery core loop: a clue points at something worth finding (codex entry, mission, or a
held captive to rescue); players acquire clues by **searching** a room or via passive
**triggers**, then resolve them automatically or through a collaborative **research project**.

- **Models:** `Clue` (DiscriminatorMixin — `target_kind` ∈ CODEX / MISSION / RESCUE + a
  per-kind FK; never exists without a target), `CharacterClue` (held-clue, roster-scoped),
  `RoomClue` (search-anchored placement + `detect_difficulty` + `eligibility_rule`),
  `ClueTrigger` (passive on-entry placement + `eligibility_rule`), `ResearchProjectDetails`
  (the clue a `ProjectKind.RESEARCH` project researches toward)
- **Key functions (`world/clues/services.py`, `research.py`):** `acquire_clue`,
  `target_already_known`, `search_room` (Search check per hidden clue), `grant_clue_target`
  (AUTOMATIC resolution — codex KNOWN / rescue mission), `maybe_grant_clue_triggers`
  (on room entry), `plant_rescue_clue` / `clear_rescue_clues` (#931), `start_research_project`
  / `contribute_research` (floored CHECK→progress) / `resolve_research` (RESEARCH handler)
- **Action:** `SearchAction` (`actions/definitions/investigation.py`) — AP + mental fatigue
  via the declarative cost on the `Action` base; rolls the seeded "Search" CheckType
- **Two-layer gating:** the detect (skill) check *and* an `eligibility_rule` predicate on
  each placement (access layer; empty rule = open to anyone)
- **Integrates with:** codex (codex-target grant via `add_progress`), missions
  (`grant_rescue_mission`, mission target), projects (RESEARCH kind), captivity (RESCUE
  clues planted on capture / cleared on resolution), predicates (eligibility), checks
  (`perform_check`), actions (search), narrative (trigger notification), typeclasses
  (`Character.at_post_move` trigger hook)
- **Source:** `src/world/clues/`
- **Details:** [investigation_and_discovery.md](investigation_and_discovery.md)
### Consent
OOC visibility groups and per-category social consent preferences for player-controlled
content sharing and social action targeting (#1141).

- **Models:** `ConsentGroup`, `ConsentGroupMember`, `VisibilityMixin` (abstract),
  `SocialConsentCategory` (NaturalKey on `key`), `SocialConsentPreference` (OneToOne on tenure),
  `SocialConsentCategoryRule` (preference + category + ConsentMode), `SocialConsentWhitelist`
  (owner_tenure / allowed_tenure / category)
- **Key Methods:** `VisibilityMixin.is_visible_to()`, `_tenure_blocks_actor()`,
  `_social_consent_exclusions()` (both in `actions/player_interface.py`)
- **Key Functions:** `seed_social_consent_categories()` (`world/seeds/consent.py`),
  `make_default_categories()` (`world/consent/factories.py`)
- **API:** `/api/consent/` — categories (read-only), preferences, category-rules, whitelist
- **Pattern:** RosterTenure-based (player's tenure, not character); absent preference row = allow-all
- **Integrates with:** actions (`ActionTemplate.consent_category` FK), roster (RosterTenure),
  codex (visibility), seed loader (`arx seed dev`)
- **Source:** `src/world/consent/`
- **Details:** [consent.md](consent.md)
### Progression
XP, kudos, development points, and unlock system. Contains the most explicit prerequisite framework.

- **Models:** `ExperiencePointsData`, `XPTransaction`, `CharacterXP`, `DevelopmentPoints`, `DevelopmentTransaction`, `KudosPointsData`, `KudosTransaction`, `CharacterUnlock`, `XPCostChart`, `XPCostEntry`, `CharacterPathHistory`, `PathIntent` (player's declared next-path preference — one per character sheet; FK to `CharacterSheet` + `Path`)
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
  - `current_path_for_character(character) -> Path | None` (`selectors.py`) — returns the character's most-recent `CharacterPathHistory` path
  - `next_path_options(character) -> list[Path]` (`selectors.py`) — returns active child paths of the current path (or all top-level paths if no current path); used by `PathOptionsView`
- **API Endpoints (progression):**
  - `GET /api/progression/path-options/` — current path + selectable next paths (character via `X-Character-ID` header) → `PathOptions` schema; transition-generic, reused beyond any single transition type
  - `GET /api/progression/path-intent/` — declared `PathIntent` or `null` (character via `X-Character-ID` header)
  - `PUT /api/progression/path-intent/` — declare a path intent; body `{ path_id }` (character via `X-Character-ID` header)
  - `DELETE /api/progression/path-intent/` — clear declared intent (character via `X-Character-ID` header)
- **Pattern:** `AbstractClassLevelRequirement` base class with polymorphic `is_met_by_character()` — extend this for new prerequisite types (society, relationship, etc.)
- **Integrates with:** traits (unlock requirements), classes (path unlocks), goals (XP rewards), magic (Audere Majora offer pre-selects from `PathIntent.intended_path_id` via `get_intended_path_id` on `PendingAudereMajoraOfferSerializer`)
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
Roleplay session recording with participant tracking, interaction logging, persona-based identity, and social action consent flow.

- **Models:** `Scene`, `SceneParticipation`, `Persona`, `SceneActionRequest`, `SceneActionTarget`, `SceneCastPullDeclaration`
- **Social action consent:** `SceneActionRequest` owns the full lifecycle (dispatch → consent → resolution) for the primary target; `SceneActionTarget` rows carry additional targets, each with independent consent and result. Resolvers fire once per accepted target (primary via `respond_to_action_request`, additional via `respond_to_action_target`).
- **Key Functions:**
  - `create_action_request(scene, initiator_persona, target_persona, action_key, ...)` — dispatches a request; NPC additional targets auto-accept immediately.
  - `respond_to_action_request(action_request, decision)` — primary-target consent + resolution.
  - `respond_to_action_target(action_target, decision)` — per-additional-target consent + resolution (never touches siblings).
  - `broadcast_scene_message(scene, action)` — pushes scene state to participants via WebSocket.
- **Read-visibility surface (canonical):**
  - `Scene.objects.viewable_by(account)` — queryset; staff=all, auth non-staff=public OR participant,
    anonymous=public. Use in `get_queryset()` / filter chains.
  - `scene.is_viewable_by(account)` — per-instance predicate; same semantics; uses
    `participations_cached` (zero queries for identity-mapped scenes). Use in object-permission checks.
  - `Interaction.objects.visible_to(account, persona_ids=..., since=...)` — queryset; the
    pose-level read tiers (room-heard public, pinned party, present/participated, GM-of-scene;
    very-private excluded except for the party). Consumed by `InteractionViewSet.get_queryset`
    and `SceneViewSet.highlight_reel`.
  - **Do not inline this logic.** `SceneViewSet`, `ReadOnlyOrSceneParticipant`, the combat
    encounter read gate, and the interaction/reel read gates all consume these forms.
- **Highlight reel (#1241):** `GET /api/scenes/{id}/highlight-reel/` — a fully-sealed featured
  moment + ranked index (ids only), ranked by `InteractionReaction` counts (a queryset-level
  `Count` annotation, no denormalized column), GM-tagged poses headline. Filtered through
  `Interaction.objects.visible_to`. Frontend: `HighlightReel` (`frontend/src/scenes/components/`).
- **API Endpoints:** `GET/POST /api/action-requests/`, `POST /api/action-requests/{id}/respond/`,
  `GET /api/action-targets/` (read-only; filterable by `scene` + `status`; surfaces pending
  additional-target consent rows for the authenticated player's personas).
- **Frontend:** `ConsentPrompt` polls both `GET /api/action-requests/?scene={id}&status=pending`
  and `GET /api/action-targets/?scene={id}&status=pending` every 5 s and renders amber consent cards for
  each; additional-target accepts/denies pass `target_persona_id` to the shared respond endpoint.
- **Integrates with:** roster (characters), stories (EpisodeScene join), instances (preservation check),
  flows (auto-logging via message_location), combat (encounter read gate via `Scene.objects.viewable_by`),
  actions (resolver registry via `get_resolver(action_key)`), consent (`SocialConsentCategory` enforcement)
- **Source:** `src/world/scenes/`
- **Details:** [scenes.md](scenes.md)
### Stories
Player-driven narrative campaign system with hierarchical structure and task-gated progression.

- **Models:** `Story` (incl. `summary` — player-facing "The Story So Far"; `description` = GM pitch), `Chapter`, `Episode`, `Transition`, `Beat`, `BeatCompletion`, `EpisodeResolution`, `StoryProgress`, `GroupStoryProgress`, `GlobalStoryProgress`, `AggregateBeatContribution`, `AssistantGMClaim`, `SessionRequest`, `StoryNote` (append-only OOC authorial memory, never player-visible), `Era`, `StoryParticipation`, `PlayerTrust`, `TrustCategory`
- **Authoring backbone enums:** `StoryScope.UNASSIGNED` (new default), `StoryMaturity` (PITCH/OUTLINE/PLOT — per-node authoring completeness on Story/Chapter/Episode), `BeatKind` (SITUATION/ENCOUNTER/TASK/REQUIREMENT), `ProgressStatus` (ACTIVE/WAITING_FOR_GM/RESTING/COMPLETED on the three Progress models; **not currently exposed to the frontend** — see stories.md follow-ups)
- **GM↔player visibility contract:** `description`/`consequences` are GM/staff-only; `summary` is player-facing ("The Story So Far"), blanked while node `maturity == PITCH`. Enforced server-side in two places: the three Detail serializers' `to_representation` (via `_gm_text_gate`, default-deny when no request) **and** `serialize_story_log` (per-beat internals gated to privileged roles). No dedicated `pitch` field by design — `description`=GM pitch, `summary`=player recap
- **Reactivity entry points (Phase 3):** `stories.services.reactivity.on_character_level_changed` / `on_achievement_earned` / `on_condition_applied` / `on_condition_expired` / `on_codex_entry_unlocked` / `on_story_advanced`
- **Key Services:** `evaluate_auto_beats`, `record_gm_marked_outcome`, `record_aggregate_contribution`, `get_eligible_transitions`, `resolve_episode` (reconciles ProgressStatus on advance; distinguishes routing-block from authoring frontier), `create_character_progress` / `create_group_progress` / `create_global_progress` (reject UNASSIGNED scope), `services.frontier.resolve_frontier` / `set_progress_status`, `services.maturity.promote_episode_maturity`, `services.dashboards.compute_story_status_line`, `catch_up_character_stories` (called from `Character.at_post_puppet`)
- **API Endpoints:** `POST /api/episodes/{id}/promote/` (set node maturity; PLOT-gate mirrored in `PromoteEpisodeInputSerializer` → 400 on gate violation), `POST /api/stories/{id}/assign-to-scope/` (lift a story out of UNASSIGNED; sets scope + creates the matching progress record; 400 if already-assigned or scope↔target invariant violated), `GET /api/stories/gm-queue/` + `GET /api/stories/staff-workload/` (now query-bounded with `assertNumQueries` locks; staff-workload per-GM membership is status-agnostic), plus standard ViewSet CRUD and the existing `log/` / `my-active/` / `resolve-episode/` / beat-`mark`/`contribute` / AGM-claim / session-request actions, and append-only `/api/story-notes/`
- **Authoring/run-control UI:** `StoryAuthorPage` carries the run-control surface — `PromoteMaturityButton` (inline PLOT-gate 400), `ScopeAssignDialog`, GM Notes tab (StoryNote), inline `ProgressStateBanner`, Resolve/Mark run-control, nimble +Beat/+Branch quick-add; `BeatFormDialog` exposes kind/advances/risk (risk staff-gated); forms use "Internal GM Description" / "The Story So Far" labels + episode `resting_conclusion`/`is_ending`
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
### NPC Services
Unified "ask NPC for thing" framework: per-NPC-role offer surface, persona-keyed standing,
per-kind effect handler dispatch. Covers permits today; missions/loans/training/favors
register as additional kinds.

- **Models:** `NPCRole`, `NPCServiceOffer` (kind discriminator + draw_mode + eligibility_rule),
  `PermitOfferDetails` (1:1 per-kind details; mirrors `ItemFacet` composition),
  `NPCStanding` (per-(PC persona, NPC persona); relocated from `world.missions.MissionGiverStanding`)
- **Constants:** `OfferKind` (PERMIT; future MISSION/LOAN/TRAINING/POLITICAL_FAVOR/...), `DrawMode` (MENU, POOL)
- **Effect dispatch:** `OFFER_EFFECT_HANDLERS: dict[str, Callable]` in
  `world.npc_services.effects` — keyed on `OfferKind`. Plan 2 ships a PERMIT stub;
  Plan 3 (#668) fills in real `BuildingPermit` ItemInstance creation. Mission migration
  onto this dispatch is #686.
- **Interaction state machine:** ephemeral `InteractionSession` (lives in caller's
  session for one interaction). `start_interaction(role, persona, character, npc_persona=None)`
  → `available_offers(session)` (single-predicate filtered) → `resolve_offer(session, offer)`
  → `end_interaction(session)` (persists new affection for class-2+ NPCs).
- **Predicate engine reuse:** `world.predicates` (shared utility — see entry below).
  `min_npc_standing` and persona-scoped `has_item` leaves live there.
- **Seeding:** `ensure_builders_guild_clerk_role()` in `world.npc_services.seeds` —
  idempotent get_or_create; NOT a committed fixture (per #683).
- **API:** `/api/npc-services/standings/`, `/api/npc-services/roles/`, `/api/npc-services/offers/`,
  `/api/npc-services/cooldowns/`, `/api/npc-services/permit-details/` — staff CRUD.
  `/api/npc-services/interactions/{start,resolve,end}/` — player-facing interaction state machine
  (session-backed; one active interaction per Django session).
- **Cross-app dependencies:** `world.predicates` (engine), `world.scenes.Persona`,
  `world.items.ItemInstance`, `world.societies.Organization`, `world.checks` (perform_check
  for non-final check-based actions), `core.mixins`.
- **Source:** `src/world/npc_services/`

### Predicates (shared rule engine)
Structural rule-tree evaluator + leaf-resolver registry. Consumers: missions
(`MissionTemplate.availability_rule`, `MissionOption.rule_json`), npc_services
(`NPCServiceOffer.eligibility_rule`), distinctions (`DistinctionPrerequisite.rule_json`).

- **Module:** `src/world/predicates/predicates.py` (no models — pure Python)
- **Key entry points:** `evaluate(rule: dict, ctx: PredicateContext) -> bool`,
  `CharacterPredicateContext(character, presented_persona=None)` (concrete context),
  `LEAF_RESOLVERS: dict[str, Callable]` (registered leaf names)
- **Leaves shipped:** `has_distinction`, `has_achievement`, `has_condition`, `has_capability`,
  `has_thread`, `min_thread_level`, `min_trait`, `has_skill`, `min_character_level`,
  `has_codex_entry`, `has_resonance`, `min_npc_standing`, `is_member_of_org`,
  `min_org_reputation`, `min_society_standing`. `has_item` exists in code but isn't
  registered yet — Plan 3 (#668) wires the PERMIT dispatch entry alongside its details
  model in a single PR.
- **Extension:** add a leaf by writing `_resolve_*(ctx, **params) -> bool` and registering
  it in `LEAF_RESOLVERS`. Persona-aware resolvers read `ctx.presented_persona`; sheet-keyed
  resolvers walk `ctx.sheet`; legacy ObjectDB-keyed resolvers walk `ctx.character`.
- **Source:** `src/world/predicates/`

### Projects (delayed multi-tick endeavors)
Project framework: kind-discriminated long-running endeavors with contributions and
outcome rolls. Plan 1 shipped the framework + two kinds (BUILDING_CONSTRUCTION,
ROOM_FEATURE_PROGRESSION).

- **Models:** `Project` (kind discriminator + status + completion_mode), `Contribution`
  (per-actor per-project contribution log; privacy-aware), per-kind details models
  (`BuildingConstructionDetails`, `RoomFeatureProgressionDetails`)
- **Constants:** `ProjectKind`, `ProjectStatus`, `CompletionMode`, `ContributionKind`,
  `ContributionPrivacy`
- **Stat definitions:** Project achievement stats are seeded in `AppConfig.ready()` via
  `register_stat_definitions()`
- **Cross-app dependencies:** `world.scenes.Persona`, `societies.Organization`
- **Source:** `src/world/projects/`

### Buildings (Permits + Construction + Materials)
Plan 3 (#668). Permits authorize **(ward × kind)** building construction via the
unified NPCServiceOffer PERMIT effect handler. Buildings spawn from completed
`BUILDING_CONSTRUCTION` Projects with materials snapshotted onto the building.

- **Models:** `BuildingKind` (open catalog with 9 non-exclusive flags: residential/
  commercial/fortified/occult/maritime/agrarian/aerial/subterranean/secret +
  `rooms_per_size_tier` multiplier), `Building` (decorates an Area at level
  BUILDING; `target_size`, `target_grandeur`, `max_rooms` mutable), `BuildingMaterial`
  (per-building snapshot of materials used at construction), `MaterialLoreEffect`
  (per-template special properties — godswar stone → resonance_amp etc.; zero
  rows shipped, content-authored), `BuildingPermitDetails` (persona-scoped permit
  holder, building_kind + approved_wards M2M), `BuildingConstructionDetails`
  (Project per-kind payload for BUILDING_CONSTRUCTION).
- **Key functions** (`world.buildings.services`):
  - `issue_permit(offer, persona) -> EffectResult` — real PERMIT effect handler
    (replaces Plan 2's stub; registered via `BuildingsConfig.ready()`)
  - `validate_permit_site(permit_details, site_room, acting_persona, target_size) -> ValidationResult`
    — raises typed `PermitValidationError` subclasses with `user_message`
  - `activate_permit(permit_details, site_room, acting_persona, target_size, target_grandeur) -> Project`
    — consumes the permit, spawns the construction project
  - `complete_building_construction(project) -> Building` — runs at project completion;
    spawns Building, snapshots materials, deletes consumed instances
  - `contribution_value_for_construction(contribution) -> int` — material/money
    value formula (materials ~110% baseline, lore-bearing materials scale by
    `lore_value`)
- **Formula:** `Building.max_rooms = BuildingKind.rooms_per_size_tier × Project.target_size`.
  House at `rooms_per_size_tier=20` gives Size-1=20, Size-5=100, Size-10=200 rooms.
- **Action:** `ActivatePermitAction` (in `src/actions/definitions/items.py`).
- **Predicate leaf:** `has_item` (persona-scoped) registered with the
  `building_permit` dispatch entry — checks if a persona holds an unconsumed
  building permit.
- **Seeding:** `ensure_plan_3_seeds()` in `world.buildings.seeds` (get-or-create
  the BuildingPermit ItemTemplate + House BuildingKind + wires House onto
  Builders Guild Clerk PERMIT offers). NOT a committed fixture (per #683).
- **Out of scope, filed as followups:** BuildingKind catalog expansion (#694),
  MaterialLoreEffect content authoring (#695), Building → Neighborhood → Domain
  progression (#696), BUILDING_RENOVATION / BUILDING_EXTENSION / BUILDING_UPGRADE
  project kinds (#673), placeholder room generation upgrade (#670 Room Builder
  Tool).
- **Cross-app dependencies:** `world.areas` (Area + AreaClosure + ward fields),
  `world.items` (ItemTemplate + ItemInstance + OwnershipEvent + `lore_value`),
  `world.projects` (Project + Contribution), `world.npc_services` (NPCRole +
  NPCServiceOffer + PermitOfferDetails), `world.scenes` (Persona), `world.predicates`
  (`has_item` leaf dispatch).
- **Source:** `src/world/buildings/`

### Room Features (Plan 4 framework — Subsystem E)
Plan 4 (#669, shipped via #703). Generic per-room enhancement framework — a
`RoomFeatureInstance` decorates a `RoomProfile` and dispatches per-kind logic
via a strategy enum. The first kind shipped is **SANCTUM** (see Sanctum below);
future kinds (Library, Training Room, Lab, etc. — #675) plug in by
registering a service strategy + per-kind details model.

- **Models** (`world.room_features.models`):
  - `RoomFeatureKind` — open catalog row. Carries `service_strategy`
    (TextChoices: `SANCTUM`, future kinds), `max_level` (cap on
    `RoomFeatureInstance.level`), display copy, install-cost knobs.
  - `RoomFeatureKindInstallRitual` — M2M-shape: which Rituals can install
    this kind. Lets one kind admit multiple install rites
    (Sanctification of own home vs. Covenant Sanctification).
  - `RoomFeatureKindOwnerType` — M2M-shape: which `HolderType` values
    (PERSONA / ORGANIZATION) may own this kind. Validated at install.
  - `RoomFeatureInstance` — per-(room, kind) decoration. OneToOne to
    `RoomProfile`; `level` field mutable via upgrade projects. One
    instance per room (unique constraint).
  - `RoomFeatureProgressionDetails` — Project per-kind payload for
    `ROOM_FEATURE_PROGRESSION` projects (install + upgrade). Carries the
    `feature_kind` + `target_level` + `existing_instance` (null for
    install; set for upgrade).
- **Dispatch:** each `service_strategy` value resolves to a
  `handle_progression(project, details) -> RoomFeatureInstance` strategy
  function. SANCTUM strategy lives at
  `world.magic.services.sanctum.handle_progression`; future kinds
  register their own.
- **Tests:** `src/world/room_features/tests/`. SANCTUM install and
  upgrade are exercised end-to-end via the SanctumDetails layer below.
- **Source:** `src/world/room_features/`

### Sanctum (Plan 4 §F — first Room Feature kind)
Plan 4 §F (#669 §F, shipped via #703). Per-resonance per-room
generation surface installed via the Ritual of Sanctification. Two
ownership modes (`SanctumOwnerMode`): `PERSONAL` (persona-owned home)
and `COVENANT` (covenant-owned sacred ground). Resonance income is
NOT stored on the Sanctum — it accumulates per-weaver into
`SanctumPendingPayout` "wells" via the daily cron tick, and weavers
drain the well by physically visiting and performing an absorb action.

- **Models** (`world.magic.models.sanctum`):
  - `SanctumDetails` — OneToOne to `RoomFeatureInstance` (the framework
    decoration), carrying `resonance_type` (FK to `Resonance`),
    `owner_mode`, optional `founder_character_sheet` (set at
    Sanctification; null only for seed/historical/test rows), ritual
    cooldown timestamps, and `pending_sacrifice_overflow` escrow. One
    PERSONAL Sanctum per founder (partial unique constraint).
  - `SanctumPendingPayout` — per-(sanctum, weaver) "well" with separate
    `pending_weaving` + `pending_owner_bonus` totals. Capped at
    `SANCTUM_PENDING_PAYOUT_CAP = 1000` (sum of both fields); ticks
    no-op once full. Unique per (sanctum, weaver_character_sheet).
- **Key functions** (`world.magic.services.sanctum_install`):
  - `perform_sanctification(room_profile, leader, resonance, *, owner_mode) -> SanctificationResult`
    — Ritual of Sanctification entry point. Validates physical
    presence, ownership match, no-existing-feature, founder-cap (1
    Personal per founder); creates `RoomFeatureInstance` + `SanctumDetails`.
  - `perform_dissolution(sanctum, leader) -> DissolutionResult` —
    Ritual of Dissolution. Tiered recovery (BOTCH 0% / FAIL 10% /
    SUCCESS 50% / CRIT 80%); founder-vs-non-founder difficulty
    multiplier 2.0×; cascades the Sanctum decoration off the room.
  - `absorb_sanctum_pool(sanctum, weaver) -> AbsorbResult` — drains
    the weaver's `SanctumPendingPayout` into `grant_resonance` ledger
    rows (`SANCTUM_WEAVING` + `SANCTUM_OWNER_BONUS` as separate
    sources) when the weaver is physically present in the room.
- **Cron** (`world.magic.services.sanctum_cron`):
  - `sanctum_resonance_generation_tick()` — daily, registered as
    `sanctum.resonance_generation_tick`. Walks every SANCTUM
    `RoomFeatureInstance`; per-Sanctum, computes per-weaver income
    `max(thread.level, 1) × effective_value(room, resonance) ×
    LEVEL_MULTIPLIERS[level-1] × K_INCOME_RATE` and bumps the well
    (capped). Owner / active-covenant-member weavers also accrue +1
    `pending_owner_bonus` per OTHER thread.
- **Dormancy gating (#671):** `_sanctum_is_dormant(sanctum, threads)`
  early-returns from `_payout_for_sanctum` when the Sanctum is
  Dormant. PERSONAL gates on `founder.is_dormant`; COVENANT gates on
  `all(t.owner.is_dormant for t in threads)`. Public
  `world.magic.services.sanctum_state.sanctum_is_dormant(sanctum)`
  for UI / API callers.
- **API endpoints** (`world.magic.views_sanctum`):
  - `POST /api/magic/sanctums/install/` — `perform_sanctification` wrapper.
  - `POST /api/magic/sanctums/<id>/dissolve/` — `perform_dissolution`.
  - `POST /api/magic/sanctums/<id>/absorb/` — `absorb_sanctum_pool`.
  - `GET /api/magic/sanctums/` — list + per-sanctum detail with
    viewer-context `pending_weaving` / `pending_owner_bonus` / `is_founder`.
- **Cross-app dependencies:** `world.room_features` (the framework),
  `world.locations` (`effective_value` / `LocationValueModifier`
  RESONANCE rows that feed the income pool, `effective_owner` for
  bonus eligibility), `world.magic.models.Thread` (SANCTUM-targeted
  threads with `SanctumSlotKind` PERSONAL_OWN / COVENANT / HELPER),
  `world.character_sheets` (`is_dormant` for #671 gating),
  `world.covenants` (`CharacterCovenantRole` for covenant-mode bonus).
- **Source:** `src/world/magic/models/sanctum.py`,
  `src/world/magic/services/sanctum*.py`.

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
  - `covenant_role_bonus(sheet, target) -> int` (Spec D §5.6, #985) — loops
    `currently_engaged_roles()` × equipped items; compatible slot adds `role_bonus`
    (stacks on combat's gear read); incompatible slot adds `max(0, role_bonus -
    gear_stat)`; 0 when no roles engaged. `role_base_bonus_for_target` and
    `item_mundane_stat_for_target` now wired (#985)
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
- **EffectType values** (`world/checks/constants.py` — dispatched by `world/mechanics/effect_handlers.py`):
  - Pre-#1018: `APPLY_CONDITION`, `REMOVE_CONDITION`, `ADD_PROPERTY`, `REMOVE_PROPERTY`,
    `DEAL_DAMAGE`, `LAUNCH_ATTACK`, `LAUNCH_FLOW`, `GRANT_CODEX`, `MAGICAL_SCARS`,
    `LEGEND_AWARD`, `CAPTURE`, `ESCAPE_CAPTIVITY`, `RESCUE_CAPTIVE`
  - Added in #1018: `CREATE_POSITION`, `MOVE_TO_POSITION`, `SEVER_EDGE`,
    `CONNECT_EDGE`, `GRANT_FLIGHT`, `REMOVE_FLIGHT`
- **Integrates with:** distinctions (modifier sources), conditions (modifier sources), traits (stat modifiers),
  action_points (AP modifiers), goals (goal domains), positioning (reshape handlers in effect_handlers.py)
- **Source:** `src/world/mechanics/`
- **Details:** [mechanics.md](mechanics.md)

### Items & Equipment
Items, equipment, inventory, and currency. Spec D PR1 shipped facets, equip/unequip
services, and equipment-modifier integration. Spec D PR2 (#1031) added the generic
crafting framework and check-driven facet/style attachment.

- **Models:**
  - `QualityTier`, `InteractionType`, `ItemTemplate`, `TemplateSlot`, `ItemInstance`,
    `TemplateInteraction`, `EquippedItem`, `OwnershipEvent`, `CurrencyBalance`
  - `ItemFacet` (Spec D §4.2) — through-model linking `ItemInstance` ↔ `Facet` with
    `attachment_quality_tier`; unique per (item_instance, facet)
  - `ItemStyle` — through-model linking `ItemInstance` ↔ `Style` with
    `attachment_quality_tier`; unique per (item_instance, style)
  - **Crafting sub-models** (`world.items.crafting`, registered under the `items` app):
    `CraftingRecipe` (one per `CraftingRecipeKind`; carries check config + AP/anima cost +
    default consumption policy), `CraftingMaterialRequirement` (ingredient rows),
    `CraftingSkillCap` (skill-rank → quality ceiling ladder), `CraftingRecipeConsequence`
    (weighted consequence pool entry with per-row `cost_consumption` override). Replaces
    the old `FacetCraftingConfig` singleton.
- **New fields on `ItemTemplate` (Spec D PR1):** `facet_capacity` (max attachable facets,
  default 0), `gear_archetype` (CharField, `GearArchetype` enum choices)
- **New field on `ItemTemplate` (#1024):** `on_use_target_kind` (nullable `TargetKind` CharField)
  — null = self-use only; CHARACTER/ITEM/ROOM = requires an external target of that kind (validated
  by `OnUseTargetPrerequisite` before `use_item` is called); PERSONA and unknown values fail closed
- **Enums:** `BodyRegion` (17 body regions), `EquipmentLayer` (skin/under/base/over/outer/
  accessory), `OwnershipEventType` (created/given/stolen/transferred/activated/consumed),
  `GearArchetype`; `PROVENANCE_EVENT_TYPES` frozenset (GIVEN/STOLEN/TRANSFERRED — transfer
  provenance used by the lore-critical predicate); `CraftingRecipeKind` (FACET_ATTACH,
  STYLE_ATTACH); `CostConsumption` (NONE, PARTIAL, FULL)
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
  - `use_item(item_instance, user, target=None) -> UseItemResult` — applies on-use pool effects;
    consumables spend a charge and are destroyed at 0 (soft- or hard-delete); non-consumable
    usable items are reusable (no charge spent, `ACTIVATED` event logged). Raises `ItemNotUsable`
    (no `on_use_pool`) or `NoChargesRemaining` (consumable at 0 charges)
  - `hard_delete_item_instance(item_instance) -> None` (`world/items/services/usage.py`) —
    deletes the whole footprint: ledger rows then game_object/instance; no dangling FKs
  - `purge_expired_soft_deleted_items(*, grace=None) -> int` (`world/items/services/cleanup.py`)
    — hard-deletes soft-deleted, non-lore-critical items past the grace period; called
    by the `items.soft_delete_cleanup` daily cron task (#1025)
  - **Crafting orchestration** (`world.items.crafting.services`):
    - `run_crafting_recipe(*, kind, crafter_account, crafter_character, item_instance, target)
      -> CraftRunResult` — atomic 8-step pipeline (pre-validate → afford → roll →
      consequence → consume → attach); raises `CraftingNotConfigured` / `CraftingCostUnaffordable`
    - `build_crafting_quote(*, kind, crafter_character, crafter_character_sheet, target)
      -> CraftingQuote` — read-only cost+quality snapshot; no mutation
    - `stage_and_assert_affordable(*, recipe, crafter_character, crafter_character_sheet)
      -> StagedCost` (`world.items.crafting.cost`)
    - `consume_cost(*, crafter_character, staged, consumption) -> dict`
      (`world.items.crafting.cost`)
    - `resolve_capped_tier(*, recipe, crafter_character, check_result) -> QualityTier`
      (`world.items.crafting.quality`)
  - **Domain wrappers** (`world.items.services.crafting`):
    - `craft_attach_facet(*, crafter_account, crafter_character, item_instance, facet)
      -> FacetCraftResult`
    - `craft_attach_style(*, crafter_account, crafter_character, item_instance, style)
      -> StyleCraftResult`
    - `compute_quality_score(check_result, *, step, min_success_level) -> int`
  - **Shared material helper** (`world.items.services.materials`):
    - `gather_consumable_pks(*, available, requirements) -> list[int]` — validates inventory,
      returns PKs to delete; also used by the ritual path
    - `consume_pks(pks) -> None`
    - `meets_quality_tier(inst, requirement) -> bool`
- **Predicates on `ItemInstance`:**
  - `differs_from_template` — True if instance has any per-instance data (custom name/desc,
    lore_value, quality_tier, facets, or non-CREATED provenance); gates soft- vs. hard-delete
    at 0 charges
  - `is_lore_critical` — True if the item must never be auto-purged: `lore_value != 0`,
    OR has facets, OR has GIVEN/STOLEN/TRANSFERRED provenance
- **Usable vs consumable:** `ItemTemplate.is_usable` (= `on_use_pool_id is not None`) is the
  canonical predicate; `use_item`, `ItemUsablePrerequisite`, and the serializer all delegate to it.
  *Consumable* is the subset where `template.is_consumable` is True; consumables spend a charge
  per use and are destroyed at 0 charges. Non-consumable usable items are reusable.
- **Serializer field `is_usable`:** `ItemInstanceReadSerializer` exposes `is_usable` (bool,
  `SerializerMethodField`) — `True` iff `template.on_use_pool_id is not None`. Clients gate the
  Use button on this field.
- **`UseItemAction`** (`key="use_item"`, `src/actions/definitions/items.py`) — action-layer entry
  point routing both telnet and web through prerequisites + `use_item`. kwargs: `item` (held
  instance), optional `target` (validated by `OnUseTargetPrerequisite` against
  `on_use_target_kind`). Visibility gate is a same-location MVP proxy; no perception system yet.
  Telnet: `CmdUse` (`use <item>` / `use <item> on <target>`, alias `apply`).
- **Exceptions:** `FacetAlreadyAttached`, `FacetCapacityExceeded`, `StyleAlreadyAttached`,
  `StyleCapacityExceeded`, `SlotConflict`, `SlotIncompatible`, `ItemNotUsable`,
  `NoChargesRemaining`, `CraftingNotConfigured`, `CraftingCostUnaffordable` — all in
  `world.items.exceptions`
- **API Endpoints:**
  - `/api/items/quality-tiers/`, `/api/items/interaction-types/`, `/api/items/templates/`
    (read-only catalog)
  - `GET/POST /api/items/item-facets/` — list/attach via `craft_attach_facet`
    (owner-or-staff perm); returns `FacetCraftResult` (201 on attach, 200 on failed roll);
    `DELETE /api/items/item-facets/{id}/` — remove
  - `GET /api/items/item-facets/quote/` — `?item_instance=<pk>&facet=<pk>` — read-only
    crafting quote; returns `CraftingQuoteSerializer`
  - `GET/POST /api/items/item-styles/` — list/attach via `craft_attach_style`; returns
    `StyleCraftResult`; `GET /api/items/item-styles/quote/` — read-only quote
  - `GET /api/items/equipped-items/` — list/retrieve (read-only); equip and
    unequip route through the action layer via the WebSocket `execute_action`
    inputfunc (`{action: "equip" | "unequip", kwargs: {target_id: N, ...}}`)
    or the telnet `wear` / `remove` / `get` / `drop` commands
  - `GET /api/items/inventory/` — read-only inventory list (`.in_play()` filtered)
  - `POST /api/items/inventory/<pk>/use/` — use item; owner-or-staff gated; returns
    `UseItemResult` (`charges_remaining`, `consumed`, `result_text`); `ItemError` → HTTP 400
- **Pattern:** Templates define archetypes; instances hold per-item state. Equipment uses
  region + layer grid (unique constraint per character). Facets attach up to `facet_capacity`
  per item via the crafting framework; worn facets feed the mechanics modifier walk (see
  Mechanics §EQUIPMENT_RELEVANT). Crafting is data-driven: new kinds register a handler +
  author a `CraftingRecipe` row — no schema change.
- **Frontend:** `WardrobePage` (outfits, equipped items, inventory grid, item detail drawer);
  `ItemDetailPanel` shows a **Use** button when `item.is_usable` is true (disabled for
  depleted consumables), calls `POST /api/items/inventory/<pk>/use/`, and renders an inline
  result block (charges remaining / consumed / text); errors toast the backend `user_message`.
  `AttachFacetDialog` (facet-only picker surfacing rolled outcome/tier) launched from
  `ItemDetailPanel`'s action row.
- **Integrates with:** mechanics (equipment modifier walk via `passive_facet_bonuses` +
  `covenant_role_bonus`), magic (outfit trickle, `outfit_item_facet` ResonanceGrant FK,
  ritual material consumption via shared `gather_consumable_pks`), covenants (gear archetype
  compatibility), checks (`perform_check` + consequence pool)
- **Source:** `src/world/items/`
- **Details:** [items.md](items.md)

### Covenants
Magically-empowered group oaths with roles, gear compatibility, a per-covenant rank
ladder, and a Mentor's Vow bond system for level-mismatched parties (#1165).

**Standing invariant:** `CovenantRole` = combat power (archetype, speed_rank,
Thread pulls). `CovenantRank` = administrative authority (invite/kick/manage).
These two axes are orthogonal — never re-merge them.

- **Models:**
  - `CharacterCovenantRole` — per-character membership row; `left_at IS NULL` =
    currently active. Fields include `covenant` FK, `covenant_role` FK, `engaged`
    boolean, `rank` FK → `CovenantRank`.
  - `GearArchetypeCompatibility` — existence-only join: which `CovenantRole`s are
    compatible with which `GearArchetype` values (read-only authored content)
  - `CovenantRoleBonus` — authored config: one row per
    `(CovenantRole, ModifierTarget)` with `bonus_per_level` SmallInt.
    `role_base_bonus_for_target(role, target, char_level)` returns
    `char_level × bonus_per_level`; no row → 0. Admin-registered.
  - `CovenantRank` — per-covenant administrative authority tier.
    Fields: `covenant` FK, `name`, `tier` (1 = top authority), `description`,
    `can_invite`, `can_kick`, `can_manage_ranks`. Unique `(covenant, tier)` and
    `(covenant, name)`.
  - **`MentorBondConfig`** (pk=1 singleton, #1165) — `band_width` (default 2),
    `adjacency_offset` (default 1), `max_sidekicks_per_mentor` (nullable = unlimited).
    Staff-tunable in Django admin.
  - **`MentorBond`** (#1165) — per-pair bond record. `covenant`, `mentor_sheet`,
    `sidekick_sheet`, `adjusted_party` (`MentorBondAdjusted.MENTOR`/`SIDEKICK`),
    `formed_at`, `dissolved_at` (null = active). Partial unique on
    `(covenant, sidekick_sheet)` when active; dissolved bonds are retained as audit
    trail. Custom manager: `.active()` → `dissolved_at__isnull=True`.
- **Handlers:**
  - `character.covenant_roles` (`CharacterCovenantRoleHandler`) — `has_ever_held(role)`,
    `currently_held_role_in(covenant)`, `currently_engaged_roles()` (returns a list),
    `invalidate()`
- **Key Services:**
  - `assign_covenant_role(sheet, role) -> CharacterCovenantRole`
  - `end_covenant_role(role_assignment) -> None`
  - `kick_member(*, target, actor) -> None` — raises
    `CannotKickEqualOrHigherRankError`, `NotAuthorizedToKickError`, `CannotKickSelfError`
  - `is_gear_compatible(role, archetype) -> bool`
  - `role_base_bonus_for_target(role, target, char_level) -> int` (in
    `world.mechanics.services`)
  - **Rank management** — all require `actor.rank.can_manage_ranks=True`:
    `create_rank`, `rename_rank`, `set_rank_capabilities`, `reorder_ranks`,
    `delete_rank`, `assign_rank`, `transfer_top`. Lock-out invariant:
    `LastManagerRankError` if an op would leave zero active managers.
  - **Induction draft gate (#1231):**
    - `can_invite_to_covenant(covenant, *, character_sheet=None, account=None) -> bool`
      — canonical predicate: True iff the character's active rank in that covenant
      has `can_invite=True`. Accepts either a `character_sheet` or an `account` (resolves
      the active sheet from the account's puppeted character). Returns False when the
      character is not a member or holds no rank.
    - `assert_initiator_can_induct(*, session: RitualSession) -> None`
      — draft-time validator dispatched via `Ritual.draft_validator_path` from
      `draft_session`. Reads the COVENANT `RitualSessionReference` from the session,
      calls `can_invite_to_covenant`, and raises `NotAuthorizedToInviteError` when
      the initiator's rank lacks `can_invite`. Wired on the Covenant Induction ritual
      factory as `draft_validator_path = "world.covenants.services.assert_initiator_can_induct"`.
  - **Mentor's Vow services** (`world.covenants.mentorship`, #1165):
    - `effective_combat_level(sheet) -> int` — bond-adjusted combat level used by
      `compute_party_profile`; returns the raw primary level when no active
      non-graduated bond applies.
    - `bond_adjusted_level(sheet) -> int | None` — adjusted level or None.
    - `active_bond_adjusting(sheet) -> MentorBond | None` — the active non-graduated
      bond where sheet is the adjusted party; None if absent.
    - `establish_mentor_bond(*, covenant, mentor_sheet, sidekick_sheet) -> MentorBond`
    - `dissolve_mentor_bond(bond) -> None`
    - `is_bond_graduated(bond) -> bool` — True when adjusted party is now in band.
    - `assert_membership_level_allowed(*, covenant, character_sheet) -> None` — **Vow gate**:
      raises `VowGateError` if character is out-of-band and has no active bond in this
      covenant. Called by `add_member`; `create_covenant` is ungated.
    - `establish_mentor_bond_via_session(*, session) -> MentorBond` — service function
      wired to `MentorsVowRitualFactory` (consensual BILATERAL_SERVICE ritual).
- **Combat seams (#985, #1174, #1165):** `apply_equipped_armor_soak` splits worn armor into
  role-compatible vs incompatible buckets; final soak = `compat_physical +
  max(incompat_physical, resonant_pool)` where the resonant pool =
  `equipment_walk_total_unblended` (facet + `covenant_role_base_total` +
  covenant-level + mantle + motif-style). `_weapon_augmented_budget` adds
  `_combat_target_bonus(sheet, WEAPON_DAMAGE_TARGET_NAME)` to technique budget
  via `get_modifier_total` → `covenant_role_bonus`. In combat,
  `_combat_target_bonus(sheet)` passes `bond_adjusted_level(sheet)` as `level_override`
  so role bonuses reflect the bond-adjusted level (not raw). Encounter scaling:
  `compute_party_profile` calls `effective_combat_level` per ACTIVE participant before
  averaging — outlier distortion is absorbed in the bond math; graduated bonds dissolve
  at `begin_declaration_phase`.
- **Enums:** `MentorBondAdjusted` (`MENTOR`/`SIDEKICK` — which party is adjusted)
- **Exceptions:** `world.covenants.exceptions` —
  `CovenantRoleNeverHeldError`, `CannotKickEqualOrHigherRankError`,
  `NotAuthorizedToKickError`, `CannotKickSelfError`,
  `NotAuthorizedToManageRanksError`, `LastManagerRankError`,
  `CrossCovenantRankError`, `IncompleteRankReorderError`,
  `CannotTransferToDepartedMemberError` (rank management, #1027),
  `NotAuthorizedToInviteError` (induction draft gate, #1231),
  `MentorBondError` (bond creation/cap), `VowGateError` (membership level gate)
- **API Endpoints:**
  - `GET /api/covenants/gear-compatibilities/` — read-only authored content
  - `GET /api/covenants/character-roles/` — read-only; non-staff scoped to own
    currently-played sheets; exposes nested `rank` + `viewer_capabilities`
    (includes `can_invite` bool for the "Induct New Member" CTA)
  - `GET|POST /api/covenants/ranks/` — list / create ranks (#1027)
  - `GET|PATCH|DELETE /api/covenants/ranks/{pk}/` — retrieve / update / delete
  - `POST /api/covenants/ranks/reorder/` — bulk tier reorder
  - `POST /api/covenants/ranks/{pk}/assign-member/` — assign member to rank
  - `POST /api/covenants/ranks/{pk}/transfer-top/` — move top rank to member
- **Permission classes:** `CanKickFromCovenant` (rank.can_kick + tier precedence),
  `CanInviteToCovenant` (unattached seam — delegates to `can_invite_to_covenant` with
  `account=`; NOT currently wired to any ViewSet; induction-draft authorization is
  enforced by `assert_initiator_can_induct` via `Ritual.draft_validator_path`),
  `CanManageCovenantRanks` (rank.can_manage_ranks)
- **Frontend:** The covenant detail page's "Induct New Member" CTA is rendered only when
  `viewer_capabilities.can_invite` is true (read from the first member row of the
  `character-roles` endpoint). The induction `RitualSessionDraftDialog` sets the
  COVENANT reference so `assert_initiator_can_induct` can validate rank at draft time.
- **Integrates with:** magic (COVENANT_ROLE Thread anchor cap = `current_level × 10`;
  `MentorsVowRitualFactory`; `Ritual.draft_validator_path` for induction gate),
  mechanics (`covenant_role_bonus` in modifier walk; `level_override` via `bond_adjusted_level`),
  items (`gear_archetype` on `ItemTemplate`),
  combat (`apply_equipped_armor_soak` + `_weapon_augmented_budget`; `compute_party_profile`),
  vitals (`covenant_role_health` in `world.vitals.services` reads `CovenantRoleBonus` rows
  targeting the `max_health` ModifierTarget to compute the covenant-role health armor term
  in `derive_base_max_health`; recompute triggers fire on role engagement/membership change)
- **Source:** `src/world/covenants/`
- **Details:** [covenants.md](covenants.md)

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
- **Concrete Actions:** `LookAction`, `InventoryAction`, `SayAction`, `PoseAction`, `WhisperAction`, `GetAction`, `DropAction`, `GiveAction`, `TraverseExitAction`, `HomeAction`, `EquipAction`, `UnequipAction`, `PutInAction`, `TakeOutAction`, `UseItemAction`, `ActivatePermitAction`, `MoveToPositionAction`, `SetTheStageAction`
- **Pattern:** `action.run(actor, **kwargs)` → applies enhancements → **enforces prerequisites (hard gate)** → charges AP/fatigue → executes → returns `ActionResult`
- **Prerequisites:** `get_prerequisites()` is load-bearing; `run()` calls `check_availability()` against post-enhancement kwargs. Prerequisites read action-specific kwargs via `context["kwargs"]`. Shipped: `StaffOnlyPrerequisite`, `HoldsItemPrerequisite`, `ItemUsablePrerequisite`, `OnUseTargetPrerequisite`.
- **Integrates with:** service functions (direct calls), commands (telnet compatibility), flows (future: complex triggers)
- **Not Yet Built:** `SyntheticAction` model, event emission, `CharacterCapabilities` facade, on-demand availability endpoint
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

### Dev Seed Orchestrator
Production-callable seed layer for populating sane defaults on a fresh dev install.

- **Entry Point:** `world.seeds.database.seed_dev_database(*, verbose=False) -> SeedReport` — calls every registered cluster seeder in sequence; idempotent (create-if-missing semantics throughout, never overwrites).
- **Cluster registry:** `world.seeds.clusters.CLUSTER_SEEDERS` — `dict[str, Callable]` keyed by cluster name (`"magic"`, `"items"`, `"combat"`, `"checks"`). Add a new cluster by appending an entry here.
- **Surfaces:**
  - `arx seed dev` — CLI entry point (management command `src/core_management/management/commands/seed.py`; `--verbose` flag prints per-cluster row deltas).
  - Django admin **"Load sane defaults"** button (`src/web/admin/seed_views.py`) — superuser-only; runs `seed_dev_database()` and flashes a success/error message.
- **Interim design (Phase A):** `src/world/seeds/clusters.py` imports existing cluster masters (`seed_magic_dev`, `seed_items_dev`, etc.) from `integration_tests.game_content` at call time — a facade until roadmap task 3.2 relocates the helpers (#1220).
- **Key modules:** `database.py` (orchestrator), `clusters.py` (per-cluster dispatch), `checks.py` (`seed_check_resolution_tables()` — the natively-owned checks cluster), `types.py` (`SeedReport` dataclass).
- **Tests:** `src/world/seeds/tests/` — idempotency, non-overwrite, and playable-slice regression.
- **Source:** `src/world/seeds/`
- **Details:** [seed-and-integration-tests.md](../roadmap/seed-and-integration-tests.md) (Phase 3)

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

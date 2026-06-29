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
    `TechniqueCapabilityGrant`,
    `AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition`
    (abstract payload bases shared by `Technique*` and `TechniqueDraft*` rows),
    `TechniqueDraft` (one-per-CharacterSheet in-progress design workbench —
    `related_name="technique_draft"`; no JSON; all proper columns),
    `TechniqueDraftCapabilityGrant` / `TechniqueDraftDamageProfile` /
    `TechniqueDraftAppliedCondition` (draft payload children — inherit abstract bases)
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
    `Ritual` (four dispatch kinds: SERVICE → `service_function_path`; FLOW →
    `FlowDefinition`; CEREMONY → `PendingRitualEffect` + finisher command; SCENE_ACTION →
    `RitualCheckConfig`; `draft_validator_path` — new CharField, blank — is called
    inside `draft_session` before the session row is created, letting domain code gate
    who may initiate the ritual without coupling magic to any specific domain),
    `PendingRitualEffect` (in-progress CEREMONY record; unique per `(character, ritual)`;
    created by `PerformRitualAction`, consumed by finisher action `WeaveThreadAction`
    or `ImbueThreadAction`),
    `RitualComponentRequirement`, `ThreadWeavingUnlock`,
    `CharacterThreadWeavingUnlock`, `ThreadWeavingTeachingOffer`,
    `SoulTetherConfig` (singleton pk=1, rescue + sineating tuning knobs),
    `ThreadSurvivabilityTuning` (per-`VitalBonusTarget` tuning row for the
    universal thread survivability baseline — `vital_target` unique choice,
    `coefficient`, `cap`, `half_saturation`; one row each for DR and MAX_HEALTH;
    seeded via `seed_thread_survivability_tuning()`, staff-tunable in admin, #1175)
  - **Combat-side Spec A surface (in `world/combat`):** `CombatPull`,
    `CombatPullResolvedEffect`
  - **Combat AoE targeting (#1321, in `world/combat`):** `CombatRoundActionTarget` (join
    table; per-`CombatOpponent` row for AREA/FILTERED_GROUP technique actions)
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
  - **Ritual Liturgy (#1352):** `RitualLiturgy` (OneToOne → `Ritual`; `opening_call`
    TextField — the officiant's authored ceremonial words; public, non-spoiler).
    Seeded alongside the Ritual of the Durance via `RitualLiturgyFactory`.
  - **Audere Majora + legend-deed minting (#953):**
    `RenownAwardConfig` (abstract base — `models/renown_config.py`; shared by
    `AudereMajoraThreshold` and `DramaticMomentType`; carries `magnitude` /
    `risk` / `reach` / `archetypes`; provides `as_renown_award_kwargs()`),
    `AudereMajoraThreshold` (inherits `RenownAwardConfig`; adds `deed_title`
    public field),
    `AudereMajoraCrossing` (inherits `AbstractClassLevelAdvancement` from
    `world.progression.models.advancement`; adds `chosen_path`, `legend_entry`
    OneToOneField → `societies.LegendEntry`; null when `risk == NONE` or no
    primary persona). Deed minting fires via `_mint_crossing_deed` in `cross_threshold`.
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
    `spend_resonance_for_pull(...)` (low-level spend; called by the pull helpers),
    `preview_resonance_pull(...) -> PullPreviewResult` (read-only preview, unchanged),
    `resolve_pull_effects(...)`, `cross_thread_xp_lock(character_sheet, thread, level)`.
    Pull commit is routed through `world/combat/pull_helpers.py`:
    `commit_combat_pull` (combat cast + clash), `build_cast_pull_declaration`,
    `resolve_pull_from_kwargs`. Non-combat cast calls
    `request_technique_cast(cast_pull=…)` instead.
  - Thread lifecycle: `weave_thread(...)`, `update_thread_narrative(...)`,
    `imbue_ready_threads(character_sheet)`, `near_xp_lock_threads(...)`,
    `threads_blocked_by_cap(character_sheet)`
  - Thread XP-lock crossing: `cross_thread_xp_lock(character_sheet, thread, level)` —
    reachable via the legacy `POST /api/magic/threads/{id}/cross-xp-lock/` web action
    and via the shared Unlock Shop (`/api/progression/unlocks/purchase/` + telnet
    `progression unlock thread=<id> level=<n>`)
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
  - Effect palette (#1584):
    `ensure_effect_palette_content()` (`world/magic/effect_palette_content.py`) — idempotent
    entry point that seeds all 9 castable effects (Summon Spirit, Aegis Field, Mirror Ward,
    Phase Step, Phase Jump, Barricade, Ghostform, Earthmeld, Force Grip). Calls individual
    `ensure_*_content()` sub-builders. Effect handlers live in
    `world/magic/services/effect_handlers.py`: `absorb_pool`, `reflect_damage`, `blink_dodge`,
    `summon_ally`, `move_position`, `create_obstacle`; adapters: `summon_ally_on_condition`,
    `move_position_on_condition`, `create_obstacle_on_condition`, `init_absorb_buffer`.
    See magic.md §"Effect Palette" for the full handler/adapter table.
  - Technique authoring draft workbench (#1496):
    `get_or_start_draft(character) -> TechniqueDraft`,
    `discard_draft(character)`,
    `set_draft_fields(draft, **fields) -> TechniqueDraft`,
    `add_draft_restriction` / `remove_draft_restriction`,
    `add_draft_capability_grant` / `add_draft_damage_profile` / `add_draft_applied_condition`
    and `remove_*` counterparts (`services/technique_draft.py`).
    `draft_to_design(draft) -> TechniqueDesignInput` — completeness gate → design input.
    `validate_design_for_character(design, policy, character)` (`services/technique_builder.py`)
    — gift-ownership gate; single source of truth (telnet + web converge on it).
  - Standalone casting (#1306):
    `ensure_technique_cast_content()` (`seeds_cast.py`) — idempotent seed: shared
    "Technique Cast" `ActionTemplate` + fallback `CheckType` + graded "Magic: Technique
    Cast" `ConsequencePool`; called by the magic dev seed.
    `get_standalone_cast_template()` (`seeds_cast.py`) — retrieves the shared
    ActionTemplate; used as default by `create_technique`.
    `ensure_character_magic_check_type(character_sheet, *, stat, skill)` (`seeds_checks.py`)
    — synthesizes a per-character `CheckType` (name from `character_magic_check_type_name()`)
    for the character's stat + skill.
    `get_character_cast_check(character)` (`services/anima.py`) — resolves the
    per-character CheckType for cast resolution.
    `get_character_anima_ritual(character)` (`services/anima.py`) — retrieves the
    character's personal SCENE_ACTION `Ritual` (their anima ritual).
    `provision_player_anima_ritual(...)` (`services/anima.py`) — updated to point
    `RitualCheckConfig.check_type` at the per-character check so ritual and technique
    casts roll the same personal check.
  - Technique targeting (#1321):
    `derive_target_relationship(technique) -> ConditionTargetKind` (`world/magic/services/targeting.py`)
    — ENEMY if hostile; ALLY if any condition has `target_kind=ALLY`; else SELF.
    `technique_alters_behavior(technique) -> bool` — True if any applied condition's
    `category.alters_behavior` is True (compulsion, charm, fear).
    `cast_requires_consent(technique) -> bool` — True iff `technique_alters_behavior`; **behavior
    only**, not blanket benign (capability/stat buffs on other PCs are consent-free).
    `validate_cast_target(*, technique, initiator_persona, target_personas)` — raises
    `InvalidCastTarget` on cardinality or relationship violations.
    `resolve_targets(*, technique, initiator_persona, scene, supplied_personas) -> list[Persona]` —
    expands `Technique.target_type` to concrete personas (SELF→caster; SINGLE→one;
    AREA→all eligible in scene; FILTERED_GROUP→supplied ∩ eligible).
    `apply_technique_conditions(*, technique, success_level, eff_intensity, targets_by_kind,
    source_character) -> list[AppliedConditionResult]` (`world/magic/services/condition_application.py`)
    — shared by both combat and standalone cast paths; extracted from combat's `_apply_conditions`.
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
  `PendingAlterationStatus`, `AlterationTier`,
  `ConditionTargetKind` (SELF/ALLY/ENEMY — `world/magic/models/techniques.py`; derived
  relationship axis for targeting, distinct from `ActionTargetType` cardinality),
  `ActionTargetType` (SELF/SINGLE/AREA/FILTERED_GROUP — `actions/constants.py`; per-technique
  cardinality field `Technique.target_type`)
- **Exceptions (used by services + views):** `AnchorCapExceeded`,
  `InvalidImbueAmount`, `ResonanceInsufficient`, `WeavingUnlockMissing`,
  `XPInsufficient`, `RitualComponentError`,
  `NoMatchingWornFacetItemsError` (FACET thread pull with no worn matching item),
  `InvalidCastTarget` (`world/magic/services/targeting.py`; raised by `validate_cast_target`
  on cardinality/relationship violations),
  `NoActiveTechniqueDraft` (no draft to work with),
  `TechniqueDraftIncomplete` (required fields missing at `draft_to_design` time),
  `UnknownTechniqueVocab` / `UnknownGift` (unknown vocab/gift name in telnet parser),
  `GiftNotOwned` (character doesn't own the design's gift — `validate_design_for_character`) —
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
    resonance/anima cost and resolved effects (the only standalone pull endpoint;
    commit is via cast/clash dispatch, not a separate endpoint)
  - `POST /api/magic/rituals/perform/` — dispatches the `perform_ritual` action (`PerformRitualAction.run()`, shared with telnet `CmdRitual`, #1331)
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
- **Offer registry** (`commands/offer_registry.py`): generic pending-offer dispatch; `SurgeOfferHandler` and `CrossingOfferHandler` in `world/magic/offer_handlers.py`. Telnet: `accept <keyword>` / `decline <keyword>`.
- **Technique authoring action:** `AuthorTechniqueAction` (key `"author_technique"`, category
  `"magic"`) — single seam; telnet `CmdTechnique` and web `POST /api/magic/techniques/author/`
  both converge here. Telnet: `technique draft|show|set|restrict|grant|damage|condition|price|author|discard`
  (`cmd:perm(Builder)` — staff/GM only).
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
Character abilities with parent skills and specializations, plus weekly training
allocations that convert AP to development points.

- **Models:** `Skill`, `Specialization`, `CharacterSkillValue`,
  `CharacterSpecializationValue`, `TrainingAllocation`
- **Actions:** `ManageTrainingAction` (`registry_key="manage_training"`) — shared by
  web `TrainingAllocationViewSet` and telnet `training` command
- **Cron:** `run_weekly_skill_cron()` registered as `skills.weekly_training` in
  `world/game_clock/tasks.py`
- **Integrates with:** traits (skill checks), character_creation (skill selection),
  action_points (weekly AP spend), progression (`DevelopmentTransaction` rows)
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
- **Seeded check types:** `Composure` (willpower-weighted; resistance-specific — seeded via `create_resistance_check_types()` in `checks/factories.py`; used by `compute_resist_increment`)
- **Key Functions:** `perform_check(character, check_type, target_difficulty, extra_modifiers) -> CheckResult`, `get_rollmod(character) -> int`, `compute_resist_increment(defender_character, resist_effort_level) -> int` (resolves the Composure CheckType to compute a numeric difficulty bonus for active defense)
- **Key Types:** `CheckResult` (outcome, chart, roller_rank, target_rank, trait_points, aspect_bonus)
- **Pipeline:** trait points (weighted via CheckTypeTrait) + aspect bonus (path level) + modifiers → CheckRank → ResultChart → roll+rollmod → outcome
- **Integrates with:** traits (lookup tables), skills (check bonuses), conditions (check modifiers), goals (bonuses), scenes (active resistance via `compute_resist_increment`)
- **Source:** `src/world/checks/`
- **Details:** [checks.md](checks.md)

### Conditions
Persistent states that modify capabilities, checks, and resistances with stage progression and interactions.

- **Models:** `ConditionCategory` (`alters_behavior` bool — marks behavior-altering categories
  such as compulsion, charm, fear; used by `technique_alters_behavior` to gate consent;
  `grants_intangibility` bool — marks intangibility categories; `is_untargetable` queries this),
  `ConditionTemplate` (`upkeep_anima_per_round` int — anima drained per round for reactive
  conditions; `reactive_anima_cost` int — anima paid per reactive-defense fire; ADR-0060),
  `ConditionStage`, `ConditionInstance` (`absorb_remaining` int nullable — Aegis Field
  absorption buffer seeded by `init_absorb_buffer`), `ConditionCapabilityEffect`,
  `ConditionCheckModifier`, `ConditionResistanceModifier`, `ConditionDamageOverTime`,
  `ConditionDamageInteraction`, `ConditionConditionInteraction`
- **Lookup Tables:** `CapabilityType`, `CheckType`, `DamageType`
- **Handlers:** `obj.conditions` (`ConditionHandler` / `CharacterConditionHandler` in
  `world/conditions/handlers.py`, installed as `@cached_property` on `ObjectParent`).
  `CharacterConditionHandler.active` mirrors `get_active_conditions`. `.invalidate()`
  wired into all `world/conditions/services.py` mutation sites.
- **Key Functions:** `apply_condition()`, `remove_condition()`, `get_capability_status()`,
  `get_check_modifier()`, `get_resistance_modifier()`, `process_round_start()`,
  `process_round_end()`, `process_damage_interactions()`, `get_treatment_candidates()`,
  `perform_treatment()`
- **Charm/Calm content (#1590):** `ensure_charm_content()` seeds the `Charm` `ConditionCategory`
  (`alters_behavior=True`) + `Charmed`/`Calm` templates; `derive_allegiance()` reads active
  `alters_behavior` conditions to compute `Allegiance` (see combat + ADR-0058).
- **Integrates with:** combat (DoT, capability blocking, NPC allegiance reads via
  `ConditionCategory.alters_behavior`; `select_npc_actions` consults `derive_allegiance`),
  magic (power sources, resonance-environment boon/injury application, behavior-consent gating
  via `ConditionCategory.alters_behavior`), progression (interactions), scenes (telnet `treat` +
  web Treat panel surface converges on the `SceneActionRequest` consent seam via the
  custom-action-resolver registry)
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
Physical appearance options (height, build, hair/eye colors) and the alternate-self
shapeshift lifecycle.

- **Models:** `HeightBand`, `Build`, `FormTrait`, `FormTraitOption`, `CharacterForm`,
  `FormCombatProfile`, `FormCombatProfileEffect`, `AlternateSelf`, `ActiveAlternateSelf`
- **Enums:** `TraitType` (color/style), `FormType` (TRUE/ALTERNATE/DISGUISE), `DurationType`
- **Key Services:** `assume_alternate_self(sheet, alt)`, `revert_alternate_self(sheet)`,
  `switch_form(character, target_form)`, `revert_to_true_form(character)`,
  `get_presented_appearance(character)`
- **Key Exceptions:** `RevertBlockedError`, `AlternateSelfActiveError`, `FormOwnershipError`
- **Integrates with:** character_sheets (appearance, character anchor), scenes (Persona),
  mechanics (ModifierSource / CharacterModifier), magic (CharacterTechnique)
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
- **Reactive fall consumer (built — #1228):** `begin_plummet` / `advance_plummet` /
  `dispatch_catch` → `resolve_catch` (`plummet.py`) — STRICT danger round (#1466) + `Plummeting` +
  per-round descent/impact + capability-gated bystander catch
- **Deferred:** gated blueprint edges (requires absent `instantiate_situation()` service)
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
### Weather (Climate baseline + transient weather — #1522)
Mechanical regional climate + transient weather feeding the #1514 comfort substrate.

- **Models:** `Climate` (signed `temperature`/`moisture` baseline + `codex_subject` lore FK), `WeatherType` (name natural key; `is_automated`, `selection_weight`, `min`/`max_temperature` climate band), `WeatherTypeExposure` (`(type, stat_key) -> value`, mirrors `StyleAffinity`), `WeatherEmit` (season `in_*` + phase `at_*` gated flavour lines), `RegionWeatherState` (current weather per region Area), `FeastDay` (recurring `ic_month`/`ic_day` → special `WeatherType`)
- **Designation:** `Area.climate` FK (mirrors `Area.realm`); `RegionWeatherState.area` OneToOne
- **Climate services:** `get_effective_climate(area)` (most-specific-wins walk-up), `current_temperature_shift()` (per-month curve off the IC `game_clock`), `climate_exposure_base(climate, stat_key, *, temperature_shift=0)` (signed weights → floored COLD/HEAT/WET/DRY; WIND never climate-driven)
- **Weather services:** `get_effective_weather(area)` (resolver), `eligible_weather_types(area)` (climate-temp-band filter), `roll_region_weather(area, *, weather_type=None)` (weighted-random eligible type → state + decaying source-tagged `weather:<area_pk>` exposure modifiers), `apply_weather_exposure`/`clear_region_weather`, `select_weather_emit(area, *, season=None, phase=None)` (season/phase-gated, weighted), `current_conditions(room) -> ConditionsSummary` (IC time + phase + season + weather + emit)
- **Live loop + surface:** `world.weather.tasks.roll_and_echo_weather` cron (registered in `game_clock` at 2h real ≈ 6 IC h — rerolls each climate region + echoes one emit to online occupants as a `NarrativeCategory.WEATHER` message); telnet `time`/`weather` command (`commands/weather.py` `CmdTime`, with `weather squelch`/`unsquelch`); `GET /api/weather/conditions/?room_id=` (`WeatherViewSet` → `Conditions` schema) + the React `WeatherWidget` (`frontend/src/weather/`) in the `GameTopBar`
- **Squelch:** `narrative.UserCategoryMute` (account, category) + `narrative.services.set_category_mute`/`is_category_muted` — suppresses a category's live push (e.g. WEATHER) while keeping it readable; gated in `send_narrative_message`
- **Comfort integration:** climate folds into `world.locations.services.felt_exposure` before the 0-floor (a cooling fixture fights a desert's heat); weather writes the same cascade modifiers; `effective_value` stays climate-free
- **Constants:** `MONTH_TEMPERATURE_SHIFT` (12-value seasonal curve), `WEATHER_FADE_DAYS`, `WEATHER_SOURCE_PREFIX` — PLACEHOLDER magnitudes
- **Integrates with:** locations (exposure axes + comfort cascade), areas (`Area.climate`, `RegionWeatherState.area`), game_clock (IC season/phase/month), codex (lore)
- **Feast days:** `special_weather_for_today()` — on an `ic_month`/`ic_day` match the tick forces the feast's special `WeatherType` (Eclipse / Moon Madness) world-wide, overriding the climate-gated roll (the GM-lever automation)
- **Not yet wired:** re-seed-as-upsert for edited emits (loaddata duplicates keyless emit rows); wind-as-mechanic combat consumer (#1555, Tehom). Madness *mechanical* effects on characters are out of scope (Tehom)
- **Source:** `src/world/weather/` — see `world/weather/CLAUDE.md`
### Societies
Social structures, organizations, reputation, and legend tracking.

- **Models:** `Society`, `OrganizationType`, `Organization`, `OrganizationRank`, `OrganizationMembership`, `OrganizationMembershipOffer`, `SocietyReputation`, `OrganizationReputation`, `LegendEntry`, `LegendSpread`
- **Enums:** `ReputationTier`, `OrganizationMembershipOffer.Kind`, `OrganizationMembershipOffer.Status`
- **Key Services:** `ensure_default_rank_ladder`, `join_organization`, `leave_organization`, `invite_to_organization`, `apply_to_organization`, `accept_invitation`, `decline_invitation`, `accept_application`, `decline_application`, `promote_member`, `demote_member`, `expel_member`
- **Action Keys:** `org_invite`, `org_apply`, `org_join`, `org_leave`, `org_promote`, `org_demote`, `org_expel`
- **Telnet:** `org <subverb>` command; `accept org` / `decline org` offer responses
- **DRF:** `OrganizationViewSet`, `OrganizationMembershipViewSet`, `OrganizationRankViewSet`, `OrganizationMembershipOfferViewSet` at `/api/societies/organizations/`, `/api/societies/memberships/`, `/api/societies/ranks/`, and `/api/societies/offers/`
- **Principle Axes:** mercy, method, status, change, allegiance, power (-5 to +5)
- **Legend deed from crossing:** `LegendEntry.audere_majora_crossing` — reverse OneToOne to `AudereMajoraCrossing` (magic app); set when `cross_threshold` mints a deed via `fire_renown_award` + `_mint_crossing_deed`.
- **Integrates with:** realms (Society.realm FK), character_sheets (Persona for identity), magic (Audere Majora crossing deed via `AudereMajoraCrossing.legend_entry`), actions (shared `action.run()` / `dispatch_player_action()` seam)
- **Source:** `src/world/societies/`
- **Details:** [societies.md](societies.md)
### Goals
Goal domain allocation and journal-based XP progression.

- **Models:** `CharacterGoal`, `GoalJournal`, `GoalRevision`
- **Goal Domains:** Stored as `ModifierTarget(category='goal')` in mechanics system
- **Six Domains:** Standing, Wealth, Knowledge, Mastery, Bonds, Needs
- **Write services:** `set_character_goals` (revision-gated replace) + `log_goal_progress` in `services.py`; `GoalError` user-safe exception in `types.py`
- **Action-backed (#1350, ADR-0001):** `set_character_goals` / `log_goal_progress` Actions wrap the services; web `CharacterGoalViewSet`/`GoalJournalViewSet` + telnet `CmdGoal` converge on `action.run()`
- **Integrates with:** progression (XP rewards), mechanics (goal domains use ModifierTarget), actions (write paths Action-backed)
- **Source:** `src/world/goals/`
- **Details:** [goals.md](goals.md)
### Journals
Character journal entries (public/private), praises, retorts, freeform tags, weekly XP.

- **Models:** `JournalEntry` (FK CharacterSheet author; self-FK parent for responses), `JournalTag`, `WeeklyJournalXP`
- **Write services:** `create_journal_entry` / `create_journal_response` / `edit_journal_entry`; `JournalError` user-safe exception in `types.py`
- **Action-backed (#1350, ADR-0001):** `create_journal_entry` / `respond_to_journal` / `edit_journal_entry` Actions wrap the services; web `JournalEntryViewSet` + telnet `CmdJournal` (`journal write|respond|edit`) converge on `action.run()`
- **Integrates with:** progression (weekly XP awards), achievements (`journals.total_written`/`total_public` stats), threads (`JournalEntry.related_threads` M2M)
- **Source:** `src/world/journals/`
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
- **Read surface (#1575):** `GET /api/clues/held/?character_sheet=<id>` (`MyHeldCluesView`,
  `HeldClueSerializer`) — the held-clue *journal*, scoped to characters the requester plays
  (`for_account`; no cross-player leak). Web `CluesTab` on `CharacterSheetPage` (own character
  only). A telnet `sheet/clues` section + active-research "pursuit" tracking are follow-ups.
- **Integrates with:** codex (codex-target grant via `add_progress`), missions
  (`grant_rescue_mission`, mission target), projects (RESEARCH kind), captivity (RESCUE
  clues planted on capture / cleared on resolution), predicates (eligibility), checks
  (`perform_check`), actions (search), narrative (trigger notification), typeclasses
  (`Character.at_post_move` trigger hook)
- **Source:** `src/world/clues/`
- **Details:** [investigation_and_discovery.md](investigation_and_discovery.md)

### Secrets (#1334)
Hidden facts about a character — cover identities, crimes, private distinctions, secret
relationships. The privacy layer for the mystery loop: **bio/story stay public**, sensitive
info is *relocated* into Secrets that must be earned and shared. A Secret is the missing 4th
primitive alongside Distinction / Condition / Resonance. *Slices 1–3 (content model, discovery,
secret-tab display) + the #1269 distinction migration + the **act-anchor cross-link** (#1573 —
`legend_deed`/`mission_deed`/`scene`, one act = one secret) are built; action-anchored minting, the
blackmail loop, and the PersonaDiscovery subsumption are later slices.*

- **Models:** `Secret` (subject-anchored to a `CharacterSheet`, which **owns** it — single-owner,
  no shared/group rows; `level` 1–4 / `category` FK / `consequences` — each may be Unknown;
  `provenance` ∈ GM / action / player-flavor; `author_persona` for OOC attribution),
  `SecretCategory` (staff-editable lookup; null category = Unknown), `SecretKnowledge`
  (roster-scoped held record with partial-knowledge layers — fact / `knows_category` /
  `knows_consequences`, monotonic; tracks *others* learning a secret)
- **Invariant:** anchor-scales-with-level — only Level-1 player-flavor may be free-authored
  (it carries no mechanical effect, so its truth is moot); heavier secrets must be GM- or
  action-anchored, so player flavor can never masquerade as canon (`Secret.clean`)
- **Key functions (`world/secrets/services.py`):** `author_secret`, `author_player_flavor_secret`,
  `grant_secret_knowledge`, `secret_known_to`, `set_secret_act_anchor` /  `secrets_explaining`
  (the act-anchor cross-link both directions, #1573)
- **Discovery:** secrets are a `Clue` `target_kind` (`SECRET` + `target_secret` FK) — found
  through the same Search / `acquire_clue` loop; `grant_clue_target` teaches the fact
- **Codex boundary:** cut on *authorship* — Codex = canon lore (lore-authority, reviewed);
  Secret = self-serve hidden fact about a concrete entity
- **Source:** `src/world/secrets/`
- **Details:** [secrets.md](secrets.md)
### Tidings / Public-reaction feed (#1450)
The pull/browse vector of the public-reaction "contextual center" (#1446) — recent public events
scoped to what a viewer's persona would have heard. **Modelless and greenfield-light:** there is no
feed table; the service aggregates two awareness M2Ms other apps already own. *In-world criers/hubs
are a later slice of #1450.*

- **No models.** `world.tidings` is a service + API app (no migrations).
- **Key function (`world/tidings/services.py`):** `public_feed_for(persona, *, limit)` → list of
  `PublicFeedItem` dataclasses (`kind` / `headline` / `subject` / `occurred_at`), newest first.
  Merges **deeds** (`societies.LegendEntry` filtered by `societies_aware`) + **scandals**
  (`secrets.Secret` filtered by `societies_exposed`), scoped to the viewer's societies (union of
  `SocietyReputation` societies + `OrganizationMembership` orgs' societies).
- **Faces:** web `/api/tidings/feed/?viewer=<RosterEntry pk>` (`PublicFeedView`) → React `/tidings`
  page (`TidingsFeed`); telnet `tidings` (`CmdTidings`). Both converge on the one service. (Named
  *tidings*, not `gossip`/`news`: `gossip` is reserved for level-1-secret access, `news` for OOC
  game news; criers will be NPCs.)
- **Source:** `src/world/tidings/`
- **Echo (push) vector — staff/GM gemits with reach (#1450), in `world.narrative`:**
  `broadcast_gemit` broadcasts a **hand-authored, verbatim** message (colour codes and all) to a
  `reach` — `GemitReach` ∈ GAME_WIDE / SPECIFIED; SPECIFIED carries any mix of
  `Gemit.reach_societies` / `reach_organizations` (societies and orgs are not exclusive). Audience =
  sessions whose **active persona** is a member of any target society/org (a TEMPORARY mask holds
  none, so the disguised fall out — by design). History is reach-scoped so a specified gemit never
  leaks to outsiders (staff see all).
  Faces: telnet `gemit` (`CmdGemit`, staff `perm(Admin)`) + web `POST /api/narrative/gemits/`.
### Consent
OOC visibility groups and per-category social consent preferences for player-controlled
content sharing and social action targeting (#1141). Consent mutations are shared REGISTRY actions
so web and telnet converge on the same write path.

- **Models:** `ConsentGroup`, `ConsentGroupMember`, `VisibilityMixin` (abstract),
  `SocialConsentCategory` (NaturalKey on `key`), `SocialConsentPreference` (OneToOne on tenure),
  `SocialConsentCategoryRule` (preference + category + ConsentMode), `SocialConsentWhitelist`
  (owner_tenure / allowed_tenure / category)
- **Key Methods:** `VisibilityMixin.is_visible_to()`, `_tenure_blocks_actor()`,
  `_social_consent_exclusions()` (both in `actions/player_interface.py`)
- **Key Functions:** `seed_social_consent_categories()` (`world/seeds/consent.py`),
  `make_default_categories()` (`world/consent/factories.py`)
- **Key Services:** `set_social_consent_preference()`,
  `set_social_consent_category_rule()`, `remove_social_consent_category_rule()`,
  `add_social_consent_whitelist()`, `remove_social_consent_whitelist()`,
  `get_social_consent_summary()` (`world/consent/services.py`)
- **Action Keys:** `set_social_consent_preference`, `set_social_consent_category_rule`,
  `add_social_consent_whitelist`, `remove_social_consent_whitelist`
  (`actions/definitions/consent_preferences.py`)
- **Telnet:** `consent` namespace (`commands/consent_preferences.py`) — `consent on|off`,
  `consent category <key>=<mode>`, `consent whitelist add|remove|list`
- **API:** `/api/consent/` — categories (read-only), preferences, category-rules, whitelist;
  writes dispatch through the consent Actions via `dispatch_player_action()`
- **Pattern:** RosterTenure-based (player's tenure, not character); absent preference row = allow-all
- **Integrates with:** actions (`ActionTemplate.consent_category` FK), roster (RosterTenure),
  codex (visibility), seed loader (`arx seed dev`)
- **Source:** `src/world/consent/`
- **Details:** [consent.md](consent.md)
### Progression
XP, kudos, development points, and unlock system. Contains the most explicit prerequisite framework.

- **Models:** `ExperiencePointsData`, `XPTransaction`, `CharacterXP`, `DevelopmentPoints`, `DevelopmentTransaction`, `KudosPointsData`, `KudosTransaction`, `CharacterUnlock`, `XPCostChart`, `XPCostEntry`, `CharacterPathHistory`, `PathIntent` (player's declared next-path preference — one per character sheet; FK to `CharacterSheet` + `Path`), `KudosDifficultyWeight` (staff-tunable band→multiplier for good-sport kudos; one row per `DifficultyChoice`), `WeeklySocialEngagement` (per-account weekly pending-kudos accumulator; `pending_points`, `granted`, `game_week` FK; `distinct_initiators` is a derived property counting child rows), `WeeklyEngagementInitiator` (child row recording each unique initiator toward a ledger; `UniqueConstraint(ledger, initiator_account)`),
  **Class-Level Advancement (#1352):** `AbstractClassLevelAdvancement` (abstract base shared by `ClassLevelAdvancement` and `AudereMajoraCrossing`; carries `scene`, `declaration_interaction`, `level_before`, `level_after`, `created_at`), `ClassLevelAdvancement` (within-tier Durance receipt — `character_sheet`, `character_class`, `officiant`, `ritual`)
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
  - `GET /api/progression/unlocks/` — purchasable unlocks for the played character; paginated, filterable by `unlock_type`
  - `POST /api/progression/unlocks/purchase/` — buy a `class_level` or `thread_xp_lock` unlock with XP; dispatches `PurchaseUnlockAction`
- **Actions:**
  - `PurchaseUnlockAction` (`registry_key="purchase_unlock"`) — shared unlock purchase path for web and telnet
  - `ClaimKudosAction` (`registry_key="claim_kudos"`) — kudos→XP conversion; shared by web and telnet (#1348)
  - `CastVoteAction` / `RemoveVoteAction` (`"cast_vote"` / `"remove_vote"`) — weekly vote budget management (#1348)
  - `ClaimRandomSceneAction` / `RerollRandomSceneAction` (`"claim_random_scene"` / `"reroll_random_scene"`) — weekly random-scene bounty claims/rerolls (#1348)
  - `SetPathIntentAction` / `ClearPathIntentAction` (`"set_path_intent"` / `"clear_path_intent"`) — declare/clear preferred next path for Audere Majora (#1348)
- **New service module (#1348):** `world.progression.services.path_intent` — `set_path_intent(sheet, path)` / `clear_path_intent(sheet)`; single seam for `PathIntentViewSet` + `CmdPathIntent`
- **Telnet Commands:** `progression unlocks`, `progression unlock class=<id>`, `progression unlock thread=<id> level=<n>` (in `commands/progression.py`);
  `kudos`, `vote`, `randomscene` (alias `rscene`), `pathintent` (in `commands/progression_rewards.py`, #1348)
- **Good-sport kudos accrual:**
  - `accrue(account, initiator_account, points) -> WeeklySocialEngagement` (`services/engagement.py`) — adds points to the weekly pending ledger; tracks `WeeklyEngagementInitiator` rows for distinct-initiator anti-farm; resets stale ledgers lazily on the game-week boundary.
  - `grant_social_engagement_kudos() -> int` (`services/engagement.py`) — called at weekly rollover; iterates ungranted ledgers, skips those below `MIN_ENGAGEMENT_BAR` distinct initiators (currently 2), awards kudos via `award_kudos`, marks `granted=True`.
  - `KudosDifficultyWeight.weight_for(band) -> Decimal` — returns configured multiplier for the difficulty band; falls back to `Decimal("1.0")` when no row exists.
- **Class-level advancement spine (#1352 — `services/advancement.py`):**
  - `primary_class_level(character) -> CharacterClassLevel | None` — primary (or highest-level) class level row; None when absent.
  - `apply_class_level_advance(sheet, *, level_after) -> None` — shared level-write + cache invalidation; no receipt, no scene side-effects. Called by both `cross_threshold` and the Durance service.
  - `assert_can_officiate(*, officiant_sheet, inductee_sheet, target_level) -> None` — raises `OfficiantIneligibleError` when level gate or Path-lineage gate fails.
  - `advance_class_level_via_session(*, session) -> list[ClassLevelAdvancement]` — `fire_session` dispatch target for the Ritual of the Durance; advances each ACCEPTED inductee, posts their testament pose, writes receipts.
- **Advancement exceptions (`exceptions.py`):** `ClassLevelAdvancementError` (base), `TierBoundaryRequiresCrossing`, `AdvancementRequirementsNotMet`, `OfficiantIneligibleError` — all carry `user_message`.
- **Pattern:** `AbstractClassLevelRequirement` base class with polymorphic `is_met_by_character()` — extend this for new prerequisite types (society, relationship, etc.)
- **Integrates with:** traits (unlock requirements), classes (path unlocks), goals (XP rewards), magic (Audere Majora offer pre-selects from `PathIntent.intended_path_id` via `get_intended_path_id` on `PendingAudereMajoraOfferSerializer`; `advance_class_level_via_session` dispatched from `fire_session` on the Ritual of the Durance; `AudereMajoraCrossing` inherits `AbstractClassLevelAdvancement`), scenes (good-sport kudos accrued at consent; weekly grant via game-clock rollover)
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
- **Seeded CG-world content (#1333):** `seed_character_creation_dev()` (`src/world/seeds/character_creation.py`) — the `"character_creation"` cluster; seeds Realm/StartingArea/Beginnings/Species/Gender/TarotCard/HeightBand/Build/12 stat Traits/Rosters/Path so `finalize_character` runs on a fresh DB. Part of `seed_dev_database()` (the admin "Load sane defaults" Big Button); surfaced in the superuser-only **Game Setup** hub.
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
Roleplay session recording with participant tracking, interaction logging, persona-based identity, social
action consent flow, and a three-mode non-combat round framework.

- **Models:** `Scene`, `SceneParticipation`, `Persona`, `SceneActionRequest`, `SceneActionTarget`,
  `SceneCastPullDeclaration`,
  **Round framework (#1351):** `SceneRound` (room-anchored non-combat round; fields: `mode`
  (`SceneRoundMode`), `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`;
  `mode`/`start_reason` orthogonal — danger rounds are STRICT, ensured via
  `ensure_round_for_acute_condition`, #1466), `SceneRoundDefaultsConfig` (singleton pk=1 — staff-tunable
  defaults: `default_mode`, `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`,
  `anti_spam_seconds`, `abandonment_grace_rounds` (#1479: N action-driven beats an abandoned downed
  victim waits before fate resolves; default 2); accessed via `get_scene_round_defaults_config()`),
  `SceneActionDeclaration`
  (per-round ledger; `is_immediate=True` for OPEN/POSE_ORDER actions, `is_immediate=False` for STRICT
  deferred declarations; carries `target_persona` FK; multiple rows per participant per round up to
  `max_actions_per_round`), `SceneRoundParticipant`
- **Abstract base:** `DefenderConsentFields` (`action_models.py`) — shared by `SceneActionRequest` and `SceneActionTarget`; carries `difficulty_choice` (DifficultyChoice plausibility band, authored by the defender), `resolved_difficulty`, `resist_effort_level` (EffortLevel, optional active resistance).
- **Effort/difficulty split:** The initiator declares `effort_level` (EffortLevel) at dispatch; the defender authors per-target `difficulty_choice` at consent. The resolver adds `EFFORT_CHECK_MODIFIER[effort_level]` to the check pool and charges the initiator social fatigue. The defender's plausibility base + optional `compute_resist_increment()` produce the numeric `difficulty_override`; active resistance charges the defender `RESIST_FATIGUE_BASE` social fatigue.
- **Social action consent:** `SceneActionRequest` owns the full lifecycle (dispatch → consent → resolution) for the primary target; `SceneActionTarget` rows carry additional targets, each with independent consent and result. Resolvers fire once per accepted target (primary via `respond_to_action_request`, additional via `respond_to_action_target`).
- **Key Functions:**
  - `create_action_request(scene, initiator_persona, target_persona, action_key, ..., effort_level)` — dispatches a request; NPC additional targets auto-accept immediately.
  - `respond_to_action_request(action_request, decision, difficulty=None, resist_effort="")` — primary-target consent + resolution; defender supplies plausibility band + optional active resistance.
  - `respond_to_action_target(action_target, decision, difficulty=None, resist_effort="")` — per-additional-target consent + resolution (never touches siblings).
  - `broadcast_scene_message(scene, action)` — pushes scene state to participants via WebSocket.
  - `ensure_scene_for_location(room, privacy_mode=None)` (`place_services.py`) — find-or-create the
    active scene for a room. Returns the existing active scene unchanged (caller's `privacy_mode`
    ignored on reuse); when creating, derives `privacy_mode` from the room when omitted —
    PUBLIC if publicly listed, else PRIVATE.
  - `ensure_scene_participation(scene, character)` (`interaction_services.py`) — create a
    `SceneParticipation` for the character's account in the scene if one does not already exist.
    Public API consumed by combat to record fighters as first-class scene participants.
  - **Round framework (`round_services.py`, #1351):**
    - `get_scene_round_defaults_config() -> SceneRoundDefaultsConfig` (`models.py`) — get-or-create the singleton config.
    - `active_round_for_room(room) -> SceneRound | None` — public service; returns the active
      (non-completed) round for a room, or None. One-active-round-per-room constraint makes
      `.first()` unambiguous. Consumed by `SceneDetailSerializer.get_active_round` (#1467).
    - `actions_this_round(scene_round, participant) -> int` — declaration count for a participant.
    - `distinct_actors_this_round(scene_round) -> int` — distinct participants with declarations this round.
    - `record_pose_order_action(scene_round, participant, target_persona=None)` — write an `is_immediate=True` ledger row.
    - `advance_pose_order_round_if_quorum(scene_round) -> SceneRound` — advance `round_number` when quorum met (round stays DECLARING).
    - `scene_round_is_complete(scene_round) -> bool` — quorum-gated (#1480): True when ≥ `ceil(advance_quorum_pct / 100 × present_active_count)` present ACTIVE `can_act` participants have a deferred (`is_immediate=False`) declaration; at 100 reduces to unanimity. Absent and present-`not can_act` participants are implicit passes.
    - `resolve_scene_round(scene_round)` — social-only resolver: runs CHALLENGE declarations in
      initiative order, fires end tick, advances round. **AFK own-peril skip (#1480):** an undeclared
      present `can_act` participant is excluded from the END-tick target set so their own acute
      conditions don't advance (ADR-0004). **Downed-victim narrowing (#1479):** a DOWNED victim's
      acute peril (Bleeding Out) advances on the END tick only when the peril's `source_character`
      declared this round (`hostile_drove_round`); otherwise the peril HOLDS and
      `ConditionInstance.abandoned_since_round` is stamped (`mark_abandoned`) when a potential
      rescuer is present. After the END tick, `_resolve_abandonment_grace` resolves any victim whose
      `round_number − abandoned_since_round ≥ SceneRoundDefaultsConfig.abandonment_grace_rounds` via
      `world.vitals.services.resolve_abandonment`; a resolved peril lets the danger round auto-end.
    - `resolve_solo_abandoned_victims(room, *, departing=None)` (#1479 Task 8) — when a departure
      removes the last potential rescuer, any still-downed victim's fate resolves immediately via
      `resolve_abandonment`; wired into `typeclasses.rooms.Room.at_object_leave`. `departing` is
      excluded from the rescuer check so the mover is not counted as a remaining rescuer.
    - `maybe_resolve_scene_round(scene_round)` — resolves iff `scene_round_is_complete` is True.
  - **Scene administration (`scene_admin_services.py`, #1445):**
    - `actor_can_administer_scene(actor, scene) -> bool` — permission gate; True for GM/Staff characters (`is_story_runner`), staff accounts, or scene co-owners (`is_owner=True`).
    - `resolve_actor_account(actor) -> AccountDB | None` — controlling account for a PC actor; None for GM/Staff/NPC.
    - `add_present_as_co_owners(scene, room)` — mark every present character with a controlling account as a co-owner at scene creation (anti-grab: latecomers are non-owners).
    - `finish_scene_full(scene, by_account=None)` — full scene-finish orchestration: `finish_scene()` → `on_scene_finished()` → deferred fatigue resets → `broadcast_scene_message(END)`. Idempotent.
    - `set_scene_round_mode(scene_round, *, mode, advance_quorum_pct, max_actions_per_round, per_target_repeat_lock) -> SceneRound` (`round_services.py`) — apply mode/knob changes in-place; raises `RoundModeError` on STRICT-exit with pending declarations (#1466 removed the DANGER-immutable block — danger rounds are ordinary STRICT rounds). #1480: after applying, re-checks completion on a DECLARING STRICT round so a quorum change takes effect immediately.
    - `ensure_round_for_acute_condition(character_sheet) -> SceneRound | None` (`round_services.py`) — ensure an active scene round for the room (enrolling everyone present); creates a STRICT `SceneRound(start_reason=DANGER)` when none active, else the peril rides the existing round (#1466; renamed from `auto_start_or_extend_danger_round`).
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
- **Privacy ↔ room-publicness invariant (#1287):** a Scene in a publicly-listed room must be PUBLIC;
  `Scene.save()`/`clean()` enforce this via `_validate_privacy_against_room()`;
  `ensure_scene_for_location` derives the default. Shared helper: `room_is_publicly_listed(room)`
  in `evennia_extensions/models.py`. See [scenes.md](scenes.md) §"Scene Privacy ↔ Room-Publicness Invariant".
- **Scene admin actions (#1445):**
  - `StartSceneAction` (key `"start_scene"`, `actions/definitions/scenes.py`) — creates scene + grants co-ownership to all present PCs; records actor as non-owner participant if scene already exists.
  - `FinishSceneAction` (key `"finish_scene"`, `actions/definitions/scenes.py`) — finishes active scene; gated by `actor_can_administer_scene`.
  - `SetRoundModeAction` (key `"set_round_mode"`, `actions/definitions/rounds.py`) — changes mode/knobs of active round; gated by `actor_can_administer_scene`; `costs_turn=False`.
- **`CmdScene`** (`commands/scene.py`) — telnet face for `scene start [name]` / `scene finish` / `scene round [open|pose_order|strict] [quorum=<pct>] [cap=<n>] [lock=on/off]` / `scene status`. Thin over the three Actions above; no business logic.
- **`is_story_runner`** character property (`typeclasses/characters.py`) — `False` on base `Character`; `True` on `GMCharacter` and `StaffCharacter` (`typeclasses/gm_characters.py`); used by `actor_can_administer_scene` as the GM/Staff fast-path.
- **API endpoint:** `POST /api/scenes/{id}/set-round-mode/` — coarse-gated `IsSceneGMOrOwnerOrStaff`; dispatches `SetRoundModeAction`; returns updated scene detail.
- **`active_round` read field on `SceneDetailSerializer`** (#1467): nullable nested field serialized by
  `SceneRoundSerializer` (read-only). Exposes `mode`, `advance_quorum_pct`, `max_actions_per_round`,
  `per_target_repeat_lock`, `status`, `round_number`, `is_danger`. `null` when no location or no active round.
- **`RoundSettingsDialog`** (React, `frontend/src/scenes/components/RoundSettingsDialog.tsx`, #1467):
  GM/owner/staff-gated (`viewer_can_gm && is_active`) dialog for setting round mode and knobs;
  consumes `active_round` from the scene detail and dispatches `useSetRoundMode` →
  `POST /api/scenes/{id}/set-round-mode/`. Wired into `SceneHeader.tsx`.
- **Integrates with:** roster (characters), stories (EpisodeScene join), instances (preservation check),
  flows (auto-logging via message_location), combat (encounter read gate + participation convergence via
  `Scene.objects.viewable_by` / `ensure_scene_participation`),
  actions (`SCENE_ADAPTIVE` backend dispatch + `CastTechniqueAction`; resolver registry via
  `get_resolver(action_key)`), consent (`SocialConsentCategory` enforcement)
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
- **Categories:** STORY, ATMOSPHERE, VISIONS, HAPPENSTANCE, SYSTEM, COVENANT, RENOWN,
  WEATHER (weather tick emits),
  ABILITY (access-change notifications — gained/lost techniques or capabilities; also used
  by `announce_achievement` for first-ever Discovery ceremonies on discoverable content)
- **Key Services:**
  - `send_narrative_message(recipients, body, category, ...)` — atomic create + fan-out + real-time push to puppeted recipients via `character.msg()` with `|R[NARRATIVE]|n` color tag; offline recipients stay queued
  - `deliver_queued_messages(sheet)` — drains queued deliveries at login (called from `at_post_puppet` via stories login service)
- **Pattern:** One message fans out to many recipients via NarrativeMessageDelivery rows (e.g., GM sends covenant message to 5 of 8 members — one message, five delivery rows). Messages are immutable; delivery rows track per-recipient state.
- **API Endpoints:** `GET /api/narrative/my-messages/` (paginated, filterable by category / related_story / acknowledged), `POST /api/narrative/deliveries/{id}/acknowledge/`
- **Integrates with:** stories (beat completions + episode resolutions emit messages via `stories.services.narrative`), character_sheets (recipient), accounts (sender)
- **Source:** `src/world/narrative/`

### Achievements
Cross-cutting meta-engagement layer: hidden milestones characters earn across every game system,
plus the shared access-change announcement surface that fires discovery ceremonies when a character
gains a discoverable content item for the first time.

- **Models:** `StatDefinition` (normalized stat key — dot-separated, e.g.
  `"relationships.total_established"`), `StatTracker` (per-character integer counter),
  `Achievement` (staff-authored; `hidden` default True, `notification_level`, chained via
  `prerequisite` self-FK, `is_active`), `AchievementRequirement` (stat threshold comparison per
  achievement), `Discovery` (OneToOne → `Achievement`; records first-ever earner timestamp),
  `CharacterAchievement` (earned record; optional `discovery` FK when the earner was a co-discoverer),
  `RewardDefinition` (TITLE / BONUS / COSMETIC / PRESTIGE reward catalog),
  `AchievementReward` (per-achievement reward with optional `reward_value` amount),
  `CharacterTitle` (earned display-only title record; FK → TITLE `RewardDefinition`),
  `ConditionStatRule` (bridge: condition event type → stat increment),
  **`DiscoverableContent`** (abstract base — adds nullable `discovery_achievement` FK to any
  content model whose instances can be discovered for the first time; inherited by `Technique`
  and `CovenantRole`; null = not discoverable; see ADR-0061)
- **Enums:** `NotificationLevel` (PERSONAL / ROOM / GAMEWIDE), `ComparisonType` (GTE / EQ / LTE),
  `RewardType` (TITLE / BONUS / COSMETIC / PRESTIGE), `ConditionEventType` (GAINED),
  `AccessChangeSource` (ASSUMED_ALTERNATE_SELF / REVERTED_ALTERNATE_SELF /
  COVENANT_ROLE_ENGAGED / COVENANT_ROLE_DISENGAGED / CHARACTER_CREATION)
- **Handlers:** `character_sheet.stats` (`StatHandler`) — `get(stat_def) -> int`,
  `increment(stat_def, n) -> int` (atomic F() expression; checks requirement thresholds after increment)
- **Key Services (`world/achievements/services.py`):** `grant_achievement(achievement,
  sheets) -> list[CharacterAchievement]`, `apply_achievement_rewards(sheet, achievement)`,
  `get_stat(sheet, stat_def) -> int`, `increment_stat(sheet, stat_def, n) -> int`
- **Access-change + discovery surface (`world/achievements/discovery.py` — ADR-0061):**
  - `announce_access_change(character_sheet, *, gained, lost, source)` — sends an ABILITY
    `NarrativeMessage` to the character listing what techniques/capabilities changed, then for
    each gained item with a non-null `discovery_achievement` FK fires `grant_achievement` and
    `announce_achievement`. Source-agnostic: callers never branch on covenant vs. form vs. CG.
  - `announce_achievement(earners, *, is_first, first_body, personal_body, category)` —
    gamewide to all active player sheets when `is_first` (first-ever Discovery); otherwise
    personal to the earner list.
- **Wired callers of `announce_access_change`:** `world/forms/services.py` (assume/revert
  alternate self), `world/covenants/services.py` (engage/disengage covenant role, via
  `_announce_capability_diff`), `world/character_creation/services.py` (CG cantrip grant)
- **API Endpoints:**
  - `GET /api/achievements/character-titles/?character_sheet=<id>` — earned titles, newest first
- **Integrates with:** magic (`Technique` inherits `DiscoverableContent`; `discovery_achievement`
  FK), covenants (`CovenantRole` inherits `DiscoverableContent`), narrative
  (`send_narrative_message` with ABILITY category), roster (`active_player_character_sheets()`
  for gamewide first-ever recipient selection), mechanics (BONUS reward → `CharacterModifier`),
  societies (PRESTIGE reward → `award_deed_prestige`), conditions (`ConditionStatRule` bridge),
  stories (reactivity hook `on_achievement_earned`)
- **Source:** `src/world/achievements/`
- **Glossary:** `src/world/achievements/AGENT_GLOSSARY.md`

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
- **Disposition (#1591):** two-tier model. Durable `NPCStanding.affection` (per
  `(pc_persona, npc_persona)`) is atomically accumulated by
  `adjust_npc_affection(pc_persona, npc_persona, delta=...)` via `F()`. Social action
  graded outcomes route through `apply_social_disposition_delta(actor, target_persona_id,
  result)`. Persona-less NPCs (mooks) use the session-scoped
  `world.npc_services.ephemeral_disposition` store; the promotion seam to durable rows is
  future work (ADR-0058).
- **Allegiance (#1590):** `derive_allegiance(opponent, encounter)` derives `ENEMY` /
  `ALLY_OF_CASTER` / `NEUTRAL` from active `alters_behavior` conditions (charm/calm);
  consumed by combat's `select_npc_actions` per opponent.
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
outcome rolls. Kinds: BUILDING_CONSTRUCTION, ROOM_FEATURE_PROGRESSION, RESEARCH, and
RANSOM (#1500).

- **Models:** `Project` (kind discriminator + status + completion_mode), `Contribution`
  (per-actor per-project contribution log; privacy-aware; `contribution_method` FK on
  CHECK rows), `ContributionMethod` (#1574 — admin-authorable, per-`ProjectKind`
  check-based method: `check_type` + `ap_cost` + `progress_on_success`), per-kind details
  models (`BuildingConstructionDetails`, `RoomFeatureProgressionDetails`)
- **Constants:** `ProjectKind`, `ProjectStatus`, `CompletionMode`, `ContributionKind`,
  `ContributionPrivacy`
- **Contribution surface (#1574):** `donate_to_project` (money → progress at 1/100c),
  `contribute_check_to_project` (spends a method's AP, rolls its check, advances on
  success), `set_contribution_story`. Telnet `CmdProject` (`+project`, `project/donate`,
  `project/check`, `project/story`); web via `DonateToProjectAction` /
  `CheckContributeAction` / `StoryContributeAction`.
- **Instant-completion kinds (#1500):** `register_instant_completion_kind` marks a kind
  (RANSOM) that resolves the moment its threshold is funded — `maybe_complete_immediately`
  fires the kind handler post-contribution instead of waiting for the cron resolver. (The
  generic RESOLVING→COMPLETED cron driver is not built yet; `scan_active_projects` only
  marks projects RESOLVING.)
- **Stat definitions:** Project achievement stats are created lazily on first
  contribution (same pattern as combat achievement counters)
- **Cross-app dependencies:** `world.scenes.Persona`, `societies.Organization`
- **Source:** `src/world/projects/`

### Captivity (held characters + crowdfundable ransom)
A character can be held captive (#931): captured into an instanced cell by an NPC
captor org, freed by escape, rescue, ransom, or release. #1500 reframes ransom as a
**crowdfundable RANSOM Project** standing in the cell.

- **Models:** `Captivity` (captive + cell + captor_organization + status; `ransom_project`
  FK → the crowdfundable RANSOM Project #1500 — the single ransom route since the
  org-treasury Contract path was retired), `CaptivityConfig` (singleton authored
  cell/clue/mission defaults)
- **Constants:** `CaptivityStatus` (HELD / ESCAPED / RESCUED / RANSOMED / RELEASED)
- **Ransom-as-project (#1500):** `demand_ransom_project` (GM surface creates the RANSOM
  project in the cell), `resolve_ransom_project` (kind handler — frees the captive on full
  funding via `resolve_captivity(RANSOMED)`; idempotent). Anyone pays via the generic
  `project/donate`; the cell-room appearance shows a red OOC captive-status banner. GM
  demand surfaces: telnet `CmdDemandRansom` (staff) + web `DemandRansomView`
  (`POST /api/gm/demand-ransom/`, `IsGMOrStaff`), both converging on `demand_ransom_project`.
- **Other services (`world.captivity.services`):** `capture_character` / `capture_party`,
  `resolve_captivity`, `rescue_captive`, `escape_captivity`
- **Integrates with:** projects (RANSOM kind + instant-completion), missions
  (escape/rescue loops), clues (rescue-clue planting), instances (the cell),
  typeclasses (`return_appearance` captive banner)
- **Source:** `src/world/captivity/`

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
    instance per room (unique constraint). `dissolved_at` (nullable
    `DateTimeField`) marks soft-deleted instances; `.active()` queryset
    excludes them.
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
- **Dissolution is a soft-delete** (#1497): `perform_dissolution` sets
  `RoomFeatureInstance.dissolved_at` (nullable `DateTimeField`) rather than deleting
  the row. `RoomFeatureInstance.active()` excludes dissolved instances. SANCTUM-anchored
  threads are soft-retired (`Thread.retired_at`) on dissolution; the
  `one_personal_per_character_sheet` DB `UniqueConstraint` on `SanctumDetails` was
  removed — one-personal-per-founder is enforced in the service layer (excluding
  dissolved). Re-sanctifying the same room is a deferred follow-up.
- **TELNET+WEB** (#1497): 7 REGISTRY Actions in `actions/definitions/sanctum.py`
  (keys `sanctum_install` / `sanctum_homecoming` / `sanctum_purging` / `sanctum_weave`
  / `sanctum_dissolve` / `sanctum_absorb` / `sanctum_sever`). `CmdSanctum`
  (`commands/sanctum.py`) is the namespaced telnet surface (`sanctum <subverb>`);
  the web `SanctumViewSet` dispatches the same Actions via `Action().run()`.
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
  - `CovenantRole` sub-role fields — `parent_role` (self-FK), `resonance` (FK →
    `magic.Resonance`), `unlock_thread_level` (PositiveInt, 0 for primary / >0 for sub-roles),
    `discovery_achievement` (FK → `achievements.Achievement`, nullable, sub-roles only),
    `codex_entry` (FK → `codex.CodexEntry`, nullable, sub-roles only).
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
    `currently_held_role_in(covenant)`, `currently_engaged_roles()` (returns resolved
    sub-roles via `resolve_effective_role`), `anchor_role_in(covenant)` (stored parent
    role, ignoring sub-role resolution), `invalidate()`
- **Key Services:**
  - `resolve_effective_role(*, character, role) -> CovenantRole` (`world.covenants.services`) —
    derive-on-read sub-role resolution; called by `currently_engaged_roles()` per row.
  - `fire_subrole_discoveries(*, thread, starting_level, new_level)` (`world.covenants.discovery`)
    — discovery beat hooked into `spend_resonance_for_imbuing`; grants achievement, unlocks
    codex entry, sends narrative message on threshold crossing.
  - `active_player_character_sheets() -> list[CharacterSheet]` (`world.roster.selectors`) —
    returns all active player character sheets (current RosterTenure with `end_date=None`);
    used by `fire_subrole_discoveries` for gamewide first-ever recipient selection.
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
- **Action Keys:** `engage_covenant_membership`, `disengage_covenant_membership`,
  `leave_covenant`, `kick_covenant_member`, `assign_covenant_rank`,
  `transfer_covenant_top_rank`, `stand_down_battle_covenant`
  (`actions/definitions/covenants.py`, #1346)
- **Telnet:** `covenant <subverb>` command (`commands/covenant.py`, #1346) for
  engage/disengage/leave/kick/rank/transfer/standdown; covenant induction via
  `ritual draft ... covenant=<name>` / `ritual join <id> role=<role>` / `ritual fire <id>`,
  banner-call rise via `ritual draft ... covenant=<name>` / `ritual join <id>` /
  `ritual fire <id>` — both adapter-dispatched from `CmdRitual` via
  `commands/ritual_adapters.py`.
- **Selectors (`world.covenants.selectors`):**
  `resolve_actor_membership(*, covenant, character_sheets, capability=None)`,
  `get_active_memberships(*, character_sheet)` — shared by viewsets and the covenant Actions.
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
  `RitualSessionResponseDialog` renders `candidate_only` participant fields (role picker),
  resolves the COVENANT reference from `session.session_references` to filter the role
  picker, and converts `emits_reference: "COVENANT_ROLE"` into a typed reference on
  accept — completing the draft → accept-with-role → fire → `CharacterCovenantRole`
  round-trip. Covered by `RitualInductionRoundTripTests` (backend) + `RitualSessionPages`
  component tests (frontend).
- **Integrates with:** magic (COVENANT_ROLE Thread anchor cap = `current_level × 10`;
  `MentorsVowRitualFactory`; `Ritual.draft_validator_path` for induction gate;
  `spend_resonance_for_imbuing` hooks `fire_subrole_discoveries` after each imbue),
  mechanics (`covenant_role_bonus` in modifier walk; `level_override` via `bond_adjusted_level`),
  items (`gear_archetype` on `ItemTemplate`),
  combat (`apply_equipped_armor_soak` + `_weapon_augmented_budget`; `compute_party_profile`),
  vitals (`covenant_role_health` in `world.vitals.services` reads `CovenantRoleBonus` rows
  targeting the `max_health` ModifierTarget to compute the covenant-role health armor term
  in `derive_base_max_health`; recompute triggers fire on role engagement/membership change),
  achievements (`discovery_achievement` FK; `grant_achievement` on threshold crossing),
  codex (`codex_entry` FK; `CharacterCodexKnowledge(KNOWN)` on crossing),
  narrative (`send_narrative_message` for discovery announcements)
- **Source:** `src/world/covenants/`
- **Details:** [covenants.md](covenants.md)

### Combat
Turn-based combat engine: encounter lifecycle, NPC threat patterns, damage resolution,
reactive maneuvers (COVER, INTERPOSE, DEFEND stance), and clash-of-wills.

- **Models (key):** `CombatEncounter`, `CombatParticipant`, `CombatOpponent`,
  `CombatRoundAction` (`maneuver` field — FLEE / COVER / YIELD / INTERPOSE; plus the
  player-decision fields `confirm_soulfray_risk` + the `CommittingDeclaration` fury mixin
  `fury_commitment` / `fury_anchor`, #1454),
  `CombatOpponentAction`, `ThreatPool`, `ThreatPoolEntry`, `BossPhase`,
  `ComboDefinition`, `Clash`, `ClashRound`, `ClashContribution`
- **Effect-palette / summon / allegiance additions (#1584):**
  - `CombatOpponent.allegiance` (`CombatAllegiance`: ENEMY default / ALLY) — mutable
    side-field; ALLY opponents fight *for* the party (summons, and future charm/
    switch-sides targets). See ADR-0059.
  - `CombatOpponent.summoned_by` (FK → `CharacterSheet`, nullable) — conjurer bond; set on
    summoned ALLY opponents.
  - `CombatOpponent.bond_expires_round` (int, nullable) — round at which the summon expires.
  - `CombatOpponentAction.opponent_targets` (M2M → `CombatOpponent`) — populated by
    `select_npc_actions` for ALLY summons so they attack ENEMY opponents. Exactly one of
    `targets` (M2M → `CombatParticipant`) or `opponent_targets` is populated per action.
- **Effect-palette / allegiance / intangibility services (#1584):**
  - `combatants_hostile_to(actor) -> tuple[list[CombatParticipant], list[CombatOpponent]]` —
    returns the sets of `CombatParticipant`s and `CombatOpponent`s that are hostile to the
    given actor, querying on `allegiance`.
  - `_resolve_npc_action_on_opponent_target(action, npc_action)` — routes an ALLY summon's
    action against a `CombatOpponent` target through `apply_damage_to_opponent`, bypassing
    the PC survivability pipeline and conditions.
  - `apply_damage_to_opponent(..., bypass_pre_apply=False)` /
    `apply_damage_to_participant(..., bypass_pre_apply=False)` — optional kwarg that skips
    `DAMAGE_PRE_APPLY` emit + `_try_interpose`; used by `reflect_damage` to bounce a hit
    without triggering another reactive cycle (loop-safety via `bypass_pre_apply=True`).
  - `drain_reactive_upkeep(encounter)` — debits `ConditionTemplate.upkeep_anima_per_round`
    from each active participant holding a reactive condition; called by `begin_round_of_combat`
    immediately after emitting `COMBAT_ROUND_STARTING`. See ADR-0060.
  - `is_untargetable(target: ObjectDB) -> bool` (`world/conditions/services.py`) — returns
    True when the target has an active `ConditionInstance` whose
    `ConditionCategory.grants_intangibility` is True; used by NPC targeting + PC AoE
    filter sites to honour the intangibility gate.
- **Event:** `EventName.COMBAT_ROUND_STARTING` (`flows/constants.py`) — emitted at the
  start of each round by `begin_round_of_combat`; `drain_reactive_upkeep` subscribes to it.
- **Condition fields added for effect palette (#1584):**
  - `ConditionCategory.grants_intangibility` (bool) — marks intangibility categories
    (Ghostform, Earthmeld); the `is_untargetable` gate reads this.
  - `ConditionTemplate.upkeep_anima_per_round` (int) — anima drained per round from the
    bearer when they hold this reactive condition (0 = no upkeep).
  - `ConditionTemplate.reactive_anima_cost` (int) — anima paid per reactive-defense fire;
    can't pay → fizzle, the attack lands (0 = free).
  - `ConditionInstance.absorb_remaining` (int, nullable) — remaining absorption buffer for
    the Aegis Field (force-field) handler; seeded by `init_absorb_buffer` on
    `CONDITION_APPLIED`.
- **Key Services (`world/combat/services.py`):**
  - `resolve_round(encounter)` — full round orchestrator: passives → refresh triggers →
    interpose challenges → focused actions → post-passes (challenges, clashes, bleed-out)
  - `declare_interpose(participant, ally)` — arm an INTERPOSE `CombatRoundAction` for the round
  - `_try_interpose(participant, pre_payload)` — fires at `DAMAGE_PRE_APPLY` seam; finds
    an armed interpose challenge and dispatches it
  - `dispatch_interpose(interposer, protected, pre_payload, approach)` — thin wrapper over
    `dispatch_capability_reaction`; calls `apply_interpose_outcome` to mutate the payload
  - `apply_interpose_outcome(pre_payload, result)` — SUCCESS zeroes payload, PARTIAL halves,
    FAILURE is a no-op
  - `_ensure_interpose_challenges(encounter, pc_actions)` — idempotently mints
    `ChallengeInstance` rows for armed INTERPOSE actions each round
  - `_refresh_participant_trigger_handlers(encounter)` — after passives, calls
    `TriggerHandler.refresh()` on each active participant so passive-installed reactive
    triggers (e.g. Shielded) fire in the same round
- **Key Services (`world/mechanics/reactions.py`):**
  - `dispatch_capability_reaction(character, protected, challenge_name, approach, outcome_fn)`
    — shared reactive spine; used by INTERPOSE and the catch-faller seam
- **Reactive content seeds:**
  - `ensure_interpose_content()` (`src/world/combat/interpose_content.py`) — idempotent
    seed for the INTERPOSE `ChallengeTemplate` + four capability-gated `Application` rows
    (telekinesis, shield, barrier, pull_aside) + Reflexes `CheckType` + SUCCESS-tier DESTROY
    consequence
  - `ensure_defend_content()` (`src/world/combat/defend_content.py`) — idempotent seed for
    the "Shielded" `ConditionTemplate` + its `DAMAGE_PRE_APPLY` `TriggerDefinition` (SELF
    filter) + `FlowDefinition` (`MODIFY_PAYLOAD multiply 0.5`) + DEFEND passive `Technique`
    with `TechniqueAppliedCondition(target_kind=ALLY)`
- **Enums:** `CombatManeuver` (FLEE / COVER / YIELD / INTERPOSE), `RoundStatus` (shared with
  `world.scenes.constants`; combat uses the same enum — DECLARING / RESOLVING / BETWEEN_ROUNDS /
  COMPLETED), `OpponentTier`, `ClashFlavor`, `EncounterOutcome`
- **API:** `/api/combat/` — GM lifecycle (begin_round, resolve_round, add/remove
  participant, add opponent, pause), player actions (declare, ready, interpose, cover,
  yield, flee, my_action, available_combos), duel challenge endpoints
- **Integrates with:** scenes (`ensure_scene_for_location`, `ensure_scene_participation`),
  vitals (`apply_damage_to_participant`, `process_damage_consequences`),
  conditions (`bulk_apply_conditions` — now installs reactive side-effects;
  `is_untargetable` for intangibility gate; `ConditionCategory.grants_intangibility`),
  mechanics (`dispatch_capability_reaction`, `resolve_challenge`),
  flows (`DAMAGE_PRE_APPLY` event; `COMBAT_ROUND_STARTING` event; `MODIFY_PAYLOAD` flow
  action for DEFEND; reactive-defense handlers in `world/magic/services/effect_handlers.py`),
  covenants (speed_rank resolution order, `apply_equipped_armor_soak`),
  magic (technique use pipeline, `CombatPull`, effect palette — summon/reactive handlers)
- **Source:** `src/world/combat/`
- **Details:** `docs/roadmap/combat.md` · architecture:
  `docs/architecture/combat-magic-integration.md`,
  `docs/architecture/damage-scaling.md`,
  `docs/architecture/combat-conditions.md`

### Vitals
Character mortality, health tracking, and the acute-peril dying state. System-agnostic — called by
combat, poison, spells, exhaustion, and any damage source.

- **Models:** `CharacterVitals` (OneToOne on CharacterSheet; fields: `life_state`
  (`CharacterLifeState`: ALIVE/DEAD — the binary mortality axis), `health`, `max_health`,
  `base_max_health` — null = derive from level/stamina/role; `died_at`),
  `VitalsConsequenceConfig` (singleton pk=1; tunable difficulty scaling + pool FKs:
  `knockout_pool`, `default_wound_pool`, `default_death_pool`)
- **Key Services (`world/vitals/services.py`):**
  - `is_dead(sheet)`, `is_alive(sheet)`, `can_act(sheet)` — mortality/agency gates.
  - `derive_character_status(sheet) -> str` — compute dead/dying/incapacitated/alive at read time.
  - `process_damage_consequences(character_sheet, damage, ...)` — full survivability pipeline:
    knockout check → death check → permanent wound check; each tier rolls the configured pool.
  - `advance_bleed_out(sheet) -> bool` — per-round progression; terminal stage routes to
    `_resolve_terminal_bleed_out` (guarded pool, not unconditional death; ADR-0049).
  - `_resolve_peril_via_pool(sheet, instance, pool) -> bool` — shared death-gated core for ALL
    acute-peril resolution: excludes `character_loss` candidates when `death_is_permitted` returns
    False; clears the condition on both death and survival; single `_mark_dead` writer.
  - `resolve_abandonment(sheet) -> bool` — resolves an abandoned victim through the source-
    appropriate pool; no-op when rescued (no acute-peril instance); seeding gap holds, never kills.
- **Key Services (`world/vitals/peril_resolution.py`, #1479):**
  - `is_pc_source(source_character) -> bool` — PC-detection via `db_account` presence.
  - `death_is_permitted(*, victim_sheet, source_character) -> bool` — False for PC sources
    (ADR-0023), None sources, and `death_deferred` victims; True for NPC sources only.
  - `select_abandonment_pool(source_character) -> ConsequencePool` — routes to
    `abandonment_pvp` / `abandonment_enemy` / `abandonment_environmental` by source kind.
  - `hostile_drove_round(victim_sheet, scene_round, declared_ids) -> bool` — True when the peril's
    source declared this round; drives the hold/advance decision in `resolve_scene_round`.
  - `potential_rescuer_present(victim_sheet, room, *, exclude_character_id=None) -> bool` — True
    when any conscious non-hostile non-victim is in the room.
  - `mark_abandoned(victim_sheet, scene_round)`, `clear_abandoned(victim_sheet)` — stamp/clear
    `ConditionInstance.abandoned_since_round`.
- **Pool constants (`world/vitals/constants.py`):** `POOL_BLEED_OUT_TERMINAL`,
  `POOL_ABANDONMENT_ENEMY`, `POOL_ABANDONMENT_PVP`, `POOL_ABANDONMENT_ENVIRONMENTAL` (seeded via
  `world.vitals.factories`; `abandonment_enemy` includes a `captured_alive` CAPTURE outcome).
- **Design invariants:** ADR-0049 (guarded pool, no unconditional death); ADR-0023 extended to the
  death layer (PC source can never produce death); ADR-0004 extended to dying state (grace window
  counts round_number beats, not wall-clock); plummet exempt from hold/abandonment.
- **Source:** `src/world/vitals/`
- **Details:** `src/world/vitals/CLAUDE.md` · `docs/roadmap/combat.md` (§Phase 8, Phase 9)

### Relationships
Track-based character-to-character regard, conditions, situational modifier gating, and
writeup kudos/complaint feedback.

- **Models:** `RelationshipCondition`, `RelationshipTrack` (+ `RelationshipTier`,
  `HybridRelationshipType`), `CharacterRelationship`, `RelationshipTrackProgress`,
  `RelationshipUpdate` (temporary points + capacity), `RelationshipDevelopment`
  (permanent points, 7/week), `RelationshipCapstone` (permanent + capacity),
  `RelationshipChange` (track-to-track redistribution), `GrievanceOption` (#1429);
  **writeup feedback (#1537):** `WriteupKudos` (subject's non-revocable commendation;
  awards kudos to the author), `WriteupComplaint` (bad-faith-RP flag for staff triage;
  `resolved` bool; zero player signal)
- **Key Fields:** `CharacterRelationship.affection` (signed sum), track
  `capacity` / `developed_points`; `UpdateVisibility` (private/shared/gossip/public)
- **Pattern:** `RelationshipCondition.gates_modifiers` (M2M to ModifierTarget) — conditions activate/deactivate situational modifiers
- **Examples:** "Attracted To" gates Allure modifier, "Fears" gates Intimidation bonus
- **Services:** `create_first_impression`, `create_development`, `create_capstone`,
  `redistribute_points` (`services.py`) — the four positive relationship-building verbs;
  `give_writeup_kudos(*, giver_account, writeup)` — commend a writeup, awards kudos to
  author (warn-skips when `"relationship_writeup"` `KudosSourceCategory` not seeded);
  `file_writeup_complaint(*, complainant_account, writeup, reason)` — file a bad-faith-RP
  complaint for staff triage
- **Exceptions:** `WriteupFeedbackError` base + `WriteupNotSharedError`,
  `NotWriteupSubjectError`, `CannotCommendOwnWriteupError`, `AlreadyCommendedError`,
  `WriteupNotVisibleError` — each with `user_message` for 400 API responses
- **Player surface (#1485, #1537):** all four verbs plus kudos/complaint are reachable
  from both web and telnet — the web `RelationshipUpdateViewSet` POST endpoints
  (`first_impression` / `develop` / `capstone` / `redistribute` / `kudos` / `complaint`)
  and the telnet `relationship <subverb>` namespace both dispatch the Actions via
  `action.run()` (ADR-0001). Read serializers expose `kudos_count` + `viewer_has_kudosed`
  on every writeup row. No consent gate — these describe the caller's regard, they do not
  compel the target's behavior (ADR-0024). FK direction: feedback lives in relationships,
  not on the kudos primitive (ADR-0010). No denormalized kudos count (ADR-0014).
- **Admin:** `WriteupComplaint` registered for staff triage (no player-facing complaint UI)
- **Actions:** `GiveWriteupKudosAction` (key `"give_writeup_kudos"`),
  `FileWriteupComplaintAction` (key `"file_writeup_complaint"`)
  (`actions/definitions/relationships.py`)
- **Integrates with:** mechanics (modifier gating), character_sheets (CharacterSheet FK),
  scenes (optional `linked_scene` defaults to the caller's active scene), progression
  (XP + `award_kudos`)
- **Source:** `src/world/relationships/`

---

## Core Infrastructure

### Actions
Self-contained game actions that own prerequisites, execution, and events.

- **Key Classes:** `Action` (base dataclass), `Prerequisite`, `ActionResult`, `ActionAvailability`
- **Registry:** `get_action(key)`, `get_actions_for_target_type(target_type)`, `ACTIONS_BY_KEY`
- **Target Types:** `SELF`, `SINGLE`, `AREA`, `FILTERED_GROUP`
- **Concrete Actions:** `LookAction`, `InventoryAction`, `SayAction`, `PoseAction`, `WhisperAction`, `GetAction`, `DropAction`, `GiveAction`, `TraverseExitAction`, `HomeAction`, `EquipAction`, `UnequipAction`, `PutInAction`, `TakeOutAction`, `UseItemAction`, `ActivatePermitAction`, `MoveToPositionAction`, `SetTheStageAction`, `PerformRitualAction` (ritual dispatch — SERVICE/FLOW runs immediately; CEREMONY creates `PendingRitualEffect`), `WeaveThreadAction` (CEREMONY finisher — consumes pending Rite of Weaving effect, calls `weave_thread`), `ImbueThreadAction` (CEREMONY finisher — consumes pending Rite of Imbuing effect, calls `spend_resonance_for_imbuing`), `RestAction` (fatigue rest — spend AP to gain `well_rested`; gated by own home + outside combat, #1491/#1524), `CreateFirstImpressionAction` / `CreateDevelopmentAction` / `CreateCapstoneAction` / `RedistributePointsAction` (relationship-building verbs — record first impressions, develop permanent points, mark capstones, redistribute between tracks; shared by telnet `CmdRelationship` and web `RelationshipUpdateViewSet`, #1485), `GiveWriteupKudosAction` / `FileWriteupComplaintAction` (writeup feedback — subject commends a writeup; any viewer files a bad-faith complaint for staff triage; shared by `CmdRelationship` and `RelationshipUpdateViewSet`, #1537)
- **Pattern:** `action.run(actor, **kwargs)` → applies enhancements → **enforces prerequisites (hard gate)** → charges AP/fatigue → executes → returns `ActionResult`
- **Prerequisites:** `get_prerequisites()` is load-bearing; `run()` calls `check_availability()` against post-enhancement kwargs. Prerequisites read action-specific kwargs via `context["kwargs"]`. Shipped: `StaffOnlyPrerequisite`, `HoldsItemPrerequisite`, `ItemUsablePrerequisite`, `OnUseTargetPrerequisite`.
- **Integrates with:** service functions (direct calls), commands (telnet compatibility), flows (future: complex triggers)
- **Not Yet Built:** `SyntheticAction` model, event emission, `CharacterCapabilities` facade, on-demand availability endpoint
- **Telnet convergence convention (ratified #1337):** the three player-action dispatch
  families and the seam each telnet command must converge on with the web — Family 1
  `dispatch_player_action()`, Family 2 consent services, Family 3 a real `Action` on
  `action.run()`. See [unified-player-action.md §10](../architecture/unified-player-action.md#10-telnet-convergence-convention--three-player-action-families-ratified-1337).
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
- **Dispatch families (#1337):** `DispatchCommand` (Family 1 → `dispatch_player_action()`),
  consent commands `ConsentRequestCommand`/`CmdAccept`/`CmdDeny` (Family 2 → consent
  services), `CmdWeaveThread` (Family 3 → `WeaveThreadAction.run()`). See
  [unified-player-action.md §10](../architecture/unified-player-action.md#10-telnet-convergence-convention--three-player-action-families-ratified-1337).
- **Magic ceremony/finisher commands (#1342):** `CmdRitual` (supports SERVICE and CEREMONY
  rituals; CEREMONY creates `PendingRitualEffect`), `CmdWeaveThread` (finisher for Rite of
  Weaving; consumes pending effect, calls `weave_thread`), `CmdImbue` (finisher for Rite of
  Imbuing; consumes pending effect, calls `spend_resonance_for_imbuing`).
- **Combat declaration pull (#1455):** A thread pull is a **modifier on `cast`/`clash`**,
  not a standalone command. `cast … pull=<thread>[,…] resonance=<name> [tier=<1-3>]` and
  `clash … pull=…` parsed by the shared `_CombatCommandMixin` pull parser. Both converge on
  `commit_combat_pull` / `request_technique_cast(cast_pull=…)` via
  `world/combat/pull_helpers.py`. Shared helpers: `build_cast_pull_declaration`,
  `resolve_pull_from_kwargs`, `commit_combat_pull`. Preview remains at
  `POST /api/magic/thread-pull-preview/` (read-only, unchanged).
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
- **Cluster registry:** `world.seeds.clusters.CLUSTER_SEEDERS` — `dict[str, Callable]` keyed by cluster name, in seed order: `"checks"` (resolution spine, first), `"magic"`, `"items"`, `"combat"`, `"consent"`, `"character_creation"` (CG-world content, last — after `magic`, which provides the cantrip/resonance `finalize_character` picks). Add a new cluster by appending an entry here. `seeded_models()` (flat representative-content list for row-count tracking) and `seeded_models_by_cluster()` (per-cluster inventory for the admin hub) are the two read shapes.
- **Surfaces:**
  - `arx seed dev` — CLI entry point (management command `src/core_management/management/commands/seed.py`; `--verbose` flag prints per-cluster row deltas).
  - Django admin **"Load sane defaults"** button (`src/web/admin/seed_views.py`) — superuser-only; runs `seed_dev_database()` and flashes a success/error message; redirects to the Game Setup hub on success.
  - Django admin **"Game Setup"** hub (`src/web/admin/game_setup_views.py`, `_game_setup/` URL, `admin_game_setup` name) — superuser-only landing page ("Welcome to a new Arx-based instance"): the clone→seed→tweak→export flow, a per-cluster content inventory (via `seeded_models_by_cluster()`) with live row counts, and links to the Big Button, Export/Import, and the World authoring apps. Header link visible to superusers next to the Big Button.
- **Interim design (Phase A):** `src/world/seeds/clusters.py` imports existing cluster masters (`seed_magic_dev`, `seed_items_dev`, etc.) from `integration_tests.game_content` at call time — a facade until roadmap task 3.2 relocates the helpers (#1220). The natively-owned clusters (`checks`, `consent`, `character_creation`) live directly under `src/world/seeds/`.
- **Key modules:** `database.py` (orchestrator), `clusters.py` (per-cluster dispatch + inventory helpers), `checks.py` (`seed_check_resolution_tables()` — the checks spine), `consent.py` (`seed_social_consent_categories()`), `character_creation.py` (`seed_character_creation_dev()` — CG-world content: Realm/StartingArea/Beginnings/Species/Gender/TarotCard/HeightBand/Build/12 stats/Rosters/Path), `types.py` (`SeedReport` dataclass).
- **Tests:** `src/world/seeds/tests/` — idempotency, non-overwrite, and playable-slice regression (including `TestSeededCharacterCreation` — `finalize_character` runs end-to-end on a seeded-only DB).
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

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
    `Gift` (self-FK `parent`, PROTECT — **gift lineage** (#2891, ADR-0192): holding a
    gift reaches its ancestors' techniques on ONE thread and ONE cap, so shared species
    material lives once in an umbrella gift; `Gift.lineage` / `lineage_ids` /
    `inherited_techniques`, `resolve_owned_gift`, `gift_threads_for`. Distinct axis from
    `species.SpeciesGiftGrant.inheritable`, which walks the *species* chain — both exist),
    `CharacterGift`, `Technique`, `CharacterTechnique` (both carry an `origin`
    field, `AcquisitionOrigin` TextChoices — #3055 acquisition-provenance ledger;
    every creation site stamps it — CG catalog pick, path/species grant, covenant
    role auto-grant, org thread weave, alt-self ability suite, the training/teaching
    mint seam, and player-authored techniques; see "Acquisition Provenance" below),
    `TechniqueStyle`, `EffectType`, `Restriction`, `IntensityTier`,
    `TechniqueCapabilityGrant`,
    `TechniqueFunctionTag` (#2443, NK `(technique, function)`, lore-repo content —
    which fine-grained `TechniqueFunction` labels a technique carries; see
    `constants.TechniqueFunction`, a 13-value code-defined vocabulary shared by
    Layer 2 per-vow specialties (`covenants.CovenantRoleTechniqueSpecialty`),
    Layer 4 situational perks (#2536), and the #2645 Insight rider (PERCEPTION
    gates `covenants.insight.maybe_produce_insight`)),
    `AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition`
    (abstract payload bases shared by `Technique*` and `TechniqueDraft*` rows),
    `TechniqueDraft` (one-per-CharacterSheet in-progress design workbench —
    `related_name="technique_draft"`; no JSON; all proper columns),
    `TechniqueDraftCapabilityGrant` / `TechniqueDraftDamageProfile` /
    `TechniqueDraftAppliedCondition` (draft payload children — inherit abstract bases)
  - **Cast-position targeting (#2206):** `position_target_shape(technique)`
    (`services/targeting.py`) classifies a technique's declared-position input shape
    (pair/single/none); combat's declaration→resolver→condition-handler wiring for the
    three placeholder-destination effect-palette techniques (Barricade/Phase Jump/Force
    Grip) lives in `docs/systems/INDEX.md`'s Combat section ("Cast-position targeting");
    see `docs/systems/magic.md`'s Effect Palette section for the updated per-effect status.
  - **Motif style binding (#2030):** `MotifResonanceStyle` (`motif_resonance` FK,
    `style` FK to `items.Style`; cap 3/resonance) is now player-authorable, not
    admin-only. Service (`services/motif_style.py`): `bind_motif_style` /
    `unbind_motif_style` / `motif_style_bindings`; exceptions `StyleResonanceUnclaimed`
    / `StyleBindingCapExceeded` / `StyleNotBound`. Actions (`actions/definitions/
    motif_style.py`, REGISTRY): `BindMotifStyleAction` / `UnbindMotifStyleAction` /
    `ListMotifStylesAction`. Telnet: `CmdMotif` (`commands/motif.py`, key `"motif"`).
    Web: `MotifStyleViewSet` (`/api/magic/motif-styles/`) + the Style catalog
    `StyleViewSet` (`/api/items/styles/`). Consumer-side wiring (coherence walker,
    style-presentation endorsement) predates this issue — see `docs/systems/magic.md`.
  - **Signature Motif Bonus (ADR-0072 — #1582):** `SignatureMotifBonus` (staff-authored
    catalog; `required_facet` FK, `required_resonance` FK, `flat_intensity_delta`,
    `narrative_snippet`; `qualifies_for(character_sheet)` gate predicate),
    `SignatureMotifBonusDamageProfile` /
    `SignatureMotifBonusAppliedCondition` (payload children inheriting the abstract bases;
    the capability-grant sibling was stripped per ADR-0248).
    `Thread.signature_bonus` (nullable FK, TECHNIQUE-kind only). Selection service
    (`services/signature.py`): `available_signature_bonuses`, `set_signature_bonus`,
    `clear_signature_bonus`, `signature_bonus_for`. Cast wiring
    (`services/signature_effects.py`): `signature_intensity_delta` + `apply_signature_bonus_conditions`
    (uses shared `apply_technique_conditions` seam) + (#1728) `signature_damage_profiles`
    (combat `_apply_damage` fold) + `resolve_signature_snippet` (shared non-combat/combat
    cosmetic narration). Narration: `signature_clause` in `narration.py`. Actions:
    `SignatureSetAction` / `SignatureClearAction` / `SignatureListAction` (REGISTRY).
    Telnet: `CmdSignature` (`commands/signature.py`, key `"signature"`). Web (#1728):
    `SignatureViewSet` (`views_signature.py`, routes under `/api/magic/signatures/`).
    E2E: `test_signature_motif_e2e.py`.
  - **Specialization engine (ADR-0055 — #1578):** `AbstractSpecializedVariant`
    (shared abstract base — the "one specialization engine"), `TechniqueVariant`
    (concrete — resonance-specialized form of a parent `Technique`, `unlock_thread_level`≥3);
    `CovenantRole` refactored to inherit the base (schema no-op). Resolved derive-on-read
    via `resolve_specialized_variant(entity, character)` (`resolve_effective_role` is a
    shim); discovery beat generalized as `fire_variant_discoveries` (dispatch on
    `target_kind`). GIFT thread substrate: `TargetKind.GIFT` + `Thread.target_gift` +
    latent provisioning at CG + `gift_resonances_for` (the four cast sites).
  - **Anima / rituals:** `CharacterAnima`, `CharacterAnimaRitual`,
    `AnimaRitualPerformance`, `SoulfrayConfig`, `MishapPoolTier`,
    `TechniqueOutcomeModifier`. `ANIMA_BANDS` + `anima_band_for(current, maximum)`
    (`constants.py`, PLACEHOLDER labels pending Apostate rewrite) derive the
    qualitative band word; `CharacterAnimaSerializer.band` surfaces it for the
    web Status tab + `sheet/status` telnet section (#1446)
  - **Ritual anima pools / blood economy (#3001, ADR-0205):**
    `Ritual.anima_requirement`, `RitualAnimaContribution` (audit; outlives its
    session), `AnimaConfig` (flat `daily_regen_amount`, `level_zero_maximum` /
    `maximum_per_level` = 10 / 100×level via `recompute_max_anima` on both
    level-write spines, `death_harvest_multiplier` ×20). Services
    (`services/ritual_pool.py`): `contribute_channel/prick/gash/sacrifice`,
    `pool_total`, `resolve_pool_gate` (deficit-bumped check; fizzle consumes the
    pool — `RitualFizzledError`), `ritual_visible_to` (hedge_accessible wired as
    the browse+perform eligibility predicate). Blood taints via authored
    `CompromiseActType` rows (`grant_blood_taint` in `services/feeding.py`);
    killing drains yield ×20 the victim's maximum. Contribute endpoint on
    `RitualSessionViewSet`; deep detail in `docs/systems/magic.md`
  - **Mage Scars (renamed from Magical Scars — display-only, §7.2):**
    `MagicalAlterationTemplate`, `PendingAlteration`, `MagicalAlterationEvent`
  - **Spec A Thread + Currency (NEW):** `Thread` (discriminator + typed FKs:
    `target_trait` / `target_technique` / `target_facet` / `target_relationship_track`
    / `target_capstone` / `target_covenant_role` / `target_gift` / `target_mantle`
    / `target_sanctum_details` — bare `ROOM` removed; SANCTUM is the leveled room
    anchor, cap = sanctum level × 10, in-sanctum pull boost), `ThreadLevelUnlock`, `ThreadPullCost`,
    `ThreadXPLockedLevel`, `ThreadPullEffect`, `ImbuingProseTemplate`,
    `Ritual` (four dispatch kinds: SERVICE → `service_function_path`; FLOW →
    `FlowDefinition`; CEREMONY → `PendingRitualEffect` + finisher command; SCENE_ACTION →
    `RitualCheckConfig`; `draft_validator_path` — new CharField, blank — is called
    inside `draft_session` before the session row is created, letting domain code gate
    who may initiate the ritual without coupling magic to any specific domain),
    `PendingRitualEffect` (in-progress CEREMONY record; unique per `(character, ritual)`;
    created by `PerformRitualAction`, consumed by finisher action `WeaveThreadAction`
    or `ImbueThreadAction`),
    `RitualComponentRequirement` (touchstone-mode: nullable `min_touchstone_tier` FK to
    `ResonanceTier`, mutually exclusive with `item_template` via `CheckConstraint`, #707 —
    see ADR-0087), `ResonanceTier` (ordered potency lookup for resonance-tied items,
    independent of `items.QualityTier` — `name`, `tier_level`, `description`),
    `ThreadWeavingUnlock`,
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
  - **Technique Entrance + Dramatic Moment Suggestion (#2183, ADR-0113):** a "make an
    entrance" whose check IS a technique cast (`enter <technique>[=<target>]` /
    `EntranceAction._execute_technique_entrance`) — one roll drives flourish +
    disposition + a GM-facing recognition nudge instead of a separate social check.
    `DramaticMomentType.suggest_on_technique_entrance` / `.suggestion_min_success_level`
    opt a moment type into the bridge; `DramaticMomentSuggestion` (PENDING/CONFIRMED/
    DISMISSED, unique per `(moment_type, character_sheet, scene)` while PENDING) is the
    suggestion row. Services: `maybe_suggest_dramatic_moments` /
    `resolve_dramatic_moment_suggestion` (`services/gain.py`). Actions:
    `ConfirmDramaticMomentSuggestionAction` / `DismissDramaticMomentSuggestionAction`
    (account-authorized, `actions/definitions/dramatic_moments.py`). Web:
    `DramaticMomentSuggestionViewSet` (`/api/magic/dramatic-moment-suggestions/`).
    Telnet: `CmdMoment` (`moment suggestions|confirm <id>|dismiss <id>`). See
    magic.md "Technique Entrance" + "Dramatic Moment Suggestion" for the full deferral
    matrix (inline / hostile-seeded / PENDING-consent / soulfray-gated) and the
    combat-side `from_entrance` marker + benign-intervention join (see Combat section).
  - **Technique effect summary (#2898):** the one block every technique surface
    shows. `summarize_technique_effects(technique) -> TechniqueEffectPayload`
    (`services/technique_effects.py`, types in `types/technique_effects.py`)
    reads the four payload tables — `TechniqueCapabilityGrant` /
    `TechniqueAppliedCondition` / `TechniqueDamageProfile` /
    `TechniqueRemovedCondition` — none of which reached any display surface
    before, and renders both structured data and a plain-words line ("Cast on an
    ally, anywhere in the room, in the physical arena. Costs 5 anima. Applies
    Guarded."). It **composes** `is_technique_hostile` and
    `derive_target_relationship` rather than restating them; no model field is
    added (`Technique.target_type`'s help text forbids a stored relationship).
    Cached on the row as `Technique.cached_effect_summary`; drop it with
    `invalidate_technique_payload_caches` after writing payload rows.
    Serialized once by `TechniqueEffectSummarySerializer` (`serializers.py`) and
    embedded as `effect_summary` on all four surfaces: `TechniqueSerializer`,
    `CGTechniqueOptionSerializer`, `CastableTechniqueSerializer` (which also
    gained `description`), and `TechniqueEntry` via `_build_magic_gifts`.
    Telnet: bare `cast` is the cast list, `sheet/magic` prints the same line;
    both and the web castable-techniques endpoint read
    `castable_techniques_for_sheet` (`world/scenes/cast_services.py`).
    Authoring gaps are reported, not guessed at —
    `technique_relationship_is_ambiguous` (payload rows carry more than one
    `target_kind`, so the derived relationship is a guess) and
    `technique_is_underspecified` (nothing authored at all), collected by
    `technique_effect_authoring_gaps()` and surfaced on `TechniqueAdmin` as
    columns + a filter. See magic.md "Technique effect summary".
  - **Per-caster technique forms (#2901):** the effect summary above describes
    the *authored* technique, which is the whole story for the two catalog
    surfaces (CG, the magic API) but not for the two per-character ones. A
    variant does not replace a technique — it makes an alternate version
    available — so the character sheet and the in-scene cast list carry a
    **list** of forms, not one resolved answer.
    `available_technique_forms(character, technique, *, character_technique=None,
    sheet=None) -> list[TechniqueFormPayload]` (`services/technique_forms.py`)
    returns the base form, each unlocked `TechniqueVariant` (at most one per GIFT
    thread resonance — `matching_variant` shadows lower tiers), and the next
    locked form per resonance as a visible goal.
    `technique_signature_payload` returns the signature flourish beside it, never
    inside it (ADR-0072). Every entry is derived by **calling
    `resolve_specialized_variant`**, never by re-implementing its selection rule;
    the `is_default` marker comes from the `preferred_resonance=None` call, the
    path that folds in the active alt-self resonance override.
    No per-caster cache exists or is needed: a resolved form is fully determined
    by `(parent_technique, variant)`, so its summary caches on
    `TechniqueVariant.cached_effect_summary` (drop it with
    `invalidate_variant_payload_caches`). Serialized by
    `TechniqueFormSerializer`; embedded as `forms` on `CastableTechniqueSerializer`
    (unlocked only — the scene shows what you can work now) and on `TechniqueEntry`
    via `_build_magic_gifts` (the full catalogue plus `signature`).
    `preferred_resonance_id` on the cast request is the web counterpart to
    telnet's `cast <tech> variant=<resonance>` (#1619); before #2901 the web had
    `use_base_form` alone and could not reach a specialized form at all.
    See magic.md "Per-caster technique forms".
  - **Ritual Liturgy (#1352):** `RitualLiturgy` (OneToOne → `Ritual`; `opening_call`
    TextField — the officiant's authored ceremonial words; public, non-spoiler).
    Seeded alongside the Ritual of the Durance via `RitualLiturgyFactory`.
  - **Audere Majora + legend-deed minting (#953):**
    `RenownAwardConfig` (abstract base — relocated to
    `world/societies/renown_config.py` in #1621 so any app can inherit it
    without a magic import cycle; shared by `AudereMajoraThreshold`,
    `DramaticMomentType`, and the societies propaganda models; carries
    `magnitude` / `risk` / `reach` / `archetypes`; provides
    `as_renown_award_kwargs()`),
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
    `StylePresentationEndorsement` (#1152 — immediate flat grant like scene-entry, keyed
    on the endorsee's claimed resonance rather than a pose; immutable, create+retrieve
    only, no settlement/delete), `ResonanceGrant` (universal audit ledger —
    discriminator `source` + typed source FKs). Read surface: `InteractionListSerializer`
    now nests `pose_kind`, `endorsee_sheet_id`, `endorsable_resonances`,
    `pose_endorsers`/`my_pose_endorsement`, `entry_endorsers`/`entry_endorsed_by_me` on
    every `GET /api/interactions/?scene=<id>` row. Frontend: `EndorsementControl` in
    `PoseUnit` (`frontend/src/scenes/components/`) — `kind` prop is `'pose' | 'entry' |
    'style'` (style added #2031), POSTing to `pose-endorsements/` /
    `scene-entry-endorsements/` / `style-presentation-endorsements/` respectively.
  - **Residence declaration + room aura, live end-to-end (#2036):** the `ROOM_RESIDENCE`
    daily-trickle `GainSource` above is reachable via a full declare→tag→tick loop —
    `SetPrimaryHomeAction` (`world.locations.services.set_primary_home`) writes
    `CharacterSheet.current_residence`, `tag_room_resonance`/`untag_room_resonance`
    (`world.magic.services.gain`) write/remove the room's aura as a
    `LocationValueModifier(key_type=RESONANCE)` row, and `residence_trickle_tick()` grants
    resonance for the intersection of tagged and claimed resonances. `StartingArea
    .grants_residence_tenancy` auto-grants a CG starting tenancy so a new character reaches
    the gate with zero manual step. A Sanctum's Ritual of Homecoming happens to write the same
    row shape onto its own room, so a resident Sanctum owner trickles from Homecoming growth
    for free — see `world/magic/CLAUDE.md` "Residence declaration + room aura tagging" for the
    full mechanism.
  - **Aura drift (#1737):** `CharacterAura`'s stored percentages recompute from
    `CharacterResonance.lifetime_earned` on every `grant_resonance()` call, firing
    achievements on authored `AuraAffinityThreshold` crossings; see magic.md
    §"Aura Drift (#1737)" for the full mechanism, including the new
    `GainSource.MISSION_REWARD` deed source.
  - **Distinctions grant/shape resonance (#1834):** `DistinctionResonanceGrant`
    (`world/magic/models/grants.py` — sidecar join, `distinctions.Distinction` × `Resonance`,
    fields `flat_amount_per_rank` / `earn_rate_bonus_per_rank`; lives in `world.magic` per
    ADR-0010). `GainSource.DISTINCTION` + `ResonanceGrant.source_character_distinction` typed
    FK. `ACCELERATED_GAIN_SOURCES` / `NON_ACCELERATED_GAIN_SOURCES` (ADR-0041, total
    classification test) gate which `GainSource`s get the earn-rate accelerator. See
    `docs/systems/distinctions.md` "Distinctions grant/shape Resonance" for the two axes
    (standing/currency vs. potency). Reverse direction (#2037):
    `DistinctionResonanceRankThreshold` (same module; unique `(distinction, resonance,
    rank)`, field `lifetime_earned_threshold`) — sustained accelerated-source gains rank up
    a **held** distinction via `check_distinction_rank_thresholds`; see distinctions.md
    "Reverse direction".
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
    `resolve_pull_effects(threads, tier, *, in_combat, target=None)`,
    `cross_thread_xp_lock(character_sheet, thread, level)`.
    Pull commit is routed through `world/combat/pull_helpers.py`:
    `commit_combat_pull` (combat cast + clash), `build_cast_pull_declaration`,
    `resolve_pull_from_kwargs`. Non-combat cast calls
    `request_technique_cast(cast_pull=…)` instead.
  - Distinction → resonance (#1834, `world/magic/services/distinction_resonance.py`):
    `reconcile_distinction_resonance_grants(character_distinction)` (establish + idempotent
    seed top-off; called by `create_distinction_modifiers`/`update_distinction_rank`),
    `distinction_earn_rate_for(character_sheet, resonance) -> Decimal` (summed earn-rate
    bonus; read by `grant_resonance` for `ACCELERATED_GAIN_SOURCES`),
    `check_distinction_rank_thresholds(character_sheet, resonance)` (#2037 reverse
    direction — ranks up held distinctions past authored
    `DistinctionResonanceRankThreshold` rows; called by `grant_resonance` for
    `ACCELERATED_GAIN_SOURCES` only, failure-isolated). Potency (POWER axis):
    `power_flat_bonus_for_resonance(sheet, resonance_id) -> int`
    (`world/mechanics/services.py`) folded into a standalone pull by
    `_fold_distinction_pull_bonus` (`world/magic/services/resonance.py`); a cast already
    reads the same modifier via `_derive_power`'s FLAT stage.
  - **Target-aware pull modulation (#1831, #1849):** `resolve_pull_effects`'s `target` param
    (the live cast/combat target; `PullActionContext.target` in `world/magic/types/pull.py`,
    populated by `commit_combat_pull` and `use_technique`'s `pull_target` kwarg) is fed
    through `apply_target_modulation(thread, target, effect_row, base_scaled)`
    (`world/magic/services/pull_modulation.py`) — the per-`target_kind` modulation seam
    (no-op unless a rule is registered for `thread.target_kind`). Two rules registered:
    `court_regard_modulation(...)` (`world/magic/services/pull_modulation_court.py`) empowers
    a COVENANT_ROLE pull by the Court leader's signed `NpcRegard` (#1717) for the target,
    sign-directed by `ThreadPullEffect.regard_polarity` (`RegardPolarity`: OFFENSIVE /
    PROTECTIVE / NEUTRAL, `world/magic/constants.py`). Tuning constant
    `COURT_REGARD_PULL_K` (placeholder, `1.0`). `relationship_bond_modulation(...)`
    (`world/magic/services/pull_modulation_relationship.py`, #1849) empowers a
    RELATIONSHIP_TRACK pull by the owner's own `CharacterRelationship.developed_absolute_value`
    bond to the thread's threaded person, when the live target IS that person or is
    hostile toward them — no polarity gate, saturating-curve magnitude via
    `RelationshipBondPullTuning` (staff-tunable singleton). Two additive valence-aware
    terms (#2034, ADR-0110) layer on top: **fraught** (keyed on `min` of
    `CharacterRelationship.developed_signed_sums`' positive/negative split — rewards a
    bond invested in both valences at once) and **devotion** (keyed on
    `max(0, developed_absolute_value - devotion_threshold)` — rewards depth alone, no
    ritual gate), each with its own tuning columns on the same singleton. The combat-UI picker
    (`compute_thread_applicability`, `world/magic/services/pull_applicability.py`) surfaces
    `InapplicabilityReason.COURT_LEADER_NO_STAKE` / `RELATIONSHIP_NO_STAKE` respectively when
    no candidate effect would ever be empowered against the given `target_persona_id`.
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
    `sanctum.feature_instance.level × 10`; GIFT: `path_stage × ANCHOR_CAP_GIFT_PER_STAGE`
    (=10) — built #1580),
    `compute_path_cap(character_sheet) -> int`, `compute_effective_cap(thread) -> int`
  - Specialization engine (ADR-0055 — #1578, `world/magic/specialization/services.py`):
    `resolve_specialized_variant(*, entity, character)` (the one resolver — Technique →
    `_ResolvedTechnique` value object with variant deltas; CovenantRole → cached-handler
    read; `resolve_effective_role` is a shim over it),
    `gift_resonances_for(character, gift) -> list[Resonance]` (derive-on-read seam
    replacing `technique.gift.resonances.all()` at the four cast sites),
    `provision_latent_gift_thread(sheet, gift, *, resonance)` (idempotent level-0 GIFT
    thread at CG, write-once on resonance). Discovery ceremony
    `fire_variant_discoveries(*, thread, starting_level, new_level)` in
    `world/covenants/discovery.py` dispatches on `target_kind` (COVENANT_ROLE → single
    parent; GIFT → iterate `gift.techniques`); called from `spend_resonance_for_imbuing`.
  - Path-crossing grant (ADR-0055 (Gift × Path) leg — #1579): `PathGiftGrant`
    (`world/magic/models/grants.py`, per `(path, gift)` curated `starter_techniques` M2M) +
    `grant_path_magic(sheet, path) -> PathMagicGrantResult` (`world/magic/services/path_magic.py`,
    idempotent — mints CharacterGift + latent GIFT thread + CharacterTechnique rows via the shared
    `grant_gift_to_character` primitive, announces via `AccessChangeSource.PATH_ADVANCEMENT`).
    Fired through the `cross_into_path(sheet, path)` seam (`world/progression/services/advancement.py`)
    used by **both** `cross_threshold` (Audere Majora) **and** the Ritual of the Durance level-3
    POTENTIAL semi-crossing (`_maybe_semi_cross_into_potential_path`, ADR-0063 — no Audere Majora).
    Proven by `test_path_crossing_grant_e2e.py` + `test_advancement.py::DuranceSemiCrossingTests`.
  - **CG catalog magic — Path → Tradition → Gift → Technique (#2426, ADR-0136):**
    `TraditionGiftGrant` (`world/magic/models/grants.py`, per `(tradition, gift)`
    grant with a `signature_techniques` M2M — a tradition's CG gift list; the
    self-taught `Unbound` tradition carries the common starter set, no extras).
    `PathGiftGrant.starter_techniques` is now read as CG pick *availability*
    (pool ∪ tradition signature extras), not an automatic grant — `grant_path_magic`
    still mints from the same rows at the level-3 Durance semi-crossing (ADR-0063,
    unchanged). `EffectType.category` (`TechniqueCategory` choices — Offense/Defense/
    Enhancement/Affliction/Utility) is the player-facing archetype grouping, replacing
    the retired `Cantrip.archetype`; `Gift.codex_entry` / `Technique.codex_entry`
    (nullable FKs → `codex.CodexEntry`) back the expanding-card → lore-modal pattern
    (#2410) on every CG catalog card. Read service (`world/magic/services/cg_catalog.py`):
    `get_gift_options(tradition, path) -> list[Gift]` /
    `get_technique_options(path, gift, tradition) -> TechniqueOptions` (callers pass
    `draft.selected_tradition` / `draft.selected_path`). The rankable
    **Tradition Training** distinction (`ModifierTarget` "Starting Technique Picks")
    adds +1 CG technique pick per rank above the Unbound baseline of 1, read via
    `CharacterDraft._get_distinction_bonus`. `Organization.tradition` (nullable FK →
    `magic.Tradition`, specific→general per ADR-0010) marks an org as a tradition's
    teaching structure; `Tradition.society` (no live consumer) was dropped. The `Cantrip`
    model + its full API/admin/frontend stack were removed. See `docs/systems/magic.md`
    and `docs/systems/character_creation.md` for the CG stage/endpoint detail.
  - **Guided Glimpse Story (#2427):** `GlimpseTag` (`models/glimpse.py`, content model —
    `CONTENT_MODELS` `magic.glimpsetag` — `axis` (`GlimpseTagAxis`), `name`, `slug`
    natural key, `description`, `example`, `sort_order`, `is_active`),
    `CharacterGlimpseTag` (instance data, never exported; `aura` FK
    `related_name="glimpse_tags"`, `tag` FK PROTECT, unique per `(aura, tag)`),
    `GlimpseTagDistinctionSuggestion` (content model — `magic.glimpsetagdistinctionsuggestion`
    — `tag`/`distinction` FKs, specific→general per ADR-0010, grants nothing, purely a
    suggestion surface). `GlimpseTagAxis`/`GlimpseState`/`GLIMPSE_AXIS_CONFIG`
    (`constants.py`) — five axes (TRIGGER single-select, what caused the
    awakening [#2611]; TONE single-select; CONSEQUENCE, WITNESS, SENSORY
    multi-select, SENSORY renders as prose prompts) and the NOT_STARTED/TAGS_ONLY/
    COMPLETE deferral cache. `GlimpseTag.paths` (M2M to `classes.Path`, empty =
    all paths; #2611) gates tag visibility by path. `CharacterAura.glimpse_state` (cache maintained
    exclusively by `world.magic.services.glimpse`, mirrors the `is_secret`
    FK-presence precedent) + `world.distinctions.models.CharacterDistinction
    .from_glimpse` (nullable FK → `CharacterAura`, SET_NULL — provenance, mirrors
    `CharacterDistinction.secret`). Services (`services/glimpse.py`):
    `refresh_glimpse_state(aura) -> GlimpseState`, `set_glimpse_tags(aura, tags, *,
    axis)`, `set_glimpse_prose(aura, text)`, `link_distinction_to_glimpse(character_distinction,
    aura)` / `unlink_distinction_from_glimpse(character_distinction)`. CG finalize
    (`world.character_creation.services.finalize_magic_data`) consumes
    `draft_data["glimpse_tag_ids"/"glimpse_story"/"glimpse_linked_distinction_ids"]`
    through these services. API: CG catalog `GET
    /api/character-creation/glimpse-tags/` (`CGGlimpseTagViewSet`, filterable
    by `?axis=` and `?path_id=<N>` [#2611], embeds
    `suggested_distinctions`) + four `CharacterAuraViewSet` actions
    (`set-glimpse-tags` / `set-glimpse-prose` / `link-glimpse-distinction` /
    `unlink-glimpse-distinction`). Sheet payload: `AuraData.glimpse_story` /
    `.glimpse_state` / `.glimpse_tags` / `.can_finish_glimpse` (privileged-only);
    `DistinctionEntry.is_from_glimpse`. Frontend: `GlimpseFlow` (shared,
    presentational), mounted by CG's `GlimpseSection` and the character sheet's
    `GlimpseEditorDialog` ("finish later"). See `docs/systems/magic.md`'s "Guided
    Glimpse Story (#2427)" section for the full detail.
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
  - Ally + party ward variants (#2208, ADR-0118): Aegis Ward/Communion, Mirror Vigil/Communion,
    Phase Guard/Communion — ALLY SINGLE/FILTERED_GROUP Technique variants of the three reactive
    wards above (no new ConditionTemplates); reactive fire (`_try_spend_reactive`) and upkeep
    (`drain_reactive_upkeep`) both debit `ConditionInstance.source_character`, falling back to
    the bearer, so an ally ward strains its caster. See magic.md §"Ally + party ward variants".
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
    `Technique.target_prerequisites` (#1793, M2M to `mechanics.Prerequisite`) — Property-gated
    targeting precondition; enforced symmetrically in both cast paths — non-combat
    (`validate_cast_target`/`resolve_targets`, `world/magic/services/targeting.py`) and combat
    (`_check_combat_target_prerequisites`/`_filter_by_target_prerequisites` under
    `resolve_combat_technique`, `world/combat/services.py`): SINGLE and SELF raise
    `InvalidCastTarget` pre-flight (SELF checks the caster directly); AREA/FILTERED_GROUP get NO
    pre-flight check and instead silently filter ineligible targets out of the resolved set.
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
  MANTLE, SANCTUM; bare ROOM removed), `EffectKind` (ThreadPullEffect — includes
  `RESISTANCE`: species-gift drawback mitigation, #1580; `resistance_amount` +
  optional `resistance_damage_type` FK; `target_gift` FK on `ThreadPullEffect` scopes
  passives to a specific gift; `get_pull_effects_for_thread` resolves gift-specific
  then generic rows),
  `VitalBonusTarget`, `RitualExecutionKind`, `AnimaRitualCategory`,
  `PendingAlterationStatus`, `AlterationTier`,
  `ConditionTargetKind` (SELF/ALLY/ENEMY — `world/magic/models/techniques.py`; derived
  relationship axis for targeting, distinct from `ActionTargetType` cardinality),
  `ActionTargetType` (SELF/SINGLE/AREA/FILTERED_GROUP — `actions/constants.py`; per-technique
  cardinality field `Technique.target_type`)
- **Exceptions (used by services + views):** `AnchorCapExceeded`,
  `InvalidImbueAmount`, `ResonanceInsufficient`, `WeavingUnlockMissing`,
  `RelationshipBondNotOwned` (weaving a RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE
  thread on a track/capstone row whose `relationship.source` isn't the weaver, #2033),
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
  mechanics (Property via Ritual site_property; Property-gated targeting via
  `Technique.target_prerequisites`, #1793),
  items (RitualComponentRequirement FKs ItemTemplate / QualityTier, or `ResonanceTier` in
  touchstone-mode; `ItemTemplate.tied_resonance`/`resonance_tier` FK into magic, #707),
  flows (Ritual FLOW dispatch via FlowDefinition),
  covenants (`draft_validator_path` on Covenant Induction ritual → `assert_initiator_can_induct`)
- **Touchstone attunement (#707 — ADR-0087):** `attune_touchstone(*, character_sheet, ritual,
  item_instance)` (`world.magic.services.touchstones`) binds a resonance-tied `ItemInstance`
  to the performer (does not consume it); dispatched by the seeded "Rite of Attunement"
  `Ritual` (SERVICE, `seeds_touchstones.py`) through the generic `perform_ritual` seam — same
  `POST /api/magic/rituals/perform/` / `CmdRitual` path every SERVICE ritual uses. The shared
  `resolve_and_consume_ritual_components(*, ritual, components, performer_sheet,
  resonance_context=None)` (`world.magic.services.ritual_components`) validates/consumes
  touchstone-mode + template-mode requirements atomically (all-or-nothing); called from both
  `PerformRitualAction._validate_components` and `SanctumInstallAction.execute()` (Sanctification
  is `client_hosted=True` and does not dispatch through `PerformRitualAction` at all — see the
  Sanctum entry above and ADR-0087).
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
  - `GET /api/magic/consequence-pool-catalog/` - the #1995 flavor catalog
    (`?action_category=` narrows to combat/technique catalogs; no param is the flat
    union). `?scope=beat` (#3562) widens it to every authored `ConsequencePool`, ordered
    by name, for the stories app's beat-authoring stakes picker; `retrieve` is always
    unfiltered and returns `ConsequencePoolDetailSerializer`'s resolved `entries` (see
    `docs/systems/magic.md`'s "Beat-authoring parity" note)
- **API endpoints (dramatic moment tagging — #1139):**
  - `GET /api/magic/dramatic-moment-types/` — unpaginated catalog for the tag-picker
  - `POST /api/magic/dramatic-moment-tags/` — create tag; `IsSceneGMOrOwnerOrStaff` gated
  - `GET /api/magic/dramatic-moment-tags/` — list tags; filterable by `character_sheet`/`scene`
- **API endpoints (entry-flourish declaration — #1140):**
  - `GET /api/magic/entry-flourish/pending/` + `GET .../pending/<id>/` — account-scoped
    pending entry-flourish offer inbox (#1140)
  - `POST /api/magic/entry-flourish/respond/` — body `{offer_id, resonance_id}`; resolves
    offer via `resolve_entry_flourish_offer` and fires the self-grant (#1140)
- **API endpoints (guided Glimpse story — #2427):**
  - `GET /api/character-creation/glimpse-tags/` — active `GlimpseTag` catalog
    (`CGGlimpseTagViewSet`, read-only, unpaginated, filterable by `?axis=`); embeds
    `suggested_distinctions` per tag. Shared by CG and the post-CG "finish later" surface
  - `POST /api/magic/character-auras/{id}/set-glimpse-tags/` — body `{axis, tag_ids[]}`
  - `POST /api/magic/character-auras/{id}/set-glimpse-prose/` — body `{text}`
  - `POST /api/magic/character-auras/{id}/link-glimpse-distinction/` — body
    `{character_distinction_id}`
  - `POST /api/magic/character-auras/{id}/unlink-glimpse-distinction/` — body
    `{character_distinction_id}`
- **Portal travel (#2222, ADR-0121):** `PortalAnchorKind` (staff-authored anchor medium
  catalog — arrival/departure verbs) + `PortalAnchor` (stackable per-room install, FK
  `room_profile`, PROTECT FK `kind`, soft-deleted via `dissolved_at`, partial-unique per
  `(room_profile, kind)` while active) + `Technique.travel_anchor_kind` (nullable FK — marks
  a technique as portal-travel through that medium). Services
  (`world/magic/services/portal_travel.py`): `travel_anchor_kinds_for` /
  `portal_destinations` / `portal_route` / `perform_portal_travel` /
  `install_portal_anchor` / `dissolve_portal_anchor`. Eligibility never consults
  `RoomProfile.is_public` — reachability is the anchor's own `is_network_open` flag OR
  owner/tenant standing at the destination. `TravelAction`'s portal branch
  (`actions/definitions/movement.py`, key `travel_to`) tries this FIRST, falling back to
  #2163's walking pathfinder unchanged when ineligible. Install costs a flat
  `settings.PORTAL_ANCHOR_INSTALL_COST` (default 5000 copper) via `InstallPortalAnchorAction`
  (key `portal_anchor_install`)/`DissolvePortalAnchorAction` (key `portal_anchor_dissolve`,
  owner-gated, no refund); telnet `CmdPortalAnchor` (`portal/install <kind>=<name>` /
  `portal/dissolve [<kind>]`). API: `GET
  /api/locations/portal-destinations/?character_id=<id>` (`world.locations.views
  .PortalDestinationsViewSet` — lives in `world.locations`, not `world.magic`, alongside the
  sibling `ComfortViewSet`; see Locations section). Frontend: `PortalsBlock`
  (room-panel). Seed: `ensure_portal_travel_content()` — starter anchors on the
  content-authored "Mirror" anchor kind, in the seeded magic-story cascade rooms. The
  "Mirrorwalking"/"Mirrorwalk" placeholder it used to invent was obliterated (#2967), so
  **no authored technique sets `travel_anchor_kind` yet and the feature has no content**.
  See magic.md "Portal travel" for the full eligibility chain + exception table.
- **Offer registry** (`commands/offer_registry.py`): generic pending-offer dispatch; `SurgeOfferHandler` and `CrossingOfferHandler` in `world/magic/offer_handlers.py`. Telnet: `accept <keyword>` / `decline <keyword>`.
- **Technique authoring action:** `AuthorTechniqueAction` (key `"author_technique"`, category
  `"magic"`) — single seam; telnet `CmdTechnique` and web `POST /api/magic/techniques/author/`
  both converge here. Telnet: `technique draft|show|set|restrict|grant|damage|condition|price|author|discard`
  (`cmd:perm(Builder)` — staff/GM only).
- **Cast observation (#2710, ADR-0170; #2734, ADR-0187; #2905, ADR-0199):**
  `resolve_cast_audience(*, caster, technique, cast_openly=False) -> CastAudience`
  (`world/magic/services/cast_observation.py`) — who perceived a cast worked in a
  concealed `TechniqueStyle.cast_concealment` style, and **how much of it they could
  attribute**, resolved per co-located observer at cast time. Concealment prefers the
  technique's gift's style when set, falling back to the caster's Path style exactly
  as before (#2905, ADR-0199) — a species-granted Minor Gift casts however the gift
  says, not however the caster's Path does. Concealment hides
  attribution, not the event: `full` (caster + technique) / `vague` (the effect, plus
  that it was a working) / `effect_only` (the effect alone). Only a technique with
  `has_perceptible_effect=False` still hides outright; a `SAME`-reach technique is never
  concealed at all, since contact gives the actor away. Materialised as
  `InteractionReceiver` rows under the `InteractionVisibility.PERCEIVED_ONLY` tier
  (writer + receivers + staff + scene GM; stricter than `VERY_PRIVATE`, which admits no
  exception). Wired into **both** cast paths — standalone
  (`world/scenes/cast_services.py`) and combat
  (`world.combat.services._record_and_broadcast_pc_action`, **not**
  `broadcast_action_outcome`, which has ~15 non-cast callers). See magic.md's "Cast
  observation" section for the full mechanism, the four enforcement points
  (`InteractionQuerySet.visible_to`, `SceneActionRequestViewSet.get_queryset`,
  `can_view_interaction`, `ActionOutcomeDetailsView`), and the lore-repo content this
  stays inert without.
- **Source:** `src/world/magic/`
- **Details:** [magic.md](magic.md) · cast lifecycle (How Magic Works):
  [technique-use-pipeline.md](../architecture/technique-use-pipeline.md) · power ledger +
  penetration contest: [power-derivation.md](../architecture/power-derivation.md)

### Traits
Character statistics and dice rolling mechanics.

- **Scale (ADR-0193, #2894):** storage is the fine-grained 1-100 range for all
  trait values. Skills display their TRUE stored value (35 reads 35 — never
  divided); stats display single-digit and store ×10 (strength 2 = stored 20),
  converted at the edge via `display_trait_value` / `STAT_DISPLAY_DIVISOR`.
  CG finalization converts stat dots ×10 and bridges CG skills into
  `CharacterTraitValue` rows.
- **Models:** `Trait`, `CharacterTraitValue`, `PointConversionRange`, `CheckRank`, `ResultChart`, `ResultChartOutcome`,
  `CharacterTraitChange` (#3055 acquisition-provenance ledger — durable record of every
  in-place `CharacterTraitValue.value` mutation: `character_sheet`, `trait`, `old_value`,
  `new_value`, `source` (`TraitChangeSource`: `CHARACTER_CREATION` / `DEVELOPMENT_LEVEL_UP`
  / `MATURATION` / `GM_GRANT`), optional `granting_tenure` FK (PROTECT, reserved for the
  #3055 slice-1c GM story-reward surface). Lives here rather than `world/progression/`
  despite `DevelopmentPoints.award_points` being its biggest writer — both `progression`
  and `character_creation` already depend one-directionally on `traits`, and the record
  answers a traits-domain question ("this value mutated") independent of which subsystem
  drove it. Writers: CG finalize's stat/skill baseline stamp (`_create_stat_values` /
  `_create_skill_values` / `_apply_post_cg_bonuses`, `world/character_creation/
  services.py`), `DevelopmentPoints.award_points` (level-up), and
  `world.progression.services.maturation.spend_maturation_point` /
  `sync_maturation_spends`. No production writer exists yet for `GM_GRANT`.
- **Handlers:** `TraitHandler` (via `character.traits`), `StatHandler` (via `character.stats`)
- **Key Functions:**
  - `character.traits.get_trait_value(name)` — with modifiers applied
  - `character.traits.get_base_trait_value(name)` — raw, no modifiers
  - `character.traits.get_trait_display_value(name)` — stats ÷10, skills true value
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
  (`from_glimpse` nullable FK → `magic.CharacterAura`, SET_NULL, #2427 — FK presence is
  the Glimpse-provenance state, mirroring `.secret`; set via
  `world.magic.services.glimpse.link_distinction_to_glimpse`/`unlink_distinction_from_glimpse`)
- **Key Methods:** `Distinction.calculate_total_cost()`, `Distinction.get_mutually_exclusive()`
- **Enums:** `DistinctionOrigin` (`CHARACTER_CREATION`, `GAMEPLAY` vestigial, `GM_AWARD`,
  `ACHIEVEMENT_AUTO_GRANT`, `CONSEQUENCE_POOL`, `ENDORSEMENT_THRESHOLD`), `OtherStatus`
- **Key Services:** `grant_distinction(character, distinction, *, origin, rank=None,
  source_description="") -> CharacterDistinction` (#2037) — the single seam every in-play
  (post-CG) acquisition/rank-up goes through; `rank=None` advances one step, an explicit rank
  only raises; `origin` is stamped once at creation and never rewritten by a rank-up; raises
  `DistinctionExclusionError` on a mutual/variant conflict (service-layer port of the CG draft
  view's checks). No XP path. See [distinctions.md](distinctions.md) "Post-CG acquisition" for
  the four ratified sources (`GMAwardDistinctionAction`/telnet `grant_distinction`, achievement
  `RewardType.DISTINCTION`, consequence-pool `EffectType.GRANT_DISTINCTION`, magic's
  `ENDORSEMENT_THRESHOLD`) and the skip-on-conflict pattern each one uses.
- **Integrates with:** character_creation (draft storage; CG-only writer besides this seam and
  admin), traits (stat modifiers), gm/actions (`GMAwardDistinctionAction`, JUNIOR-tier),
  commands (telnet `CmdGrantDistinction`), achievements (`RewardType.DISTINCTION` reward
  dispatch), checks/mechanics (`EffectType.GRANT_DISTINCTION` consequence-pool dispatch), magic
  (`DistinctionResonanceGrant` — a distinction can grant/shape `Resonance` standing and
  potency, #1834; `DistinctionResonanceRankThreshold` — the reverse direction, #2037; both
  sidecar models live in `world.magic` per ADR-0010 — see below and
  [distinctions.md](distinctions.md) "Distinctions grant/shape Resonance")
- **Source:** `src/world/distinctions/`
- **Glossary:** `src/world/distinctions/AGENT_GLOSSARY.md`
- **Details:** [distinctions.md](distinctions.md)

### Checks
Check resolution engine — converts trait values to ranks and rolls against result charts.

- **Models:** `CheckCategory`, `CheckType`, `CheckTypeTrait`, `CheckTypeAspect`, `CheckTypeCapabilityModifier` (#2505 — curated authored `(check_type, capability)` weight, `related_name="capability_modifiers"`), `CheckCall`/`CheckCallTarget` (#3295 — a GM's room-visible request that named targets roll a catalog check; one `CheckCallTarget` row per target, `status` PENDING/ANSWERED/DECLINED)
- **Scene check invocation (#3295, ADR-restating #2118's firewall):** every check anyone rolls in a scene is an authored `CheckType` at a `DifficultyChoice` band — never a freeform stat/skill/difficulty invention. `world.checks.catalog_invocation` is the shared resolve/find/band-validation core, consumed by the SENIOR ad-hoc `InvokeCatalogCheckAction` (#2118) and three new REGISTRY actions in `actions/definitions/scene_checks.py`: `SceneSelfCheckAction` (key `scene_self_check`, any player, SELF-only, broadcasts to the room via `record_interaction`/`render_challenge_outcome_narration`), `CallForCheckAction` (key `call_for_check`, JUNIOR+ GM, creates a `CheckCall` + `CheckCallTarget` rows), `AnswerCheckCallAction`/`DeclineCheckCallAction` (keys `answer_check_call`/`decline_check_call` — a target's one-tap response; answering dispatches the same self-check core bound to the call's own check/band). None of these select, compose, or fire a `ConsequenceOutcome`/consequence pool. Telnet: `check`/`callcheck` (`commands/scene_checks.py`). Web: `SelfCheckPanel`/`CheckCallPromptCard` (`frontend/src/scenes/components/`) + a `CallForCheckTab` on `GMAdjudicationPanel`. When the catalog lacks a fitting check, `ProposeCheckAction` (key `propose_check_type`) routes a structured `CheckProposal` (`world.player_submissions.models`, `SubmissionCategory.CHECK_PROPOSAL`) to the staff inbox via `submit_check_proposal` — it never creates a live `CheckType` row; adoption is a separate manual staff act.
- **Seeded check types:** `Composure` (willpower-weighted; resistance-specific — seeded via `create_resistance_check_types()` in `checks/factories.py`; used by `compute_resist_increment`)
- **Key Functions:** `perform_check(character, check_type, target_difficulty, extra_modifiers) -> CheckResult`, `get_rollmod(character) -> int`, `compute_check_rating(character, check_type, extra_modifiers=0) -> int` (pre-roll total points, no dice roll — the one answer for "what does this character bring to this check"), `compute_resist_increment(defender_character, resist_effort_level, *, level_override=None, award_development=False) -> int` (#2707, ADR-0166: routes through `compute_check_rating` on the Composure CheckType, so it now carries the defender's full rating — trait, specialization, aspect, and capability points, but NOT perk points, since `compute_check_rating` takes no `situation_ctx` and `_situational_perk_check_bonus` short-circuits to 0 without one — plus the effort modifier, clamped ≥ 0; the ACTIVE half of an opposed check. `level_override` SUBSTITUTES for the defender's resolved level so a `CombatOpponent`'s authored `level` reaches the resist path. `award_development=True` (#3066, opt-in, scene call sites only) awards the defender check-based dp for a player-declared resist effort via the same chokepoint `perform_check` uses internally), `level_opposition(check_type, *, level, character=None) -> int` (#2707, ADR-0166: the PASSIVE half — `LEVEL_POINTS_PER_LEVEL * level` plus, when `character` is given, the acting check's aspects scored against the defender's Path; deliberately exclusive with `compute_resist_increment` — a call site uses one or the other, never both, since an active rating already contains level points; combat's clash roll is the deliberate exception that opposes neither, staying at `target_difficulty=0` since a clash grades two rolls against each other instead)
- **Result-chart direction (ADR-0165):** `rank_difference = roller_rank - target_rank`; positive means the roller is stronger and gets the easier chart — the convention `ResultChart.rank_difference`'s own `help_text` states and the engine computes; guarded by `world/checks/tests/test_chart_direction.py`.
- **Key Types:** `CheckResult` (outcome, chart, roller_rank, target_rank, trait_points, aspect_bonus, level_points, specialization_points, capability_points)
- **Pipeline:** trait points (weighted via CheckTypeTrait) + aspect bonus (path level) + level points (`LEVEL_POINTS_PER_LEVEL * class level`, guaranteed on EVERY check — #2707, ADR-0166) + capability points (weighted via authored `CheckTypeCapabilityModifier` as `weight x (effective value − innate_baseline)`, curated gate — #2505, deviation-scored per #2704/ADR-0164) + modifiers → CheckRank → ResultChart → roll+rollmod → outcome
- **Integrates with:** traits (lookup tables), skills (check bonuses), progression (`get_character_path_level` — sole source of a character's class level, #2707), conditions (check modifiers + `get_effective_capability_value` agency oracle for authored capability points), goals (bonuses), scenes (active resistance via `compute_resist_increment`), combat (opposed difficulty on offense/penetration/NPC-attack defense, and `CombatOpponent.level` fed into the resist path for social verbs), mechanics (`resolve_challenge()` folds its `capability_source.value` into `extra_modifiers`)
- **Source:** `src/world/checks/`
- **Details:** [checks.md](checks.md)

### Authored Movement Redirection (#3416, ADR-0242)
Special movement (labyrinths, one-way thresholds, doors that lead elsewhere by time of
day) is **authored as rows, never modeled per space.** There is deliberately no
`Labyrinth` model and no model naming any particular space - see ADR-0242.

- **The seam:** `Character.move_to` (`typeclasses/characters.py`) dispatches
  `MOVE_PRE_DEPART` itself and honors the payload's (possibly redirected)
  `destination`. It must happen there, not in `at_pre_move`: Evennia binds
  `destination` as a local in `move_to` before calling the hook, so `at_pre_move`
  can veto a move but can never change where it goes. `MovePreDepartPayload` is
  deliberately unfrozen for this (`MovedPayload` beside it is `frozen=True`); a
  one-shot `ndb.suppress_move_pre_depart` flag stops `at_pre_move` re-emitting for
  the same move and running every trigger twice.
- **Generic verbs:** `flows.service_functions.movement.redirect_move_to_bearer_at_stage`
  (land in a random object bearing condition X at stage N) and `redirect_move` (land
  somewhere fixed); `world.conditions.services.advance_condition_stage` (event-driven
  stage progression - the round tick is the only other driver) and
  `remove_condition_by_name`.
- **How a space is expressed:** depth is `ConditionInstance.current_stage`; the dwell
  budget per depth is `ConditionStage.rounds_to_next`, so **the arrival bound is the
  authored sum of that field, not a rule in Python**; per-depth effects are
  `ConditionStage.on_entry_conditions`; room-to-depth grouping is a condition on the
  **room** (`ConditionInstance.target` accepts rooms). Logic is a `TriggerDefinition`
  + `FlowDefinition`, discriminated by `Trigger.additional_filter_condition`.
- **Worked example:** `flows/tests/test_authored_movement_redirection.py` builds a
  complete labyrinth from rows and asserts no `Labyrinth*` model exists.
- **Authoring gap:** flows/triggers are only editable in raw Django admin today - #3417.

### Conditions
Persistent states that modify capabilities, checks, and resistances with stage progression and interactions.

- **Intoxication (#2852, ADR-0184):** `intoxication_content.ensure_intoxication_content`
  (Intoxicated staged Tipsy/Drunk/Sodden/Blackout, IC-clock expiry; Hungover with a
  willpower `ConditionModifierEffect` — the #2845 moon impairment predicate's food) +
  `intoxication_service.imbibe` (the one drink seam: advance severity by potency; past
  Blackout roll `fatigue_endurance_physical`, failure = built Unconscious + Hungover).
  Fired by the `INTOXICATE` consequence effect; drugs are future content on the same seam.

- **Models:** `ConditionCategory` (`alters_behavior` bool — marks behavior-altering categories
  such as compulsion, charm, fear; used by `technique_alters_behavior` to gate consent;
  `grants_intangibility` bool — marks intangibility categories; `is_untargetable` queries this),
  `ConditionTemplate` (`upkeep_anima_per_round` int — anima drained per round for reactive
  conditions; `reactive_anima_cost` int — anima paid per reactive-defense fire; ADR-0060),
  `ConditionStage`, `ConditionInstance` (`absorb_remaining` int nullable — Aegis Field
  absorption buffer seeded by `init_absorb_buffer`), `ConditionCapabilityEffect`,
  `ConditionCheckModifier`, `ConditionResistanceModifier`, `ConditionDamageOverTime`,
  `ConditionDamageInteraction`, `ConditionConditionInteraction`, `TreatmentTemplate`
  (`mend_on_crit`/`mend_on_success`/`mend_on_partial` PositiveSmallInt, default 0 — HP mend
  amounts routed through `world.vitals.services.mend_wound()`, #2644; `once_per_wound_per_helper`
  bool, default False — duplicate-attempt gate keys on the wound instance instead of the scene
  when set), `TreatmentAttempt` (`health_mended` int, default 0 — the actual amount
  `mend_wound()` returned, may be less than the template's `mend_on_*` value; `once_per_wound_guard`
  bool, denormalized from `once_per_wound_per_helper` at insert time, mirrors
  `once_per_scene_guard`'s pattern — partial `UniqueConstraint` on
  `(helper, target_condition_instance)` where true, #2644)
- **Lookup Tables:** `CapabilityType`, `CheckType`, `DamageType`
- **Handlers:** `obj.conditions` (`ConditionHandler` / `CharacterConditionHandler` in
  `world/conditions/handlers.py`, installed as `@cached_property` on `ObjectParent`).
  `CharacterConditionHandler.active` mirrors `get_active_conditions`. `.invalidate()`
  wired into all `world/conditions/services.py` mutation sites.
- **Key Functions:** `apply_condition()`, `remove_condition()`, `get_capability_status()`,
  `get_check_modifier()`, `get_resistance_modifier()`, `process_round_start()`,
  `process_round_end()`, `process_damage_interactions()` (wired into combat #2018), `get_treatment_candidates()`,
  `perform_treatment()` (routes `mend_on_*` through `world.vitals.services.mend_wound()`
  alongside its existing severity-decay path, #2644), `get_effective_capability_value()`
  (the one-oracle agency/requirement answer — see "Capability magnitude curve" below)
- **Capability magnitude curve (#2708 — `magic.CapabilityPowerConfig`):** staff-tunable
  singleton (`power_per_doubling`, default 10) driving
  `world.magic.services.capability_curve.apply_capability_curve` /
  `get_capability_power_config()` — `value = round(base * 2 ** (sensitivity * power /
  power_per_doubling))`, replacing the old linear `base + intensity_multiplier * power`
  shape on `TechniqueCapabilityGrant.calculate_value()`. **No config row = every
  consumer's pre-#2708 number, bit-for-bit** — both oracles check for the row FIRST and,
  when absent, skip power derivation entirely and call `calculate_value()` bare rather
  than deriving a real power figure and feeding it to the retired formula (a regression
  caught and fixed before merge). Two oracles read technique-granted capability magnitude
  and must agree on the ambient default: `_technique_capability_values`
  (`world.conditions.services`, the agency oracle behind `get_effective_capability_value`,
  accepts an optional `action_ctx`) and `_get_technique_sources`
  (`world.mechanics.services`, the availability oracle behind
  `get_capability_sources_for_character`, always ambient — no `action_ctx` param). Both
  derive power as `technique.intensity + context_free_power + contextual_thread_power(...)`
  (`CharacterThreadHandler`, `world/magic/handlers.py`) and resolve the technique→gift
  mapping via `resolve_gift_ids_by_technique` once per sweep, never per grant. A thread's
  tier-0 `INTENSITY_BUMP` only feeds this power figure when
  `_anchor_ambiently_active` (`world/magic/services/resonance.py`) confirms real,
  demonstrable engagement (not player assertion) — the paid-pull sibling predicate is
  `_anchor_in_action`, deliberately separate. See ADR-0169 for the full design decisions.
- **Perception gate (#1225):** `can_perceive(actor, target)` composes co-location with
  per-observer concealment detection (`is_concealed()`, `active_concealments()`,
  `ConditionInstance.detected_by`). Consulted by `OnUseTargetPrerequisite` (item-use targeting),
  `RoomStatePayloadSerializer._serialize_contents` + telnet `BaseState.get_display_characters`
  (room-occupant lists omit a concealed-and-undetected character entirely — name, dbref, and
  avatar never leak), `SearchAction` (the detection roll; a successful detection also pushes
  a `send_room_state()` refresh to the detecting actor so the target appears without waiting for
  the next natural refresh), and `LookAction`'s direct-target gate (naming a concealed character
  directly fails with the same not-found message a genuinely absent target would — `CmdLook`
  rewrites the message from the player's own raw input so a prefix/case-variant probe can't
  distinguish "concealed" from "never there"). The global presence directories (`where_listing`,
  `who_listing`) instead consult the unconditional `is_concealed()` directly (no per-observer
  detection concept for an anonymous global directory) — a concealed character never appears in
  `where`/`who`, regardless of who's asking. Every condition-removal path that can end
  a concealing condition fires the same register/clear teardown `remove_condition`
  uses, so none of them bypass the OOC unseen-observer hook: the bulk-clear paths
  (`remove_conditions_by_category`, `clear_all_conditions`), the severity
  advance/decay paths (`advance_condition_severity` re-advancing from zero,
  `decay_condition_severity` decaying to zero), the admin-authorable interaction
  paths (`process_damage_interactions`'s `ConditionDamageInteraction.removes_condition`,
  `bulk_apply_conditions`'s `ConditionConditionInteraction.removes_condition`), and
  natural `DurationType.ROUNDS` countdown-to-zero expiry
  (`_process_duration_and_progression`). See ADR-0083 for the separate OOC
  unseen-observer transparency guarantee this composes with.
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
Species/race definitions with stat bonuses, trait-backed language fluency/comprehension (#2993,
ADR-0214), and species-gift provisioning.

- **Models:** `Species`, `SpeciesStatBonus`, `Language` (`trait` O2O to a `TraitType.LANGUAGE`
  `Trait` — per-character fluency is the ordinary `CharacterTraitValue`; `is_universal` grants at CG
  regardless of species/Beginnings), `CharacterSheet.current_language` / `Interaction.language` FKs,
  `SpeciesGiftGrant` (through-model: species → MINOR `Gift` + optional `drawback_condition`/
  `benefit_condition` FKs to `conditions.ConditionTemplate`, optional `drawback_distinction`
  FK to `distinctions.Distinction`, and `cg_point_cost` (PositiveInteger, default 0);
  natural key `(species, gift)`; `clean()` asserts `gift.kind=MINOR`; FK direction
  specific→general per ADR-0010. Four independent, freely-combinable balance shapes —
  condition drawback, benefit condition, drawback distinction, CG point cost — plus the
  all-null/0 free-weak-gift default; per-species shape assignment is lore-repo content.
  See [species.md](species.md).)
- **Key Services:** `provision_species_gifts(sheet, *, resonance=None)` (`world/species/services.py`) —
  mints the MINOR `CharacterGift`, the latent level-0 GIFT thread (via
  `provision_latent_gift_thread`), applies any drawback/benefit condition, and grants any
  forced `drawback_distinction` (via `distinctions.services.grant_distinction`,
  `origin=DistinctionOrigin.SPECIES`) idempotently; called from `finalize_magic_data`
  (CG, after the Major-gift block). See ADR-0071. `cg_point_cost` is summed across the
  selected species + ancestors into the `"species"` line of
  `CharacterDraft.calculate_cg_points_breakdown()` (character_creation).
  Appetites (#2853, ADR-0182): `services/appetites.py` (upkeep/glut/Ravenous/regen-skip),
  `services/feeding.py` (`feed_anima` + feed/drain consent resolvers), models
  `AppetiteUpkeep`/`AppetiteUpkeepReceipt`/`FeedingRecord`, `CharacterAnima.glut`;
  `vitals.mark_fed_to_death` is the NPC gorge-kill seam. See magic.md.
  Sunlight bane/allergy (#2846, ADR-0179): `sun_exposure.felt_sun_exposure` (graded
  breakdown), `sun_sensitivity.sun_sensitivity_for`/`sun_severity` (tag-anchored tier →
  severity), `reconcile_sunlight_exposure` + `reconcile_sun_exposure_safely` (movement/
  cron/equip/position triggers; staged condition sync), `sun_refuge.find_sun_refuge`/
  `flee_to_sun_refuge` (AFK auto-flee), `species_innate_distinction_ids` (CG gate),
  `tasks.sun_reconcile_tick` (`species.sun_reconcile` cron), factories
  `ensure_sunlight_exposure_content` (staged template) + `ensure_sunlight_distinctions`
  (Bane/Allergy: Sunlight anchor rows); PLACEHOLDER constants in `sun_constants.py`.
  Moon control (#2845, ADR-0183): `moon_pull.felt_moon_pull`/`moon_clarity_instance_value`,
  `moon_sensitivity.reconcile_moon_pull` (control window: `moon_control` check →
  forced shift + shared Berserk) + `reconcile_cani_unease` (umbrella flavor state),
  `moon_provisioning.ensure_lycan_battle_form` (lazy battle-form provisioning),
  `tasks.moon_reconcile_tick` (`species.moon_reconcile` cron), factories
  `ensure_moon_bound_distinction`/`ensure_moonlit_unease_condition`; seeded content in
  `_seed_moon_content` ("The Wolf's Fury" grant); Berserk production seed + Restore-to-Sense
  removal effect in `world/conditions/berserk_content.py`; compulsion in
  `world/combat/berserk_compulsion.py` (auto-attack fallback, disengage refusal,
  out-of-combat rampage); PLACEHOLDER constants in `moon_constants.py`.
  Language mechanics (#2993, ADR-0214): `language_constants.py` (`Fluency` bands
  broken/conversational/fluent, `BAND_KEEP_RATIO`, `FLUENT_GRANT_VALUE=70`),
  `language_services.py` (`garble_text`, `speech_seed`, `fluency_value`, `effective_band`,
  `render_speech` — deterministic per-viewer comprehension, live-recomputed on every render, never
  snapshotted), `provision_starting_languages(sheet, *, beginnings)` (universal + Beginnings/species
  grant at CG, called from `finalize_magic_data`); actions `set_language`/`train_language`
  (`actions/definitions/language.py`) + telnet `speak`/`train_language`
  (`src/commands/language.py`); `say`/`whisper`/`mutter` resolve a per-utterance language
  (`_resolve_spoken_language`, `actions/definitions/communication.py`); `GET
  /api/species/my-languages/` (`MyLanguagesViewSet`). See species.md's Language Mechanics section.
- **Key Methods:** `Species.get_stat_bonuses_dict()`, `Species.is_subspecies`
- **Integrates with:** character_creation (Beginnings.allowed_species, CG points
  breakdown, `provision_starting_languages` at CG finalize), forms (physical traits — per-species
  palettes + `is_required` identity markers on `SpeciesFormTrait`), roster heredity (Parent Dominance
  species inheritance, #2815 / ADR-0173), magic (GIFT thread via
  `provision_latent_gift_thread`), scenes (`Interaction.language` + per-viewer comprehension in
  interaction serializers, #2993), conditions (drawback/benefit condition application),
  distinctions (forced drawback distinction grant)
- **Source:** `src/world/species/`
- **Details:** [species.md](species.md)
### Forms
Physical appearance options (height, build, hair/eye colors) and the alternate-self
shapeshift lifecycle.

- **Models:** `HeightBand`, `Build`, `FormTrait` (+ `composite_option` FK, #2632 — the
  umbrella value blends resolve to: multihued hair, mismatched eyes), `FormTraitOption`
  (+ `requires_teaching`, #2632 — exotic looks gated on knowing them), `CharacterForm`,
  `FormValueComponent` (#2632 — the ACTUAL ordered components of a blended value, so the
  normalized layer renders "Red-Green" honestly under descriptor concealment),
  `CharacterKnownStyle` (#2632 — learned by having it done: NPC stylist or a knowing PC
  stylist teaches on application), `FormCombatProfile`, `FormCombatProfileEffect`,
  `AlternateSelf`, `ActiveAlternateSelf`, `FormMarking` (#2985 — tattoo/scar/brand/
  birthmark/rune on a form's body region; concealed by clothing, Reveal/Cover state)
- **Enums:** `TraitType` (color/style/feature — FEATURE = structural species markers:
  horns, wings, fangs, #2815), `FormType` (TRUE/ALTERNATE/DISGUISE), `DurationType`,
  `MarkingKind` / `MarkingSource` (#2985, `constants.py`)
- **Key Services:** `assume_alternate_self(sheet, alt)`, `revert_alternate_self(sheet)`,
  `switch_form(character, target_form)`, `revert_to_true_form(character)`,
  `get_presented_appearance(character)` (normalized = joined blend components when present),
  `change_appearance(..., blend=)` (#2632 — blend ADDS the color: composite value +
  component rows; a full application clears components),
  `knows_style(sheet, option)` / `learn_style(sheet, option)` (#2632),
  `trigger_transformation(sheet, alt, *, cause, instance_value=1.0)` (the seam both non-command cause-paths call; #1604),
  `identification_difficulty(viewer_sheet, target_character)` / `attempt_identification(viewer, target, guess_name=None)` (`world/forms/services/identification.py`, #1107 slice 5 — the PC-to-PC "who's really under this mask" check; second `PersonaDiscovery` producer, see [appearance_and_identity.md](appearance_and_identity.md) §"Identification loop (slice 5)"),
  `grant_marking(sheet, ...)` / `visible_markings_for(character, observer)` (`world/forms/services/markings.py`, #2985 — the marking write seam + the observer-filtered read behind look's "Markings:" line and `GET /api/items/visible-markings/`)
- **Key Exceptions:** `RevertBlockedError`, `AlternateSelfActiveError`, `FormOwnershipError`,
  `TraitNotBlendableError`, `StyleNotKnownError` (#2632; items-side wrappers
  `BlendNotSupported` / `StyleNotKnown` / `StyleChoiceRequired` on `use_item`)
- **Integrates with:** character_sheets (appearance, character anchor), scenes (Persona,
  `PersonaDiscovery`, `CharacterRelationship`-adjacent familiarity), mechanics
  (ModifierSource / CharacterModifier), magic (CharacterTechnique), npc_services
  (`random_active_functionary` botch picker), actions (`IdentifyAction`, registry key
  `identify`)
- **Source:** `src/world/forms/`
- **Details:** [forms.md](forms.md)
### Appearance & Identity (architecture)
How Persona (identity), Form (real body), disguise/illusion (fake overlay), and the
true-form/natural baseline compose into what a viewer sees — plus the per-persona
descriptor overlay, cosmetic editing, and shapeshift slots.

- **Spans:** forms (body), scenes (Persona), character_sheets (anchor), npc_services
  (Functionary botch picker), actions (`IdentifyAction`)
- **Key ideas:** four-question model; `(Persona × FormTrait)` descriptor; single
  render composition (viewer-gated); real-vs-fake truth ledger; cosmetic vs disguise;
  PC-to-PC identification loop (familiarity-staged intellect+Investigation check vs.
  the illusion-piercing contest, kept distinct)
- **Status:** design (slices 1-4); **slice 5 (PC-to-PC identification loop) BUILT,
  #1107** — `identify` registry action + telnet `CmdIdentify` + `PersonaContextMenu`
  web dispatch; depends on #1044
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
  - `ensure_default_character_class() -> CharacterClass` — get-or-creates the single
    shared placeholder `CharacterClass` (`DEFAULT_CHARACTER_CLASS_NAME`, "Adventurer")
    every character is stamped with pre-class-selection (#3038); CG finalize and the
    #2121 `select_initial_path` recovery seam both call it before stamping level 1.
- **Key Methods:** `Path.parent_paths`, `Path.child_paths` (evolution hierarchy)
- **Integrates with:** progression (level requirements), character_creation (Prospect
  selection), vitals (`derive_base_max_health` reads `ClassStageHealthRate` + `stage_for_level`)
- **Source:** `src/world/classes/`
- **Details:** [classes.md](classes.md)
### Areas
Spatial hierarchy for organizing rooms into a nested tree of areas, from individual
buildings up to entire planes. A `Room` is not its own `Area` level — it hangs off a
`Building`-level `Area` via `RoomProfile.area`.

- **Models:** `Area` (nullable `grid_x`/`grid_y` parent-local rendering coordinates,
  #2223; `slug` unique `SlugField` + `NaturalKeyMixin` (`NaturalKeyConfig.fields =
  ["slug"]`) + `origin` (`GridOrigin`), #2436/#2448), `AreaClosure` (unmanaged,
  materialized view)
- **Enums:** `AreaLevel` (low to high: Building, Neighborhood, Ward, City, Region,
  Kingdom, Continent, World, Plane); `GridOrigin` (both `world.areas.constants` —
  AUTHORED/STORY/PLAYER, #2436/#2448): who authored a grid
  element. Only `origin=AUTHORED` areas/rooms (with their identity key set) export to
  the lore repo via `grid_export.export_grid_bundles()`; `STORY` (GM-built) and
  `PLAYER` (player-built) rows never export. Default is `PLAYER` so nothing exports by
  accident; promotion to `AUTHORED` is a deliberate staff act. `evennia_extensions.
  RoomProfile` carries the matching `fixture_key` (permanent, slugged identity,
  natural-keyed) + `origin` pair — see "Grid content export/import" below.
- **Key Functions:** `get_ancestry()`, `get_descendant_areas()`, `get_rooms_in_area()`,
  `reparent_area()`, `area_grid_path(area) -> list[tuple[int | None, int | None]]`
  (#2223, root->area chain of parent-local `(grid_x, grid_y)` pairs; rendering-hint
  data only, never consulted by `find_route()` or any routing code)
- **Presence & Travel (#1463 + #2163 + #2222 + #2223):** `where_listing()` — public presence
  directory, returns `WhereEntry(persona_name, room_path, room_id)` per online
  character in a publicly-listed room; `find_route(origin_room, destination_room) ->
  list[ObjectDB] | None` (`world.areas.positioning.travel`) — frontier-batched BFS
  pathfinder that crosses Area boundaries via the room exit graph (ADR-0120; no
  separate Area-to-Area adjacency model), public-rooms-only, capped at
  `settings.TRAVEL_MAX_HOPS`. `TravelAction`/`StopTravelAction` (`registry_key`s
  `travel_to`/`stop_travel`) auto-walk a computed route one hop at a time; shared by
  telnet `CmdTravel` and "Go there" buttons on the scene browser + presence panel.
  `TravelAction.execute()` tries a portal-travel branch FIRST (#2222 — instant relocation via
  a known travel-mode `Technique` + matching anchors at both ends), falling back to this
  walking pathfinder unchanged when ineligible; see the Magic section's "Portal travel" entry.
  See [areas.md](areas.md) "Presence & Travel" and "Coordinates" sections.
- **Pattern:** Postgres materialized view with recursive CTE for hierarchy queries
- **Integrates with:** realms (Area.realm FK), evennia_extensions (RoomProfile.area FK)
- **Area Quality (#1889):** `AreaQuality` sidecar (per-Area quality 0-5, 3=Ordinary).
  Raised by `CLEANUP` TIERED_PERIOD projects (players contribute AP/money/items;
  graded at deadline into quality-delta tiers). Eroded by crime heat (`accrue_heat`
  calls `erode_area_quality`) and `OPEN_ENCOUNTER` combat (via `ENCOUNTER_COMPLETED`
  trigger). Weekly decay sweep (`cleanup_quality_decay_tick`) decays above-normal
  quality after `CLEANUP_DWELL_DAYS` and regains below-normal after
  `CLEANUP_REGAIN_WEEKS`. Room descriptions get quality-based suffixes at display
  time, appended after any #3291 season/phase description variant has already
  replaced the base desc (see `RoomState.get_display_desc`,
  `flows/object_states/room_state.py`). Contributors earn celestial resonance (via
  `ProjectKindResonanceAward`) and society reputation (via `bump_society_reputation`
  with `area.dominant_society`).
- **Room Description Variants (#3291):** `evennia_extensions.RoomDescVariant`
  (`room_profile` FK, nullable `season`/`phase` TextChoices reusing
  `world.game_clock.constants.Season`/`TimePhase`, `description` text, unique on
  `(room_profile, season, phase)`) - optional builder-authored prose for a specific
  IC season/time-of-day. `resolve_room_description(profile, ic_now)`
  (`evennia_extensions.services.room_desc_variants`) resolves most-specific-wins:
  `(season, phase)` > `(season, -)` > `(-, phase)`, falling back to the base desc
  (including when the game clock is unset). An event's `temporary_description`
  overlay (`world.events.services._apply_room_overlay`) always takes precedence
  over a variant. Authoring: `RoomDescVariantInline` on `RoomProfileAdmin`, plus
  `staff_set_room_desc_variant`/`staff_remove_room_desc_variant` in the staff
  world-builder canvas below.
- **Staff World-Builder Canvas (#2449, epic #2436):** `world.areas.grid_services`
  extracts the area-generic room-graph core (`create_room`, `create_exit_pair`,
  `cell_occupied`, `place_room_on_grid`, `stranded_rooms` BFS, `promote_to_authored`,
  `suggest_fixture_key`, `ensure_slug_change_allowed`) out of
  `world.buildings.room_services` (#670), so the owner-facing Room Builder and the
  staff canvas share one substrate instead of two drifting copies. Forty-three
  REGISTRY actions (`src/actions/definitions/world_builder.py`,
  `category="world_builder"`, `target_type=SELF`) — `create_area`/`edit_area`/
  `staff_dig_room`/`staff_edit_room`/
  `staff_link_rooms`/`staff_unlink_rooms`/`staff_rename_exit`/`staff_place_room`/
  `staff_publish_room`/`staff_remove_room`/`staff_remove_area`/`staff_move_room`/
  `promote_room`/`promote_area` + the six #2451 discovery/portal verbs + the #3269
  Phase B room-authoring set (stats/places/ambient/feature/staffing/travel/
  blueprint/bindings/exit-detail/duplicate/batch-dig; `edit_area` carries the
  Phase C area metadata) + the #3291 `staff_set_room_desc_variant`/
  `staff_remove_room_desc_variant` pair — gated by `BuildWarrantPrerequisite`
  (#3477 Task 1, replacing the old `StaffOnlyPrerequisite`: staff bypass
  unconditionally, a non-staff GM additionally passes with an `AreaBuildGrant`
  over the resolved area at the `BUILDING` floor — no ownership/tenancy standing
  otherwise) except `edit_area` (the stricter level-aware variant) and
  `author_clue` (`MinimumGMLevelPrerequisite(SENIOR)`, #3432). `staff_dig_room`
  requires an AUTHORED area and always authors the new room outright — and, as of
  #3477 Task 2, births it *unpublished*: `RoomProfile.published_at` defaults to
  `now()` (an ordinary/PLAYER room is live immediately) but `create_room` sets it
  to `NULL` for `origin=AUTHORED`, and an unpublished room does not exist in the
  live world — not enterable (`ExitState.can_traverse`) and its exits hidden from
  the room-state payload (`RoomStatePayloadSerializer._exit_hidden_from_looker`)
  — for anyone but a story-runner (GM/Staff, `is_story_runner`). `staff_publish_room`
  (kwarg `room_id`) stamps `published_at=now()`; idempotent (a re-publish just
  refreshes the stamp), no unpublish verb, no separate "done" flag.
  `staff_remove_room` refuses an
  already-exported room (report-never-delete pipeline territory, not the canvas);
  `staff_unlink_rooms`'s stranding guard is the narrower "would this drop leave an
  *occupied* room with zero exits" rule, not the Room Builder's anchor-room BFS
  (there's no single anchor world-wide). `world.locations.services.
  set_room_display_data` gained `persona=None`/`bypass_ownership=False` kwargs so
  `staff_edit_room` can write display data with no owner/tenant standing. Read-only
  staff API: `WorldBuilderViewSet` (`src/world/areas/builder_views.py`, mounted at
  `/api/world-builder/areas/` — `IsAdminUser`-gated; `GET .../<id>/manager/` returns
  the area's full room+exit payload, private rooms included, unlike the player-facing
  `AreaViewSet`/`RoomProfileViewSet`). Frontend: shared `map-canvas/` primitives
  (`MapCanvasShell`, `useMapNodeInteraction`, `coords`/`edges`/`ghosts`/`GhostNode`)
  extracted so buildings, battles, and the new `world-builder/` app
  (`/staff/world-builder`, linked from the profile dropdown + Game Setup hub) render
  off one canvas shell instead of three parallel ones. Not built this slice:
  `edit_area` UI. **GM story areas (#2450, epic #2436
  slice 3) BUILT** — a GM's own build-and-run space on the same substrate, gated by
  GM trust rather than the staff flag; see the GM system's "Story areas & story
  rooms" entry above for the full model/service/action/API/telnet rundown.
  **Discovery/portal authoring (#2451, epic #2436 slice 4) BUILT** — clue/portal
  layers land in the staff canvas: `RoomDetailPanel` gains staff-only "Clues" and
  "Portal anchors" sections (`PlaceClueDialog`/`PlacePortalAnchorDialog`),
  `WorldRoomNode` shows a combined clue+trigger count badge, and `WorldCanvas`
  renders paired same-kind `PortalAnchor`s as dashed edges (`pairPortalAnchors` +
  `portalEdges` in `map-canvas/edges.ts`; an unpaired anchor still shows, just with
  no edge). Six new REGISTRY actions
  (`staff_place_clue`/`staff_remove_clue`/`staff_place_clue_trigger`/
  `staff_remove_clue_trigger`/`staff_place_portal_anchor`/`staff_remove_portal_anchor`)
  and a new staff-authoring service, `install_portal_anchor_as_staff` (no owner/tenant
  standing check, no currency cost — see magic.md's "Portal travel" section). The
  grid bundle format gains `clues`/`clue_triggers`/`portal_anchors` sidecar sections;
  see the "Investigation & Discovery" system entry below for the clue-side
  model/action detail. **Area art cascade + ambient-condition authoring (#3477 Task
  3):** `Area.art` (FK to `arxii.Media`, mirrors `PageBackground.art`'s shape) resolves
  most-specific-wins down the hierarchy like climate/realm; area and room payloads gain
  `art_url` (`WorldBuilderAreaSerializer.get_art_url` walks the area chain directly, the
  same inline-cascade convention as `get_effective_climate` on that serializer;
  `world.locations.services.resolve_area_art(room_profile)` is the room-level entry
  point — a room's own `ObjectDisplayData.thumbnail` wins outright, else it falls back to
  the area cascade). Authoring (#3535): `staff_edit_room`/`edit_area` take an `art_id`
  (`Media` pk; falsy takes the art down, absent leaves it untouched), reached from both
  documents' marginalia via the shared `ArtDialog` (library + upload reuse
  `/api/roster/media/`). Two new REGISTRY actions, `staff_add_ambient_condition`/
  `staff_remove_ambient_condition`, wire the pre-existing (BUILT NOT WIRED)
  `AmbientEmoteCondition` model to the canvas — kwargs `line_id`/`condition_type`/
  `target_id` plus per-type extras (`minimum_value` for RESONANCE_MIN, `min_fame_tier`/
  optional `perceiving_society_id` for RENOWN_MIN; LEGEND_DEED needs no ref). The
  room-detail payload's `ambient_lines` now nest a `conditions` list
  (`{id, condition_type, label}`; `world.narrative.ambient_content.describe_condition`
  renders the label). Every ambient line/condition write re-derives the delivery
  Trigger graph in place via `world.narrative.ambient_triggers.
  resync_room_ambient_triggers`/`resync_area_ambient_triggers` (#3477 fix round 2) —
  entry lines deliver only through pre-derived Triggers with frozen line groups
  (`ensure_ambient_group_trigger`, moved there from `grid_import`, which now
  delegates), so without the resync a canvas write was invisible until a re-import
  ADR-0238 forbids on a populated database.
- **Source:** `src/world/areas/`
- **Details:** [areas.md](areas.md)

### Locations (Ambient Value Cascade)
Authored substrate for room/area values that cascade through the `Area`/`AreaClosure` hierarchy:
ambient stats (crime, order, lighting, climate-driven exposure), magical resonance magnitudes, and
(#1744) per-hazard damage-type shelter — plus deed/tenancy ownership tracking.

- **Models:** `LocationValueOverride` (absolute claim, most-specific wins), `LocationValueModifier`
  (additive, `change_per_day` decay/growth), `LocationOwnership` (deed/title, cascades
  most-specific-wins), `LocationTenancy` (granted use right, ALL applicable rows collected, not
  most-specific-wins; **the one tenancy model** — #670 removed the old
  `RoomProfile.tenant_persona` pointer — with `is_primary_home` (the Arx-1
  `addhome`; one active per persona via partial unique constraint; drives
  home-anchored `prestige_from_dwellings` and syncs the #1514 Evennia-`home`
  residence))
- **Enums:** `StatKey` (CRIME/ORDER/LIGHTING/NOISE/AMENITY/COLD/HEAT/WET/WIND/DRY/…),
  `LocationParentType` (AREA/ROOM), `key_type` discriminator (STAT/RESONANCE/DAMAGE_TYPE — selects
  `stat_key` CharField vs `resonance` FK (`magic.Resonance`) vs `damage_type` FK
  (`conditions.DamageType`)), `HolderType` (PERSONA/ORGANIZATION)
- **Damage-type axis (#1744):** hazard shelter per room, generic across any `conditions.DamageType`
  row — adding a new hazard needs zero new discriminator code, only new `LocationValueModifier`/
  `LocationValueOverride` rows. `hazard_is_covered(room, damage_type, *, threshold=1)` is the
  read-side hard boolean gate ("does the hazard reach this place at all"), distinct from
  `ConditionResistanceModifier` arithmetic ("how much damage gets through") — see ADR-0069.
- **Key Functions:** `effective_value(room, stat_key=… | resonance=… | damage_type=…)` (single-axis
  polymorphic read), `effective_values_for_rooms()` (bulk), `hazard_is_covered()`,
  `felt_exposure()`/`room_discomfort()`/`comfort_points()`/`comfort_level()` (climate → comfort
  cascade, #1514/#1522), `resolve_area_art(room_profile)` (#3477 — a room's own
  `ObjectDisplayData.thumbnail` wins outright, else most-specific-wins up `Area.art`, mirroring
  `get_effective_climate`), `character_comfort_summary()`/`comfort_mitigation()` (per-character
  readout), `effective_owner()`/`current_tenants()`/`ownership_for()`/`is_owner()`/`tenancies_for()`/
  `is_tenant()` (ownership/tenancy lookups), `assign_room_tenant()`/`end_room_tenancy()`/
  `set_primary_home()` (#670 player tenancy seam — owner grants/evicts, tenant departs or
  designates home; syncs the #1514 Evennia-`home` residence + recomputes prestige). #2036 widened
  `set_primary_home()`: it now also writes `CharacterSheet.current_residence` (via
  `world.magic.services.gain.set_residence`, the daily resonance-trickle gate) on every deliberate
  declaration, accepts org-derived owner/tenant standing (not only a direct `LocationTenancy` row)
  by minting a personal tenancy first via `grant_tenancy()`, and `end_tenancy()` clears
  `current_residence` when the ended tenancy was the declared residence.
  `maybe_default_residence()` was widened the same way — the first room a persona rents/acquires
  now defaults both Evennia `home` and `current_residence`. Room aura tagging —
  `tag_room_resonance()`/`untag_room_resonance()` (`world.magic.services.gain`) — writes/removes
  the `LocationValueModifier(key_type=RESONANCE, source=ROOM_RESONANCE_TAG_SOURCE)` row a room's
  resident resonances trickle from; reached via Actions `tag_room_resonance`/`untag_room_resonance`
  (telnet `room/aura <resonance>` / `room/aura clear <resonance>`, web `RoomAuraPicker`), gated by
  `IsRoomTenantPrerequisite` (widened #2036 to owner-OR-tenant standing, not a direct tenancy row
  only — same widened gate now used by `SetPrimaryHomeAction` itself).
- **API:** `GET /api/locations/comfort/?character_id=<id>` (`ComfortViewSet`) — personal comfort
  readout, tenure-gated; `GET /api/locations/portal-destinations/?character_id=<id>`
  (`PortalDestinationsViewSet`, #2222) — every portal-network anchor that character could
  travel to right now (list-only discovery; travel itself dispatches `travel_to` — see the
  Magic section's "Portal travel" entry)
- **Frontend:** `ComfortWidget` (`frontend/src/comfort/`) — silent unless something is biting
- **Integrates with:** areas (`AreaClosure` cascade walk), magic (resonance axis feeds Sanctum
  income, `world/magic/CLAUDE.md`), conditions (`DamageType` FK for the hazard-shelter axis),
  weather (`Climate` folds into exposure axes, `world/weather/CLAUDE.md`), items
  (`GarmentMitigation` feeds per-character comfort mitigation), mechanics (`CharacterModifier`
  comfort-mitigation targets), buildings (`place_decoration`/`RoomDecoration` write the AMENITY
  axis this app resolves; the bare `comfort_level()` this app exposes is what #2991's room-state
  `comfort_level` field surfaces in scenes — see the Buildings section's "Building purchase,
  priced decoration & the crafted-furniture seam" entry)
- **Source:** `src/world/locations/`
- **Details:** `src/world/locations/CLAUDE.md`

### Positioning (#530 + #1017 + #1018 + #2006 + #2209)
Room-anchored spatial graph: named position nodes, traversable edges, per-object
occupancy, capability-gated movement, GM terrain blueprints, a spatial tactical-map
UI (scene + combat), dynamic battlefield reshaping (aerial layer, chasms,
consequence effects for graph mutation and flight), and Rampart living barriers
(#2209 — a position-anchored entity with a shared integrity pool, see ADR-0125).

- **Models:** `Position` (`PositionKind` discriminator; `elevation_anchor` self-FK —
  the ground node an AERIAL or CHASM node is anchored to; `layout_x`/`layout_y`
  nullable-small-integer cosmetic tactical-map coordinates, #2006), `PositionEdge` (optional
  `gating_challenge` FK + `is_passable` + `blocks_flight`), `ObjectPosition` (OneToOne
  occupancy); **abstract bases** `PositionNodeBase` / `PositionEdgeBase` shared by live
  and blueprint layers; **blueprint models** `PositionBlueprint` (reusable GM-authored
  layout), `BlueprintPosition` (`layout_x`/`layout_y` too), `BlueprintEdge`;
  `RoomProfile.default_blueprint` FK (`evennia_extensions`) links a room to its
  preferred layout. **Rampart trio (#2209):** `Rampart` (`OneToOneField` → `Position`,
  `integrity`/`max_integrity`, `element_profile` FK, `crack_state` property),
  `RampartElementProfile` (authored Stone/Wind/Fire/Thorn rows, one `RampartSignature`
  behavior each), `RampartElementResistance` (per-damage-type resist/vulnerability row).
- **Key Services:** `create_position` / `remove_position` / `connect_positions` /
  `disconnect_positions` / `edge_between` / `place_in_position` /
  `move_to_position` (adjacency + passability + MOVEMENT capability + active-gating) /
  `force_move_to_position` / `position_of` / `reachable_positions` /
  `adjacent_open_positions` / `position_graph(room) -> PositionGraph` (full node+edge
  graph for the tactical map — keeps impassable/gated edges, unlike
  `room_position_adjacency`; #2006); **blueprint authoring** `create_blueprint` /
  `add_blueprint_position` / `connect_blueprint_positions` / `remove_blueprint`;
  **staging** `instantiate_blueprint(blueprint, room, *, replace=False)`;
  **aerial layer** `materialize_aerial_layer(room)` / `teardown_aerial_layer(room)` /
  `enter_aerial(objectdb)` / `leave_aerial(objectdb)`;
  **fall seam** `maybe_emit_fall(objectdb, position)` — emits `EventName.FELL` when entering a CHASM;
  **ramparts** `raise_rampart` / `rampart_at` / `damage_rampart` (shared mutation seam — also
  used by combat's WARD-Clash progress sync) / `expire_rampart_rounds` / `teardown_ramparts` (#2209)
- **Enums:** `PositionKind` (PRIMARY / FEATURE / ELEVATED / AERIAL / BARRIER_SIDE / CHASM);
  `PositionDestination` in `world/checks/constants.py`
  (ACTOR_POSITION / GATING_FAR_SIDE / NAMED / AWAY_FROM_ACTOR) — governs `MOVE_TO_POSITION`
  effect destination; AWAY_FROM_ACTOR is combat's knockback primitive (#1317)
- **Seed factory:** `AerialPropertyFactory` (`world/mechanics/factories.py`) — get-or-create
  factory for the `"aerial"` `Property` tag used to track airborne objects
- **Shared serializers** (`positioning/serializers.py`): `PositionSummarySerializer`,
  `PositionAdjacencyItemSerializer`, `PersonaPositionSerializer`, `PositionNodeSerializer`,
  `PositionEdgeSerializer` (the last two are the tactical-map node/edge shapes, #2006 —
  used by both combat and scenes layers; `PositionNodeSerializer` gained `rampart_element` /
  `rampart_integrity` / `rampart_max_integrity` / `rampart_crack_state`, all `None` when
  uncovered, #2209)
- **Actions:** `MoveToPositionAction` (`registry_key="move_to_position"`), `TakePositionAction`
  (`registry_key="take_position"` — voluntary PRIMARY/FEATURE entry for an UNPLACED actor,
  #2005), `GMPlaceInPositionAction` (`registry_key="gm_place_in_position"` — staff/scene-GM
  unchecked placement, #2005; surfaced to the web via the `_gm_place_in_position_actions`
  adapter and to telnet via `position/place`, #3385) + `SetTheStageAction`
  (`registry_key="set_the_stage"`, gated on `MinimumGMLevelPrerequisite(GMLevel.STARTING)`,
  staff bypass preserved, #2117)
- **Telnet:** `CmdPosition` (`position` / `position <name>` / `position/place <target>=<position
  name>`, #2005/#3385) — list/take/move face over `TakePositionAction`/`MoveToPositionAction`,
  room-scoped name resolution, plus a GM-only `place` switch dispatching
  `GMPlaceInPositionAction`; see [areas.md](areas.md) "Telnet" section. `CmdEncounter add`
  (`commands/encounter.py`) also gained an optional position token (#3385).
- **Scene API:** `SceneDetailSerializer` exposes `positions`, `position_adjacency`,
  `persona_positions`, and (#2006) `position_nodes`/`position_edges` — the full tactical-map
  graph for the scene's room, via `position_graph(obj.location)`
- **Combat API:** `EncounterDetailSerializer` exposes `position_nodes`/`position_edges`
  (same shape, via `position_graph(obj.room)`, #2006); `Participant.current_position` /
  `Opponent.current_position` (`PositionSummarySerializer | null`) locate each combatant
  directly on the row (combat doesn't use a `persona_positions`-style side list)
- **Frontend (#2006):** `TacticalMap` (shared read-only `@xyflow/react` canvas,
  `frontend/src/areas/components/`) + `SceneTacticalMap` (scene wrapper, replaces the old
  `RoomPositionsPanel`, `frontend/src/scenes/components/`) + `CombatTacticalMap` (combat
  wrapper — occupants from `current_position` not `persona_positions` — mounted as a "Map"
  tab in `CombatRail`'s right rail alongside "Your Turn"/`CombatTurnPanel` (#2197: `CombatRail`
  renders in-scene on `SceneDetailPage`'s `/scenes/:id`, not a dedicated route,
  `frontend/src/combat/components/`) + `MovementActions` (shared adjacent-position button
  list, `frontend/src/combat/components/`). `PositionMapNode` renders a covering Rampart as
  a colored ring (solid/dashed/pulsing-dashed by `crack_state`, #2209). `TacticalMap` gained
  an `onGMPlace` prop (#3385) — GM click-to-place, consumed after the #2206
  `onPickPosition` cast-targeting hook; `SceneTacticalMap`/`CombatTacticalMap` both grew a
  "Place" toggle + target picker over the room's co-located participants/opponents/personas
  when a `gm_place_in_position` `PlayerAction` is available.
- **Pattern:** Spatial obstacles reuse `mechanics.ChallengeInstance` — no parallel obstacle model;
  aerial edges mirror ground adjacency but are always passable/ungated (flight bypasses obstacles)
- **Reactive fall consumer (built — #1228):** `begin_plummet` / `advance_plummet` /
  `dispatch_catch` → `resolve_catch` (`plummet.py`) — STRICT danger round (#1466) + `Plummeting` +
  per-round descent/impact + capability-gated bystander catch
- **Gated blueprint edges (built — #1216):** `BlueprintEdge.gating_challenge_template` →
  `instantiate_blueprint` mints a live `ChallengeInstance` via `instantiate_challenge`
  (`world.mechanics.challenge_resolution`) on staging.
- **Integrates with:** combat (`CombatParticipant.current_position` / `CombatOpponent.current_position`;
  `add_opponent(..., position=...)` spawns an opponent already placed, #2005),
  mechanics (Challenge/gating + `ConsequenceEffect` reshape handlers),
  flows (`EventName.FELL` reactive seam),
  actions (`MoveToPositionAction` / `TakePositionAction` / `GMPlaceInPositionAction` /
  `SetTheStageAction`), commands (`CmdPosition`, #2005)
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
- **Integrates with:** locations (exposure axes + comfort cascade), areas (`Area.climate`, `RegionWeatherState.area`), game_clock (IC season/phase/month), codex (lore), battles (read-only `get_effective_weather(area)` via `Battle.region` to seed ambient weather; `Battle.weather_override`/`BattlePlace.weather_override` are battle-owned casts, not writes into `world.weather`, #1715 — see the "Battles" section)
- **Feast days:** `special_weather_for_today()` — on an `ic_month`/`ic_day` match the tick forces the feast's special `WeatherType` (Eclipse / Moon Madness) world-wide, overriding the climate-gated roll (the GM-lever automation)
- **Not yet wired:** re-seed-as-upsert for edited emits (loaddata duplicates keyless emit rows). Madness *mechanical* effects on characters are out of scope (Tehom)
- **Source:** `src/world/weather/` — see `world/weather/CLAUDE.md`
### Societies
Social structures, organizations, reputation, and legend tracking.

- **Models:** `Society`, `OrganizationType`, `Organization`, `OrganizationRank` (`can_resolve_appeals` #3293 — leader gate for appeal resolution; `can_declare_standing` #3290 — leader gate for standing declarations, alongside `can_invite`/`can_kick`/`can_manage_ranks`/`can_lead_rituals`), `OrganizationMembership`, `OrganizationMembershipOffer`, `OrganizationOffice` (#2239 — named portfolio: `slug`/`title`/`holder`/`feeds_check`), `OrganizationObligation` (#2428 — personal Golden Hare debt: `debtor` CharacterSheet → `creditor` Organization, `origin`/`state` TextChoices, never deleted; distinct from `currency.OrgObligation`'s org-to-org tithe/tax), `OrgAppeal` / `OrgAppealSignon` (#3293 — appeals to organizations: free-text IC ask, OPEN → GRANTED/DECLINED/WITHDRAWN, partial-unique one OPEN appeal per (org, petitioner); see ADR-0231 for the Appeal/Petition vocabulary split), `SocietyReputation`, `OrganizationReputation`, `StandingDeclaration` (#3290 — leader favor/disfavor audit row: `organization`/`target_persona`/`declared_by_persona` FKs, `direction` (`StandingDirection` FAVOR/DISFAVOR), `delta_applied`, `citation`, `game_week` FK (rate-limit key), `created_at`; unique per (organization, target_persona, game_week)), `LegendEntry`, `LegendSpread`, `LegendHonor` (#3466 — paid testimony that
  raises a deed's `base_value`), `LegendLevelCalibration` (#3466 — per-level honor Hare
  cost/value-added/title-threshold dials)
- **Office services** (`office_services.py`, #2239): `appoint_office` / `vacate_office` / `office_holder` / `holds_office`
- **Obligation services** (`obligation_services.py`, #2428): `settle_obligation(obligation, token)` (redeems the Hare via `currency.redeem_favor_token`, flips `OWED` → `SETTLED`, stamps `settled_at`/`settled_by_token`; raises `ObligationNotOwedError` if not `OWED`) / `has_open_obligation(sheet, org)` (read-only gate for training/entrance flows)
- **Standing declarations** (`standing_services.py`, #3290): `declare_standing(*, organization, target_persona, declared_by_persona, direction, citation)` — rank-gates on `can_declare_standing`, gates DISFAVOR through the #2170 antagonism-consent seam (the `hostile` `SocialConsentCategory`, the same one `world.secrets.services.accusation_permitted` consults for frame-job denounce), rate-limits to one declaration per (organization, target_persona) per IC `GameWeek`, applies the PLACEHOLDER `STANDING_DECLARATION_FAVOR_DELTA`/`STANDING_DECLARATION_DISFAVOR_DELTA` (`constants.py`) via the existing `bump_organization_reputation` (never a parallel writer), and mints the `StandingDeclaration` audit row. Typed errors: `NotAuthorizedToDeclareStandingError`, `InvalidStandingTargetError`, `StandingConsentBlockedError`, `StandingRateLimitedError`.
- **Appeal services** (`appeal_services.py`, #3293): `lodge_appeal` / `signon_appeal` / `resolve_appeal` (rank `can_resolve_appeals` or staff) / `withdraw_appeal` (petitioner-only) / `can_resolve_org_appeals(persona, organization)`
- **Enums:** `ReputationTier`, `OrganizationMembershipOffer.Kind`, `OrganizationMembershipOffer.Status`, `StandingDirection` (#3290 — FAVOR/DISFAVOR), `OrgAppealState` (OPEN/GRANTED/DECLINED/WITHDRAWN)
- **Key Services:** `ensure_default_rank_ladder`, `join_organization`, `leave_organization`, `invite_to_organization`, `apply_to_organization`, `accept_invitation`, `decline_invitation`, `accept_application`, `decline_application`, `promote_member`, `demote_member`, `expel_member`
- **Action Keys:** `org_invite`, `org_apply`, `org_join`, `org_leave`, `org_promote`, `org_demote`, `org_expel`, `declare_standing` (#3290 — direction kwarg picks FAVOR/DISFAVOR, shared by both telnet subverbs and the web dialog), `org_appeal_lodge`, `org_appeal_signon`, `org_appeal_resolve`, `org_appeal_withdraw` (#3293)
- **Telnet:** `org <subverb>` command (`favor`/`disfavor <person> in <org>=<citation>` added #3290); `appeal <org>=<title>/<body>` / `appeal list <org>` / `appeal signon <id>[=<note>]` / `appeal resolve <id>=grant|decline/<answer>` / `appeal withdraw <id>` (`CmdAppeal`, #3293); `accept org` / `decline org` offer responses
- **DRF:** `OrganizationViewSet` (`?name=` iexact filter), `OrganizationMembershipViewSet`, `OrganizationRankViewSet`, `OrganizationMembershipOfferViewSet` (+ `respond` detail action, #3412 — `POST /offers/{id}/respond/` accept/decline via the existing `membership_services` functions, no staff bypass, matching telnet's `accept org`/`decline org`), `OrganizationReputationViewSet`, `OrgAppealViewSet` (list/retrieve + `signon`/`resolve`/`withdraw` actions, member-gated: members + own appeals), `StandingDeclarationViewSet` (#3290 — public read, unlike the self-scoped reputation viewset; writes go through `declare_standing_action`, never a POST here), `DeedViewSet` (#3466 — public read of active `LegendEntry` rows + `honor` detail action, `POST /deeds/{id}/honor/`), `LegendEventViewSet` (#3466 — public read of `LegendEvent` rows + `establish` detail action, `POST /events/{id}/establish/`; both honor actions dispatch through `PerformRitualAction` against the seeded "Rite of Honors" ritual, never `honor_deed` directly) at `/api/societies/organizations/`, `/api/societies/memberships/`, `/api/societies/ranks/`, `/api/societies/offers/`, `/api/societies/reputations/` (self-scoped org standing, #1446), `/api/societies/standing-declarations/`, `/api/societies/appeals/`, `/api/societies/deeds/`, and `/api/societies/events/`
- **Principle Axes:** mercy, method, status, change, allegiance, power (-5 to +5)
- **Battle Legend (#3467):** `apply_battle_legend_awards` delegates to
  `world.battles.legend_settlement`. A battle prices from the beat it was fought over
  (`activate_stakes_for_battle` locks that contract), so the flat 25/12/15 constants are
  retired. ADR-0080 is preserved: a war's *stakes* stay un-scaled by who turned up,
  while each individual's *Legend* prices on their own `personal_risk` — different
  questions. A battle with no staked beat has no target level, hence no station, hence
  no advancement Legend. ADR-0122's curation survives (RESCUE/ROUT/BREACH, per-kind
  titles) and its standout stacking is preserved battle-side.
- **Mission Legend (#3468):** both mission Legend paths price through
  `world.missions.services.legend_pricing`. A mission is its own settled context —
  its template's `risk_tier` is the declaration and its `level_band_max` is the
  threat level, so no `StakeContractActivation` is consulted (which is what makes the
  deferred POST_CRON payout tractable, since the contract has long closed by cron
  time). `_grant_legend_points` is unsealed: a queued `LEGEND_POINTS` row now mints a
  priced solo deed stamped at station, and a row that prices to **zero** still flips
  `applied` — "correctly priced to nothing" is a settled outcome, not a fault.
- **Legend settlement (#3463, ADR-0249):** Legend is **settled at the end of a story
  unit**, never minted at the act. `world.societies.legend_settlement.settle_legend_for`
  is the single seam: per-person peril floor (risk priced against each earner's OWN
  level via `SettlementParticipant.personal_risk` — below the floor mints zero, not
  less), held-objective share, station stamp (`LegendEntry.earned_at_level` =
  `min(earner level, threat level)`), and a standout pass that pays brilliance even on
  a lost unit (ADR-0122 generalized past `Battle`). New models: `LegendContribution`
  (the ledger, written at the `perform_check` chokepoint; `success_level` is
  SERVER-ONLY), `RenownMagnitudeAward` and `LegendSettlementConfig` (authored tuning,
  with the Python constants demoted to fallbacks). `societies` stays the reusable
  primitive — consumers adapt into the seam (ADR-0010);
  `world.stories.services.legend_settlement` is the stakes-contract adapter and
  `world.scenes.beat_selectors` shares the scene→running-beat precedence chain with
  the #3433 risk badge. Station is stamped but NOT folded into `base_value`, and
  `station_multiplier()` is applied on read by `LegendRequirement`, so retuning never
  requires recomputing history and `CharacterLegendSummary` stays the tale-worth total.
- **Rite of Honors (#3466, ADR-0252, ADR-0253):** `world.societies.honors.honor_deed` —
  spend Golden Hares + write a public journal to raise a witnessed deed's `base_value`, or
  establish a fresh solo deed for an act settlement never credited. Clamped to
  `anchor_event.base_value - deed.base_value` (**ADR-0252**): peer judgment redistributes
  recognition inside an envelope the event already proved, never invents peril, so this does
  not reopen what ADR-0249 closed. Establishing refuses when the honoree already has an
  active deed anchored to that event (one deed per act, not one per honorer); a struck
  (`is_active=False`) deed proves nothing, counts toward no station max, and blocks nothing.
  Unrestricted by life-state (honoring the dead is by design). New models: `LegendHonor`
  (the paid testimony — deed/honorer/journal/Hares spent/value added/`established_deed`;
  story-significant, never hard-deleted, struck via the deed's own `is_active`),
  `LegendLevelCalibration` (per-level Hare cost/value-added/title-threshold dials; authored,
  deliberately-unguarded lookups). Dispatched by the seeded "Rite of Honors" `magic.Ritual`
  row (`SERVICE` kind, `hedge_accessible=False` — a Gifted rite) via both telnet
  (`commands.ritual.CmdRitual`, free-text grammar special-cased for this one ritual) and web
  (`DeedViewSet.honor` / `LegendEventViewSet.establish`, both converging on
  `PerformRitualAction`, never calling `honor_deed` directly). **Titles retarget to Persona
  in the same PR (ADR-0253):** see the Achievements section's `PersonaTitle` entry — a deed
  earned behind a mask titles the mask and can never surface on the character sheet.
- **Legend deed from crossing:** `LegendEntry.audere_majora_crossing` — reverse OneToOne to `AudereMajoraCrossing` (magic app); set when `cross_threshold` mints a deed via `fire_renown_award` + `_mint_crossing_deed`.
- **Scandal reach fork (#1464, ADR-0082):** `world/societies/scandal.py` —
  `route_deed_reach` runs at scene-deed birth (`create_solo_deed` /
  `create_legend_event`, both now taking `archetypes=`): scandal = archetype
  dot ≤ `SCANDAL_THRESHOLD` per society (`scandalous_societies`); private or
  successfully-contained scandalous acts mint an act-anchored contained
  `Secret` (blackmail material); public news/leaks set `societies_aware`,
  fire `apply_archetype_society_reputation`, and scale `spread_multiplier`
  by the involved personas' fame (`FAME_SPREAD_FACTORS`). Containment (#1824):
  a declared `WitnessApproach` (`WITNESS_APPROACHES` registry — intimidation /
  seduction / manipulation→Con-or-Deceive / bribery / household;
  `witness_approaches_for(character, household=)` is the one eligibility
  predicate; a declared bribery attempt tags the deed with the `bribery`
  CrimeKind), else the legacy auto-pick (Household Command for own-household
  witnesses, Con/Intimidation by stat). Act-time Stealth is wired:
  `concealed=True` on the deed services rolls `reduce_witnesses_by_stealth`
  (weakest link on group events; full success sheds all outsiders AND
  auto-contains via `fully_concealed`); a Stealth mission `ChallengeApproach`
  declares it (`ResolutionContext.chosen_approach` → `_legend_award`).
  Untagged deeds skip the fork.
- **`Organization`/`Society` as `NpcRegard` target (#1717):** either can now be the *target* (not
  holder) of a notable NPC's external opinion — see the Regard bullet in the NPC Services
  section above.
- **Integrates with:** realms (Society.realm FK), character_sheets (Persona for identity; `OrganizationObligation.debtor` FK, #2428), currency (`OrganizationObligation.settled_by_token` → `FavorTokenDetails`, string FK + `obligation_services.py` deferred-imports `redeem_favor_token`; FK direction societies→currency, ADR-0010 — currency never imports societies for this), magic (Audere Majora crossing deed via `AudereMajoraCrossing.legend_entry`), secrets (contained-scandal minting + exposure, #1464), justice (leaked crimes mint heat via the knowledge seam, #1765), actions (shared `action.run()` / `dispatch_player_action()` seam), battles (consumer — `world.battles.legend_wiring` calls `create_legend_event`/`create_solo_deed` from a battle-conclusion hook, win-gated Legend, #2184; FK direction battles→societies, ADR-0010 — this app never imports `world.battles`)
- **Source:** `src/world/societies/`
- **Details:** [societies.md](societies.md)

### Houses (#1884)
Noble/merchant/crime houses as first-class play — a house IS an `Organization`
(`family` FK → `roster.Family`) on the kinship graph (#2062, ADR-0098).

- **Models** (`world/societies/houses/`): `NobiliaryParticle`, `HouseRecognitionRule`, `FealtyEdge`, `SuccessionLaw`, `Title`, `Domain`, `HoldingKind`, `DomainHolding`, `DomainImprovementDetails`, `DomainCrisis`, `CrisisIntel`, `MarriagePact`, `PactCommitment`; plus `Organization.family` / `Organization.default_succession_law`
- **Enums:** `TitleTier`, `RecognitionRuleKind`, `SuccessionDerivation`, `SuccessionOrdering`, `PactCommitmentKind`, `PactDissolutionReason`, `DomainCrisisSeverity`
- **Family Kind (#3617):** `NobiliaryParticle.kind` / `HouseTemplate.kind` are FKs to
  `roster.FamilyKind` (replaces the retired `family_type` code list). Authoring recipes
  for family standing, subordination, patronage, and culture-specific facts through this
  layer: [family-authoring-recipes.md](family-authoring-recipes.md) (recipes 4-7 and 9
  use the houses layer); design record: ADR-0268, ADR-0269.
- **Key Services:** `full_display_name` (degree-aware particle naming, #3261) / `resolve_particle` / `sync_name_aliases` (derived-name telnet aliases), `recognize_birth` / `acknowledge_into_family`, `derive_succession_candidates` / `pass_title` / `register_gifted_power_rater`, `swear_fealty` / `vassals_of` / `liege_chain_of`, `sign_marriage_pact` / `dissolve_pact` / `handle_death_for_pacts` / `breach_commitment`, `create_domain` / `add_holding`, `start_domain_improvement` (+ `DOMAIN_IMPROVEMENT` `ProjectKind` handler), `is_org_leader` / `can_administer_domain` (#2239 — the in-play domain-management gate: leader OR `domain-steward` office), `sync_house_channel`; `house_feed_for` lives in `world/tidings/services.py`. **In-play surface (#2239):** the CG/seed-only `add_holding`/`start_domain_improvement` are now reachable via `actions/definitions/domains.py` (`add_domain_holding` / `start_domain_improvement` / `appoint_domain_office` / `vacate_domain_office`) + telnet `CmdDomain` (`domain <subverb>`)
- **Proclamations & edicts (#2842, ADR-0178):** `StanceArchetype` (sibling of `PhilosophicalArchetype` — positions, not deed-judgments) + `Proclamation` (issuer, optional org voice, stance, display-only prose, stored roll) in societies; `issue_proclamation` applies the renown dot-product per society with asymmetric roll scaling (support earned on success only; provocation mitigated by success, amplified on botch) — `world/societies/proclamations.py`. `EdictKind` (inherent stance + payload: income %, weekly unrest, upkeep) + `DomainEdict` (one active per domain) in houses; `enact_edict` proclaims the stance and persists the payload, read by `accrue_income_stream`, the weekly `edict_weekly_tick` rollover processor, spy `domain_report`, and the PROCLAMATION feed kind. Seeds: `proclamations` cluster (9 stances + 6 edict kinds). API: `/api/societies/proclamations/` (+`proclaim`, #3412 slice 3 — now dispatches through `IssueProclamationAction.run()`, `actions/definitions/organizations.py`, instead of calling the `proclamations` service functions directly; the offscreen-act gate (ADR-0246) now refuses a captured/unconscious/dead issuer before the service layer's own leadership/domain-authority checks ever run).
- **Threat/opportunity loop (#2837, ADR-0177):** `DomainCrisisType` gains `valence` (threat/opportunity) + `audience` (domain/org/criminal-org); `DomainCrisis` gains a nullable `org` leg (exactly-one-of), `surfaces_at` (generated crises spawn covert for `COVERT_WINDOW_DAYS`; hidden even from their target until surfaced or swept), and `CrisisIntel` (org × crisis early knowledge, minted by spy sweeps). `crisis_generation_tick` (weekly rollover processor) ambient-spawns per domain and per eligible org (active income streams or covert org type); opportunities expire after `OPPORTUNITY_LIFETIME_DAYS`; org-target threats skim stream accrual (`org_crisis_income_factor` in `accrue_income_stream`); MISSION options now actually mint (`choose_crisis_option` → `staff_assign_mission`); `apply_crisis_boon` pays seizure (owner: prosperity; anyone else: treasury coppers). Catalog seeded by the `crisis_types` cluster (`world/seeds/crisis_types.py`). Spy counterplay: `reveal_schemes` / `crisis_severity_delta` / `exploit_crisis` route payouts + `TaskTargetKind.CRISIS` (see tasking).
- **Civ-stats drive gameplay (#2238):** `Domain.income_multiplier` (prosperity / `DOMAIN_PROSPERITY_BASELINE`) scales a holding's gross in `currency.accrue_income_stream` — prosperity now drives income, not just display. `unrest_crisis_chance` / `maybe_open_unrest_crisis` roll a `DomainCrisis` when unrest is high (called from the weekly `domain_consumption_tick`). Unrest also skims food collection (`agriculture._apply_unrest_skim`) and a well-fed week recovers prosperity/unrest toward equilibrium (`agriculture` recovery drift). Still deferred (own PR): unrest→justice-heat *suppression* + crackdown loop (unrest makes a domain heat-safe until a crackdown spikes heat)
- **DRF:** `OrganizationSerializer.house` block + `/api/societies/organizations/{id}/feed/`
- **Web:** `/orgs/:id` house section + House Tidings; **Telnet:** `sheet/house`
- **House creator (Phase D, CG-only):** `HouseTemplate` + `HouseClaim`; gates in `houses/creator.py` (`submit_house_claim`, `approve_house_claim`, `materialize_house_claim` at CG finalization); admin review; `/api/character-creation/house-titles/` + draft `house-claim` action
- **The charter catalog is lore-repo content (#2875):** `SuccessionLaw`, `HoldingKind`, `HouseTemplate` and `HouseFeature` all carry `NaturalKeyMixin` (`name`) + `CreditedContent` and sit in `CONTENT_MODELS`, the same shape #2868 already gave `HouseAspectDefinition`/`HouseAspectOption` below. `world/seeds/houses.py` looks all four up via `authored_or_sample()` (#2875 Task 2) rather than inventing them with `get_or_create()`; the Crown organization and its Society (plain seeder-owned config, not `CONTENT_MODELS`) moved to `world.seeds.config_prerequisites._house_charter_anchors`, run before the content load so a content-repo row can FK them by name (ADR-0171). Authoring guide (what a charter holds, the Workbench/admin authoring path per ADR-0238, the liege/society code prerequisites, and what founding copies): "Authoring a realm's charter" in [houses.md](houses.md).
- **Regional flavor (#2079):** `HouseAspectDefinition`/`HouseAspectOption` (required catalog-only choices per template, ADR-0101), `HouseFeature` (slug-anchored cultural facts), `HouseClaimAspect` picks → `OrganizationAspect`/`OrganizationFeature` facets at materialization; `Organization.words/colors/sigil_description` stylings (all org types); `Domain.description` lands writeup. **The aspect catalog is lore-repo content (#2868)** — both aspect models carry `NaturalKeyMixin` and sit in `CONTENT_MODELS`; `HouseAspectOption.codex_entry` binds an option to its lore write-up (Inferna's House Quiddities), surfaced to CG as `codex_entry_id`
- **House Stature (#3091, ADR-0209/0210):** perceived-vs-true deterrence for landed orgs. Models: `StatureBand` (authored percentile tiers; `threat_multiplier` scales ambient predation; headline templates), `HouseStature` (components renown/military/economic/allied, `crisis_penalty`, true/perceived totals, band + trend, `prestige_rank`, stored realm rank), `StatureShift` (why-it-moved ledger → tidings), `PrestigeRankBand` (rank-relative benefits → prosperity drift), `OrgPrestigeRank` (unlanded orgs). Services in `stature_services.py`: `recompute_stature` (renown channels: members, head's COURT covenant, kin via `Kinsperson.gifted_rating`, union partners — marriage both-ways full, consorts half/senior-only/landed-title-gated/capped, paramours zero), `converge_perceived`, `apply_death_shock` (vitals seam), `apply_pact_shift`, `crisis_stature_shift` (covert threats hit perceived only after surfacing), `apply_whisper`, `assign_bands`/`assign_realm_ranks`/`recompute_org_prestige_ranks`, `apply_prestige_prosperity_drift` (zero-open-threats gate; ~3x income ceiling via prosperity clamp), `weekly_stature_tick` (rollover processor before crisis generation), `gifted_power_rating` (first live `MOST_POWERFUL_GIFTED` rater), `award_marriage_tier_prestige`. Six-step `TitleTier` (empire/kingdom/duchy/march/county/barony). Surfaces: org API `house.stature` panel, `domain stature` telnet, `FeedItemKind.STATURE` tidings, spy `_stature_lines` + `whisper_stature_delta` payout. Seeds: cluster `stature` (bands, rank bands, consort/paramour `UnionKind` rows — Luxen's non-recognition = no row)
- **Predator ecology (#3093, ADR-0211):** named NPC antagonists in `world/predators/` (thin dedicated models, never Organizations): `PredatorKind` (authored vocabulary), `PredatorBand` (strength/loot/prey/home region + `MenaceStage` ladder: rumors → lawlessness → robbery → raids → terror, ~10 weekly crons rumor→raid, advancing only while unanswered), `MenaceEvent` (tidings source), `AfflictionSign` (the dread week before an outbreak). Services: `weekly_menace_tick` (spawn/stalk/pressure/escalate; prey = weakest-perceived landed org honoring consort regional peace), `strike_band`/`sabotage_band` (counterplay: burn, knockdown, dormancy, disband; wired into `resolve_crisis` for attributed raids), `weekly_affliction_tick` (SIGNS → deterrence-blind outbreak → capped one-hop spread; `DomainCrisisType.ignores_stature`/`affliction_spreads`, `DomainCrisis.aggressor_band`/`spread_count`, `CrisisOrigin.PREDATOR`/`AFFLICTION`). Espionage: `TaskTargetKind.PREDATOR` + `scout_predator`/`sabotage_predator` payouts. `FeedItemKind.MENACE` tidings. Grand displays: `apply_grand_display` (event PROVISION quality → bounded upward perceived-stature bluff, seamed at `complete_event`). Seeds: cluster `predators`. Details: [predators.md](predators.md)
- **Org pacts & marriage-in-play (#2999, ADR-0212):** `PactKind` lever catalog + `OrgPact` (propose/ratify by leadership; income tithe mints `OrgObligation`; BETRAYAL is a stamped world event with a permanent prestige cost, auto-flagged when offensive spy tasks hit a pact partner), `Betrothal`/`BetrothalTerm` (25% stature preview; breaking costs standing), `solemnize_wedding` via the WEDDING `CeremonyTypeKey` (union + marriage pact + tier prestige in one rite — first in-play `record_union` caller; #2358 adds officiant-driven dual consent at ceremony start and `initiate_divorce` — unilateral, `Union.ended_at` + `PactDissolutionReason.DIVORCE`, both spouses' prestige hit, initiator steeper). Stature's allied slot reads ratified OrgPacts at their authored share. **Match dossier**: `dossier_services.build_dossier` + `GET .../organizations/{id}/dossier/` + `/orgs/:id/dossier` — any authenticated player; covert crises enriched only via the viewer org's `CrisisIntel`. Telnet `CmdPact`. Seeds: cluster `pacts`. Union membership reads the m2m through table (idmapper corrupts `prefetch_related` grouping — `_union_membership`)
- **Seeds:** cluster `houses` (rides `kinship`)
- **Integrates with:** roster kinship (recognition/succession read parentage; RESIDENCY writes `FamilyMembership`), currency (`OrgIncomeStream` holdings, `OrgObligation` subsidies, treasury dowries), projects (`DOMAIN_IMPROVEMENT`), areas (Domain decorates an Area), tidings (house feed), secrets (breach scandal channel)
- **Source:** `src/world/societies/houses/`
- **Details:** [houses.md](houses.md)

### Goals
Goal domain allocation and journal-based XP progression.

- **Models:** `CharacterGoal`, `GoalJournal`, `GoalRevision`
- **Goal Domains:** Stored as `ModifierTarget(category='goal')` in mechanics system
- **Six Domains:** Standing, Wealth, Knowledge, Mastery, Bonds, Needs
- **Write services:** `set_character_goals` (revision-gated replace) + `log_goal_progress` in `services.py`; `GoalError` user-safe exception in `types.py`
- **Action-backed (#1350, ADR-0001):** `set_character_goals` / `log_goal_progress` Actions wrap the services; web `CharacterGoalViewSet`/`GoalJournalViewSet` + telnet `CmdGoal` converge on `action.run()`
- **Web surface (#3045):** `GET /api/goals/my-goals/` and `POST /api/goals/journals/` had zero
  frontend callers until now — `GoalsPanel` (`frontend/src/goals/components/`), mounted on
  `XpKudosPage`, shows current goal allocations and a "Log Progress" dialog that awards the
  weekly-capped XP. No "current goals" display existed to extend (only the one-time
  character-creation allocator, `FinalTouchesStage`), so this is a small new component, not
  an extension of pre-existing UI. Goal *allocation* (`CharacterGoalViewSet.update_all`) is
  still telnet/CG-only — out of scope for #3045, which only closed the journal-log gap.
- **Integrates with:** progression (XP rewards), mechanics (goal domains use ModifierTarget), actions (write paths Action-backed)
- **Source:** `src/world/goals/`
- **Details:** [goals.md](goals.md)
### Journals
Character journal entries (public/private), praises, retorts, freeform tags, weekly XP.

- **Models:** `JournalEntry` (FK CharacterSheet author; self-FK parent for responses;
  `posthumous_override`/`revealed_at`/`revealed_by_settlement` #3287), `JournalTag`,
  `WeeklyJournalXP`, `JournalBequestGrant` (recipient_sheet/deceased_sheet FKs CharacterSheet,
  created_by_settlement FK estates.EstateSettlement, #3287)
- **Write services:** `create_journal_entry` / `create_journal_response` / `edit_journal_entry`; `JournalError` user-safe exception in `types.py`
- **Action-backed (#1350, ADR-0001):** `create_journal_entry` / `respond_to_journal` / `edit_journal_entry` / `set_journal_disposition` (#3287) Actions wrap the services; web `JournalEntryViewSet` + telnet `CmdJournal` (`journal write|respond|edit|disposition`) converge on `action.run()`
- **Web surface (#2160):** previously zero web frontend (telnet-only); now `/journals`
  (composer, public feed, own-entries tab) plus a `JournalTab` quick-compose panel in the
  in-scene sidebar. `/journal` (singular) was freed from the missions ledger, which moved to
  `/missions/journal` in the same PR — see Missions below and `journals/AGENT_GLOSSARY.md`'s
  disambiguation entry for the "journal" homonym across apps.
- **Integrates with:** progression (weekly XP awards), achievements (`journals.total_written`/`total_public` stats), threads (`JournalEntry.related_threads` M2M), estates (posthumous reveal + writings bequest, #3287)
- **Account block/mute (#2996):** the public feed excludes an account-level-blocked account's
  entries both directions, and an account-level-muted account's entries from the muter's own
  feed only (`services.exclude_blocked_and_muted_authors`); a praise/retort response between a
  blocked pair is rejected with a neutral shared failure, a muted pair's response persists but
  is hidden from the entry author's own read only — see `world/scenes/CLAUDE.md`'s Block/Mute
  entries and ADR-0204
- **Posthumous afterlife (#3287, ADR-0229):** a `CharacterSheet.posthumous_journal_disposition`
  (REVEAL default / SEAL) plus a per-entry `JournalEntry.posthumous_override`
  (INHERIT default / REVEAL / SEAL) decide what happens to a character's private entries at
  death. `services.reveal_journals_for_settlement` and `services.grant_journal_bequest` are
  called explicitly from `estates.services.execute_settlement` (no signals) — the reveal always
  runs; the grant only when the will carries a `BequestKind.WRITINGS` line. SEAL always wins,
  even over a bequest grant (enforced at the read path via `services.sealed_effective_q` /
  `entry_visible_via_bequest`, never by excluding sealed rows from the grant itself). Read
  paths: the public feed includes `revealed_at`-stamped entries (`is_public` is never mutated
  by a reveal); a bequest recipient browses the deceased's non-sealed private corpus via
  `GET /api/journals/entries/?deceased=<sheet_id>`; `GET/PATCH /api/journals/entries/disposition/`
  reads/sets the caller's sheet-level default.
- **Source:** `src/world/journals/` (no dedicated `docs/systems/journals.md`; see the app's
  `CLAUDE.md` and `AGENT_GLOSSARY.md`)
### Action Points
Time/effort resource economy with regeneration via cron. The most complete gate pattern in the codebase.

- **Models:** `ActionPointConfig`, `ActionPointPool`
- **Key Methods:**
  - `ActionPointPool.get_or_create_for_character(character)` — safe accessor
  - `pool.can_afford(amount) -> bool` — check before spending
  - `pool.spend(amount) -> bool` — atomic via `select_for_update`
  - `pool.unbank(amount) -> int`, `pool.consume_banked(amount) -> bool` (no `bank()` — removed
    as dead code; `banked` only accrues via the codex teaching flow)
  - `pool.get_effective_maximum() -> int` — base + distinction modifiers
  - `pool.apply_daily_regen()`, `pool.apply_weekly_regen()`
- **Pattern:** Fully integrated with mechanics modifier system via `get_modifier_total(sheet, modifier_target)` for regen rates and pool max. Uses `select_for_update` for race-condition safety.
- **Surfaces:** `GET /api/action-points/{character_id}/` (`ActionPointPoolView`) — self-scoped
  read `{current, effective_maximum, banked}` for the web Status tab + `sheet/status` telnet
  section; `current` is the authoritative weekly-remaining figure (#1446)
- **Integrates with:** codex (teaching costs AP), mechanics (AP modifiers from distinctions), cron (daily/weekly regeneration)
- **Source:** `src/world/action_points/`
- **Details:** [action_points.md](action_points.md)

### Codex
Lore storage and character knowledge tracking.

- **Models:** `CodexCategory`, `CodexSubject`, `CodexEntry`, `CharacterCodexKnowledge`
- **Key Methods:** Character learning from starting choices or teaching
- **Visibility (ADR-0221):** entries are the only unit of secrecy; categories/subjects
  with no visible entry in their subtree are hidden by every endpoint. Reader knowledge
  is the union across the account's characters (`?character=` narrows; `known_by`
  per-character breakdown in entry payloads) — `CodexVisibilityMixin` in
  `world/codex/views.py`; the account's knowledge map is `Account.cached_codex_knowledge`
  (#3597), cleared on every knowledge write, so the mixin holds no per-request state
- **Art (#2408):** `CodexEntry.art` — nullable FK → `evennia_extensions.Media`,
  `SET_NULL`; illustration rendered in the codex-modal lore-card (`CodexModal.tsx`).
  No art set falls back to the existing placeholder convention.
- **Integrates with:** action_points (teaching costs), consent (visibility), character_creation (starting knowledge), evennia_extensions (`Media`, art)
- **Source:** `src/world/codex/`
- **Details:** [codex.md](codex.md)

### Investigation & Discovery
The mystery core loop: a clue points at something worth finding (codex entry, mission, a
held captive to rescue, a character secret, or a masked identity); players acquire clues by
**searching** a room, via passive **triggers**, or by an NPC **revealing** one (#3428), then
resolve them automatically or through a collaborative **research project**.

- **Models:** `Clue` (DiscriminatorMixin — `target_kind` ∈ CODEX / MISSION / RESCUE / SECRET /
  PERSONA_LINK / ITEM + a per-kind FK; never exists without a target. PERSONA_LINK (#2120) is
  the documented multi-discriminator exception: `target_persona` + `target_persona_linked`, both
  FKs → `scenes.Persona`, required together. ITEM (#2540 exact-pointer ruling) is a second such
  exception: `target_item_template` (required, FK → `items.ItemTemplate`) + optional
  `target_item_instance` (FK → `items.ItemInstance`, must match the template's instance when
  both set) — template-only means "any of this kind", instance-pinned means "this exact one".
  ITEM has no "already known"/AUTOMATIC-grant concept; the held `CharacterClue` row IS the
  knowledge, read by `scenes.boon_services.character_has_item_pointer`. Also carries a
  `NaturalKeyMixin` `slug`
  (#2451) and is a `CONTENT_MODELS` citizen — a `Clue` now exports/imports as
  lore-repo content, natural-keyed by slug), `CharacterClue` (held-clue, roster-scoped),
  `RoomClue` (search-anchored placement + `detect_difficulty` + `eligibility_rule` +
  `fixture_key`), `ClueTrigger` (passive on-entry placement + `eligibility_rule` +
  `fixture_key`), `ResearchProjectDetails`
  (the clue a `ProjectKind.RESEARCH` project researches toward)
- **Staff authoring (#2451, epic #2436 slice 4):** `RoomClue`/`ClueTrigger` both carry
  a nullable-unique `fixture_key` (same pattern as `RoomProfile.fixture_key`),
  set when placed from the staff world-builder canvas. `staff_place_clue`/
  `staff_remove_clue`/`staff_place_clue_trigger`/`staff_remove_clue_trigger`
  (`src/actions/definitions/world_builder.py`, `category="world_builder"`,
  `StaffOnlyPrerequisite`-gated) place/hard-delete these rows; the grid bundle
  format gains `clues`/`clue_triggers` sidecar sections (keyed by `fixture_key`,
  referencing rooms by their `fixture_key` and the clue by its `slug`), upserted
  by `grid_import.load_grid_bundles()`'s 5th pass and report-never-deleted when a
  fixture-keyed row is absent from a reimported bundle.
- **Authoring the clue itself (#3432):** `author_clue`
  (`src/actions/definitions/world_builder.py`, `category="world_builder"`,
  `MinimumGMLevelPrerequisite(GMLevel.SENIOR)` — staff bypass built in) mints the `Clue`
  row (name/description/target_kind/target ids; `slug` generated + uniquified), closing the
  admin-only gap the staff-authoring canvas above left. **SECRET-target clues are
  additionally staff-only** (no GM-scoped secrets listing exists yet) — canon-creating
  surfaces gate hard by owner ruling; see the system doc's "Authoring the clue itself"
  section. Frontend: the shared `AuthorClueDialog`
  (`frontend/src/clues/components/`), reached from `PlaceClueDialog`'s "New clue…" and
  `StaffSecretsPanel`'s "Author a clue to this secret".
- **Key functions (`world/clues/services.py`, `research.py`):** `acquire_clue`,
  `target_already_known`, `clue_target_kind_allowed(account, target_kind)`
  (#3566 - the clue-authoring policy as one callable: staff → anything,
  SENIOR+ GM required otherwise, SECRET staff-only; shared by `author_clue`
  and the stake reward-line CLUE-sink gate), `search_room` (Search check per hidden clue), `grant_clue_target`
  (AUTOMATIC resolution — codex KNOWN / rescue mission / secret fact / persona-link
  `PersonaDiscovery` via `_grant_persona_link_target`, #2120 — the only in-game
  `PersonaDiscovery` producer; mask piercing stays GM-authored per ADR-0033), `maybe_grant_clue_triggers`
  (on room entry), `plant_rescue_clue` / `clear_rescue_clues` (#931), `start_research_project`
  / `contribute_research` (floored CHECK→progress) / `resolve_research` (RESEARCH handler —
  CODEX/SECRET/MISSION targets grant to every distinct contributor; MISSION grants via
  `staff_assign_mission`, log-and-continue per contributor, #3429)
- **Action:** `SearchAction` (`actions/definitions/investigation.py`) — AP + mental fatigue
  via the declarative cost on the `Action` base; rolls the seeded "Search" CheckType
- **NPC reveal (#3428):** `npc_services.OfferKind.CLUE_REVEAL` +
  `ClueRevealOfferDetails` — a role-anchored acquisition surface parallel to Search/triggers;
  see the "NPC Services" system entry above and `docs/systems/npc-lifecycle.md` for the
  interaction-loop side, and `investigation_and_discovery.md`'s "Acquisition surfaces"
  section for how it composes with `acquire_clue` / `grant_clue_target`.
- **Two-layer gating:** the detect (skill) check *and* an `eligibility_rule` predicate on
  each placement (access layer; empty rule = open to anyone)
- **Read surface (#1575):** `GET /api/clues/held/?character_sheet=<id>` (`MyHeldCluesView`,
  `HeldClueSerializer`) — the held-clue *journal*, scoped to characters the requester plays
  (`for_account`; no cross-player leak). Web `CluesTab` on `CharacterSheetPage` (own character
  only). A telnet `sheet/clues` section + active-research "pursuit" tracking are follow-ups.
- **GM search surface (#3566):** `GET /api/clues/search/?q=` (`ClueSearchView`,
  `IsAuthenticated` + `IsGMOrStaff`) - a small picker endpoint for the stake
  reward-line editor's CLUE sink, not a general clue browser. Filters to
  `RESOLVABLE_CLUE_TARGET_KINDS`, then policy-filters each row through
  `clue_target_kind_allowed` for the requester; returns at most 25
  `{id, name, target_kind}` rows (`ClueSearchResultSerializer`).
- **Integrates with:** codex (codex-target grant via `add_progress`), missions
  (`grant_rescue_mission` for RESCUE's AUTOMATIC mission target; `staff_assign_mission`
  for a RESEARCH-resolved MISSION target, #3429), projects (RESEARCH kind), captivity
  (RESCUE clues planted on capture / cleared on resolution), predicates (eligibility),
  checks (`perform_check`), actions (search), narrative (trigger notification + RESEARCH
  MISSION-grant story text), typeclasses (`Character.at_post_move` trigger hook)
- **Source:** `src/world/clues/`
- **Details:** [investigation_and_discovery.md](investigation_and_discovery.md)

### Secrets (#1334)
Hidden facts about a character — cover identities, crimes, private distinctions, secret
relationships. The privacy layer for the mystery loop: **bio/story stay public**, sensitive
info is *relocated* into Secrets that must be earned and shared. A Secret is the missing 4th
primitive alongside Distinction / Condition / Resonance. *Slices 1–3 (content model, discovery,
secret-tab display) + the #1269 distinction migration + the **act-anchor cross-link** (#1573 —
`legend_deed`/`mission_deed`/`scene`, one act = one secret) + the **blackmail → leverage loop**
(#1680) are built; action-anchored minting and the PersonaDiscovery subsumption are later slices.*

- **Models:** `Secret` (subject-anchored to a `CharacterSheet`, which **owns** it — single-owner,
  no shared/group rows; `level` 1–4 / `category` FK / `consequences` — each may be Unknown;
  `provenance` ∈ GM / action / player-flavor; `author_persona` for OOC attribution;
  `subject_item_template`/`subject_item_instance`, nullable FKs → `items.ItemTemplate`/
  `ItemInstance` — #2540 exact-pointer ruling, an optional "this secret is about an item"
  pointer, same shape as `Clue`'s ITEM target; dependency stays specific→general per
  ADR-0010, `secrets` points items-ward, never the reverse),
  `SecretCategory` (staff-editable lookup; null category = Unknown), `SecretKnowledge`
  (roster-scoped held record with partial-knowledge layers — fact / `knows_category` /
  `knows_consequences`, monotonic; tracks *others* learning a secret),
  `Leverage` (#1680 — standing coercive hold `holder_sheet → subject_sheet`, `founded_on` a
  `Secret`; minted by a successful Blackmail)
- **Blackmail → leverage loop (#1680):** the `Blackmail` social action (register-gated by a
  `blackmail` `SocialConsentCategory` at `FRIENDS_WHITELIST` default, resolved by the defender's
  plausibility band, ammo = a `SecretKnowledge` you hold about the target) mints `Leverage`.
  Spend it two ways: **`coerce`** (`CoerceAssetAction`) extracts an un-played NPC as a
  `COERCION` `NPCAsset` of a chosen kind (a played/piloted target keeps agency — routed back to
  the register); **`reveal_secret`** (`reveal_leveraged_secret`) exposes the secret to the
  subject's societies and spends the leverage. Services in `world/secrets/services.py`
  (`mint_leverage` / `has_leverage` / `character_knows_secret` / `reveal_leveraged_secret`) +
  `world/assets/services.py` (`coerce_into_asset`).
- **Invariant:** anchor-scales-with-level — only Level-1 player-flavor may be free-authored
  (it carries no mechanical effect, so its truth is moot); heavier secrets must be GM- or
  action-anchored, so player flavor can never masquerade as canon (`Secret.clean`)
- **Key functions (`world/secrets/services.py`):** `author_secret`, `author_player_flavor_secret`,
  `grant_secret_knowledge`, `secret_known_to`, `set_secret_act_anchor` /  `secrets_explaining`
  (the act-anchor cross-link both directions, #1573)
- **Frame-jobs / accusations (#1825, ADR-0114):** `SecretProvenance.ACCUSATION` — a
  player-authored false scandal about *someone else*, exempt from the player-flavor caps so it
  carries weight + mints heat/reputation like a true scandal (falsity emergent). `mint_accusation`
  (thin over `author_secret`) + `accusation_permitted` (consent gate: the target's `hostile`
  category, #2170; NPC always frameable). `MintAccusationAction` (key `mint_accusation`), telnet
  `accuse <char> = <claim>` (`commands/social/accusations.py`). A *criminal* accusation bridges
  into pursuit heat justice-side via `AccusationCrimeClaim` + `file_criminal_accusation`
  (see Justice, #1825) — wild L2 (named crime, no real deed → easily refuted) vs L3 frame
  (a real deed pinned on someone who didn't do it → robust)
- **Counter-play, secrets side (#1825):** `gossip.plant_smear` (one-move L1 smear:
  Gossip roll gates mint + heat seed + counter-clue; `SmearAction`, `gossip smear`),
  `gossip.refute_accusation` + `AccusationRebuttal` (the consentless defense — partial
  compensating reversal; `RefuteAccusationAction`, `accuse/refute`),
  `reverse_secret_exposure` (the shared compensating-bump seam; full reversal =
  justice's nullification), public `hub_region_for`/`societies_for_region` seams.
  The evidence/frame/nullify/denounce/case-file machinery is justice-side (see Justice)
- **Discovery:** secrets are a `Clue` `target_kind` (`SECRET` + `target_secret` FK) — found
  through the same Search / `acquire_clue` loop; `grant_clue_target` teaches the fact
- **Staff authoring (#3266):** `AuthoredSecretViewSet` at `/api/secrets/authored/`
  (`IsAdminUser`, no player IC scope): list (`?subject=` required), create, patch, and a
  `categories` action; no delete (secrets are story data). `AuthoredSecretSerializer` fixes
  provenance server-side (`GM_AUTHORED` + `author_persona=None`) and exposes `author_secret`'s
  `subject_aware` kwarg; `SecretVictim`/`archetypes` (reputation) stay admin-only, off the API.
  Frontend: `StaffSecretsPanel` + `AuthorSecretDialog`, staff-only-mounted on
  `CharacterSheetPage`.
- **Codex boundary:** cut on *authorship* — Codex = canon lore (lore-authority, reviewed);
  Secret = self-serve hidden fact about a concrete entity
- **Source:** `src/world/secrets/`
- **Details:** [secrets.md](secrets.md)

### Justice (#1765)
Local law + persona pursuit heat: how actively local forces hunt a *persona* in an *area* —
distinct from `SocietyReputation` (regard). Laws are per-area data rows resolving
most-specific-wins up the `Area` tree; knowledge propagation is the accrual engine
(hot where the deed is *known*, falloff emergent); jurisdiction scopes minting and
reading to the enforcing society's dominion (ADR-0080 — sanctuary and cross-border
immunity are the same mismatch rule). Masks (TEMPORARY personas) deliberately soak
heat; identity-association copies it (`associate_heat` — the #1334 outing seam).
Lifecycle (#1826, `justice/lifecycle.py`): **lie low** (`LieLowState` — declared
go-to-ground: ×`LIE_LOW_DECAY_MULT` decay in the area + CRIME_KICKUP collection
malus for member orgs; broken by any IC action there — interaction or fresh heat);
**bribe** (`attempt_bribe` — coin sink scaled by heat, `perform_check`-banded;
botch mints a `bribery` crime); **pardon** (`pardon_persona` — magistrate office
or org leadership of the enforcing society; `PardonGrant` audit + public feed
item); **wanted visibility** (`wanted_rows_for_area` — at/above
`WANTED_VALUE_FLOOR` the warrant flips public: tier + presented name + crime
kinds, never numbers; `GET /api/justice/wanted/` also carries the area's
awaiting-trial `held` list — public record, the help-the-accused discovery
seam — and `viewer_can_pardon` for the lord's-grant control gate; the room
hub payload (`_get_hub`, flows room_state serializer) exposes `area_id` so
the frontend `WantedBoard` renders at notice boards/criers, and `CrimeTab`
shows the captive's own case + stand-trial control via `GET
/api/justice/my-case/`).
Pipeline (#2378, `justice/pipeline.py`): guard pressure is **event-driven rolls
against active public play** — the trigger ladder (`maybe_guard_encounter`) fires
on NPC transactions at wanted, any public interaction at hunted, room arrival at
max (hooks: `dispatch_offer_effect`, the interaction seam, `Character.at_post_move`;
never offline, never private rooms). Evasion check → escape / seen (+heat) /
captured (`resolve_guard_encounter`); capture brigs via captivity and opens a
`JusticeCase`. **The trial waits on the captive** (`initiate_trial` — argument
checks by accused + helpers, nobody prosecutes); helpers can only help
(`submit_exculpatory` — threshold releases outright; manufactured evidence
exposed backfires on the SUBMITTER). Sentences scale with prosecution weight
(fine/brig/humiliation/exile), a society's `SentenceLadderRung` can override the
kind on repeat offenses (`ARENA_TRIAL` seeded but INERT pending the combat
substrate); **the lethal wall holds** (ADR-0023):
`PlayerData.lethal_consequences_opt_in` + an exhausted case (`failed_outs`)
gate PC execution — NPCs may hang; a non-opted PC's terminal instead lands
BANISHMENT, the non-lethal terminal ADR-0233 adds (amends ADR-0023's scope
note, doesn't supersede it).

**Sentence enforcement (#2378, `justice/sentences.py`):** `schedule_sentence`
dispatches a TRIED case's verdict to its enforcement path; `sentence_sweep_tick`
is the daily cron (`justice.sentence_sweep`) that serves matured BRIG_TERM
releases and carries out (or voids, on rescue/pardon) due terminal sentences.
EXILE mints an `ExileDecree` + floors/holds heat at `pin_heat_for_decree`
(shared with terminal BANISHMENT) and ejects to `Area.exile_destination`
(`eject`, null-safe); returning under an active decree mints its own
`breach-of-exile` CrimeKind heat (`pipeline._mint_breach_heat`) and forces a
near-auto-botch evasion roll unless magically concealed (`is_magically_concealed`
— seam, always False today, TehomCD's detection substrate). CONFISCATION seizes
carried goods into the area's Brig room (`room_features.brig_services
.find_brig_for_area`/`brig_has_capacity` — also the capture-time custody route,
promoted from #1862) or falls back to a double-rate fine. HUMILIATION applies a
clamped deed-prestige hit (`apply_humiliation`, mechanics-only — Apostate authors
the real copy), persisted onto `JusticeCase.humiliation_prestige_hit`. **Two-layered
humiliation (#2378 follow-up, ADR-0235):** a PERMANENT physical brand
(`mint_humiliation_brand` — documented no-op seam, scar substrate, TehomCD's
domain) atop a TEMPORARY reputational layer (the prestige hit + a persona-scoped
examine/profile explanation, `active_humiliation_mark` → `PersonaSerializer
.humiliation_mark`) that fades at `HUMILIATION_TERM_DAYS`, restored by
`sentence_sweep_tick`'s `_sweep_humiliation_restores` leg (ADR-0081 "automatic
gain" nuance addressed in ADR-0235 — it's a reversal of the sweep's own earlier
automatic loss, not new value). `active_public_marks(area)` derives the wanted
board's public record (no stored row) from live humiliations/decrees/pending
terminals, surfaced on `GET /api/justice/wanted/`'s `records` field and `GET
/api/justice/my-case/`'s sentence/countdown fields; a sentenced verdict also
fires a `tidings` VERDICT feed item. `justice/notifications.py`:
`notify_verdict`/`notify_verdict_safely` deliver a verdict/carried-out/voided
notice (three DISTINCT bodies — a voided terminal never re-sends
sentence-affirming copy) to the case's reachable audience (accused + exculpatory
submitters — accusers/victims deliberately out of scope, ratified #2378
follow-up: broader reach lives in the area-scoped public record instead, never a
direct push); `notify_brig_visitation` OOC-adverts a served brig term to the
accused's active friends. Public records are permanent IC history — removed
only via pardon/exoneration (ratified #2378 follow-up, ADR-0235).

- **Models:** `CrimeKind` (normalized vocabulary; **content rule: no sexual crimes,
  ever**), `AreaLaw` (`heat_weight` posture + `exempts`), `DeedCrimeTag`
  (→ `LegendEntry`), `PersonaHeat` (persona × area × enforcing society;
  `pinned_until` — decay-exempt exile-pin hold, #2378), `HeatSource`
  (allegation provenance — false accusations are emergent, never flagged),
  `AccusationCrimeClaim` (→ `secrets.Secret` — the frame-job→heat bridge; `real_deed`
  null = wild L2, set = L3 frame for a real crime; `retracted_at` set by
  nullification, #1825), `CrimeEvidence` (physical evidence a crime-tagged deed
  left at its scene; → `items.ItemInstance` when gathered; states
  AT_SCENE→GATHERED→TAMPERING→OFF_GRID→PRODUCED/DISPOSED), `FrameJobDetails`
  (FRAME_JOB Project payload), `AccusationNullification` (proven-fabrication
  record + the authorship secret), `DenounceRecord` (once-only backfire guard),
  `ExileDecree` (persona × area × society banishment; `ends_at` null = permanent,
  #2378), `SentenceLadderRung` (per-society escalation step keyed on
  `(society, level)`, matched against `failed_outs - 1`, #2378); `JusticeCase`
  gains `sentence_ends_at`/`terminal_due_at`/`terminal_carried_out_at` (#2378) and
  `humiliation_prestige_hit` (#2378 follow-up — the exact restorable hit);
  `areas.Area` gains `exile_destination` (RoomProfile the banished are ejected to,
  #2378)
- **Key functions (`world/justice/services.py`):** `law_for`, `enforcing_society_for`,
  `accrue_heat`, `accrue_for_deed_knowledge` (evidence-disposal dampener), `heat_for`,
  `associate_heat`, `tag_deed_crimes` (+ evidence generation), `heat_decay_tick`
  (daily cron); accusation bridge (#1825): `record_accusation_crime`,
  `accrue_accusation_heat` (skips retracted claims), `file_criminal_accusation`
  (composes `secrets.mint_accusation` + claim + heat — justice→secrets, ADR-0010);
  counter-play (#1825): `evidence.generate_crime_evidence`/`gather_evidence`/
  `dispose_evidence`, `frame_jobs.start_frame_job`/`resolve_frame_job` (FRAME_JOB
  handler), `nullification.nullify_accusation`, `denounce.denounce_framer`,
  `case_file.has_local_authority`/`produce_case_evidence`/`examine_evidence`;
  sentence enforcement (`justice/sentences.py`, #2378): `schedule_sentence`,
  `sentence_sweep_tick`, `apply_exile`, `apply_confiscation`, `apply_humiliation`,
  `mint_humiliation_brand` (no-op seam, #2378 follow-up), `active_public_marks`,
  `active_humiliation_mark` (persona-scoped sibling, #2378 follow-up),
  `terminal_kind_for`, `pin_heat_for_decree`, `eject`, `is_magically_concealed`;
  seeds: `seeds.seed_placeholder_sentence_ladders`
  (Umbros/Inferna placeholder rungs, skips gracefully when a society is absent)
- **Writers:** deed-knowledge seam (`grant_deed_knowledge(room=…)`); mission report
  CRIME_WATCH sink (`missions.integrations.crime_watch.flag_crime` + the
  MOSTLY_ACCURATE dodge + masked-report association chance)
- **Surfaces (self-only):** room-desc tier line + `heat` on the room-state payload;
  safe-now relief line on movement; `sheet/crime` + web Crime tab over
  `GET /api/justice/heat/` (tiers only, never raw values; `PersonaHeatSerializer`
  also carries `society` id for the web Reputation tab's client-side join, #1446);
  public standing (#2378): the wanted board's `records` field (`PublicMarkSerializer`)
  and `GET /api/justice/my-case/` (`MyCaseSerializer` — `sentence_kind`,
  `sentence_amount`, `sentence_ends_at`, `terminal_due_at`, `failed_outs`) plus web
  sentence-countdown UI on the character sheet's Crime tab; examine/profile
  (#2378 follow-up): `PersonaViewSet`'s `PersonaSerializer.humiliation_mark`
  (`HumiliationMarkSerializer` — `kind`/`until`/neutral `explanation`), None once
  the term passes. Fix
  round (#2378 Task 7): `scenes` serializer identity leaks closed —
  `endorsee_sheet_id` and `dramatic_moment_tags`' sheet ids now gate behind the same
  reveal predicate as the rest of a masked persona's identity, so a disguised
  persona can no longer be unmasked through those two fields.
- **Source:** `src/world/justice/`
- **Details:** [justice.md](justice.md)

### Tidings / Public-reaction feed (#1450)
The pull/browse vector of the public-reaction "contextual center" (#1446) — recent public events
scoped to what a viewer's persona would have heard. **Modelless and greenfield-light:** there is no
feed table; the service aggregates two awareness M2Ms other apps already own.

- **No models.** `world.tidings` is a service + API app (no migrations).
- **Birthday digest (#2756):** `_birthday_items()` is a crier-scope-only source folded into
  `hub_feed_for_room` — upcoming celebrated birthdays (next 3 IC weeks) of Active-roster,
  alive, non-dormant characters, as `FeedItemKind.BIRTHDAY` rows. Merge-on-read like every
  other source. The enum also gained `PARDON`/`CRISIS` (fix-on-sight: those emitters
  previously bypassed the serializer's choices).
- **Key functions (`world/tidings/services.py`):** `public_feed_for_societies(society_ids, *,
  limit)` is the core read; `public_feed_for(persona, *, limit)` (viewer scope: union of
  `SocietyReputation` societies + `OrganizationMembership` orgs' societies) and
  `hub_feed_for_room(room, *, limit)` (civic-hub scope: `societies_for_area` ancestor walk) both
  delegate to it. Returns `PublicFeedItem` dataclasses (`kind` / `headline` / `subject` /
  `occurred_at` / `category`), newest first. Merges **deeds** (`societies.LegendEntry` filtered by
  `societies_aware`) + **scandals** (`secrets.Secret` filtered by `societies_exposed`). `category`
  is the authored scandal-category label — the first attached archetype named `*Scandal` (#1806).
- **Faces:** web `/api/tidings/feed/?viewer=<RosterEntry pk>` (`PublicFeedView`) → React `/tidings`
  page (`TidingsFeed`); telnet `tidings` / `tidings local` (`CmdTidings`). All converge on the one
  service. (Named *tidings*, not `gossip`/`news`: `gossip` is reserved for level-1-secret access,
  `news` for OOC game news; criers are NPCs.)
- **Civic-hub reader (#1450 final slice):** rooms carrying a `NOTICE_BOARD` or `TOWN_CRIER`
  `RoomFeatureKind` (see Room Features; `active_hub_feature(room_profile)` is the gate) surface the
  local slice: arrival echo of the two freshest items (`Room._echo_hub_tidings`), telnet
  `tidings local`, and a `hub` block on the `room_state` payload (`_get_hub` in
  `flows/service_functions/serializers/room_state.py`) rendered by the web `HubTidingsPanel`.
  Installing a Town Crier places a "Town Crier" `Functionary` in the room
  (`handle_town_crier_progression` → `place_functionary`). Kinds + the crier `NPCRole` seed via
  the `civic_hubs` cluster (`world/seeds/clusters.py`).
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
  `SocialConsentCategory` (NaturalKey on `key`; forms a **tree** via `parent` self-FK, #2170 —
  a category with no player rule inherits its parent up to the root's `default_mode`, so
  `default_mode` is consulted only on a root; `ancestor_chain()` returns `[leaf, …, root]`),
  `SocialConsentPreference` (OneToOne on tenure),
  `SocialConsentCategoryRule` (preference + category + ConsentMode), `SocialConsentWhitelist`
  (owner_tenure / allowed_tenure / category), `SocialConsentBlacklist` (#1698 —
  owner_tenure / blocked_tenure / category; consulted under `ALL_BUT_BLACKLIST`)
- **ConsentMode (#1698):** `EVERYONE` / `ALL_BUT_BLACKLIST` / `FRIENDS_WHITELIST` (OOC friends via
  `scenes.Friendship`) / `RIVALS` (declared **mutual** rivals via `scenes.Rivalry`, double
  opt-in — #2170; `friend_services.is_rival` + `declare_rival`/`undeclare_rival`, telnet
  `rival`/`unrival`/`rivals`, web `RivalryViewSet` `/api/scenes/rivals/` + the sheet/card
  `RivalButton`) / `ALLOWLIST`. Settable at any tree node; `CONSENT_MODE_GUIDANCE`
  + `consent_mode_guidance()` (constants) give the per-mode pros/cons copy the settings page /
  telnet `consent modes` / `GET /api/consent/categories/modes/` render (PLACEHOLDER, #2170).
  Onboarding: the "Terms of Engagement" tutorial side-step (tutor-offered, gated on T1;
  `world/seeds/game_content/tutorial.py`) walks a new player to the consent tree
- **Consent tree (#2170):** seed builds an **All Antagonism** root (`FRIENDS_WHITELIST`) with
  every detriment-capable category — `hostile`, `blackmail`, `manipulative`, `theft` —
  parented under it (`world/seeds/consent.py`); theft's effective default becomes the root's
  `FRIENDS_WHITELIST` (its own `ALLOWLIST` survives only as the unseeded `theft_category()`
  fallback / orphaned-row case). `effective_consent_mode(pref, category)`
  is the shared walk-up (nearest rule wins, else root default) — ADR-0113.
  `makeover_category()` (#2632, default `ALLOWLIST`, NOT under All Antagonism — friendly but
  body-autonomy) gates PC stylists applying cosmetic items to another character's real form
  (`use_item`'s pre-charge `_require_makeover_consent`; NPC targets never gate)
- **Key Methods:** `VisibilityMixin.is_visible_to()`, `_tenure_blocks_actor()` (thin delegator
  to `consent_blocks_targeting`, #1909), `decide_consent_block()` (takes `is_rival`),
  `effective_consent_mode()`, `_social_consent_exclusions()` (`actions/player_interface.py`) —
  the batched picker sweep now **honors** the tree/`default_mode` in agreement with
  `consent_blocks_targeting` (#2170 resolved the #1909 allow-only divergence). PvP opt-out is
  the duel-start gate only (#1698): `ChallengeAction` refuses opted-out
  (`_consent_blocked`) + blocked (`block_services.sheet_blocked_for_viewer`) challengers
- **Key Functions:** `seed_social_consent_categories()` (`world/seeds/consent.py`),
  `make_default_categories()` (`world/consent/factories.py`)
- **Key Services:** `set_social_consent_preference()`,
  `set_social_consent_category_rule()`, `remove_social_consent_category_rule()`,
  `add_social_consent_whitelist()`, `remove_social_consent_whitelist()`,
  `add_social_consent_blacklist()`, `remove_social_consent_blacklist()` (#1698),
  `get_social_consent_summary()`, `consent_blocks_targeting(*, owner_tenure, category,
  actor_tenure)` (#1909/#2170 — the public single-tenure gate decision; resolves the effective
  mode by walking the category's ancestor chain, nearest rule wins else the root default),
  `effective_consent_mode(pref, category)` (#2170 — shared walk-up used by read surfaces),
  `theft_category()` (#1909 — lazy seeded "theft" category, own `ALLOWLIST` root)
  (`world/consent/services.py`)
- **Action Keys:** `set_social_consent_preference`, `set_social_consent_category_rule`,
  `add_social_consent_whitelist`, `remove_social_consent_whitelist`,
  `add_social_consent_blacklist`, `remove_social_consent_blacklist` (#1698)
  (`actions/definitions/consent_preferences.py`)
- **Telnet:** `consent` namespace (`commands/consent_preferences.py`) — `consent on|off`,
  `consent modes` (#2170 — per-mode pros/cons), `consent category <key>=<mode>`,
  `consent whitelist add|remove|list`, `consent blacklist add|remove|list` (#1698); plus
  `accept/<difficulty>` + `deny/blacklist` on the consent-response commands (`commands/consent.py`)
- **API:** `/api/consent/` — categories (read-only, now carry `parent` + `default_mode` for the
  tree; `GET /categories/modes/` returns the mode guidance rows, #2170), preferences,
  category-rules, whitelist, blacklist (#1698); writes dispatch through the consent Actions via
  `dispatch_player_action()`
- **Pattern:** RosterTenure-based (player's tenure, not character); absent preference row and
  absent per-category rule fall through to the category's `default_mode` (#1909) — `EVERYONE`
  preserves the legacy allow-all default; a category like theft opts into default-deny
- **Integrates with:** actions (`ActionTemplate.consent_category` FK), roster (RosterTenure),
  codex (visibility), seed loader (`arx seed dev`)
- **Source:** `src/world/consent/`
- **Details:** [consent.md](consent.md)
### Progression
XP, kudos, development points, and unlock system. Contains the most explicit prerequisite framework.

- **Models:** `ExperiencePointsData`, `XPTransaction`, `CharacterXP`, `DevelopmentPoints`, `DevelopmentTransaction`, `KudosPointsData`, `KudosTransaction`, `CharacterUnlock`, `XPCostChart`, `XPCostEntry`, `CharacterPathHistory`, `PathIntent` (player's declared next-path preference — one per character sheet; FK to `CharacterSheet` + `Path`), `KudosDifficultyWeight` (staff-tunable band→multiplier for good-sport kudos; one row per `DifficultyChoice`), `WeeklySocialEngagement` (per-account weekly pending-kudos accumulator; `pending_points`, `granted`, `game_week` FK; `distinct_initiators` is a derived property counting child rows), `WeeklyEngagementInitiator` (child row recording each unique initiator toward a ledger; `UniqueConstraint(ledger, initiator_account)`),
  **Class-Level Advancement (#1352):** `AbstractClassLevelAdvancement` (abstract base shared by `ClassLevelAdvancement` and `AudereMajoraCrossing`; carries `scene`, `declaration_interaction`, `level_before`, `level_after`, `created_at`), `ClassLevelAdvancement` (within-tier Durance receipt — `character_sheet`, `character_class`, `officiant`, `ritual`, `witnesses` M2M → `scenes.Persona`),
  **Training Site (#1700):** `DuranceTrainingSite` (room + trainer-of-record pair; enables site-convened sessions — `room_profile` FK → `RoomProfile`, `officiant` FK → `CharacterSheet`, `training_path` FK → `Path` (nullable), `is_active`; unique `(room_profile, officiant)`),
  **Maturation Points (#2756, ADR-0172):** `MaturationStatCap` (authored per-`PathStage` stat cap, seeded 5/6/11/16/21/25 per the #3001 ruling — `seed_maturation_stat_caps` in `progression/seeds.py`, previously never authored) + `MaturationSpend` (sheet FK, trait FK, `milestone_year`, `is_active` — active iff `milestone_year <= sheet.matured_years`; unique per (sheet, milestone_year)). Services in `progression/services/maturation.py`: `milestone_count` / `available_points` / `spend_maturation_point` (+1 display dot = +10 internal, stage-capped; caps are authored in display dots and convert at the comparison — ADR-0193) / `sync_maturation_spends` (reversal deactivates, re-aging reactivates — every `matured_years` writer outside the birthday tick must call it). Both writers also stamp a `traits.CharacterTraitChange` row (`source=MATURATION`, #3055) for each ±1 dot they apply

  **Level Stat Points (#3001, ADR-0205):** `LevelStatPointSpend` (sheet FK, trait FK, `level_granted` 2..N, `is_active`; unique per (sheet, level_granted)) — one point per class level past the first, balance derived (`level − 1` minus active spends, no grant hook). Services in `progression/services/stat_points.py`: `stat_points_earned` / `available_stat_points` / `spend_level_stat_point` (same `MaturationStatCap` stage cap) / `sync_level_stat_point_spends` (called from `apply_class_level_advance` so reversals refund). Both writers stamp `traits.CharacterTraitChange` rows (`source=LEVEL_STAT_POINT`, #3055). API: `GET /api/character-sheets/{id}/stat-points/` + `POST .../spend-stat-point/`; frontend `StatPointPanel` beside `MaturationPanel`
- **Unlock Requirements** (all have `is_met_by_character(character) -> tuple[bool, str]`):
  - `TraitRequirement` — checks CharacterTraitValue
  - `LevelRequirement` — checks character_class_levels
  - `ClassLevelRequirement` — checks specific class level
  - `MultiClassRequirement` — multiple class levels
  - `TierRequirement` — tier 1 vs tier 2
  - `AchievementRequirement` — checks `CharacterAchievement` for a granted `Achievement`
  - `RelationshipRequirement` — counts the character's own qualifying `RelationshipTrackProgress`
    rows (tier >= `minimum_tier`, optionally narrowed to `required_track_kind`) against
    `minimum_count` (#2116)
  - `ItemRequirement` — possession-only check of a physical touchstone/trophy item, template or touchstone mode (#1859)
  - `CodexKnowledgeRequirement` — checks `CharacterCodexKnowledge` at `KNOWN` status for a specific `CodexEntry`; gates Path selection behind codex knowledge (#2603)
- **Key Functions:**
  - `check_requirements_for_unlock(character, unlock) -> tuple[bool, list[str]]`
  - `get_available_unlocks_for_character(character) -> AvailableUnlocks`
  - `ExperiencePointsData.can_spend(amount) -> bool`
  - `CharacterXP.can_spend(amount) -> bool`
  - `current_path_for_character(character) -> Path | None` (`selectors.py`) — returns the character's most-recent `CharacterPathHistory` path
  - `next_path_options(character) -> list[Path]` (`selectors.py`) — returns active child paths of the current path (or all top-level paths if no current path); used by `PathOptionsView`
  - `eligible_advanced_paths_for(sheet) -> list[Path]` (`selectors.py`, #1700) — active child paths at the next level's stage (for the semi-crossing resolver); empty when not at a stage boundary
  - `resolve_advanced_path_by_name(sheet, name) -> Path | None` (`selectors.py`, #1700) — case-insensitive name match against `eligible_advanced_paths_for`
- **API Endpoints (progression):**
  - `GET /api/progression/path-options/` — current path + selectable next paths (character via `X-Character-ID` header) → `PathOptions` schema; transition-generic, reused beyond any single transition type
  - `GET /api/progression/path-intent/` — declared `PathIntent` or `null` (character via `X-Character-ID` header)
  - `PUT /api/progression/path-intent/` — declare a path intent; body `{ path_id }` (character via `X-Character-ID` header)
  - `DELETE /api/progression/path-intent/` — clear declared intent (character via `X-Character-ID` header)
  - `GET /api/progression/unlocks/` — purchasable unlocks for the played character; paginated, filterable by `unlock_type` (`class_level` / `thread_xp_lock` / `skill_breakthrough`, #2115)
  - `POST /api/progression/unlocks/purchase/` — buy a `class_level`, `thread_xp_lock`, or `skill_breakthrough` unlock with XP; dispatches `PurchaseUnlockAction`
  - `GET /api/progression/durance/status/` — Durance readiness hub for the played character; mirrors telnet `durance status` exactly (#3045)
  - `POST /api/progression/durance/convene/` — open a site-convened Durance session at the played character's room; calls `convene_durance_at_site` directly, not a dispatch seam (#3045)
  - `GET`/`POST`/`PATCH`/`DELETE /api/skills/training-allocations/` — deliberate skill training allocations (`world.skills`, `TrainingAllocationViewSet`); dispatches `ManageTrainingAction`
- **Web Advancement tab (#3045):** `frontend/src/progression/components/advancement/` —
  `AdvancementTab` (mounted on `CharacterSheetPage`, own-sheet + active-puppet gated) hosts
  `BreakthroughsCard` / `ClassUnlocksCard` (both over the Unlock Shop above) / `TrainingCard`
  (over `TrainingAllocationViewSet`) / `DuranceCard` (over the Durance endpoints above, joining
  via the existing `RitualSessionViewSet.accept`, now auto-firing a site-convened session to
  match telnet's `ritual join` — see `docs/systems/progression.md`). Closed the "every SPEND
  path was telnet-only" gap; `RandomScenePanel` (earn-path, previously built-but-orphaned) now
  mounts on `XpKudosPage` instead.
- **Actions:**
  - `PurchaseUnlockAction` (`registry_key="purchase_unlock"`) — shared unlock purchase path for web and telnet
  - `ClaimKudosAction` (`registry_key="claim_kudos"`) — kudos→XP conversion; shared by web and telnet (#1348)
  - `CastVoteAction` / `RemoveVoteAction` (`"cast_vote"` / `"remove_vote"`) — weekly vote budget management (#1348)
  - `ClaimRandomSceneAction` / `RerollRandomSceneAction` (`"claim_random_scene"` / `"reroll_random_scene"`) — weekly random-scene bounty claims/rerolls (#1348)
  - `SetPathIntentAction` / `ClearPathIntentAction` (`"set_path_intent"` / `"clear_path_intent"`) — declare/clear preferred next path for Audere Majora (#1348)
- **New service module (#1348):** `world.progression.services.path_intent` — `set_path_intent(sheet, path)` / `clear_path_intent(sheet)`; single seam for `PathIntentViewSet` + `CmdPathIntent`
- **Telnet Commands:** `progression unlocks`, `progression unlock class=<id>`, `progression unlock thread=<id> level=<n>` (in `commands/progression.py`);
  `kudos`, `vote`, `randomscene` (alias `rscene`), `pathintent` (in `commands/progression_rewards.py`, #1348);
  `durance [status|intent|convene]` (in `commands/durance.py`, #1700)
- **`award_kudos` real-time push + privacy guard (#2161):** every `award_kudos` call
  schedules `notify_kudos_received` via `transaction.on_commit`, pushing a `kudos_received`
  WS frame (amount/source_category/description) to the recipient's connected sessions —
  central to the service, not per-caller, so vote settlement, GM awards, writeup kudos, and
  the social-engagement roll below all get the toast for free. `KudosTransactionSerializer`
  no longer exposes `awarded_by`/`awarded_by_name` to the recipient (ADR-0033 structural
  guard — the awarder's identity never leaks to the person they kudos'd).
- **Good-sport kudos accrual:**
  - `accrue(account, initiator_account, points) -> WeeklySocialEngagement` (`services/engagement.py`) — adds points to the weekly pending ledger; tracks `WeeklyEngagementInitiator` rows for distinct-initiator anti-farm; resets stale ledgers lazily on the game-week boundary.
  - `grant_social_engagement_kudos() -> int` (`services/engagement.py`) — called at weekly rollover; for each ungranted ledger with `engagement_events > 0`, rolls the diminishing-chance curve once per event (`_roll_good_sport_points`, guaranteed first point, capped at `GOOD_SPORT_WEEKLY_CAP`) and awards kudos via `award_kudos` when the roll yields > 0; every ledger is marked `granted=True` regardless of the rolled amount. There is no distinct-initiator floor — `distinct_initiators` (from `WeeklyEngagementInitiator` rows) is tracked on the ledger but not read by this function. Requires the `"social_engagement"` `KudosSourceCategory` to exist (seeded by the "kudos" cluster, #2026) or it logs a warning and no-ops.
  - `KudosDifficultyWeight.weight_for(band) -> Decimal` — returns configured multiplier for the difficulty band; falls back to `Decimal("1.0")` when no row exists.
- **Class-level advancement spine (#1352 — `services/advancement.py`):**
  - `primary_class_level(character) -> CharacterClassLevel | None` — primary (or highest-level) class level row; None when absent.
  - `apply_class_level_advance(sheet, *, level_after) -> None` — shared level-write + cache invalidation; no receipt, no scene side-effects. Called by both `cross_threshold` and the Durance service.
  - `assert_can_officiate(*, officiant_sheet, inductee_sheet, target_level) -> None` — raises `OfficiantIneligibleError` when level gate or Path-lineage gate fails.
  - `advance_class_level_via_session(*, session) -> list[ClassLevelAdvancement]` — `fire_session` dispatch target for the Ritual of the Durance; advances each ACCEPTED inductee, posts their testament pose, records witnesses, writes receipts.
  - `convene_durance_at_site(*, inductee_sheet, room) -> RitualSession` (#1700) — drafts a Durance session using the room's `DuranceTrainingSite` trainer as initiator; raises `NoDuranceSiteError` when no eligible site is present.
- **Advancement exceptions (`exceptions.py`):** `ClassLevelAdvancementError` (base), `TierBoundaryRequiresCrossing`, `AdvancementRequirementsNotMet`, `AdvancementUnlockNotPurchasedError` (#2116 — missing `CharacterUnlock` purchase, an additional gate stacked alongside `AdvancementRequirementsNotMet`), `OfficiantIneligibleError`, `NoDuranceSiteError` (#1700) — all carry `user_message`.
- **Pattern:** `AbstractClassLevelRequirement` base class with polymorphic `is_met_by_character()` — extend this for new prerequisite types (society, relationship, etc.)
- **Integrates with:** traits (unlock requirements), classes (path unlocks), goals (XP rewards), magic (Audere Majora offer pre-selects from `PathIntent.intended_path_id` via `get_intended_path_id` on `PendingAudereMajoraOfferSerializer`; `advance_class_level_via_session` dispatched from `fire_session` on the Ritual of the Durance; `AudereMajoraCrossing` inherits `AbstractClassLevelAdvancement`), scenes (good-sport kudos accrued at consent; weekly grant via game-clock rollover)
- **Source:** `src/world/progression/`
- **Details:** [progression.md](progression.md)

### Character Sheets
Character identity, appearance, demographics, and guise system.

- **Models:** `CharacterSheet`, `Profile` (bio + lineage, #1270), `ProfileTextVersion`
  (#2631 — snapshot-on-write history for `ProfileTextField` prose (background,
  personality): full text per version, stamped with IC datetime + active `stories.Era`;
  written ONLY through `services.update_profile_text`, which also captures the CG
  original on the first post-CG write; admin edits route through it via
  `ProfileAdmin.save_model`), `Heritage`, `Gender`, `Pronouns`, `MoodOption`
- **Mood (#2994):** `CharacterSheet.current_mood` — a sticky, nullable, INTERNAL declared
  state (`feel <state>` telnet / `SetMoodAction`, key `set_mood`). Silent by design: no room
  echo, no scene Interaction row, no look/appearance rendering, no mechanical effect. Owner/
  staff-only on `CharacterSheetSerializer`'s identity section; any other viewer learns it only
  through the earned `SenseMoodAction` (`sense_mood`) — gated on a `skills.Specialization`
  named "Empathy" and resolved via `perform_check` against a `checks.CheckType` named "Sense
  Mood" (both content gaps, fail cleanly until the lore repo authors them). See
  `character_sheets.md`'s "Mood" section.
- **API:** `GET /api/character-sheets/{pk}/profile-text-versions/` — the prose-history
  timeline; **owner/staff-only by default** (#2631 ruling — everyone else gets an empty
  list); entries carry era/IC-date stamps + the applying request's reasoning caption
- **Absence vocabulary (#2728 §5):** `CharacterSheet.objects` carries the single
  answer to "is this character absent?" — `.active()` (ACTIVE + ALIVE),
  `.dormant()` (its exact complement), `.claimable()` (delegates to
  `RosterEntryQuerySet.available_characters()`, never a second copy of the
  predicate), and `.inactive_at_least(tier)` (the DB-level twin of the
  `decay_tier` property, pinned to it by a parity test). Consumers ask these
  instead of each deriving absence from raw timestamps or flags — mothballing,
  the sanctum gates and applications previously used three different
  definitions. Derived, never stored: a stored tier would need maintaining on
  both the cron path and the login path. The manager is based on
  `SharedMemoryManager` (identity map preserved) but deliberately NOT
  `ArxSharedMemoryManager`, whose `cached_all()` is a footgun on a
  playerbase-scoped table.
- **State axes (#671, split #2728 §2):** `ActivityState` is OOC (is the player
  showing up); `LifecycleState` is IC (what is true in the fiction) — orthogonal
  by design. `LifecycleState.UNKNOWN` is separate from `CAPTURED`: captured means
  someone is holding them (the captivity system drives it), unknown means
  whereabouts are genuinely unknown and investigation can resolve it.
  `DecayTier.SHORT_INACTIVE` (30d) is named so it stops colliding with
  `ActivityState.INACTIVE` — a day-count tier and a swept flag are not the same
  thing.
- **Age axes (#2756, ADR-0172):** `matured_years` + `withered_years` +
  `aging_paused` + nullable `ic_birth_year` + `birthday_month`/`birthday_day`
  (celebrated date; Sleeper waking day — `Heritage.chronological_age_unknown`
  leaves the birth year null). Derived properties `biological_age` (= matured +
  withered), `apparent_age` (= biological; cosmetic overrides are free and live
  in the appearance layer), `chronological_age` (vs `get_ic_now()`, None =
  "Unknown"). Old `age`/`real_age`/`birthday` columns retired. Maturation
  Points live in progression; decline/Frailty/dying window live in vitals;
  the birthday digest lives in tidings. Sheet API: identity carries public
  `age` (apparent) + `birthday`, owner/staff-only `chronological_age`/
  `biological_age`/`withered_years`; owner actions `GET …/maturation/` +
  `POST …/spend-maturation-point/`.
- **Integrates with:** roster (character management), character_creation (sheet setup),
  gm (table update requests apply prose rewrites), stories (`Era` stamps),
  game_clock (chronological derivation + aging crons), progression (Maturation
  Points), vitals (Frailty decline), species (`eternal_youth`,
  `decline_start_age`), tidings (birthday digest)
- **Source:** `src/world/character_sheets/`
- **Details:** [character_sheets.md](character_sheets.md)
### Character Creation
Multi-stage character creation flow with draft system.

- **Models:** `CharacterDraft`, `StartingArea` (`grants_residence_tenancy` BooleanField, default
  True, #2036 — an authored per-area toggle for whether finalizing a character there grants a
  `LocationTenancy` at the starting room; `crest_art` — nullable FK →
  `evennia_extensions.Media`, `SET_NULL`, #2408 — replaced a raw-URL field, gradient
  placeholder when unset), `Beginnings` (`art` — same `Media` FK shape, #2408; `prelude_mission`
  nullable FK → `missions.MissionTemplate`, #2470 — the Beginning's auto-granted first-hour Mission)
- **Key Functions:** Stage validation, draft progression, `_grant_cg_residence_tenancy()` (#2036,
  `world/character_creation/services.py`) — called from `finalize_character`; when
  `starting_area.grants_residence_tenancy` and the starting room resolves a `RoomProfile`, calls
  `world.locations.services.grant_tenancy()` for the new primary persona (notes="Academy
  enrollment"), which auto-defaults both Evennia `home` and `CharacterSheet.current_residence` via
  `maybe_default_residence()` — closes the "Academy auto-residence" story with zero manual player
  step, making the daily residence-trickle gate reachable straight out of CG.
- **Prelude mission auto-grant (#2470):** `_grant_prelude_mission()`
  (`world/character_creation/services.py`) — called from `finalize_character` right after
  `_grant_cg_residence_tenancy`. No-op when `draft.selected_beginnings.prelude_mission` is null;
  otherwise calls `world.missions.services.run.staff_assign_mission()` verbatim (no new
  missions-app surface). Deliberately NOT best-effort — a misconfigured template raises and rolls
  back the whole finalization transaction (a content-authoring bug, not contention).
- **Seeded CG-world content (#1333):** `seed_character_creation_dev()` (`src/world/seeds/character_creation.py`) — the `"character_creation"` cluster; seeds the 12 stat Traits unconditionally, plus every `RosterType` shelf via `world.roster.seeds.ensure_rosters()` (#2728 — replaced two name-keyed `Roster.objects.get_or_create` calls that created duplicates of Active/Available while never creating Inactive, Frozen or Restricted at all), so `finalize_character` runs on a fresh DB. Species/Gender/HeightBand/Build/FormTrait family/Distinction family/CGExplanation are all `CONTENT_MODELS` (#2698, ADR-0168) — looked up via `authored_or_sample()` and invented only under `SEED_SAMPLE_CONTENT`; Realm/StartingArea/Beginnings/TarotCard/Path are open-ended world content gated behind the same flag. Part of `seed_dev_database()` (the admin "Load sane defaults" Big Button); surfaced in the superuser-only **Game Setup** hub.
- **Email notifications (#2162):** `world.character_creation.email_service.CGEmailService` —
  submission/approved/revisions-requested/denied notices, called (best-effort) from
  `submit_draft_for_review`/`approve_application`/`request_revisions`/`deny_application`.
  Extends `world.roster.email_service.EmailServiceBase` (split out of `RosterEmailService` in
  the same change so a sibling domain service can reuse `_send_email`/`_get_staff_emails`
  without subclassing `RosterEmailService` itself, whose approve/deny methods take a
  roster-specific `tenure` arg). See [character_creation.md](character_creation.md#email-notifications-2162).
- **Lineage stage: Upbringings (#3617):** the Lineage stage offers per-beginning
  `OriginTemplate` rows ("Upbringing" in CG copy) with a CG point cost, a trust
  gate, and a family path (claim a staff-authored family, name a new one, or
  none). Authoring recipes (an Upbringing, an orphan, a family with influence, a
  new `FamilyKind`, and more): [family-authoring-recipes.md](family-authoring-recipes.md);
  the design decisions: ADR-0268, ADR-0269.
- **Integrates with:** All character-related systems (traits, skills, magic, sheets)
- **Source:** `src/world/character_creation/`
- **Details:** [character_creation.md](character_creation.md)
### Market (#2066, standing gating #2995)
Two-tier commerce: capital market squares (NPC stock sinks + PC stalls of
unfinished wares w/ buyer finishing passes) and crafter shops (stations +
craft-as-service offers). The description belongs to the player; dual
provenance ("Crafted by X, Designed by Y"). A persona-bearing NPC seller
(`MarketStall.shopkeeper_persona` / `CraftingServiceOffer.crafter_persona`)
reads `NpcRegard` (#1717) at purchase time — a functionary service, not a
static shop: standing shifts price, gates reserved stock, and past a
hostile floor refuses service outright.

- **Models:** `MarketSquare`, `MarketStall` (host-org cuts,
  `shopkeeper_persona`), `StockListing` (`min_regard`), `WareListing`,
  `FinishingPass`, `CraftingServiceOffer` (`min_regard`), `MarketSale`;
  `ItemInstance.designer_*` pair
- **Services:** `world.items.market.services` — purchase_stock/list_ware/
  purchase_ware/finish_ware/set_service_offer/run_service_craft (offering
  crafter as skill source, shop-anchored, regard-gated + regard-adjusted
  price), dual_provenance_line, `_shopkeeper_regard`/`_regard_adjusted_price`/
  `_check_regard_gate` (`world.items.market.constants` bands/floor)
- **Surfaces:** 6 `market_*` REGISTRY actions; `/api/items/market-squares/`
  + `/service-offers/` (read-only; directory advertises, execution requires
  visiting; regard-gated rows hidden per-viewer); web `/market`; telnet
  `market` namespace; seeds cluster `market`
- **Source:** `src/world/items/market/`
- **Details:** [market.md](market.md)

### Trade (#2990)
Player<->player negotiated exchange: both sides stage items/coin, either side
restages until both confirm, atomic swap. Barter falls out for free; auction
is deferred to its own follow-up (not two-party-confirm shaped).

- **Models:** `TradeSession` (`CharacterSheet`-keyed, `PROPOSED`/`ACTIVE`/
  `COMPLETED`/`CANCELLED`, plain coin columns per side), `TradeItemStake`
- **Services:** `world.items.trade.services` — propose_trade/accept_trade/
  stake_item/unstake_item/set_coin_offer/confirm/cancel_trade/execute_trade
  (mirrors `resolve_crossing_offer`'s two-phase `select_for_update` shape;
  item relocation mirrors `give()`; coin via `currency.services.transfer`)
- **Surfaces:** 7 REGISTRY actions; `/api/items/trade-sessions/` (read-only,
  IC-scoped); web `TradePanel` (two-column staging card)
- **Source:** `src/world/items/trade/`
- **Details:** [trade.md](trade.md)

### Tavern Games (#3292)
A pure social-fun coin sink: characters at a table in a social hub open a
curated coin-stakes dice game, ante in, roll, winner takes the pot, visible
to the room. Pure chance at MVP (no skill input); server-side `randint`.

- **Models:** `TavernGame` (`NaturalKeyMixin`, curated content, one row at
  MVP), `TavernGamblingConfig` (singleton, weekly loss cap), `GameSession`
  (place + game + escrowed pot, OPEN/RESOLVED/ABANDONED), `GameSeat`
  (ante_paid + nullable roll_result), `GamblingLossLedger`
  (character_sheet + game_week, mirrors `currency.PurseDrainWeek`)
- **Services:** `world.tavern_games.services` - open_session/join_session/
  roll/leave_session; ante is a currency sink into `GameSession.pot`, payout
  is a currency mint from the pot, refund on leave; loss-cap refusal locks +
  bumps the week's ledger row in the same transaction as the ante sink;
  highest-roll resolve with whole-table re-roll on a tie; public POSE/OUTCOME
  narration via `world.scenes.interaction_services`
- **Surfaces:** 4 REGISTRY actions (`tavern_game_open`/`_join`/`_roll`/
  `_leave`); `/api/tavern-games/` (`games/` read-only catalog, `sessions/`
  read + open/join/roll/leave custom actions); telnet `game` namespace; web
  Place-bar game widget; seeds cluster `tavern_games`
- **Source:** `src/world/tavern_games/`
- **Details:** [tavern-games.md](tavern-games.md)
- **Glossary:** `src/world/tavern_games/AGENT_GLOSSARY.md`

### Roster
Character lifecycle management with web-first applications and player anonymity.

- **Models:** `Roster`, `RosterEntry`, `RosterTenure`, `RosterApplication`, `PlayerMail`
- **`Roster.roster_type` is the key (#2728):** a `RosterType` TextChoices
  (`ACTIVE`/`INACTIVE`/`AVAILABLE`/`RESTRICTED`/`FROZEN`/`PENDING`/`NPC` — PENDING and
  NPC were previously real shelves living outside the enum, matched on `name` text)
  is the unique, DB-`CheckConstraint`-enforced identity for a shelf; `name` is a
  free-text display label only, editable by staff without creating a second shelf.
  `world.roster.seeds.ensure_rosters()` is the single seeding path (idempotent,
  `get_or_create` on `roster_type`) — service functions look up a shelf via
  `Roster.objects.get(roster_type=...)`, never by calling `ensure_rosters()` at
  runtime (that function is seeding-only).
- **Activity + auto-release (#2728 §4/§6/§7):** `RosterEntry.activity_requirement` is
  **authored per character** (staff-editable), deliberately not on `Roster` — approval
  moves a character Available → Active, which would flatten a shelf-level value. It
  governs which signals count (HIGH = IC action + login; LOW = login only) and whether
  inactivity also *releases*; it no longer decides whether a character is swept at all.
  `sweep_activity_states` is **demotion-only**, scoped to the Active shelf (NPCs are
  excluded by shelf, not by a special case); promotion is event-driven via
  `mark_character_active` from `at_post_puppet`. Hiatus expiry runs after demotion so a
  lapsed vacation doesn't cost the character in the same tick. Release is narrower than
  the flag — HIGH/LOW released, NONE and OCs never — and ends the tenure rather than
  deleting it, so `RosterApplication.approve` can re-seat a returning player onto their
  own row instead of renumbering them as a second player.
- **Sweep cost is writes-only (#2728):** the cron's population is the whole active
  playerbase, so its per-character cost is what matters. It `select_related`s the shelf
  and `true_profile` and prefetches the tenures + player account via
  `Prefetch(..., to_attr="cached_tenures")` — `decay_tier` otherwise walks
  `roster_entry → current_tenure → player_data → account` per sheet.
  `RosterEntry.cached_tenures` reads `.all()` (an `order_by` on a related manager always
  re-queries, silently voiding a caller's prefetch; newest-first now lives in
  `RosterTenure.Meta.ordering`). Because `SharedMemoryModel` reuses instances, any bulk
  fill or tenure mutation must call `RosterEntry.invalidate_tenure_cache()` or the fill
  answers with a stale snapshot for the life of the process — `test_sweep_query_slope`
  guards both the slope and the cleanup.
- **`RosterApplication` uniqueness (#2162):** a PENDING-only `UniqueConstraint` on
  `(player_data, character)` (was a status-blind `unique_together`, which blocked
  re-applying for a character after denial/withdrawal, not duplicate submissions —
  those were always serializer-blocked). The create serializer catches the two-tab
  race `IntegrityError` and returns the existing `DUPLICATE_PENDING_APPLICATION`
  error code. `web.api.serializers.PendingApplicationSerializer` gained
  `character_id` (alongside `character_name`) so the frontend can match a pending
  application against `available_characters`.
- **Email service split (#2162):** `world.roster.email_service.EmailServiceBase` now
  hosts the shared `_send_email`/`_get_staff_emails` primitives; `RosterEmailService`
  extends it unchanged. `world.character_creation.email_service.CGEmailService`
  extends the same base — see Character Creation above.
- **OOC mail web surface (#2160, ADR-0226):** `PlayerMailViewSet` gained two actions —
  `POST /api/roster/mail/{id}/mark-read/` (idempotent, recipient-scoped via the queryset) and
  `GET /api/roster/mail/unread-count/` (unread + unarchived, across the requester's tenures).
  Sending mail fires `notify_mail_arrived` via `transaction.on_commit` (the
  `notify_battle_state_changed` pattern), pushing a new `WebsocketMessageType.MAIL_ARRIVED`
  (`src/web/webclient/message_types.py`) payload — `mail_id`/`sender_display`/`subject` only, no
  account identifiers. Frontend: in-scene "Message the player" quick-compose
  (`MessagePlayerDialog` pre-filling `ComposeMailForm`) from the character card, an
  `UnreadMailBadge` in the header, and a mark-read-on-open flow in `ReceivedMailList`. No
  telnet mail command exists or is planned. PlayerMail is OOC between players; IC missives
  are #3289's separate system (ADR-0226).
- **Game invites (#2483):** `GameInvite` model + `GameInviteViewSet` for
  player-to-friend contextual invites. Trust-gated via `PlayerTrust` (new
  `INVITE` `TrustCategory`, `BASIC` minimum, seeded via the Big Button
  "roster" cluster). Token-in-URL flow: inviter creates invite with a message
  → friend registers via `/register?invite=TOKEN` → claims on first login
  → invite annotates their first `DraftApplication.invited_via` FK → inviter
  gets a websocket push on submission. Services use the `game_invite` prefix
  (`create_game_invite`/`claim_game_invite`/`revoke_game_invite`) to avoid
  collision with `world/gm/services.py`'s `GMRosterInvite` functions. See
  ADR-0141. **Gated on `RegistrationConfig.registration_open` (#3182):** while
  registration is closed, `create_game_invite` and `claim_game_invite` raise
  `RegistrationClosedError` (403 at the API) and `resolve_invite` returns None
  (404) — a player invite is never a side door around the staff
  `AccountInvite` gate.
- **Staff application review queue (#3265):** `RosterApplicationViewSet`
  (`/api/roster/applications/`, staff-only via `CanApproveApplications` →
  `PlayerData.can_approve_applications()`) surfaces the review workflow the admin
  bulk actions previously gated alone. List/detail use the new
  `RosterApplicationListSerializer` and the (now-wired) pre-existing
  `RosterApplicationDetailSerializer`; `review` posts through the pre-existing
  `RosterApplicationApprovalSerializer` to `RosterApplication.approve()`/`.deny()`.
  Fixed in the same change: `character_name` on both serializers now sources
  `character.character.db_key` (was `character.db_key`, one hop short of the
  `ObjectDB` - `character` here is the `CharacterSheet`, not the game object).
  Frontend: `/staff/roster-applications` (queue) + `/staff/roster-applications/:id`
  (detail, approve/deny), linked from the staff hub's "Roster Character
  Applications" card; the pre-existing hub card was retitled "Character
  Applications" to disambiguate from CG's DraftApplication queue.
- **Durable character selection (#3412 slice 1, ADR-0241):** `PlayerData.selected_entry`
  is the account's server-side "who am I browsing as" fact (state 2.5 — selected but
  not necessarily puppeting). Sole mutator `world.roster.services.selection.set_selected_entry`;
  sole reader for "who is this request acting as" `selection.selected_character(account)`
  (missions journal, NPC interactions; ADR-0260 says why not `request.user.puppet`);
  `POST /api/roster/entries/select/` + `selected_entry`/`selected_entry_id` on
  `GET /api/user/`. Zero lifecycle/session/puppeting side effects — selection is not
  presence. Frontend mirrors it in `gameSlice` (hydrated from the account query, reload-
  and cross-device-durable) and surfaces it as `SelectedCharacterChip` in `Header` — see
  [roster.md](roster.md)'s "Frontend: Selection Chrome" section for the full detail.
- **The Hall — logged-in home surface (#3412 slice 2, ADR-0245):** `GET
  /api/roster/entries/mine/` annotates `unread_narrative_count` per character (one
  aggregated JOIN/GROUP BY over unacknowledged `NarrativeMessageDelivery` rows, not
  per-row queries); `MyRosterEntrySerializer.get_unread_narrative_count` reads the
  annotation off `obj.__dict__` when present, falling back to a direct count on the
  unannotated `select`-endpoint path. Drives the "Your Characters" band's tidings
  `CountChip` on `/` — see [roster.md](roster.md)'s API Endpoints section. The same
  band (`CharactersBand`) carries an extra grid tile for a staff/GM account
  (`account.is_gm`/`is_staff`) — `GMSlot` (#3478), the Hall's GM onboarding/edit
  surface; see the GM section's "GM onboarding lives on the Hall" entry.
- **The offscreen-act gate (#3412 slice 3, ADR-0246):** `MyRosterEntrySerializer` also
  exposes `lifecycle_state` (plain read-only `CharField` mirror of
  `CharacterSheet.lifecycle_state`, no annotation, no migration), letting the Hall's
  OffscreenActsPlate render world-voice refusal prose for a docked
  CAPTURED/DEAD/RETIRED/UNKNOWN character instead of the offscreen-act rows. The
  actual gate — `actions.offscreen_gate.offscreen_act_state` — runs server-side in
  `Action.check_availability()` for journal/goal/persona/proclamation acts; see the
  Actions section above and ADR-0246.
- **Integrates with:** accounts, character_sheets, scenes
- **Source:** `src/world/roster/`
- **Details:** [roster.md](roster.md)

### Kinship (#2062)
Person-node genealogy: typed parentage/union edges, truth-vs-public-record via
Secrets, souls with per-life-knowledge reincarnation chains, app-in slots/pools.

- **Models:** `Family` (`kind` FK `FamilyKind`, `influence`, #3617),
  `FamilyKind` (authored rows: Commoner, Noble, Crime, or any kind staff add;
  `styles_as_house`), `Kinsperson` (5 definition tiers; heredity stubs
  `species`/`power_band`, #2815), `FamilyMembership`, `UnionKind`/`Union`,
  `ParentageEdge` (6 kinds; step/in-law DERIVED; `is_ritual_invoker` marks the
  Tree of Souls dominant line), `KinspersonTraitValue` (lazily-pinned parent
  colors), `Soul`/`SoulIncarnation`, `KinSlotPool`; `Secret.subject_aware` delta
- **Enums:** `PowerBand` (Quiescent→Transcendent; null = assumed sub-Puissant)
- **Services:** `world.roster.services.kinship` — viewer-aware walks
  (`derive_relationship`, `family_tree_for`, `parents_of`...), writers
  (`record_parentage`/`record_union`/`record_incarnation`, memberships,
  `mint_from_pool`/`claim_appable_node`/`define_deferred`); `OMNISCIENT` sentinel.
  `world.roster.services.heredity` (#2815) — Parent Dominance:
  `derive_lines_for_child`/`derivable_species`/`inherited_options`
- **Surfaces:** `families/` (+`has_open_positions`/`area_id` filters) +
  `families/:id/tree/` + `families/:id/slots/` REST — the same `FamilyViewSet`
  is also mounted at `/api/character-creation/families/` for CG; (#3003)
  `kin/tree/<character_id>/` (viewer-filtered graph payload for one character)
  + `kin/relationship/?a=&b=` (viewer-derived relationship label); CG slot claim
  (draft `claimed_kin_slot/_pool`, `_bind_kinship_node` at finalize; FE
  `KinSlotPicker`); CG invented parents (`second_parent_species` + draft_data
  names/genders → `_bind_invented_parents` + `_pin_heredity_back_inference` at
  finalize; FE `InventedParentsCard`); parent-aware
  `form-options/:species_id/?draft=` (inherited option groups + `is_required`);
  telnet `sheet/family`; staff admin. (#3003) Character-sheet FE:
  `KinshipPanel` (Kinship tab, `KinTreeGraph` + relationship readout). Seeds:
  cluster `kinship`
- **Consumed by:** #1884 recognition/succession law; #1985 estates (future);
  future child-generation spec (deferred, #2815)
- **Source:** `src/world/roster/models/families.py`, `services/kinship.py`,
  `services/heredity.py`
- **Details:** [kinship.md](kinship.md) · ADR-0097 · ADR-0173

### GM
Player-GM identity, tables, roster recruitment, and the trust ladder that caps what a
GM at a given level may author (#2000, ADR-0097).

- **Models:** `GMProfile` (OneToOne account, `level: GMLevel`, `approved_at`/`approved_by`,
  `last_active_at` stub, `contact_times`/`ooc_info` freeform `TextField`s (#3478) —
  writable only through the GM's own `mine` endpoint below), `GMApplication` (freeform
  text, staff response, one PENDING
  per account), `GMTable` (a GM's working group; ACTIVE/ARCHIVED lifecycle),
  `GMTableMembership` (persona-pinned, soft-leave via `left_at`), `GMRosterInvite`
  (single-use recruitment code, public or private-with-email-match, 30-day default
  expiry), `GMLevelCap` (one row per `GMLevel`, staff-tunable: `max_beat_risk`
  (`RenownRisk`), `allow_custom_stakes`, `allow_global_scope_authoring`,
  `auto_clear_regional`, `max_story_areas`, `max_story_rooms_per_area`,
  `max_story_npcs`, `allow_item_rewards` (#3566 - gates ITEM-sink
  `StakeRewardLine` authoring, seeded `True` for EXPERIENCED/SENIOR only);
  seeded via `factories.seed_default_gm_level_caps`), `GMLevelChange` (audit row: `profile`,
  `old_level`, `new_level`, `changed_by`, `reason`, `created_at`; written only by
  `promote_gm`, never edited by hand), **`GMRewardConfig`** (#2123 — pk=1 singleton,
  `load()` classmethod; every GM Story Reward award value as a proper column:
  `beat_xp_per_player`/`beat_xp_cap`, `episode_xp_per_player`/`episode_xp_cap`,
  `story_completion_xp_per_player`/`story_completion_xp_cap`, `weekly_reward_cap`,
  `feedback_xp_per_rating_point`; staff-editable in admin, seeded via the `gm`
  cluster seeder, surfaced read-only on the Game Ops Story/GM panel), **`GMWeeklyRewardTracker`**
  (#2123 — OneToOne `GMProfile`, FK `game_clock.GameWeek` (SET_NULL),
  `xp_awarded_this_week`; mirrors `journals.WeeklyJournalXP`'s get-or-reset-by-week shape).
  **Scenario catalog (#2127, ADR-0110):**
  `SituationKind` (`NaturalKeyMixin`, cross-cutting taxonomy tag — "Chase",
  "Negotiation" — `minimum_gm_level` breadth-gates visibility; `objects` has
  `cached_all()` via `CachedAllMixin`, mirrors `ConsequencePoolManager`; holds no FK
  to `mechanics.SituationTemplate` — ADR-0010, `gm` depends on `mechanics`, not the
  reverse), `CheckTypeSituationFit` (through, `checks.CheckType` ↔ `SituationKind`,
  `fit_notes`), `SituationDifficultyGuide` (`situation_kind` + `risk: RenownRisk` +
  `recommended_difficulty: DifficultyChoice` + `guidance_text`; `unique_together`),
  `ConsequencePoolGuide` (`situation_kind` + `pool: actions.ConsequencePool` +
  `selection_criteria` + `is_default`; ADVISORY TEXT ONLY — no code path reads it to
  select/write a live `consequence_pool` FK, Decision 7), `CatalogSuggestion`
  (`submitted_by: accounts.AccountDB`, `situation_kind` nullable, `proposal_kind`,
  `proposal_text`, `status: player_submissions.SubmissionStatus` — reused directly,
  Decision 8 — `reviewer`, `review_notes`, `resolved_at`).
  **`GMSummonOffer`** (#3071 — consent-prompted GM summon: `target_sheet`, `invited_by`
  (`GMProfile`, nullable — `None` for a staff account with no profile),
  `gm_display_name` (snapshot, not a live FK walk), `room` (`RoomProfile`, destination),
  `scene` (nullable, display only), `created_at`; `unique_pending_gm_summon_offer` on
  `target_sheet` — row existence IS pending status, deleted by
  `resolve_gm_summon_offer` on accept or decline, mirroring `PendingCast`/
  `PendingAudereOffer` rather than `DuelChallenge`'s status-enum shape)
- **Enums (`constants.py`):** `GMLevel` (STARTING/JUNIOR/GM/EXPERIENCED/SENIOR),
  `GM_LEVEL_ORDER` + `gm_level_index(level)` (position on the ladder, 0–4),
  `GMApplicationStatus`, `GMTableStatus`, `CatalogSuggestionProposalKind`
  (NEW_SITUATION/CHECK_FIT/DIFFICULTY_GUIDE/POOL_GUIDE/OTHER) + `PROPOSAL_KIND_MIN_LEVEL`
  (dict: the minimum `GMLevel` required to submit each kind — Decision 9),
  `TableRequestKind` (PROFILE_TEXT/DISTINCTION_CHANGE), `TableRequestStatus`
  (PENDING/APPROVED/REJECTED/WITHDRAWN/COMPLETED), `TableRequestRole` (MINE/GM)
- **Table update requests (#2631, ADR-0155):** `TableUpdateRequest` (FK
  `GMTableMembership` — table-routed by design: no table → no requests; `kind`,
  `player_reasoning`, `status`, `gm_notes`, `resolved_by`, timestamps) with 1:1 payload
  models `ProfileTextRequestDetails` (`field`, `proposed_text`, `applied_version` →
  `character_sheets.ProfileTextVersion`) and `DistinctionChangeRequestDetails`
  (`action`, `distinction`/`character_distinction`, `sheet_update_request` →
  `distinctions.SheetUpdateRequest`). Services:
  `submit_profile_text_request`/`submit_distinction_change_request`,
  `signoff_table_update_request` (prose applies immediately; distinction
  creates-and-approves a #2628 `SheetUpdateRequest` — XP auto-debits — both →
  COMPLETED), `withdraw_table_update_request`, `gm_may_review_for_persona` (the
  #2631 review-pool rule: staff or any GM whose table the persona actively sits at;
  also gates the #2628 `review_sheet_update` action).
  API: `TableUpdateRequestViewSet` (`/api/gm/table-update-requests/`, actions
  `signoff`/`withdraw`, FilterSet `status`/`kind`/`role`)
- **Types (`types.py`):** `GMEvidenceSummary` (dataclass: `profile_id`, `level`,
  `approved_at`, `last_active_at`, `stories_running`, `beats_completed_by_risk`,
  `feedback_by_category`, `level_changes`), `CategoryFeedback` (`category_name`,
  `average_rating`, `rating_count`), `DiscoveryResult` (#3564: `templates`,
  `challenges`, `kinds: list[KindResult]`, what `find_situations` returns and
  both its faces render), `KindResult` (`kind`, `check_fits`,
  `difficulty_guide` (the guide for the requested risk or `None`),
  `all_guides` (the full ladder), `pool_guides`)
- **Key Services (`services.py`):** `create_table`/`archive_table`/`transfer_ownership`,
  `join_table`/`leave_table` (auto-detaches CHARACTER-scope stories on leave),
  `gm_application_queue(gm)`/`approve_application_as_gm`/`deny_application_as_gm`,
  `surrender_character_story`, `create_invite`/`revoke_invite`/`claim_invite`
  (`select_for_update`-raced), **`promote_gm(profile, new_level, *, changed_by, reason) ->
  GMLevelChange`** — the only path that writes `GMProfile.level`; raises `ValueError` on
  same-level or unknown-level input (programmer-error guard, real validation lives in
  `PromoteGMInputSerializer`), **`gm_evidence_summary(profile) -> GMEvidenceSummary`** —
  aggregate track record (stories running, beats completed by risk, feedback by trust
  category, level-change audit trail) backing a staff promotion/demotion decision,
  **`award_gm_story_reward(*, gm_profile, players_served, per_player_xp, event_cap,
  description) -> XPTransaction | None`** (#2123) — the single choke point for GM Story
  Reward XP: `raw = min(per_player_xp * players_served, event_cap)`, further truncated by
  `GMRewardConfig.weekly_reward_cap` headroom in `GMWeeklyRewardTracker` for the current
  `GameWeek`; awards via `progression.award_xp(reason=ProgressionReason.GM_STORY_REWARD)`.
  Never raises — a bug here logs and returns `None` rather than aborting the beat
  mark/episode resolve/story completion/feedback submission that triggered it.
  **`find_situations(*, query, risk, actor_level_index) -> DiscoveryResult`**
  (#3564): the one catalog search behind telnet `setsituation find` and
  `GET /api/gm/discovery/`; kinds always come from `SituationKind.objects
  .cached_all()` filtered to `actor_level_index`, templates and challenges only
  when `query` is non-empty (capped `FIND_RESULT_LIMIT = 15`), fits/guides/pool
  guidance loaded with three grouped `filter(situation_kind_id__in=...)`
  queries rather than a `to_attr` prefetch onto the identity-mapped kinds
  (ADR-0263). **`user_breadth_index(user) -> int`**: the web caller's
  `find_situations` breadth: staff get the top index, a GM their own level
  index, an account with no `GMProfile` get `0`; mirrors
  `FindSituationAction._actor_breadth_index` for a request user rather than an
  actor object.
- **Trust-ladder consumers:** `cap_for_profile(profile) -> GMLevelCap | None`
  (`world.gm.services`, #3562) is the single `GMLevelCap.objects.get(level=profile.level)`
  lookup - `None` when the level is unseeded, never raises. `stories.BeatSerializer`'s risk
  gate (`gm_max_risk`, `world.gm.services`) and `stories.StakeSerializer`'s custom-stakes/
  global-scope gates (`_gm_allows_custom_stakes`/`_gm_allows_global_scope`,
  `world.stories.serializers`) all delegate to it instead of re-deriving the query (staff
  bypass unchanged, handled by each caller); `stories.StakeRewardLineSerializer`'s
  ITEM-sink gate (`_gm_allows_item_rewards`, #3566) does the same;
  `combat.StakesLevelRequirement.minimum_gm_level`
  gates on `gm_account.gm_profile.level` directly (no profile → STARTING). `GMProfileMineSerializer`
  (below) also reads it to surface the caller's own cap on the wire.
- **API Endpoints:** `GMApplicationViewSet` (`/api/gm/applications/`; create for
  players, list/review/update for staff — approval auto-creates a `GMProfile`),
  `GMProfileViewSet` (`/api/gm/profiles/`, read-only list for any authenticated user;
  `POST /api/gm/profiles/{id}/promote/` and `GET /api/gm/profiles/{id}/evidence/`, both
  `IsAdminUser`; `GET`/`PATCH /api/gm/profiles/mine/` (#3478) — the requesting account's
  own `GMProfile` via `GMProfileMineSerializer`, `contact_times`/`ooc_info` writable,
  `level` read-only, 404 for a non-GM account. **`max_beat_risk`/`allow_custom_stakes`
  (#3562)** are read-only `SerializerMethodField`s built from `cap_for_profile` - staff
  get `RenownRisk.EXTREME`/`True` regardless of any cap row, a non-staff GM gets its own
  `GMLevelCap.max_beat_risk`/`allow_custom_stakes` (`RenownRisk.NONE`/`False` when the
  level is unseeded); a PATCH body naming either field is silently ignored
  (`SerializerMethodField` is never writable). The beat-authoring frontend
  (`useGMProfileMine`, `frontend/src/gm/queries.ts`) reads this payload to build its
  risk-select options and stakes-picker gating from the same ceiling the API enforces,
  instead of a client-side guess; `POST /api/gm/profiles/character/` (#3478)
  mints the account's own GM/Staff character via `mint_gm_character`
  (`world.roster.services.staff_characters`, role-aware: staff mints
  `typeclasses.gm_characters.StaffCharacter`, an approved GM mints `GMCharacter`, anyone
  else refused; one GM/Staff character per account, enforced via an active
  `RosterTenure` on an existing GM/Staff-typeclassed character), returning
  `character_id`/`name`, a `StaffMintError` surfacing as 400 — both typeclasses'
  `get_display_name` append an unconditional `(GM)` tag
  (`typeclasses/gm_characters.py`'s `_MechanicallyImmuneCharacterMixin`)), `GMTableViewSet`
  (`/api/gm/tables/`; staff sees all, GMs their own,
  players tables where an active persona holds membership; `archive`/`transfer_ownership`
  staff-only actions), `GMTableMembershipViewSet`, `GMRosterInviteViewSet`,
  `GMApplicationQueueView`/`GMApplicationActionView` (a GM's own pending-application
  queue), `GMInviteClaimView`, `DemandRansomView`, `GMSummonOfferViewSet`
  (`/api/gm/summon-offers/`, read-only, #3071, see "GM summon" below),
  `DiscoveryView` (`GET /api/gm/discovery/?q=&risk=`, `IsAuthenticated` +
  `IsGMOrStaff`, #3564: the web GM panel's and beat form's catalog browse;
  invalid `risk` 400s, empty `q` returns kinds only, see "Scenario catalog"
  below). **UI-wired
  (#3268):** the invite/application group (`GMRosterInviteViewSet`,
  `GMApplicationQueueView`/`GMApplicationActionView`) renders in `RecruitmentTab` on
  `frontend/src/tables/pages/TableDetailPage.tsx`; `GMInviteClaimView` renders in
  `frontend/src/tables/pages/ClaimInvitePage.tsx` (route `/invites/claim`); the
  `character_creation` app's `finalize-gm` draft action renders in
  `FinalizeForTableDialog` off the CG Review stage (see character_creation.md).
  `GMDashboardView` (`GET /api/gm/dashboard/`) payload gained `pending_applications`
  (count from `gm_application_queue(gm)`) and `open_invites` (this GM's unclaimed,
  unexpired `GMRosterInvite` rows) as the tile source for those same recruitment
  surfaces (#3268).
- **GM onboarding lives on the Hall (#3478):** the Hall's GM slot
  (`frontend/src/home/hall/GMSlot.tsx`) is the sole surface for both
  `mine`/`character` endpoints above — `CreateGMCharacterDialog` mints via
  `mintGMCharacter`, `EditGMProfileDialog` edits `contact_times`/`ooc_info`; the slot
  hides its edit affordance rather than rendering the 404 for a staff account with no
  `GMProfile` row. **This replaced the world-builder page's inline mint form**
  (`mint-builder-character`, #3283's original staff-only stopgap): that endpoint and
  its frontend caller (`mintBuilderCharacter`, `frontend/src/world-builder/api.ts`)
  are deleted; `WorldBuilderPage`'s no-actor banner
  (`data-testid="world-builder-actor-banner"`) became a plain "set up your GM Profile
  from the Hall" message linking to `/` — until #3538 retired `WorldBuilderPage`
  entirely (the Atlas, #3477/#3533, replaced the grid-first canvas). See
  `docs/roadmap/tooling.md`'s "GM onboarding moves to the Hall" entry and
  `gm-system.md`'s Phase 9.
- **Telnet:** `CmdGMTable` (`gmtable`) — table admin parity. `CmdGMTrust` (`gmtrust`,
  #2000) — `gmtrust show [account]` (self-service; naming another is staff-only),
  `gmtrust evidence <account>` (staff-only), `gmtrust promote <account>=<level>
  reason=<why>` (staff-only; `reason` required) — thin over the same `promote_gm` /
  `gm_evidence_summary` services the web actions call. `gm dashboard` gains an
  "Open group requests: N" line + `gm claim <request-id>` (#2119), dispatching
  `stories.ClaimGroupStoryRequestAction`.
- **Adjudication toolkit (#2118, ADR-0110):** `IsSceneGMPrerequisite` (`actions/prerequisites.py`
  — staff bypass, else `Scene.is_gm(actor.active_account)` on the actor's active scene) gates
  three catalog-only Actions in `actions/definitions/gm_adjudication.py`:
  `InvokeCatalogCheckAction` (key `gm_invoke_check` — invokes an authored `CheckType` at a
  `DifficultyChoice` band via `perform_check`, plus a `find`/list catalog-search mode; never an
  integer difficulty or a consequence-pool reference; #2857: gated on
  `MinimumGMLevelPrerequisite(GMLevel.SENIOR)` — a staff/senior stopgap; JUNIOR/STARTING
  player GMs are funneled to `SetSituationAction`), `GMAwardAction` (key
  `gm_award_progression` — `award_xp`/`award_development_points` with
  `ProgressionReason.GM_AWARD`, gated additionally on `MinimumGMLevelPrerequisite(GMLevel
  .JUNIOR)`; `award_type="favor_token"` (#2428) mints a Golden Hare from an org via
  `currency.mint_favor_token`, resolving `org_ref` pk-or-name against `societies.Organization`
  and requiring a non-empty `description` as the token's `provenance_note`; two more kinds
  (#3055 slice 1c) write the acquisition-provenance ledger: `award_type="stat"` raises an
  authored `Trait` (must be `TraitType.STAT`) by one display dot via
  `progression.award_stat_raise`, writing a `traits.CharacterTraitChange` with
  `source=GM_GRANT` and `granting_tenure` set to the GM's own current tenure (`None` for a
  staff-piloted GM); `award_type="technique"` mints a `Technique` via the shared
  `magic.learn_technique` seam, passing `origin=AcquisitionOrigin.GM_GRANT` and
  `source=AccessChangeSource.GM_AWARD` with `ap_cost=0` for an immediate mint),
  `GMApplyConditionAction` (key `gm_apply_condition` — `apply_condition` against an
  authored `ConditionTemplate` via `get_by_name`, same JUNIOR floor). Telnet: `gm check [find
  <term>]` / `gm check <char> <check-type>=<band> [edge=<reason>|setback=<reason>]`, `gm award
  <char> xp=<amount>|dev=<trait> amount=<n>|hare=<organization> reason=<text>|stat=<trait>|
  technique=<name>`, `gm condition <char>
  condition=<name> [severity=<n>] [duration=<n>] [note=<text>]` (`commands/gm_ops.py`'s
  `CmdGMDashboard`). **Web (#3070):** `GMAdjudicationPanel`
  (`frontend/src/scenes/components/`), gated on `scene.viewer_can_gm`, rendered on the
  scene detail page. Dispatches `gm_invoke_check`/`gm_award_progression`/
  `gm_apply_condition` (plus `set_situation`/`place_challenge`, below) directly over
  the generic REGISTRY REST dispatch seam (`useDispatchPlayerAction` ->
  `POST /api/actions/characters/{id}/dispatch/`) — mirroring
  `PersonaContextMenu.tsx`'s `challenge`/`identify` items, since none of these five
  actions carry an `ActionTemplate` and so are absent from `get_player_actions`. The
  REST dispatch path does no ObjectDB resolution of its own (`objectdb_target_kwargs`
  only helps the websocket inputfunc), so `_resolve_gm_target`
  (`actions/definitions/gm_adjudication.py`) resolves the `target` kwarg from either
  an already-resolved `ObjectDB` (telnet) or a plain int pk (the web panel sends the
  target character's id — a `CharacterSheet`'s pk equals its owning `ObjectDB`'s pk).
  Catalog pickers: `checks.CheckTypeViewSet` (new, `GET /api/checks/check-types/`,
  `IsGMOrStaff`, `search`/`category` filters, excludes inactive and
  per-character-synthesized rows) for Call Check; the pre-existing
  `conditions.ConditionTemplateViewSet` (`/api/conditions/templates/`),
  `mechanics.SituationTemplateViewSet`/`ChallengeTemplateViewSet`
  (`/api/mechanics/situation-templates/`/`challenge-templates/`) for Condition and
  Situation/Challenge placement, reused as-is.
- **GM summon (#3071):** ruled 2026-08-08 — a GM may move a party mid-session, but only
  WITH consent, and only into a scene they actually run. `SummonPlayerAction` (key
  `summon_player`, `actions/definitions/gm_adjudication.py`) is gated the same as
  `GMAwardAction`/`GMApplyConditionAction` (`IsSceneGMPrerequisite` +
  `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`) and creates/replaces a `gm.GMSummonOffer`
  row naming the target, the GM's current room, and their active scene (a summon does not
  stack — re-summoning the same target just refreshes the invite). It does NOT move anyone
  itself. The target responds via `AcceptGMSummonAction`/`DeclineGMSummonAction` (keys
  `accept_gm_summon`/`decline_gm_summon`, `actions/definitions/gm_summon_offers.py`,
  `target_type=SELF`, no GM gating — a player always decides their own consent); accept calls
  `world.gm.services.resolve_gm_summon_offer(offer, accept=True)`, which moves the target's
  ObjectDB via `move_to()` to the offer's room and deletes the row either way (row existence
  IS pending status, mirroring `PendingCast`/`PendingAudereOffer` rather than
  `DuelChallenge`'s status-enum shape). Leak analysis: the consent prompt names the GM
  (`gm_display_name`, a snapshot taken at offer time — never a live account-username walk)
  and the scene title only, never room contents or other occupants.
  **Telnet:** `gm summon <character>` (`commands/gm_ops.py`'s `CmdGMDashboard`) resolves the
  target GLOBALLY (`caller.search(name, global_search=True)`, unlike every other `gm`
  subverb's room-scoped `_resolve_target` — the target need not be co-located, that's the
  point of a summon); `accept summon` / `decline summon` route through
  `GMSummonPendingHandler` (`world/gm/offer_handlers.py`, registered in `world/gm/apps.py`'s
  `ready()`), the offer-registry pattern the soulfray/crossing/surge handlers use
  (`commands/offer_registry.py`).
  **Web:** `GET /api/gm/summon-offers/` (`GMSummonOfferViewSet`, read-only, mirrors
  `DuelChallengeViewSet`'s account-scoped-inbox shape — `pagination_class = None`, at most
  one pending offer per played character) backs `SummonPromptNotifier`
  (`frontend/src/gm-adjudication/SummonPromptNotifier.tsx`, mounted once at the app root
  alongside `DuelChallengeNotifier`/`HazardPromptNotifier`/`ConsentAttentionNotifier`) — a
  15s-polled toast with inline Accept/Decline dispatching `accept_gm_summon`/
  `decline_gm_summon` over the generic REGISTRY REST seam. `GMAdjudicationPanel` also gained
  a Summon tab reusing the existing `ParticipantPicker` (scene participants only — an
  arbitrary off-scene target needs a global character-search affordance the panel doesn't
  have yet; telnet's `gm summon <character>` has no such limit).
- **GM fiat levers mid-combat (#3387):** three adjacent gaps flagged in the 2026-08-26
  combat audit, ruled the same session. (1) **Edge/Setback** — two curated
  `ConditionTemplate` rows (`world/conditions/gm_edge_content.py`,
  `ensure_gm_edge_content()`, wired into `ensure_conditions_content()`) applied through
  the existing `gm_apply_condition` lever, no new mechanism: `default_duration_type=ROUNDS`,
  `default_duration_value=1` (expires at that round's own end-of-round tick, so it covers
  every check made in the round it's applied to), one `ConditionCheckModifier` each scoped
  to `check_category=Combat` (±10, `scales_with_severity=True`). `GMAdjudicationPanel`'s
  Condition tab gained "Quick Edge"/"Quick Setback" buttons dispatching `gm_apply_condition`
  with only `target`/`condition_ref` set, falling back to the template's authored defaults.
  (2) **Manual dramatic beat** — `GMTriggerDramaticBeatAction` (key
  `gm_trigger_dramatic_beat`, `actions/definitions/gm_combat.py`), gated
  `MinimumGMLevelPrerequisite(GMLevel.SENIOR)` (staff bypass) alongside the encounter's
  scene-GM/staff check (`_active_encounter_for_gm`) — the first `gm_combat.py` action to
  combine both. Resolves the target `CombatParticipant` by `character_sheet_id=target.pk`
  (the ObjectDB/CharacterSheet shared-pk O2O) — deliberately NOT
  `_resolve_participant_in_encounter`'s string lookup, whose digit branch treats a numeric
  string as a participant pk, not a character pk. Requires a non-empty `reason`, calls
  `apply_dramatic_surge(..., trigger_kind=SurgeTriggerKind.GM_MANUAL, subject_sheet=None,
  reason=reason)` with `amount=encounter.escalation_curve.spike_intensity_amount` (fallback
  `2`); a repeat trigger on the same character is `DramaticSurgeRecord`'s existing dedup
  no-op, surfaced as a distinct refusal rather than a silent success. Telnet: `gm dramatic
  <character> reason=<text>` (`commands/gm_ops.py`'s `CmdGMDashboard`). Web:
  `GMAdjudicationPanel` gained a Dramatic Beat tab (reason `Input` + submit; server-side
  Prerequisite is the only gate, no client-side trust check). (3) **Situation declaration —
  no override, by design:** recorded as ADR-0240 rather than built; GM tooling investment
  goes toward making state genuinely true (positioning #3385, encounter settings #3383).
- **GM web parity: Grant Item, Stage, Traps tabs + condition removal (#3431):** the
  2026-08-28 GM storytelling-tools audit found `grant_item`, `stage_prop`/
  `stage_property`, and `list_room_traps`/`arm_trap`/`gm_disarm_trap` `[BUILT &
  WIRED]` on telnet only (zero web callers), and GM condition *removal* fully
  `[ABSENT]` (`GMApplyConditionAction` had no off-switch). **Backend (one new
  pair, `actions/definitions/gm_adjudication.py`):** `GMRemoveConditionAction`
  (key `gm_remove_condition`) — gated identically to `GMApplyConditionAction`
  (`IsSceneGMPrerequisite` + `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`);
  resolves `target` via `_resolve_gm_target`, `condition` (a template name, but
  resolved against the target's own ACTIVE `ConditionInstance`s via
  `get_active_conditions` — refuses when the target doesn't currently carry it,
  unlike `remove_condition_by_name`'s silent no-op), and a required `reason`
  echoed in the result message (no persisted field — `remove_condition` carries
  no note/description of its own). `GMListConditionsAction` (key
  `gm_list_conditions`, same gates) returns the target's active instances
  (template name, severity, `rounds_remaining`, `expires_at`) as result data —
  the `list_room_traps` pattern (a REGISTRY dispatch, not a ViewSet) — because no
  read path exposes this to a GM: `CharacterConditionsViewSet` is self-only and
  its `observed` action filters to `is_visible_to_others=True`, hiding a GM's own
  fiat-applied hidden conditions from the GM who applied them. Telnet: `gm
  condition remove <character> condition=<name> reason=<text>` extends
  `CmdGMDashboard`'s existing `gm condition` subverb (`commands/gm_ops.py`).
  **Frontend:** `GMAdjudicationPanel` gained three tabs, all thin dispatches over
  the pre-existing telnet-only actions above, plus a Remove mode on the Condition
  tab: **Grant Item** (participant picker + a searchable `ItemTemplateViewSet`
  select feeding `template_name`, dispatching `grant_item` with `target_name`
  resolved from the picked participant's persona display name — that action
  resolves its target by `actor.search()`, not pk, a telnet-era shape this spec
  didn't change); **Stage** (prop mode → `stage_prop` with `item_template`;
  property mode → `stage_property` with a free-text `property` name — no
  `Property` enumeration endpoint exists and none was added — and an optional
  `target_id` from the shared participant picker, omitted to tag the room
  itself); **Traps** (mounts-on-open dispatch of `list_room_traps` — Radix
  `Tabs.Content` unmounts inactive tabs, so "on mount" is "on open" — rendering
  its result-data rows with per-row Arm/Disarm buttons dispatching
  `arm_trap`/`gm_disarm_trap` then refreshing the list); **Condition → Remove**
  (participant picker feeds `gm_list_conditions` to populate an active-instance
  select, then dispatches `gm_remove_condition` with the picked template name +
  a required reason).
- **Pool opacity split between vitals and anima (#3071 superseded for vitals by #3434,
  2026-08-29):** the two views no longer match. `CharacterAnimaViewSet.get_queryset`
  (`world/magic/views.py`) stays staff-or-own-tenure only - no `viewer_can_gm` carve-out -
  per the original 2026-08-08 #3071 ruling: a scene's GM narrates off public wound text
  (badges, pose descriptions) and what a character chooses to show, not raw anima
  numbers. This is least-privilege BY DESIGN for anima, not a gap that got missed - its
  `get_queryset` carries a docstring pointing back here so a future agent doesn't "fix"
  it without a fresh ruling. `CharacterVitalsView._can_view` (`world/vitals/views.py`)
  gained a narrower carve-out (#3434, the fresh ruling #3071 asked for): staff, own
  tenure, OR the GM of an active non-battle scene at the character's location, at JUNIOR+
  GM trust (`HasGMTrust`), with the target actually present in that scene right now
  (`Scene.has_character_present` - location-derived, not participation-derived, so a
  participant who steps out of the room drops out of the carve-out). Matches the parity
  combat already grants via `CombatParticipantSerializer._can_view_vitals`
  (`world/combat/serializers.py:285`). Feeds the GM story rail (#3434,
  `GET /api/scenes/{id}/gm-rail/`, see `docs/systems/scenes.md`'s "API Endpoints"
  section) as one of its per-participant sections.
- **Scenario catalog (#2127, ADR-0110):** extends the same "discovery, never invention"
  shape from checks to situations. Since #3564 the search itself lives in one
  service, `find_situations` (`world.gm.services`), behind two faces:
  `FindSituationAction` (key `gm_find_situation`, read-only, gated
  `MinimumGMLevelPrerequisite(GMLevel.STARTING)`, lower than
  `SetSituationAction`'s JUNIOR floor since browsing mutates nothing) formats
  the result for telnet, and `DiscoveryView` (`GET /api/gm/discovery/`) formats
  it for the web; both search `mechanics.SituationTemplate`/`ChallengeTemplate`
  by name/description(/goal) and, independently by the same term, any matching
  `SituationKind`, returning its `CheckTypeSituationFit`,
  `SituationDifficultyGuide`, and `ConsequencePoolGuide` rows (text on telnet,
  structured JSON on the wire). An empty query is a kind-first cold open:
  every kind in breadth, no templates or challenges, on both faces.
  `SituationKind` results are filtered server-side on `minimum_gm_level` against the
  caller's own `GMLevel` (staff see everything) — a kind above a GM's tier never
  appears, even on an exact name match. `SubmitCatalogSuggestionAction` (key
  `gm_submit_catalog_suggestion`, same STARTING floor) creates a `CatalogSuggestion`
  via `world.gm.services.submit_catalog_suggestion`, gated additionally on
  `PROPOSAL_KIND_MIN_LEVEL[proposal_kind]` (Decision 9) — refuses a below-tier
  `proposal_kind` with a level-appropriate message; staff bypass every gate. Both
  actions live in `actions/definitions/gm_catalog.py`. Telnet: `setsituation find
  <term>` (extends `commands/setsituation.py`, mirroring `gm check find`'s
  shape) and `gm suggest <kind>=<text>` (`commands/gm_ops.py`'s
  `CmdGMDashboard`, kind one of
  `new_situation`/`check_fit`/`difficulty_guide`/`pool_guide`/`other`). **Web
  (#3564):** `DiscoveryView` (`IsAuthenticated` + `IsGMOrStaff`) backs
  `SituationFinder.tsx` (`frontend/src/gm-adjudication/`), which renders kind
  cards (fits, difficulty guide, pool guidance always marked advisory) plus
  templates and challenges, with host-injected Stage/Place/Use-this-check
  buttons and a "Suggest an entry" dialog (`CatalogSuggestionDialog.tsx`,
  dispatches `gm_submit_catalog_suggestion`) shown only when a character is
  active. Three hosts embed it behind a "Browse the catalog" toggle: beat
  prep's staged-templates editor (`StagedTemplatesEditor` in
  `stories/components/BeatFormDialog.tsx`, Stage appends a row), the scene
  panel's Situation tab below (one-click Place), and its Call Check tab
  (a fitting check selects it and pre-fills the difficulty band from the
  guide for the running beat's risk, `GMAdjudicationPanel`'s
  `scene.running_beat?.risk`; the same running beat may also carry a scene
  clock, `scene.clock` - see "Scene clock (#3567)" below). Suggestion inbox: `SubmissionCategory
  .CATALOG_SUGGESTION` (`world.player_submissions.constants`) +
  `_catalog_suggestion_to_item` in `world.staff_inbox.services.get_staff_inbox`,
  mirroring `GMApplication`'s exact mapping shape (Decision 8); staff triage via
  `CatalogSuggestionViewSet` (`/api/gm/catalog-suggestions/`, list/retrieve/update,
  `IsAdminUser` — no create route, creation only through the Action). Starter
  taxonomy (Chase/Negotiation/Infiltration + a `SituationDifficultyGuide` row per
  `RenownRisk` tier) provided by `world.gm.factories.seed_catalog_starter_content`,
  composed into the `"gm"` cluster seeder alongside `seed_default_gm_level_caps`.
  **Since #2865 that taxonomy is content-repo-owned**: `gm.situationkind`,
  `gm.checktypesituationfit`, `gm.situationdifficultyguide` and
  `gm.consequencepoolguide` are registered in `CONTENT_MODELS` (natural keys added
  to the latter three), so `seed_catalog_starter_content` looks rows up via
  `authored_or_sample` and invents only under `SEED_SAMPLE_CONTENT` (ADR-0168).
  `mechanics.situationtemplate`/`situationchallengelink`/`situationtraplink` are
  registered too — the situation catalog was previously unexportable even once
  authored.
- **Quick challenge placement (#2865, ADR-0110):** `PlaceChallengeAction` (key
  `place_challenge`, `actions/definitions/situations.py`, gated
  `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)` — same floor as `SetSituationAction`,
  it mints the same class of live row per ADR-0091) places ONE authored
  `mechanics.ChallengeTemplate` against a GM-named target object, minting a
  standalone `ChallengeInstance` (`situation_instance=None`) through the pre-existing
  `instantiate_challenge`. The one adaptation permitted is a one-band shift with a
  required reason, persisted as `ChallengeInstance.severity_adjustment` /
  `adjustment_reason` (two DB `CheckConstraint`s; GM-facing only, never in
  `ChallengeInstanceSerializer`) and read back through the new
  `ChallengeInstance.effective_severity`. Band-shift helpers are shared with
  `InvokeCatalogCheckAction` via `actions/definitions/gm_shift.py`.
  `FindSituationAction` also searches `ChallengeTemplate` now, so one browse surface
  covers both placement verbs. Telnet: `setsituation challenge
  <template>=<target name> [edge=<why>|setback=<why>]`. **Web (#3070):**
  `GMAdjudicationPanel`'s Situation tab dispatches `set_situation`
  (`situation_template_id`) or `place_challenge` (`challenge_template_id` +
  `target_object_name` + optional edge/setback) the same generic REST way as the
  check/award/condition tabs above — both act on the GM's own room
  (`target_type=SELF`), so this tab has no participant picker. **Since #3564**
  the same tab embeds `SituationFinder` behind a "Browse the catalog" toggle;
  choosing a template or challenge card there dispatches the same
  `set_situation`/`place_challenge` one-click, with an empty challenge target
  refused server-side rather than client-validated. Two fold-ins:
  `ChallengeTemplate.severity` is re-expressed in `DIFFICULTY_VALUES` points (default
  `1` → `45`; it feeds `perform_check`'s `target_difficulty` directly, so the old
  scale resolved every authored challenge at the bottom rank), and
  `instantiate_challenge` now honours `discovery_type` instead of hardcoding
  `is_revealed=True`, which silently defeated `DiscoveryType.DISCOVERABLE`.
- **Story areas & story rooms (#2450, epic #2436 slice 3, ADR-0141):** a GM's own
  build-and-run space, layered on the #2436/#2449 grid substrate. Models:
  `StoryArea` (sidecar per ADR-0010 — `gm.StoryArea.area` OneToOne to a
  `GridOrigin.STORY` `Area`, `gm` FK; row survives a staff promotion to AUTHORED as
  provenance, but cap counting filters `area__origin=STORY` so a promoted area stops
  counting), `StoryRoomGrant` (consent-first join grant: `room`
  (`evennia_extensions.RoomProfile`) + `character` + `granted_by`, unique
  `(room, character)`; `return_location` captured at join, cleared on leave — gates
  the JOIN only, walking inside rides ordinary exits, ADR-0141), `GMLevelCap
  .max_story_areas`/`max_story_rooms_per_area` (per-level caps, #2450),
  `instances.InstancedRoom.gm_owner` (nullable FK — a temp scene room a GM spun up
  rather than a mission/player instance). `world.instances.services
  .spawn_instanced_room` gained a `gm_owner` kwarg and now always forces
  `RoomProfile.is_public=False` regardless of the model default, so no instanced
  room (GM scene room, mission room, captivity cell) can leak into public listings.
  **Services (`world.gm.story_services`):** `create_story_area`/`remove_story_area`
  (cap-checked create, empty-only remove), `story_room_cap_check` (raises before a
  dig would exceed `max_story_rooms_per_area`), `grant_story_room`/
  `revoke_story_room` (idempotent grant create; revoke returns an in-room character
  first, via `_return_character`, then deletes the row), `join_story_room`/
  `leave_story_room` (the character's own move, captures/consumes
  `return_location`), `spin_up_scene_room`/`close_scene_room` (temp-room lifecycle
  over `world.instances.services`; `close_scene_room` is deliberately
  non-atomic and retryable — `move_to` has non-DB side effects a DB rollback can't
  undo, so a blocked return leaves the grant/instance alone rather than faking
  atomicity). **Actions (`actions/definitions/story_builder.py`, 15 REGISTRY
  keys):** category `story_builder` (GM-authored, `MinimumGMLevelPrerequisite
  (STARTING)`, staff bypass) — `create_story_area`/`edit_story_area`/
  `remove_story_area`, `story_dig_room`/`story_edit_room`/`story_remove_room`,
  `story_link_rooms`/`story_unlink_rooms`/`story_place_room`,
  `grant_story_room`/`revoke_story_room` (resolves either a story-area room or an
  active GM-owned temp room), `spin_up_scene_room`/`close_scene_room`; category
  `story_rooms` (player-side, no GM standing required — authorization is the grant
  itself) — `join_story_room`/`leave_story_room`. Story rooms dug via
  `story_dig_room` are always `origin=STORY`, `is_public=False`, and never carry a
  `fixture_key`. `world.areas.grid_services` gained two public helpers
  (`has_character_occupants`/`has_non_exit_contents`) so the story-builder module's
  stranding/occupancy guards don't reach into private members. **Telnet**
  (`commands/story_rooms.py`, play verbs only — canvas authoring stays web-only per
  epic Decision 2): `sceneroom <name> = <description>` / `sceneroom close <#id>`
  (GM lifecycle, thin over `SpinUpSceneRoomAction`/`CloseSceneRoomAction`),
  `joinroom [<#id>|<name>]` (bare form lists the caller's own grants),
  `leaveroom`. **API:** `StoryBuilderViewSet` (`/api/gm/story-areas/`,
  `IsGMOrStaff`, read-only — mutations go through action dispatch) reuses
  `world.areas.builder_views.area_manager_payload` (extracted from
  `WorldBuilderViewSet.manager`, #2449) for `GET .../<id>/manager/`, attaching
  per-room `grants` (granted character names); `GET .../instances/` lists the
  caller's active GM-owned temp scene rooms (staff: all), unpaginated. STORY-origin
  areas/rooms are excluded from `AreaViewSet`/`RoomProfileViewSet` (the
  player-facing grid API) even when `is_public=True` on the room —
  `evennia_extensions.models.room_is_publicly_listed` treats any
  `GridOrigin.STORY` room as never publicly listed, defense in depth alongside the
  area-level exclusion. Frontend: `/gm/story-builder`
  (`frontend/src/story-builder/`) on the shared `map-canvas/` + world-builder
  components, with a story-specific tool palette. **Player web join surface
  (#2450 spec Decision 1 fix):** `MyStoryGrantsViewSet`
  (`/api/gm/my-story-grants/`, `IsAuthenticated`, read-only, paginated
  `LargeResultsSetPagination`) lists the requesting account's own
  `StoryRoomGrant`s (`character__character__db_account=request.user`) with
  `room_id`/`room_name`/`character_id`/`character_name`/`is_inside`/
  `created_at`; `character_id` matters because `join_story_room`/
  `leave_story_room` resolve their actor from `actor.sheet_data` with no
  target-character kwarg, so the frontend must dispatch each row against the
  exact character the grant names. Frontend: `/story-rooms`
  (`frontend/src/story-rooms/`) — a Join/Leave button per grant row,
  dispatching the same `join_story_room`/`leave_story_room` REGISTRY actions
  telnet's `joinroom`/`leaveroom` already used; linked from
  `ProfileDropdown`'s general (non-staff) menu section.
- **GM story-NPC on-ramp (#3426):** `mint_story_npc`
  (`world.roster.services.staff_characters`) — JUNIOR+ `GMProfile` (staff bypass) +
  the new `GMLevelCap.max_story_npcs` per-level cap (most-restrictive/refuse when
  unconfigured; enforced by the shared `check_story_npc_cap`), delegating to
  `_mint_character_working_set` for the working set (#3283 — Character + sheet +
  PRIMARY persona + NPC-shelf `RosterEntry` + active `RosterTenure` binding it to
  the GM's own account, the same tenure the persona picker and telnet `@ic` key
  on). `description` writes `CharacterSheet.additional_desc` via
  `set_physical_description`. In-scope bugfix: `_mint_character_working_set`'s
  shelf lookup re-keyed from `name="NPC"` to `roster_type=RosterType.NPC` (unique;
  `roster/seeds.py`'s seeded shelf is named "NPCs", so the old lookup missed it and
  collided on create). Heavyweight sibling: `finalize_gm_character(draft,
  claim_as_npc=True)` (`world.character_creation.services`) lands a full-CG
  character on the NPC shelf with the same tenure hand-off instead of tenure-less
  on Available, gated by the same `check_story_npc_cap`. **Action + telnet:**
  `MintStoryNPCAction` (key `mint_story_npc`, `actions/definitions/gm_npcs.py`,
  `MinimumGMLevelPrerequisite(JUNIOR)`); `gm npc <name>[=<description>]`
  (`CmdGMDashboard`, `commands/gm_ops.py`). **API:**
  `CharacterDraftViewSet.finalize_gm`'s `claim_as_npc` body flag;
  `FinalizeForTableDialog`'s matching checkbox. **Leak fix:** `RosterEntryViewSet`
  (`AllowAny`) now excludes `RosterType.NPC` entries from its general queryset
  (staff and the entry's own tenure holder still see them) — previously
  individually reachable even though `RosterViewSet` already hid the shelf itself.
  Frontend: a "My NPCs" block on `GMDashboardPage` + a mint dialog. See
  `docs/systems/npc-lifecycle.md`'s "GM story-NPC on-ramp" section for the full
  rundown and how this relates to the ambient-NPC ladder.
- **Story-NPC statline presets (#3427):** `NPCStatlinePreset`
  (`world.roster.models`, `NaturalKeyMixin + CreditedContent`, registered in
  `CONTENT_MODELS` — staff-authored catalog, GMs select but never edit values,
  ADR-0176 intact) + its child rows `NPCPresetTraitLine`
  (STAT trait, display-scale 1-10) / `NPCPresetSkillLine` (SKILL, true 1-100),
  unique per (preset, trait)/(preset, skill), admin page with two inlines.
  `apply_npc_preset(sheet, preset)` (beside `mint_story_npc`) mirrors CG
  finalize's write shape exactly (`_create_stat_values`/`_create_skill_values`,
  `world.character_creation.services`): trait lines at `display_value *
  STAT_DISPLAY_DIVISOR`, skill lines as a `CharacterSkillValue` plus the #2894
  bridging `CharacterTraitValue` on `skill.trait`, every line stamped with a
  `CharacterTraitChange` (`old_value=0`, `source=TraitChangeSource.NPC_PRESET`).
  Refuses re-application to a sheet already carrying an NPC_PRESET stamp — no
  re-apply path in v1, staff adjust via admin instead.
  `mint_story_npc`/`MintStoryNPCAction` gain a keyword-only/optional `preset`
  (resolved by natural key; unknown name → refusal, no mint). Telnet: `gm npc
  <name>[=<description>] [preset=<name>]` (`CmdGMDashboard`, `commands/gm_ops.py`).
  **API:** `NPCStatlinePresetViewSet` (`/api/roster/npc-presets/`, read-only,
  `IsGMOrStaff`, `SearchFilter` on `name`) feeds a preset `Select` in the #3426
  mint dialog (`GMDashboardPage`). Seed: 3-4 starter presets (Guard, Courtier,
  Innkeeper, Investigator) via `authored_or_sample` in the roster seed cluster
  (`world.roster.seeds.ensure_starter_npc_presets`) — modest values, staff
  rewrite freely.
- **Integrates with:** stories (`GMTable.primary_stories`, risk/custom-stakes gates;
  `GroupStoryRequest.claimed_by` → `GMProfile`, #2119 — claiming creates the GROUP
  Story and seats the covenant via `join_table`; `world.stories.services.gm_rewards`
  (#2123) — `players_served_for_scope`/`credit_gm_story_reward`, called from
  `record_gm_marked_outcome`, `resolve_episode`, `complete_story`, and
  `world.stories.services.feedback.submit_story_feedback` — is the specific side of
  the dependency per ADR-0010; `world.gm` never imports `world.stories` at module
  level), combat (`StakesLevelRequirement
  .minimum_gm_level`), roster (`GMRosterInvite` → `RosterApplication`), scenes
  (`GMTableMembership` pinned to `Persona`, `Scene.is_gm` for the adjudication
  toolkit's gate), checks (`InvokeCatalogCheckAction` → `perform_check`;
  `CheckTypeSituationFit` → `checks.CheckType`), progression (`GMAwardAction` →
  `award_xp`/`award_development_points`;
  `award_gm_story_reward` → `award_xp(reason=ProgressionReason.GM_STORY_REWARD)`, #2123),
  conditions (`GMApplyConditionAction` → `apply_condition`), mechanics
  (`FindSituationAction` → `mechanics.SituationTemplate`, text-search only, no FK),
  actions (`ConsequencePoolGuide.pool` → `actions.ConsequencePool`, advisory only),
  player_submissions/staff_inbox (`CatalogSuggestion` → `SubmissionCategory
  .CATALOG_SUGGESTION`), areas (`StoryArea.area` → a `GridOrigin.STORY` `Area`;
  `world.areas.grid_services` for room/exit CRUD, #2450), evennia_extensions
  (`StoryRoomGrant.room` → `RoomProfile`), instances (`InstancedRoom.gm_owner` →
  `GMProfile`; `spawn_instanced_room`/`complete_instanced_room` back
  `spin_up_scene_room`/`close_scene_room`, #2450)
- **Source:** `src/world/gm/`
- **Glossary:** `src/world/gm/AGENT_GLOSSARY.md`
- **Details:** [../roadmap/gm-system.md](../roadmap/gm-system.md),
  [../adr/0110-gm-content-is-catalog-and-adaptation-never-invention.md](../adr/0110-gm-content-is-catalog-and-adaptation-never-invention.md),
  [../adr/0097-gm-trust-is-gmprofile-level.md](../adr/0097-gm-trust-is-gmprofile-level.md),
  [../adr/0141-story-room-access-is-player-side-join.md](../adr/0141-story-room-access-is-player-side-join.md)

### Beta Reset (#3055 PR 2)
Guarded management command that wipes every play-provenance row back to a pristine
CG/authoring-only baseline at the alpha→beta cutover, filtering on the acquisition-
provenance ledger (ADR-0206). Never an admin surface; four independent guards (hardcoded
constant, one-way DB latch, typed confirmation phrase, verified-fresh-backup precheck)
must all pass before `--execute` touches a row; defaults to a dry-run.

- **Models:** `ReleaseLatch` (`released_at`, `released_by` PROTECT AccountDB, `note`)
- **Services:** `world.beta_reset.services.wipe_pristine_world` /
  `preview_pristine_world_wipe` / `mark_released`; `SCOPE_TABLE` is the introspectable
  per-model delete/filter list (wholesale vs provenance-filtered)
- **Commands:** `arx manage beta_reset [--execute --confirm "..." --backup-verified-at ...]`,
  `arx manage mark_beta_release --released-by <username>`
- **Source:** `src/world/beta_reset/`, `src/world/management/commands/beta_reset.py`,
  `src/world/management/commands/mark_beta_release.py`
- **Details:** [beta_reset.md](beta_reset.md) · ADR-0206 · ADR-0207

### Scenes
Roleplay session recording with participant tracking, interaction logging, persona-based identity, social
action consent flow, and a three-mode non-combat round framework.

- **Models:** `Scene` (incl. `running_beat` FK → `stories.Beat`, nullable, #3425 — the beat this
  scene is currently running, set by `RunBeatAction`/cleared by `finish_scene_full`; see
  stories.md's "Session prep"), `SceneClock` (#3567 - an authored countdown on the beat a scene
  is running: `scene`/`beat` FKs, `size`/`filled`, `closed_at`/`closed_reason`
  (`SceneClockClosedReason`); one open clock per beat (`UniqueConstraint`); see scenes.md's
  "Scene clock" and ADR-0264), `SceneParticipation`, `Persona`, `SceneActionRequest`, `SceneActionTarget`,
  `SceneCastPullDeclaration`,
  **Round framework (#1351):** `SceneRound` (room-anchored non-combat round — `room` FKs
  `evennia_extensions.RoomProfile` since #2608, as do `Place.room` and `SpeakerQueue.room`;
  fields: `mode`
  (`SceneRoundMode`), `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`;
  `mode`/`start_reason` orthogonal — danger rounds are STRICT, ensured via
  `ensure_round_for_acute_condition`, #1466), `SceneRoundDefaultsConfig` (singleton pk=1 — staff-tunable
  defaults: `default_mode`, `advance_quorum_pct`, `max_actions_per_round`, `per_target_repeat_lock`,
  `anti_spam_seconds`, `abandonment_grace_rounds` (#1479: N action-driven beats an abandoned downed
  victim waits before fate resolves; default 2); accessed via `get_scene_round_defaults_config()`),
  `SceneActionDeclaration`
  (per-round ledger; `is_immediate=True` for OPEN/POSE_ORDER actions, `is_immediate=False` for STRICT
  deferred declarations; carries `target_persona` FK; multiple rows per participant per round up to
  `max_actions_per_round`; `succor_target` FK (`SceneRoundParticipant`) + `succor_resolution` (float,
  cached graded outcome) for the scene-round Succor sibling, #1744), `SceneRoundParticipant`,
  `Boon` (#2540, `boon_models.py` — the payload of a structured social ask, 1:1 with its
  `SceneActionRequest`: `kind` (`BoonKind`: MONEY/HELD_ITEM/VAULT_ITEM/DEED/MATERIAL), `amount`,
  `item_instance`, `deed_text`, `fulfilled_at`, `material_category` (nullable FK →
  `items.MaterialCategory`, MATERIAL asks only).
  `character_has_item_pointer(*, sheet, item)` (`boon_services.py`) —
  the exact-pointer predicate for a named-item ask: True when the roster entry holds a
  discovered ITEM-target clue, a KNOWN codex entry, or known secret knowledge naming the
  instance (or its template with no instance pinned) — see `ClueTargetKind.ITEM` and the
  matching `CodexEntry`/`Secret` item-pointer FKs below. **Wired into `validate_boon_ask`
  (2026-08-27 ruling, slice 3):** `_validate_held_item_ask`/`_validate_vault_item_ask` also
  require `character_has_item_pointer(sheet=asker_sheet, item=item)` (`asker_sheet` threaded
  from `create_action_request`'s `initiator_persona`) — a pointer-less ask on a valid,
  target-held item id fails with a neutral message, never revealing whether the item exists.
  `pointer_known_items_for_target(*, asker_sheet, target_persona)` is the boon-options display
  seam: the asker's pointer-known items relevant to one target (held or vault-accessible),
  batched from the asker's own pointers, never a browse of the target's holdings — surfaced as
  `boon-options`' `pointer_items` (requires an `initiator_persona` query param owned by the
  caller, since this reveals private knowledge). **Co-presence gate (2026-08-27 fix wave 3):**
  returns `[]` (200, never an error) unless the asker and target currently share an active scene
  (`_asker_and_target_share_an_active_scene`, reusing `interaction_services.get_active_scene`) —
  `pointer_items` must not become a remote discovery surface for holder identity. Named-item ask
  validation is unaffected; the action-dispatch flow itself does not enforce scene co-presence on
  `target_persona` (verified, not fixed — see `world/scenes/CLAUDE.md`).
  Slice 2 wired the full loop (`boon_services`):
  `BoonAsk` + `validate_boon_ask` (dial-1 ask-time eligibility — an ask the target could not
  grant never exists: penniless-target money, unheld item, empty deed rejected before any row).
  **Money asks are relative sum tiers (#2540 ruling): `BoonSumTier` MINOR/FAIR/GREAT *to the
  target* (PLACEHOLDER pcts of their purse), never raw coppers — nothing to probe a purse with;
  `boon_sum_values` is the UI display seam (tier → concrete coppers, OOC reveal accepted) and
  the coppers freeze onto `Boon.amount` at ask time.** The `boon` action key on
  `BoonAction` (`actions/definitions/social.py`) + `ActionTemplate`/`boon`-consent-category seeds,
  `npc_boon_tier_shift` (the mandatory dial-2 NPC band — for money and material, the chosen tier
  IS the band, fed into
  `resolved_base_difficulty(extra_tier_modifier=…)`; piloted defenders are never band-shifted),
  and the `boon` resolver (`register_resolver`) — fulfillment + the per-Boon stacking affection
  cost (`BOON_AFFECTION_COST`, PLACEHOLDER) fire on BOTH consent paths, never via `execute()`.
  Every kind fulfills: MONEY via `currency.transfer`, VAULT_ITEM via the org vault's audited
  withdraw (target as authority, asker as recipient), HELD_ITEM via a lean sheet-level
  hand-over — unequip → object move/dematerialize → holder switch → `OwnershipEvent(TRANSFERRED)`
  snapshotting the scene's presented personas, MATERIAL via `world.items.gems.buckets`'
  spend/credit pair (amount computed fresh AT FULFILLMENT — tier pct of the target's bucket,
  min 1, never frozen at ask time like money) — and DEED RP-only.
  **MATERIAL kind + honest unavailability (slice 3, #2540):** `BoonAsk.material_category_id` +
  `sum_tier` (reuses money's tier labels; NEVER a computed value — deliberate money asymmetry).
  The boon-options endpoint's `material_categories` is the STATIC public `MaterialCategory` list
  (`[{id, name}]`), never filtered by the target's holdings (a filtered picker would leak wealth
  OOC — the ruling accepts the honest-refusal boolean reveal at ask time instead).
  `check_boon_availability`, called right after `validate_boon_ask`, raises `BoonUnavailable`
  (distinct from `ValidationError`) when a well-formed MATERIAL ask names an empty bucket — for
  BOTH NPC and piloted targets, before any request row exists (no roll, no consent burn, no
  affection drain). `SceneActionRequestViewSet.create` maps `BoonUnavailable` to a 200
  `{"boon_refused": true, "detail": ...}` (non-error UX; chosen over a 400 since the existing
  payload-less-boon guard's 400 has no FE error surface today). **Explicit dispatch (recon trap
  fix):** `validate_boon_ask`/`fulfill_boon` dispatch on `kind` through explicit per-kind tables
  (`_BOON_ASK_VALIDATORS`/`_BOON_FULFILLERS`) — an unhandled kind raises `ValueError` loudly
  instead of silently falling through to DEED's handling (the original if/elif chains' trap).
  **Ask flavors (slice 3, #2540):** three sibling `ActionTemplate` singletons over the same
  Boon payload — Con a Boon (`boon_con`, Con check), Charm a Boon (`boon_charm`, Seduction
  check), Menace a Boon (`boon_menace`, Intimidation check, +1 tier like Seduce-harder-than-
  Flirt) — join plain `boon` in `BOON_ACTION_KEYS` (the frozenset replacing the old single
  `BOON_ACTION_KEY` everywhere: the server payload guard, the resolver registration loop, and
  the FE `ActionPanel` gate). All four share the `boon` consent category and one resolver
  registration loop — one opt-in, one fulfillment path; only the check type differs per
  flavor (rejected: a `flavor` payload field selecting the check type at resolution time — the
  check type belongs on the template, ADR-0235).
  **Standing-gap audacity shift (slice 3, #2540):** `npc_boon_tier_shift` (dial 2's NPC band)
  now sums the existing relative-cost band with `_rank_gap_shift`, one difficulty tier per
  `RANK_GAP_TIER_BANDS` (PLACEHOLDER magnitudes) threshold crossed by how far the asker's
  inverted `social_rank` sits below the target's — asking a much higher-standing NPC is
  harder; punching down or asking an equal never adds a tier. NPC-only: a piloted target's own
  `difficulty_choice` always rules (`action_services.py`'s piloted call site omits
  `extra_tier_modifier` by design, per the July piloted-consent ruling). See ADR-0235.
- **Abstract base:** `DefenderConsentFields` (`action_models.py`) — shared by `SceneActionRequest` and `SceneActionTarget`; carries `difficulty_choice` (DifficultyChoice plausibility band, authored by the defender), `resolved_difficulty`, `resist_effort_level` (EffortLevel, optional active resistance).
- **Effort/difficulty split:** The initiator declares `effort_level` (EffortLevel) at dispatch; the defender authors per-target `difficulty_choice` at consent. The resolver adds `EFFORT_CHECK_MODIFIER[effort_level]` to the check pool and charges the initiator social fatigue. The defender's plausibility base + optional `compute_resist_increment()` produce the numeric `difficulty_override`; active resistance charges the defender `RESIST_FATIGUE_BASE` social fatigue.
- **Social action consent:** `SceneActionRequest` owns the full lifecycle (dispatch → consent → resolution) for the primary target; `SceneActionTarget` rows carry additional targets, each with independent consent and result. Resolvers fire once per accepted target (primary via `respond_to_action_request`, additional via `respond_to_action_target`).
- **Key Functions:**
  - `create_action_request(scene, initiator_persona, target_persona, action_key, ..., effort_level)` — dispatches a request; NPC targets (primary or additional) auto-accept immediately (#2214), guarded so an unresolvable request stays PENDING instead of raising.
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
  - **Scene-round Succor (#1744) — the non-combat sibling of combat's Succor maneuver:**
    - `declare_succor_scene(participant, ally)` (`round_services.py`) — writes/updates a deferred
      `SceneActionDeclaration.succor_target` for the current round; always names a specific ally
      (mirrors `world.combat.services.declare_succor`).
    - `ensure_succor_challenges_for_round(scene_round)` (`succor_content.py`) — round-resolution
      pre-pass: binds a Succor `ChallengeInstance` to each protected ally declared this round.
      Called from `resolve_scene_round` right before `_resolve_scene_declarations`. No prior
      scene-round "bind a reactive challenge" plumbing existed — this is the scene-round
      equivalent of combat's `_ensure_succor_challenges`, keyed off
      `SceneActionDeclaration.succor_target` instead of `CombatRoundAction`.
    - `SceneRoundContext.get_cover_for(target, damage_type)` (`round_context.py`) — resolves and
      caches this round's Succor cover multiplier on `SceneActionDeclaration.succor_resolution`,
      mirroring `CombatRoundContext.get_cover_for`'s caching contract.
    - `SuccorSceneAction` (`actions/definitions/rounds.py`, key `"scene_succor"`) — the REGISTRY
      dispatch surface wrapping `declare_succor_scene`; shared by telnet `scene succor <ally>`
      (`CmdScene`) and the web dispatcher.
  - **Out-of-combat sudden-harm Interpose (#1316) — the non-combat sibling of combat's Interpose
    maneuver, for one-shot ambush/trap damage rather than a recurring hazard tick:**
    - `PendingSuddenHarm` (`models.py`) — one-shot damage payload held pending a reactive Interpose
      beat: `target_sheet` (OneToOne `CharacterSheet`), `scene_round` FK, `amount`, `damage_type`
      (nullable FK), `source_description`.
    - `arm_or_apply_sudden_harm(target, amount, damage_type, *, source_description="")`
      (`sudden_harm.py`) — called from `world.mechanics.effect_handlers._deal_damage`; applies
      immediately via `apply_resolved_damage` below `sudden_harm_interpose_threshold` or with no
      bystander present, else binds an Interpose `ChallengeInstance`, bootstraps a DANGER round
      (`ensure_round_for_acute_condition`), and creates a `PendingSuddenHarm` row.
    - `declare_interpose_scene(participant, ally)` (`round_services.py`) — writes/updates a
      deferred `SceneActionDeclaration.interpose_target` for the current round; named-ally only
      (mirrors `declare_succor_scene`'s #1744 narrowing).
    - `resolve_pending_interpose_harm(scene_round)` (`sudden_harm.py`) — called from
      `resolve_scene_round` right after the END tick; resolves each pending harm via the unchanged
      `world.combat.services.dispatch_interpose` against this round's `interpose_target`
      declaration (if any), applies the result via `apply_resolved_damage`, then cleans up the
      `ChallengeInstance` and `PendingSuddenHarm` row. No declaration -> full harm lands (AFK-safe
      default).
    - `InterposeSceneAction` (`actions/definitions/rounds.py`, key `"scene_interpose"`) — the
      REGISTRY dispatch surface wrapping `declare_interpose_scene`, registered and callable via
      the web dispatcher (`Action().run()`) and telnet (`scene interpose <ally>`,
      `commands/scene.py`'s `CmdScene`, mirroring `scene succor <ally>`).
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
- **Highlight reel (#1241; re-ranked #2161):** `GET /api/scenes/{id}/highlight-reel/` — a
  fully-sealed featured moment + ranked index, carrying `vote_count`/`reaction_count` per pose.
  Ranked by all-time `WeeklyVote` count first (survives weekly settlement, unlike the weekly
  `Interaction.vote_count` counter), `InteractionReaction` count as tie-break, recency last;
  GM-tagged poses headline. Filtered through `Interaction.objects.visible_to`. Frontend:
  `HighlightReel` (`frontend/src/scenes/components/`) — direct-mounted (no extra Accordion
  wrapper, it's already self-collapsing) in the `/game` right sidebar's Room tab via
  `SceneHighlightsPanel` (`frontend/src/game/components/room-panel/`), in addition to its
  original mount on `SceneDetailPage`.
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
  - `StartSceneAction` (key `"start_scene"`, `actions/definitions/scenes.py`) — creates scene + grants co-ownership to all present PCs; records actor as non-owner participant if scene already exists. **Web convergence (#3069):** `SceneViewSet.perform_create` (`world/scenes/views.py`) dispatches this Action instead of a bespoke `Scene.objects.create`, so the web "Start Scene" button now gets the same privacy derivation + co-owner/GM enrollment telnet always had.
  - `FinishSceneAction` (key `"finish_scene"`, `actions/definitions/scenes.py`) — finishes active scene; gated by `actor_can_administer_scene`.
  - `SetRoundModeAction` (key `"set_round_mode"`, `actions/definitions/rounds.py`) — changes mode/knobs of active round; gated by `actor_can_administer_scene`; `costs_turn=False`.
  - `TruncatePrecaptureAction` (key `"truncate_precapture"`, `actions/definitions/scenes.py`, #3069 sub-item 4) — lists/truncates pre-scene-captured poses; gated by `actor_can_administer_scene`. See [scenes.md](scenes.md) §"Pre-scene RP capture".
- **Pre-scene RP capture (#3069 sub-item 4):** `StartSceneAction`'s new-scene branch now folds prior unattached (`scene=None`) poses into the scene via `world/scenes/precapture_services.py`'s `capture_prescene_interactions` — present authors attach immediately, absent authors get a `PrecaptureConsentRequest` (`precapture_models.py`) needing explicit accept (`world/scenes/precapture_offer_handler.py`'s telnet `accept precapture`/`decline precapture` + web `PrecaptureConsentRequestViewSet`). See [scenes.md](scenes.md) §"Pre-scene RP capture" for the full design (candidate window, privacy invariants, truncation).
- **`CmdScene`** (`commands/scene.py`) — telnet face for `scene start [name]` / `scene finish` / `scene round [open|pose_order|strict] [quorum=<pct>] [cap=<n>] [lock=on/off]` / `scene capture [<n>]` (#3069) / `scene status`. Thin over the Actions above; no business logic.
- **`is_story_runner`** character property (`typeclasses/characters.py`) — `False` on base `Character`; `True` on `GMCharacter` and `StaffCharacter` (`typeclasses/gm_characters.py`); used by `actor_can_administer_scene` as the GM/Staff fast-path.
- **API endpoint:** `POST /api/scenes/{id}/set-round-mode/` — coarse-gated `IsSceneGMOrOwnerOrStaff`; dispatches `SetRoundModeAction`; returns updated scene detail.
- **`active_round` read field on `SceneDetailSerializer`** (#1467): nullable nested field serialized by
  `SceneRoundSerializer` (read-only). Exposes `mode`, `advance_quorum_pct`, `max_actions_per_round`,
  `per_target_repeat_lock`, `status`, `round_number`, `is_danger`. `null` when no location or no active round.
- **`RoundSettingsDialog`** (React, `frontend/src/scenes/components/RoundSettingsDialog.tsx`, #1467):
  GM/owner/staff-gated (`viewer_can_gm && is_active`) dialog for setting round mode and knobs;
  consumes `active_round` from the scene detail and dispatches `useSetRoundMode` →
  `POST /api/scenes/{id}/set-round-mode/`. Wired into `SceneHeader.tsx`.
- **Places (#1866):** `Place`/`PlacePresence` (`place_models.py`) — a named sub-location
  within a room. `JoinPlaceAction`/`LeavePlaceAction` (`actions/definitions/places.py`)
  are the seam both `PlaceViewSet` (`place_views.py`) and telnet `CmdPlaces` (`places`,
  `commands/places.py`) dispatch through.
- **Block/Mute/Friendship/Rivalry (#1278, #1727, #2170, #2996):** the OOC safety + connection
  primitives, all keyed on `PlayerData`/`RosterTenure` (never derived from IC relationships).
  `Block` (mutual, account-first by default since #2996) and `Mute` (one-way, also account-first
  by default) are the enforcement primitives every OOC delivery seam (mail, journal
  reactions/feed, event invites, kudos, pages/tells, friend adds) consults via the shared query
  helpers `block_services.account_block_active`/`blocked_player_ids_for` and
  `mute_services.account_muted`/`muted_player_ids_for`; `Friendship`/`Rivalry` are the positive
  connection primitives (`friend_services.py`) feeding the `FRIENDS_WHITELIST`/`RIVALS` consent
  modes. See `world/scenes/CLAUDE.md`'s Block/Mute entries and ADR-0204 for the full seam table.
- **Perception & altered reality (#2997):** three axes for "who perceives what is
  real" — room-broadcast membership exclusion (Axis 1, `register_broadcast_exclusion`/
  `resolve_broadcast_exclusions` in `flows/service_functions/perception_registry.py`),
  per-viewer content shape/tiering on a recorded event (Axis 2, ADR-0170 snapshot vs
  ADR-0214 live recompute — deliberately not unified), and downstream read-time
  feed filtering (Axis 3, mute/block/`visible_to`). Orthogonal canonical check seam:
  `resolve_perception_check(observer_sheet, *, difficulty, specialization=None)`
  (`world/checks/perception_services.py`) — the one AD&D-style roll every
  perceive-the-real mechanic resolves through; ADR-0033 boundary: reveals wrongness,
  never identity. See [scenes.md](scenes.md) §"Perception & altered reality" for the
  full taxonomy and decision checklist.
- **Integrates with:** roster (characters), stories (EpisodeScene join), instances (preservation check),
  flows (auto-logging via message_location), combat (encounter read gate + participation convergence via
  `Scene.objects.viewable_by` / `ensure_scene_participation`),
  actions (`SCENE_ADAPTIVE` backend dispatch + `CastTechniqueAction`; resolver registry via
  `get_resolver(action_key)`), consent (`SocialConsentCategory` enforcement)
- **Source:** `src/world/scenes/`
- **Details:** [scenes.md](scenes.md)
- **Speaker Queue (#2356):** Room-scoped turn-order utility for structured RP gatherings (court, sermons, Q&A). Does NOT gate actions — players can pose/say/react freely.
  - **Models** (`speaker_queue_models.py`): `SpeakerQueue` (one active per room, UniqueConstraint on `is_active=True`; FK room PROTECT, scene SET_NULL for auto-clear, opened_by persona), `SpeakerQueueEntry` (ordered membership; FK queue CASCADE + persona CASCADE; position 1=current speaker; unique per queue+persona).
  - **Services** (`speaker_queue_services.py`): `open_queue`, `close_queue`, `join_queue`, `leave_queue`, `advance_queue`, `skip_speaker`, `get_active_queue`, `queue_entries`, `clear_queue_on_scene_finish`, `remove_persona_from_room_queues`.
  - **Actions** (`actions/definitions/speaker_queue.py`): 6 REGISTRY actions — `open_speaker_queue`, `close_speaker_queue`, `join_speaker_queue`, `leave_speaker_queue`, `advance_speaker_queue`, `skip_speaker`. All `target_type=SELF`, `category="scenes"`.
  - **Telnet** (`commands/speaker_queue.py`): `CmdLine` (`line`) — subverb-routed: `line open|close|join|leave|next|skip <name>`.
  - **Web** (`speaker_queue_views.py`): `SpeakerQueueViewSet` — read + `open`/`close`/`join`/`leave`/`advance`/`skip` action endpoints.
  - **Frontend** (`scenes/components/SpeakerQueueBar.tsx`): Inline scene panel component, mirrors `PlaceBar`.
  - **Auto-cleanup:** Scene finish (`finish_scene_full`), departure (`Room.at_object_leave`), disconnect (`Character.at_post_unpuppet`).
### Stories
Player-driven narrative campaign system with hierarchical structure and task-gated progression.

- **Models:** `Story` (incl. `summary` - player-facing "The Story So Far"; `description` = GM pitch), `Chapter`, `Episode`, `Transition`, `Beat` (incl. `outcome_key`, denormalised from `BeatCompletion.outcome_key`, #3565), `BeatCompletion` (incl. `outcome_key`), `EpisodeResolution`, `TransitionRequiredOutcome` (incl. `required_outcome_key`, #3565), `StoryProgress`, `GroupStoryProgress`, `GlobalStoryProgress`, `AggregateBeatContribution`, `AssistantGMClaim`, `SessionRequest`, `StoryGMOffer` (directed CHARACTER-scope player→GM offer), `GroupStoryRequest` (covenant-scoped broadcast ask for a GM, #2119 - see below), `StoryNote` (append-only OOC authorial memory, never player-visible), `Era`, `StoryParticipation`, `PlayerTrust`, `TrustCategory`, `BeatOpponentLine`/`BeatStagedTemplate` (session prep child rows on ENCOUNTER/SITUATION beats, #3425 - see below), `BeatStagedBattle`/`BeatStagedBattleUnit` (a whole pre-staged battle on an ENCOUNTER beat, O2O + child rows, mutually exclusive with `BeatOpponentLine`, #3569 - see below), `StoryScenario` (`story` FK + `template` O2O onto `missions.MissionTemplate`, `related_name="story_scenario"`; the ownership link that makes the mission scenario graph a story beat's body, #3565 - see below and Missions & Living Grid)
- **The scenario graph is a beat's body, not a second option engine (#3565):** a `Beat` (SITUATION or TASK kind) points at a `missions.MissionTemplate` via `required_mission`; when that template is `StoryScenario`-owned, the story's Lead GM authored it under the trust ladder rather than staff. `Transition.mode`/`TransitionMode`/`AmbiguousTransitionError` are retired: routing is fully automatic, the lowest `(order, pk)` eligible outbound transition fires, and `services/routing.py`'s `routing_report`/`RoutingReport` (surfaced as `routing_problems` on the episode payloads and `EpisodeDetailSerializer.routing_ambiguous`, #3563) warns the author tree when two transitions could both be eligible at once, or when a beat/stake outcome has no accepting transition. `Beat.predicate_type` defaults to `OUTCOME_TIER` (was `GM_MARKED`) - a beat resolves from its graph, an encounter, a battle, or a decisive check by default; GM-marked is now the exception, authored only for an out-of-band fact a machine grader cannot see. See stories.md's "StoryScenario" section and Missions & Living Grid below.
- **Session prep + Run Beat (#3425, #3569):** a GM authors `BeatOpponentLine` (creature × count × position hint) on an ENCOUNTER beat, `BeatStagedTemplate` (situation XOR challenge template) on a SITUATION beat, or - mutually exclusive with `BeatOpponentLine` - a whole `BeatStagedBattle` (blueprint/region/name/party side + `BeatStagedBattleUnit` lines) on an ENCOUNTER beat, #3569 - nested read-write on `BeatSerializer`, including the id-based-diff update path for the child lists and an omitted-vs-null convention for the single nested `staged_battle`. `RunBeatAction` (`run_beat`)/`GMListRunnableBeatsAction` (`gm_list_runnable_beats`, `actions/definitions/gm_story.py`) instantiate the authored prep into the GM's live scene in one call: for ENCOUNTER, creates a `CombatEncounter`/spawns opponents, or - when a `BeatStagedBattle` exists - stages a `Battle` from its blueprint instead (`Battle.story_beat=beat`, units spawned by side/place, the running scene's present party enlisted on the declared side, idempotent re-run); for SITUATION, instantiates situations/challenges; and sets `scenes.Scene.running_beat` (the first-class "scene is running this beat" pointer, cleared by `finish_scene_full`). Web: `BeatFormDialog`'s kind-gated repeatable rows (plus an Opponents/Battle toggle for ENCOUNTER, mounting `BattlePrepEditor` in Battle mode) + `GMAdjudicationPanel`'s Run Beat tab ("Start siege" for a staged-battle row, navigates to `/scenes/{battle_scene_id}/battle`). See stories.md's "Session prep"/"Run Beat" sections and scenes.md's "Session prep: Run Beat".
- **Scene clock (#3567; ADR-0264):** `Beat.clock_size` (0 = no clock) authors a countdown that
  `RunBeatAction` opens as a `world.scenes.models.SceneClock` (`scenes` app, keyed by beat, one
  open row per beat) when the beat runs. Filled by two sources - combat round starts
  (`begin_declaration_phase`, `world.combat.services`; battle rounds never call it, so a staged
  battle's own rounds don't tick) and the GM `advance_clock` gesture (`AdvanceClockAction`,
  `actions/definitions/gm_story.py`, telnet `story clock [n]`) - both via `tick_scene_clock`
  (`world.scenes.clock_services`, the sole writer of `SceneClock` rows: also
  `start_scene_clock`/`open_clock_for_beat`/`close_open_clock_for_beat`/`close_scene_clocks`). A
  full clock stamps FILLED and schedules the beat's EXPIRED completion via
  `transaction.on_commit`, lock-then-checked so a later round-pipeline failure can never roll
  back a completion players were already told about. `finish_scene_full` closes every clock
  opened in that scene as SCENE_ENDED (no completion); any other beat completion closes the open
  clock as COMPLETED. Player-visible on every scene viewer as `SceneDetailSerializer.clock`
  (`{size, filled}`, no beat/consequence named) rendered by `SceneClockPips.tsx` on the scene
  header; the GM story rail additionally shows the beat's authored `clock_size` plus an Advance
  control. See stories.md's "Scene clock" (Run Beat section) and scenes.md's "Scene clock".
- **Declared-risk badge (#3433):** `SceneDetailSerializer.declared_risk` - the player-visible
  sibling of the GM-gated `running_beat` field, tier string only (`RenownRisk`, never a beat
  id/name). Precedence: `scene.running_beat.risk` → the active `CombatEncounter.story_beat.risk`
  → the scene's PENDING `DecisiveCheckMarker.beat.risk` → `null`; `RenownRisk.NONE` also renders
  nothing. Web: `SceneHeader.tsx`'s `DeclaredRiskBadge`, beside the "In Combat" badge. See
  scenes.md's "Declared-risk badge" section.
- **Authoring backbone enums:** `StoryScope.UNASSIGNED` (new default), `StoryMaturity` (PITCH/OUTLINE/PLOT — per-node authoring completeness on Story/Chapter/Episode), `BeatKind` (SITUATION/ENCOUNTER/TASK/REQUIREMENT), `ProgressStatus` (ACTIVE/WAITING_FOR_GM/RESTING/COMPLETED on the three Progress models; **not currently exposed to the frontend** — see stories.md follow-ups)
- **`BeatPredicateType.FACTION_STANDING_AT_LEAST` (#1760):** a Beat gates on accumulated `SocietyReputation`/`OrganizationReputation.value` — `Beat.required_society`/`required_organization` (exactly one) + `required_standing`; evaluator `_evaluate_faction_standing_at_least` (`world.stories.services.beats`). Read-side complement to the Stakes Contract Engine's `FACTION` `subject_standing_delta` writer (below)
- **`BeatPredicateType.NPC_REGARD_AT_LEAST` (#3570):** a Beat gates on a named NPC's `NpcRegard` for the character, using `Beat.required_npc_sheet` (the NPC, FK → CharacterSheet, SET_NULL) + `required_standing` (shared with the faction predicate above); evaluator `_evaluate_npc_regard_at_least` reads `NpcRegard` from the NPC's primary persona toward the character's primary persona (missing row = 0, never `NPCStanding.affection` or the relationships affection track). Read-side complement to the Stakes Contract Engine's `NPC_FATE` `npc_regard_delta` writer and the structured-consequence `SHIFT_NPC_REGARD` pool effect (below); GROUP/GLOBAL scopes fall through to UNSATISFIED like the faction sibling (neither is in the ANY-member predicate set)
- **GM↔player visibility contract:** `description`/`consequences` are GM/staff-only; `summary` is player-facing ("The Story So Far"), blanked while node `maturity == PITCH`. Enforced server-side in two places: the three Detail serializers' `to_representation` (via `_gm_text_gate`, default-deny when no request) **and** `serialize_story_log` (per-beat internals gated to privileged roles). No dedicated `pitch` field by design — `description`=GM pitch, `summary`=player recap
- **Reactivity entry points (Phase 3):** `stories.services.reactivity.on_character_level_changed` / `on_achievement_earned` / `on_condition_applied` / `on_condition_expired` / `on_codex_entry_unlocked` / `on_story_advanced`. The general-purpose `on_character_state_changed` also gets called directly (#3570): `world.npc_services.regard.record_npc_regard_event` (after its regard write) and `world.societies.renown.bump_society_reputation`/`bump_organization_reputation` (after a non-zero reputation write), so an `NPC_REGARD_AT_LEAST`/`FACTION_STANDING_AT_LEAST` beat can flip in the same request
- **Key Services:** `evaluate_auto_beats`, `record_gm_marked_outcome`, `record_scenario_outcome` (`world.stories.services.beats`; a scenario run's ending on an OUTCOME_TIER beat, #3565, closes #3560), `record_aggregate_contribution`, `get_eligible_transitions` (`services/transitions.py`), `routing_report` / `routing_reports_for_episodes` (`services/routing.py`, authoring-time dead-end + ambiguity report, #3563), `resolve_episode` (reconciles ProgressStatus on advance; distinguishes routing-block from authoring frontier; routing is now fully automatic, no `chosen_transition` input), `create_character_progress` / `create_group_progress` / `create_global_progress` (reject UNASSIGNED scope), `services.frontier.resolve_frontier` / `set_progress_status`, `services.maturity.promote_episode_maturity`, `services.dashboards.compute_story_status_line`, `catch_up_character_stories` (called from `Character.at_post_puppet`), `services.scenarios.create_scenario_for_beat` (#3565, the write side of `POST /api/beats/{id}/scenario/`)
- **API Endpoints:** `POST /api/episodes/{id}/promote/` (set node maturity; PLOT-gate mirrored in `PromoteEpisodeInputSerializer` → 400 on gate violation), `POST /api/episodes/{id}/resolve/` (fire `resolve_episode`; body `{progress_id?, gm_notes?}` - no `chosen_transition`, #3565, routing is automatic), `POST /api/beats/{id}/scenario/` (GM authors a scenario graph as the beat's body, #3565: creates the `MissionTemplate` + `StoryScenario` row, sets `beat.required_mission`; idempotent), `GET /api/scenes/{id}/scenario/` (#3565, `world.scenes` - the running scenario's node/options for the party, ballots + node for the GM, see stories.md), `POST /api/stories/{id}/assign-to-scope/` (lift a story out of UNASSIGNED; sets scope + creates the matching progress record; 400 if already-assigned or scope↔target invariant violated), `GET /api/stories/gm-queue/` + `GET /api/stories/staff-workload/` (now query-bounded with `assertNumQueries` locks; staff-workload per-GM membership is status-agnostic), plus standard ViewSet CRUD and the existing `log/` / `my-active/` / beat-`mark`/`contribute` / AGM-claim / session-request actions, and append-only `/api/story-notes/`
- **Authoring/run-control UI:** `StoryAuthorPage` carries the run-control surface — `PromoteMaturityButton` (inline PLOT-gate 400), `ScopeAssignDialog`, GM Notes tab (StoryNote), inline `ProgressStateBanner`, Resolve/Mark run-control, nimble +Beat/+Branch quick-add; `BeatFormDialog` exposes kind/advances/risk (risk staff-gated); forms use "Internal GM Description" / "The Story So Far" labels + episode `resting_conclusion`/`is_ending`
- **Integrates with:** scenes (episode content), roster (participants), achievements / conditions / codex / classes (predicate evaluation + reactivity hooks fire from their services), narrative (beat completions and episode resolutions emit NarrativeMessages)
- **Player→GM recruitment loop (#2119):** `GroupStoryRequest` — a covenant officer's open,
  broadcast ask for a GM (PENDING/ACCEPTED/WITHDRAWN; one PENDING per covenant, DB partial-unique
  constraint). Authoring gated by `covenants.CovenantRank.can_request_gm` (new flag, mirrors
  `can_lead_rituals`) via `covenants.services.can_request_gm_for_covenant`. Services
  (`stories.services.tables`): `request_gm_for_covenant`, `claim_group_story_request` (creates the
  GROUP-scope `Story` + `GroupStoryProgress` bound to the claiming GM's table, and seats every
  active `CharacterCovenantRole`'s persona at that table via the existing `gm.services.join_table`
  — no schema change to `GMTableMembership`), `withdraw_group_story_request`. Actions
  (`actions/definitions/gm_stories.py`): `RequestGMForCovenantAction`, `ClaimGroupStoryRequestAction`,
  `WithdrawGroupStoryRequestAction` — REGISTRY backend, reachable from web via the generic
  `POST /actions/characters/<id>/dispatch/` **and** telnet (`covenant request-gm`/
  `withdraw-gm-request`, `gm claim <id>`) — deliberately not a bespoke DRF `@action` (the gap that
  left `StoryGMOffer` telnet-less). Read-only `GroupStoryRequestViewSet`
  (`/api/group-story-requests/`; staff see all, any GM sees the PENDING queue + their own claims,
  others see only their own covenants' requests). `GMQueueView`/`GMDashboardView` gain
  `open_group_requests` (visible to any GM, not scoped to existing tables/stories).
- **Source:** `src/world/stories/`
- **Details:** [stories.md](stories.md)

### Stakes Contract Engine (#1770 PR1-4; web editor + GM-pick retirement #3561)
GM-authored, player-visible "what's actually at risk" contract backing a story
`Beat`'s risk declaration — named stakes with WIN/LOSS/WITHDRAWAL branches, banded
by designer-tunable calibration rows, priced for the actual party at scene-start
lock (activation wired at every commit surface, PR4), read by the Legend award,
resolved per-stake at beat completion (machine grading; a named branch is chosen
by the completing beat's authored `outcome_key`, never a runtime GM pick - #3561,
ADR-0259), and paying authored win-reward lines through an anti-farming activation
gate (PR3). ADR-0067. The full contract is now editable from the story author
page (`StakesPanel` on the beat, #3561) - see the "Web editor + GM-pick
retirement" entry below.

- **Models:** `RiskCalibration` (per-tier severity floor/ceiling + `max_fuse_hops`
  chain-rule bound; `reward_floor`/`reward_ceiling` band the WIN reward total —
  PR3, ceiling 0 = unconfigured), `StakeTemplate`
  (menu-first catalog, `min_risk`/`max_risk` band), `Stake` (beat FK
  `related_name="stakes"`; typed subject FKs incl. `subject_asset` (#3561, →
  `assets.NPCAsset`) + `subject_label`; `player_summary`),
  `StakeResolution` (stake FK `related_name="resolutions"`; `column`
  WIN/LOSS/WITHDRAWAL; `outcome_key` (#1760 — designer slug naming a branch
  within `column`'s polarity, blank = plain default; unique
  `(stake, column, outcome_key)`); `consequence_pool`; `escalates_to_risk`;
  PR2 writer payloads `forfeits_subject_item` / `subject_standing_delta`
  (dispatch by `subject_kind` — `NPC_FATE` writes `NPCStanding`, `FACTION`
  writes `SocietyReputation`/`OrganizationReputation`, #1760) /
  `sets_subject_lifecycle` — pillar-12 validated; `machine_match_lifecycle_state`
  (#1760 — generalizes the old NPC-vitals DEAD-only override to the full
  `LifecycleState` ladder; a match wins over the beat-derived column, even
  crossing WIN/LOSS polarity); `npc_regard_delta` (#2039 writer, exposed on the
  serializer #3561) and `transitions_subject_asset` (#3561 writer, `ASSET`-only,
  transitions `subject_asset` to COMPROMISED/LOST/DISMISSED)), `StakeRewardLine`
  (PR3; ITEM/CLUE/CODEX sinks added #3566; resolution FK
  `related_name="reward_lines"`; `sink` MONEY/RESONANCE/ITEM/CLUE/CODEX;
  `amount` per-participant money-equivalent scalar (pinned to
  `item_template.value` for ITEM); `resonance`/`item_template` (PROTECT)/
  `clue` (PROTECT)/`codex_entry` (PROTECT) each required iff `sink` matches),
  `StakeContractActivation`
  (lock + audit row; partial-unique open-per-beat; `effective_risk`),
  `StakeOutcome` (PR2 per-stake resolution audit/routing row; exactly one per
  stake; `method` is always MACHINE since #3561 retired `GM_PICK`);
  `Beat.target_level`; `TransitionRequiredOutcome.stake` +
  `required_stake_column` (PR2 stake-level transition routing, authorable via
  `TransitionFormDialog`'s stake-column routing mode, #3561).
- **Enums:** `StakeSeverity` (SETBACK…REMOVAL, 1-5), `StakeSubjectKind` (incl.
  `ASSET`, #3561), `StakeResolutionColumn`, `StakeOutcomeMethod` (`MACHINE` only
  since #3561 retired `GM_PICK`), `StakeRewardSink` (MONEY/RESONANCE/ITEM/CLUE/
  CODEX, #3566 added the last three - no Legend sink; Legend stays automatic),
  `RISK_LADDER`, `DEFAULT_RISK_CALIBRATIONS`.
- **Key Services (`world.stories.services.stakes`):** `compute_effective_risk`
  (party-level-vs-target-level curve, `LEVELS_PER_TIER=2`, bounded +1 under-level
  upgrade), `validate_stakes_readiness` (severity bands + WIN reward band (PR3)
  + jeopardy-reachability fuse walk over the failure cascade — PITCH episodes
  never count),
  `activate_stakes_contract` (idempotent lock; unready → effective `NONE`),
  `effective_risk_for_beat` (read seam consumed by `_legend_award`),
  `resolve_open_activation` (wired into the beat-completion tail).
- **Key Services (`world.stories.services.stake_resolution`, PR2; branch
  selection reworked #3561):** `resolve_stakes_for_completion` (completion-tail
  machine grading; NPC-vitals DEAD → LOSS override; `outcome_key`-matched named
  branch selection, #3561; withdrawal and revoked-consent branch firing both
  record the empty outcome when unauthored, Decision 2 #3561; idempotent audit
  rows), `_branch_for_column` (#3561 - the shared branch picker: lifecycle
  match, then `outcome_key` match, then plain default, then first authored),
  `stake_resolution_payload_problems` + `sheet_is_player_held` (pillar-12
  no-fiat validation; #3561 added the `transitions_subject_asset`-requires-ASSET
  check), `_apply_stake_rewards` (PR3 - WIN payout per line x
  participant, gated on a ready effective-risk-bearing activation; each
  line x participant delivery individually try/excepted since #3566 so one
  failure doesn't stop the rest; sinks: `currency.deliver_mission_money`,
  `magic.grant_resonance` with `GainSource.STAKE_REWARD`,
  `items.narrative_grants.grant_touchstone_item_to_character` (#3566),
  `clues.grant_clue_target` (#3566), `codex.grant_codex_entry` (#3566);
  deliberately NOT the missions deed router). CLUE/CODEX delivery
  (`_deliver_knowledge_reward_line`) skips an NPC participant with no
  `roster_entry_or_none` while MONEY/RESONANCE/ITEM still pay that
  participant (#3566).
  `resolve_stake_by_gm_pick` and `POST /api/stakes/{id}/resolve/` are removed
  (#3561, ADR-0259). Cross-app writers: `items.forfeit_item_instance`
  (soft-forfeit), `npc_services.adjust_npc_affection`,
  `roster.set_lifecycle_state`, `assets.transition_asset_status` (#3561);
  `vitals._mark_dead` now propagates
  `LifecycleState.DEAD` to the roster lifecycle.
- **Opt-in surfaces (PR4):** `check_stake_boundaries`
  (`world.stories.services.boundaries` — real hard-line/treasured-subject
  registry since #1771, see [Boundaries](#boundaries) below;
  `StakeBoundaryReport` in `world.stories.types`; `blocked_reason_private` is
  staff-only, ADR-0033); `stakes_summary_for_beat` +
  `StakesSummarySerializer`/`StakeSummarySerializer` (pillar 9 — branch contents
  never serialized; `StakeSummarySerializer.reward_kinds`, #3566, is the one
  exception in spirit only - sorted/deduped payout *category* labels
  (`REWARD_KIND_BY_SINK`: money/resonance/item/knowledge, CLUE and CODEX both
  read as "knowledge"), never an amount or a target); `GET
  /api/beats/{id}/stakes-summary/`; `GET
  /api/scenes/{id}/stakes-summary/` (#3561 - the scene-scoped sibling, since a
  player never receives the running beat's id from any scene payload; delegates
  to the same builder); `combat_stakes` on
  both consent-prompt serializers (`world.scenes.action_serializers`) rendered
  by `ConsentPrompt`; activation wired at `create_pvp_duel`/`create_lethal_duel`/
  `seed_or_feed_encounter_from_cast` (via `combat.beat_wiring.
  activate_stakes_for_scene` + `staked_unsatisfied_beats_for_scene`), at
  `issue_mission` (via `missions.services.beat.activate_stakes_for_instance`),
  and via the `declare_stakes` GM action (freeform scenes);
  `missions.MissionRiskAcknowledgement` + `MISSION_RISK_ACK_TIER` gate with the
  two-phase `acknowledge_risk` opt-in inside `npc_resolve`
  (`MissionRiskUnacknowledgedError`); `InteractionOfferSerializer.risk_tier`
  pre-accept surfacing. NPC mission offers now carry the opt-in themselves
  (#1780): `MissionOfferDetails.source_beat` (staff-authored, exposed on
  `MissionOfferDetailsSerializer`) copies onto `MissionInstance.source_beat` at
  `issue_mission`, so the risk gate also fires — and surfaces the linked
  beat's `player_summary` stake lines — whenever that beat is staked
  (`risk != NONE`), independent of the template's own `risk_tier`; ADR-0085
  puts the FK on `MissionOfferDetails`, not the unified `NPCServiceOffer`.
  `MissionOfferDetails.target_project` (#2045) copies onto
  `MissionInstance.target_project` at `issue_mission` — same instance-binding
  shape as `source_beat`. A PROJECT reward sink (`DeedRewardSink.PROJECT`)
  routes through `apply_deed_rewards` → `add_contribution(kind=MISSION)` →
  `maybe_complete_immediately`. Loud refusal at issuance when PROJECT lines
  exist but no project is bound; soft-skip-with-notice at payout when the
  project is non-ACTIVE or null. ADR-0103.
  GM-tier mission assignment (#2048): `gm_assign_mission` creates a
  `MissionInstance` with `source_beat` set (direct drop, no accept gate).
  `Beat.required_mission` is wired as the beat's authoring pointer
  (writable on `BeatSerializer`). Stakes arm lazily on the player's first
  beat action (engagement-armed stakes), not at assignment time.
  `BeatViewSet.assign_mission` action (`POST /api/beats/{id}/assign-mission/`,
  `CanAssignMissionToBeat` — Lead GM or staff). ADR-0104.
- **Web editor + GM-pick retirement (#3561, ADR-0259):** `StakesPanel` mounted
  under the beat in `StoryAuthorTree` (collapsible) and `BeatFormDialog` (edit
  mode) - `StakeRow` (template, `SubjectRefFields` subject picker with a new
  ASSET case), `BranchColumns` (WIN/LOSS/WITHDRAWAL, per-subject-kind writer
  fields), `RewardLinesEditor`, `ReadinessStrip`. Every write goes through the
  existing CRUD viewsets - no new write endpoint. `TransitionFormDialog`'s
  `AddRoutingRow` gained a stake-column routing mode (writes
  `TransitionRequiredOutcome.stake`/`required_stake_column`). `GMStoryRail`
  gained a Stakes section (`rail_services._serialize_stakes`/
  `_serialize_activation`) showing each stake's outcome once fired plus the
  activation strip. `SceneHeader`'s declared-risk badge is now a toggle opening
  a "What is wagered" panel reading the scene stakes-summary endpoint above.
  `NPCAssetViewSet`'s search (`?name=`) backs the ASSET subject picker, widened
  for a non-staff GM to their own assets plus assets promoted within a story
  they lead (never every player's assets). Readiness gained two problems for
  named-branch authoring gaps: a column with a named branch but no default,
  and a named key the beat's scenario doesn't declare.
- **Three-concepts disambiguation:** `Beat.risk`+contract (stakes/reward) is
  distinct from `combat.RiskLevel` (cast-pull acknowledgement gate) and
  `combat.StakesLevel` (GM access scope) — see stakes.md.
- **Integrates with:** stories (`Beat.risk`/`target_level`, `Transition` fuse
  walk + stake-level routing), societies (`RISK_LEGEND_AWARDS`), mechanics
  (`_legend_award` scaling), checks (`Consequence.character_loss` reachability
  test; branch pools via the shared `_fire_pool_with_context`), combat
  (FLED/ABANDONED withdrawal wire + PR4 activation seams), items /
  npc_services / roster / assets (writers - `assets.transition_asset_status`,
  #3561), currency / magic (PR3 win-reward sinks),
  scenes / missions / actions (PR4 opt-in surfaces; #3561 adds the GM rail
  Stakes section + scene stakes-summary)
- **Source:** `src/world/stories/` (models/services/serializers/views — search `#1770`)
- **Details:** [stakes.md](stakes.md)

### Custody & Cross-GM Clearance (#2001)
GM-authorable protection guarding a story's load-bearing assets (NPCs, items, factions,
locations, custom subjects — `StoryProtectedSubject`, replaces the NPC-only
`StoryNPCDependency`) from being appeared-with/harmed/removed by actors at *other*
tables, absent an active `CustodyClearance` at sufficient scope (APPEAR < HARM <
REMOVE). One seam (`check_subject_custody`) gates every enforcement point: the NPC
death guard, stake authoring, `StakeResolution` writer fire-time recheck, and
`add_opponent` spawning. Clearance requests may name the protection by pk or (the only
self-serviceable path when the requester doesn't know the pk — see ADR-0099) by
`subject_kind` + typed identity ref, fanning out across every story independently
protecting that identity. Grant/deny is the protecting story's Lead GM only (no staff
bypass); a denied or stale request escalates to staff. Story-declared narrative
structure — distinct from `world.boundaries` (player-declared emotional safety, see
below); ADR-0098.
- **Key Models:** `StoryProtectedSubject`, `CustodyClearance`
- **Key Services (`world.stories.services.custody` / `custody_clearance`):**
  `check_subject_custody`, `is_death_prevented_by_story`, `request_clearance`,
  `grant_clearance`/`deny_clearance`, `escalate_clearance`, `resolve_escalation`,
  `revoke_clearance`, `matching_active_protected_subjects`
- **API:** `/api/protected-subjects/` (owner/lead-GM CRUD, soft-deactivate `DELETE`),
  `/api/custody-clearances/` (list/create + `grant`/`deny`/`escalate`/`resolve`/`revoke`
  actions)
- **Telnet:** `story protect`, `story clearance` (`src/commands/story.py`)
- **Frontend:** `ProtectedSubjectsPanel` (StoryAuthorPage tab), `ClearanceInbox`
  (GMQueuePage section) — `frontend/src/stories/components/`
- **Integrates with:** stakes (custody gates on `StakeSerializer`/`StakeResolution`
  writers), boundaries (shared `_subject_identity` matching, separate axis), combat
  (`add_opponent` APPEAR gate), GM (`GMProfile`/`GMTable.gm` custodian identity)
- **Source:** `src/world/stories/` (search `#2001`)
- **Details:** [custody.md](custody.md)

### Boundaries
Player-private content-boundary registry backing `check_stake_boundaries` (#1771):
hard lines (auto-blocked `ContentTheme` matches, always private) and treasured
subjects (specific entities requiring an explicit pre-scene sign-off), plus a
consent-style sharing layer, a scene "lines & veils" aggregate, and a privacy-safe
GM availability read. ADR-0086 (extends ADR-0024, ADR-0033).

- **Models:** `ContentTheme` (NaturalKey on `key`, staff-authored),
  `PlayerBoundary` (owner `PlayerData`; `kind` HARD_LINE/ADVISORY; `theme` FK,
  `PROTECT`; `detail`; + `VisibilityMixin`), `TreasuredSubject` (owner
  `RosterTenure`; `subject_kind`; typed subject FKs mirroring `Stake` —
  `character_sheets.CharacterSheet` / `items.ItemInstance` / `societies.Society` /
  `societies.Organization`, all `SET_NULL`; `subject_label`; + `VisibilityMixin`).
  Stories-side: `StakeTemplate.content_themes` (M2M → `ContentTheme`),
  `TreasuredSignoff` (beat/player_data/treasured_subject FKs; `active` property).
- **Enums:** `BoundaryKind` (HARD_LINE/ADVISORY), `TreasuredSubjectKind` (mirrors
  `StakeSubjectKind` values verbatim, no `stories` import — ADR-0010).
- **Two matching mechanisms:** hard lines are a coarse `ContentTheme` intersection
  (player hard-line ∩ `StakeTemplate.content_themes` blocks the whole contract);
  treasured subjects are a fine specific-entity identity match
  (`_subject_identity`, shared by the enforcement check and the withdrawal
  override) requiring a `TreasuredSignoff`, not a block.
- **Key Services (`world.boundaries.services`):** `scene_lines_and_veils(scene,
  viewer_tenure) -> SceneLinesAndVeils` — anonymized, hard-line-free scene
  aggregate (`world.boundaries.types`: `SharedAdvisoryBoundary`,
  `SharedTreasuredSubject`, `SceneLinesAndVeils`).
- **Key Services (`world.stories.services.boundaries`, per ADR-0010 dependency
  direction — `boundaries` never imports `stories`):** `check_stake_boundaries`
  (real registry since #1771, unchanged contract), `grant_treasured_signoff`,
  `withdraw_treasured_signoff`, `stake_availability(beat, character_sheets) ->
  StakeAvailability` (`world.stories.types`: `available`/`blocked`/
  `needs_signoff` counts only). Resolution override:
  `resolve_stakes_for_completion` routes a withdrawn treasured stake to
  `StakeResolutionColumn.WITHDRAWAL` at ordinary completion (siblings unaffected).
- **API:** `/api/boundaries/` — `content-themes` (read-only), `player-boundaries`,
  `treasured-subjects` (owner-scoped `ModelViewSet`s, no staff carve-out),
  `scenes/{id}/lines-and-veils/`; `/api/treasured-signoffs/` +
  `/api/beats/{id}/stake-availability/` (mounted on the stories router, same
  dependency-direction reason).
- **Frontend:** `frontend/src/boundaries/` — `BoundariesPage`
  (`/profile/boundaries`, a Profile tab): boundary authoring, treasured-subject
  flagging, pre-scene sign-off; `SceneLinesAndVeilsCard` on `SceneDetailPage`.
- **Privacy invariant (ADR-0033/ADR-0086):** hard-line `theme`/`detail` and
  `blocked_reason_private` never reach a player- or GM-facing surface —
  structurally (owner-scoped querysets, hard-line-only-ever-excluded queries,
  counts-only value objects), not by convention.
- **Seed data:** `world.boundaries.factories.make_default_content_themes()` — a
  small starter `ContentTheme` set (child endangerment, suicide/self-harm, sexual
  violence, torture); not yet wired into a `world/seeds/clusters.py` cluster.
- **Integrates with:** stories (stakes contract enforcement + resolution), consent
  (`VisibilityMixin` reuse), roster (`RosterTenure` ownership), character_sheets /
  items / societies (typed subject FKs), scenes (`persona_handler` participant
  resolution for the lines-&-veils aggregate).
- **Source:** `src/world/boundaries/`; enforcement/sign-off/availability in
  `src/world/stories/services/boundaries.py`
- **Details:** [boundaries.md](boundaries.md)

### Narrative
General-purpose IC message delivery — GM/Staff/automated messages to characters. Used by stories for beat and episode-resolution informs; also available for atmosphere, visions, happenstance.

- **Models:** `NarrativeMessage` (body, ooc_note, category, sender_account, optional related_story / related_beat_completion / related_episode_resolution FKs), `NarrativeMessageDelivery` (message + recipient_character_sheet, delivered_at, acknowledged_at), `AmbientEmoteLine` (authored prose + weight/cooldown/fire-chance), `AmbientEmoteCondition` (0+ leaf conditions per line, AND/OR-composed)
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
- **Ambient room reactions (#2471 v2):** `AmbientEmoteLine` (authored prose + weight/cooldown/
  fire-chance) + `AmbientEmoteCondition` (0+ leaf conditions per line, AND/OR-composed) — species/
  resonance-threshold/distinction/fame-tier/legend-deed conditions compile (`world.narrative.ambient_content
  .compile_line_filter`) to real Trigger-system filter conditions, extending the DSL's existing
  method-dispatch pattern (`Character.has_property`/`has_capability`/`shares_covenant_with`) with
  four methods (`has_resonance_at_least`/`has_public_distinction`/`fame_tier_at_least`/
  `has_legend_deeds`). The `LEGEND_DEED` condition (#2523) gates on the entering persona having
  common-knowledge, non-secret deeds (via `Persona.legend_murmur` handler, cached). Lines with
  `{name}`/`{deeds}` placeholders in their body are dynamically templated from the entering
  persona's display name and deed titles (`_render_body`); static lines pass through unchanged.
  Dispatched via the existing Flows/Triggers `MOVED` event: at grid-bundle import
  (`core_management.grid_import._install_ambient_triggers`), lines are grouped by their compiled,
  identical condition set, and each distinct group gets one DERIVED `TriggerDefinition`/
  `FlowDefinition`/`Trigger` (not authored directly, not a fixed config singleton — computed from
  content, like `RegionWeatherState`). `deliver_ambient_group` only picks among an
  already-matched group's own lines (weighted + cooldown + fire-chance); it never re-decides
  whether a condition matched. Supersedes `world.societies.fame_reactions` (#881, retired).
- **Ambient room texture (#2988):** `AmbientEmit` (periodic room-*linger* flavor — fires
  while occupants remain, unlike entry-triggered `AmbientEmoteLine`; text-only, no NPC/
  encounter spawning). One model serves both roaming flavor and risk telegraphing — the only
  difference is whether `gate_stat_key` is set (a `StatKey` gate against
  `world.locations.services.effective_value`, single axis per row, mirrors `WeatherType`'s
  `min`/`max_temperature` shape). Plain nullable `area`/`room_profile` scope (not a
  `DiscriminatorMixin` pair — most rows are scope-free); selection
  (`world.narrative.ambient_texture.select_ambient_emit`) picks the most-specific non-empty
  scope pool (room > area > generic), filters season/phase flags (`WeatherEmit`'s exact
  shape) + cooldown + the state gate, then weighted-picks
  (`checks.outcome_utils.select_weighted`). Driver
  `roll_and_echo_ambient_texture` rides the `game_clock` scheduler exactly like
  `roll_and_echo_weather` (shared phase-transition guard,
  `game_clock.task_registry.phase_transitioned_since_last_run`); delivery audience is derived
  from **live sessions** (`evennia.SESSION_HANDLER`), never a grid-wide room scan. Delivered
  via `send_narrative_message` under `NarrativeCategory.ATMOSPHERE` (never `message_location`
  — this is a systemic emit, not actor-driven scene text). Content round-trip splits by scope
  like `AmbientEmoteLine`/`WeatherEmit`: room/area-scoped rows are meant to ride the
  grid-import bundle (not yet wired — admin-authored only today); scope-free gated-pool rows
  ride `content_export.py`'s natural-key round trip (`CONTENT_MODELS` entry
  `narrative.ambientemit`, filtered to `area`/`room_profile` both null via `EXPORT_FILTERS`).
  Risk telegraphing (a "seedy district can spawn pickpockets" read) is text-only here — actual
  encounter/NPC spawning off the gate is #2378's job, a later consumer of the same substrate.
- **Source:** `src/world/narrative/`

### Achievements
Cross-cutting meta-engagement layer: hidden milestones characters earn across every game system,
plus the shared access-change announcement surface that fires discovery ceremonies when a character
gains a discoverable content item for the first time.

- **Models:** `StatDefinition` (normalized stat key — dot-separated, e.g.
  `"relationships.total_established"`; `CONTENT_MODELS` since #2698), `StatTracker` (per-character integer counter),
  `Achievement` (staff-authored; `hidden` default True, `notification_level`, chained via
  `prerequisite` self-FK, `is_active`; natural key `slug`; `CONTENT_MODELS` since #2832),
  `AchievementStatRequirement` (stat threshold comparison per
  achievement; composite natural key `(achievement, stat, threshold, comparison)`; `CONTENT_MODELS` since #2832;
  renamed from `AchievementRequirement` by #2906's Task 3, disambiguating it from
  `progression.AchievementRequirement`),
  `Discovery` (OneToOne → `Achievement`; records first-ever earner timestamp plus a required
  `discovered_by_tenure` FK → `roster.RosterTenure` (`on_delete=PROTECT`) +
  `shared_with_tenures` M2M for simultaneous co-discoverers, anchoring the
  discovery to the (player-as-this-character) join object — a sheet with no player tenure is
  structurally incapable of claiming a first-ever slot, #3055),
  `CharacterAchievement` (earned record; required `earned_by_tenure` FK →
  `roster.RosterTenure` (`on_delete=PROTECT`, #3055) — stamped from the earning sheet's
  current tenure inside `grant_achievement`, giving every co-earner of a party grant their
  own individually durable (player, character) pairing, not just the primary `Discovery`
  slot's discoverer. No `discovery` FK exists — removed #3055 as a redundant parallel
  mechanism (credit died with the character, couldn't distinguish primary/shared);
  `is_discoverer()` derives discoverer status by comparing `earned_by_tenure` against the
  achievement's `Discovery.discovered_by_tenure`/`shared_with_tenures`),
  `RewardDefinition` (TITLE / BONUS / COSMETIC / PRESTIGE / DISTINCTION reward catalog;
  `distinction` nullable FK → `distinctions.Distinction`, mirrors `modifier_target`, #2037;
  natural key `key`; `CONTENT_MODELS` since #2832),
  `AchievementReward` (per-achievement reward with optional `reward_value` amount, or an
  explicit rank for DISTINCTION; composite natural key `(achievement, reward)`; `CONTENT_MODELS` since #2832),
  `PersonaTitle` (earned display-only title record on a `Persona`, not the character sheet,
  #3466; exactly one of `reward` (TITLE `RewardDefinition`) or `legend_entry`
  (`societies.LegendEntry`) is set — see `maybe_grant_deed_title`),
  `ConditionStatRule` (bridge: condition event type → stat increment; composite natural key
  `(stat, condition, event_type)`; `CONTENT_MODELS` since #2832),
  **`DiscoverableContent`** (abstract base — adds nullable `discovery_achievement` FK to any
  content model whose instances can be discovered for the first time; inherited by `Technique`,
  `CovenantRole`, and `CodexEntry`; null = not discoverable; see ADR-0061)
- **Enums:** `NotificationLevel` (PERSONAL / ROOM / GAMEWIDE), `ComparisonType` (GTE / EQ / LTE),
  `RewardType` (TITLE / BONUS / COSMETIC / PRESTIGE / DISTINCTION), `ConditionEventType` (GAINED),
  `AccessChangeSource` (ASSUMED_ALTERNATE_SELF / REVERTED_ALTERNATE_SELF /
  COVENANT_ROLE_ENGAGED / COVENANT_ROLE_DISENGAGED / CHARACTER_CREATION / PATH_ADVANCEMENT /
  GIFT_ACQUISITION / TECHNIQUE_GRANT / ACADEMY_TRAINING / CODEX_LEARNING)
- **Handlers:** `character_sheet.stats` (`StatHandler`) — `get(stat_def) -> int`,
  `increment(stat_def, n, *, check_achievements=True) -> int` (atomic F() expression; checks
  requirement thresholds after increment unless `check_achievements=False`, used by the batch
  seam below, #3075)
- **Key Services (`world/achievements/services.py`):** `grant_achievement(achievement,
  sheets) -> AchievementGrantResult` (`world/achievements/types.py` — frozen dataclass with
  `character_achievements: list[CharacterAchievement]` and `created_discovery: Discovery |
  None`, the latter non-None only when this call minted the achievement's Discovery row, the
  "first-ever" ceremony signal `execute_ceremony_beat` reads). Drops any sheet that fails
  `can_earn_achievements`, returning an empty result and creating no Discovery if none
  remain; for a first-ever grant, the Discovery's `discovered_by_tenure` is the *first*
  eligible sheet in the list — the triggering sheet for party grants; the remaining eligible
  sheets' tenures land in `Discovery.shared_with_tenures` as simultaneous shared credit;
  co-earners still get `CharacterAchievement` rows but no second Discovery, #3055; every
  earner's own `CharacterAchievement.earned_by_tenure` is stamped from that sheet's own
  current tenure, #3055),
  `can_earn_achievements(character_sheet) -> bool` (current, non-staff `RosterTenure`; #3024,
  ADR-0202), `apply_achievement_rewards(sheet, achievement)`,
  `get_stat(sheet, stat_def) -> int`, `increment_stat(sheet, stat_def, n) -> int`,
  `increment_stat_for_group(sheets, stat_def, n=1) -> None` (#3075, batch stat-check seam below)
- **Display rule (#3063):** `DiscoverySerializer.shared` (`world/achievements/serializers.py`)
  is `True` iff `shared_with_tenures` is non-empty — the primary `discovered_by_tenure` FK is
  pure bookkeeping in the group case (it has to point somewhere) and must never be read as a
  display privilege; every co-discoverer displays symmetrically as "shared". **A group grant
  must be ONE `grant_achievement(achievement, sheets)` call, never a per-sheet loop** — looping
  `grant_achievement`/`execute_ceremony_beat` once per participant lets the first iteration's
  call claim the sole `Discovery` row before the others run, so co-participants earn the
  `CharacterAchievement` but never land in `shared_with_tenures`. `fire_combo_discovery`
  (`world/combat/combo_discovery.py`) is the reference implementation: it grants the whole combo
  participant group in one call rather than routing through the single-sheet
  `execute_ceremony_beat` helper (see that module's docstring).
- **Batch stat-check seam (#3075):** `increment_stat_for_group(sheets, stat, amount=1)`
  increments every sheet's tracker with the per-sheet achievement check deferred
  (`StatHandler.increment(..., check_achievements=False)`), then runs ONE group evaluation
  (`_check_achievements_for_group`, the same evaluator `_check_achievements` delegates into for
  the single-sheet case) — per candidate achievement, the crossing set is every sheet (caller
  order) that meets the requirements now and doesn't already hold it, and `grant_achievement` is
  called once per achievement with that set, so the first crossing sheet takes the primary
  Discovery slot and the rest share it. A sheet that doesn't cross this increment earns the
  achievement solo, non-shared, later. Wired callers: combat encounter completion
  (`world/combat/services.py::_increment_completion_counters`, bucketed by outcome via
  `world/combat/achievement_counters.py::increment_combat_counter_for_group`) and relationship
  reciprocation (`world/relationships/services.py::create_first_impression`).
- **Access-change + discovery surface (`world/achievements/discovery.py` — ADR-0061):**
  - `announce_access_change(character_sheet, *, gained, lost, source)` — sends an ABILITY
    `NarrativeMessage` to the character listing what techniques/capabilities changed, then for
    each gained item with a non-null `discovery_achievement` FK fires `grant_achievement` and
    `announce_achievement`. Source-agnostic: callers never branch on covenant vs. form vs. CG.
    Gated by two eligibility checks before the per-item loop: (1) the same `can_earn_achievements`
    predicate `grant_achievement` enforces globally (#3024, ADR-0202), checked again here only to
    skip the ceremony (not the plain gained/lost message) early; (2) content reachable through a
    CG catalog table is excluded regardless of route (`_cg_catalog_exclusions`, #2899). Gate (2)
    remains local to this function by design; gate (1) is inherited by every `grant_achievement`
    caller, including paths outside this function such as `execute_ceremony_beat`; see
    `world/achievements/CLAUDE.md`.
  - `announce_achievement(earners, *, is_first, first_body, personal_body, category)` —
    gamewide to all active player sheets when `is_first` (first-ever Discovery); otherwise
    personal to the earner list.
- **Wired callers of `announce_access_change`:** `world/forms/services.py` (assume/revert
  alternate self), `world/covenants/services.py` (engage/disengage covenant role, via
  `_announce_capability_diff`), `world/character_creation/services.py` (CG starter-catalog
  Gift/Technique grant), `world/magic/services/technique_acquisition.py` (`learn_technique`),
  `world/magic/services/path_magic.py` (`grant_path_magic`), `world/codex/services.py`
  (`grant_codex_entry`, #2899)
- **API Endpoints:**
  - `GET /api/achievements/persona-titles/?persona=<id>` — a persona's earned titles, newest
    first; `persona` is required (400 if absent), #3466
- **Integrates with:** magic (`Technique` inherits `DiscoverableContent`; `discovery_achievement`
  FK), covenants (`CovenantRole` inherits `DiscoverableContent`), codex (`CodexEntry` inherits
  `DiscoverableContent`; `codex.entries_learned` stat, #2899), narrative
  (`send_narrative_message` with ABILITY category), roster (`active_player_character_sheets()`
  for gamewide first-ever recipient selection), mechanics (BONUS reward → `CharacterModifier`),
  societies (PRESTIGE reward → `award_deed_prestige`), distinctions (DISTINCTION reward →
  `grant_distinction(origin=ACHIEVEMENT_AUTO_GRANT)`, #2037), conditions (`ConditionStatRule`
  bridge), stories (reactivity hook `on_achievement_earned`)
- **Source:** `src/world/achievements/`
- **Glossary:** `src/world/achievements/AGENT_GLOSSARY.md`

### Tasking (covert orgs & spy networks)
The dual-fulfillment job primitive (#2820, all 5 phases): an org issues a discrete,
deadline-bearing `OrgTask` against an authored template; an NPC agent resolves it
offscreen as a double check (handler dispatch margin × agent tradecraft roll) with
outcome-tier payout routes, or a PC runs the template's linked mission into the
same routes. Spy networks, tax runs, crime jobs, and military actions are
consumers, not systems.

- **Models:** `TaskTemplate` (check + duration + `target_kind` + nullable
  `mission_template`/`consequence_pool`), `TaskOutcomeRoute` (per
  `traits.CheckOutcome` tier: money, clue-pool draw, report template; fail closed;
  nullable `collection_success_level` — set = this route lands the issuing org's
  `currency.collect_org_income` graded at that level via `success_level_override`,
  with the handler as collector; null = no collection, #696 item 2), `OrgTask`
  (status lifecycle, `DiscriminatorMixin` target), `TaskFulfillment`
  (`npc_asset` XOR `mission_instance`, stored dispatch check, report),
  `ListenerPost` (buzz meter on a LISTENER `NPCAssignment` + hidden counterplay
  state), `ListenerHarvest` (caught Secret XOR planted red herring)
- **Services:** `create_task`, `assign_agent` (own or issuing-org agents),
  `resolve_task` (risk via consequence pool with `ResolutionContext.npc_asset`
  scoping per ADR-0092), `resolve_due_tasks` (hourly cron), `accept_task` +
  `resolve_task_for_mission` (PC path, `_finish_terminal` seam),
  `listener_services` (post/sweep/collect — weekly cron `tasking.listener_sweep`;
  mechanical residue only, ADR-0175), `counterplay_services`
  (suppress/flip/plant/detect/clear; `espionage` consent category)
- **Covert layer (societies/assets):** `OrganizationType.is_covert`,
  `Organization.parent_org`, `OrganizationMembership.covert_secret`
  (`sync_covert_membership_secret` — level tracks rank tier),
  `NPCAsset.promoter_org` XOR `promoter_persona` (`transfer_asset_to_org`),
  `SPYMASTER_OFFICE` + `can_oversee_org`/`overseen_org_ids` (parent READ access)
- **API:** `/api/tasking/` — staff `templates/`+`routes/`; member `tasks/`
  (create/assign/accept), `roster/`, `posts/` (+collect), `counterplay/`;
  React `OperationsSection` (Roster/Postings/Operations) on `OrgPage`
- **Spy Job Kit (#2833):** ten route payouts (`spy_payouts.py`) —
  movements report, unmask (PERSONA_LINK), gossip heat ±, building
  condition ±, suborn-NPC, the incriminating-residue rule (handler
  secret + hub trail), plus cross-system payouts: domain report, domain
  unrest ± (foment/soothe), organization report (treasury banded),
  military strength assay; issue-time espionage consent gate covers PCs
  AND PC-led orgs/domains; sample templates in `world/seeds/spy_tasks.py`
- **Domain collection worked example (#696 item 3):** "Collect the Levies" —
  a DOMAIN-target `TaskTemplate` (`category=DOMAIN`, `check_type=Tax
  Collection`) linked to a single-node CHECK `MissionTemplate` of the same
  name, so a member can `accept_task` it as a mission; each terminal
  `CheckOutcome` tier's route grades `collection_success_level` straight off
  `currency.COLLECTION_BAND_PCTS`' own floors (2/1/0/-1; Critical Failure
  below -1 = catastrophe) — one payout surface, no mission-side MONEY reward.
  PLACEHOLDER prose/tuning throughout; seeded by
  `world.seeds.domain_tasks.seed_domain_collection_task` (the `domain_tasks`
  cluster, after `governance` + `missions`/`checks`).
- **Actions + telnet:** 11 REGISTRY actions (`actions/definitions/tasking.py`)
  are the ADR-0001 seam — viewsets dispatch through them; telnet `network`
  family (`commands/network.py`: board/issue/assign/accept/post/collect/
  sweep/clear/suppress/flip/plant)
- **Boundary:** standing "stay until recalled" postings are `NPCAssignment`
  rows, never tasks — every task ends; prose is never a surveillance input
- **Source:** `src/world/tasking/` · **Doc:** `docs/systems/tasking.md` ·
  **ADRs:** 0174, 0175
- **Glossary:** `src/world/tasking/AGENT_GLOSSARY.md`

### NPC Lifecycle (tier ladder)
One identity climbs a ladder of tiers on the sheet-spine (ADR-0176: the sheet is
the person; personas are faces — identically for PCs and NPCs). #2827, all 5
phases.

- **Models:** `StaffingProfile`/`StaffingProfileLine` (BuildingKind → baseline
  crew, applied at building activation + weekly `staffing.weekly_refill` cron),
  `Functionary.persona` (the materialization link), `NameCulture`/
  `NameCultureEntry` (area-resolved name pools; `Family.name` surnames),
  `PersonalityTrait`/`NpcPreference` (likes/dislikes with check-easing teeth),
  `tasking.NpcTaskAptitude` (job-family bands)
- **Services:** `staffing.py` (ensure/refill), `instantiation.py`
  (`materialize_functionary` — sheet+persona minted at first engagement via the
  `npc_start` hook; NPC-roster shelf entry), `personality.py`
  (`preference_modifier` → cultivation + counterplay rolls),
  `assets.extract_asset` (dual-mode recruitment: in-place default, extraction
  as a choice), `lifecycle.py` (`promote_to_standing`/`demote_to_instantiated`/
  `standing_candidates`/`graduate_to_roster`)
- **API:** staff CRUD `staffing-profiles|staffing-lines`, staff ops
  `/api/npc-services/lifecycle/…`, player `/api/assets/{id}/extract/`
- **Source:** `src/world/npc_services/` · **Doc:** `docs/systems/npc-lifecycle.md`

### NPC Services
Unified "ask NPC for thing" framework: per-NPC-role offer surface, persona-keyed standing,
per-kind effect handler dispatch. Covers permits today; missions/loans/training/favors
register as additional kinds.

- **Models:** `NPCRole`, `NPCServiceOffer` (kind discriminator + draw_mode + eligibility_rule),
  `PermitOfferDetails` (1:1 per-kind details; mirrors `ItemFacet` composition; fully
  authorable over `/api/npc-services/permit-details/` since #1684 — building_kind FK,
  default_approved_wards M2M, size cap, permit cost; `role` filter walks `offer__role_id`),
  `NPCStanding` (per-(PC persona, NPC persona); relocated from `world.missions.MissionGiverStanding`),
  `Functionary` (#1766 — a class-1 NPC placement = `NPCRole` + `room` FK; the non-piloted room-feature
  anchor for gameplay loops; see ADR-0070 for the Functionary/Standing NPC/Story NPC ontology),
  `NpcRegard` (#1717 — a notable NPC's signed opinion of a persona/Organization/Society;
  see the Regard bullet below and ADR-0085)
- **Content pipeline (#3056):** MISSION-kind `NPCServiceOffer` rows (+ `MissionOfferDetails`) are
  lore-repo content, natural key `(role, label)`; other offer kinds stay seeder-owned. See the
  missions "Content pipeline (#2470)" bullet for the full export/import detail.
- **NPC ontology (ADR-0070):** **Functionary** (class-1, abstracted, room-anchored via its own FK) /
  **Standing NPC** (class-2, named Persona + object) / **Story NPC** (class-3/4, object + sheet, piloted).
  Presence: `functionaries_in_room` / `functionary_in_location` (`world.npc_services.functionaries`);
  `hire <name>` prefers a co-located Functionary, falling back to a global role lookup; staff place
  them with the `functionary place/remove` command (`commands/functionary.py`); they surface on
  `look` (`actions.definitions.examine_extras.gather_examine_extras`, the `LookAction` seam —
  ADR-0213).
- **Reaction lines (#2632):** `NPCReactionLine` — banded, data-authored NPC reactions
  ("Alphonso sees to <name>…"): per-role defaults + per-functionary override sets;
  `metric` (`ReactionMetric`, ALLURE first — resolves via `reactions.METRIC_RESOLVERS`,
  one function per metric, never per-NPC code), `band_floor` (highest floor <= value
  wins), `<name>` interpolation. Leads the STYLING resolution message when authored;
  the serving placement resolves via `functionaries_in_location` (co-located
  functionary of the offer's role → its `display_name` + personal lines). Staff CRUD:
  `/api/npc-services/reaction-lines/`.
- **Styling & Archive profiles (#2632):** `StylingOfferDetails` (kind=STYLING — one offer
  per (cosmetic `FormTrait`, `FormTraitOption`), coppers price; `run_styling_offer`
  charges the purse then applies via the shared `change_appearance` seam),
  `ProfileRecordingOfferDetails` + `RecordedProfile` (kind=PROFILE_RECORDING — pay for an
  Archive sitting → COMMISSIONED `RecordedProfile`; the player's write-up completes via
  `complete_recorded_profile`, which sets the character's description through
  `character_sheets.set_physical_description` and archives the text forever with IC-date +
  Era stamps — the diegetic desc history). API:
  `/api/npc-services/recorded-profiles/` (owner-scoped list + `complete`). Seeds:
  `world.seeds.styling` (stylist + scribe roles, cosmetic templates incl. the
  enchanted-lens eye-color gate).
- **NPC-held clues (#3428):** `ClueRevealOfferDetails` (kind=CLUE_REVEAL — 1:1 `offer` +
  `clue` FK PROTECT → `clues.Clue`; mirrors `PermitOfferDetails`'s shape). Staff attaches a
  pre-authored clue to an `NPCRole`; `available_offers()` excludes the offer once the
  character's roster entry already holds the clue
  (`services._clue_reveal_not_yet_held`). Final offers skip the engine's own check
  application, so the handler (`run_clue_reveal_offer`) rolls `offer.check_type` /
  `check_difficulty` itself when set (mirrors `raise_court_grant`); on success (or a null
  check_type — auto-success) it calls `acquire_clue` + `grant_clue_target` — the same
  chokepoint Search/Research use — voiced as reaction-line flavor + the clue's description.
  Fails closed with a plain message when the finder has no roster tenure. See
  `docs/systems/investigation_and_discovery.md` for the clue-side detail. Editor: Mission
  Studio's `AddOfferForm`/`ClueDetailsPanel` (`NPCRoleEditorPage.tsx`) — no Django admin
  round-trip beyond a debugging-only `ClueRevealOfferDetailsAdmin`.
- **Constants:** `OfferKind` (PERMIT / MISSION / LOAN / COLLECTION / IMPROVEMENT (#930) /
  INFORMANT / CONTACT / PERSONAL_FAVOR / GUARD / FAN / MINOR_ALLY / ASSET_TASK_INTEL /
  ASSET_TASK_COLLECT / TRAIN (#2440) / SETTLE_OBLIGATION (#2428 whole-branch fix) /
  STYLING / PROFILE_RECORDING (#2632) / CLUE_REVEAL (#3428);
  `RecordedProfileStatus` (COMMISSIONED/RECORDED); future POLITICAL_FAVOR/...),
  `DrawMode` (MENU, POOL).
  `NPCServiceOffer.ap_cost` (#930) charges the resolving character before any effect
  dispatches (`InsufficientAPError` rolls the grant back) — a generic knob on every kind;
  TRAIN offers leave it at 0 and charge AP through the technique-acquisition multiplier
  seam instead (see below).
- **Effect dispatch:** `OFFER_EFFECT_HANDLERS: dict[str, Callable]` in
  `world.npc_services.effects` — keyed on `OfferKind`: `issue_permit` (buildings),
  MISSION (registered by `world.missions.apps.ready`), `grant_loan`, the #930
  domain-running pair `run_collection` / `run_improvement` (over
  `currency.collect_org_income` / `improve_org_domain`; org resolved via the shared
  `_resolve_authority_org` single-treasury-authority rule), and `run_train_offer` (#2440,
  below).
- **TRAIN offers — Academy training (#2440):** `NPCRole.teaches_tradition` (nullable FK →
  `magic.Tradition`, `SET_NULL`) scopes which tradition's signature techniques a trainer
  role can teach; `TrainOfferDetails` (1:1 per-offer details — `technique` FK, `learn_ap_cost`,
  `gold_cost`) authors **one offer row per teachable technique** (mirrors how MISSION/PERMIT
  enumerate per-template/per-kind rows — the smallest shape consistent with MENU/POOL
  selection; MENU-mode already lists every eligible offer as its own menu line). Handler
  (`run_train_offer`): resolve the Academy (`offer.role.faction_affiliation`) → obligation
  gate (`societies.obligation_services.has_open_obligation`, #2428 — an OWED Academy debt
  blocks further training) → availability gate (the learner's own (Path × Gift) pool
  (`PathGiftGrant`) ∪ their ACTIVE `CharacterTradition` membership's signature list
  (`TraditionGiftGrant`, `left_at__isnull=True` since #2441 Task 8 — see "Tradition
  membership lifecycle" below) via `magic.services.cg_catalog.get_technique_options`; a
  signature technique is teachable only when the trainer's own `teaches_tradition` matches
  the learner's currently active tradition — pool techniques are teachable by any Academy
  trainer regardless of tradition) → resolve exactly one unredeemed Golden Hare (`currency.FavorTokenDetails`)
  issued by the Academy and held by the learner (`NoAvailableFavorTokenError` if none) →
  charge AP + coin + the Hare → acquire via `magic.services.gift_acquisition
  .charge_and_learn` — the extracted shared charge+acquire core `accept_technique_offer`
  (#1587, player-to-player teaching) also delegates to; one seam, two front doors. The Hare
  is always redeemed to the ACADEMY (not the trainer's own taught tradition) — Hares are
  Academy-specific venue tokens (ruling on #2428). The generic `hire` command/
  `InteractionSession` loop lists and resolves TRAIN offers with no command-layer changes —
  the offer kind is fully expressible through the existing eligibility/dispatch machinery.
- **Great Archive self-study (#2440 ruling 5):** the post-Vanishing path for orphaned
  traditions — a quest-completion flag unlocks self-teaching, mechanically a TRAIN offer
  set on a "Great Archive Librarian" `NPCRole` (`faction_affiliation` = Shroudwatch
  Academy — same Hare/coin seam as any other Academy trainer; `teaches_tradition=None`,
  shared pool only). Gate mechanism: reuses `NPCServiceOffer.eligibility_rule` — already
  THE offer visibility/selectability predicate — with the existing `has_achievement` leaf
  (`world.predicates.predicates`) rather than a new FK; no migration needed for the gate
  itself. Seeded by `ensure_great_archive_librarian_role()` (`world.npc_services.seeds`),
  which also get-or-creates the PLACEHOLDER `Achievement` row
  (`GREAT_ARCHIVE_SELF_STUDY_ACHIEVEMENT_SLUG`) the offers gate on — granting it to a
  character is the lore-repo quest's job, not this seed's. Self-study teaches the shared
  (Path × Gift) pool only — it does **not** restore an orphaned tradition's own signature
  technique list; that recovery is story content, not a mechanical unlock.
- **Ghost tutors — summoned teachers for orphaned traditions (#2460):** a SERVICE-kind
  `Ritual` ("Summon Ghostly Tutor") dispatches `world.magic.services.ghost_tutor
  .summon_ghost_tutor`, which validates the performer has an active
  `CharacterTradition` membership for the target tradition (members-only) and
  creates a permanent `GhostTutelage` record. The tutelage extends
  `_technique_available_to_learner` (`world.npc_services.effects`) so the existing
  generalist Academy trainer (whose `teaches_tradition=None`) can surface that
  tradition's signature techniques for the summoning learner — the learner still
  pays AP + coin + a Golden Hare via the standard TRAIN offer / `charge_and_learn`
  seam. One summoning unlocks the entire tradition signature list (per-tradition
  scope); the tutelage is permanent (the story-gate is the summoning ritual's
  components + site access, not an upkeep loop). This is one route into the broader
  Path-discovery system (#2603); it does not model the full research/discovery
  progression that gates Path selection. Seeded by `wire_ghost_tutor_content()`
  (`world.magic.factories`), called by `seed_magic_dev()`.
- **Check-based technique training (#2727):** `resolve_training_check()`
  (`world.magic.services.technique_training`) wraps
  `contribute_to_technique_progress` with a learning check. The learner
  rolls intellect + the new "Arcane Theory" skill ("Technique Training"
  `CheckType`, seeded by `ensure_technique_training_content()`). The
  check outcome maps to a dev-point multiplier via
  `TrainingOutcomeAward(OutcomeTierAward)` (botch/failure=0×, partial=0.5×,
  success=1.0×, critical=1.5×). AP is always spent; only dev-point yield
  varies. `contribute_to_technique_progress` was changed to accept
  `dev_points` + `ap_to_spend` as co-equal params (decoupling AP from
  dev points). Difficulty: `target_difficulty = (technique.tier × step)
  − (learner_level // divisor) − teacher_skill_bonus
  + (self_study_penalty if teacher is None)`. Four tuning knobs on
  `GiftAcquisitionConfig`.
- **Player-facing training trigger (#2739):** the production caller #2727 shipped
  without. `TrainTechniqueAction` (`actions/definitions/technique_training.py`, key
  `"train_technique"`, REGISTRY, `category="magic"`) is the `action.run()` seam
  telnet and web converge on — resolves the learner's `TechniqueProgress` meter for
  a `technique_id` kwarg (no meter → clean failure naming the front doors that
  create one: accepting a teaching offer or an Academy TRAIN offer), resolves a
  co-present teacher (`progress.teacher_tenure`'s character sharing the learner's
  room *at session time* — Decision 3a: never a location hard-block, silent
  self-study fallback otherwise, true for both PC-teacher and Academy meters), and
  calls `resolve_training_check`. `ap_to_invest` defaults to 1 (no base-session-cost
  constant exists yet) and is rejected when non-positive; the action does not
  pre-bound it further — the seam spends it in full and raises
  `WeeklyTrainingCapExceeded`/`MagicError` (mapped to failure `ActionResult`s) or a
  bare `ValueError` (mapped the same way) when the meter's technique arrived by
  another route while the meter sat open (a staff grant, a `TechniqueGrant` item).
  **Telnet:** `CmdTrain` (`commands/training.py`, key `"train"`) — `train <technique>
  [=<ap>]` dispatches the action by resolved `technique_id`; bare `train` lists the
  caller's `TechniqueProgress` meters (name, progress/total, teacher-or-dash) with no
  dispatch. **Web:** `TechniqueProgressViewSet`
  (`world/magic/views_technique_progress.py`, routed at
  `/api/magic/technique-progress/`) — `GET` lists the scoped character's own meters
  (`TechniqueProgressSerializer`: technique id/name, `points_accumulated`/
  `total_required`, teacher name-or-null via `RosterTenure.display_name`, source
  label, a batched-query `weekly_remaining`); `POST <technique_id>/train/` dispatches
  the action, mapping a failure `ActionResult` to HTTP 400 with its message.
  Character scoping mirrors `MotifStyleViewSet` (#2030): `X-Character-ID` header,
  validated as owned, takes precedence over the active puppet. `<technique_id>` is
  the `Technique` pk (matching the action's own kwarg), not the `TechniqueProgress`
  row's pk — a technique with no meter yet surfaces the action's own "you aren't
  training that" failure as a clean 400 rather than a router-level 404. **Frontend:**
  `TechniqueProgressPanel` (`frontend/src/magic/components/`), mounted in
  `SpellbookTab` below `MotifStylePanel`, own-view only — one card per meter (progress
  bar/fraction, teacher-or-self-study, weekly remaining, an optional AP-to-invest
  input, a Train button); the session outcome and any 400 message render inline per
  row. See `frontend/src/magic/CLAUDE.md` for the wire-contract detail.
- **SETTLE_OBLIGATION — the Academy Registrar (#2428 whole-branch fix):** closes the gap
  where `societies.obligation_services.settle_obligation` (Task 1) shipped with no live
  caller — an Unbound Prospect had no in-game way to ever pay off their Academy entrance
  debt. Handler `run_settle_obligation_offer`: resolve the offer's org
  (`offer.role.faction_affiliation`) → fetch the learner's OWED `OrganizationObligation`
  against it (`None` → typed refusal, not an error) → resolve one unredeemed Golden Hare
  (reuses `_resolve_unredeemed_hare`, same row-lock as TRAIN) → `settle_obligation`
  redeems it and flips the row to SETTLED, inside one outer `transaction.atomic()`.
  Seeded by `ensure_academy_registrar_role()` (`world.npc_services.seeds`) as an
  ungated, always-visible offer on a class-1 "Academy Registrar" bursar role — a debtor
  must always be able to find someone to pay. A second seed,
  `ensure_academy_generalist_trainer_role()`, mirrors the Great Archive librarian's shape
  (same one-technique-per-starter-Gift sample) but with no achievement gate, so a
  fresh-DB Prospect has ≥1 reachable TRAIN offer immediately, without needing the
  Archive's not-yet-authored quest content. Both are PLACEHOLDER-flagged dev-minimum
  content — real Academy trainer curricula are lore-repo authored.
- **Tradition membership lifecycle (#2441 Task 8):** `magic.CharacterTradition` gained
  `left_at` (nullable) + a partial-unique `unique_active_tradition_per_character`
  constraint (`character` WHERE `left_at IS NULL`) — mirrors
  `societies.OrganizationMembership.left_at`. `unique_together` on `(character,
  tradition)` was dropped (a character may rejoin a tradition they previously left,
  creating a second historical row for the same pair). `world.magic.services.
  tradition_membership`: `join_tradition(sheet, tradition, *, via_membership=None)` —
  ends the active row (`left_at`), creates a new one, and — when the joined tradition
  is not orphaned (`_tradition_is_orphaned`, reading `character_creation.
  BeginningTradition.required_distinction__slug="orphaned-tradition"`, the only place
  "no living teachers" is recorded in the schema, per Task 5/#2428) — deletes any held
  `unbound`/`orphaned-tradition` drawback `CharacterDistinction` row (direct queryset
  delete; `grant_distinction` has no removal counterpart, see
  `world/distinctions/CLAUDE.md`). Raises `AlreadyInTraditionError` on a no-op re-join.
  `leave_tradition(sheet)` — `left_at` only, no replacement row; re-applies the
  `unbound` drawback via `grant_distinction(origin=DistinctionOrigin.GAMEPLAY)`
  (defensive no-op, logged, if the "unbound" `Distinction` isn't seeded yet — Task 9
  ships it), catching `DistinctionExclusionError`. Raises `NoActiveTraditionError` if
  already traditionless. **Wired trigger:** `societies.membership_services.
  _maybe_join_tradition`, called from both `accept_invitation` and `accept_application`
  when `organization.tradition_id` is set (ruling 1 on #2441 — a tradition is joined
  through its teaching org's membership-offer accept flow); swallows
  `AlreadyInTraditionError` so re-accepting an org invite never fails the membership
  accept. `leave_tradition` has no live caller yet — a symmetric
  `leave_organization`/`expel_member` hook is a natural future wiring point, deliberately
  left undecided by this task. Learned techniques are never revoked on switch (ruling 3,
  "learned is learned") — only the TRAIN-offer signature-list *access* gate
  (`npc_services.effects._technique_available_to_learner`) was upgraded to read
  `left_at__isnull=True`; `magic.services.ritual_knowledge.reconcile_ritual_knowledge`'s
  "all traditions in history" walk is deliberately unchanged (a different, intentionally
  permanent grant).
- **Unbound magic-learning AP surcharge (#2442):** the "Unbound" drawback `Distinction`
  (slug `unbound`, seeded by `world.seeds.character_creation
  .ensure_unbound_drawback_distinction`, mirroring Task 5's `orphaned-tradition` shape —
  `cost_per_rank=-2`, `max_rank=1`, category "Arcane") carries a +50 `DistinctionEffect` on
  the new `magic_learning_ap_cost` `ModifierTarget` (category `magic`, seeded by
  `wire_magic_learning_ap_cost_target`). `charge_and_learn` (`magic.services
  .gift_acquisition`) reads it live via `world.mechanics.services.get_modifier_total` (the
  post-CG `CharacterModifier` resolution path — NOT the CG-draft `_get_distinction_bonus`
  helper) and scales AP: `ceil(ap_cost × (100 + surcharge%) / 100)`, applied identically to
  both `charge_and_learn` front doors (accept + TRAIN). TIME, not power — resonance
  earning/spending is untouched (a corrected-in-review alternative: taxing resonance would
  have made the Unbound weaker, not slower). Every Unbound `BeginningTradition` row now
  carries `required_distinction=<Unbound drawback>` (was `None` pre-#2442); unlike Orphaned
  Tradition's deliberate "must already hold it" gate, `select_tradition`
  (`character_creation.views`) auto-adds the Unbound drawback to the draft when missing — a
  one-off exception preserving CG completability now that Unbound (CG's tradition-agnostic
  default) carries a gate. Shed by `join_tradition`/re-applied by `leave_tradition` above —
  the `CharacterModifier` row cascade-deletes with the `CharacterDistinction` row
  (`ModifierSource.character_distinction` is `on_delete=CASCADE`), so the surcharge
  disappears automatically, no separate cleanup.
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
- **Regard (#1717):** `NpcRegard` — a notable NPC's signed opinion
  (`-1000`..`1000`) of a persona/Organization/Society, mirroring
  `LocationOwnership`'s discriminator pattern. Read via `get_regard(holder_persona,
  target)`. Deliberately separate from `NPCStanding` (see ADR-0085). Consumed by
  Covenant of the Court's `has_regarded_target_present` engagement gate
  (`world/covenants/court_missions.py`).
- **Regard buildup / toxic-bond family (#2039):** `NpcRegardEvent` — a per-event
  ledger on top of `NpcRegard`, mirroring justice's `HeatSource`/`PersonaHeat`
  shape. `record_npc_regard_event(*, holder_persona, target, amount, reason,
  source_pc_combat_action=None, source_npc_combat_action=None, source_scene=None,
  source_stake_resolution=None)` (`world/npc_services/regard.py`) is the single
  write seam — wrapped in `transaction.atomic()`, clamps `amount` to
  `RegardEventConfig.max_event_delta` and the resulting `NpcRegard.value` to
  `REGARD_MIN`/`REGARD_MAX`. `NpcRegardEventReason` (6 values) each carry a
  distinct, DB-enforced citation requirement (`NpcRegardEvent.clean()`) — a
  PC-attributed reason (`NPC_HARMED_PC_INTEREST`, `PC_FOILED_NPC_PLAN`) must cite
  a real resolved `CombatOpponentAction`/`CombatRoundAction`, never a freetext
  claim; `SOCIAL_ACTION_RESOLVED` cites the resolved `Scene`;
  `STAKE_RESOLUTION` cites the `StakeResolution` row that pre-authored it;
  `GM_MANUAL_ADJUSTMENT` may optionally cite any of those; `DISTINCTION_SEED`
  cites none. `is_bond_story_vital(regard)` derives "vital to your story" status
  from `|value| >= RegardEventConfig.story_vital_threshold` — no stored flag,
  matching `NpcRegard`'s "no separate enemy flag" design; symmetric for hostile
  and infatuated (toxic-bond-family) valence alike. `record_npc_regard_event`
  also calls `stories.services.reactivity.on_character_state_changed(target.character_sheet)`
  inside its own transaction, after the relationships-track mirror call, so a
  `BeatPredicateType.NPC_REGARD_AT_LEAST` beat gated on this NPC's regard can
  flip in the same request instead of waiting for the character's next login
  (#3570)
  - **Four authoring paths:** (1) combat auto-hooks in
    `world/combat/services.py`'s `_resolve_pc_action`/`_resolve_npc_action_on_target`
    fire on a genuine defeat/critical-hit against a persona-backed opponent; (2) the
    structured-consequence `EffectType.SHIFT_NPC_REGARD` +
    `ConsequenceEffect.npc_regard_amount` + `_shift_npc_regard` handler
    (`world/mechanics/effect_handlers.py`) mirrors `SHIFT_AFFECTION` for social
    actions — content-authored amounts only, never GM-freehanded; (3)
    `StakeResolution.npc_regard_delta` (`world/stories/`) lets a GM pre-bind "if
    this stake resolves this way, regard shifts by N" before the scene plays out,
    dispatched through the existing `NPC_FATE` `subject_kind` branch; (4)
    `DistinctionRegardSeed` (lookup sidecar, mirrors `DistinctionResonanceGrant`'s
    shape) lets a CG distinction pre-seed a bond with a named NPC, reconciled via
    `reconcile_distinction_regard_seeds()` in the chargen `CharacterDistinction`
    bulk-create loop.
  - **Bridge to #2013:** `mirror_npc_regard_event_to_track(event)`
    (`world/relationships/services.py`) reuses `apply_affection_shift`'s
    track-selection/capstone-write-shape but dedups on the event row itself
    (no `Scene`+`ConsequenceEffect` needed) — every `record_npc_regard_event` call
    also mirrors onto the PC's own `CharacterRelationship`/`RelationshipTrackProgress`
    Regard/Friction system tracks, so #2013's hated-foe surge (unmodified) picks
    up nemesis buildup for free.
- **Interaction state machine:** ephemeral `InteractionSession` (lives in caller's
  session for one interaction). `start_interaction(role, persona, character, npc_persona=None)`
  → `available_offers(session)` (single-predicate filtered) → `resolve_offer(session, offer)`
  → `end_interaction(session)` (persists new affection for class-2+ NPCs).
- **Predicate engine reuse:** `world.predicates` (shared utility — see entry below).
  `min_npc_standing` and persona-scoped `has_item` leaves live there.
- **Seeding:** `ensure_builders_guild_clerk_role()`, `ensure_great_archive_librarian_role()`
  (#2440), `ensure_great_archive_self_study_achievement()` (#2440) in
  `world.npc_services.seeds` — idempotent get_or_create; NOT a committed fixture (per #683).
  The Archive seed rides the Big Button via the `"npc_services"` cluster
  (`world.seeds.clusters`), after `"progression"` (Shroudwatch Academy org + starter
  Gift/Technique catalog it depends on).
- **API:** `/api/npc-services/standings/`, `/api/npc-services/roles/`, `/api/npc-services/offers/`,
  `/api/npc-services/cooldowns/`, `/api/npc-services/permit-details/` — staff CRUD.
  `/api/npc-services/interactions/{start,resolve,end}/` — player-facing interaction state machine
  (session-backed; one active interaction per Django session).
  `/api/npc-services/summons/` — directed-offer summonses (#2050): GM/staff create + list; players
  list their own + respond via `/api/npc-services/summons/{id}/respond/`.
- **Cross-app dependencies:** `world.predicates` (engine), `world.scenes.Persona`,
  `world.items.ItemInstance`, `world.societies.Organization`, `world.checks` (perform_check
  for non-final check-based actions), `world.covenants` (Court grant config for summons
  escalation), `core.mixins`.
- **Source:** `src/world/npc_services/`

### NPC Guard Assignment (#2178)
Owner-gated NPC guard postings with post-arrival detection. A room owner
assigns a Functionary or NPCAsset as a GUARD; when an unauthorized character
enters, the intruder rolls Stealth vs. a difficulty constant.

- **Model:** `NPCAssignment` (`world.npc_services.models`) — join model with
  `DiscriminatorMixin` (Functionary XOR NPCAsset), `room` FK, `assignment_role`
  (GUARD/DOORMAN/SERVANT), `assigned_by` persona FK, `is_active`/`ended_at`.
  One active GUARD per room (partial unique constraint).
- **Detection service:** `check_guard_detection(character, room)`
  (`world.npc_services.guard_services`) — fires from
  `Character.at_post_move` as a `run_safely` block. Resolves the room's active
  GUARD; an unauthorized arrival branches on the sneak stance (#3288): a loud
  (non-sneaking) entrant is noticed automatically — no roll — while a sneaking
  entrant contests `resolve_security_check(SNEAK)` against
  `GUARD_DETECTION_DIFFICULTY` (PLACEHOLDER 50); a guard win strips the stance.
  On detection: room echo + owner `.msg()` if online and co-located.
- **Actions:** `assign_guard` / `unassign_guard` / `list_guard_assignments`
  (REGISTRY, `IsRoomOwnerPrerequisite`-gated, `target_type=SELF`).
- **Telnet:** `guard` command (`guard assign <npc>` / `guard unassign` / `guard`).
- **Deferred:** persistent security log.
- **Source:** `src/world/npc_services/guard_services.py`

### Mundane Stealth — sneak/unsneak stance (#3288, ADR-0228)
Hidden identity, disclosed presence: a sneaking character drops off IC
surfaces via the #1225 `Concealed` condition (sneak-sourced instances only —
magical concealment is untouched), while every room they occupy discloses an
identity-free unseen presence. Disclosure is one-way: arrivals always announce
(anonymous echo + `room_state` flag), departures are silent (normal "X leaves"
broadcast suppressed while sneaking). One concealment roll per room per visit
(`.ndb` anti-spam token); arriving re-rolls automatically — failure strips the
stance quietly and the arrival is a normal visible one.

- **Services:** `world.stealth.services` — `is_sneaking` / `start_sneaking` /
  `stop_sneaking` (instance-scoped by `source_description="sneaking"`),
  `roll_sneak` (SNEAK oracle vs `SNEAK_BASE_DIFFICULTY`, PLACEHOLDER 25),
  `reroll_on_arrival`, per-room token helpers, `refresh_room_state`.
- **Oracle:** `resolve_security_check` (`world.checks.security_services`) now
  delegates to `perform_check_with_modifiers` — conditions/equipment reach
  security rolls; first live caller of the #2180 SNEAK kind.
- **Actions:** `sneak` / `unsneak` (REGISTRY, `target_type=SELF`,
  `actions/definitions/stealth.py`). **Telnet:** `sneak` / `unsneak`
  (`commands/stealth.py`, `CmdHide`-style verb branch).
- **Movement hooks:** `Character.announce_move_from` (silent while sneaking) /
  `announce_move_to` (re-roll resolves BEFORE the announce; still-hidden →
  anonymous echo, never silence).
- **Disclosure:** `room_state` payload's `has_unseen_presence` — room-derived
  (any occupant with active concealment; scene-independent, unlike the
  scene-scoped #1225 unseen-observer banner, which is unchanged). Frontend:
  unseen-presence row in the room panel (`UnseenPresenceRow.tsx`) with the
  identity-free report dialog.
- **Report path:** `POST /api/player-submissions/player-reports/hidden-presence/`
  — `report_hidden_presence` (`world.player_submissions.services`) resolves the
  room's concealed occupants into staff-visible `PlayerReport`s; the reporter
  never learns identity.
- **Counter-play:** the existing `search` verb (`SearchAction`, AP+fatigue)
  already pierces concealed characters per-observer — no new discovery verb.
- **Source:** `src/world/stealth/services.py`

### Servant/Doorman Assignment, Pampering Ambience, Expulsion (#2989)
Household daily-life behaviors riding the #2178 `NPCAssignment` substrate:
SERVANT/DOORMAN assignment mirrors GUARD's action triplet; servants pamper
(meal/bath prep, servant-fetch's delay+echo idiom) and a doorman announces
every arrival (deterministic, no check). A separate, unresistable OOC
expulsion valve (`ExpulsionBar`) covers "get rid of a disruptive character" —
access-challenge doorman behavior stays deferred pending a real
invitation/guest-list primitive (see the #2989 spec's Decision 4).

- **Actions:** `assign_servant` / `unassign_servant` / `list_servant_assignments`
  and `assign_doorman` / `unassign_doorman` / `list_doorman_assignments`
  (REGISTRY, `IsRoomOwnerPrerequisite`-gated, `target_type=SELF`,
  `actions/definitions/npc_assignments.py`). `assign_guard`/`unassign_guard`/
  `list_guard_assignments` (#2178) were refactored onto the same
  `_assign_npc_role`/`_unassign_npc_role`/`_list_npc_role` helpers when
  SERVANT/DOORMAN shipped — one implementation of "assign/unassign/list an
  NPC role" parameterized by role, not three near-duplicate GUARD-only
  bodies plus three more for SERVANT/DOORMAN; guard behavior/messages are
  unchanged (existing guard tests are the regression oracle).
  `servant_prepare_meal` / `servant_prepare_bath` (REGISTRY, gated
  like servant fetch — owner/tenant standing + an active SERVANT in reach,
  not owner-only) and `expel_character` / `lift_expulsion_bar` (REGISTRY,
  `IsRoomOwnerPrerequisite`-gated) live in `actions/definitions/npc_ambience.py`.
- **Telnet:** `servant` (`servant assign <npc>` / `unassign` / `meal` / `bath`),
  `doorman` (`doorman assign <npc>` / `unassign`), `expel <character>` /
  `expel/lift <character>` (`commands/servant.py`, `commands/doorman.py`,
  `commands/expulsion.py`).
- **Doorman announcement:** `announce_arrival(character, room)`
  (`world.npc_services.doorman_services`) — fires from `Character.at_post_move`
  alongside `check_guard_detection`; deterministic room echo naming the
  arriver via the doorman's `get_active_target_name()`, excludes the arriving
  character. No check, no owner/tenant gate — announces everyone.
- **Servant pampering ambience:** `prepare_meal(actor)` / `prepare_bath(actor)`
  (`world.npc_services.servant_ambience`) — same delay+departure/arrival-echo
  shape as `servant_fetch.servant_fetch_item`. Meal is pure ambience (no
  mechanical payoff — "appetites"/"catering" don't verify as a hookable
  ordinary-meal system, see the #2989 spec's anti-reinvention ledger). Bath
  additionally recovers a flat amount of PHYSICAL fatigue via
  `world.fatigue.services.recover_fatigue` (the #2852 partial-recovery seam
  food/drink already ride) — a genuine one-line hook, so it's wired rather
  than staying prop-only.
- **Household word-spread — deferred, not one line:** `world.tidings.services
  .house_feed_for` is a read-only aggregator over other domains' own models
  (Stature shifts, proclamations, open crises) with no generic
  push-a-custom-message write path, so servant-carried household word-spread
  (ratified amendment 1) does not verify as a one-call hook and ships
  deferred, pending the future Arx-1-style messenger system.
- **Expulsion (unresistable OOC soft gate):** `world.npc_services
  .expulsion_services.expel_character(actor, target, imposed_by)` — moves the
  target through the room's first exit (deterministic, ordered by `db_key`)
  and writes/reactivates an `ExpulsionBar`. No check, no roll, no
  prerequisite bypass on the target, regardless of character power — a
  consent/disruption valve, not a combat surface. `lift_expulsion_bar(room,
  name)` clears an active bar by the barred character's name.
- **Model:** `ExpulsionBar` (`world.npc_services.models`) — `room` FK
  (RoomProfile), `barred_sheet` FK (CharacterSheet), `imposed_by` persona FK,
  `imposed_at`/`lifted_at` (null while active). Partial-unique per
  `(room, barred_sheet)` while `lifted_at IS NULL`, mirroring
  `NPCAssignment`'s active-row pattern.
- **Entry enforcement:** pre-traversal at every commit-a-move seam (not
  post-arrival like guard detection/ward reaction, since a barred character
  must never even land in the room) — all three read
  `expulsion_services.active_bar_for(destination, caller_sheet)` before the
  move. `flows.service_functions.movement.check_exit_traversal` raises
  `CommandError` (covers ordinary exit traversal and `TravelAction`'s
  walking hop-pacing, both call it). `world.magic.services.portal_travel
  .perform_portal_travel` raises the same `CommandError` before any anima
  debit or broadcast (covers `TravelAction`'s portal fast-path, the DEFAULT
  route when a portal exists — `_try_portal_travel` catches it and returns a
  failure `ActionResult`). `actions.definitions.movement.HomeAction` checks
  inline and returns a failure `ActionResult` (covers the `home` command, a
  narrower vector: only reachable when a barred character's declared home is
  the room they were shown out of).
- **Source:** `src/world/npc_services/doorman_services.py`,
  `src/world/npc_services/servant_ambience.py`,
  `src/world/npc_services/expulsion_services.py`

### Missions & Living Grid
Branching narrative quest chains — a character receives a mission with broad objectives,
makes decisions at branching points gated by skills/traits/predicates, and the consequences
reshape the world around them. No engine arbitration: the player picks, pick+check routes;
state is node position + snapshots + already-applied consequences, never a scratch blob.

- **Models:** `MissionTemplate` (authored graph: entry node + availability metadata — level
  band, risk tier, draw weight, visibility) → `MissionNode` (`track_successes`/
  `track_failures`/`track_success_target`/`track_failure_target`/`track_success_beat_outcome`/
  `track_failure_beat_outcome`, #3568 - a progress-track node: 0/0 = not a track, both
  thresholds travel together; `is_track` property reads `track_successes > 0`) →
  `MissionOption` (`OptionKind`: `BRANCH` / `CHECK` / `EXTERNAL_ACT` / `ENCOUNTER` (#3565) /
  `CONTEST` (#3568 - a CHECK whose difficulty adds `level_opposition` for the option's
  `opposition_sheet` at `effective_combat_level`, checked with `opposition_check_type`; the
  NPC never rolls, tiers and routes are a CHECK's)) → `MissionOptionRoute`
  (outcome-tier-keyed, optionally weighted `Candidate`s; `beat_outcome` (SUCCESS/FAILURE,
  blank), meaningful only on a terminal route, #3565 - a terminal route can declare the
  linked story beat FAILURE even when the party reached an ending, so walking away isn't
  silently a win) → `MissionOptionRouteReward` (`DeedRewardSink`: MONEY / LEGEND_POINTS /
  RESONANCE / RUMOR / CRIME_WATCH / BEAT / ITEM / FOLLOW_ON_SUMMONS / PROJECT).
  `MissionInstance` (the live run — `current_node`, participant set, status),
  `MissionParticipant`, `MissionDeedRecord` (+ child `MissionDeedRewardLine` rows, no dict
  payloads), `MissionTrackProgress` (#3568 - per-run `successes`/`failures` counter for a
  track node, one row per (instance, node); `enter_node` resets it to 0/0 on every entry,
  matching `MissionNodeSnapshot`'s per-visit semantics; play state, resettable),
  `MissionRiskAcknowledgement`, `MissionRunTale` (#2047 player-authored epilogue),
  `MissionGiver` (`GiverKind`: `ROOM_TRIGGER` / `ENVIRONMENTAL_DETAIL` / `BOARD` — a Notice
  Board), `MissionAssistPattern` (support-move density catalog), `MissionInvite`/
  `MissionGroupBallot` (co-op), `MissionOption.encounter_risk_level` (`RiskLevel`, ENCOUNTER
  options only, #3565), `MissionOptionOpponentLine` (the `BeatOpponentLine` shape keyed on
  an ENCOUNTER option instead of a beat, #3565).
- **External-Act Beat (#1035, ADR-0112):** `OptionKind.EXTERNAL_ACT` +
  `MissionOption.required_act` (`ExternalAct`: `TECHNIQUE_CAST` / `THREAD_WOVEN` /
  `COVENANT_SWORN`) — an option presented like any other but never pickable; it resolves when
  `satisfy_external_act(character_sheet, act)` (`world.missions.services.external_acts`) is
  called directly (log-and-continue) from `weave_thread`, `create_covenant`/
  `induct_member_via_session`, and `use_technique` after each succeeds. Durable acts
  (`THREAD_WOVEN`/`COVENANT_SWORN`) also fast-forward at `enter_node`; `TECHNIQUE_CAST` never
  does. Powers the seeded Tutorial Chain (`world.seeds.game_content.tutorial`, `"tutorial"`
  seed cluster) — seven templates walking a new character through the level-1 loops.
- **Story beats run on the scenario graph, GM-owned scenarios (#3565):** `StoryScenario`
  (`world.stories`) links a `MissionTemplate` to a story with no reverse FK from missions
  (ADR-0010) - ownership reads through `template.story_scenario.story`. A story-owned
  template is created RESTRICTED with an empty `availability_rule` and `base_weight=0`, and
  is excluded from `services/boards.py`/`services/opportunities.py`'s querysets by
  `story_scenario__isnull=True`, so a GM's scenario never becomes a public quest offer.
  `IsStaffOrScenarioOwner` (`world.missions.permissions`) opens `MissionTemplateViewSet` /
  `MissionNodeViewSet` / `MissionOptionViewSet` / `MissionOptionRouteViewSet` /
  `MissionOptionRouteCandidateViewSet` / `MissionOptionRouteRewardViewSet` /
  `MissionCategoryViewSet` (read) / `PredicateLeafCatalogViewSet` (read) to a Lead GM over
  their own story's scenarios, staff unrestricted; `MissionGiverViewSet` and
  `MissionInstanceViewSet` stay `IsAdminUser`. Read scope: `scenario_scope_q` (OPEN templates
  within the caller's risk cap, OR a `StoryScenario` their table leads); write scope:
  `user_leads_template`. `max_risk_tier_for` caps a non-staff author's writes at the
  `RiskLevel`↔`RenownRisk` mapping of their `GMLevelCap.max_beat_risk`
  (`world.gm.services.gm_max_risk`, moved off `world.stories.serializers._gm_max_risk` so
  neither app imports the other for it). Template creation is staff-only except through
  `POST /api/beats/{id}/scenario/` (`world.stories.services.scenarios.create_scenario_for_beat`)
  - a GM cannot create a bare `MissionTemplate` and cannot take ownership of a catalog one.
  Frontend: `MissionCanvasPage`/`NodePage`/`OptionPage` (unchanged components) mount a second
  time under `/stories/scenarios/:id/canvas|nodes/:nodeId|nodes/:nodeId/options/:optionId`
  behind `GMRoute` (`account.is_gm || account.is_staff`), alongside the staff-only
  `/staff/missions/...` mount; `studioPaths` (`frontend/src/missions/studioPaths.ts`) is the
  shared link builder both mounts' pages use so the components stay identical between them.
  `scenario_scope_q`'s OPEN branch also requires `risk_tier__gte=1` (#3562) - `risk_tier=0` is
  an unset sentinel, never a living tier, and without the floor it slipped into scope under any
  positive ceiling (`0 <= max_risk_tier_for(user)` for any GM with a profile).
  `BeatSerializer.validate` (`world.stories.serializers`) reuses `scenario_scope_q` too: a
  non-staff GM's `required_mission` write is rejected (`{"required_mission": "..."}`, 400)
  unless the template is in that same scope - see `docs/systems/stakes.md`'s API table for the
  sibling GM readiness endpoint this task also added.
- **ENCOUNTER option: objective-first (#3565, ADR-0258):** picking (or a group vote landing
  on) an ENCOUNTER option creates a `CombatEncounter` in the scene via the same service
  `RunBeatAction._run_encounter_beat` uses, spawns the option's authored
  `MissionOptionOpponentLine` roster (`world.combat.encounter_prep.spawn_opponent_lines`),
  pauses the run (`MissionInstance.is_paused`), and stamps the pending
  `MissionDeedRecord` on `CombatEncounter.scenario_deed` (SET_NULL) - never
  `story_beat`. `start_encounter_for_option`/`complete_encounter_for_option`
  (`world.missions.services.encounter_option`) mint the deed+fight and, on
  `ENCOUNTER_COMPLETED`, classify the encounter's (outcome, risk_level) via
  `classify_battle_outcome` + `EncounterOutcomeMapping` into a `CheckOutcome` tier and route
  it through `resolution._route_graded_outcome` exactly like a rolled CHECK. FLED and
  ABANDONED are tiers like any other here - the GM authors their routes, required content on
  the admin sentinel (#3444) alongside #3559's rows. `world.combat.beat_wiring
  .encounter_completed_beat_handler` branches on `encounter.scenario_deed_id` first: a
  scenario ENCOUNTER never touches the linked story beat, only the graph's eventual terminal
  does (a fight is incidental to the objective, never grades the beat by itself).
- **CONTEST option and track nodes - multi-stage scenes on the scenario graph, not a second
  engine (#3568, ADR-0265):** `OptionKind.CONTEST` resolves inside `resolve_option` exactly
  like an AUTHORED CHECK, except the target difficulty is `instance.template.risk_tier +
  _contest_opposition(option)`, where `_contest_opposition` adds
  `level_opposition(option.opposition_check_type, level=effective_combat_level
  (option.opposition_sheet), character=option.opposition_sheet.character)` - the opposition
  is an authored `CharacterSheet` (usually an NPC's), never a second roller; its passive level
  term is the only cost. `MissionOption.clean()`'s `_contest_errors` requires AUTHORED source,
  both check types, `opposition_sheet`, and forbids `branch_target` (a CONTEST is always a
  dice resolution, like a CHECK). A **track node** is a `MissionNode` with both
  `track_successes`/`track_failures` set (`is_track`): its CHECK/CONTEST options' routes may
  not set `target_node`/`is_random_set` (`MissionOptionRoute.clean()`) - "the track decides."
  `_route_graded_outcome` still applies the resolving route's per-tier consequence, then (when
  `node.is_track` and the option is CHECK/CONTEST) hands the graded deed to `_advance_track`
  instead of routing/terminating; `tier_is_success(outcome)` (`success_level >= 1`) decides
  which counter on the per-run `MissionTrackProgress` row increments. Reaching
  `track_successes` routes to `track_success_target` with `track_success_beat_outcome` (default
  SUCCESS); reaching `track_failures` routes to `track_failure_target` with
  `track_failure_beat_outcome` (default FAILURE); `_end_track` enters the target node when set,
  else calls `_finish_terminal(instance, beat_outcome=...)` for a null target. `enter_node`
  resets a re-entered track's counter to 0/0. `MissionNode.clean()`'s `_validate_track` forbids
  a track node on `ConflictMode.JOINT` (each attempt would count once per participant, not
  once for the node) and forbids ENCOUNTER/EXTERNAL_ACT options on a track
  (`_track_node_kind_errors`) - a track's tier comes only from a CHECK or CONTEST deed.
  Presentation: `TrackView` (`successes`/`needed`/`failures`/`allowed`, counts only - no
  opposition sheet, no check type, no difficulty number) on `BeatView.track`/
  `GroupBeatView.track`, built by `services/play.py`'s `_track_view`; the web `BeatCard`/
  `GroupBeatCard` render it via the generic `frontend/src/components/ui/pips.tsx` `Pips`
  component (two rows: successes toward the threshold, failures toward theirs) rather than a
  bespoke scene-clock widget. `MissionNodeSerializer`/`MissionOptionSerializer`/
  `MissionOptionRouteSerializer` (`world.missions.serializers`) each gained a `validate()` that
  builds a probe model instance and calls its `clean()` - DRF's `ModelSerializer` skips
  `clean()` on `save()`, so without this a bad CONTEST/track row 500'd instead of 400'ing (the
  fix also closed two pre-existing gaps: `MissionOptionRoute.save()` never called `clean()` at
  all, and the node/option serializers hadn't mirrored their models' pre-#3568 kind-pairing
  invariants either).
- **Key services:** `services/resolution.py` (`resolve_option`, `enter_node` (resets
  `MissionTrackProgress` on track re-entry, #3568), `tier_is_success` (#3568 - whether a graded
  `CheckOutcome.success_level >= 1`), `_route_graded_outcome` - shared tier-routing tail for a
  rolled CHECK, a completed ENCOUNTER (#3565), and a track-node CHECK/CONTEST hand-off to
  `_advance_track` (#3568), `_advance_track`/`_end_track` (#3568 - count a track deed and route
  a threshold hit)), `services/run.py` (`start_scenario_for_scene(beat, scene)` - starts or
  rejoins the beat's scenario for the scene's whole party, #3565), `services/beat.py`
  (`beat_outcome_for_route`, `on_mission_complete_for_beat(instance, *, route=, option=,
  beat_outcome=)` - the mission→beat report-back seam, reads the resolving option's key and
  applies the `beat_outcome` rule before calling `stories.services.beats
  .record_scenario_outcome`, #3565; the `beat_outcome` keyword (#3568) overrides the derived
  outcome with a track node's authored terminal outcome - the route's graded tier, when any,
  still records as `outcome_tier`),
  `services/encounter_option.py` (`start_encounter_for_option`, `complete_encounter_for_option`,
  #3565), `services/play.py` (journal/beat presentation + `abandon_mission`), `services/report.py`
  (after-action payout + `ReportStyle`), `services/boards.py` (Notice Board preview-then-take),
  `services/opportunities.py` (here/nearby/your-orgs discovery), `services/multiplayer.py`
  (GROUP_VOTE/JOINT group beats), `services/rewards.py` (deed reward routing).
- **Court situational-perk scoping (#2536 slice 3, ADR-0153):** all six mission `perform_check`
  call sites — `resolution.py`'s `_resolve_challenge_check` + `resolve_option`'s AUTHORED CHECK
  branch, `support.py`'s `_roll_and_bank`, `report.py`'s `_run_embellish_check` /
  `_run_consequence_dodge_check` / `_apply_masked_deed_association` — thread a
  `SituationContext(mission=instance, ...)` via the shared `services/_situation.py
  .mission_situation_ctx(character, instance)` helper (hoisted out of the three call-site files
  where it was originally byte-for-byte duplicated), so a Court-scoped `VowSituationalPerk`
  (`mission_category`/`mission_template` scope columns) can fire on a mission check.
  `mission_situation_ctx` returns `None` when the character has no `CharacterSheet` — mirrors
  `checks.services._situational_perk_check_bonus`'s own sheet guard, so a checker without a
  sheet stays byte-identical to the pre-#2536 default.
- **Legend-Risk Floor (ADR-0107):** any `LEGEND_POINTS`-sink reward or legend-paying renown
  award requires the parent template's `risk_tier ≥ LEGEND_RISK_FLOOR_TIER` (4); enforced at
  `clean()`. See also the Co-Presence (Solo-Darkness) Guard entry in the missions
  `AGENT_GLOSSARY.md` for the broader solo-legend stance.
- **Report target required to pay out (#1753, #3040):** `report_to_role_for(instance)` —
  `MissionTemplate.report_to_role`, else the accepting `NPCServiceOffer.role` — decides
  whether a terminal run pauses at RESOLVED (awaiting a report) or jumps straight to COMPLETE
  with no payout (`_finish_terminal`, `services/resolution.py`). A trigger/environmental/board
  grant carries no `source_offer`, so its template must set `report_to_role` explicitly or its
  authored MONEY/RESONANCE/etc. lines are silently orphaned — the starter board's 3
  `MissionTemplate` rows (`world.seeds.game_content.missions`) and the Tutorial Chain's T1/T2
  (`world.seeds.game_content.tutorial`) all set it to the "Threshold Warden" `NPCRole`
  (co-located with both the board and the tutor Functionary in the canonical starting room);
  T4-T7 set it too for robustness against a non-offer grant (e.g. `staff_assign_mission`).
- **API:** `/api/missions/journal/` (+ `.../opportunities/`, `.../{id}/report/`,
  `.../{id}/tale/`, `.../{id}/invite/`, group-pick/vote/beat), `/api/missions/boards/<pk>/take/`.
  Authoring viewsets (`/api/missions/templates/`, `/api/missions/nodes/`,
  `/api/missions/options/`, `/api/missions/routes/`, ... - `world.missions.urls`) are
  `IsStaffOrScenarioOwner`-gated (#3565, see above), not `IsAdminUser` any more;
  `POST /api/beats/{id}/scenario/` (stories app) and `GET /api/scenes/{id}/scenario/`
  (scenes app) are the story-side authoring and play seams - see stories.md.
  `.../{id}/report/` request/response are typed (`MissionReportRequestSerializer`/
  `MissionReportResultSerializer`, #3040 — was raw dict access). The web Journal
  (`frontend/src/missions/pages/JournalPage.tsx`) surfaces a RESOLVED entry under its own
  "Awaiting report" section with a `ReportMissionDialog` offering all four `ReportStyle`
  choices; a co-location 400 renders inline verbatim rather than being pre-computed client-side.
- **Web front doors (#3044):** the three authored discovery surfaces are mouse-reachable in
  the room view, not just typed telnet commands. **Board:** `ObjectsList`
  (`frontend/src/game/components/room-panel/ObjectsList.tsx`) flags a row `is_mission_board`
  (a batched `MissionGiver.objects.filter(giver_kind=BOARD, is_active=True, target_id__in=...)`
  lookup added to `ObjectStateSerializer`/`RoomStatePayloadSerializer`,
  `flows/service_functions/serializers/room_state.py` — a board has no dedicated typeclass, so
  this can't be derived from the payload's existing fields) and offers "View Board", opening
  `MissionBoardDialog` (`frontend/src/missions/components/MissionBoardDialog.tsx`) over the
  pre-existing `GET .../boards/<pk>/postings/` + `POST .../take/` client (`getBoardPostings`/
  `takeBoardPosting`, previously dead code with zero consumers). **Examine:** `ObjectsList` rows
  expand on click and dispatch the `look` REGISTRY action (`{ref: {backend: 'registry',
  registry_key: 'look'}, kwargs: {target: <objectdb pk>}}`) through the same
  `dispatch_player_action` seam telnet's `CmdLook` uses, rendering the returned description
  inline. This closes a real gap found while wiring it: `LookAction.execute()`
  (`actions/definitions/perception.py`) renders through the flows-layer
  `BaseState.return_appearance`, which never touched the mission
  ENVIRONMENTAL_DETAIL/BOARD-rendering hook on `ObjectParent.at_examined`
  (`typeclasses/mixins.py`) — that hook only fires from the typeclass's OWN
  `return_appearance`, which nothing in the live look pipeline (telnet included) actually
  called. `LookAction.execute()` called `maybe_dispatch_on_examine` explicitly (`run_safely`,
  matching the mixin's own pattern) so examine-triggered mission dispatch worked from real play on
  BOTH surfaces for the first time, not just from tests that called the service directly — #3084
  later generalized this into `actions.definitions.examine_extras.gather_examine_extras`, the one
  aggregation seam for every examine-time display extra (see ADR-0213), and deleted the dead
  typeclass path entirely. Also
  added the precedented `_resolve_look_target` int-pk fallback (mirroring `_resolve_room`/
  `_resolve_identify_target`) since REST dispatch sends a raw int, never a pre-resolved
  `ObjectDB`. **NPC talk:** `Functionary` placements (class-1+ NPC givers — carry no `ObjectDB`
  of their own, so they can never appear in the room's `characters`/`objects` lists) surface as a
  new `npc_givers` room-state field (`role_id` + display name, room-scoped via
  `RoomProfile`/`get_room_profile`); `NpcGiversBlock`
  (`frontend/src/game/components/room-panel/NpcGiversBlock.tsx`) renders a "Talk" button per
  giver that mounts the pre-existing `NPCInteractionDialog` (previously only reachable from
  `OrgBooksPage`) — same dialog, no fork. The Opportunities tab is deliberately untouched
  (ADR-0094: it stays the map, never a door).
- **Telnet:** `CmdMission` (`commands/missions.py`) — thin face over `services.play`, no
  separate Action; `mission`/`mission beat`/`mission resolve`/`mission report`/`mission take`/
  `mission invite`/`mission pick`/`mission vote`.
- **Integrates with:** `npc_services` (`NPCServiceOffer(kind=MISSION)`, Notice Board givers,
  Directed Summons via `OfferSummons`), `magic` (thread weaves, technique casts),
  `covenants` (covenant founding/induction; Layer 4 Court situational-perk scoping via
  `mission_situation_ctx`, #2536 slice 3), `predicates` (`availability_rule`/`rule_json`
  gating, `has_completed_mission` chain leaf), `mechanics` (Challenge-sourced options),
  `stakes contract engine` (`activate_stakes_for_instance`), `justice` (CRIME_WATCH sink).
- **Content pipeline (#2470):** `MissionTemplate`/`MissionNode`/`MissionOption` (+ authored `key`
  slug)/`MissionOptionRoute`/`MissionOptionRouteCandidate`/`MissionOptionRouteReward` (+ NK-only
  `sequence`, auto-assigned in `save()`)/`MissionRenownAward` (+ `sequence`) all carry
  `NaturalKeyMixin` and are in `core_management.content_export.CONTENT_MODELS` — the lore repo can
  author a mission graph as a fixture and install it via the ordinary export/import pipeline, same
  as any other content model. `checks.CheckType`/`checks.CheckCategory` joined the allowlist in the
  same change (needed for `MissionOption.authored_check_type` to round-trip). `checks.Consequence`
  remains un-keyed (documented gap). `npc_services.NPCServiceOffer` gained a `(role, label)` natural
  key in #3056: MISSION-kind offers (+ `MissionOfferDetails`, keyed on its O2O `offer`) are exported
  content, filtered to `kind="mission"` via `EXPORT_FILTERS`, with `source_beat`/`target_project`
  stripped via `EXPORT_FIELD_EXCLUSIONS`, so `MissionOptionRouteReward.followon_offer` round-trips
  by natural key; other offer kinds stay seeder-owned. The seeded Tutorial Chain is unaffected -
  it predates this pipeline and stays imperatively seeded.
- **Source:** `src/world/missions/`. Roadmap: `docs/roadmap/missions.md`.

### Currency & Org Economy (#923–#932, #930 active collection)
Ledger money (`transfer` is the single audited mutation point), org treasuries/books, and
the **active-collection income model** (ADR-0081): income never lands passively — each
`OrgIncomeStream` accrues its gross into an uncapped `uncollected_pool` weekly, and money
reaches the treasury only through a steward-summon collection dispatch whose Tax
Collection check band decides how much of the gathered aggregate arrives (graft leaks off
the *collected* amount; the catastrophic band loses the whole pool — collector-incident
encounter seam, combat domain). Obligations/withholding ride collection declarations, so
an idle org reaches stasis in both directions (loan interest still accrues — opted-in risk).

- **Models:** `CharacterPurse`, `OrganizationTreasury`, `CurrencyTransfer` (audit),
  `OrgIncomeStream` (`uncollected_pool`, optional `area` FK — authored anchor for a future
  local order/crime difficulty modifier), `IncomeDeclaration` (actual-vs-declared),
  `OrgEconomicsProfile` (`graft_pct`), `OrgObligation`, `DebtInstrument`, `Contract`,
  `Business`, `CharacterEmployment`, `DistinctionPurseDrain` (#2613 — per-distinction weekly
  purse-drain config: `drain_percent`/`floor_coppers`; the "Somehow Always Broke" sidecar,
  in `currency` not `distinctions` per ADR-0010), `PurseDrainWeek` (#2613 — per-holder
  per-week baseline persisted between the `SNAPSHOT` and `DRAIN` cron bands + drain audit row)
- **Key functions (`world/currency/services.py`):** `transfer`, `accrue_income_stream`
  (weekly pool growth), `collect_org_income` (the dispatch: check → band pct → graft →
  per-stream proportional landing), `improve_org_domain` (Domain Investment check → gross
  bump + graft crackdown), `process_income_stream(stream, amount)` (landing path),
  `settle_obligations`, `run_weekly_economy` (Sunday rollover phases),
  `snapshot_purse_drains` / `run_purse_drains` (#2613 — the two-band Somehow Always Broke
  weekly drain: `SNAPSHOT` records each holder's opening balance before income, `DRAIN` empties
  the purse down to `opening − outflows` after upkeep, so only that week's income survives;
  ordered via `CronPhase`, ADR-0150),
  `withdraw_from_treasury(*, organization, persona, amount)` (#2540 — the discretionary-spend
  primitive: a `can_spend_treasury`-authorized member draws treasury→purse; the treasury→member
  outflow #930 never built. Action-driven, so inherently piloted-only; never automate it),
  `distribute_allowance(*, organization, surplus)` (#2540 — the non-discretionary allowance rail:
  a PLACEHOLDER `ALLOWANCE_SURPLUS_PCT` share of surplus auto-splits treasury→purse among *active
  piloted* members [account login within `ACTIVE_WEEK_LOGIN_DAYS`; pure NPCs excluded], the head
  cannot withhold it; the active-piloted member scan itself lives in the shared
  `_active_allowance_sheets(organization, cutoff)` helper, reused below),
  `distribute_material_allowance(*, organization, landed_by_category)` (#2540 slice 2, "the
  crafting draw" — the materials analogue of `distribute_allowance`: for each
  `(MaterialCategory, landed)` in `landed_by_category`, a PLACEHOLDER `MATERIALS_ALLOWANCE_PCT`
  share splits evenly across `_active_allowance_sheets`'s population into each member's
  `MaterialBucket` via `items.gems.buckets.credit_materials`; `OrgMaterialStock` [`select_for_update`]
  is debited by exactly the total actually credited [`per_member * member_count`, floor
  remainder stays in stock], capped at the stock's current value so a concurrent spend can
  never drive it negative — the cap recomputes `per_member` down rather than over-crediting. A
  category with nothing landed, or a missing stock row [shouldn't happen], is skipped. Returns
  `MaterialAllowanceResult(total_by_category, member_count)`),
  `collect_and_distribute(*, organization, character, success_level_override=None)` (#2540,
  ruled 2026-07-20 — THE distribution dispatch, both live call sites now wired: the active
  piloted collection (`npc_services.effects.run_collection`) and the route-graded mission
  landing (`tasking._land_route_collection`, which passes its own
  `success_level_override`) — collect → `service_debt_principal` [a mandatory PLACEHOLDER
  `DEBT_PRINCIPAL_GROSS_PCT` of GROSS toward debt principal, oldest first, diverting debts
  skipped, capped by treasury; a catastrophe funds no debt service; complements the weekly
  at-source ARREARS/interest withholding #927] → `distribute_allowance` on the post-debt
  remainder of what landed → `distribute_material_allowance` (#2540 slice 2) on
  `collection.landed_by_category` → `auto_sell_excess_materials` (#2540 slice 2, ALWAYS LAST —
  liquidates whatever `OrgMaterialStock` the allowance leg didn't already draw down) — each
  phase independently atomic; the coin remainder stays in the treasury, the materials remainder
  stays in `OrgMaterialStock`.
  `success_level_override` passes straight through to `collect_org_income` for a
  caller that already resolved the run's outcome elsewhere. Returns `DistributionResult`, which
  carries `material_allowance: MaterialAllowanceResult` alongside `allowance` and `auto_sold:
  int` (coppers minted to the treasury from the auto-sell leg, 0 when nothing sold)). Both entry
  points append one PLACEHOLDER report line ("raw materials were shared out to N members")
  only when `material_allowance.total_by_category` is non-empty.
  `auto_sell_excess_materials(*, organization)` (`world.currency.services`, #2540 slice 2) — the
  org-level analogue of `market.sell_materials`: for each `OrgMaterialStock` row over the
  PLACEHOLDER `MATERIAL_AUTO_SELL_THRESHOLD`, sells `excess = value - threshold` at the market's
  `MATERIAL_SALE_RATE_PCT` (imported from its market home, one rate constant, no duplicate) into
  the treasury; rows read/debited under `select_for_update`, same locking discipline as the
  allowance leg since both debit the same stock table. A category whose excess rounds to zero
  coppers is left alone; each category liquidates independently. Called ONLY from the end of
  `collect_and_distribute` — never the weekly cron directly (ADR-0081/ADR-0234: automatic gain
  is not automatic).
- **Checks (#930):** Tax Collection / Household Command (presence + Leadership + Stewardship) and Domain
  Investment (intellect + Scholarship + Economics), seeded by the `governance` cluster
- **Collection difficulty (#696 item 1):** `_collection_target_difficulty` derives the Tax
  Collection check's target difficulty from local order/crime — worst-stop wins: for each
  stream with an authored `area`, net pressure = area CRIME total − area ORDER total
  (`world.locations.services.area_stat_total`), and the MAX pressure across an org's streams
  shifts the base NORMAL difficulty point-for-point (clamped to TRIVIAL..HARROWING).
  PLACEHOLDER tuning — point-for-point shift and worst-stop-wins are first guesses pending
  real turf-war stat magnitudes. `collect_org_income`'s `success_level_override` lets a
  caller that already resolved the run's outcome elsewhere (a mission's terminal grade, via
  `tasking.TaskOutcomeRoute.collection_success_level`) skip the check and band on that grade
  instead (#696 item 2) — see Tasking's `resolve_task_for_mission`.
- **Books surface:** `GET /api/currency/org-books/{org}/` (`OrgBooksViewSet`) — treasury,
  graft, income streams w/ pools + `uncollected_total`, debts, obligations, contributions,
  ledger; per-line summon affordances drive the npc_services interaction dialog
  (`frontend/src/org_books/`)
- **Vault-events surface (#2540):** `GET /api/currency/org-books/{org}/vault-events/`
  (`OrgBooksViewSet.vault_events`, `OrgVaultEventSerializer`) — read-only reader for the
  item vault's `OrgVaultEvent` audit rail (kind, item display name, actor persona name,
  `created_at`; newest first, capped at 50); same membership gate as the books
  (`_require_member_org` — visible to any active member, not just withdraw-authorized
  ones, since the audit trail is how embezzlement gets discovered)
- **Purse surface:** `GET /api/currency/purse/{character_id}/` (`CharacterPurseView`) —
  self-scoped `{balance}` coppers (vitals-view gating: staff or active tenure, else 404);
  lazy-creates the purse at zero. Feeds the web Status tab (`formatCoppers`) and
  `sheet/status` telnet section (#1446)
- **Physical currency (#1909):** ledger money can leave the books as a real, holdable
  `ItemInstance` — a coin cache or grand instrument, born physical (a materialized
  `game_object` in the minter's inventory) so it can be dropped/given/stowed/**stolen**
  like any other item. `Denomination.LOOSE` is the everyday-cash face (arbitrary
  `face_value`, no mint fee) alongside the six fixed grand-coin denominations (which do
  carry `MINT_FEE_PCT`, a deliberate sink, #923).
  - **Key functions:** `mint_loose_cache(*, amount, holder_sheet, from_purse=None,
    from_treasury=None) -> ItemInstance` (fee-free, arbitrary face value);
    `mint_instrument(*, denomination, holder_sheet, ...)` (fixed denomination + fee);
    both call `world.items.services.materialize.materialize_item_game_object` to birth
    the physical object. `redeem_instrument(*, instance, to_purse=None, to_treasury=None)`
    — fee-free deposit/redemption for *any* instrument (loose or grand); consumes the
    physical object (`game_object.delete()` CASCADEs the `ItemInstance` row;
    `OwnershipEvent` rows survive via `SET_NULL`, #1025 provenance) so a redeemed coin
    never lingers as a ghost item.
  - `parse_coppers(text) -> int | None` (`world.currency.constants`) — parses
    `"1g 2s 3c"`-style free text into coppers; `None` when the text isn't money. Used by
    telnet `CmdGive` to branch into `give_coins` and by the withdraw-coins grammar.
  - **Action keys:** `withdraw_coins` (mints a loose cache), `deposit_coins` (redeems any
    instrument), `give_coins` (coppers straight to a co-located recipient's purse) —
    `actions/definitions/currency.py`. Telnet: `withdraw coins <amount>` (via the existing
    `CmdWithdraw`), `deposit <item>` (`CmdDeposit`), `give <amount>` (via `CmdGive`,
    auto-detected through `parse_coppers`).
- **Golden Hares / favor tokens (#2428):** an org-issued deed token — a gold coin bearing
  a rabbit with emerald eyes, one Hare = one deed done for `issuing_organization`.
  Deliberately NOT coppers-denominated (a distinct instrument from `CurrencyInstrumentDetails`);
  tradeable as an ordinary item via existing give/trade (no market machinery). Deed-provenance
  is story-significant, so redemption never hard-deletes: `FavorTokenDetails` (`item_instance`
  OneToOne, `issuing_organization` FK, `provenance_note`, `minted_at`, `redeemed_at`) rows and
  their `ItemInstance` both survive redemption.
  - **Key functions:** `mint_favor_token(org, recipient_character, *, provenance_note) ->
    FavorTokenDetails` (mirrors the coin-mint item-creation shape, no ledger transfer/fee);
    `redeem_favor_token(token, *, redeemer_org) -> None` — only the issuing org may redeem its
    own Hare; soft-disposes the item (stamps `ItemInstance.destroyed_at`, relocates the
    game_object out of play, logs a CONSUMED `OwnershipEvent`) rather than hard-deleting it,
    mirroring the items app's provenance-preserving soft-delete norm
    (`consume_item_charges`'s preserve branch / `forfeit_item_instance`), not
    `redeem_instrument`'s hard-delete.
  - Substrate for the tradition-sponsorship cluster (#2428/#2440/#2441/#2442): Academy
    training costs a Hare; sponsorship is a Hare spent on the Prospect's behalf at CG.
  - **Minting hook (Task 4, #2428):** `GMAwardAction` (`gm_award_progression`, see the
    GM Adjudication Toolkit entry below) gains `award_type="favor_token"` — thin over
    `mint_favor_token`, resolving `org_ref` (pk-or-name) against `societies.Organization`
    and requiring a non-empty `description` (becomes the token's `provenance_note`).
    Same JUNIOR-tier GM-fiat trust bar as the existing `xp`/`development` award types.
    Missions have an authored per-route reward surface (`MissionOptionRouteReward` /
    `DeedRewardSink`), but no sink resolves to an `Organization` today and adding one
    (`FAVOR_TOKEN` sink + an org FK on the reward template) is a schema change — out of
    scope here. Until that lands, mission-triggered Hares are GM-tool + authored-content
    driven (a GM hands one out via this action mid-scene), not an automatic completion
    payout.
- **Source:** `src/world/currency/`

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
outcome rolls. Kinds: BUILDING_CONSTRUCTION, ROOM_FEATURE_PROGRESSION, RESEARCH,
RANSOM (#1500), and PROPAGANDA (#1621 — the money→prestige sink; the only kind whose
completion fires a renown award; details/handler owned by `world.societies`, mirroring
captivity's RANSOM ownership).

- **Models:** `Project` (kind discriminator + status + completion_mode), `Contribution`
  (per-actor per-project contribution log; privacy-aware; `contribution_method` FK on
  CHECK rows), `ContributionMethod` (#1574 — admin-authorable, per-`ProjectKind`
  check-based method: `check_type` + `ap_cost` + `progress_on_success`), per-kind details
  models (`BuildingConstructionDetails`, `RoomFeatureProgressionDetails`)
- **Constants:** `ProjectKind`, `ProjectStatus`, `CompletionMode`, `ContributionKind`
  (AP/MONEY/ITEM/CHECK/**MISSION** — #2045 adds MISSION for mission→project payouts),
  `ContributionPrivacy`
- **Contribution surface (#1574):** `donate_to_project` (money → progress at 1/100c),
  `contribute_check_to_project` (spends a method's AP, rolls its check, advances on
  success), `set_contribution_story`. Telnet `CmdProject` (`+project`, `project/donate`,
  `project/check`, `project/story`); web via `DonateToProjectAction` /
  `CheckContributeAction` / `StoryContributeAction`.
- **Instant-completion kinds (#1500):** `register_instant_completion_kind` marks a kind
  (RANSOM, PROPAGANDA) that resolves the moment its threshold is funded —
  `maybe_complete_immediately` fires the kind handler post-contribution instead of
  waiting for the cron resolver. (The generic RESOLVING→COMPLETED cron driver is not
  built yet; `scan_active_projects` only marks projects RESOLVING.)
- **Propaganda campaigns (#1621):** `PropagandaCampaignTier` + `PropagandaDetails`
  (both inherit `RenownAwardConfig`; live in `world/societies/models.py`),
  `launch_propaganda_campaign` / `resolve_propaganda_project`
  (`world/societies/propaganda.py`; registered at societies app-ready). The handler
  fires `fire_renown_award` for `owner_persona` exactly once (`renown_fired` guard),
  only if the threshold was reached — under-funded deadline resolutions award nothing
  and refund nothing. `LaunchPropagandaCampaignAction`
  (key `"launch_propaganda_campaign"`); telnet `project/launch <tier>=<name>` (bare
  form lists active scales). Seeds: `propaganda` cluster (3 PLACEHOLDER tiers).
- **Stat definitions:** Project achievement stats are created lazily on first
  contribution (same pattern as combat achievement counters)
- **PROJECT_CONTRIBUTION resonance payout (#2038):** `ProjectKindResonanceAward`
  (per-`ProjectKind` opt-in: `kind` unique, `resonance_award_amount`; missing
  row/amount 0 = no payout) + `_maybe_grant_project_contribution_resonance`,
  called at the end of `add_contribution` for every `ContributionKind`. Grants
  `Project.resonance` via `grant_resonance(..., source=GainSource.PROJECT_CONTRIBUTION)`
  (see "Resonance Gain Surfaces" in [magic.md](magic.md)); exception-guarded (a
  payout failure never rolls back the contribution) and uncapped (repeat
  contributions each grant again). Seeded via `ensure_project_kind_resonance_awards`
  (`world/projects/seeds.py`, `project_resonance` cluster) — only
  `ORGANIZATION_CAPABILITY` opts in today, at +5.
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
  the `LookAction` examine-extras seam (captive banner — ADR-0213)
- **Source:** `src/world/captivity/`

### Buildings (Permits + Construction + Materials)
Plan 3 (#668). Permits authorize **(ward × kind)** building construction via the
unified NPCServiceOffer PERMIT effect handler. Buildings spawn from completed
`BUILDING_CONSTRUCTION` Projects with materials snapshotted onto the building.

- **Models:** `BuildingKind` (open catalog with 9 non-exclusive flags: residential/
  commercial/fortified/occult/maritime/agrarian/aerial/subterranean/secret),
  `BuildingSizeTier` (#670: `tier` → `space_budget` lookup, PLACEHOLDER seeded
  Hut 50 → Citadel 5000), `Building` (decorates an Area at level BUILDING;
  `target_size`, `target_grandeur`, `space_budget`, `entry_room` FK →
  RoomProfile; `fortification_level` — persistent defense investment, #1713,
  capped at `MAX_FORTIFICATION_LEVEL`), `BuildingMaterial`
  (per-building snapshot of materials used at construction), `MaterialLoreEffect`
  (per-template special properties — godswar stone → resonance_amp etc.; zero
  rows shipped; content-authored via the `MaterialLoreEffectAdmin` Django admin
  registration, #695), `BuildingPermitDetails` (persona-scoped permit
  holder, building_kind + approved_wards M2M), `BuildingConstructionDetails`
  (Project per-kind payload for BUILDING_CONSTRUCTION),
  `BuildingExtensionDetails` (#670: BUILDING_EXTENSION payload — `added_budget`,
  `applied_at` idempotency marker), `InteriorDesignDetails` (#670:
  INTERIOR_DESIGN payload — `template` FK ProjectTemplate, `building`, nullable
  `room` target, `applied_at`), `FortificationUpgradeDetails` (#1713:
  FORTIFICATION_UPGRADE payload — `building`, `target_level`, `applied_at`
  idempotency marker; monotonic max-set on completion, not additive),
  `BuildingRenovationDetails` (#1858: BUILDING_RENOVATION payload — `building`,
  `target_kind` FK BuildingKind, `applied_at` idempotency marker; re-points
  `Building.kind` to a different catalog kind on completion, set-once — does
  not mutate per-building flags, which are catalog-level per the glossary).
- **Key functions** (`world.buildings.services`):
  - `issue_permit(offer, persona) -> EffectResult` — real PERMIT effect handler
    (replaces Plan 2's stub; registered via `world.buildings.apps.ready()`)
  - `validate_permit_site(permit_details, site_room, acting_persona, target_size) -> ValidationResult`
    — raises typed `PermitValidationError` subclasses with `user_message`
  - `activate_permit(permit_details, site_room, acting_persona, target_size, target_grandeur) -> Project`
    — consumes the permit, spawns the construction project
  - `complete_building_construction(project) -> Building` — runs at project completion;
    spawns Building, snapshots materials, deletes consumed instances
  - `contribution_value_for_construction(contribution) -> int` — material/money
    value formula (materials ~110% baseline, lore-bearing materials scale by
    `lore_value`)
- **Fortification investment** (`world.buildings.fortification_services`, #1713):
  `start_fortification_upgrade(persona, building, target_level) -> Project` — opens
  a FORTIFICATION_UPGRADE Project (raises `FortificationLevelExceedsMaximumError` if
  `target_level` isn't strictly greater than the current level or exceeds
  `MAX_FORTIFICATION_LEVEL`); `complete_fortification_upgrade(project)` — kind
  handler, monotonic `max(current, target_level)` set on `Building.fortification_level`
  so completion order never regresses it. Consumed by `world.battles.services
  .create_fortification`, which snapshots the level once into a new `Fortification`'s
  `max_integrity` — see [battles.md](battles.md#sieges-1713).
- **Building renovation** (`world.buildings.renovation_services`, #1858):
  `start_building_renovation(persona, building, target_kind) -> Project` — opens
  a BUILDING_RENOVATION Project (owner-gated; raises `RoomBuildError` for a
  no-op reassignment to the building's current kind);
  `complete_building_renovation(project)` — kind handler, re-points
  `Building.kind` to the target catalog `BuildingKind` exactly once via the
  `applied_at` marker. Flags stay catalog-level per the glossary — a renovation
  swaps the catalog row, it does not mutate per-building flags. Slice #1 of
  epic #673 (future ProjectKind values).
- **Condition tiers & upkeep (#1930, ADR-0093):** `Building.condition_tier`
  (`ConditionTier` IntegerChoices ladder Decayed…**Excellent**…Immaculate) +
  `condition_since` / `upkeep_arrears` (capped) / `ultra_upkeep` /
  `mothballed_at` / building-scoped `consecutive_missed_upkeep` +
  `consecutive_paid_upkeep`. Weekly cron `buildings.weekly_upkeep`
  (`upkeep_services.apply_weekly_upkeep_all_buildings`, walks ALL buildings):
  paid weeks hold Excellent (one-tier regain per `REGAIN_WEEKS_PER_TIER` below
  it); misses accrue arrears capped at `ARREARS_CAP_WEEKS ×` weekly cost, then
  slide one tier per `SLIP_WEEKS_PER_TIER` past `GRACE_MISSES` (floor DECAYED —
  **polish/feature rows are never mutated by nonpayment**; the #676 decay +
  restoration machinery is deleted). Above-Excellent tiers dwell-decay
  (`ABOVE_NORMAL_DWELL_DAYS`); Immaculate holds only via the ultra-upkeep
  premium. `set_condition_tier` is the single tier write path (stamps + fires
  the prestige recompute). Prestige: `recompute_persona_prestige_from_dwellings`
  step-multiplies each building-derived component by
  `CONDITION_PRESTIGE_MULTIPLIER[tier]` (5%–200%; home-room polish follows the
  containing building's tier). Recovery (`condition_services`, purse sinks):
  `settle_upkeep_arrears`, `refurbish_building` (to Excellent;
  arrears-settled gate; "refurbish" ≠ the kind-swap "renovation"),
  `set_ultra_upkeep`; `ConditionServiceError.user_message` on refusals.
  **Grand Preparation is a project** (Apostate 2026-07-06): the
  `BUILDING_PREPARATION` kind + `BuildingPreparationDetails`
  (`start_building_preparation` / `complete_building_preparation`, registered
  kind handler) — threshold = `PREPARE_COST_PERCENT_OF_PRESTIGE` (25%/50%) ×
  `building_prestige_base(building)` (BuildingPolish + style bonus; also the
  recompute input), floored per `PREPARE_COST_FLOOR_COPPERS` × target_size;
  created ACTIVE (ransom precedent) and funded via `project/donate`
  (1 progress/100c) or sped by the AP "Direct the Household"
  `ContributionMethod` (Household Command check; seeded by
  `ensure_preparation_contribution_method`, cluster `building_condition`);
  an underfunded time-limit lapse fizzles (tier applied only when the
  threshold was met).
  Mothballing (`mothball_services`, weekly cron `buildings.mothball_sweep`):
  owner decay-tier ≥ LONG_INACTIVE hides the building's rooms
  (`RoomProfile.is_public` snapshotted per-room in `MothballedRoomState`) and
  freezes accrual; return restores with zeroed misses, no back-billing. The
  renown payload's `owned_dwellings` carries only the public
  `condition_label`; arrears/misses/ultra state are owner-only via the action
  family.
- **Space budget (#670, ADR-0075):** `Building.space_budget` snapshots
  `BuildingSizeTier[target_size]` at construction; rooms spend their
  `RoomSizeTier` units (`evennia_extensions`) from it. Replaces the old
  `max_rooms = rooms_per_size_tier × target_size` flat count — rooms trade
  count for grandeur freely. Rooms within budget are instant/free;
  `BUILDING_EXTENSION` grows the budget via the contribution pipe.
- **Room Builder** (`world.buildings.room_services`, #670):
  - `dig_room(persona, from_room, direction, name, description="", like=None, size=None)`
    — stub creation (direction + name only), exit pair with standard aliases,
    cosmetic grid coords (never block creation), `like=` exemplar copy
  - `resize_room(persona, room, size)` / `remove_room(persona, room)` (guards:
    entry room, installed feature, active design project, graph connectivity;
    evicts tenants + contents to `entry_room`)
  - `link_rooms` / `unlink_rooms` (connectivity-guarded) / `rename_exit`
  - `place_room(persona, room, grid_x, grid_y, floor=None)` (#670 PR2) —
    cosmetic map re-placement (web canvas drag); only guard is cell collision
  - `space_used(building)` / `space_remaining(building)` / `building_for_room(room)`
    / `building_exits(building)`
  - `start_building_extension(persona, building, added_budget)` +
    `complete_building_extension` handler; `commission_decoration(persona,
    building, template, room=None)` + `complete_interior_design` handler —
    finally drives the polish machinery (`apply_project_completion` /
    `apply_room_polish_delta`)
  - `render_building_map(building, floor=0)` (`world.buildings.map_render`) —
    telnet ASCII floor map (budget header, connectors, unplaced list)
- **Actions:** `ActivatePermitAction` (in `src/actions/definitions/items.py`);
  the #670 builder family in `src/actions/definitions/locations.py` —
  `dig_room`, `resize_room`, `remove_room`, `link_rooms`, `unlink_rooms`,
  `rename_exit`, `place_room`, `assign_room_tenant`, `end_room_tenancy`,
  `set_primary_home`, `commission_decoration`, `start_building_extension`,
  plus the #1930 condition family `settle_building_arrears`,
  `refurbish_building`, `prepare_building`, `toggle_ultra_upkeep` (bare
  invocation prints the owner-only condition/arrears status; `confirm` pays) —
  owner-gated (`IsRoomOwnerPrerequisite`) except home
  (`IsRoomTenantPrerequisite`)/tenancy-end. Structural actions accept an
  explicit `room_id` anchor (+ `to_room_id`/`exit_id`) so the web canvas can
  operate building-wide; the prerequisite gates on the resolved room (#670 PR2).
  Telnet: the `room` family (`CmdRoom`, aliases `build`/`manageroom`).
- **REST API (#670 PR2, `world/buildings/{serializers,views,urls}.py`, mounted
  at `/api/buildings/`):** `manager/<building_id>/` (owner-gated manager
  payload — rooms w/ sizes+grid+tenancies, exits, budget, floors; pinned at 12
  queries), `manager/for-room/<room_id>/` (RoomPanel resolver: `building_id`,
  `is_owner`, `is_tenant`, `is_primary_home_here` — ids/booleans only),
  `room-size-tiers/` + `decoration-templates/` ReadOnly catalogs. Viewer =
  `?character_id=` validated via `RosterEntry.objects.for_account` →
  `active_persona_for_sheet`. Writes go through action dispatch, never REST.
- **Web builder** (`frontend/src/buildings/`, #670 PR2): `BuildingBuilderDialog`
  (mounted from RoomPanel "Manage Building"; full-screen, keeps the game
  websocket alive), React Flow `BuilderCanvas` (grid rooms, ghost-cell digs,
  drag → `place_room`, exit-pair edges), `RoomDetailPanel` (identity/size/
  exits/tenants/remove), Dig/Decoration/Extension dialogs, `BudgetMeter`;
  tenants get "Set as Home" on RoomPanel (`set_primary_home`).
- **Architectural style tiers (#1469):** `ArchitecturalStyle.is_default` /
  `prestige_bonus` / `cost_multiplier` (PLACEHOLDER magnitudes; cost charging
  awaits the economy pass). Throwback (non-default) styles gate on codex
  knowledge of `codex_subject` — `can_build_style(persona, style)`
  (`world/buildings/services.py`); unlocked via the clue→RESEARCH pipeline
  (ADR-0079). `SetBuildingStyleAction` (key `set_building_style`, owner-gated,
  `room_id` anchor) is the player verb; telnet `room/style <name>`. Owned home
  building's style adds `prestige_bonus` in
  `recompute_persona_prestige_from_dwellings`. Seeds:
  `ensure_architectural_styles()` (2 default + 2 discoverable PLACEHOLDER rows
  w/ codex subjects/entries/clues).
- **Comfort fixtures + owner build-HUD (#1514 close-out):**
  `PlaceFixtureAction`/`RemoveFixtureAction` (keys `place_room_fixture` /
  `remove_room_fixture`, owner-gated, `room_id` anchor; telnet `room/fixture` /
  `room/removefixture`) — the first production callers of
  `place_decoration`/`remove_decoration`. `ensure_decoration_kinds()` seeds 3
  PLACEHOLDER kinds. HUD read: `GET
  /api/buildings/manager/room/<room_id>/comfort/` (owner-gated) — enclosure,
  comfort level/points/amenity, per-axis pressure/mitigation/net
  (`world.locations.services.room_exposure_breakdown`), placed fixtures, and
  the kinds catalog; rendered by `ComfortSection` in the web builder's room
  panel.
- **Predicate leaf:** `has_item` (persona-scoped) registered with the
  `building_permit` dispatch entry — checks if a persona holds an unconsumed
  building permit.
- **Seeding:** `ensure_plan_3_seeds()` in `world.buildings.seeds` (get-or-create
  the BuildingPermit ItemTemplate + House BuildingKind + wires House onto
  Builders Guild Clerk PERMIT offers). NOT a committed fixture (per #683).
- **Out of scope, filed as followups:** BuildingKind catalog expansion (#694),
  MaterialLoreEffect catalog content — authoring surface shipped in #695;
  ongoing staff content authoring, not a code task — Building → Neighborhood →
  Domain progression (#696), BUILDING_RENOVATION / BUILDING_UPGRADE project kinds
  (#673; EXTENSION + INTERIOR_DESIGN shipped with #670).
- **Cross-app dependencies:** `world.areas` (Area + AreaClosure + ward fields),
  `world.items` (ItemTemplate + ItemInstance + OwnershipEvent + `lore_value`),
  `world.projects` (Project + Contribution), `world.npc_services` (NPCRole +
  NPCServiceOffer + PermitOfferDetails), `world.scenes` (Persona), `world.predicates`
  (`has_item` leaf dispatch); `world.battles` reads `Building.fortification_level`
  (`Fortification.building` FK, #1713) but this app never imports `world.battles` —
  the dependency runs one-way, buildings→battles direction avoided (FK direction
  specific→general, ADR-0010).
- **Source:** `src/world/buildings/`
- **Property grants (generic "hand a persona an already-existing Building"
  primitive):** `PropertyGrantProfile` (catalog: `building_kind`, nullable
  `ward_area` — falls back to a shared placeholder Ward Area, lazily created;
  `initial_condition_tier`; nullable `activation_target_tier` — unset means
  the grant is already active, set means it starts upkeep-exempt and needs a
  `BUILDING_ACTIVATION` project; `activation_cost_floor_coppers`),
  `BuildingActivationDetails` (per-project payload: `building`, snapshotted
  `target_tier`, `applied_at` idempotency marker). `Building` gains
  `granted_via_profile` / `property_granted_at` / `property_activated_at`.
  Not content-specific — `character_creation.Beginnings.property_grant_profile`
  is the only current caller (via `finalize_character`), but
  `grant_property_house` is callable from anywhere (a future GM/story grant
  needs no new plumbing). **Key functions**
  (`world.buildings.property_grant_services`): `grant_property_house(persona,
  profile) -> Building` (creates the Area/Building/entry-room shape
  `complete_building_construction` produces, minus the permit/project),
  `start_building_activation(*, persona, building) -> Project` (owner-gated,
  `BUILDING_ACTIVATION` kind, `SINGLE_THRESHOLD`, cost = `profile.
  activation_cost_floor_coppers × building.target_size`), `complete_building_
  activation(project, outcome_tier=None)` (kind handler — sets
  `condition_tier` to the snapshotted target, stamps `property_activated_at`,
  idempotent via `applied_at`). Weekly upkeep (`apply_weekly_upkeep_for_
  building`) exempts a granted-not-activated building the same way it exempts
  a mothballed one; `refurbish_building` refuses on one (typed
  `ConditionServiceError`) — the first-time bring-to-life arc is deliberately
  the `BUILDING_ACTIVATION` project, not the instant purse-priced refurbish
  path. Action: `StartBuildingActivationAction` (`"start_building_activation"`,
  owner-gated via `IsRoomOwnerPrerequisite`, same family as the #1930
  condition actions). Dev seed: `world.buildings.seeds.ensure_placeholder_
  property_grant_profile` (cluster `"property_grants"`) — a generic
  placeholder profile/kind so the feature is exercisable before real content
  wires a `Beginnings` row at it.
- **Building purchase, priced decoration & the crafted-furniture seam (#2991):** the
  real coin front door onto `LocationOwnership`, alongside the CG-only
  `grant_property_house` freebie above. `BuildingListing` (O2O → `Building`,
  `price_coppers`, nullable `organization` treasury FK — falls back to a shared
  placeholder ward-office org, `is_available` / `sold_to_persona` / `sold_at`) mirrors
  `WareListing`'s shape at building scope; MVP inventory is staff/content-curated
  (player-to-player resale is a deferred follow-up once this loop is proven — reuse
  `WareListing`/`purchase_ware` when it lands). **Key function**
  (`world.buildings.services`): `purchase_building(*, persona, listing) -> BuildingListing`
  — validates `is_available`, debits the buyer's purse into the listing's (or the
  placeholder) treasury via `transfer()`, calls the existing `world.locations.services.
  transfer_ownership(area=building.area, to_persona=persona)` (ends any prior active
  `LocationOwnership`, cascades most-specific-wins to every room — unchanged mechanism),
  **also** stamps `Building.owner_persona` (the polish/prestige + upkeep-purse anchor —
  `upkeep_services`/`polish_services` read this field, not `LocationOwnership`, so both
  must move together), flips the listing sold. Raises typed `BuildingPurchaseError`.
  Action: `PurchaseBuildingAction` (key `purchase_building`, `target_type=SELF`, kwarg
  `listing_id`, gated only by `HasCharacterSheetPrerequisite` — funds/availability are
  checked service-side). Dev seed: `ensure_placeholder_building_listing` (cluster
  `"building_listings"`) — a schema-exercising placeholder Building + listing.
  **Priced decoration placement:** `DecorationKind.cost_coppers` (PLACEHOLDER, default 0
  — the pre-#2991 seeded catalog stays free); `place_decoration` gains `buyer_persona`/
  `item_instance` kwargs and charges `cost_coppers` via `transfer()` before creating the
  `RoomDecoration` row (no partial placement on insufficient funds); raises
  `DecorationPlacementError`. `PlaceFixtureAction` passes the caller's persona and an
  optional `item_instance_id` kwarg through; its success message carries the charged
  amount. **Crafted-furniture seam (Ratified amendment, riding ADR-0192 — not a parallel
  furniture path, no new recipe machinery, recipe content stays lore-repo authored):**
  `DecorationKind.crafted_item_template` (nullable FK → `items.ItemTemplate`) marks a
  kind as crafted-economy furniture; `RoomDecoration.source_item_instance` (nullable O2O
  → `items.ItemInstance`) anchors the specific placed piece. `crafted_decoration_amenity
  (kind, quality_tier) -> int` is the ADR-0192 mapping — `round(kind.amenity *
  quality_tier.stat_multiplier)`, falling back to the flat `amenity` when
  `quality_tier is None` — applied automatically by `_materialize_decoration` whenever a
  placement carries a `source_item_instance`. `place_decoration` validates the held
  instance matches the kind's template and isn't already placed elsewhere. **Room-state
  legibility:** `flows.service_functions.serializers.room_state` gains additive
  `decorations: list[str]` (ordered `RoomDecoration.kind.name` by `placed_at`) and
  `comfort_level: int` (bare `comfort_level(room)`, no per-character offset) fields —
  makes decor/comfort visible where scenes already read the room, without touching the
  room's authored `desc` or `comfort_summary`. **Deferred:** player-to-player building
  resale, comfort-flex/decor-driven prestige (#1522's natural next consumer — the
  room-state field above is the read hook, not the prestige math), rent/tenancy pricing.

### Ships (#1832)
Persistent upgrades + repair + ship-as-sanctum + covenant-scale combat bridge, the
follow-up to #1714's battle-time-only `BattleVehicle`. A ship is a per-kind
extension of `buildings.Building` (composition, mirroring `Covenant`↔`Organization`);
the hull stat IS `Building.fortification_level`, reused not duplicated. Full detail:
[ships.md](ships.md).

- **Models:** `ShipType` (open catalog: base hull/handling/armament/crew/cargo),
  `ShipDetails` (OneToOne PK → `Building`; `ship_type`, `handling_level`,
  `armament_level`, `crew_capacity`, `cargo_capacity`, `needs_repair`;
  `effective_handling()`/`effective_armament()`/`effective_hull()`),
  `ShipDeployment` (links a `ShipDetails` to its in-battle `BattleVehicle` for one
  `Battle` — FK direction ships→battles per ADR-0010), `ShipConstructionDetails` /
  `ShipUpgradeDetails` / `ShipRepairDetails` (per-Project payload rows, `applied_at`
  idempotency marker, mirror `FortificationUpgradeDetails`'s shape).
- **Key functions** (`world.ships.services`): `start_ship_construction` /
  `complete_ship_construction` (spawns Area+Building+deck room+`ShipDetails`),
  `start_ship_upgrade` / `complete_ship_upgrade` (`SHIP_UPGRADE` Project,
  monotonic max-set), `start_ship_hull_upgrade` (thin wrapper over
  `buildings.fortification_services.start_fortification_upgrade` — no separate
  hull Project kind), `start_ship_repair` / `complete_ship_repair` (clears
  `needs_repair`). All four completion handlers registered via
  `world.projects.services.register_kind_handler` at `world.ships.apps.ready()`.
- **Ship-as-sanctum** (`world.ships.sanctum_bonus`): `ship_sanctum_bonus(ship) ->
  ShipStatBonus` / `ship_sanctum_capability_grants(ship) -> list[ShipCapabilityGrant]`
  read the ship's installed `SanctumDetails`' woven SANCTUM threads (at most one sanctum
  room per ship for MVP) — snapshotted at materialize time, not read live. Both halves
  are **authored content**: tier-0 `TargetKind.SANCTUM` `ThreadPullEffect` rows, the
  stat bonus via `VITAL_BONUS` + a `SHIP_HULL`/`SHIP_HANDLING`/`SHIP_ARMAMENT`
  `vital_target`, the capability via `CAPABILITY_GRANT` curved by
  `apply_capability_curve`. Unauthored resonance = inert, never an error (ADR-0188,
  #2736). Zero rows authored in the lore repo today.
- **Combat bridge** (`world.ships.battle_bridge`):
  `materialize_ship_as_battle_vehicle(ship, battle, side, place_name=None) ->
  BattleVehicle` — one-way snapshot of persistent stats (+ sanctum bonus) into a
  `create_battle_vehicle`-built `BattleVehicle` (hull integrity, `speed`
  capability, `strength`, the sanctum's authored capability rows); links a
  `ShipDeployment`. Mints no `CapabilityType` — it writes only what the catalog
  resolved (ADR-0188). From there REPOSITION/BREACH/sinking/ejection run through
  unmodified `world.battles` machinery — see [battles.md](battles.md#battlevehicle).
- **Repair writeback** (`world.ships.battle_wiring`): `apply_ship_battle_outcome`
  registered as a **battle-conclusion hook**
  (`world.battles.conclusion_hooks.register_battle_conclusion_hook`, new pattern
  for `battles`) — on `conclude_battle`, flags any deployed ship whose hull ended
  `breached` as `needs_repair`, gating further investment until a `SHIP_REPAIR`
  Project clears it. `battles` imports nothing from `ships` (ADR-0010).
- **Telnet:** `CmdShip` (`ship`, `src/commands/ships.py`) — `ship [status]`,
  `ship commission ship_type=<name> [covenant=<name>] name=<ship name>`,
  `ship upgrade stat=handling|armament|hull level=<n>`, `ship repair`.
- **Actions** (`actions/definitions/ships.py`, REGISTRY, `category="ships"`):
  `CommissionShipAction` (`commission_ship`), `UpgradeShipAction` (`upgrade_ship`)
  / `RepairShipAction` (`repair_ship`, both gated `IsShipOwnerPrerequisite`),
  `ShipStatusAction` (`ship_status`, read-only).
- **REST API:** `GET /api/ship-types/` (catalog), `GET /api/ships/`
  (`ShipViewSet` — read-only, scoped to the requester's owned ships, direct or
  covenant-held).
- **Cross-app dependencies:** `world.buildings`, `world.areas`, `world.projects`,
  `world.battles` (ships depends on battles' reusable primitives, never the
  reverse — ADR-0010), `world.magic` (read-only sanctum/thread reads),
  `world.locations`, `world.scenes`, `world.covenants`.
- **Source:** `src/world/ships/`

### Companions (#672)
Generic bound-creature substrate plus one concrete consumer: a Beastlord-style
Gift letting a PC bind a wild beast archetype as a persistent, room-present
companion. Full detail: [companions.md](companions.md).

- **Models:** `CompanionArchetype` (staff-authored catalog: `domain`, `name`,
  `bind_difficulty`, `capacity_cost` — binding is archetype-selection, no
  discrete in-room "wild creature" object), `Companion` (the bound instance:
  `owner` → `CharacterSheet`, `archetype`, `granting_gift` → `magic.Gift`,
  `name`, `objectdb` → live `CompanionObject`, `bonded_at`/`released_at`;
  never hard-deleted).
- **Companion Capacity** (`world.companions.services`): `companion_capacity` /
  `used_companion_capacity` compute a PC's capacity from the granting Gift's
  `Thread.level` via the existing `ThreadPullEffect` mechanism
  (`TargetKind.GIFT`, `EffectKind.FLAT_BONUS`, tier 0) — no new magic enum
  values (ADR-0088).
  `bind_companion` / `release_companion` create/tear down the `Companion` row
  + its live `CompanionObject` (release soft-deletes: `released_at` set,
  `objectdb` cleared, never a hard delete).
- **Typeclass:** `typeclasses.companions.CompanionObject` extends `Character`
  (ADR-0088), not `Object` — a valid future combat participant without a
  typeclass migration. `Character.companions`
  (`world.companions.handlers.CharacterCompanionHandler`) exposes a PC's
  active companions; `Character.at_post_move` moves them along with their
  owner between rooms.
- **Actions** (`actions/definitions/companions.py`, REGISTRY,
  `category="companions"`): `BindCompanionAction` (`bind_companion`) — gated
  by `HasCompanionCapacityPrerequisite`, executes via `perform_check` against
  `CompanionArchetype.bind_difficulty`. `CompanionEmoteAction`
  (`companion_emote`, #3294) — pose *as* a bonded, present companion, gated
  by `CompanionPresentPrerequisite` (owned + active + co-located).
- **Companion emote (#3294):** `world.scenes.models.Interaction
  .attributed_companion` — nullable FK → `Companion`, purely cosmetic feed
  attribution (`Interaction.persona` stays the owner for block/mute/consent).
  Telnet `companion emote <name|id> <text>`; web `POST
  /api/companions/companions/{id}/emote/` + a composer toggle gated on
  `CompanionSerializer.is_present`. Full detail: [companions.md](companions.md#companion-emote-3294),
  [scenes.md](scenes.md#companion-pose-attribution-3294).
- **REST API:** `world.companions.views.{CompanionViewSet,
  CompanionArchetypeViewSet}` — read endpoints are read-only; write endpoints
  (`bind`/`release`/`fight`/`deploy`/`order`/`emote`) converge on
  `action.run()` via `PuppetActorMixin`, mounted at `/api/companions/`.
- **Cross-app dependencies:** `world.character_sheets`, `world.magic`
  (Gift/Thread/ThreadPullEffect), `world.checks` (`perform_check`).
- **Source:** `src/world/companions/`

### Assets (#1872)

Promotes a class-1 `Functionary` into a permanently-owned, named NPC
(informant/contact/personal-favor/guard/fan/minor-ally) once rapport crosses a
threshold and a capability trait gate is met. Modeled as a plain
`NPCServiceOffer` on the existing offer/effect-dispatch framework — see
ADR-0091.

- **Models:** `NPCAsset` (`promoter_persona`, `asset_persona` — both FK
  `scenes.Persona`; `role_context`; `source_functionary` FK `Functionary`
  (nullable — NULL for CG-granted assets); `acquisition_source` enum
  (`PROMOTION` runtime, `DISTINCTION_GRANT` CG, `COERCION` blackmail — #1680, both source FKs
  null); `source_distinction_grant` FK
  `DistinctionAssetGrant` (nullable — idempotency key for CG grants);
  `status`; `weekly_income` (coppers per cycle, 0 = none — #2294);
  `uncollected_pool` (accrued income awaiting active collection — #2294);
  `created_at`). No `standing` field — ongoing affection reads
  through the existing `NPCStanding` row for the same persona pair.
- **`DistinctionAssetGrant`** sidecar (`world.assets.models`): staff-authored
  mapping of a `Distinction` → `NPCRole` + `role_context` + `starting_affection`
  + `asset_display_name`. Reconciled at CG finalization via
  `reconcile_distinction_asset_grants` (#1906), mirroring the
  `DistinctionResonanceGrant` pattern. Lives in `world.assets` per ADR-0010.
- **`OfferKind`** additions: `INFORMANT`, `CONTACT`, `PERSONAL_FAVOR`
  (#1872); `GUARD`, `FAN`, `MINOR_ALLY` (#1907)
  (`world.npc_services.constants`).
- **Effect handlers** (`world.assets.effects`): resolve the Functionary from
  the PC's current location + the offer's role, roll `offer.check_type`
  directly (final offers don't auto-roll), and on success spawn a
  Character+CharacterSheet+PRIMARY Persona via
  `create_character_with_sheet`, place it in the Functionary's room, create
  the `NPCAsset` row, and deactivate the source Functionary. Registered via
  `world.assets.apps.ready()`.
- **Seed content** (`world.assets.content`): reuses the existing
  Stealth/Leadership/Persuasion/Scholarship check content
  (`world.seeds.stealth_checks`/`governance_checks`/`social_checks`) rather
  than inventing new Trait rows — framework-proving only. The #1907 variants
  gate on Persuasion (GUARD, FAN) and Scholarship (MINOR_ALLY), rolling
  Intimidation/Gossip/Domain Investment checks respectively.
- **Intel tasking** (#1905, #2293): `ASSET_TASK_INTEL` `OfferKind` +
  `run_asset_intel_task` effect handler. The PC directs an owned asset to
  gather intel — a `perform_check` gates success (failure = "nothing useful
  to report"), and on success a `Clue` is drawn from a weighted `CluePool`
  (#2293: replaced the single fixed `clue` FK with a `clue_pool` FK on
  `AssetTaskIntelDetails`). The draw excludes clues the promoter's
  `RosterEntry` already holds (via `CharacterClue`), and when the pool is
  exhausted (all clues held) the offer becomes ineligible — hidden from
  `available_offers` via `_intel_pool_has_unheld_clues` in
  `world.npc_services.services`. Per-(offer, persona) `OfferCooldown` still
  gates recurrence. The asset itself can be lost (`AssetStatus.COMPROMISED`/
  `LOST`/`DISMISSED`), removing the intel source entirely. This embodies
  ADR-0081: no dependable, entirely passive generation — the pool is finite,
  the check can fail, the cooldown gates recurrence, and the asset can be
  lost. Staff must add new clues to replenish an exhausted pool.
  - **`CluePool`** (`world.assets.models`): named, reusable collection of
    clues with weighted `CluePoolEntry` rows (default weight 1, min 1).
    Mirrors `ConsequencePool`'s shape but purpose-built for clues — no
    inheritance/exclusion machinery.
  - **`CluePoolEntry`**: links a `Clue` to a `CluePool` with a draw weight.
    Unique per (pool, clue). Drawn via the shared `select_weighted` utility
    (`world.checks.outcome_utils`).
- **Income collection** (#2294): `ASSET_TASK_COLLECT` `OfferKind` +
  `run_asset_collect_task` effect handler. An asset with `weekly_income > 0`
  accrues coppers into its `uncollected_pool` each weekly economy cycle
  (no cap — ADR-0081). The PC actively collects via an offer dispatch; a
  `Tax Collection` check (reusing `COLLECTION_BAND_PCTS`) decides how much
  arrives — catastrophe loses the entire pool. Money lands in the PC's
  `CharacterPurse` via `transfer()` with a `CurrencyTransfer` audit row.
  Offer is hidden when no active asset has `uncollected_pool > 0`
  (`_asset_has_collectable_income` in `world.npc_services.services`).
- **REST API:** `world.assets.views.NPCAssetViewSet` — read-only, mounted
  at `/api/assets/`, scoped by default to the requesting user's own promoted
  assets. **Widened for a non-staff GM (#3561):** own assets plus assets
  promoted by a persona whose character sheet participates in a story that GM
  leads (staff see every asset) - backs the stakes editor's ASSET subject
  picker; `NPCAssetFilter`'s `name` filter (`icontains` on the promoted
  persona's name) is the search field. Never every player's assets.
- **Source:** `src/world/assets/`

Deferred follow-ups: distinction-granted starting assets (`needs-design`),
voluntary asset sharing.

### Room Features (Plan 4 framework — Subsystem E)
Plan 4 (#669, shipped via #703). Generic per-room enhancement framework — a
`RoomFeatureInstance` decorates a `RoomProfile` and dispatches per-kind logic
via a strategy enum. Shipped kinds: **SANCTUM** (see Sanctum below),
**COMMAND_CENTER** (#930), **LAB** (#1234), and the civic-hub readers
**NOTICE_BOARD** / **TOWN_CRIER** (#1450 — `active_hub_feature(room_profile)`
resolves a room's hub; crier install places a "Town Crier" `Functionary` via
`handle_town_crier_progression`), and **SOCIAL_HUB** (#1694 — the
owner-upgradeable amplifier on top of `RoomProfile.is_social_hub`; see Social
Hub below). Future kinds (Library, Training Room, etc. — #675) plug in by
registering a service strategy + per-kind details model.

- **Models** (`world.room_features.models`):
  - `RoomFeatureKind` — open catalog row. Carries `service_strategy`
    (TextChoices: `SANCTUM`, `LIBRARY`, `TRAINING_ROOM`, `LAB`,
    `COMMAND_CENTER`, `GRANARY`, `SIEGE_DECK`, `CAPTAINS_QUARTERS`,
    `NOTICE_BOARD`, `TOWN_CRIER`, `SOCIAL_HUB`), `max_level` (cap on
    `RoomFeatureInstance.level`), display copy, install-cost knobs.
  - `RoomFeatureKindInstallRitual` — M2M-shape: which Rituals can install
    this kind. Lets one kind admit multiple install rites
    (Sanctification of own home vs. Covenant Sanctification).
  - `RoomFeatureKindOwnerType` — M2M-shape: which `RoomFeatureOwnerType` values
    (PERSONA / ORG_NOBLE / ORG_TRADE / ORG_CRIMINAL / ORG_COVENANT / ORG_DEVOTIONAL)
    may own this kind. Consulted by Covenant Sanctification's leader gate
    (`world.magic.services.sanctum_install._covenant_ownership_allowed_for_sanctum`,
    #708); no other install path (e.g. the generic `StartRoomFeatureProjectAction`
    Project flow) checks it yet.
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
  `handler(project, target_level, outcome_tier) -> None` strategy
  function (`world/room_features/services.py`). SANCTUM strategy lives at
  `world.magic.services.sanctum.handle_progression`; future kinds
  register their own.
- **Tests:** `src/world/room_features/tests/`. SANCTUM install and
  upgrade are exercised end-to-end via the SanctumDetails layer below.
- **Source:** `src/world/room_features/`
- **Traps** (`world.room_features.models.Trap`, #1051/#520 Phase 6, position-scoped #1317):
  a room-anchored (or, optionally, `Position`-anchored) hazard resolved through the shared
  check/consequence-pool path — see `trap_services.py`'s `check_room_traps_on_entry` /
  `check_traps_at_position`. Not a `RoomFeatureInstance` kind; a plain FK to `RoomProfile`
  since a room may hold several.
  - **Placement is situation-driven** (ADR-0199): the authored blueprint is
    `mechanics.SituationTrapLink`, and `instantiate_situation` mints an armed `Trap` per
    link. There is no standalone trap catalog row and no `place_trap` verb; a GM places
    traps with `set_situation` (telnet `setsituation <name|id>`).
  - **GM management** (#3002, `actions/definitions/traps.py`): `list_room_traps`,
    `arm_trap` and `gm_disarm_trap`, telnet `gm trap list|arm <id>|disarm <id>`. Each is
    gated on `MinimumGMLevelPrerequisite(JUNIOR)`, and each resolves the trap strictly
    within the actor's own room - but WHICH traps in that room an actor may act on is a
    per-row rule (`_room_traps`): staff and the active scene's GM may act on every trap
    there; anyone else (e.g. a JUNIOR GM staging a room ahead of a scene) may only act on
    traps they placed themselves (`created_by_sheet` matches their own sheet).
    `list_room_traps` returns a filtered list rather than refusing outright. These actions
    also reach technique-conjured zone hazards (see "Lifetime" below), not just
    situation-placed traps - `arm_trap` refuses to re-arm one whose duration is already
    spent (`duration_rounds == 0`). `arm_trap` deliberately leaves `detected_by` alone, so
    a re-armed trap fires for newcomers and stays inert for anyone who already resolved
    it. `gm_disarm_trap` rolls nothing, unlike the player's `disarm_trap`, which rolls
    `disarm_check_type` and fires the trap on a failed roll.
  - **Lifetime:** a GM-placed trap carries `created_by_sheet` (stamped by
    `instantiate_situation`'s `placed_by_sheet` kwarg) and is disarmed at scene end by
    `teardown_conjured_hazards`, wired into `finish_scene_full` beside the obstacle and
    rampart teardowns. An admin-authored trap has a null `created_by_sheet` and stays
    armed permanently. That teardown saves per instance rather than bulk-updating,
    because a bulk `.update()` sends no `post_save` and leaves SharedMemoryModel's
    identity map serving a stale `is_armed`.
  - **Player half** (#3011): detect in `search`, see what you detected, disarm it.
    `search_room_traps` (`trap_services.py`) is a sibling of `world.clues.services
    .search_room` — traps carry their own per-trap `detect_check_type`/`detect_difficulty`
    (clues share one Search `CheckType`), so it does not slot into the clue roll for free;
    `SearchAction` (`actions/definitions/investigation.py`) calls both and folds detected
    traps into the same result message. `Trap.is_hidden` gets its first readers here:
    `is_hidden=False` skips the roll entirely on both detection paths (entry via
    `resolve_trap_on_character`, and `search_room_traps`) — an authored obvious hazard is
    just visible, no chance to fail spotting it. A hidden trap still rolls on entry
    (`check_room_traps_on_entry`/`check_traps_at_position`), which now also messages the
    detector directly (spotted vs triggered) since entry carries no `ActionResult` of its
    own. Read surface: `RoomTrapViewSet` (`views_traps.py`, `GET
    /api/room-features/traps/?character_id=`) — personal like `ComfortViewSet`/
    `PortalDestinationsViewSet` (owned-character tenure gate doubles as "present in the
    room"); lists armed traps that are `is_hidden=False` OR already in the viewer's own
    `detected_by` (never another character's detection, never an unarmed trap); serializer
    exposes only `id`/`name`/`is_armed` (no consequence pool, no difficulties). Frontend:
    `TrapsBlock` (`frontend/src/game/components/room-panel/TrapsBlock.tsx`) in `RoomPanel`,
    reading `useRoomTrapsQuery` (`frontend/src/room_features/`) and dispatching
    `disarm_trap` via the standard registry-action seam; a failed disarm's consequence
    message surfaces through the same toast as a success. Telnet: `disarm <trap name>`
    (`commands/traps.py`, `CmdDisarm`) resolves by name among the traps visible to the
    caller (same leak rule as the ViewSet) and dispatches `DisarmTrapAction` directly.
- **`PreparedGround`** (`world.room_features.models`, #2646): a room a character has
  prepared as their battleground ahead of time — "the fight was won yesterday." Plain FK
  to `RoomProfile` (a room may hold several characters' prepared grounds) but `prepared_by`
  is a OneToOne to `character_sheets.CharacterSheet` — one active prepared ground per
  character; re-preparing elsewhere MOVES the row rather than stacking a second one.
  Recorded/refreshed by `world.covenants.perks.services.record_ground_preparation_from_cast`
  — a rider on an out-of-combat standalone cast of a PERCEPTION-tagged (`magic.
  TechniqueFunction.PERCEPTION`) technique by a character holding an active engaged
  `CharacterCovenantRole` whose `covenant_role.prepares_ground` flag is set (data-authored;
  not every role prepares ground), called from `world.scenes.cast_services.
  _resolve_and_pose_cast` after the cast resolves — not a new player verb, an existing one's
  side effect. Consumed by `world.combat.chosen_ground.compute_on_chosen_ground`, which
  stamps `CombatEncounter.on_chosen_ground` (Combat section, "Situational-perk seams") at
  encounter-CREATE time. Not a `RoomFeatureInstance` kind.
- **Installable exit/room defenses — bars/ward/alarm** (`world.room_features.models`,
  #2177): three independent details models, siblings of `RoomFeatureInstance` (like
  `Trap` above) — **NOT** `RoomFeatureKind` instances. A room can hold a
  `RoomFeatureInstance` (e.g. LAB or SANCTUM) *and* a `RoomWardDetails` *and* a
  `RoomAlarmDetails` simultaneously; an `ExitBarsDetails` hangs off a specific exit, not
  a room, so one room's several exits can each carry their own bars independently.
  - `ExitBarsDetails` — OneToOne to `evennia_extensions.ExitProfile`. `level` scales
    durability; gates `flows.object_states.exit_state.ExitState.can_traverse`
    **alongside** the pre-existing lock check (both must pass) rather than replacing it.
    Bypassed by breaking through: `BreakExitAction` (#2176, key `break_exit`) always
    succeeds and drops `level` by 1 per hit, dissolving the row (soft-delete via
    `dissolved_at`) at 0 rather than flooring it — the same intruder path that bypasses
    a locked exit.
  - `RoomWardDetails` — OneToOne to `RoomProfile`. `level` scales the reaction;
    `resonance` (FK to `magic.Resonance`) + `resonance_reserve` fund a daily upkeep
    cost drained by the `room_ward_upkeep_tick` cron job (`world/room_features/
    services.py`); reserve hitting 0 sets `lapsed_at` (ward stops reacting, but is
    never dissolved by lapsing alone — a lapsed ward can be refunded). Reaction is
    **deterministic, not a CheckType roll** (Decision 5): applies `reaction_condition`
    (FK to `conditions.ConditionTemplate`, filtered to `ConditionCategory.is_negative=True`
    at install time per #2280) and/or `reaction_damage_amount` to an
    unauthorized entrant. Both fields are set at install/upgrade time through
    `StartDefenseInstallationAction` (kwargs `reaction_condition`/`reaction_condition_id`
    + `reaction_damage_amount`), carried by `DefenseProgressionDetails`, and applied
    by `_install_or_level_ward` on project completion.
  - `RoomAlarmDetails` — OneToOne to `RoomProfile`, independent of `RoomWardDetails`
    (a room may hold both). No resonance upkeep — only the ward is magical. On an
    unauthorized entry, echoes to the room (identity-transparent, ADR-0083) and
    notifies the room's owner persona via `send_narrative_message` (offline-safe).
  - **Reaction dispatch:** both ward and alarm react from one shared entry point,
    `react_to_unauthorized_entry(actor, room)` (`world/room_features/services.py`),
    called by `flows.service_functions.movement.traverse_exit` immediately after a
    successful unauthorized move (`_trigger_ward` / `_trigger_alarm`) — the same seam
    every exit traversal already goes through, so no separate polling/trigger wiring
    was needed.
  - **Installation/upgrade** rides the pre-existing Project + Progression-details
    pattern (`DefenseProgressionDetails`, mirroring `RoomFeatureProgressionDetails`)
    via `StartDefenseInstallationAction` / `FundRoomWardAction`
    (`actions/definitions/room_features.py`); dispatched by both the web
    `DefenseInstallViewSet` (`world/room_features/views_defense.py`) and telnet
    `CmdDefense` (`commands/defenses.py`, `defense install <bars|ward|alarm>` /
    `defense upgrade` / `defense fund`) through the same seam. Ward installs
    accept optional `condition=<name>` (telnet) / `reaction_condition_id` (web)
    and `damage=<n>` / `reaction_damage_amount` kwargs (#2280) to configure the
    ward's reaction at install time; the condition must be from a harmful
    (`is_negative=True`) category.

### Boards (player-postable bulletin boards - #3286)
The IC read/write layer the Notice Board room feature and org pages were
missing: a `Board` is anchored to EITHER a `RoomProfile` (LOCATION board,
riding the shipped NOTICE_BOARD room feature) OR an `Organization` (ORG
board) - never both (DB check constraint, no JSON). Posts are signed,
persistent, exact-text notices authored by a `scenes.Persona` - a masked
persona posts under its false identity. Distinct from #2986 rumors
(distorting, spreading) and the GM-only `TableBulletinPost` (OOC,
table-scoped) - see `docs/adr/0228-board-posts-are-authored-by-persona.md`.

- **Models** (`world.boards.models`): `Board` (nullable `room_profile` /
  `organization` FKs, exactly-one-set check constraint + a per-anchor unique
  constraint - one board per room, one per org; `max_active_posts`, default
  30, newest-first display cap - no auto-expiry at MVP, older posts stay in
  the DB), `BoardPost` (`board` FK, `author_persona` FK `scenes.Persona`,
  `title`, `body`, `created_at`, `edited_at`, soft-delete
  `removed_by_persona` / `removed_at` - moderation never hard-deletes).
- **Permission booleans** on `societies.OrganizationRank`: `can_post_to_board`
  (every default rank grants it - org boards are rank-and-file coordination),
  `can_moderate_board` (leadership-only by default, mirrors
  `can_manage_ranks`).
- **Services** (`world.boards.services`): `create_board_post` /
  `edit_board_post` / `remove_board_post` (permission logic lives here,
  raises typed `BoardError`) - LOCATION posting/remove-own requires physical
  presence in the board's room; ORG posting requires `can_post_to_board`,
  removing another member's post requires `can_moderate_board` or staff.
  `get_or_create_location_board` / `get_or_create_org_board`;
  `visible_posts_for_board` (display-cap + soft-delete filter);
  `exclude_blocked_and_muted_board_authors` (mirrors
  `journals.services.exclude_blocked_and_muted_authors`).
- **Room-feature integration:** `room_features.services.handle_notice_board_progression`
  get-or-creates the LOCATION board on install; `PostToBoardAction` also
  lazily get-or-creates it at first post (covers a NOTICE_BOARD room
  installed before #3286 shipped).
- **Action-backed (ADR-0001):** `PostToBoardAction` / `EditBoardPostAction` /
  `RemoveBoardPostAction` (`actions/definitions/boards.py`); telnet
  `CmdBoard` (`board`, `board read <n>`, `board post <title>=<body>`,
  `board remove <n>`, scoped to the caller's current room) and the web
  dispatch seam converge on the same Actions.
- **API:** `BoardViewSet` / `BoardPostViewSet` (`world/boards/views.py`,
  read-only - writes go through action dispatch); ORG board visibility is
  gated on active `OrganizationMembership` (mirrors
  `tasking.views.OrgTaskViewSet`), LOCATION boards are public reads.
- **Web:** OrgPage's Board section (`orgs/pages/OrgPage.tsx`), and the room
  panel's board block (`game/components/RoomPanel.tsx`,
  `boards/components/BoardPanel.tsx`) - both share one `BoardPanel` read/post
  component.
- **Examine integration:** `actions/definitions/examine_extras.py`'s room
  section renders the LOCATION board's current postings under the existing
  Notice Board hint line.
- **Source:** `src/world/boards/` (see the app's `AGENT_GLOSSARY.md` and
  `docs/systems/boards.md` for the full write-up).

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
- **Component-gated Sanctification (#707):** both Sanctification `Ritual` rows carry seeded
  `RitualComponentRequirement` rows (a touchstone-mode row + 3 generic reagent rows, see the
  magic system doc's "Touchstones + reagents" section). `sanctum_install` validates/consumes
  them via `resolve_and_consume_ritual_components` before creating the Sanctum. `CmdSanctum`
  auto-gathers carried items (`_gather_components`); the web `install` endpoint takes an explicit
  `components` list of `ItemInstance` pks (`SanctifyActionSerializer.components`).
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

### Agriculture (Field + Granary crop/food system — #1864)
A coupled pair of Room Feature kinds implementing an accrue-then-collect food
system. The Field produces food into an `uncollected_pool` on a daily cron tick;
a character actively collects it via a lossy check-based dispatch (mirrors
`collect_org_income`); the Granary's level gates storage capacity; a domain's
population consumes food weekly with shortage raising unrest and lowering
prosperity.

**Food collection mini-game (#2218):** Collection is a two-event reactive flow.
Before the pool is zeroed, `FOOD_PRE_COLLECT` fires with a mutable
`FoodPreCollectPayload` — reactive flows may inspect the pool size, adjust the
`difficulty_modifier` (intimidation, persuasion, bribery), or cancel the
collection entirely (pool stays intact). After the outcome resolves,
`FOOD_COLLECTED` fires with a frozen `FoodCollectedPayload` for post-hoc
reactions (spawn a bandit ambush on catastrophe, etc.). Pool size scales
difficulty: pools above `FoodConfig.pool_difficulty_threshold` add +1 difficulty
per `pool_difficulty_step`, capped at `pool_difficulty_max_bonus`.

- **Models** (`world.agriculture.models`):
  - `CropType` — staff-authored catalog (name, base_production, description).
  - `FieldDetails` — OneToOne to `RoomFeatureInstance`; carries `crop_type` FK
    and `uncollected_pool` (accrued food awaiting active collection).
  - `GranaryDetails` — OneToOne to `RoomFeatureInstance`; no stored amount
    (the domain-level `FoodStockpile` holds the balance; level→capacity is
    derived at read time via `max_food_capacity(domain)`).
  - `FoodStockpile` — OneToOne to `Domain`; `stored` balance + `last_collected_at`.
    Lazily created via `get_or_create` in `collect_field_food`.
  - `FoodConfig` — singleton (pk=1) tuning knobs: production rate, consumption
    per capita, shortage penalties, granary capacity per level, pool-size
    difficulty scaling (`pool_difficulty_threshold` / `pool_difficulty_step` /
    `pool_difficulty_max_bonus`, #2218), and army provisioning knobs
    (`army_food_per_member` / `max_provisioning_morale_penalty` /
    `max_provisioning_strength_penalty`, #2375).
  - `FoodTransfer` — audit row for inter-domain food transfers (#2219);
    source_domain, target_domain, amount, acting_persona, created_at.
    Mirrors `CurrencyTransfer`.
- **Services** (`world.agriculture.services`):
  - `field_production_tick()` — daily cron; accrues `base_production × level ×
    multiplier` into each active Field's `uncollected_pool`.
  - `collect_field_food(character, field_instance)` — active collection dispatch;
    emits `FOOD_PRE_COLLECT` (cancellable, #2218), zeroes pool, rolls a Food
    Collection check at effective difficulty (base + pool bonus + reactive
    modifier), applies `COLLECTION_BAND_PCTS` (reused from currency), then
    **unrest skims the haul** (`_apply_unrest_skim`, #2238), lands food into
    domain's `FoodStockpile` (capped at Granary capacity; excess is
    overflow/lost), emits `FOOD_COLLECTED`.
  - `domain_consumption_tick()` — weekly cron (part of weekly rollover); the
    domain **civ-stat update**: population consumes food; shortage raises unrest +
    lowers prosperity; a **well-fed** week instead relaxes unrest + recovers
    prosperity toward `FoodConfig.prosperity_equilibrium` (#2238, recovery drift);
    then rolls `houses.maybe_open_unrest_crisis` per domain. No stockpile row =
    perpetual shortage. Telemetry: `domains_processed` / `shortages` / `crises_opened`.
  - `provision_army(covenant)` (#2375) — called at battle covenant mobilization
    (`rise_battle_covenant_via_session`). Counts engaged members, computes
    `needed = engaged_count × army_food_per_member`, deducts from the covenant's
    org's domains' `FoodStockpile` reserves (proportionally), and stores the
    resulting `provisioning_ratio` (0.0–1.0) on `Covenant`. `add_unit()` reads this
    ratio and reduces the `MilitaryUnit`'s starting morale/strength by
    `(1 - ratio) × max_penalty`, capped at config knobs, never below 1. Cleared at
    `stand_down_battle_covenant()`. Fires a narrative message to engaged members.
  - `resolve_domain_for_feature(instance)` — walks `RoomProfile.area` →
    `AreaClosure` ancestor chain to find the `Domain`.
  - `max_food_capacity(domain)` — sums `granary.level × capacity_per_level`
    across all active Granaries in the domain's area subtree.
  - `transfer_food(*, source_domain, target_domain, amount, acting_persona,
    character)` (#2219) — moves food from source `FoodStockpile` to target
    (capped at Granary capacity; overflow lost). Emits `FOOD_PRE_TRANSFER`
    (cancellable) + `FOOD_TRANSFERRED` (frozen) events. Creates a `FoodTransfer`
    audit row.
- **Flow service functions** (`flows.service_functions.agriculture`):
  - `food_collection_difficulty` — flow-callable wrapper that computes the
    pool-size difficulty bonus for a collection attempt (#2218).
- **Action:** `CollectFoodAction` (key `"collect_food"`, category
  `"agriculture"`) — the single commit seam for telnet + web. Resolves its Field
  from a pre-resolved `field_instance`, a `field_instance_id` (web/REST — the REST
  path does no ObjectDB resolution, so the action resolves it), or the active FIELD
  feature in `actor.location` (telnet). Handles cancelled results (returns
  failure with `cancelled: True`). **Surfaces (#2237):** telnet `harvest`
  (`commands/agriculture.py` `CmdHarvest`) + web `POST /api/agriculture/collect/`
  (`CollectFoodView`, body `{field_instance_id}`). Without a surface the loop
  couldn't close — the pool filled but never drained.
- **Events:** `FOOD_PRE_COLLECT` (cancellable pre-collect, #2218),
  `FOOD_COLLECTED` (post-collect outcome), `FOOD_SHORTAGE`,
  `FOOD_PRE_TRANSFER` (cancellable pre-transfer, #2219),
  `FOOD_TRANSFERRED` (post-transfer outcome) (in `flows/constants.py`).
  Payloads: `FoodPreCollectPayload` (mutable), `FoodCollectedPayload` (frozen),
  `FoodPreTransferPayload` (mutable), `FoodTransferredPayload` (frozen) in
  `flows/events/payloads.py`.
- **Cron tasks:** `agriculture.field_production` (daily 24h),
  `agriculture.domain_consumption` (weekly, via weekly rollover).
- **Seeds:** `ensure_field_granary_kinds()` + `ensure_starter_crop_types()`
  (Wheat/Barley/Root Vegetables with PLACEHOLDER production values).
- **Source:** `src/world/agriculture/`

### Lab (crafting-station economy — #1234)
Second Room Feature kind (`RoomFeatureServiceStrategy.LAB`), registered by
`world.items`. A per-Lab durability meter gates and wears down under crafting
attempts, with a coppers-only repair economy.

- **Models:** `LabStationDetails` (`world.items.crafting.models`) — per-kind
  state, OneToOne to `RoomFeatureInstance` (mirrors `SanctumDetails`);
  `durability` / `max_durability` + `is_broken` property.
- **Key functions** (`world.items.crafting.station`):
  `handle_lab_progression` (the LAB strategy — installs/upgrades the feature
  instance, (re)setting durability to the new level's max on both), and
  `repair_station_durability` (coppers-only repair via
  `currency.services.transfer`, cost scales with level and points restored).
- **Crafting integration:** `CraftingRecipe.requires_station` gates
  `run_crafting_recipe` (raises `CraftingStationRequired` /
  `CraftingStationBroken`) and wears the station by 1 durability per attempt
  that reaches the roll; `CraftingQuote.station_status` surfaces a read-only
  snapshot. See [items.md](items.md) for the full pipeline.
- **TELNET+WEB:** `StartRoomFeatureProjectAction` / `RepairLabStationAction`
  (`actions/definitions/room_features.py`); `CmdLabStation` (`station`,
  `commands/crafting_station.py`) and `LabStationViewSet`
  (`/api/items/lab-stations/`) converge on the same Actions.
- **Source:** `src/world/items/crafting/station.py`.

### Library, Training Room, Siege Deck, Captain's Quarters (#675)
Four Room Feature kinds that **broaden existing systems** via read-time
bonus lookups (mirrors Sanctum's pattern — `instance.level` is the bonus
input, no per-kind details model). Install/upgrade reuse the shared
`_install_or_level_feature` handler + `StartRoomFeatureProjectAction`.
Genuinely-new-mechanics features (Brig/prisoner, Stables/mount,
Field+Granary/crop) are split to `needs-design` follow-up issues.

- **Library** (`RoomFeatureServiceStrategy.LIBRARY`, `max_level=10`):
  discounts codex-learning AP. Consumer hook:
  `CodexTeachingOffer.accept(room_profile=...)` in
  `world/codex/models.py` calls `active_library_in(room_profile)` and
  reduces `learn_cost` by `level * LIBRARY_AP_DISCOUNT_PER_LEVEL` (floor 1).
- **Training Room** (`TRAINING_ROOM`, `max_level=3`): discounts
  technique-learning AP. Consumer hook: `learn_technique(..., location=...)`
  in `world/magic/services/technique_acquisition.py` resolves the room
  profile from the location, calls `active_training_room_in(room_profile)`,
  and reduces `ap_cost` by `level * TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL`
  (floor 0). Callers `learn_technique_from_ritual` and
  `accept_technique_offer` pass `character.location`.
- **Siege Deck** (`SIEGE_DECK`, `max_level=5`, renamed from Cannon Deck —
  pre-gunpowder: ballistae/catapults/scorpions): adds to a ship's effective
  armament in battle. Maritime-gated via `allowed_building_kinds` (the
  Vessel `BuildingKind`; airship kinds added as a content edit when they
  arrive). Consumer hook: `_siege_deck_armament_bonus(ship)` in
  `world/ships/sanctum_bonus.py` sums `level *
  SIEGE_DECK_ARMAMENT_PER_LEVEL` across active Siege Decks on the ship's
  rooms; folded into the `armament` slot of `ShipStatBonus` consumed at
  `battle_bridge.py:96`.
- **Captain's Quarters** (`CAPTAINS_QUARTERS`, `max_level=1`):
  maritime-gated reachability feature (like Command Center). No numeric
  bonus; its "content" is that surfaces are reachable where it stands.
  Consumer hook deferred (`needs-design`).
- **Social Hub** (`SOCIAL_HUB`, `max_level=5`, #1694): the owner-upgradeable
  amplifier on top of `RoomProfile.is_social_hub` (#1572). Store/room owners
  (`PERSONA` / `ORG_TRADE`) install it via the plain ROOM_FEATURE_PROGRESSION
  project; `handle_social_hub_progression` flips `is_social_hub` on and
  reconciles a crowd-draw `TRAFFIC` `LocationValueModifier`
  (`sync_social_hub_traffic` → `world.locations.services.set_room_stat_modifier`,
  `level * SOCIAL_HUB_CROWD_DRAW_PER_LEVEL`). That bonus flows through the
  location cascade into `room_activity_band`, which the **deed-spreading path**
  already reads (`world/societies/spread_services.py`) — so a bigger hub spreads
  deeds further and earns more **fame** from the retelling. Prestige (awarded at
  the deed, no room context) is intentionally not hub-amplified. Dissolving
  clears the amplification (a reconcile drops the modifier; `active_social_hub_in`
  returns None) but leaves the baseline hub bool. Magnitudes PLACEHOLDER.
- **Helpers** (`world/room_features/services.py`): `active_library_in`,
  `active_training_room_in`, `active_siege_deck_in`,
  `active_captains_quarters_in`, `active_social_hub_in` — each filters by
  `service_strategy` + `.active()`, mirroring `active_hub_feature`.
- **Source:** `src/world/room_features/seeds.py`, `services.py`, `apps.py`.

### Mechanics
Unified modifier system — categories, types, sources, and per-character modifier values.

- **Models:** `ModifierCategory`, `ModifierTarget`, `ModifierSource`, `CharacterModifier`, `ConsequenceEffect`, `ObjectProperty`, `ChallengeTemplateProperty`, `PropertyDamageModifier` (#1793), `PropertyDetonation` (#2210), `SituationTemplate`, `SituationChallengeLink`, `SituationTrapLink` (#1625), `SituationInstance`
- **Key Functions:**
  - `instantiate_situation(template, location) -> SituationInstance` (#1625) — mints
    a SituationInstance + materializes its SituationTrapLink rows into Trap rows.
    Traps only; does not mint ChallengeInstances (see mechanics.md Situation System).
  - `property_damage_bonus(target, damage_type) -> int` (#1793) — sums `PropertyDamageModifier`
    rows for a target's active `Property` set; folded into combat technique damage in
    `CombatTechniqueResolver._profile_damage` (`world/combat/services.py`)
  - `volatile_object_property(target) -> ObjectProperty | None` (#2210) — the
    `ObjectProperty` row making `target` "volatile" (its `Property` carries a
    `PropertyDetonation`), or `None`. Consumed by combat redirect resolution
    (`world/combat/services.py`'s `_try_technique_interpose` REDIRECT branch) — see
    combat.md's Redirect section.
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
  - `resolve_challenge(character, challenge_instance, approach, capability_source) -> ChallengeResolutionResult` — resolve a character's action against a challenge. `ResolutionContext.target` is now populated from `challenge_instance.target_object` (#2503, was always `None`), so an `EffectTarget.TARGET` consequence lands on the actual object.
  - `select_consequence(character, check_type, difficulty, consequences) -> PendingResolution` — generic: perform check + select weighted consequence (in `checks/consequence_resolution.py`)
  - `apply_resolution(pending, context) -> list[AppliedEffect]` — generic: dispatch ConsequenceEffects (in `checks/consequence_resolution.py`)
  - **Bare-object affordances (#2503, ADR-0147):** `Application.default_template` (nullable FK
    to `ChallengeTemplate`) is a curated gate — when set, `get_available_actions` also
    synthesizes an `AvailableAction` straight from an `ObjectProperty` match on any object at
    the location (no authored `ChallengeInstance` needed), via `_bare_object_actions`. Surfaced
    through a second action backend, `ActionBackend.WORLD_INTERACTION` (`ActionRef.application_id`
    + `target_object_id`); `dispatch_player_action` re-validates, mints via
    `instantiate_challenge(resolved_default_template, location, target_object)`, then resolves
    through the same `resolve_challenge()`. `stage_property(target, property_, value=1)` — the
    GM improv upsert wrapping `ObjectProperty.objects.update_or_create` (used by
    `StagePropertyAction`, see the Actions section). See
    `docs/architecture/action-template-pipeline.md`'s "Bare-Object Affordances" section.
- **Categories:** stat, magic, affinity, resonance, action_points, development, height_band,
  condition_control_percent, condition_intensity_percent, condition_penalty_percent, goal
- **Constants (Spec D PR1):**
  `EQUIPMENT_RELEVANT_CATEGORIES = frozenset({"stat", "magic", "affinity", "resonance"})`
  — gates the equipment modifier walk in `get_modifier_total`
- **Pattern:** `DistinctionEffect` → `ModifierSource` → `CharacterModifier`. Equipment
  bonuses flow through `passive_facet_bonuses` + `covenant_role_bonus` (called inline
  by `get_modifier_total`, not stored as `CharacterModifier` rows). **Exception (#1834):** a
  resonance-category `DistinctionEffect` never enters this pattern at all — no
  `ModifierSource`/`CharacterModifier` row — it flows through
  `reconcile_distinction_resonance_grants` (the `DistinctionResonanceGrant` sidecar in
  `world.magic`) instead. A POWER-category `DistinctionEffect` (potency) is unaffected and
  follows the pattern normally.
- **EffectType values** (`world/checks/constants.py` — dispatched by `world/mechanics/effect_handlers.py`):
  - Pre-#1018: `APPLY_CONDITION`, `REMOVE_CONDITION`, `ADD_PROPERTY`, `REMOVE_PROPERTY`,
    `DEAL_DAMAGE`, `LAUNCH_ATTACK`, `LAUNCH_FLOW`, `GRANT_CODEX`, `MAGICAL_SCARS`,
    `LEGEND_AWARD`, `CAPTURE`, `ESCAPE_CAPTIVITY`, `RESCUE_CAPTIVE`
  - Added in #1018: `CREATE_POSITION`, `MOVE_TO_POSITION`, `SEVER_EDGE`,
    `CONNECT_EDGE`, `GRANT_FLIGHT`, `REMOVE_FLIGHT`
  - Added in #1697: `SET_RELATIONSHIP_CONDITION`, `SHIFT_AFFECTION`
  - Added in #2037: `GRANT_DISTINCTION` — `ConsequenceEffect.distinction` FK (CASCADE, mirrors
    `property`) + `distinction_rank` (nullable, mirrors `property_value`; null = advance one
    step). Handler `_grant_distinction` calls the shared `distinctions.grant_distinction` seam
    with `origin=DistinctionOrigin.CONSEQUENCE_POOL`; a `DistinctionExclusionError` is caught
    and turned into a skipped `AppliedEffect` (mirrors `_apply_capture`'s
    `AlreadyCapturedError` skip pattern) — never crashes the surrounding resolution.
  - Added in #3071: `GRANT_SECRET` — mirrors `GRANT_CODEX`'s shape (`ConsequenceEffect.secret`
    FK, CASCADE, nullable) but not its bypass: `_grant_codex` deliberately hand-rolls
    `get_or_create(status=UNCOVERED)` to stay below `grant_codex_entry`'s full-KNOWN grant,
    while `_grant_secret` calls the canonical `world.secrets.services.grant_secret_knowledge`
    directly — `SecretKnowledge` has no UNCOVERED-equivalent status field to bypass; holding
    the row at all already means the fact is known, and `knows_category`/`knows_consequences`
    are two independently-unlockable boolean layers on top. Left at their defaults (`False`),
    that call already IS the "a scene hands you a lead, not the answer" grant. Skips gracefully
    (mirrors `_grant_codex`) when the character has no `RosterEntry`.
- **Integrates with:** distinctions (modifier sources), conditions (modifier sources), traits (stat modifiers),
  action_points (AP modifiers), goals (goal domains), positioning (reshape handlers in effect_handlers.py)
- **The effect layer is lore-authorable (#3071):** `checks.consequence`,
  `checks.consequenceeffect`, `actions.consequencepool`, `actions.consequencepoolentry` are
  registered in `CONTENT_MODELS` (`core_management/content_export.py`) — the load-bearing gap
  the anti-reinvention ledger flagged: the template/link layer (`ChallengeTemplate`, mission
  routes) was already lore-authorable, but the layer that actually FIRES a reward
  (`ConsequenceEffect`, via `apply_all_effects`) was seeder/admin-only. `ConsequencePool`
  already carried `NaturalKeyMixin` (#1871, keyed `name`) but was never registered.
  `Consequence` is keyed `(outcome_tier, label)`, `ConsequenceEffect` is keyed `(consequence,
  execution_order)` — neither is DB-enforced (mirrors `ActionEnhancement`, #3034: several
  production seeders write these tables via `.objects.get_or_create()`/`.objects.create()`
  directly). `ConsequencePoolEntry` is keyed `(pool, consequence)`, backed by the pre-existing
  `unique_pool_consequence` constraint (mirrors `TechniqueVariant`, #3034). All four now carry
  `CreditedContent` (their prose fields — `Consequence.mechanical_description`,
  `ConsequencePool.description`, and several `ConsequenceEffect` narrative-payload fields —
  are classified in `core_management/prose_fields.py`). Rows are authored-only (every
  production creation site is a seeder/factory, no player-facing mutation path), so no
  `EXPORT_FILTERS` row-level split was needed.
- **Source:** `src/world/mechanics/`
- **Details:** [mechanics.md](mechanics.md)

### Items & Equipment
Items, equipment, inventory, and currency. Spec D PR1 shipped facets, equip/unequip

- **Enchantment authoring (#3430):** `ItemCheckModifier`/`ItemTemplateProperty`
  (template check-bonus + default-Property authoring; `checks/services.py`'s
  `collect_check_modifiers` EQUIPMENT block is the runtime consumer of the former,
  `materialize.apply_template_properties` of the latter) were runtime-wired but
  shell-only — now inline on `ItemTemplateAdmin`
  (`ItemCheckModifierInline`/`ItemTemplatePropertyInline`,
  `src/world/items/admin.py`). New `ItemTemplate.requires_attunement` gates a
  flagged template's `ItemCheckModifier` contribution and `use_item` dispatch on
  `ItemInstance.attuned_to_character_sheet`: the EQUIPMENT block's queryset
  constrains equipped-and-attuned to the SAME joined instance in one `.filter()`
  call (apply-once stacking — two equipped instances, one attuned, contributes
  once, never doubled); attunement writers are unchanged (touchstone ritual +
  admin). See docs/systems/items.md ("Enchantment authoring").

- **Fashion vocabulary (#2907):** `Silhouette` (the wearable FORM — umbrella
  hierarchy, `WearFamily`, prose skins via `silhouette_prose_noun`: cut/garments,
  setting/jewelry) with `ItemTemplate.silhouette` (authored default) +
  `ItemInstance.silhouette` (family-validated crafter pick at making;
  `effective_silhouette` resolves the fallback); `Style` re-ruled
  cultural/historical (`origin`, `era` current/ancient, `founder` persona FK —
  intent adjectives rejected as Accent-redundant); seed cluster `fashion`
  (47 PLACEHOLDER forms + 9 registers). Modeling economy: `CachetWallet` +
  `ShowcaseState` toggle (`ShowcaseAction`/`CmdShowcase`), entrance
  auto-stake → `FashionShowing` ledger → weekly-cron settlement
  (`settle_fashion_showings`; never immediate), acclaim on items/outfits +
  Silhouette/Style vogue momentum. Coverage ruling (#2965, ADR-0194): accents
  multiply per visible slot, prestige per-piece, legend pierces concealment;
  `compute_worn_visibility` + `RevealAction`/`reveal`. See docs/systems/items.md.

- **#2862-review gap closures (#2869 follow-through):** telnet `endure`/`retreat`
  (hazard prompt answers — the prompt now names them), `turf` / `turf push <crew>`
  (turf status + the war's opening move), `makeshade <character>` (GM tool; the only
  caller `apply_shade_undeath` has ever had), the `inventory` burden line
  (encumbrance was invisible before), the `weather` and `justice_laws` seed clusters
  (`world/seeds/weather_content.py`, `world/seeds/justice_laws.py` — the latter is
  what makes crime mint heat at all), the Shade anchor + daily-drain production seed,
  and admin for `MarketStall` (where a fence gets placed), `NeighborhoodTurf`,
  `CarriedBody`, `AppetiteUpkeep`(+receipts), `FeedingRecord`, `HazardResponseState`.
- **The underworld (#2862, ADR-0185):** the fence (`MarketStall.stall_kind=FENCE`,
  `sell_to_fence` — the first sell-to-NPC path; first consumer of `ItemTemplate.value`;
  first live heat producers for the dormant `contraband`/`smuggling` CrimeKinds, AreaLaw-
  weighted); Dust/Haze intoxicant ladders (`condition_template` override on INTOXICATE —
  Dusted's pass-out reaches the dream realm via the built Unconscious rule; Hazed cannot
  drop anyone); `CraftingRecipe.required_feature_kind` (LAB hardcode generalized — drug
  refinement gates on the Workshop of Iniquity); `NeighborhoodTurf` + `turf_services`
  (grip/flip; writes `StatKey.CRIME`, re-targets CRIME_KICKUP, provokes Retaliation
  crises; the orphaned gang-turf project machinery finally moves state via
  `complete_gang_turf` + `start_gang_turf` action); guard pressure scales with area
  CRIME (`area_stat_total` in locations services); 7 RESTRICTED criminal missions on a
  covert board + first `MissionCategory` rows + the standing smuggling route
  (`TaskTemplate` + linked mission — the dual-execution bridge); seeds in
  `world/seeds/underworld.py` (cluster `underworld`), all PLACEHOLDER.
- **Consumables + cooking (#2852, ADR-0184):** three consequence EffectTypes
  (`RESTORE_FATIGUE` → new `fatigue.services.recover_fatigue`; `RESTORE_ANIMA` clamped —
  consumption, never regeneration; `INTOXICATE` → `imbibe`) make every edible pure content:
  a consumable ItemTemplate + deterministic on-use pool (`seed_consumable_catalog` — bread,
  stew, wine, ale, firebrandy, Cardian Ambrosia, all PLACEHOLDER). Cooking check-spine
  activation (`world/seeds/provisioning_checks.py`, cluster `provisioning`): Cooking
  skill/CheckType (wits+agility avg + Cooking, Brewing spec linked as a
  `CheckTypeSpecialization` row at weight 1.0 — #2894), the live 12-rung QualityTier
  ladder (Poor→Legendary, #2878) + the 7-rung AccentLevel ladder. **The stationless
  ITEM_CREATE recipes (Hearty Stew, Honeyed Wine, Dream Dust, Haze) + their ingredient
  ItemTemplates + skill caps moved to the lore repo (#3006 Task 4)** — the seeder no
  longer mints them (see "Production data path" above); a fresh deploy with no lore
  fixtures has the Cooking check spine but no recipes to roll it against. Event
  catering: `EventCatering` snapshot rows
  (#2869 reshaped: `designate_catering_container` flags a vessel — banquet table,
  amphora, tray — and the `put_in` path tags any consumable set out in it via
  `tag_catered_provision`; nothing is consumed, and the tag is permanent and deduped
  per (event, item), so food taken back out still counts and shuffling cannot farm
  prestige); at `complete_event` the tagged provisions' quality sum mints the host's
  Hospitality deed via `create_solo_deed` (`_award_catering_prestige` — the one
  event-completion reward hook). Items carry their catering history on examine
  ("This amphora was used for catering at ..."), rendered through the
  `LookAction` examine-extras seam (ADR-0213). Telnet: `event cater <container>`.
  **Event grandeur (#2357):** a catering-shaped sibling for once-in-a-lifetime events
  (royal wedding, coronation, grand ball) — `EventGrandeurContribution` tags a
  currency-sink spend (`contribute_grandeur`, `world.currency.services.transfer`,
  null destination) against a `GrandeurCategory` (VENUE/ENTERTAINMENT/FAVORS/DECOR —
  food stays catering's lane). At `complete_event`, `_award_grandeur_prestige` sums
  spend into a sqrt-diminishing-returns score (`_grandeur_score`, capped), mints the
  primary host's "Grandeur" deed via the same `create_solo_deed` +
  `_apply_grand_display` pipeline catering uses (independent scores — both can fire on
  one event), and — only when the event has a linked, COMPLETED `Ceremony` whose
  `ceremony_type.key` is WEDDING or CORONATION — mints an additive per-honoree deed
  (`_award_grandeur_honoree_cut`, a flat percent of the host's deed value, mirroring
  `CeremonyConfig.officiant_cut_percent`'s shape) on top of whatever `finish_ceremony`
  already awarded them (the COMPLETED gate, not merely "linked," stops an
  `abandon_ceremony`'d wedding from still paying a cut — event completion and
  ceremony finish/abandon are independent triggers). Ratified 2026-08-15: no
  `is_milestone` flag and no cooldown bookkeeping — for a ceremony-linked event the
  economic cost of the spend IS the gate; plain diminishing returns apply to every
  event alike. **Nonrefundable on cancellation** (controller-ruled, spec silent):
  `cancel_event` has no grandeur unwind — a cancelled SCHEDULED event's contributions
  stay spent (real sink, no prestige minted) as nonrefundable-deposit flavor. The
  org's existing 10% member-deed trickle (`Organization.accumulated_prestige`) feeds
  off the bigger score automatically — no new house-benefit code path. Action:
  `event_invest_grandeur` (`ContributeGrandeurAction`, treasury-sourced spends gated
  on `can_spend_treasury`
  at the Action layer). Telnet: `event grandeur <id> category=<...> amount=<n>
  [org=<name>]`. Frontend: `GrandeurPanel` on the event detail page.
services, and equipment-modifier integration. Spec D PR2 (#1031) added the generic
crafting framework and check-driven facet/style attachment. #2211 added the ITEM_CREATE
mint pipeline; #2240 made it playable web-first: `ItemCreateCraftViewSet` serves
`GET .../crafting/create/recipes/` (browse) + `.../quote/` (cost/quality) alongside the
`POST` mint, and the React `CreateItemDialog` (Wardrobe "Craft item") drives them.
#2242 added **recipe knowledge**: `CraftingRecipe.requires_knowledge` gates a pattern
behind `CharacterRecipeKnowledge` (a character↔recipe join) — open recipes stay open,
gated ones need a learned row. Both the browse endpoint and `run_crafting_recipe` enforce
it; `world.items.crafting.knowledge` carries `character_knows_recipe` / `grant_recipe_knowledge`
/ `teach_recipe` (teacher must know it), raising `RecipeNotKnown`. Discovery via the clue
loop is a future hook. #2243 added the crafting **reward loop**:
`world.items.services.pricing.appraise(instance)` (quality tier × `template.value` +
material `lore_value` → suggested worth, surfaced as the read-only
`ItemInstanceReadSerializer.suggested_value`) and **masterwork→renown**
(`world.items.crafting.reward` — a craft whose tier's `stat_multiplier` meets
`MASTERWORK_STAT_MULTIPLIER_THRESHOLD` mints a solo `LegendEntry` for the maker via
`create_solo_deed`, from `run_crafting_recipe`). Mint self-provenance now stamps
`designer_*` too (#2066/#2243). Magnitudes PLACEHOLDER.

**Theft reclamation (#2368):** `ReclamationClaim` (claimant/original-claimant sheets —
the immunity anchor never moves on assignment; `estate_claim` bridge FK; `acquired_from`
lineage) + `ClaimTraceStep` (one revealed hop per row). Services
(`world.items.services.reclamation`): `file_theft_claim` (provenance-victim gate),
`open_trace_for_estate_claim`, `assign_claim`, `advance_trace` (check-banded, one hop
per success, botch chills `TRACE_CHILL_HOURS`), `file_reclamation_accusation` (lawful
route — mints receiving-stolen-goods heat on the holder),
`execute_lawful_seizure` / `record_steal_back` (both `_return_item` → RECOVERED
provenance event clears the hot flag), `has_reclamation_standing`. API:
`/api/items/reclamation-claims/` (list/file/claimable/advance/report/take-back,
self-scoped; `claimable` lists the viewer's unfiled thefts — the filing seam). Web:
`/reclamation` (`ReclamationPage` — file at discovery, follow the trail hop by hop,
then choose lawful seizure vs steal-back; linked from the inventory sidebar). The
holder is never notified a claim exists.

- **Models:**
  - `QualityTier`, `InteractionType`, `ItemTemplate`, `WeaponClass` (#2879 — weighted
    strength/agility blend for `ItemTemplate.weapon_class`, replaces the small/medium/heavy
    override; see `world.combat.stat_mapping`), `TemplateSlot`, `ItemInstance`,
    `TemplateInteraction`, `EquippedItem`, `OwnershipEvent`, `CurrencyBalance`
  - `ItemFacet` (Spec D §4.2) — through-model linking `ItemInstance` ↔ `Facet` with
    `attachment_quality_tier`; unique per (item_instance, facet)
  - `ItemStyle` — through-model linking `ItemInstance` ↔ `Style` with
    `attachment_quality_tier`; unique per (item_instance, style)
  - `Style.audacity` (#2029) — `StyleAudacity` tier (UNDERSTATED/EXPRESSIVE/BOLD/
    OUTRAGEOUS; default EXPRESSIVE) scaling how much a Style is mechanically rewarded.
    `AudacityTuning` (singleton, pk=1, mirrors `magic.RelationshipBondPullTuning`) is the
    staff-tunable per-tier multiplier (defaults 0.75/1.00/1.35/1.75); accessed via
    `get_audacity_tuning()` / `audacity_multiplier_for(style)`
    (`world.items.services.styles`). Two consumers: the passive motif-coherence bonus
    (`_compute_motif_coherence_bonus`, `world/mechanics/services.py`) multiplies each
    matched binding's quality contribution by its style's audacity multiplier; the peer
    style-presentation endorsement grant (`create_style_presentation_endorsement`,
    `world/magic/services/gain.py`) scales the base grant by the *highest*-audacity match
    when the endorsee wears multiple items whose styles bind to the endorsed resonance.
    Seeded vocabulary: `seed_style_vocabulary()` (`world/seeds/game_content/items.py`) —
    16 names, four per tier.
  - **Crafting sub-models** (`world.items.crafting`, registered under the `items` app):
    `CraftingRecipe` (one per `CraftingRecipeKind`; carries check config + AP/anima cost +
    default consumption policy), `CraftingMaterialRequirement` (ingredient rows — each
    targets **either** a specific `item_template` **or** a `MaterialCategory` (xor,
    DB-enforced); a category requirement is satisfied by any member template. Build 0a.
    `world.items.seeds_facet_reagents.ensure_facet_attach_reagent_requirement(recipe)`
    seeds a generic reagent requirement onto a FACET_ATTACH recipe, content-only, #707),
    `CraftingSkillCap` (skill-rank → quality ceiling ladder), `CraftingRecipeConsequence`
    (weighted consequence pool entry with per-row `cost_consumption` override). Replaces
    the old `FacetCraftingConfig` singleton. **Production data path (#3006):** all four
    models (+ `MaterialCategory`) carry natural keys and are in `CONTENT_MODELS`, so the
    lore repo authors/overrides recipes, skill caps, material requirements, and
    consequence rows directly; `CONFIG_PREREQUISITES["crafting"]` seeds a floor row for
    each null-`check_type`-raising kind (`FACET_ATTACH`/`STYLE_ATTACH`/`GEM_CUT`, one
    shared "Enchanting" `CheckType`, plus the FACET_ATTACH reagent default) before the
    content load so a fresh deploy is never `CraftingNotConfigured`; authored fixtures win
    via upsert. `ITEM_CREATE` recipes raise nothing when absent, so they're pure content —
    the four example recipes (Hearty Stew, Honeyed Wine, Dream Dust, Haze) moved out of
    `world.seeds.provisioning_checks` to the lore repo; that seeder now only ensures the
    Cooking check spine + QualityTier/AccentLevel ladders. See `docs/systems/items.md`
    "Production data path" for detail.
  - **`MaterialCategory`** (`world.items.models`, lookup) — a crafting-equivalence class of
    materials (e.g. "Precious Gemstones"); `ItemTemplate.material_category` FK points into it
    (specific→general, ADR-0010). The *eligibility* axis only; value-denominated requirements
    ("N value of a tier") are Build 0b, gated on the gemstone-value ladder. Crafting
    *execution* honors category requirements; the read-only quote preview raises
    `CategoryRequirementsNotQuotable` until the quote surface lands.
  - **Gem value model** (`world.items.gems`, Build 0b slice 1) — gem *types* are ordinary
    `ItemTemplate` rows decorated by a `GemDetails` sidecar (`quality_level` 1–15; tier =
    `MaterialCategory`; motif reuses `tied_resonance`), so they stay requirable/consumable like
    any material. A cut gem *instance* is an `ItemInstance` decorated by `GemInstanceDetails`
    carrying its size/purity/cut `GemGrade`s (one axis-discriminated lookup, `multiplier` floor
    1.0). Worth = `template.value × size × purity × cut` via `world.items.gems.services
    .compute_gem_worth`, folded into the wired `appraise()` (`services/pricing.py` → `suggested_value`).
    Accessors: `ItemTemplate.gem_type_or_none`, `ItemInstance.gem_or_none`. No standalone gem
    roster (would orphan the consumption stack); `quality_level` is a plain int, not new
    `QualityTier` rows. Mining / cut-recipe are later 0b slices.
  - **Gem adornment** (`world.items.gems`, Build 0b slice 2) — `Adornment` (standalone model,
    *not* an `ItemAttachment` subclass — that base requires a non-null `attachment_quality_tier`,
    meaningless for a grade-carrying gem) links a host `ItemInstance` to an embedded `gem_instance`
    with `narration` + `set_by_account`/`set_at`. `world.items.gems.services.adorn_item()` gates on
    `ItemTemplate.adornment_capacity` (mirrors `facet_capacity`), validates the offered instance is
    a gem and unset, embeds it (clears holder), and adds its worth to the host's `lore_value` so the
    wired `appraise()` reflects it. `adorned_materials(host)` is the queryable "materials on this
    piece" seam magic reads. Exceptions: `AdornmentCapacityExceeded` / `NotAGem` / `GemAlreadyAdorned`.
    Safe craft-time path only. **Risky prying** (`pry_adornment`, Build 0b slice 6): the risky
    end of the lifecycle — a `perform_check` (skill feeds the roll) removes a set gem; the stone
    leaves the piece either way (host `lore_value` drops by its worth), freed to the pryer's
    inventory on success or **shattered** on a botch (same shatter spine as gem cutting).
    Returns `PryResult`; spends AP up front.
  - **Gem cutting** (`world.items.gems.services.cut_gem`, Build 0b slice 3) — the risky value-add
    axis, "very much crafting": reuses a `CraftingRecipe` (`CraftingRecipeKind.GEM_CUT`) config +
    the `perform_check` primitive (crafter's `skill_trait` feeds the roll), spends the recipe's AP,
    and resolves `success_level` **directly to an improved cut `GemGrade`** (`resolve_cut_grade` —
    no `QualityTier` detour, since the framework's outcome type doesn't fit a gem grade). A botch
    (`success_level < min`) **shatters** the stone (deleted); success advances the cut ladder and
    worth recomputes. Returns `CutResult`. **Player-reachable (#3006 Task 3):** `CutGemAction`
    (key `cut_gem`, `actions/definitions/crafting.py`) wraps `cut_gem` directly — not
    `run_crafting_recipe`/the handler registry, since gem cutting has no attach/create
    handler, consequence pool, or material staging — resolving the `GEM_CUT` recipe via
    the same `_resolve_recipe_for_run` seam `run_crafting_recipe` uses (the Task 2 seeded
    default row is what makes a fresh deploy playable). `GemCutViewSet`
    (`GET/POST /api/items/gem-cuts/`, `GET .../quote/`) mirrors `ItemFacetViewSet`/
    `ItemStyleCraftViewSet`; the quote (`build_gem_cut_quote`) reports AP cost/difficulty
    plus an explicit shatter-risk sentence before the player commits. Telnet: `craft cut
    item=<id>` (`CmdCraft`). Deferred: a hard skill-value cap (`CraftingSkillCap`
    style) and the consequence-pool narrative outcomes; risky adornment prying reuses this shatter
    spine.
  - **Gem mining engine** (`world.items.gems.mining.roll_gem_haul`, Build 0b slice 4) — the pure,
    deterministic (injected `roll` seam) haul generator. One mine cycle → a common-gem **aggregate
    value** (`GemHaul.common_value`, never instanced) plus, rarely, a few **Rare-Find** gem
    `ItemInstance`s (born uncut, loose). Mine quality + minister bonus both raise the Rare-Find
    chance (base 1%) and shift every axis roll up; a find rolls 1d4 stones with `size`/`purity`
    floored above common (type not floored), top-heavy grade distribution (`_grade_index`, roll²).
    Does **not** schedule or wire domains — the weekly cron, the per-holding
    `HoldingMaterialSource` row (#2540 slice 2; was the `mine_quality` field), and the
    schema-only minister-check seam (`OrganizationOffice.feeds_check`, #2239) are the
    Build-1 wiring that *calls* this; where common value accrues is handled by
    `accrue_holding_materials` (below). All magnitudes PLACEHOLDER.
  - **Material value buckets + bulk requirements** (`world.items.gems.buckets`, Build 0b slice 5,
    generalized #2540 slice 2) — `MaterialBucket` (`world.items.materials_models`; a crafter's
    material value per category — a `MaterialCategory` — never instanced; the type-blind bulk
    source, originally gem-only). `credit_materials` / `spend_materials` / `material_value`
    (canonical mutate-then-save, not `F()`; `InsufficientMaterialStock` — kept distinct from the
    pre-existing instance-consumption `InsufficientMaterials`).
    `CraftingMaterialRequirement.required_value` (nullable, category-only, DB-constrained) is a
    "N value of {category}" **bulk** requirement: `stage_and_assert_affordable` splits value reqs
    from instance reqs — instance reqs go through `gather_consumable_pks` (0a, unchanged), value
    reqs are aggregated per category and checked against the crafter's buckets (via
    `StagedCost.bucket_spends`); `consume_cost` spends them. Named Rare-Find stones are never
    auto-consumed — only this fungible bulk source is. This is the "gem-covered table, don't care
    which" path; the primary use is still adornment. Common value crediting from mining is the
    Build-1 cron's job.
  - **Holding material accrual** (`world.items.materials_production.accrue_holding_materials`,
    #2540 slice 2 Task 2 — replaces the deleted, gem-mine-only `accrue_mine_cycle`) — the weekly
    cycle for a holding, iterating *every* `HoldingMaterialSource` row it carries (not just one).
    A `GEM_MINE` source (`quality` + `material_category`) still calls `roll_gem_haul` (`gems.mining`,
    unchanged; `minister_bonus` passthrough kept for the #2239 seam); a `BULK` source produces flat
    `quality * BULK_YIELD_PER_QUALITY` (new constant, PLACEHOLDER 100, `world.items.constants`) with
    no rare finds. Both credit **uncollected** pools on the holding's `OrgIncomeStream` — common
    value into `StreamMaterialPool` (`world.items.materials_models`, per stream/category; the gem
    analogue of `OrgIncomeStream.uncollected_pool`), GEM_MINE Rare Finds into `PendingRareFind` (a
    loose stone awaiting collection). Returns `MaterialHaul` (`common_value_by_category:
    list[tuple[MaterialCategory, int]]`, `rare_finds: list[ItemInstance]`) — the multi-source
    generalization of `GemHaul`. "Lumped with tax collection": both ride the **same** active
    `collect_org_income` dispatch (same band/graft/catastrophe loss) into the house's stock — see
    Mine collection (below). A holding with no income stream accrues nothing. Lives in a new
    top-level `world.items.materials_production` module, not `gems.mining` — it is no longer
    gem-specific, and only imports the gem roller as one of its two source-kind branches.
  - **Mine collection** (`world.items.gems.collection`, Build 0b domain-cron collection) —
    `collect_org_income` gathers the org's pending gems alongside coin and applies the *same* Tax
    Collection band + graft + catastrophe. `collect_org_materials` (renamed from
    `collect_org_gems`, #2540 slice 2) zeros the pools, credits net common value to the shared
    **`OrgMaterialStock`** (`world.items.materials_models`; `organization`+`material_category`;
    `credit_org_materials`, the stock members craft from), delivers
    `floor(count × band × (1−graft))` of the stones to the collector, and destroys the rest
    (catastrophe loses all). `org_has_pending_materials` (renamed from `org_has_pending_gems`)
    widens the empty-gate so a gems-but-no-coin mine still collects. `CollectionResult`
    (`world.currency.types`) grew `material_value_landed` (renamed from `gem_value_landed`) /
    `landed_by_category` / `stones_delivered` / `stones_lost`. Currency reaches this via a lazy
    import (FK direction preserved — currency stays free of an items dependency at load).
    Remaining sub-slices: only the minister seam
    (#2239) — the `game_clock` scheduling shipped (#2610) and the crafting draw itself shipped
    (see the currency section's `distribute_material_allowance`).
  - **Personal material sale** (`world.items.market.services.sell_materials`,
    `@transaction.atomic`, #2540 slice 2) — sells `amount` of a `CharacterSheet`'s
    `MaterialBucket` value for one category at the market's PLACEHOLDER
    `MATERIAL_SALE_RATE_PCT` (40%), coppers minted straight to the seller's purse
    (`sell_to_fence`'s mint-to-purse convention). Apostate's frictionless ruling (ADR-0234):
    unlike the fence (#2862), needs no stall, no NPC, no location gate — bulk material is
    abstract bucket value, not a physical good to haggle over. The coin computation happens
    BEFORE the bucket is touched, so a sale too small to round up to a single copper is refused
    outright rather than debiting the bucket for nothing; raises `MarketServiceError` (wrapping
    `InsufficientMaterialStock`) when the bucket falls short — nothing moves in that case.
    Surfaced via `SellMaterialsAction` (`actions.definitions.market`, key `sell_materials`,
    kwargs `material_category_id`/`amount`). Both this and `sell_to_fence` are
    `@transaction.atomic` (fix commit `32b1a8d37` — a mid-sale exception previously left a
    spent-but-unpaid seller). The org-level auto-sell sibling
    (`currency.services.auto_sell_excess_materials`) is documented in the currency section.
- **Org vault (#2540 Layer 4, `org_vault_models.py` + `services/org_vault.py`):** logical org
  custody of items — the ratified "model B with model D's access surface". `OrganizationVault`
  (OneToOne org, get-or-create; `withdraw_rank_max`, the `spend_rank_max` twin),
  `VaultHolding` (vault + OneToOne `ItemInstance` + `deposited_by`/`deposited_at`; created on
  deposit, deleted on withdrawal), `OrgVaultEvent` (append-only audit — the `CurrencyTransfer`
  analogue for items; how embezzlement gets discovered). Services (sole mutators):
  `get_or_create_org_vault`, `can_access_vault` (active membership at tier <=
  `withdraw_rank_max`), `deposit_item_to_vault` (any active member, must hold the item; holder
  goes null + `game_object` dematerialized — custody is the row, not the prop),
  `withdraw_item_from_vault` (rank-gated; `to_persona` directs the item elsewhere — the
  VAULT_ITEM boon shape, its first live caller). **Collection return leg (#2540 ruling
  2026-07-20):** `VaultTransit` — collection is a mission; `collect_org_gems` mints one
  in-transit custody row per stone delivered to the collector's hands, and
  `resolve_vault_transit(organization, carrier_persona, keep_item_ids)` completes the mission:
  unlisted items resolve DEPOSITED (→ `VaultHolding` + audited event, reason "collection
  deposit"), `keep_item_ids` resolve KEPT (embezzled) behind the **double gate** —
  `can_embezzle_from` requires at least one *piloted* org leader whose dedicated
  `embezzlement` consent category (seeded under `antagonism`) admits the carrier (strict-all
  across piloted heads, PLACEHOLDER semantic), AND the carrier's explicit keep list is the
  opt-in. A KEPT stone stays in the carrier's hands and books NO vault event — the resolved
  transit row is the staff-side record; the tally-vs-deposits gap is the in-world discovery
  hook. In-transit loss deliberately not built (loss lives in the collection roll). **The
  WHERE gate is now wired** (#2540 economy wiring — supersedes the earlier follow-up note):
  `VaultDepositAction`/`VaultWithdrawAction` (`actions/definitions/org_vault.py`, keys
  `vault_deposit`/`vault_withdraw`, REST int kwargs), **`TreasuryWithdrawAction`** (key
  `treasury_withdraw` — draws coppers from the org treasury via
  `currency.withdraw_from_treasury`; the CONTROLLER RULING extending the same access
  surface to coin, not just items, cites the Layer 4 access-surface ruling on #2540), and
  **`DeliverCollectionAction`** (key `deliver_collection`, "Deliver the Take" — the
  collection mission's return leg over `resolve_vault_transit`; `keep_item_ids` is the
  carrier's embezzlement opt-in, subset-validated against the actor's own open
  `VaultTransit` rows and resolved atomically) are ALL performable only where an active
  **BANK** `RoomFeatureServiceStrategy` feature stands (a bank room on grid or an
  owner-installed bank-access decor feature — the ratified access surface; reachability-only
  handler in `room_features`, COMMAND_CENTER's shape; seeded via `ensure_bank_kind()`,
  `world/room_features/seeds.py`). Distinct from the physical room-feature
  VAULT (#2179), which secures loose items in a room. **Weekly material accrual is wired**:
  `run_weekly_economy`'s `materials` phase (`_weekly_mine_accrual`, renamed key #2540 Task 2) runs
  one `accrue_holding_materials` per holding with a `HoldingMaterialSource` row (#2540 slice 2) —
  haul amasses uncollected per ADR-0081; only an active collection delivers it.
- **New fields on `ItemTemplate` (Spec D PR1):** `facet_capacity` (max attachable facets,
  default 0), `gear_archetype` (CharField, `GearArchetype` enum choices)
- **New field on `ItemTemplate` (#1024):** `on_use_target_kind` (nullable `TargetKind` CharField)
  — null = self-use only; CHARACTER/ITEM/ROOM = requires an external target of that kind (validated
  by `OnUseTargetPrerequisite` before `use_item` is called); PERSONA and unknown values fail closed
- **New fields on `ItemTemplate` (touchstones, #707):** `tied_resonance` (nullable FK to
  `magic.Resonance`) + `resonance_tier` (nullable FK to `magic.ResonanceTier`) — mark a template
  as a resonance-tied touchstone; `CheckConstraint` requires both set together or both null
- **New fields on `ItemInstance` (touchstone attunement, #707):** `attuned_to_character_sheet`
  (nullable FK to CharacterSheet, `SET_NULL`) + `attuned_at` (nullable DateTimeField) — set by
  `world.magic.services.touchstones.attune_touchstone()`
- **Enums:** `BodyRegion` (17 body regions), `EquipmentLayer` (skin/under/base/over/outer/
  accessory), `OwnershipEventType` (created/given/stolen/transferred/activated/consumed),
  `GearArchetype`; `PROVENANCE_EVENT_TYPES` frozenset (GIVEN/STOLEN/TRANSFERRED — transfer
  provenance used by the lore-critical predicate); `CraftingRecipeKind` (FACET_ATTACH,
  STYLE_ATTACH, ITEM_CREATE — the mint pipeline, #2211); `CostConsumption` (NONE, PARTIAL,
  FULL); `ContainerAccessPolicy` (#1909 —
  `OPEN` / `FRIENDS` / `OWNER_ONLY`, who may take contents out of a container; steal
  bypasses it with consequences); `StyleAudacity` (#2029 — UNDERSTATED/EXPRESSIVE/BOLD/
  OUTRAGEOUS ordinal tier on `Style`)
- **New field on `ItemInstance` (#1909):** `access_policy` (`ContainerAccessPolicy`, default
  `OPEN`) — container-only; non-containers ignore it. Set via
  `flows.service_functions.inventory.set_container_policy` (owner-only).
- **Ownership + container-access gate (#1909):** a plain `pick_up`/`take_out` on a
  someone-else's-owned room item, or on an item in a container whose `access_policy` bars
  the taker, raises `OwnedByAnother` / `ContainerAccessDenied`. The single test —
  `flows.service_functions.inventory.take_requires_steal(taker_sheet, item_instance) -> bool`
  — decides room-item ownership directly and container-item access via the container's
  policy (a container item owned by the container's owner still passes on an `OPEN`
  policy — sanctioned borrowing). Sheet-less actors (GM/staff/companion tooling) always
  return `False` (legacy free-take — theft consequences are sheet-anchored). `steal`
  (below) is the deliberate bypass.
- **Steal (#1909):** `flows.service_functions.inventory.steal(character, item)` — takes an
  item that plain take refuses, transferring ownership (`OwnershipEvent(STOLEN)`, never
  destroyed) and birthing a crime-tagged, concealed `LegendEntry` deed
  (`world.societies.services.create_solo_deed`, `concealed=True` rolls Stealth to shed
  witnesses, #1824; `scene=None` when no active scene — the theft spreads cold).
  `steal_permitted(taker_sheet, item_instance) -> bool` is the target-side-only
  availability predicate (visibility = eligibility): requires `take_requires_steal` first,
  then NPC-owned holdings (owner sheet has no active `RosterTenure`) are always
  antagonism-allowed; player-owned holdings gate on `world.consent.services
  .consent_blocks_targeting(category=theft_category())` (default-deny — opt-in required).
  Lazy rows: `_theft_crime_kind()` (`justice.CrimeKind`, slug `"theft"`),
  `_theft_source_type()` (`societies.LegendSourceType`, name `"Crime"`).
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
    - `gather_consumable_pks(*, available, requirements) -> list[tuple[ItemInstance, int]]` —
      validates inventory, returns (instance, amount) allocations to consume; also used by the
      ritual path. Matches a requirement by its `material_category_id` (any member template)
      when set, else by `item_template_id` (Build 0a; ritual requirements have no category
      and their caller pre-filters to `item_template_id`, so that path is unchanged)
    - `consume_materials(allocations) -> None`
    - `meets_quality_tier(inst, requirement) -> bool`
  - **Narrative acquisition** (`world.items.services.narrative_grants`, #707 — no shop/
    merchant system exists anywhere in this codebase):
    - `grant_touchstone_item_to_character(*, character_sheet, template, granted_by=None)
      -> ItemInstance` — creates one `ItemInstance` of `template`, held by
      `character_sheet`. `granted_by` is audit-only, never surfaced to the recipient
      (mirrors `award_kudos`). Called by `GrantItemAction` (`registry_key="grant_item"`,
      gated on `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`, staff bypass preserved, #2117)
      via telnet `CmdGrantItem` (`grant_item <character>=<item template name>`,
      `src/commands/grant_item.py`) and by the Mission `DeedRewardSink.ITEM` reward sink
      (`world.missions.services.rewards._route_line`, `IMMEDIATE`-dispatched, not queued)
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
- **Serializer fields (#1909):** `ItemInstanceReadSerializer` additionally exposes
  `game_object_id`, `access_policy`, `is_currency_instrument` (has a
  `CurrencyInstrumentDetails` row — drives the Deposit affordance), and `can_steal`
  (`SerializerMethodField` wrapping `steal_permitted` for the requesting viewer — drives
  the Steal affordance). Frontend wiring: Drop/Give/Put-in/Deposit/Secure/Steal/Withdraw.
- **`UseItemAction`** (`key="use_item"`, `src/actions/definitions/items.py`) — action-layer entry
  point routing both telnet and web through prerequisites + `use_item`. kwargs: `item` (held
  instance), optional `target` (validated by `OnUseTargetPrerequisite` against
  `on_use_target_kind`). Visibility gate routes through the `can_perceive` seam (#1225): same-location
  plus the `Concealed`-condition producer contract (`ConditionCategory.conceals_from_perception`,
  per-observer detection via `ConditionInstance.detected_by`) — see ADR-0083 for the OOC
  unseen-observer transparency guarantee this composes with. Stealth witness-reduction (#1464) and
  disguise-piercing (forms) remain deferred automated producers of concealment/detection.
  Telnet: `CmdUse` (`use <item>` / `use <item> on <target>`, alias `apply`).
- **Exceptions:** `FacetAlreadyAttached`, `FacetCapacityExceeded`, `StyleAlreadyAttached`,
  `StyleCapacityExceeded`, `SlotConflict`, `SlotIncompatible`, `ItemNotUsable`,
  `NoChargesRemaining`, `CraftingNotConfigured`, `CraftingCostUnaffordable`,
  `OwnedByAnother` (#1909 — plain take refused a someone-else's-owned room item),
  `ContainerAccessDenied` (#1909 — container's `access_policy` bars this taker),
  `TheftNotPermitted` (#1909 — `steal` refused: no ownership gate to bypass, or consent
  denies it) — all in `world.items.exceptions`
- **Steal + policy Actions (#1909, `actions/definitions/currency.py`):** `StealAction`
  (key `"steal"`) — gated by `CanStealPrerequisite`, which delegates to `steal_permitted`
  (the same predicate `steal` re-checks at execution time); `SetContainerPolicyAction`
  (`"set_container_policy"`) — owner-only, wraps `set_container_policy`. Telnet:
  `CmdSteal` (`steal <item>` / `steal <item> from <container>`, `commands/currency.py`),
  `CmdSecure` (`secure <container>=<open|friends|owner_only>`).
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
- **Telnet (#1866, gem cut #3006 Task 3):** `CmdCraft` (`craft`, `commands/crafting.py`) drives
  facet/style attach-detach + gem cut (`craft cut item=<id>`) through
  `AttachFacetAction`/`DetachFacetAction`/`AttachStyleAction`/`CutGemAction`
  (`actions/definitions/crafting.py`); `CmdOutfit` (`outfit`, `commands/outfit.py`)
  drives outfit CRUD through `SaveOutfitAction`/`RenameOutfitAction`/
  `DeleteOutfitAction`/`AddOutfitSlotAction`/`RemoveOutfitSlotAction`
  (`actions/definitions/outfits.py`) — the same Actions the `ItemFacetViewSet`/
  `ItemStyleCraftViewSet`/`OutfitViewSet`/`OutfitSlotViewSet` now dispatch through.
- **Template-authored default Properties (#2503):** `ItemTemplateProperty`
  (`world/items/models.py`, migration `0041`) declares which `mechanics.Property` rows a
  template's instances carry by default (e.g. a Torch template → `flammable`). Applied at the
  materialization chokepoint — `apply_template_properties(obj, item_template)`
  (`world/items/services/materialize.py`), called from `_create_item_object_db`, the single
  place any `ItemInstance` gains a physical `ObjectDB` — so every materialization path
  (character inventory, GM-staged room prop) upserts the same `mechanics.ObjectProperty` rows
  a granted-technique Property would use. `stage_prop(item_template, room)`
  (`world.items.services.staging`) is the GM stage-prop wrapper over
  `materialize_item_game_object_in_room` — see the Actions section's `StagePropAction`.
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
  ritual material consumption via shared `gather_consumable_pks`; touchstone
  `tied_resonance`/`resonance_tier` FKs into `magic.Resonance`/`ResonanceTier`, #707),
  covenants (gear archetype compatibility), checks (`perform_check` + consequence pool),
  missions (`DeedRewardSink.ITEM` reward line grants via `grant_touchstone_item_to_character`)
- **Source:** `src/world/items/`
- **Details:** [items.md](items.md)

### Covenants
Magically-empowered group oaths with roles, gear compatibility, a per-covenant rank
ladder, a Mentor's Vow bond system for level-mismatched parties (#1165), and a Covenant
of the Court type for master/servant pacts (#1589).

**Standing invariant:** `CovenantRole` = combat power (SWORD/SHIELD/CROWN blend
weights, speed_rank, Thread pulls). `CovenantRank` = administrative authority
(invite/kick/manage). These two axes are orthogonal — never re-merge them.

- **Models:**
  - `CharacterCovenantRole` — per-character membership row; `left_at IS NULL` =
    currently active. Fields include `covenant` FK, `covenant_role` FK, `engaged`
    boolean, `rank` FK → `CovenantRank`, `is_secondary` boolean (#2641, ADR-0159 —
    marks an engaged SECONDARY vow; at most one engaged PRIMARY + one engaged
    SECONDARY per (character_sheet, covenant type); chassis layers 1/3 never read
    secondary memberships, Layers 2/4 scale a secondary's contribution by
    `SecondaryVowConfig.potency_tenths`; see `docs/systems/covenants.md`'s
    "Secondary vows" section for the full split), `standing`
    (`MembershipStanding.CORE`/`MINOR`, #2992, ADR-0213 — MINOR is DURANCE-only,
    engages the secondary lane only, may engage it without an engaged primary
    (a waiver on the #2641 rule), and bypasses `add_member`'s level-band gate;
    see `docs/systems/covenants.md`'s "Minor covenant membership" section).
  - `SecondaryVowConfig` (#2641) — singleton (pk=1) potency dial,
    `potency_tenths` (default 6 = ×0.6), lazy-created via
    `secondary_vow_config()` (`world.covenants.services`).
  - `CovenantRole.sword_weight`/`.shield_weight`/`.crown_weight` (#2529, ADR-0149) —
    Decimal weights forming the combat-identity blend; stored on primary roles only
    (sum to 1), sub-roles delegate via `blend_weight_for(axis) -> Decimal`. Replaced
    the single-value `archetype` enum. Lore-repo content (`NaturalKeyMixin`,
    `CONTENT_MODELS`).
  - `CovenantRole` sub-role fields — `parent_role` (self-FK), `resonance` (FK →
    `magic.Resonance`), `unlock_thread_level` (PositiveInt, 0 for primary / >0 for sub-roles),
    `discovery_achievement` (FK → `achievements.Achievement`, nullable, sub-roles only),
    `codex_entry` (FK → `codex.CodexEntry`, nullable, sub-roles only).
  - `CovenantRoleActionScaling` (#2529, ADR-0149; replaced `ArchetypeActionScaling`) —
    one row per `(covenant_role, action_key)` with `thread_level_multiplier`. Read by
    `covenant_role_action_scaling_bonus(character, action_key)`, anchor-role
    normalized. Lore-repo content.
  - `CovenantRoleTechniqueSpecialty` (#2443, ADR-0149's 2026-07-20 amendment; **Layer 2**
    of the vow-power model) — one row per `(covenant_role, function)` keyed on
    `magic.TechniqueFunction`, `multiplier_tenths` (default 10 = ×1.0). Valid on both
    primary roles AND sub-roles — sub-role rows ADD to the parent's (unlike the blend
    weights/action-scaling anchor-only rule). Read by
    `covenant_role_specialty_power_term` (`world.magic.services.power_terms`).
    Lore-repo content.
  - `VowSituationalPerk` / `VowSituationalPerkSituation` / `VowSituationalPerkRung`
    (#2536 slices 1-3, ADR-0151/ADR-0152/ADR-0153; **Layer 4** of the vow-power model — "the
    point of vows", now COMPLETE) — deterministic, situational bonuses. `VowSituationalPerk` (NK
    `(covenant_role, name)`): `beneficiary` (SELF/COVENANT_ALLIES/WHOLE_GROUP), `effect_kind`
    (all four values live: POWER_BONUS/CHECK_BONUS slice 1; TIER_FLOOR/BOTCH_IMMUNITY slice 2),
    `magnitude_tenths` (no negatives — structural, `PositiveIntegerField`), `announce_template`,
    optional `check_type` scope, optional `floor_success_level` (SmallInt, canonical −10..+10
    scale — TIER_FLOOR-only, `clean()`-enforced both directions, ADR-0152). Slice 3 adds three
    scope columns (ADR-0153): `mission_category`/`mission_template` (FKs, CHECK_BONUS-only) and
    `battle_action_kind` (`BattleActionKind` CharField, CHECK_BONUS/POWER_BONUS only) — every
    non-empty scope on a row must match (AND), narrowing WHEN a fired perk applies (distinct
    from a `Situation`, which asks whether the game state holds at all).
    `VowSituationalPerkSituation` (AND-composed situation attachments) + `VowSituationalPerkRung`
    (cumulative escalation tiers — rung N requires rungs 1..N-1 too, highest qualifying rung's
    magnitude replaces the base). Both inherit `SituationRequirementMixin` (#2623, ADR-0154) —
    four typed, nullable/blank parameter columns (Situation Parameters): `threshold_percent`
    (0-100), `count_threshold`, `affinity` (`AffinityType` axis), `origin_side`
    (`SituationOriginSide.OURS`/`THEIRS`, blank = side-blind). No JSON (ADR-0007). Which
    situation reads/requires which params is `SITUATION_PARAM_SPECS`
    (`world.covenants.perks.constants`); the mixin's `clean()` enforces both directions. All
    lore-repo content. Situations are drawn from `world.covenants.perks.constants.Situation`, a
    code-defined library (15 values as of #2646: slice 1's 9 plus `CHAMPION_DUEL`,
    `COMBAT_OPENED_FROM_PARLEY`, `AMBUSH_UNDERWAY`, `ALLY_INTERCEPTED_FOR_ME`, and
    `ATTACKER_AFFINITY` — the Abyssal-only attacker-typing situation renamed and parameterized to
    all three `AffinityType` axes by #2623 — plus `ON_CHOSEN_GROUND` (#2646)) with a registered
    evaluator per value
    (`world.covenants.perks.evaluators.SITUATION_EVALUATORS`) — attaching a situation to a perk
    (and tuning its params) is content; adding a new situation to the library is code.
    `world.covenants.perks.services
    .applicable_perks(subject, *, effect_kind, resolution, target, attacker=None)` is the
    beneficiary evaluation point every delivery seam calls (`effect_kind` accepts a single kind
    or a `tuple[str, ...]`, slice 2 — same fixed query ceiling; `attacker`, slice 3, threads the
    defense-side attacking entity through). `perk_scope_matches(perk, ctx, *,
    mission_category_ids=None)` (slice 3) filters a fired set by the three scope columns above.
    `announce_fired_perks` is the dual-dispatch (WS + a direct telnet `location.msg_contents()`
    call, NOT `message_location`) presentation-contract seam for LIVE firings;
    `dormant_perk_firings`/`announce_dormant_perks` (slice 3, ruling 2 — "the loud OFF state")
    deliver `"your vow lies dormant — {perk.name} would have answered here"` to the HOLDER
    ALONE (WHISPER Interaction + telnet `.msg()`, never the room) when a DISENGAGED role would
    have fired — see `docs/systems/covenants.md`'s "Court/Battle scoping + defense-side seam"
    and "Dormant-vow messaging" sections and ADR-0151/ADR-0152/ADR-0153 for the full design
    (registry pattern, query ceiling, why `broadcast_action_outcome` alone was insufficient for
    telnet parity). Delivery: `POWER_BONUS` via `vow_situational_power_term`
    (`world.magic.services.power_terms`, see the Magic section above); `CHECK_BONUS` via
    `perform_check`'s optional `situation_ctx` parameter (`world.checks.services`) — both
    thread-scaled and (slice 3) scope-filtered. `TIER_FLOOR`/`BOTCH_IMMUNITY` also ride
    `perform_check`, via `_apply_outcome_guarantees` AFTER the outcome is determined
    (rolled or test-rig forced) — ABSOLUTE, never thread-scaled, ungated; `TIER_FLOOR` guarantees
    `success_level >= floor_success_level`, `BOTCH_IMMUNITY` downgrades a botch
    (`success_level <= world.checks.constants.BOTCH_SUCCESS_LEVEL_MAX`) to the least-bad
    non-botch outcome; announces only when a guarantee actually altered the outcome. Slice 3
    (ADR-0153) threads `situation_ctx` into all six mission `perform_check` sites
    (`world.missions.services._situation.mission_situation_ctx`) and every Battle warfare-roll
    check/cast (`world.battles.resolution._battle_situation_ctx`), and threads
    `SituationContext(attacker=opponent_action.opponent, ...)` into the defender's
    `perform_check` in `world.combat.services.resolve_npc_attack` — the defense-side seam, the
    only defense-check site carrying `attacker` in v1.
  - `InsightTableEntry` (#2645, NK `["name"]`, `CONTENT_MODELS`) — the Know need's
    once-per-fight ace: a curated random table of large, narrowly-scoped, ONE-ROUND
    effects (never instant-win — that ceiling belongs to the audere arc; enforced
    editorially by curation, not an engine check). Fields: `prose` (announced reading,
    `{caster}`/`{target}` placeholders), `condition` FK → `conditions.ConditionTemplate`
    (PROTECT — author a one-round `default_duration_value` on the condition itself),
    `target_kind` (`InsightTargetKind`: SELF/ALLY/TEAM), `weight`
    (`PositiveSmallIntegerField`, default 1 — weighted-random draw), `is_active`.
    Lore-repo content — **never seeded in arxii**; the first dozen entries are a
    companion lore commit. `CovenantRole.grants_insight` (BooleanField, riding rule —
    a sub-role without its own grant rides an engaged parent's) is the rider flag.
    `CombatParticipant.insight_used` (`world.combat.models`) is the per-encounter
    once-only stamp — a per-encounter row needs no reset machinery. Rider service:
    `world.covenants.insight.maybe_produce_insight(caster_sheet, technique,
    resolution_participant) -> bool` — fires when the caster's engaged
    `grants_insight` role's technique cast carries the PERCEPTION
    `magic.TechniqueFunctionTag` and the participant hasn't used their Insight this
    encounter; draws a weighted-random active entry, resolves targets (ALLY → the
    cast's declared `CombatRoundAction.focused_ally_target`, falling back to the
    caster; TEAM → every ACTIVE `CombatParticipant` in the encounter; SELF → the
    caster), applies the entry's condition via `conditions.services.apply_condition`
    (`source_character=caster`), and announces the entry's prose on BOTH channels
    (`combat.interaction_services.broadcast_action_outcome` for the WS payload +
    `encounter.room.msg_contents` for telnet parity, mirroring
    `world.combat.escalation`'s room-wide surge narration). Hooked into
    `world.combat.services._resolve_pc_action` right after a focused technique cast
    resolves (`_maybe_produce_insight_for_cast`, best-effort/failure-isolated like the
    sibling `_maybe_suggest_entrance_dramatic_moment`). Distinct in weight from the
    light "Look out!" callout (#2637): the callout is frequent/small/names-no-counter,
    the Insight is rare/large/specific.
  - `GearArchetypeCompatibility` — existence-only join: which `CovenantRole`s are
    compatible with which `GearArchetype` values (read-only authored content)
  - `CovenantRoleBonus` — authored config: one row per
    `(CovenantRole, ModifierTarget)` with `bonus_per_level` SmallInt.
    `role_base_bonus_for_target(role, target, char_level)` returns
    `char_level × bonus_per_level`; no row → 0. Lore-repo content (#2533,
    `NaturalKeyMixin`, `CONTENT_MODELS`).
  - `DefenseStyle` (`TextChoices`, #2533, ADR-0149 Layer 3) — `GEAR_SOAK`/
    `EVASION`/`BARRIER`, how a covenant vow defends. Code-defined vocabulary
    (Layer 4's situational perks, #2536, key on these labels).
  - `CovenantRoleDefenseProfile` (#2533) — one row per `CovenantRole` (OneToOne,
    `related_name="defense_profile"`): `style` (`DefenseStyle`),
    `gear_additive_tenths` (default 10 = fully additive). Lore-repo content
    (`NaturalKeyMixin` NK `["covenant_role"]`, `CONTENT_MODELS`). Read via
    `gear_additive_fraction(character)` — see "Combat seams" below.
  - `CovenantRank` — per-covenant administrative authority tier.
    Fields: `covenant` FK, `name`, `tier` (1 = top authority), `description`,
    `can_invite`, `can_kick`, `can_manage_ranks`, `can_lead_rituals` (may lead
    this covenant's group rituals), `can_request_gm` (#2119 — may post an open
    ask for a GM via `GroupStoryRequest`; deliberately separate from `can_invite`
    — petitioning an outside GM is a different authority from admitting members).
    Unique `(covenant, tier)` and `(covenant, name)`.
  - **`Covenant.leader`** (#1589) — FK → `character_sheets.CharacterSheet`
    (`null=True`, `on_delete=SET_NULL`). Required for COURT covenants, forbidden for others.
    Identifies the master character.
  - **`CourtPact`** (#1589) — per-(Court covenant, servant) sworn-fealty bond. Fields:
    `covenant` FK (PROTECT), `servant_sheet` FK → `CharacterSheet` (PROTECT),
    `granted_pull_cap` (PositiveSmallIntegerField — master-set thread-pull ceiling,
    now negotiable post-swearing, #1718 — see "Court services" below),
    `sworn_at` (auto), `released_at` (null = active). Partial-unique on
    `(covenant, servant_sheet)` when active. Custom queryset: `.active()`.
  - **`Covenant.court_grant_role`** (#1718) — FK → `npc_services.NPCRole`
    (`null=True`, `on_delete=SET_NULL`), auto-provisioned by
    `ensure_court_grant_role`; carries the Court's `OfferKind.COURT_GRANT`
    petition offer.
  - **`CourtGrantConfig`** (pk=1 singleton, lazy get-or-created via
    `get_court_grant_config()`, #1718) — `base_headroom`, `affection_divisor`,
    `mission_divisor`, `emergency_draw_max_bonus` (max the emergency draw may
    exceed the ceiling by), `debt_repay_affection_divisor`,
    `debt_repay_mission_divisor`, `petition_failure_escalation_threshold`,
    plus nullable `petition_check_type` / `escalation_consequence_pool` FKs.
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
  - `add_member(*, covenant, character_sheet, role, standing=CORE) -> CharacterCovenantRole`
    (#2992) — MINOR standing bypasses the level-band gate.
  - `assign_covenant_role(sheet, role) -> CharacterCovenantRole`
  - `end_covenant_role(role_assignment) -> None`
  - `swear_core(*, membership) -> None` / `step_back_to_minor(*, membership) -> None`
    (#2992) — MINOR↔CORE standing transitions; `swear_core` re-runs the level-band
    gate, `step_back_to_minor` un-engages a primary-lane engagement first.
  - `leave_covenant(*, membership) -> None` / `kick_member(*, target, actor) -> None` —
    Covenants never dissolve from attrition (#2992, ADR-0042 amendment — the covenant
    persists at any active-member count, including zero); `kick_member` raises
    `CannotKickEqualOrHigherRankError`, `NotAuthorizedToKickError`, `CannotKickSelfError`
  - `is_gear_compatible(role, archetype) -> bool`
  - `role_base_bonus_for_target(role, target, char_level) -> int` (in
    `world.mechanics.services`)
  - `covenant_role_action_scaling_bonus(character, action_key) -> float` (#2529,
    ADR-0149; replaces `archetype_action_scaling_bonus`) — sums `thread_level ×
    multiplier` across engaged roles' `CovenantRoleActionScaling` rows, anchor-role
    normalized
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
    - `can_request_gm_for_covenant(covenant, *, character_sheet=None, account=None) -> bool`
      (#2119) — same shape as `can_invite_to_covenant` but filters
      `rank__can_request_gm=True`; gates `RequestGMForCovenantAction` in
      `world.stories.services.tables.request_gm_for_covenant`.
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
      covenant (for non-COURT types); raises `CourtGulfViolationError` if the servant's
      power tier is not strictly below the leader's (for COURT). Called by `add_member`;
      `create_covenant` is ungated.
    - `establish_mentor_bond_via_session(*, session) -> MentorBond` — service function
      wired to `MentorsVowRitualFactory` (consensual BILATERAL_SERVICE ritual).
  - **Court services** (`world.covenants.services`, #1589):
    - `swear_court_pact(*, covenant, servant_sheet, granted_pull_cap) -> CourtPact` —
      creates an active pact; raises `CourtPactExistsError` if one already exists.
    - `release_court_pact(*, pact) -> None` — sets `released_at = now()`.
    - `active_court_pact_for(*, covenant, servant_sheet) -> CourtPact | None`
  - **Court grant negotiation** (`world.covenants.court_grant`, #1718):
    - `court_grant_ceiling(*, covenant, servant_sheet) -> int` — max grant the
      master is currently willing to formalize; reads affection + completed
      Court missions, nets against `outstanding_debt(...)`, floored at 0.
    - `raise_court_pact_grant(*, pact, new_cap) -> CourtPact` — strictly
      monotonic; raises `CourtGrantNotMonotonicError` on any attempted decrease
      (equal is a no-op).
    - `ensure_court_grant_role(covenant) -> NPCRole` — idempotent,
      `@transaction.atomic` with a `select_for_update()` re-fetch of the
      `Covenant` row (race-safe); auto-provisions the Court's
      `OfferKind.COURT_GRANT` petition offer the first time any servant
      negotiates.
    - `completed_court_mission_count(*, character_sheet, covenant) -> int`
    - Emergency thread-bond draw: not a service here — see the
      "Grant negotiation" section of `docs/systems/covenants.md` for the
      `beseech=` token / `_resolve_emergency_draw` seam
      (`world.combat.pull_helpers`).
  - **Court engagement** (`world.covenants.court_missions`, #1589):
    - `has_active_court_mission(*, character_sheet, covenant) -> bool` — True iff
      the character participates in an ACTIVE `MissionInstance` whose
      `source_offer.role.faction_affiliation_id == covenant.organization_id`. Single
      `.exists()` query; lazy-imports `world.missions` to avoid circular deps.
  - **Court gulf helper** (`world.covenants.power_tier`, #1589):
    - `power_tier_for_level(level: int) -> int` — maps levels 1–5 → tier 1,
      6–10 → tier 2, 11–15 → tier 3, etc. (`ceil(level / TIER_ONE_MAX_LEVEL)`).
      Used by the COURT gulf check in `assert_membership_level_allowed`.
  - **The Sphinx of Black Quartz** (`world.covenants.sphinx`, #2640, ADR-0157) — read-only
    vow-suitability oracle, never a gate. `judge_vow(sheet, role) -> SphinxVerdict`
    re-runs `covenant_role_specialty_power_term`'s kit∩demand join as a three-tier report
    (`SphinxTier.TAKES`/`DORMANT`/`NOT_YET`, `world.covenants.constants`): demand =
    the role's (+ parent's, for a sub-role) `CovenantRoleTechniqueSpecialty` functions
    UNION the creator-functions its SELF-beneficiary `VowSituationalPerk`
    situations/rungs require (via the new code-defined
    `SITUATION_CREATOR_FUNCTIONS: dict[str, frozenset[str]]`,
    `world.covenants.perks.constants` — the `TARGET_DISTRACTED`/`TARGET_SWAYED_BY_ALLY`
    provenance mapping run in reverse; a situation absent from it demands nothing).
    `SphinxVerdict.shopping_list` — up to 3 learnable techniques per uncovered function
    (gift-ownership — `learn_technique`'s own gate; #2700/ADR-0167). `audit_vow_coverage()
    -> list[SphinxCoverageRow]` — the staff instrument (built first per the spec): every
    active anchor role × every active Tradition, specialty-demand-only coverage
    (`"full"`/`"partial"`/`"none"`), rendered at the staff-only `_sphinx/` admin page
    (`admin_sphinx_audit`, linked from Game Setup). Player surface:
    `GET /api/covenants/roles/sphinx/?role=<id-or-slug>` (self-character only) and the
    `sphinx <vow name>` telnet command (`commands/sphinx.py`) — both call `judge_vow`
    directly, no parallel logic.
- **Combat seams (#985, #1174, #1165, #2533):** `apply_equipped_armor_soak` splits worn armor into
  role-compatible vs incompatible buckets; compatible soak is scaled once by
  `gear_additive_fraction(character)` (`world.covenants.services`, #2533 — MAX
  `CovenantRoleDefenseProfile.gear_additive_tenths` fraction across engaged roles,
  `1` with no profile); final soak = `compat_physical +
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
- **Covenant Treasury (#2992):** `world.covenants.treasury` —
  `covenant_treasury(covenant) -> OrganizationTreasury` (lazy-created on the
  covenant's backing `Organization`); `deposit_covenant_funds(*, membership, amount,
  reason="") -> CurrencyTransfer` (any active member, core or minor);
  `withdraw_covenant_funds(*, membership, amount, reason="") -> CurrencyTransfer`
  (rank-gated: `membership.rank.tier <= treasury.spend_rank_max`, default 1 =
  Founder tier). Covenant treasury authority derives from `CharacterCovenantRole`,
  not `OrganizationMembership`. See `docs/systems/covenants.md`'s "Covenant
  Treasury" section.
- **Enums:** `MentorBondAdjusted` (`MENTOR`/`SIDEKICK` — which party is adjusted);
  `MembershipStanding` (`CORE`/`MINOR`, #2992)
- **Exceptions:** `world.covenants.exceptions` —
  `CovenantRoleNeverHeldError`, `CannotKickEqualOrHigherRankError`,
  `NotAuthorizedToKickError`, `CannotKickSelfError`,
  `NotAuthorizedToManageRanksError`, `LastManagerRankError`,
  `CrossCovenantRankError`, `IncompleteRankReorderError`,
  `CannotTransferToDepartedMemberError` (rank management, #1027),
  `NotAuthorizedToInviteError` (induction draft gate, #1231),
  `MentorBondError` (bond creation/cap), `VowGateError` (membership level gate),
  `CourtGulfViolationError` (servant tier not below leader's, #1589),
  `CourtPactExistsError` (duplicate active pact for pair, #1589),
  `CourtGrantNotMonotonicError` (grant raise would lower the cap, #1718),
  `MinorStandingRequiresSecondaryEngageError`, `MinorStandingDuranceOnlyError`
  (minor covenant membership, #2992), `CovenantTreasuryError` (base) →
  `NotAnActiveCovenantMemberError`, `NotAuthorizedToSpendCovenantTreasuryError`,
  `CovenantTreasuryTransferError` (covenant treasury, #2992)
- **Action Keys:** `engage_covenant_membership`, `disengage_covenant_membership`,
  `leave_covenant`, `kick_covenant_member`, `assign_covenant_rank`,
  `transfer_covenant_top_rank`, `stand_down_battle_covenant`,
  `deposit_covenant_funds`, `withdraw_covenant_funds` (#2992)
  (`actions/definitions/covenants.py`, #1346)
- **Telnet:** `covenant <subverb>` command (`commands/covenant.py`, #1346) for
  engage/disengage/leave/kick/rank/transfer/standdown/deposit/withdraw
  (deposit/withdraw added #2992: `covenant deposit <amount> [in <covenant>]` /
  `covenant withdraw <amount> [in <covenant>]`); `covenant request-gm
  <message> [in <covenant>]` / `covenant withdraw-gm-request [in <covenant>]`
  (#2119) dispatch `RequestGMForCovenantAction`/`WithdrawGroupStoryRequestAction`;
  covenant induction via
  `ritual draft ... covenant=<name>` / `ritual join <id> role=<role>` / `ritual fire <id>`,
  banner-call rise via `ritual draft ... covenant=<name>` / `ritual join <id>` /
  `ritual fire <id>` — both adapter-dispatched from `CmdRitual` via
  `commands/ritual_adapters.py`; `sphinx <vow name>` (#2640, `commands/sphinx.py`) — the
  Sphinx of Black Quartz's three-tier verdict, telnet parity for the REST endpoint below.
- **Selectors (`world.covenants.selectors`):**
  `resolve_actor_membership(*, covenant, character_sheets, capability=None)`,
  `get_active_memberships(*, character_sheet)` — shared by viewsets and the covenant Actions.
- **API Endpoints:**
  - `GET /api/covenants/gear-compatibilities/` — read-only authored content
  - `GET /api/covenants/character-roles/` — read-only; non-staff scoped to own
    currently-played sheets; exposes nested `rank` + `viewer_capabilities`
    (`can_invite`/`can_kick`/`can_manage_ranks`/`can_request_gm` bools — the last
    gates the "Request a GM" CTA, #2119)
  - `GET /api/group-story-requests/` (`world.stories`, #2119) — read-only
    `GroupStoryRequestViewSet`; staff see all, any GM sees the PENDING queue +
    their own claims, everyone else sees only their own covenants' requests
  - `GET|POST /api/covenants/ranks/` — list / create ranks (#1027)
  - `GET|PATCH|DELETE /api/covenants/ranks/{pk}/` — retrieve / update / delete
  - `POST /api/covenants/ranks/reorder/` — bulk tier reorder
  - `POST /api/covenants/ranks/{pk}/assign-member/` — assign member to rank
  - `POST /api/covenants/ranks/{pk}/transfer-top/` — move top rank to member
  - `GET /api/covenants/roles/sphinx/?role=<id-or-slug>` (#2640) — the Sphinx of Black
    Quartz's verdict for the requesting account's own active character; self-character
    only, read-only, never gates
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
  component tests (frontend). `GroupStoryRequestPanel` (#2119) on `CovenantDetailPage`
  shows the covenant's open GM ask (if any) with a Withdraw control, or a "Request a GM"
  form gated on `viewer_capabilities.can_request_gm`; `GMDashboardPage` gets an "Open Group
  Requests" section with a Claim control per row. Both dispatch through the generic
  `POST /api/actions/characters/{id}/dispatch/` endpoint (REGISTRY actions), not a
  bespoke `@action`.
- **Integrates with:** stories (`GroupStoryRequest` → `Covenant`/claiming `GMProfile`,
  #2119 — claim seats every active `CharacterCovenantRole`'s persona at the GM's table),
  magic (COVENANT_ROLE Thread anchor cap = `current_level × 10`;
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
  narrative (`send_narrative_message` for discovery announcements),
  currency (`world.currency.services.get_or_create_treasury`/`get_or_create_purse`/
  `transfer` back the Covenant Treasury, #2992)
- **Source:** `src/world/covenants/`
- **Details:** [covenants.md](covenants.md)

### Combat
Turn-based combat engine: encounter lifecycle, NPC threat patterns, damage resolution,
reactive maneuvers (COVER, INTERPOSE, DEFEND stance), and clash-of-wills.

- **Models (key):** `CombatEncounter` (`story_beat` FK → `stories.Beat`,
  nullable, #1760, #3559 - `beat_for_scene_conclusion` picks at most ONE beat
  an encounter may grade: this explicit `story_beat` when it's still
  UNSATISFIED `OUTCOME_TIER`, else the scene's `running_beat` when that is
  itself the objective (`kind=ENCOUNTER`); the old find-every-linked-beat
  scan is gone - an unrouted encounter with no running beat grades nothing),
  `CombatParticipant`, `CombatOpponent`,
  `CombatRoundAction` (`maneuver` field — FLEE / COVER / YIELD / INTERPOSE / SUCCOR / CHARGE /
  JOUST (#1843, see "Mounted combat" below); plus the
  player-decision fields `confirm_soulfray_risk` + the `CommittingDeclaration` fury mixin
  `fury_commitment` / `fury_anchor`, #1454; `cast_destination` / `cast_position_a` /
  `cast_position_b` — nullable FKs → `areas.Position` carrying a declared cast-position
  target/pair for position-consuming techniques, #2206, see "Cast-position targeting" below;
  `redirect_opponent_target` (FK `CombatOpponent`, SET_NULL) / `redirect_object_target`
  (FK `objects.ObjectDB`, SET_NULL) — mutually exclusive declared REDIRECT-flavor
  destinations, #2210, see the Redirect section above),
  `CombatOpponentAction`, `ThreatPool`, `ThreatPoolEntry`, `BossPhase`,
  `ComboDefinition`, `ComboSlot` (`requirement_label` names what a slot asks for, #3553),
  `ComboLearning` (use_count tracks repeat
  use; written by `fire_combo_discovery` on first combat trigger, #2017),
  `ComboSignature` (covenant+combo narrative flourish, #2017), `Clash`,
  `ClashRound`, `ClashContribution`, `BreakBarContribution` (#2642, see "Boss-fight structure"
  below), `CombatOpponent.reinforces` (self-FK, lieutenant->boss edge, #2642)
- **Technique-entrance combat integration (#2183):** `CombatRoundAction.from_entrance`
  (bool, default False) — stamped when a hostile Technique Entrance (see magic.md
  "Technique Entrance") seeds/feeds an encounter (`world.combat.cast_seed
  .seed_or_feed_encounter_from_cast(..., from_entrance=True)`); read at round resolution
  by `_maybe_suggest_entrance_dramatic_moment` (`world/combat/services.py`) to fire the
  Dramatic Moment Suggestion check once the declared cast's real success level is known
  (the entrance's own recognition hooks fired flourish-only at declaration time — the
  suggestion was deferred). `world.combat.cast_seed
  .seed_or_feed_encounter_from_benign_intervention(*, caster_sheet, target_sheet, scene)`
  is the benign sibling: seats a non-combatant whose protective (non-hostile) cast
  landed on an already-embattled ally into the fight — no opponent row, no stakes
  lock, no FOCUSED declaration (the cast already resolved standalone); no-ops when there
  is no feedable encounter or the target isn't embattled in it. #2226 (ADR-0119)
  generalized this to **all** benign casts via the `seat_caster_for_benign_intervention`
  wrapper (`cast_seed.py`), called post-resolution from `_route_immediate_cast` and
  `resolve_accepted_cast`; the entrance path's own seating calls were removed (the
  generalized calls supersede them).
- **Situational-perk seams (#2536 slice 3, ADR-0153):**
  - `CombatEncounter.opened_from_parley` (bool, default False) — stamped True by
    `world.combat.cast_seed.seed_or_feed_encounter_from_cast` ONLY when it CREATES a new
    encounter (never when it feeds an existing one) from a hostile cast landing inside an
    active, non-Battle-backed `Scene` (the same classification `Situation.DURING_NEGOTIATION`
    documents). v1 approximation: holds for the encounter's ENTIRE lifetime once stamped, not
    just its opening moment. Read by `Situation.COMBAT_OPENED_FROM_PARLEY` (holds whenever the
    flag is True) and `Situation.AMBUSH_UNDERWAY` (round-1-only: `opened_from_parley` True OR a
    round-1 `from_entrance=True` `CombatRoundAction` exists, per the technique-entrance
    integration above; False from round 2 on).
  - `CombatEncounter.initiated_by_pc_side` (`BooleanField(null=True)`, #2623, ADR-0154) — who
    sprang the fight: `True` = a PC participant's action opened it, `False` = the opposing side
    did, `NULL` = unknown/undirected (duels, battles, staff-opened). Stamped `True`
    unconditionally by `seed_or_feed_encounter_from_cast` at CREATE — every verified
    encounter-creation path today is PC-cast, so no code path stamps `False` yet (honest gap,
    recorded not invented; `False` is admin/GM-stampable via combat admin in v1). Read by an
    `origin_side` Situation Parameter on `COMBAT_OPENED_FROM_PARLEY`/`AMBUSH_UNDERWAY`:
    `OURS` requires `True`, `THEIRS` requires `False`, a `NULL` initiator with a non-blank
    `origin_side` never holds (direction unprovable); blank `origin_side` ignores this column
    entirely (today's side-blind behavior).
  - `CombatEncounter.is_champion_duel` (bool, default False) — see `docs/systems/battles.md`'s
    "Command Hierarchy & the Champion" section; read by `Situation.CHAMPION_DUEL`.
  - `CombatEncounter.on_chosen_ground` (bool, default False, #2646) — "the fight was won
    yesterday": stamped at CREATE time (never mutated after) in the three PC-vs-NPC
    encounter-creation seams (`world.combat.cast_seed.seed_or_feed_encounter_from_cast`,
    `world.combat.duels.create_lethal_duel`, `world.battles.services.open_place_encounter`) by
    `world.combat.chosen_ground.compute_on_chosen_ground(room)` — True iff the encounter's room
    holds a `room_features.PreparedGround` whose preparer is physically present in that room.
    `world.combat.duels.create_pvp_duel` never stamps it (PvP is never lethal). See
    `PreparedGround` (Room Features section below) for how a ground gets prepared. Read by
    `Situation.ON_CHOSEN_GROUND`, which mirrors `Situation.CHAMPION_DUEL`'s shape exactly (one
    cached FK read off the resolution's participant, False outside combat).
  - `CombatOpponent.affinity` (`AffinityType` CharField, blank default) — authored magical
    affinity typing for non-persona/generic NPCs that carry no `CharacterAura` row to infer
    from. Read by `Situation.ATTACKER_AFFINITY`'s evaluator FIRST against the row's required
    `affinity` Situation Parameter (authored typing wins outright when present, matching that
    axis is definitional and any `threshold_percent` is ignored), falling back to a reachable
    `ObjectDB`'s `CharacterAura` (`attacker.objectdb.aura` for a `CombatOpponent` — covers both
    persona-backed story NPCs and PvP attackers, whose `objectdb` is the attacking PC — or
    `attacker.aura` for a bare `ObjectDB` attacker) when blank: with `threshold_percent` set,
    that axis's Decimal percentage must be ≥ the threshold; unset, `dominant_affinity` must
    equal the axis (the pre-#2623 parameterless default).
  - `world.combat.services.resolve_npc_attack` threads a `SituationContext(attacker=
    opponent_action.opponent, resolution=CombatRoundContext(participant), holder=subject=
    participant.character_sheet, target=None, ...)` into the defender's real `perform_check` —
    the defense-side seam (the one context where the SUBJECT is not the aggressor), and the
    ONLY defense-check site threading `attacker` in v1. Makes CHECK_BONUS/TIER_FLOOR/
    BOTCH_IMMUNITY situational perks — including `ATTACKER_AFFINITY`-gated ones — live on
    defense rolls for the first time. `world.covenants.perks.services.applicable_perks` and its
    `_PerkResolver` gained the matching `attacker` parameter/field to propagate it into each
    candidate holder's `SituationContext`. See ADR-0153/ADR-0154 and `docs/systems/covenants.md`'s
    "Court/Battle scoping + defense-side seam" for the full design.
- **The Damage Identity — bounded percent lanes, vow-keyed stacking, execute (#2643,
  ADR-0158):** `combat.constants.ENEMY_LANE_CAP_PERCENT` (default 50) clamps the summed
  `ConditionDamageInteraction.damage_modifier_percent` in
  `_apply_condition_damage_interactions` (Undermine's enemy-side lane) before it multiplies
  net damage. `AbstractDamageProfile.execute_missing_health_multiplier` (Decimal, default
  0) scales a landing hit's damage by `1 + multiplier * missing_health_fraction`, computed
  off the target's PRE-hit health; applied at both `apply_damage_to_opponent` (live caller:
  `CombatTechniqueResolver._apply_profiles_to_target`, threading the resolving damage
  profile's own value) and `apply_damage_to_participant` (kwarg accepted + tested; no live
  caller yet — combat technique damage in this codebase only ever resolves against
  `CombatOpponent` targets). The sibling bounded ally-buff lane (`team_damage_percent`,
  vow-keyed diminishing returns via `ConditionInstance.source_vow`) lives in the magic app
  — see `docs/systems/magic.md`'s "The Damage Identity" section and ADR-0158 for the full
  composition.
- **Effect-palette / summon / allegiance additions (#1584):**
  - `CombatOpponent.allegiance` (`CombatAllegiance`: ENEMY default / ALLY) — mutable
    side-field; ALLY opponents fight *for* the party (summons, and future charm/
    switch-sides targets). See ADR-0059.
  - `CombatOpponent.summoned_by` (FK → `CharacterSheet`, nullable) — conjurer bond; set on
    summoned ALLY opponents.
  - `CombatOpponent.bond_expires_round` (int, nullable) — round at which the summon expires.
  - `CombatOpponent.morale` / `max_morale` (PositiveSmallIntegerField, #2015) — first-class
    depletable resolve pool mirroring war-scale `BattleUnit.morale`. Derived state via
    `morale_state_for` (STEADY/FALTER/BREAK) drives `select_npc_actions` (falter weakens,
    break → FLED). `OpponentTierTemplate.has_morale` flags mindless tiers (resist, not immune).
  - `ThreatPoolEntry.requires_steady` (bool, default False, #2015) — skipped when the
    opponent is faltering; lets designers author "weakened" entries.
  - `CombatOpponent.status` gains `OpponentStatus.REMOVED` (#3382) — a GM pull, distinct
    from `DEFEATED`/`FLED`. `world.combat.services.remove_opponent(opponent)` reuses the
    defeat teardown seam minus defeat consequences (no legend/loot/aftermath): breaks the
    opponent's active `EngagementLock` (`LockBreakReason.REMOVED`), fizzles any
    `PendingOpponentAttack` of its own via `_broadcast_windup_fizzled`, and re-checks
    `_check_encounter_completion`/`_classify_encounter_outcome` the same way
    `resolve_round`'s tail does — removing the last ACTIVE `ENEMY` opponent completes the
    encounter as VICTORY. `CombatOpponent` rows are never hard-deleted (status flip only,
    same historical-record invariant as a defeat). Surfaced by
    `CombatEncounterViewSet.remove_opponent` (`opponent_id`, gated `IsEncounterGMOrStaff`),
    `RemoveOpponentAction` (`actions/definitions/gm_combat.py`, key `remove_opponent`), and
    telnet `encounter removenpc <opponent>` — symmetric with `add_opponent`/`remove_participant`.
  - **Bestiary spawn (#3424):** `world.combat.services.spawn_from_creature_template(encounter,
    template, *, position=None, acting_account=None)` — previously built but zero-caller
    (Django-admin-only) — is now GM-reachable: `SpawnCreatureAction` (key `spawn_creature`,
    `actions/definitions/gm_combat.py`) mirrors `AddOpponentAction`'s shape exactly (same
    `_active_encounter_for_gm` resolution, same `acting_account` custody threading), resolving
    `template` pk-or-name via `resolve_model_by_pk_or_name(CreatureTemplate, ...)` and
    `position_id` as a pk. Telnet: `encounter spawn <template name> [at <position>]`
    (`commands/encounter.py`) resolves the position name to a pk in the command layer, exactly
    as `_handle_add` does. Web: `CreatureTemplateViewSet` (`GET
    /api/combat/creature-templates/`, read-only, `IsGMOrStaff`, `search`/`tier` filters) feeds
    the GM `AddOpponentDialog`'s "From Bestiary" tab
    (`frontend/src/combat/sections/GMEncounterControls.tsx`), which dispatches `spawn_creature`
    over the generic REGISTRY dispatch seam. The catalog serializer is deliberately thin (`name`/
    `tier`/`description`/`has_phases`/`threat_pool_name` — no phase or break-bar internals) so
    browsing it never spoils a boss's authored phases ahead of Consider/weakness-research
    discovery. `spawn_from_creature_template` clones any authored `CreaturePhaseTemplate` rows
    into `BossPhase` rows and stamps `BreakBarConfig` onto the spawned opponent when present.
  - `CombatOpponentAction.opponent_targets` (M2M → `CombatOpponent`) — populated by
    `select_npc_actions` for ALLY summons so they attack ENEMY opponents. Exactly one of
    `targets` (M2M → `CombatParticipant`) or `opponent_targets` is populated per action.
- **Rampart interception (#2209, epic #2040 decision 3; see `docs/systems/areas.md`'s
  "Rampart — Living Barriers" for the model and ADR-0125 for the design rationale):**
  `apply_rampart_interception` (`world/combat/services.py`) chips a position-covering
  `Rampart`'s `integrity` — via the shared `damage_rampart` seam — at the top of both
  `apply_damage_to_participant` and `_resolve_opponent_pre_apply`, **before**
  `DAMAGE_PRE_APPLY` emits. Firing order: Rampart → personal reactive interceptors → Guardian
  reactions. `ThreatPoolEntry.delivery` (`StrikeDelivery`: MELEE/MISSILE — also the field the
  wind-as-mechanic consumer below reads) plus `is_area` (`targeting_mode != SINGLE`) feed a Wind
  profile's `MISSILE_WARD` resist adjustment. `Clash.rampart` (nullable FK) binds a
  sustained-attack WARD clash to the covered position's Rampart; `_sync_rampart_progress`
  (`world/combat/clash.py`) mirrors each round's progress delta onto `rampart.integrity`
  through the same `damage_rampart` seam, so interception (paused while that clash is
  ACTIVE) and clash-progress never drift apart.
- **Boss-fight structure — diversity-weighted break accrual, lieutenant gate, pacing floor
  (#2642, ADR-0160):** `assess_break_bar` (`world/combat/services.py`) persists a
  `BreakBarContribution` row (mirrors `ClashContribution`'s per-round audit shape; `opponent`,
  `participant` nullable, `round_number`, `kind` — `BreakContributionKind`: DAMAGE / COMBO /
  HOLD / DEBUFF / SUPPRESSION, `effect_type` nullable, `amount`) for each qualifying feed. Round
  depletion sums 1 unit per distinct (actor, kind) pair, doubled (`BREAK_NOVELTY_MULTIPLIER=2`)
  for a (kind, effect_type) pair's first-ever occurrence in the encounter, plus a landed combo's
  flat `bonus_damage` — replacing the pre-#2642 flat ">=2 distinct PCs x >=2 distinct
  effect_types = 1 chip" gate (dead by ruling; no per-actor cap survives). New non-damage feeds:
  HOLD (a PC-side LOCK-flavor `Clash` win against the boss resolved this round — read via
  `Clash.resolved_round`/`resolution`, contributors from that round's `ClashContribution` rows),
  DEBUFF (a new behavior-altering `ConditionInstance` landed on the boss's `objectdb`, detected by
  `applied_at >= encounter.round_started_at`), SUPPRESSION (a reinforcing lieutenant newly
  suppressed via the same condition signal or a freshly-started `EngagementLock`).
  `CombatOpponent.reinforces` (self-FK, null=not a lieutenant) marks a lieutenant's boss; the
  **lieutenant gate** divides each round's raw depletion by `1 + active_unsuppressed_reinforcers`
  (`_active_reinforcer_count` — ACTIVE status, morale not BREAK, no behavior-altering condition,
  not pinned in an ACTIVE `EngagementLock`, acted this round; a parked/idle lieutenant never
  gates), floored at 1 unit whenever depletion occurred — proportional, never a hard block. The
  **pacing floor** (`minimum_break_bar_threshold()`) clamps a stamped `break_bar_threshold` to
  `>= (soulfray_stage_count + 2) * BAR_UNITS_PER_ROUND` at both stamping sites
  (`_stamp_phase_break_bar_config`, `_stamp_break_bar`) — 0 (no clamp) when Soulfray has no
  authored `ConditionStage` rows. `assess_break_bar` now runs AFTER `resolve_round`'s clash
  post-pass (was before) so the HOLD feed can see a LOCK-clash win resolved the same round. BOSS
  tier opponents resist a decisive Parley calm by one success-level step
  (`BOSS_PARLEY_RESISTANCE_STEP`, `_resolve_parley`). The break broadcasts a celebration naming
  every distinct contributor recorded on the boss's `BreakBarContribution` rows this encounter
  (`join_labels`, promoted from `interaction_services._join_labels` to a shared public helper).
- **Wind-as-mechanic (#1555, ADR-0129):** the combat consumer of the WIND exposure axis
  (`world.locations.services.felt_exposure`, `StatKey.WIND`; provider is #1522).
  `wind_penalty(felt: int) -> int` (`world/combat/constants.py`) bands felt WIND into a check
  modifier — CALM (<15) → 0, BREEZY (15-39) → -5, WINDY (40-69) → -10, GALE (70+) → -20.
  On the PC offense side, `CombatTechniqueResolver._roll_check` (`world/combat/services.py`)
  appends a `ModifierContribution(source_kind=SCENE, label="Wind", ...)` when the attacker's
  strongest equipped weapon (`_select_equipped_weapon`, the same pick the damage path uses)
  has `gear_archetype` RANGED or THROWN and the encounter has a room; melee/lance attacks skip
  the `felt_exposure` lookup entirely. On the NPC side, `resolve_npc_attack` adds the
  same-magnitude *positive* contribution to the PC's defense roll when the attacking
  `ThreatPoolEntry.delivery` is MISSILE — symmetric with the offense side ("the gale that
  ruins your shot ruins theirs"); flat `base_damage` entries with no defense check
  (`defense_check_type` unset) never reach this seam.
- **Mounted combat (#1843):** a mount is a companion + a verb-gating condition, not a new
  typeclass or a blanket stat bonus (ADR-0126). `world.companions.services.mount_companion`/
  `dismount_companion` set/clear `Companion.ridden_by` (nullable unique FK →
  `CharacterSheet`) and apply/remove the seeded "Mounted" `ConditionTemplate`
  (`world.companions.mount_content`, no `ConditionCheckModifier` rows — mounting alone
  grants no passive bonus). Dismount fires on three triggers: voluntary (`dismount
  companion`), encounter exit (`LeaveEncounterAction`), and companion defeat
  (`resolve_companion_defeat`'s die outcome, via `release_companion`).
  `CombatManeuver.CHARGE`: `declare_charge(participant, technique, opponent)` requires the
  Mounted condition and a target >= 1 hop away and reachable within `CHARGE_MAX_HOPS`;
  resolution (`_resolve_charge_movement`, dispatched from `_resolve_pc_action`) force-moves
  the rider onto the opponent's position then falls through to the normal weapon-attack
  pipeline — `CombatTechniqueResolver` folds `CHARGE_CHECK_BONUS`/`CHARGE_DAMAGE_BONUS`
  (doubled for an equipped `GearArchetype.LANCE`) into the same
  `collect_check_modifiers`/damage-budget seams every other check contribution uses; never
  `bypass_pre_apply` — defenses/guardians/ramparts fire unchanged.
  `CombatManeuver.JOUST`: `declare_joust(participant, technique)` only in a 2-participant
  DUEL where both duelists hold Mounted and have a LANCE equipped; resolution
  (`_resolve_joust_pass`) rolls one opposed weapon-attack check per side via the same
  resolver seam and grades the `success_level` gap into `JOUST_DECISIVE_MARGIN`/
  `JOUST_NARROW_MARGIN` bands — decisive unhorses the loser (2x lance damage + the seeded
  "Unhorsed" condition + a force-dismount), narrow deals 1x lance damage, a tie jars both
  with no damage; damage applies to the loser's mirror `CombatOpponent` via the existing
  non-bypassing `apply_damage_to_opponent` path (ADR-0023 non-lethal PvP capping
  unchanged). `LANCE_UNMOUNTED_PENALTY` applies at the same check-modifier seam to any
  attack made with an equipped LANCE while not Mounted, regardless of maneuver.
  `GearArchetype.LANCE` (`world.items.constants`) joins `WEAPON_ARCHETYPES`; a starter
  "Lance" `ItemTemplate` seeds via `world.seeds.game_content.items.seed_lance_item`. Telnet:
  `companion mount <name|id>` / `companion dismount` (`CmdCompanion`), `combat charge <opp>
  with <technique>` / `combat joust [with] <technique>` (`CmdCombat`) — no web/frontend
  surface (matches the several existing maneuvers that ship telnet-only since the web
  "available actions" endpoint excludes REGISTRY maneuvers without `ActionTemplate`
  backing).
- **Dramatic surge engine (#2013):** `apply_dramatic_surge(*, encounter, participant, amount,
  trigger_kind, subject_sheet=None, reason="", subject_opponent=None,
  subject_phase_number=None)` (`world/combat/escalation.py`) — the one write
  path for every intensity surge, backed by `DramaticSurgeRecord` (dedup audit row;
  `SurgeTriggerKind`: ALLY_FALLEN / ALLY_PERIL / HATED_FOE / HIGH_STAKES / INTERFERENCE /
  GM_MANUAL / BOSS_PHASE / BOSS_ENRAGE / BOSS_BREAK). `reason` (#3387) persists onto the
  record as GM-stated provenance for a manual trigger only — every automatic leg leaves it
  blank; never broadcast to the room. Three new trigger legs alongside the
  existing #872 grief spike: mortal-peril (`escalation_spike_on_mortal_peril` on
  `CONDITION_APPLIED`, filtered via `world.vitals.peril_resolution
  .acute_peril_condition_names()`), hated-foe (checked on encounter join and NPC opponent add,
  reading `CombatOpponent.persona.character_sheet` against the PC's own negative-sign
  `CharacterRelationship`), and stakes (`StakesEscalationModifier`, one row per `StakesLevel`:
  per-tick `intensity_step_bonus` + one-shot `initial_surge` + `default_curve`
  auto-assigned at encounter creation). `EscalationCurve` gained
  `peril_spike_intensity_amount` / `hated_foe_spike_intensity_amount` / `surge_narration`
  (generic `{character}`-only template). Surfaced to the web combat panel via
  `EncounterDetailSerializer.surge_beats` (owner/GM-scoped provenance) and broadcast to the
  room via `room.msg_contents(...)` (telnet). The boss legs (#3445) - `apply_boss_phase_surge`
  / `apply_boss_break_surge`, `world/combat/escalation.py` - fire from
  `check_and_advance_boss_phase` and `_assess_boss_break_bar`, magnitudes authored on
  `EscalationCurve.boss_{phase,enrage,break}_spike_intensity_amount`, deduped per boss per
  phase (ADR-0250).
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
    Both paths now also call `process_damage_interactions` after soak/resistance/armor
    (#2018) — condition-damage interactions amplify, dampen, consume, or transform
    conditions. Narration fires only on transitions (removal/transform), not every hit.
    `apply_damage_to_opponent` also calls `_try_interpose_for_opponent` (#2207) so a
    declared guardian can shield an ALLY-allegiance opponent (a summon) the same way
    `apply_damage_to_participant` shields a PC — see the Key Services list below.
  - `drain_reactive_upkeep(encounter)` — debits `ConditionTemplate.upkeep_anima_per_round`
    from each active participant holding a reactive condition; called by `begin_round_of_combat`
    immediately after emitting `COMBAT_ROUND_STARTING`. See ADR-0060. **Consented upkeep
    (#3573):** unaffordable upkeep on an instance with `ConditionInstance.soulfray_consented`
    debits into deficit (via `_debit_ally_paid_upkeep`/`_pay_upkeep`) instead of lapsing the
    condition, and accrues Soulfray; a deficit fire narrates "bleeds soul to keep the ward on
    {bearer}". Both here and in interpose, lethality is `encounter.is_lethal` (already a
    live combat encounter by construction). Same consent branch structure applies to a
    Barrier/other reactive-condition fire (`_try_spend_reactive`, `world/magic/services/
    effect_handlers.py`) - since that seam can fire on a ward held outside a combat
    encounter, it instead reads `active_combat_engagement_for(payer)` (extracted from
    `ParticipantSerializer._combat_engagement`, #3573) for the character's live COMBAT
    `CharacterEngagement`, falling back to lethal when None. See ADR-0255 (amends
    ADR-0118).
  - `is_untargetable(target: ObjectDB) -> bool` (`world/conditions/services.py`) — returns
    True when the target has an active `ConditionInstance` whose
    `ConditionCategory.grants_intangibility` is True; used by NPC targeting + PC AoE
    filter sites to honour the intangibility gate.
- **Cast-position targeting (#2206):** runtime destination selection for the
  position-consuming effect-palette techniques (Barricade/obstacle, Phase Jump/teleport,
  Force Grip/telekinesis — previously placeholder `destination_position_id=0` at seed
  time, see `docs/systems/magic.md`), wired end-to-end for combat declaration:
  - `resolve_cast_position_params(participant, technique, position_params)`
    (`world/combat/services.py`) — validates a declared `destination_position_id` (single)
    or `position_a_id`/`position_b_id` (pair) against the encounter's own room and the
    technique's `reach`/`reach_hops`; raises `ActionDispatchError` (`UNKNOWN_ACTION_REF`) on
    a foreign-room position or a half-supplied pair, `TARGET_OUT_OF_REACH` when the caster
    is placed and the destination exceeds reach.
  - `CastTechniqueAction.round_declaration` (`actions/definitions/cast.py`) forwards a
    `position_params` kwarg into the round-declaration kwargs; `CombatRoundContext
    ._resolve_cast_positions` (`world/combat/round_context.py`) calls
    `resolve_cast_position_params` and persists the resolved FKs onto the
    `CombatRoundAction` at declaration time (`declare_action`, `world/combat/services.py`).
  - `CombatTechniqueResolver._apply_conditions` (`world/combat/services.py`) reads the three
    FKs back off the declared action and forwards them as `position_params` to
    `apply_technique_conditions` (`world/magic/services/condition_application.py`), the same
    shared seam the non-combat cast path already used.
  - **Root-cause fix in the shared conditions layer:** position ids now thread through
    `BulkConditionApplication.cast_destination_id` / `cast_position_a_id` /
    `cast_position_b_id` (`world/conditions/types.py`) and are stamped onto the resulting
    `ConditionInstance` by `_stamp_cast_positions` (`world/conditions/services.py`) **before**
    `CONDITION_APPLIED` fires — same-event reactive handlers
    (`create_obstacle_on_condition` and siblings, #2019) read the position fields off
    `payload.instance` synchronously. This replaces the old post-hoc
    `_apply_position_params_to_instances` helper (removed) and also fixes the previously-broken
    non-combat live path, which suffered the same race.
  - `position_target_shape(technique) -> "pair" | "single" | "none"`
    (`world/magic/services/targeting.py`, batched `Prefetch` over condition→trigger→flow
    steps) classifies which position input shape a technique's effects consume; exposed on
    available actions via `PlayerAction.position_target_shape`
    (`actions/player_interface.py`) → `RoundActionSerializer.position_target_shape`
    (`actions/serializers.py`) so the frontend can render the right picker (single point vs.
    endpoint pair) without hardcoding technique names.
  - `RoundActionSerializer` (`world/combat/serializers.py`) exposes the three FKs; note
    drf-spectacular does not introspect them (pre-existing generator gap) — generated
    frontend types were not regenerated for this field, a known/documented degradation.
  - **Frontend:** a Positions picker in `ActionDeclarationCard` (single/pair, reach-greyed),
    shape-aware `position_params` dispatch kwargs, state lifted to `CombatRail` (#2197: renders
    in-scene on `/scenes/:id`, formerly the now-deleted `CombatScenePage`'s own route), and
    map-click picking via `TacticalMap.onPickPosition` (`frontend/src/areas/components/`).
  - **Telnet needed zero changes** — #2019's `position=`/`position_a=,position_b=` command
    grammar (`commands/combat.py`) already produced a `position_params` kwarg; #2206 is what
    makes that kwarg actually reach validation and persistence in the combat round.
  - Proven at the round seam by `world/combat/tests/test_cast_position_declaration.py`
    (foreign-room rejection + a full declare→resolve→condition→sealed-edge journey for
    Barricade); non-combat web casting still has no position picker (telnet-only there).
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
  - `ConditionInstance.soulfray_consented` (bool, default False, #3573) - the caster
    consented at cast time to keep this condition's reactive cost/upkeep firing past zero
    anima at the price of Soulfray; stamped by `_create_instance_from_context` from both
    `apply_technique_conditions` and `apply_signature_bonus_conditions`, never changes
    after creation. Read by `_try_spend_reactive` and `drain_reactive_upkeep`.
- **Key Services (`world/combat/services.py`):**
  - `resolve_round(encounter)` — full round orchestrator: passives → refresh triggers →
    interpose challenges → focused actions → post-passes (challenges, clashes, bleed-out)
  - `declare_interpose(participant, ally=None, technique=None, redirect_opponent_target=None, redirect_object_target=None)`
    — arm an INTERPOSE `CombatRoundAction` for the round. **Guardian reaction
    declaration (#2207):** an optional *technique* reuses `CombatRoundAction.
    focused_action` (no new column) to carry a declared protective technique into the
    round; gated on the participant knowing it (`CharacterTechnique`) and it
    classifying to a protective flavor via `world.magic.services.targeting.
    protective_flavor`, and `ally` still resolving to an active co-encounter
    participant when given. `technique=None` keeps the pre-#2207 mundane shape
    (passives only, `focused_action` zeroed). See the combat `AGENT_GLOSSARY.md`'s
    Guardian reaction entry and ADR-0118. **Redirect declaration (#2210):**
    `redirect_opponent_target`/`redirect_object_target` (mutually exclusive, both
    `None` = "away") declare a REDIRECT-flavor technique's saved-damage destination
    at declaration time (ADR-0032/0122), validated by `_validate_redirect_declaration`
    - see combat `AGENT_GLOSSARY.md`'s Redirect entry. **Soulfray consent (#3573):**
    a keyword-only `confirm_soulfray_risk` (bool, default False) is captured at
    declaration time, since a reaction fires inside someone else's resolution and
    can't stop to prompt - stored on `CombatRoundAction.confirm_soulfray_risk` and
    read by `_try_technique_interpose`. Telnet: a trailing `soulfray` keyword on
    `combat interpose ...` (`commands/combat_maneuvers.py`) sets it. See ADR-0255
    (amends ADR-0118).
  - `_try_interpose(participant, pre_payload)` — fires at `DAMAGE_PRE_APPLY` seam; finds
    an armed interpose challenge naming *participant* (or "any ally") and dispatches it
    via `_dispatch_interpose_action`
  - `_try_interpose_for_opponent(opponent, pre_payload)` (#2207) — the summon-guarding
    sibling of `_try_interpose`: extends interpose to ALLY-allegiance `CombatOpponent`
    wards (player summons/companion NPCs). **ANY-ALLY only** — `CombatRoundAction.
    focused_ally_target` FKs `CombatParticipant`, so it can never name a `CombatOpponent`
    directly; only an armed `focused_ally_target IS NULL` declaration can pick up a
    summon. Named-ally guarding of a summon is a follow-up once `focused_ally_target`
    (or a sibling field) can point at an opponent. Called from `apply_damage_to_opponent`.
  - `_dispatch_interpose_action(action, protected, pre_payload)` (#2207) — shared tail for
    both ward types; computes the bond-bonus modifier (`bond_bonus`, #2021) then forks on
    `action.focused_action_id`: set → `_try_technique_interpose` (anima cost, no fatigue);
    unset → `dispatch_interpose(..., select_best_check_rating=True)` + fatigue charge on fire.
  - `dispatch_interpose(interposer, protected, pre_payload, approach, *, select_best_check_rating=False)`
    — thin wrapper over `dispatch_capability_reaction`; calls `apply_interpose_outcome` to
    mutate the payload. **Best-of check selection (#2207):** the mundane guardian path calls
    this with `select_best_check_rating=True`, so `dispatch_capability_reaction` picks the
    higher-rated of the guardian's *real* available reaction approaches (the Reflexes vs.
    Melee-Defense twins seeded per interpose capability in `interpose_content.py`) via
    `world.checks.services.compute_check_rating` — deterministic, zero extra rolls, never
    inventing an action outside `get_available_actions`'s output (ADR-0032).
  - `_try_technique_interpose(action, interposer, protected, pre_payload, *, extra_modifiers=0)`
    (#2207) — resolves a technique-guardian's declared protective reaction. Affordability
    first (`ConditionTemplate.reactive_anima_cost` via `protective_condition_and_flavor`,
    gated by `_guardian_can_fire_technique_interpose`: affordable fires unconditionally;
    unaffordable fires only when `action.confirm_soulfray_risk` was set at declaration
    (#3573) - no pool at all still fizzles regardless); rolls the guardian's own cast check
    (`resolve_cast_check_type`, None-guarded — an unprovisioned caster fizzles the same way)
    against the mundane Interpose challenge's severity; debits anima (not fatigue) on any
    non-fizzle fire via `_settle_technique_interpose_cost` (#3573) - `deduct_anima(lethal=
    encounter.is_lethal)` runs the guardian into deficit when consented, and a consented
    fire also accrues Soulfray through `world.magic.services.soulfray.accumulate_soulfray`
    (deficit>0 narrates "tears at their own soul to hold the line over {ally}"); grades via
    the SAME `_grade_interpose_damage` the mundane path uses (SHIELD divisor included). A
    clean `blink`-flavored block relocates the ward to the guardian's own current position
    (`force_move_to_position`) - a stand-in for #2206's `CombatRoundAction.cast_destination`,
    preferred once that field lands. See ADR-0118 (amended by ADR-0255, #3573) for why this
    rolls outside `use_technique`. **`redirect`-flavored resolution
    (#2210):** `saved = amount_before - pre_payload.amount` after grading (zero
    redirects nothing); `_resolve_technique_redirect` dispatches the saved amount to
    the declared destination (`_redirect_away` / `_redirect_to_opponent` /
    `_redirect_to_object`, each broadcasting via `broadcast_action_outcome`) —
    `_redirect_to_opponent` calls `apply_damage_to_opponent(..., bypass_pre_apply=True)`
    (ADR-0060's loop guard); `_redirect_to_object` fires the volatile object's
    `PropertyDetonation.consequence_pool` at every combatant positioned there via the
    new `world.room_features.trap_services.fire_pool_at_characters` (reuses
    `apply_pool_deterministically`, no roll), then deletes the triggering
    `ObjectProperty` (one-shot). Any destination no longer valid at resolution time
    (opponent defeated, object moved/consumed/no Position) degrades to
    `_redirect_away`.
  - `apply_interpose_outcome(pre_payload, result)` — SUCCESS zeroes payload, PARTIAL halves,
    FAILURE is a no-op
  - `_ensure_interpose_challenges(encounter, pc_actions)` — idempotently mints
    `ChallengeInstance` rows for armed INTERPOSE actions each round
  - `declare_succor(participant, ally)` — arm a SUCCOR `CombatRoundAction` sheltering a
    specific ally from a round-ticked environmental hazard (#1744); unlike Interpose, Succor
    always names a specific ally (no "any ally" path)
  - `dispatch_succor(succorer, protected, approach)` — thin wrapper over
    `dispatch_capability_reaction`; calls `apply_succor_outcome` to derive the tick-amount
    multiplier
  - `_ensure_succor_challenges(encounter, pc_actions)` — idempotently mints
    `ChallengeInstance` rows bound to each protected ally for armed SUCCOR actions each round
  - `declare_use_item(participant, item_instance, *, target=None)` (#2023/#2120) — arm a
    USE_ITEM `CombatRoundAction` (a primary maneuver — consumes the round's action slot,
    unlike the passives-only maneuvers); validates possession via `ItemState.is_in_possession`;
    `target` may be a `CombatParticipant` (→ `focused_ally_target`) or `CombatOpponent`
    (→ `focused_opponent_target`). Resolution (`_resolve_use_item`) dispatches the existing
    `UseItemAction` with the declared target threaded through (the #2120 target-forwarding fix).
    Entry points: telnet `combat use <item> [on <target>]`, web `POST /api/combat/{pk}/use_item/`,
    registry key `combat_use` (`UseItemManeuverAction`, `actions/definitions/combat_maneuvers.py`).
  - `maybe_resolve_on_ready(encounter)` (#2120) — PaceMode.READY early resolution: when every
    ACTIVE participant's round action is `is_ready=True`, calls `resolve_round` immediately
    instead of waiting for the TIMED game-clock sweep. Called from `ReadyAction.execute`
    after `toggle_action_ready`, only when the toggle landed on ready=True.
- **Key Services (`world/mechanics/succor_shared.py`, #1744):** `SUCCOR_CHALLENGE_NAME` +
  `apply_succor_outcome(result)` — domain-agnostic Succor pieces shared by combat and scene
  rounds (moved out of `world.combat` so `world.scenes` doesn't need a one-directional import
  into `world.combat` for a domain-agnostic concept). `apply_succor_outcome` maps a graded
  Succor resolution to a float multiplier (clean block → 0.0, partial → 0.5, fail → 1.0);
  consumed by round-tick hazard damage instead of mutating a payload in place (Interpose's
  shape). Both `world.combat.services.dispatch_succor` and
  `world.scenes.round_context.SceneRoundContext.get_cover_for` import from here.
  - `_refresh_participant_trigger_handlers(encounter)` — after passives, calls
    `TriggerHandler.refresh()` on each active participant so passive-installed reactive
    triggers (e.g. Shielded) fire in the same round
- **Key Services — social/mental combat (#2015):**
  - `morale_state_for(opponent)` / `apply_morale_damage(opponent, amount)` /
    `tier_has_morale(opponent)` (`world/combat/morale.py`) — derived state + mutation
  - `declare_rally` / `declare_demoralize` / `declare_taunt` / `declare_parley`
    (`world/combat/services.py`) — arm the four social-combat `CombatRoundAction`s
  - `_resolve_rally` / `_resolve_demoralize` / `_resolve_taunt` / `_resolve_parley` —
    round-tick resolution in `_resolve_pc_action`; roll stat+skill(+spec) checks via
    `collect_check_modifiers` + `perform_check`, with Composure defense
    (`compute_resist_increment`) and mindless resistance (`MINDLESS_MORALE_RESISTANCE`).
    Taunt reuses `accumulate_threat`; parley reuses `apply_social_disposition_delta`
    + the seeded Calm condition; demoralize depletes morale via `apply_morale_damage`.
  - `ensure_social_combat_content()` (`src/world/combat/social_combat_content.py`) —
    idempotent seed for the 4 social-combat CheckTypes (Rally/Demoralize/Taunt/Parley
    with stat+skill+spec), the Inspired condition, and a Charming Word technique.
- **Key Services (`world/mechanics/reactions.py`):**
  - `dispatch_capability_reaction(character, protected, challenge_name, approach, outcome_fn, *, select_best_check_rating=False)`
    — shared reactive spine; used by INTERPOSE and the catch-faller seam. `approach`
    still wins when given; `select_best_check_rating=True` (opt-in, #2207) only changes
    the ``approach is None`` fallback: instead of the naive first-match pick, it groups
    the actor's real available reaction actions by resolved `check_type`, rates each
    DISTINCT check type once via `world.checks.services.compute_check_rating`, and
    returns the action backed by the higher-rated one (`_select_best_rated_action`) —
    deterministic (ADR-0019), no invented actions (ADR-0032). Existing callers (Succor,
    the scene-cover path) leave it `False` and keep the prior first-match behavior.
- **Reactive content seeds:** (interpose/succor/fall-catch/redirect run in production
  via the `reactive_challenges` cluster in `world.seeds.clusters`, #2636 — after
  `combat_checks`, which seeds the Melee Defense `CheckType` Interpose looks up;
  `ensure_defend_content` is deliberately NOT in the cluster: it seeds a placeholder
  Gift/Technique, which is lore-repo content territory)
  - `ensure_interpose_content()` (`src/world/combat/interpose_content.py`) — idempotent
    seed for the INTERPOSE `ChallengeTemplate` + four capability-gated `Application` rows
    (telekinesis, shield, barrier, pull_aside) + Reflexes `CheckType` + SUCCESS-tier DESTROY
    consequence. Each interpose capability also seeds a Melee-Defense twin `Application`
    (#2207) keyed on the SAME `CapabilityType` as its base row (not a separate
    `melee_guard` type) — the twin is what `select_best_check_rating` actually has to
    choose between on the real dispatch path.
  - `ensure_succor_content()` (`src/world/combat/succor_content.py`) — idempotent seed for
    the SUCCOR `ChallengeTemplate`, reusing the same four capability-gated `Application` rows
    Interpose seeds + a dedicated exploration `CheckType` + SUCCESS-tier DESTROY consequence
  - `ensure_defend_content()` (`src/world/combat/defend_content.py`) — idempotent seed for
    the "Shielded" `ConditionTemplate` + its `DAMAGE_PRE_APPLY` `TriggerDefinition` (SELF
    filter) + `FlowDefinition` (`MODIFY_PAYLOAD multiply 0.5`) + DEFEND passive `Technique`
    with `TechniqueAppliedCondition(target_kind=ALLY)`
  - `ensure_redirect_content()` (`src/world/combat/redirect_content.py`, #2210) —
    idempotent seed for one example volatile `Property` ("Volatile (Powder)") + its
    `PropertyDetonation` sidecar + a small detonation `ConsequencePool` (one
    DEAL_DAMAGE `Consequence`). Mirrors `ensure_interpose_content`'s self-contained
    `get_or_create` idiom.
- **Telegraphed enemy wind-ups + reaction economy (#2637, #2639; ADR-0161 — extends
  ADR-0118's pre-armed-policy shape):**
  - `ThreatPoolEntry.windup_rounds` (PositiveSmallInt, default 0) + `windup_telegraph`
    (CharField) — authored data on existing threat pools; 0 is today's same-round behavior
    unchanged. `_broadcast_windup_telegraph` always names a target (#3572): authored text
    may use `{opponent}` and `{target}`; if it lacks `{target}`, `WINDUP_TARGET_CLAUSE`
    (`" It is aimed at {target}."`) is appended; a room-targeting wind-up (no `target`)
    formats as `WINDUP_NO_TARGET_LABEL` ("no one in particular"). Blank `windup_telegraph`
    falls back to `WINDUP_GENERIC_TELEGRAPH` ("`{opponent} begins something enormous,
    bearing down on {target}...`"). All three constants live in `world/combat/constants.py`.
  - `PendingOpponentAttack` (`world/combat/models.py`) — clones the deferred-then-reactive
    shape of `world.scenes.models.PendingSuddenHarm` (#1316) rather than importing it (that
    model is single-round out-of-combat; this one is multi-round, combat-native, with its
    own downgrade bookkeeping). Fields: `encounter`/`opponent`/`threat_entry` FKs,
    `target` (nullable FK → `CombatParticipant`, v1 single-target — null when the entry is
    room-targeting), `declared_round`/`resolves_round` (CheckConstraint `resolves_round >
    declared_round`), `called_out` (bool), `downgrades` (PositiveSmallInt).
  - **Declaration:** `_build_opponent_round_actions` (`world/combat/services.py`) creates a
    `PendingOpponentAttack` INSTEAD OF a same-round `CombatOpponentAction` when the chosen
    entry's `windup_rounds > 0`; `_batch_fetch_cooldown_data` also reads
    `PendingOpponentAttack.declared_round` so a wind-up commits to its entry's cooldown
    immediately, not only once it matures. Telegraph is dual-dispatched
    (`_dual_dispatch_combat_narration` — `broadcast_action_outcome` WS + direct
    `room.msg_contents` telnet, mirroring `announce_fired_perks`'s HARD-parity shape).
  - **Auto-callout v1** (`CovenantRole.calls_out_windups`, bool): `_find_windup_caller`
    auto-calls a wind-up (`called_out=True`) when any ACTIVE participant holds an
    active-engaged `CharacterCovenantRole` whose role (or that role's `parent_role` — rides
    the same shape as `blend_weight_for`) has the flag; at most one call-out per round per
    encounter. v1 is partially-passive — it picks THAT a wind-up gets called, not WHICH one.
  - **Client surface (#3572):** `EncounterDetailSerializer.pending_attacks`
    (`get_pending_attacks`, schema-typed via `PendingAttackSerializer`, the same
    schema-only idiom as `EngagementLockSerializer`) lists pending `PendingOpponentAttack`
    rows soonest-landing first: id, opponent_id, opponent_name, target_participant_id,
    target_name, declared_round, resolves_round, rounds_until_landing, downgrades,
    called_out, damage_scale (`windup_damage_scale`), cancelled. One query, select_related
    on opponent/target. `frontend/src/combat/components/PendingAttacks.tsx` renders the
    rows as the threat strip at the top of `YourTurn` (Guard/Strike prefills) and
    read-only for observers in `CombatTurnPanel`; telnet bare `combat`
    (`src/commands/combat_maneuvers.py`) prints the same rows as a `Wind-ups:` block.
  - **Maturation:** `_mature_pending_opponent_attacks` runs in `resolve_round` after the
    encounter flips to RESOLVING but BEFORE the round's `CombatOpponentAction` rows are
    queried, so a matured wind-up's synthesized action (real `CombatOpponentAction`,
    `damage_scale` set) is picked up by the normal NPC-resolution pipeline unmodified in the
    same pass. `downgrades >= WINDUP_FIZZLE_DOWNGRADES` (3) fully cancels; otherwise
    `damage_scale = max(WINDUP_MIN_DAMAGE_SCALE, 1 - WINDUP_DOWNGRADE_STEP * downgrades)`
    (0.25 floor). `CombatOpponentAction.damage_scale` (FloatField, default 1.0) is the new
    persisted multiplier `resolve_npc_attack` and the flat (no-defense-check) NPC-damage
    path both read.
  - **Interception rider:** `_apply_windup_interception_rider`, called from `_resolve_pc_action`
    right after the combo rider — any PC hit landing damage > 0 on an opponent with a
    not-yet-matured `PendingOpponentAttack` adds `WINDUP_BLIND_DOWNGRADE` (1), or
    `WINDUP_CALLED_OUT_DOWNGRADE` (2) when `called_out` — no new button, rides the existing
    damage-landed moment.
  - **Situations:** `Situation.ENEMY_WINDUP_UNDERWAY` / `ENEMY_WINDUP_CALLED_OUT`
    (`world.covenants.perks`) — true while the subject's encounter has a not-yet-matured
    `PendingOpponentAttack` (declared is the situation, mirrors `ALLY_INTERCEPTED_FOR_ME`);
    the called-out variant additionally requires `called_out=True`. No params.
  - **Reaction economy (#2639), shared fire seam per F-10c:** `CombatParticipant.
    reactions_used` (reset to 0 for every participant in `begin_declaration_phase` via
    identity-map-safe `bulk_update`, never a raw queryset `.update()` — that would leave any
    already-cached instance reading a stale value) vs `REACTIONS_PER_ROUND` (1) — gated +
    incremented in `_dispatch_interpose_action`, the shared tail both `_try_interpose` and
    `_try_interpose_for_opponent` call. `DamagePreApplyPayload.answers_consumed` (int,
    default 0) vs `ABSORPTION_CAP_PER_MOMENT` (2) — per-LANDING-HIT cap on how many
    interceptors may answer, incremented at the same seam. Both budgets decline with the
    same "did not fire" no-op shape as an unaffordable/failed reaction. Standing defenses
    (absorb/reflect/blink conditions, flow-triggered) stay OUTSIDE both budgets — they carry
    their own reactive costs (flagged judgment call).
  - **`select_npc_actions` wiring gap (#2637 design 8):** investigated — it had ZERO
    production callers outside the simulation harness (`world/combat/simulation.py`); no
    Action/command/task called it before `resolve_round` in live play. `resolve_round` now
    auto-selects (while status is still DECLARING, since `select_npc_actions` requires it)
    when the round has no NPC selection of EITHER shape yet — no `CombatOpponentAction` AND
    no `PendingOpponentAttack` declared this round — a conservative, idempotent fallback;
    any explicit prior selection (staff, simulation, tests) is left alone.
- **PC sustained actions (#2705; ADR-0190 — extends ADR-0161's pre-armed shape to the
  PC side):**
  - `SustainedAction` (`world/combat/models.py`) — the PC-side mirror of
    `PendingOpponentAttack`, placed immediately after it. `sustained_kind`
    (`SustainedKind`: RITUAL/TECHNIQUE) discriminates a `ritual`/`technique` FK pair
    (exactly one non-null, enforced by `clean()` + two DB `CheckConstraint`s), plus
    `declared_action` (nullable — set for TECHNIQUE, null for RITUAL, since a ritual is
    declared through `PerformRitualAction`, not the combat declaration seam),
    `declared_round`/`resolves_round` (`CheckConstraint resolves_round > declared_round`),
    `absorption_budget` (written once at declaration), `outcome_snapshot` (FK →
    `traits.CheckOutcome`, so logs/UI can say WHY the budget is what it is), `downgrades`.
    `subject_name` property (`ritual.name` or `technique.name`) lets the broadcast
    helpers stay kind-agnostic.
  - `Technique.windup_rounds` (`world/magic/models/techniques.py`, PositiveSmallInt,
    default 0) / `RitualCheckConfig.sustained_rounds` (`world/magic/models/
    ritual_check_config.py`, same shape) — authored data; 0 is today's
    resolve-immediately behavior, unchanged for every existing row.
  - **Declaration (technique):** `_validate_no_pending_sustained` (`world/combat/
    services.py`) raises `ValueError` in `declare_action` when the participant is still
    holding a not-yet-matured commitment (`resolves_round__gte round_number` — a row
    maturing THIS round still blocks, since maturation only consumes it during
    RESOLVING and declaration only runs during DECLARING; `__gt` alone left that
    boundary open and let a colliding same-round `CombatRoundAction` get declared,
    which crashed `resolve_round` on `unique_action_per_participant_per_round` at
    maturation — #2705 adversarial review, Fix 1). Excludes only a TECHNIQUE row with
    `declared_round == round_number` — the current round's own in-progress
    commitment, which is the re-declaration case handled by
    `_sync_sustained_technique_declaration`'s delete-then-recreate, not a block. A
    same-round RITUAL row is never excluded that way (Fix 2b): a ritual is declared
    through `try_declare_sustained_ritual`, not `declare_action`, so there's no sync
    step here to replace it — one cannot conduct a ritual and also swing a sword the
    same round. Structural, not just thematic: `CombatRoundAction`'s
    `unique_action_per_participant_per_round` constraint means a same-round
    declaration on top of a pending commitment would collide with maturation's clone.
    `_sync_sustained_technique_declaration` runs unconditionally from `declare_action`,
    deleting any existing same-round **TECHNIQUE-kind** `SustainedAction` first
    (re-declare replaces, never stacks; scoped to TECHNIQUE since Fix 2a — an unscoped
    delete used to silently strand a same-round sustained ritual's already-consumed
    components), then creating a new one only when `technique.windup_rounds > 0`.
  - **Declaration (ritual):** `try_declare_sustained_ritual` (`world/combat/
    services.py`), called from `PerformRitualAction.execute()`
    (`actions/definitions/ritual.py`) after components are validated/consumed and
    before dispatch — components stay spent even if the commitment later breaks.
    Returns `None` (dispatch immediately, exactly as today) unless the performer is an
    ACTIVE `CombatParticipant` in a DECLARING encounter, `ritual.check_config_or_none
    .sustained_rounds > 0`, `kwargs` is empty (a ritual invoked with per-cast kwargs
    can't be deferred — persisting them would need a JSON field, which ADR-0007
    forbids), and the performer isn't already holding an earlier commitment. Unlike
    the declare-action guard this does NOT raise on that last case — a ritual
    invocation isn't the round-declaration seam, so blocking outright would strand
    components already consumed inside the same atomic transaction; it just falls
    through to immediate dispatch.
  - **The budget roll:** `get_concentration_check_type()` (mirrors
    `get_penetration_check_type` — `CheckType.objects.get(name="Concentration")`,
    never `get_or_create`) + `roll_sustained_absorption_budget(participant)` — rolls
    via `perform_check_with_modifiers` (NOT plain `perform_check` — only the
    `_with_modifiers` wrapper folds in `ConditionCheckModifier`, and the 26 authored
    Concentration modifier rows across 9 lore fixtures are the entire payoff of
    rolling this check at all), then `budget = clamp(SUSTAINED_BASE_ABSORPTION (2) +
    result.success_level, SUSTAINED_MIN_ABSORPTION (0), SUSTAINED_MAX_ABSORPTION (4))`
    (`world/combat/constants.py`). Clamped because `CheckOutcome.success_level` is an
    authored -10..+10 field with no lore-authored ladder to pin it — Base 2 puts a
    clean Success at 3, landing exactly on ADR-0161's `WINDUP_FIZZLE_DOWNGRADES`.
  - **Erosion:** `_apply_sustained_erosion_rider(participant, damage_dealt)`, called
    from `apply_damage_to_participant` once the final applied damage is known — the
    PC-side sibling of `_apply_windup_interception_rider`. `damage_dealt > 0` on a
    participant with a not-yet-matured `SustainedAction` (`resolves_round__gte`
    current round) adds a flat `SUSTAINED_HIT_DOWNGRADE` (1) — no called-out split
    (a PC's sustain is telegraphed publicly the moment it's declared, so there's
    nothing to "call out").
  - **Maturation:** `_mature_sustained_actions(encounter, round_number)` runs in
    `resolve_round` immediately after `_mature_pending_opponent_attacks`, same pass,
    before the round's `CombatRoundAction` rows are queried, so a matured technique's
    cloned row is picked up by the normal PC pipeline unmodified.
    `_mature_one_sustained_action` breaks (no refund — the cost stands) when
    `downgrades > 0 and downgrades >= absorption_budget` (requires an actual landing
    hit, not just the floor — a Critical-Failure budget of 0 must break on the
    participant's FIRST HIT, not fizzle an untouched commitment in total safety at
    maturation; `downgrades >= budget` alone let `0 >= 0` fire with zero hits taken —
    #2705 adversarial review, Fix 5) or the holder can no longer hold it together
    (left the encounter / died, distinct "comes to nothing" narration); otherwise
    TECHNIQUE clones `declared_action`'s fields into a brand-new `CombatRoundAction`
    row via `.objects.create()` from a field dict (deliberately NOT the plan's literal
    `clone.pk = None` recipe — mutating the idmapper-cached fetched instance in place
    and re-saving reassigns a new pk to the SAME cached Python object without updating
    the idmapper's cache entry for the ORIGINAL pk, so a later `.objects.get(pk=
    <declaring round's pk>)` would silently return the maturation round's data; see
    the docstring in `services.py` for the full trap), resetting `from_entrance`
    (else a windup declared as a dramatic entrance spuriously re-fires
    `_maybe_suggest_entrance_dramatic_moment` N rounds later — Fix 4) and `maneuver`/
    `item_instance` (belong to the declaring round's action shape, not the matured
    cast) while deliberately PRESERVING `confirm_soulfray_risk` and the cast geometry
    FKs (`cast_destination`/`cast_position_a`/`cast_position_b`/
    `redirect_opponent_target`/`redirect_object_target` — these describe the declared
    cast itself), copying `CombatRoundActionTarget` rows via `bulk_create`; RITUAL
    dispatches via `dispatch_ritual` (`world/magic/services/ritual_dispatch.py`),
    catching only the same ritual-surface exceptions `PerformRitualAction` already
    catches (a content-authoring gap in one participant's ritual must not abort round
    resolution for everyone).
  - **Encounter-completion teardown (#2705 adversarial review, Fix 3):**
    `cleanup_completed_encounter` — the seam every production completion path
    (`complete_encounter`, called from round-resolution auto-complete, `end_encounter`,
    duel completion) unconditionally reaches — calls
    `_break_pending_sustained_actions(encounter)` first, breaking (broadcast + delete,
    no refund) every `SustainedAction` still on the board when the encounter ends
    early. Before this, an encounter completing before a commitment's `resolves_round`
    arrived (last enemy killed mid-ritual, GM abandons, everyone flees) orphaned the
    row forever — it never matured, never narrated, and a RITUAL row's already-
    consumed components bought nothing. `PendingOpponentAttack` (the NPC mirror) has
    the same pre-existing gap, deliberately NOT fixed here — out of scope, no
    consumed-cost consequence.
  - **The declaring round is skipped**, not resolved: `resolve_round` collects
    `SustainedAction.objects.filter(declared_round=round_number)`'s participant ids and
    excludes them from that round's PC resolution loop — that round's
    `CombatRoundAction` is the declaration, not an action to resolve yet.
  - **Ritual dispatch extraction:** `dispatch_ritual` (`world/magic/services/
    ritual_dispatch.py`) — the SERVICE/FLOW/CEREMONY switch extracted verbatim out of
    `PerformRitualAction._dispatch_service`/`_begin_ceremony`/`_dispatch_flow`, so a
    ritual conducted over combat rounds can dispatch at maturation through the exact
    same switch the synchronous non-combat path uses, with no second copy. Behavior-
    preserving — the pre-existing ritual action/service tests are its oracle; none
    changed.
  - **Broadcasts:** `_broadcast_sustained_telegraph`/`_broadcast_sustained_erosion`/
    `_broadcast_sustained_broken`/`_broadcast_sustained_held`
    (`world/combat/services.py`) — PC wrappers alongside the existing `_broadcast_
    windup_*` NPC ones, both funneling into a shared `_broadcast_commitment_line`
    core (`_dual_dispatch_combat_narration`); the two rows carry different subjects
    (`opponent.name` vs a participant's character + `subject_name`), so only the
    dispatch is shared, not a row-polymorphic narration builder.
- **Sent Flying — consequence events in flight (#2638; ADR-0162 — clones #1228's plummet
  pattern: marker + reactable window + explicit resolution):**
  - `ThreatPoolEntry.sends_flying` (bool, default False) — authored data on existing threat
    pools; pairs naturally with `windup_rounds`. `CombatParticipant.sent_flying_damage`
    (PositiveIntegerField, default 0) is the v1 damage carrier (the marker is
    non-stackable, so a single field is sufficient — cleared to 0 on catch or landing).
    `CombatOpponentAction.matured_from_called_out_windup` (bool, default False) survives
    the `PendingOpponentAttack` row's deletion at maturation so the celebration broadcast
    can still credit the wind-up's caller.
  - **Content** (`world.combat.sent_flying_content.ensure_sent_flying_content`, wired into
    the `"combat"` seed cluster — see that module's docstring for why not yet the
    `"reactive_challenges"` cluster #2636 introduced): the "Sent Flying"
    `ConditionTemplate` (no stages, no DoT, `PERMANENT` duration — NOT a literal
    `ROUNDS`/1, despite the design doc's "1-round marker" shorthand; see ADR-0162) reusing
    Plummeting's own `Falling` `ConditionCategory`, plus a dedicated "Physical"
    `DamageType` for the hard-landing impact.
  - **Trigger:** `_trigger_sent_flying` (`world/combat/services.py`), called from
    `_resolve_npc_action_on_target` whenever `threat_entry.sends_flying` and the landed
    `dmg_result.damage_dealt > 0` — applies the marker, stamps the damage carrier,
    dual-dispatches the produced-moment narration, then immediately consults the catch seam.
  - **The catch seam:** `_try_catch_sent_flying` reuses `_try_interpose`'s query shape (an
    armed INTERPOSE this round, named or guard-anyone) but never calls `dispatch_interpose`
    — a mid-air catch is a binary rescue, not gradeable damage mitigation, so it never rolls;
    "fires" means clearing `REACTIONS_PER_ROUND` (mirrors `_dispatch_interpose_action`'s own
    "fire = attempt, not success" vocabulary). `ABSORPTION_CAP_PER_MOMENT` is not consulted
    — only the first eligible guardian is ever queried (documented v1 scope).
  - **Explicit resolution:** `_resolve_sent_flying_markers`, called at the end of
    `resolve_round` (after `tick_round_for_targets`, before boss/completion transitions —
    deliberately after the generic duration tick, since a literal ROUNDS/1 duration would
    race it). A marked participant either gets launched into a CHASM Position and handed to
    the existing `maybe_emit_fall` → `begin_plummet` machinery (zero new descent code), or
    takes `floor(sent_flying_damage * SENT_FLYING_IMPACT_FRACTION)` (0.5) Physical damage
    through the standard `apply_damage_to_participant` + `process_damage_consequences` path
    with NO extra narration — the celebrate/silence boundary (rescues are loud, absences are
    unremarked).
  - **Situation:** `Situation.ALLY_SENT_FLYING` (`world.covenants.perks`) — true while a
    covenant-mate co-present in the subject's encounter currently carries the marker; mate
    scoping mirrors `ALLY_LOW_HEALTH`/`ALLY_INTERCEPTED_FOR_ME` exactly. No params.
  - **Bug fix folded in:** `_try_interpose`'s (and the new catch seam's)
    `focused_ally_target__in=[participant, None]` never actually matched a guard-anyone
    declaration — Django drops a `None` `__in` member instead of adding `OR IS NULL`. Both
    now use `Q(focused_ally_target=participant) | Q(focused_ally_target__isnull=True)`.
- **Enums:** `CombatManeuver` (FLEE / COVER / YIELD / INTERPOSE / SUCCOR / ENGAGE / DISENGAGE / RALLY / DEMORALIZE / TAUNT / PARLEY / USE_ITEM), `OpponentMoraleState` (STEADY / FALTER / BREAK — derived, `world.combat.morale`), `RoundStatus` (shared with
  `world.scenes.constants`; combat uses the same enum — DECLARING / RESOLVING / BETWEEN_ROUNDS /
  COMPLETED), `OpponentTier`, `ClashFlavor`, `EncounterOutcome`
- **API:** `/api/combat/` — GM lifecycle (begin_round, resolve_round, add/remove
  participant, add opponent, pause), player actions (declare, ready, interpose, cover,
  yield, flee, use_item, my_action, available_combos, rally, demoralize, taunt, parley),
  duel challenge endpoints. **Round combos (#3553):** `available_combos` returns
  `RoundComboSerializer` rows from `scan_round_combos` — every combo taking shape this round
  with each slot filled or open (`ComboSlotFill`: requirement + filler), the
  `bonus_damage`/`bypass_soak` rider and `complete`; `detect_available_combos` is its complete
  fills. A partial fill is listed only for a combo an active PC in the encounter knows
  (knowledge counts before the knower declares), so the party sees "needs one more: Defense"
  while the round is open; unknown combos surface only once complete. Telnet mirror:
  `combat combos`. **Guard declaration (#2207):** `InterposeSerializer`
  (`world/combat/serializers.py`) only carries `ally_participant_id` — the optional
  `technique_id` (protective technique) and, since #2210, `redirect_opponent_target_id`/
  `redirect_object_target_id` have no bespoke REST verb, so the web Guard panel
  dispatches through the generic REGISTRY path instead
  (`POST /api/actions/characters/{characterId}/dispatch/` with
  `registry_key: "combat_interpose"`, `actions/definitions/combat_maneuvers.py`), the
  same seam bespoke-verb-less maneuvers already use. **Redirect picker data (#2210):**
  `EncounterDetailSerializer.volatile_objects` — objects in the encounter room carrying
  a detonatable `ObjectProperty` (`{id, name, position_id, position_name}`), single
  query with `select_related` across the Position OneToOne link.
- **Web (#2207/#2210):** a "Guard" panel in `YourTurn` (`frontend/src/combat/sections/
  YourTurn.tsx`) — a ward select (any-ally default or a named participant) plus an
  optional protective-technique select sourced from `PlayerAction.protective_flavor`
  (`barrier`/`blink`/`redirect`/`null`). Since #2210, picking a `redirect`-flavored
  technique reveals a destination select (Away / `encounter.opponents` / `encounter.
  volatile_objects`) — dispatches via `useGuardMutation`'s `redirectOpponentTargetId`/
  `redirectObjectTargetId` args (`frontend/src/combat/queries.ts`) and shows a
  "Guarding" badge once armed. **Soulfray consent + fee (#3573):** when a protective
  technique is selected, a `guard-soulfray-toggle` checkbox (fee read from
  `PlayerAction.reactive_anima_cost`, anima from `useCharacterAnima`) lets the
  guardian consent up front to hold the ward alive past zero anima by drawing on
  Soulfray - `confirm_soulfray_risk` rides `useGuardMutation`'s `confirmSoulfrayRisk`
  arg; resets to false when the technique select reverts to mundane. The focused cast
  card carries the same consent for a ward-bearing technique with no active Soulfray
  warning (`cast-ward-soulfray-toggle`, bound to the existing `soulfrayAccepted`
  state) - when a warning IS active, `SoulfrayAcceptGate`'s acceptance alone covers
  both. The real out-of-combat integration point (party wards) is the standalone
  cast panel (`ActionPanel.tsx`'s `castableTechniques` list), not the technique-
  enhancement path: a selected technique's `reactive_anima_cost` (exposed via
  `CastableTechniqueSerializer`) drives its own `cast-ward-soulfray-toggle`, which
  sends `soulfray_consented: true` through `castTechnique` - see the
  `TechniqueCastCreateSerializer.soulfray_consented` note in `docs/systems/magic.md`
  for the full wire-to-`ConditionInstance.soulfray_consented` path.
- **Telnet parity (#2207/#2210):** `combat interpose [ally] [with <technique>] [into
  <destination>]` (`CmdCombat._resolve_interpose_args`, `src/commands/
  combat_maneuvers.py`) — all three clauses optional; `with <technique>` splits on
  `" with "` (mirrors `CmdClashCommit`'s split) and resolves the technique name via
  `_find_technique_id`, which already gates on the caller knowing it (defense-in-depth
  alongside the service-layer gate in `declare_interpose`). `into <destination>`
  (#2210) further splits the technique clause on `" into "`; `_resolve_redirect_
  destination` resolves the name against an active opponent first, then a room
  object; `into away` (or omitting the clause) is the default. Works ally-less:
  `combat interpose with <technique> into <destination>`.
- **Standalone-cast offense flavor catalog (#1995):** `world.combat.seeds_offense`
  (`ensure_melee_offense_pool()` / `ensure_combat_offense_catalog_content()`) seeds a base
  "Combat: Melee Offense" `ConsequencePool` + curated "Brutal"/"Precise" flavor children,
  wired onto the "Melee Attack" `ActionTemplate` (`world.combat.factories
  .wire_melee_attack_action_template`) — the PHYSICAL-category sibling of magic's
  "Magic: Technique Cast" catalog (#1320, see `docs/systems/magic.md`). **This catalog is
  standalone-cast only** — combat ROUND resolution never reads
  `ActionTemplate.consequence_pool` (it resolves its own `on_hit_consequence_pool` /
  `resolution_consequence_pool` / `per_round_consequence_pool` rows instead); see ADR-0130.
- **Integrates with:** scenes (`ensure_scene_for_location`, `ensure_scene_participation`),
  vitals (`apply_damage_to_participant`, `process_damage_consequences`),
  conditions (`bulk_apply_conditions` — now installs reactive side-effects;
  `is_untargetable` for intangibility gate; `ConditionCategory.grants_intangibility`),
  mechanics (`dispatch_capability_reaction`, `resolve_challenge`),
  flows (`DAMAGE_PRE_APPLY` event; `COMBAT_ROUND_STARTING` event; `MODIFY_PAYLOAD` flow
  action for DEFEND; reactive-defense handlers in `world/magic/services/effect_handlers.py`),
  covenants (speed_rank resolution order, `apply_equipped_armor_soak`),
  magic (technique use pipeline, `CombatPull`, effect palette — summon/reactive handlers)
- **Test composition helper:** `BossFightScenarioFactory` (`world/combat/factories.py`,
  #2095) composes a full 3-PC-vs-boss encounter (distinct-EffectType techniques, a
  learned PC1/PC2 combo, a BOSS opponent with 3 authored `BossPhase` rows — break bar +
  phase-2 reinforcement + phase-3 enrage — and a threat pool carrying both a flat-damage
  entry and a `conditions_applied` entry) in one call, mirroring
  `PlayableCombatScenarioFactory`'s style; use it instead of hand-rolling boss-fight
  fixtures. Driven end-to-end by `src/integration_tests/test_boss_fight_journey.py`.
- **Engagement locks — foil duels (#2020, player surface #3386):** `EngagementLock`
  (`world/combat/models.py`) pairs one PC to one opponent; while ACTIVE the locked
  opponent's targeting narrows to just that PC (`_build_opponent_round_actions`,
  `world/combat/services.py`). #2020 shipped the whole mechanic (threat tracking,
  autonomous lock formation past `auto_lock_threshold`, boss-suppression consumer —
  see the break-bar entry above) but left its two player entry points unreachable
  until #3386: `EngageAction`/`DisengageAction` (`actions/definitions/
  combat_maneuvers.py`, registry keys `combat_engage`/`combat_disengage`) are now
  routed from telnet `combat engage <opponent>`/`combat disengage`
  (`CmdCombat._SUBVERBS`, `src/commands/combat_maneuvers.py`) — the same REGISTRY
  keys the web reaches generically via `useDispatchPlayerAction`
  (`{ ref: { backend: 'registry', registry_key: 'combat_engage' }, kwargs: {
  opponent_id } }`). **Web click affordance (#3447):** the opponent click-menu on
  `CombatantsList.tsx` now carries "Engage in a duel" (hidden while anyone holds
  the lock) and "Disengage" (shown only when the viewer's own participant holds
  it — resolved via `character_sheet_id` against the viewer's character pk, which
  CharacterSheet shares with ObjectDB), both dispatching the registry keys through
  the same generic seam as the #3381 maneuvers.
  `EncounterDetailSerializer.get_engagement_locks` is schema-typed via
  `@extend_schema_field(EngagementLockSerializer(many=True))` (mirrors
  `get_clashes`/`ClashStateSerializer`), and `CombatantsList.tsx` renders a
  read-only "Locked: `<name>`" badge on both rows of the pair (opponent row
  since #3386, PC row since #3555). **Map overlays (#3555):** `CombatTacticalMap`
  also draws the lock as a `locked` glyph on both occupants' avatars plus an
  animated link edge between their positions, a behind-cover glyph on every
  occupant of a rampart-covered node, and `covering`/`covered` glyphs from the
  round's declared cover maneuver; the target picker's out-of-reach buttons now
  show the hop count (`hopDistance` in `combat/reach.ts`, "2 positions away" /
  "no path"). See [areas.md](areas.md#frontend-built--wired).
  **Lock-lifecycle close-out (#3386):** fleeing while locked now breaks
  the lock (`LockBreakReason.FLEE`, `_resolve_flee` in `world/combat/services.py`)
  alongside the pre-existing defeat-breaks-lock and disengage-breaks-lock paths —
  a PC who flees no longer leaves a phantom pairing behind.
  **Interference beat armed (#3447):** `trigger_interference_drama`
  (`world/combat/engagement_locks.py`) — zero callers since #2020 — now fires from
  `_maybe_trigger_lock_interference` in `apply_damage_to_opponent`: a non-locked
  PC landing post-soak damage on a locked opponent fires the locked duelist's
  `break_in_consequence_pool` + INTERFERENCE dramatic surge, deduped per
  (duelist, interloper) per encounter via the `DramaticSurgeRecord` trail.
- **Duels — `DuelChallenge` + GM-initiated lethal duels (#568, #3068):** `DuelChallenge`
  (`world/combat/models.py`) is the one challenge/accept/decline/withdraw handshake model
  for BOTH shapes: PC-vs-PC (`challenger_sheet` set, accepting opens `create_pvp_duel`) and
  GM-initiated lethal (`is_lethal=True`, `challenger_sheet` NULL — the challenger is a
  significant NPC named by `opponent_name`/`opponent_tier`/`threat_pool`, accepting opens
  `create_lethal_duel` instead). `world.combat.duels.create_lethal_duel_challenge` creates
  the PENDING lethal row (validates `tier` against `constants.SIGNIFICANT_NPC_TIERS` — ELITE/
  BOSS/HERO_KILLER); `accept_challenge` branches on `is_lethal` to pick which encounter
  constructor to call. `world.combat.duels.SIGNIFICANT_NPC_TIERS` (promoted from a
  `create_lethal_duel`-local constant, #3068) is the one significant-NPC-tier source of
  truth both the service layer and `ProposeLethalDuelSerializer` validate against.
  **Non-negotiable consent invariant:** a GM's proposal never creates a `CombatEncounter`
  by itself — only the targeted PC's own `accept` (the same `AcceptChallengeAction`/`duel
  accept` a PvP challenge uses) does; `decline` leaves no encounter. GM initiation surfaces:
  web `POST /api/combat/duel-challenges/propose_lethal_duel/`
  (`DuelChallengeViewSet.propose_lethal_duel`, gated by `IsEncounterGMOrStaff` — widened
  #3068 from `{"create"}` to also cover this action, same staff-or-scene-GM-or-owner scene
  gate `CombatEncounterViewSet.create` uses) via the `GMEncounterControls` "Start Lethal
  Duel" dialog (`frontend/src/combat/sections/GMEncounterControls.tsx`); telnet `encounter
  duel <character> <name> <tier> <pool>` (`ProposeLethalDuelAction`,
  `actions/definitions/duels.py`, `src/commands/encounter.py`). The player's accept/decline
  step rides the pre-existing `DuelChallengeNotifier` toast (site-wide, #2157) — extended to
  read `opponent_name` when `challenger` is null and show a fight-to-the-death warning; no
  new player-facing verb exists, only a new challenge *shape* the existing one carries. The
  Battle system's champion-duel path (`world.battles.services.open_champion_duel`) is the
  OTHER `create_lethal_duel` caller — player-initiated (the Champion chooses to fight), no
  challenge handshake, preserved unchanged as a first-class consumer of the same service.
  **Known frontend gap (#3068 audit finding, not a backend limitation):** the DB model puts
  no constraint on how many `CombatEncounter` rows share one `Scene` (`scene` is a plain FK,
  and `create_lethal_duel`/`create_pvp_duel` each open their own new encounter), so several
  simultaneous duel confrontations in one wider scene ARE structurally supported and
  DB-proven (two PENDING lethal challenges + two accepts → two independent
  `CombatEncounter`s, same scene). But the scene-level web UI
  (`useEncounterForScene`/`GamePage`/`SceneDetailPage`/`SceneHeader`) resolves and renders
  only the single most-recent non-completed encounter per scene — a second simultaneous
  duel's `CombatRail` does not surface automatically there. Reaching it needs its own
  `encounterId` (e.g. a future multi-encounter picker); out of scope for #3068 (a GM-verb +
  consent-flow issue, not a scene-UI-architecture one) — flagged here rather than hacked
  around.
- **Source:** `src/world/combat/`
- **Details:** `docs/roadmap/combat.md` · architecture:
  `docs/architecture/combat-magic-integration.md`,
  `docs/architecture/damage-scaling.md`,
  `docs/architecture/combat-conditions.md`,
  `docs/systems/COMBAT_DEFENSES.md`

### Battles (#1592)
Large-scale battle scenes (war covenant engagements, sieges, pitched fields) resolved
through abstract round-based VP mechanics. `Battle` is a 1:1 extension of `scenes.Scene`.

- **Models:** `Battle` (O2O Scene, `campaign_story` FK, `round_limit`, `outcome` / `concluded_at`;
  `is_concluded` property; `current_round` property; `region` FK → `areas.Area`, nullable —
  seeds ambient weather via `get_effective_weather(region)`; `weather_override` /
  `weather_override_expires_round` — the battle-wide default set by a `BATTLE`-scoped
  `SET_ENVIRONMENT` cast, #1715), `BattleSide` (`role` ATTACKER/DEFENDER,
  `covenant` FK → `covenants.Covenant` (nullable, #1710) fielding this side, `posture`
  (`BattlePosture`, #1711), `victory_points`, `victory_threshold`; unique `(battle, role)`),
  `BattlePlace` (named front; `combat_encounter` FK bridge seam; `terrain_type`
  (`TerrainType`, #1711); `movement_cost` (authored, no consuming action yet, #1711);
  `controlled_by` FK → `BattleSide`, nullable, set by a successful HOLD declaration, #1712;
  `weather_override` / `weather_override_expires_round` — a `PLACE`-scoped local exception
  that beats the battle-wide value at this front only, #1715),
  `BattleUnit` (`descriptor` free-text flavor tag — renamed from the spine's `unit_type`,
  #1711; `properties` (M2M → `mechanics.Property`, presence-only tags) and `capabilities`
  (M2M → `conditions.CapabilityType` through `BattleUnitCapability`, authored per-unit
  magnitude) replace #1711's single-select `composition`/`UnitComposition`, #1794;
  `individual_count` (nullable, mirrors `CombatOpponent.swarm_count`'s naming, #1794;
  drives a banded STRIKE bonus + proportional STRIKE/ROUT body loss via
  `swarm_strike_modifier`/`_apply_swarm_losses`, #1841); `quality` (`UnitQuality`) drives mechanics, #1711; `commander` / `summoned_by` FK
  → `character_sheets.CharacterSheet`, #1711; `strength` attrited by STRIKE; `morale` — a
  second resource, starts well below its ceiling, damaged by ROUT / restored by RALLY,
  #1712; `status` always DERIVED jointly from `strength` + `morale` via
  `resolution._compute_unit_status`, never written directly; `effective_capability`/
  `has_property` conform to `mechanics.types.HasCapabilities`/`HasProperties`, #1794),
  `BattleUnitCapability` (authored `(unit, capability) → magnitude` through row, #1794;
  unique `(unit, capability)`),
  `BattleRound` (subclasses `AbstractRound`; partial unique constraint: one active round per
  battle), `BattleParticipant` (`character_sheet` FK, `side`, `place`, `status`; unique
  `(battle, character_sheet)`), `BattleActionDeclaration` (`technique` FK required,
  `action_kind` STRIKE/SUPPORT/RESCUE/ROUT/RALLY/REPEL/HOLD/BREACH/FORTIFY (#1713),
  `target_unit`, `target_ally`,
  `scope` (`BattleActionScope` UNIT/PLACE/SIDE, #1710) + `target_place`/`target_side`,
  `target_fortification` (#1713, set for BREACH/FORTIFY),
  `resolved`, `success_level`; unique `(battle_round, participant)`);
  `TechniquePropertyAffinity` / `TerrainPropertyEffect` (authored type-matchup /
  terrain-effect catalogs keyed on `Property`, summed across a unit's matching properties,
  #1794, replacing #1711's `TechniqueCompositionAffinity`/`TerrainCompositionEffect`);
  `WeatherTypePropertyEffect` / `WeatherTypeCapabilityChallenge` (authored
  `(weather_type, property) -> modifier` / `(weather_type, capability, threshold) -> modifier`
  catalogs, #1715 — mirror `TerrainPropertyEffect`'s shape but key on the place's *effective*
  weather rather than static `terrain_type`; `WeatherTypeCapabilityChallenge` is the first
  absence/threshold-based battle modifier, applying when `effective_capability(capability)`
  falls strictly below `threshold`);
  `BattleOutcomeMapping` (`BattleOutcome` → `CheckOutcome`
  tier for beat resolution, #1785); `Battle.afk_peril_override` (BooleanField, default
  False — narrow ADR-0004 exception for Surrounded peril escalation, #1733);
  `Fortification` (#1713: a defensible structure — wall/gate/battlement — at a
  `BattlePlace`; `defending_side` FK gates BREACH/FORTIFY ownership; `building` FK →
  `buildings.Building` (nullable) snapshots `max_integrity` from
  `Building.fortification_level`; `integrity`/`max_integrity`/`breached`);
  `BattleVehicle` (#1714: a ship/airship/dragon/kraken modeled as one in-fiction
  object pairing a `unit` O2O → `BattleUnit` (the thing that fights) with a
  `place` O2O → `BattlePlace` (what other units/participants embed onto via
  their own `place` FK); `vehicle_kind` (`VehicleKind` SHIP/AIRSHIP/DRAGON/KRAKEN);
  `is_structural` (default True — structural vehicles get a hull `Fortification`
  via `create_battle_vehicle`; living mounts route destruction through
  `BattleUnitStatus.DESTROYED` instead); `BattlePlace.x`/`y`/`footprint_radius`
  (#1714, ADR-0085) place every `BattlePlace` on a shared battle-map plane —
  `places_overlap` compares two footprints' center distance against the sum of
  their radii)
- **Key Services (`world.battles.services`):**
  - Setup: `create_battle`, `add_side`, `add_place`, `add_unit` (`properties`/
    `capability_values`/`individual_count` kwargs, #1794), `enlist_participant`,
    `set_battle_side_posture` (#1711), `assign_unit_commander` (#1711),
    `create_fortification` (snapshots `max_integrity` from `Building.fortification_level`
    if a `building` is given, #1713)
  - Lifecycle: `begin_battle_round` (opens DECLARING round; raises `BattleConcludedError`;
    the first round open also calls `activate_stakes_for_battle` - scoped to
    `battle.story_beat` alone when it is set and itself a staked, still-UNSATISFIED
    beat, else falling back to every staked beat sharing `battle.scene`, #3569, so a
    battle pre-staged onto one beat via session prep never also locks a sibling
    staked beat that merely shares its scene - see battles.md's "Stakes / Beat Wiring"),
    `declare_battle_action` (requires `technique`; update_or_create; now dispatches 11
    `BattleActionKind` values; scope/command-tier validated for PLACE/SIDE, #1710;
    REPEL/HOLD require scope=PLACE, #1712; BREACH/FORTIFY validate `target_fortification`
    ownership, #1713; SET_ENVIRONMENT requires scope=BATTLE or PLACE and a
    `technique.target_weather_type`, #1715; REPOSITION bypasses the command-tier gate,
    validated instead against `target_place.vehicle.unit.commander`, #1714; a UNIT-scope
    STRIKE against a non-overlapping `target_unit`, or a BREACH against a non-overlapping
    vehicle hull, is rejected via `places_overlap` regardless of command tier — the
    boarding gate, #1714),
    `open_champion_duel` (binds a `BattlePlace` to a
    lethal duel via `create_lethal_duel`, gated on an engaged `is_champion_role`, #1710),
    `open_siege_engine_encounter` (same bridge/duel call, no Champion-role gate, #1713)
  - Vehicles (#1714): `create_battle_vehicle` (creates a paired `BattleUnit` +
    `BattlePlace`, plus a hull `Fortification` if `is_structural`), `places_overlap`
    (predicate: do two `BattlePlace` footprints intersect on the battle map, ADR-0085),
    `eject_vehicle_occupants` (clears embedded units'/participants' `place` FK and
    applies a drowning/falling hazard consequence; called from resolution on hull
    breach or living-mount defeat)
  - Conclusion: `check_victory` (graded outcome: decisive if margin ≥ 50, else marginal),
    `conclude_battle` (sets outcome + ends scene; resolves the one story beat this
    battle grades, if any, via `resolve_battle_beats`, #1785, #3559; runs every registered
    `battles.conclusion_hooks` hook, including win-gated Legend wiring below; still never
    calls `complete_story`),
    `maybe_conclude_on_timer` (timeout: defender holds unless attacker met threshold)
- **Legend wiring (`world.battles.legend_wiring`, #2184):** `apply_battle_legend_awards`
  — a `battles.conclusion_hooks` hook (`battles` importing `societies`, the ratified
  direction, both general/reusable systems). Win-gated `create_legend_event` ("Victory at
  {battle.name}") for the winning `BattleSideRole`'s participants + unit commanders (25
  decisive / 12 marginal, `BattleOutcome`-driven); a separate standout pass
  (`create_solo_deed`, 15) fires for *either* side on a resolved RESCUE/ROUT/BREACH
  declaration with `success_level >= 2` — stacks with the victory event. Idempotent via a
  lazy `"Battle"` `LegendSourceType` existence check on `battle.scene`. See
  [battles.md](battles.md#legend-wiring-2184), ADR-0122.
- **Resolution (`world.battles.resolution`):** `resolve_battle_round(battle_round)` →
  `BattleRoundResult` — casts each declaration's `technique` via `resolve_battle_technique`
  (routes through the real `use_technique` magic envelope, not a generic shared check),
  folding in the full modifier stack (Property affinity, terrain, weather property/
  capability, unit quality, swarm-count band bonus, commander bonus, posture, move cost —
  #1711/#1794/#1715/#2007/#1841); REPEL resolves before every other kind so its defense
  bonus is live for STRIKE in the same round (#1712). STRIKE/ROUT attrite
  strength/morale + award VP; SUPPORT/REPEL/HOLD award flat VP; RALLY restores morale;
  RESCUE clears Surrounded; BREACH attrites a `Fortification`'s `integrity` (setting
  `breached=True` at 0) + awards VP; FORTIFY restores it (capped at `max_integrity`) +
  awards flat VP (#1713); failure debits PC health + `process_damage_consequences`. A
  swarm-style target (`individual_count` not None) also loses bodies proportional to
  STRIKE's net attrition / ROUT's actual morale loss via `_apply_swarm_losses` (#1841).
  Returns `BattleRoundResult(vp_awarded, units_destroyed, units_routed, casualties,
  unit_losses)`.
  `BattleTechniqueResolver` is the `resolve_fn` passed to `use_technique`.
- **Round context (`world.battles.round_context`):** `BattleRoundContext(RoundContext)` —
  wired into `get_active_round_context` (after combat branch); `resolve_battle_round_context`
  finds the character's ACTIVE participant in an active-scene battle.
- **Action Keys:** `begin_battle_round` / `resolve_battle_round` / `conclude_battle` (GM,
  `target_type=AREA`) · `declare_battle_action` (player, `target_type=SELF`, requires
  `technique_id`; forwards `action_kind`/`target_unit`/`target_ally`/`scope`/
  `target_place`/`target_side`/`target_fortification` — all 12 `BattleActionKind` values,
  including BREACH/FORTIFY, are reachable through this Action, see
  [battles.md](battles.md#sieges-1713)) ·
  `challenge_champion_duel` (player, `target_type=AREA`, #1710)
- **Telnet:** `battle [declare strike|support|rescue|rout|rally|repel|hold|breach|fortify|
  set_environment|move|reposition ... with <technique>|duel <front> vs <boss name>|round|
  resolve|conclude]` — `strike`/`rout`/`rally` also accept `side` or `place <name>` scope
  tokens (#1710/#1712); `breach`/`fortify` require `place <name> fortification <kind>`
  (#1713).
- **Enums:** `BattleSideRole`, `BattleUnitStatus`, `BattleParticipantStatus`,
  `BattleActionKind` (12 values, #1713 adds BREACH/FORTIFY, #1714 adds REPOSITION,
  #1715 adds SET_ENVIRONMENT, #2007 adds MOVE),
  `BattleActionScope` (#1710),
  `BattleOutcome`, `UnitQuality`, `TerrainType`, `BattlePosture` (all #1711),
  `FortificationKind` (WALL/GATE/BATTLEMENT, #1713; HULL added for vehicle hulls, #1714),
  `VehicleKind` (SHIP/AIRSHIP/DRAGON/KRAKEN, #1714)
- **Exceptions:** `BattleError` (base + `user_message`) → `BattleConcludedError`,
  `RoundNotOpenError`, `NotAParticipantError`, `CharacterDoesNotKnowTechniqueError`,
  `TechniqueNotBattleReadyError`, `NoCommandHierarchyError`, `InsufficientCommandTierError`,
  `MissingScopeTargetError`, `CannotStrikeOwnSideError` (#1710; guards STRIKE and ROUT
  since #1712), `NotAChampionError`,
  `PlaceAlreadyDuelingError` (#1710; also raised by `open_siege_engine_encounter`, #1713),
  `PlaceScopeRequiredError` (#1712; also raised for REPOSITION outside PLACE scope, #1714),
  `FortificationTargetRequiredError`,
  `FortificationOwnershipMismatchError`, `FortificationAlreadyBreachedError` (#1713),
  `NotVehicleCommanderError` (REPOSITION by a non-commander, #1714),
  `PlacesDoNotOverlapError` (UNIT-scope STRIKE or BREACH targeting a non-overlapping
  place — the boarding gate, #1714)
- **Command Hierarchy & the Champion (#1710):** `CovenantRole.command_tier`
  (NONE/SUBORDINATE/SUPREME) + `.is_champion_role`, settable only on `CovenantType.BATTLE`
  roles; `BattleSide.covenant` links a side to the fielding War Covenant. PLACE/SIDE-scope
  declarations fan out across every unit/participant at the scope target instead of a
  single one. The Champion duel reuses `create_lethal_duel` unmodified, binding the
  `CombatEncounter` to `BattlePlace.combat_encounter`; outcome feedback (rout/destroy the
  loser's unit, VP bonus to the winner) is wired via `world.battles.duel_wiring`.
- **Battle-flow actions (#1712):** `BattleUnit.morale` is a second numeric resource
  alongside `strength` — `status` is always derived jointly from both. ROUT damages an
  enemy unit's morale (own-side excluded); RALLY restores a friendly unit's morale
  (including already-ROUTED units); REPEL/HOLD are PLACE-scope only — REPEL raises a
  same-round STRIKE-defense bonus at a front, HOLD captures/sustains
  `BattlePlace.controlled_by`. No action kind denies/subtracts VP from a side (award-only).
- **Environmental weather (#1715, ADR-0084):** two-tier — `Battle.region`/`weather_override`
  is the battle-wide default (`BATTLE`-scoped `SET_ENVIRONMENT` cast, or ambient-seeded from
  `region` via the Weather system's `get_effective_weather`, see the "Weather" section);
  `BattlePlace.weather_override` (`PLACE`-scoped cast) is a local exception that beats it at
  one front only. `resolution.effective_weather(place)` resolves the precedence: place
  override → battle override → ambient → none, each with a round-count expiry
  (`weather_override_expires_round`, cleared at round-boundary). Feeds the same
  modifier-stack resolvers as terrain via `WeatherTypePropertyEffect`/
  `WeatherTypeCapabilityChallenge`. `world.weather` internals are unchanged — battles only
  ever calls `get_effective_weather(area)` read-only, never writes into `RegionWeatherState`.
- **Peril / Rescue (#1733):** isolated participants can be Surrounded — a staged,
  3-stage acute-peril `ConditionTemplate` (seeded by
  `world.vitals.factories.ensure_surrounded_content`) resolved through the same
  guarded-consequence-pool core (`_resolve_peril_via_pool`) Bleeding-Out uses. Entry
  roll on isolated declaration failure (`_maybe_apply_surrounded`); per-round escalation
  tick gated on declaring-this-round or `Battle.afk_peril_override`
  (`_advance_surrounded_participants` / `advance_surrounded`); terminal stage routes to
  an enemy-vs-pvp pool (`select_surrounded_terminal_pool`, ADR-0023-safe); a
  `BattleActionKind.RESCUE` clears an ally's Surrounded condition
  (`_resolve_rescue_success`), declared via `battle declare rescue <ally> with
  <technique>`. See ADR-0074 for the AFK-safety exception.
- **Sieges (#1713):** `Fortification` (wall/gate/battlement, per `BattlePlace`, each
  independently breachable — ADR-0083) + `BREACH`/`FORTIFY` `BattleActionKind` values,
  ownership-validated in `declare_battle_action`. `open_siege_engine_encounter` binds a
  siege-engine skirmish the way `open_champion_duel` binds a Champion challenge, without
  the Champion-role gate. `create_fortification` snapshots starting integrity from
  `Building.fortification_level`, itself raised via a persistent `FORTIFICATION_UPGRADE`
  Project (`world.buildings.fortification_services`). BREACH/FORTIFY are reachable
  through `DeclareBattleActionAction` and `CmdBattle`'s telnet grammar, the same as every
  other `BattleActionKind` (#1713). See [battles.md](battles.md#sieges-1713) for the full
  mechanism.
- **Vehicles (#1714):** `BattleVehicle` pairs a `BattleUnit` (fights, takes STRIKE
  damage, can be destroyed) with a `BattlePlace` (what other units/participants embed
  onto). `create_battle_vehicle` builds the pair, plus a hull `Fortification` for
  structural vehicles (ship/airship) — living mounts (dragon/kraken) have none and
  route destruction through `BattleUnitStatus.DESTROYED` instead. `REPOSITION` moves
  a vehicle's `BattlePlace` on the shared `(x, y)` battle-map plane (ADR-0085),
  gated on `target_place.vehicle.unit.commander` rather than covenant `command_tier`.
  `places_overlap` then range-gates cross-vehicle targeting: a UNIT-scope STRIKE or a
  BREACH against another vehicle's hull is rejected (`PlacesDoNotOverlapError`) unless
  the acting side's place overlaps the target's — the mechanism that makes "boarding"
  mean something, independent of the room-scoped `can_perceive`. On hull breach or
  living-mount defeat, `eject_vehicle_occupants` clears every embedded unit's/
  participant's `place` FK and applies a drowning (ship/kraken) or falling
  (airship/dragon) hazard consequence (ADR-0073) — abstract units take a flat
  strength penalty unless they carry the matching `flying`/`aquatic` `Property`; real
  participants route damage through `resolve_damage_type_resistance` then
  `process_damage_consequences`. Reposition movement resolution is built
  (`_resolve_reposition_success` in `resolution.py`), and its `CmdBattle` telnet
  subcommand (`battle declare reposition <place> <dx> <dy> with <technique>`)
  shipped with #2007; a player-facing embark action (setting a unit/participant's
  `place` FK to a vehicle's place, today only doable by direct model manipulation)
  remains deferred. See [battles.md](battles.md#battlevehicle) for the full
  mechanism.
- **REST/WS surface (#2009):** `BattleViewSet` (`IsAuthenticated`, scene-gated exactly like
  `CombatEncounterViewSet` — staff unfiltered, else `scene__in=Scene.objects.viewable_by`,
  404s a private battle rather than leaking a 403) exposes `GET /api/battles/` (list,
  `?scene=`/`?outcome=` filters) and `GET /api/battles/<pk>/` (`BattleDetailSerializer` —
  the single aggregate: sides → places (x/y/footprint/terrain/`controlled_by`/
  `encounter_scene_id`/`vehicle`/`fortifications`) → units → participants (persona
  id/name/thumbnail only)). `notify_battle_state_changed` sends a slim `BATTLE_STATE`
  WS ping (`{battle_id, round_number}`, no battle data) to connected participants from
  `begin_battle_round`/`resolve_battle_round`/`conclude_battle`, each via
  `transaction.on_commit` (see ADR-0095: ping-plus-refetch, not a state payload push).
  Frontend: `/scenes/:id/battle` — a read-only React Flow `BattleMapPage`, refetching
  the aggregate via React Query on `BATTLE_STATE` receipt. See
  [battles.md](battles.md#web-surface-2009) for the full contract.
- **Staging (#2010):** the setup layer had no mutation path at all before this — a Battle
  could only exist via admin/tests/factories. New parallel catalog models:
  `BattleMapBlueprint` (`name` unique, `is_active`) → `BlueprintBattlePlace`
  (`terrain_type`/`movement_cost`/`x`/`y`/`footprint_radius`, unique `(blueprint, name)`)
  → `BlueprintFortification` (`kind`/`max_integrity`/`defending_side_role`) —
  catalog-time counterparts to `BattlePlace`/`Fortification`, copied onto a live
  `Battle` by `instantiate_battle_blueprint`; `BattleUnitTemplate` (`name` unique,
  `quality`/`strength`/`morale`/`individual_count`/`properties` M2M/`capabilities` M2M
  through `BattleUnitTemplateCapability`) — catalog-time counterpart to `BattleUnit`,
  copied by `spawn_units_from_template`. **Services** (`world.battles.staging`):
  `stage_battle` (creates a Battle + both sides, optionally cloning a blueprint;
  `location` kwarg binds `battle.scene.location` — battles stay location-less by
  default, ADR-0081), `instantiate_battle_blueprint` (`replace=True` guarded against
  an already-live battle — a round opened, or a unit/participant stationed —
  `BattleStagingError`), `spawn_units_from_template` (clamped to
  `MAX_TEMPLATE_SPAWN=20`). **Actions** (all `MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`,
  `target_type=SELF`): `create_battle`, `stage_battle_map`, `spawn_battle_units`,
  `enlist_battle_participant` (the latter three battle-scoped, re-verifying
  `_actor_may_gm_battle`), `browse_battle_catalog` (read-only, `is_active=True` only —
  the one surface the catalog-visibility rule is enforced on). `CreateBattleAction` is
  a third writer of `SceneParticipation.is_gm` (see the "Scenes" section). **Telnet**:
  `battle create/stage/spawn/enlist/maps/units` subverbs (`CmdBattle`). **Catalog API**:
  `GET /api/battles/map-blueprints/` / `GET /api/battles/unit-templates/`
  (`ReadOnlyModelViewSet`s gated `world.gm.permissions.HasGMTrust` — new JUNIOR-tier
  DRF permission class, staff bypass). **Web**: `StagingPanel`
  (`frontend/src/battles/components/`) on `BattleMapPage`, gated by dispatchable-action
  presence, dispatching through the same generic Action seam
  (`DispatchResultSerializer.success` is now nullable on the wire to distinguish an
  honest failure from a real success). See ADR-0111 and [battles.md](battles.md#staging-2010)
  for the full contract.
- **Deferred follow-ups:** battle writeup page (#1735 — should reuse
  `BattleDetailSerializer`'s aggregate rather than authoring a second one; the live
  strategic map itself shipped, #2009); naval/aerial embark actions remain deferred
  (#1714) — the vehicle model, REPOSITION declaration and movement resolution,
  overlap-gated boarding, hull-breach/living-mount-defeat ejection, and REPOSITION's
  telnet subcommand are built (see the Vehicles subsection above; the telnet gap
  closed with #2007). Live narration of battle actions (any kind, not
  vehicle-specific) is also unbuilt — `push_ephemeral_interaction` requires a
  player `persona` and battle-linked Scenes are created with `location=None`,
  skipping room-based broadcast entirely; see the narration-scope correction note
  in [battles.md](battles.md#battlevehicle).
- **Test coverage:** unit + integration tests in `src/world/battles/tests/`
  (including `test_siege.py`'s three E2E siege journeys, #1713, and
  `test_seed_staging_catalog.py`, #2010) and
  `src/world/buildings/tests/test_fortification_upgrade_kind.py` (#1713); E2E journeys
  `src/integration_tests/pipeline/test_battle_telnet_e2e.py`, `test_battle_peril_rescue_e2e.py`,
  `test_battle_staging_telnet_e2e.py` (#2010)
- **Integrates with:** scenes (1:1 extension), character_sheets (participant/commander FK),
  vitals (damage consequences; shared `_resolve_peril_via_pool` core for Surrounded, #1733),
  conditions (the "Surrounded" staged `ConditionTemplate`, #1733; `CapabilityType` via
  `BattleUnit.capabilities`/`BattleUnitCapability`, #1794), weather (read-only
  `get_effective_weather(area)` via `Battle.region` to seed ambient weather, #1715 —
  see the "Weather" section above; no write dependency), areas (`Battle.region` FK), magic
  (`BattleActionDeclaration.technique` FK; `resolve_battle_technique`
  → `use_technique`; `TechniquePropertyAffinity.technique` FK, #1794; `Technique.target_weather_type`
  for `SET_ENVIRONMENT` casts, #1715; military-grade
  `summon_ally(payload.military=True)` now reading `payload.properties`/
  `payload.capabilities`, #1711/#1794), mechanics (`Property` via `BattleUnit.properties`;
  `HasProperties`/`HasCapabilities` `Protocol`s, #1794), checks (`perform_check` sourced from
  `resolve_cast_check_type` — the caster's provisioned personal magic check, falling back to
  the cast technique's `action_template.check_type` only when unprovisioned, ADR-0096 — via
  `use_technique`; `select_consequence` for the Surrounded entry roll and resist checks,
  #1733), combat
  (`BattlePlace.combat_encounter` bridge, now wired for Champion duels, #1710, and
  siege-engine skirmishes, #1713; shared `RoundStatus` / `AbstractRound`), covenants
  (`BattleSide.covenant`; `CovenantRole.command_tier`/`.is_champion_role`, #1710), stories
  (`campaign_story` FK — beat-resolution linkage via `world.battles.beat_wiring`'s
  campaign-stakes propagation, #1785; also read directly as the `story=` arg to the
  win-gated `create_legend_event` call, #2184), societies (`world.battles.legend_wiring`
  imports `societies.services.create_legend_event`/`create_solo_deed` +
  `societies.models.LegendEntry`/`LegendSourceType` — a battle-conclusion hook, `battles`
  importing `societies`, #2184), buildings (`Fortification.building` FK, nullable,
  #1713 — `create_fortification` reads `Building.fortification_level` once at creation;
  this app does not import `world.buildings` beyond that FK),
  actions (REGISTRY + `get_active_round_context` seam), gm (`world.gm.permissions.HasGMTrust`
  gates the two staging catalog `ReadOnlyModelViewSet`s; `MinimumGMLevelPrerequisite
  (GMLevel.JUNIOR)` gates the 5 staging Actions, #2010)
- **Source:** `src/world/battles/`
- **Details:** [battles.md](battles.md)

### Worship & Ceremonies (#2355/#2289)
Gods as authorable data with worship economies, and ceremonies (funerals first) as
lightly-structured freeform RP. Full doc: `docs/systems/worship.md`; model decision ADR-0132.

- **Worship models** (`world/worship`): `WorshipTradition` (name, `rites_specialization` FK →
  skills.Specialization), `WorshippedBeing` (tradition FK, `resonance_pool` + `lifetime_worship`
  BigIntegers, nullable OneToOne `avatar_sheet`, `is_active`), `WorshipGrant` (audit ledger),
  `DevotionStanding` (unique sheet+being, `favor`/`lifetime_favor`), `WorshipDeclaration`
  (OneToOne sheet; `public_being` + `secret_being` + minted `secret` FK; `public_is_sincere`
  BooleanField default True, #2361 — the heart-vs-lip-service inward truth, private,
  owner/staff-only in the sheet identity serializer).
- **Worship services**: `grant_worship`, `bump_devotion` (+ God's Favorite
  Princess/Prince/Chosen achievement on top-favor reach/tie), `gods_favorite_achievement_for`;
  `mint_worship_secret` (`worship/secrets.py`); `convert_public_worship(sheet, new_being, *,
  is_sincere=True)` (#2361 — the single write path for a post-CG public conversion; get-or-
  creates the declaration, repoints `public_being`, stores `public_is_sincere`; never touches
  `DevotionStanding` or the secret side). CG: `CharacterDraft.public_worship`/
  `secret_worship` → `_create_worship_declaration` at finalization. Seeds: `worship` cluster
  (Rites skill + 4 specs, Ceremony Rites CheckType, Devotion aspect for Path of the Chosen,
  achievements, PLACEHOLDER beings); `secret-investigation` consent category in the consent seed.
- **Ceremony models** (`world/ceremonies`): `CeremonyType`
  (Funeral/Blessing/Sermon/Seance/Wedding/Conversion/Coronation rows — seeded via the
  `"ceremonies"` cluster, #2393/#2358/#2361), `Ceremony` (officiant Persona, TRUE
  `being` vs `presented_being` — player surfaces render
  presented ONLY, one-OPEN-per-location constraint, nullable scene/event/title FKs
  — `title` is CORONATION-only, `quality_level`),
  `CeremonyHonoree`, `CeremonyOffering` (item destroyed; snapshot), `CeremonySpeech`,
  `CeremonyConfig` singleton (`get_ceremony_config`, PLACEHOLDER magnitudes),
  `WorshipConversionOffer` (#2361, one per PC-officiated Conversion honoree —
  PENDING/ACCEPTED/DECLINED + `is_sincere`, mirrors `SeanceManifestationOffer`).
- **Ceremony services**: `open_ceremony` (twisted-rite being/presented mapping; validates
  honoree count/liveness per type — CONVERSION needs exactly one, the convert),
  `record_offering` (pool → TRUE being; devotion follows belief), `record_speech`
  (Performance/Oratory), `finish_ceremony` (Rites + tradition-spec quality roll; honoree deeds
  via `create_solo_deed` — `_mint_ceremony_deed` takes optional `archetypes`/`scene` kwargs,
  #2361; officiant cut; funeral → `execute_will` NO-OP seam for #1985; WEDDING
  refuses to solemnize until every `WeddingConsentOffer` is ACCEPTED, then solemnizes the
  honorees' active Betrothal; CORONATION (open precondition: exactly one honoree holding
  `title`) mints the permanent `Coronation` record; conversion → `convert_public_worship` per
  confirmed honoree, tags the deed with the existing "Treacherous Scandal"
  `PhilosophicalArchetype` when converting away from an already-declared faith so
  `route_deed_reach` (#1464) judges it),
  `abandon_ceremony`, `open_funeral_for` (ghost container); `run_twisted_rite_leak`
  (`ceremonies/leak.py` — consent-gated Search roll → clue on the worship Secret).
  Exceptions: `CeremonyError` (user_message). `respond_to_conversion_offer` (#2361,
  account-scoped accept/decline, mirrors `respond_to_seance_offer`; accepting records
  the heart-vs-lip-service choice on the offer — the actual repoint happens at finish),
  `pending_conversion_offers_for_account`. Actions: `conversion_offer_respond`; telnet
  `conversion` (offers/accept/decline, telnet accept is always sincere — the lip-service
  choice is web-only); API `/api/ceremonies/conversion-offers/` (list + accept/decline,
  `WorshipConversionOfferSerializer`, `accept` body takes optional `sincere`); frontend
  `ConversionOfferBanner`/`ConversionOfferDialog` (mounted in `Layout.tsx` next to
  `SeanceOfferBanner`; the dialog's Switch carries the heart-vs-lip-service choice).
- **Wedding/Coronation (#2358)**: `WeddingConsentOffer` (one per spouse honoree, minted by
  the officiant's `open_ceremony` call at ceremony START, shares `SeanceOfferStatus`) —
  `respond_to_wedding_consent_offer` (account-scoped, mirrors `respond_to_seance_offer`; a
  DECLINE calls `abandon_ceremony`), `pending_wedding_consent_offers_for_account`. Consent
  replaced the earlier idea of gating at `propose_betrothal`; the union + marriage pact still
  mint only at FINISH via `world.societies.houses.pact_services.solemnize_wedding`.
  `Coronation` (`honoree_sheet` + `title`, `UniqueConstraint` — one-off per (honoree, title),
  a later coronation for a DIFFERENT title still stands) is minted at FINISH, never OPEN, so an
  abandoned attempt never blocks a retry. Neither type mints extra flat prestige beyond the
  shared honoree-renown pass — event grandeur (#2357) is the prestige-influx lever. Actions:
  `wedding_consent_respond`; telnet `ceremony/wedding`, `ceremony/coronation`, `wedding`
  (offers/accept/decline, mirrors `seance`). Divorce (`initiate_divorce`, unilateral, both
  spouses' personal prestige hit, initiator steeper) lives in `docs/systems/houses.md`'s pacts
  section — it is a house-pact concern, not a ceremony.
- **Seance (#2393)**: `SeanceManifestationOffer` (one per honoree, PENDING/ACCEPTED/DECLINED)
  — created by `open_ceremony` for a SEANCE-type ceremony. `respond_to_seance_offer`
  (account-scoped accept/decline; accept moves the honoree's character to the ceremony's
  location), `pending_seance_offers_for_account`, `revoke_seance_manifestations` (called from
  `finish_ceremony`/`abandon_ceremony`, unpuppets any manifested RETIRED honoree). Retired-login
  bypass lives on `Account.can_puppet_for_seance` — deliberately NOT merged into
  `can_puppet_character`/`get_available_characters` (see ADR-0147). Actions:
  `seance_offer_respond`; telnet `seance` (offers/accept/decline); API
  `/api/ceremonies/seance-offers/` (list + accept/decline); frontend `SeanceOfferBanner`.
- **Integration**: `GhostWindowPrerequisite` third container (open funeral, or an open
  ACCEPTED seance, at the ghost's location, #2393); `_dead_owner_trusts` corpse-handler
  exemption (`flows/service_functions/
  inventory.py`); `ceremonies.auto_abandon` hourly cron. Actions `ceremony_open`/`_offering`/
  `_speech`/`_finish`/`_abandon`; telnet `ceremony` family; API `/api/worship/beings/` +
  `/api/ceremonies/ceremonies/` (both paginated read-only); game-view `CeremonyRoomCard`.

### Wills & Estate Settlement (#1985)
Death opens a settlement window; the estate executes through the first of three doors —
funeral finish, executor will-reading, or the deadline sweeper (14 real days, PLACEHOLDER)
— never blockable by an idler, never stealing RP (ADR-0133). Full doc:
[estates.md](estates.md).

- **Models** (`world/estates`): `Will` (OneToOne sheet; testament prose; frozen once a
  settlement exists), `WillExecutor` (persona; any one may read), `Bequest` (kind-major
  lines: SPECIFIC_ITEM/COIN_AMOUNT/ALL_COIN/BUILDING/BUSINESS/RESIDUARY/WRITINGS (#3287,
  no target FK — the corpus itself is the asset); typed persona-XOR-org recipient;
  items/businesses/WRITINGS persona-only), `EstateSettlement`
  (PENDING/SETTLED/PARKED + `settled_via`), `EstateClaim` (inherited theft grievance,
  claimant-visible only), `EstateConfig` (singleton window).
- **Services**: `open_settlement` (from `_mark_dead`, which now also stamps
  `Kinsperson.is_deceased` + fires `handle_death_for_pacts`); `execute_settlement` (ONE
  idempotent path: debts → bequests → residuary sweep → contract substitution → tenancy/
  employment end → claims → journal reveal + WRITINGS bequest grant, #3287; PARKED =
  zero-mutation rollback); `resolve_intestate_heir`
  (family-org head → public-record kin; hidden kin never auto-inherit);
  `resolve_escheat_org` (nearest `Domain.owner_org` by parent walk).
- **Ownership/theft**: `OwnershipEventType.INHERITED` (+ `PROVENANCE_EVENT_TYPES`);
  `items/services/provenance.py` hot-item reads; `receiving-stolen-goods` consent
  category (default-deny) gating `give()` + estate delivery via `RecipientConsentDenied`
  (category-generic refusal).
- **Integration**: funeral door via `ceremonies.execute_will` delegation; `will_reading`
  REGISTRY action; `estates.auto_settle` hourly cron; API `/api/estates/`
  (wills/bequests/executors CRUD own-scoped 404-not-filtered; settlements
  executor-scoped; claims claimant-scoped); `AgreementsPanel` sheet tab.
- **Source:** `src/world/estates/`
- **Details:** [estates.md](estates.md)

### Dreams (#2290)
The dream realm — a parallel layer on the room graph for sleeping/unconscious characters.
Dream reflections, mental fatigue dream danger, Dream Peril consequence pool (nightmares/
madness/death, narrated to the player via `character.msg`), thread-gated dreamwalking with
escape lever, and the deep dreaming area.
- **Models (#3003):** `DreamwalkPresence` — persisted dreamwalk anchor keyed on the host
  sheet (see ADR-0198), replacing the process-local `ndb.dreamwalk_destination` stash.
- **Services (#3003):** `dreamspace_for(sheet)` (the single "whose dreamspace does this
  character perceive" resolution point — every viewer-facing caller routes through it),
  `co_dreamers_for`, `start_dreamwalk`/`end_dreamwalk`, `has_dream_bond`,
  `dreamwalk_candidates_for`.
- **Surfaces (#3003):** `GET /api/dreams/<character_id>/` (dream-state payload — co-dreamers,
  dreamwalk host/candidates, descend/ascend availability, wake-blocked flag); FE
  `frontend/src/dreams/` (`DreamspacePanel`, takes over the play view's Room tab while
  dreamside).
- **Source:** `src/world/dreams/`
- **Details:** [dreams.md](dreams.md)

### Vitals
Character mortality, health tracking, and the acute-peril dying state. System-agnostic — called by
combat, poison, spells, exhaustion, and any damage source.

- **Body carrying (#2852, ADR-0184):** `CarriedBody` (O2O carrier/carried) +
  `carry_services.pick_up_body`/`set_down_body`/`carried_body_follow` (at_post_move hook
  brings the body along; releases when the carried can act). PC bodies gated on the
  `body-handling` consent category (`world.consent.services.body_handling_category`,
  makeover-precedent allowlist default); NPCs open. Robbing a downed body:
  steal-path-only reach widening in `flows.service_functions.inventory`
  (`_unconscious_holder_reachable` — worn gear excluded; theft consent unchanged).
  Surfaces: `carry_body`/`set_down_body` actions, telnet `carry <name>`/`setdown`.

- **Models:** `CharacterVitals` (OneToOne on CharacterSheet; fields: `life_state`
  (`CharacterLifeState`: ALIVE/DEAD — the binary mortality axis), `health`, `max_health`,
  `base_max_health` — null = derive from level/stamina/role; `died_at`; #2287: `died_in_scene`
  FK scenes.Scene — bounds the ghost emit window + death-kudos eligibility — and `retired_at`,
  the final puppet lock), `VitalsConsequenceConfig` (singleton pk=1; tunable difficulty scaling +
  pool FKs: `knockout_pool`, `default_wound_pool`, `default_death_pool`; #2287: wake-arc knobs
  `wake_base_difficulty`/`wake_scaling_per_percent`/`wake_ease_per_round`/`wake_guaranteed_rounds`,
  `auto_retire_days`, admin-editable `death_condolence_body`), `WoundDetails` (#2644; OneToOne →
  `conditions.ConditionInstance`, CASCADE, `related_name="wound_details"` — FK direction
  specific→general per ADR-0010; `damage_taken` PositiveInt — the debit that caused the wound,
  the mend-cap basis; `health_mended_total` PositiveInt, default 0 — running sum every
  `mend_wound()` call has ever mended on this wound, across every healer; stamped by
  `_record_wound_details` the moment the wound tier applies a wound condition)
- **Old-age decline (#2756, ADR-0172):** the Frailty condition (severity counts accumulated
  decline; its `ConditionModifierEffect` −1 × severity vs the `max_health` ModifierTarget is
  that target's first writer, folded in by `recompute_max_health`). `world/vitals/aging.py`
  carries the three IC-cadence cron services — `run_birthday_tick` (AFK-safe window query
  advancing `matured_years`), `run_decline_checks` (Aging Resistance stamina check,
  difficulty = `aging_difficulty_per_year` × years past `Species.decline_start_age`;
  Failure/Partial deepen Frailty by `frailty_fail_severity`/`frailty_partial_severity`),
  `run_death_sweep` (resolves `CharacterVitals.aging_death_ic_deadline` via `_mark_dead` →
  estates settlement). Config knobs live on `VitalsConsequenceConfig` (all PLACEHOLDER);
  registered as `aging.birthday_tick`/`aging.decline_check`/`aging.death_sweep`
  (`FrequencyType.IC`) in `game_clock/tasks.py`.
- **Key Services (`world/vitals/services.py`):**
  - `is_dead(sheet)`, `is_alive(sheet)`, `can_act(sheet)` — mortality/agency gates.
  - `derive_character_status(sheet) -> str` — compute dead/dying/incapacitated/alive at read time.
  - `process_damage_consequences(character_sheet, damage, ...)` — full survivability pipeline:
    knockout check → death check → permanent wound check; each tier rolls the configured pool.
    The wound tier now actually applies conditions (#2644 — closed the audit's central gap) and
    stamps `WoundDetails` on each applied instance via `_record_wound_details`.
  - `mend_wound(healer_sheet, target_sheet, wound_instance, amount) -> int` (#2644) — double-
    bounded HP mend, the attrition invariant (ADR-0156): caps at
    `NEVER_TO_FULL_FRACTION x wound_details.damage_taken - health_mended_total`, clamps to
    `max_health`, returns the amount actually mended (0 is legal, not an error). Raises
    `world.vitals.exceptions.NotAWoundError` when the instance has no `WoundDetails`. Never
    callable outside the treatment flow (`conditions.services.perform_treatment` is the sole
    caller) — the once-per-healer-per-wound bound lives one layer up, on
    `conditions.TreatmentAttempt`'s partial `UniqueConstraint`.
  - `advance_bleed_out(sheet) -> bool` — per-round progression; terminal stage routes to
    `_resolve_terminal_bleed_out` (guarded pool, not unconditional death; ADR-0049).
  - `_resolve_peril_via_pool(sheet, instance, pool, *, death_permitted) -> bool` — shared
    death-gated core for ALL acute-peril resolution: excludes `character_loss` candidates when
    the caller-supplied `death_permitted` is False; clears the condition on both death and
    survival; single `_mark_dead` writer. `death_permitted` is supplied by the caller
    (bleed-out/abandonment via `death_is_permitted`; battle Surrounded via
    `select_surrounded_terminal_pool` routing, #1733) rather than derived internally, since not
    every peril source is an `ObjectDB` character.
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
- **Wake arc + death off-ramp (#2287, ADR-0131; `services.py`, `death_kudos.py`, `seeds.py`):**
  - `attempt_wake(sheet, *, in_combat_tick=False) -> WakeResult` — one Endurance roll per round
    (wall-clock round-equivalent out of combat via `last_resist_attempt_at`; free roll on the
    combat tick), difficulty `calculate_wake_difficulty(health_pct, rounds_elapsed)`, guaranteed
    wake at the knockout-stamped `expires_at` deadline. Dying blocks waking. Surfaces:
    `WakeAction`/`wake`.
  - `perceives_dreamside(sheet)`, `get_dream_room()` — unconscious perception relocates to the
    liminal dream room (web room-state, look, `message_location` skip); dead ghosts stay waking-side.
  - `_mark_dead` stamps `died_in_scene` + delivers `death_condolence_body` (character msg +
    `character_died` WS frame). Ghost interlude: `DEAD_ALLOWED_ACTION_KEYS` whitelist in
    `Action.check_availability`; `GhostWindowPrerequisite` bounds emit/pose (death scene / IC day).
  - `retire_character(sheet, *, forced_by=None)`, `is_retired(sheet)` — the release lock, enforced
    at `Account.can_puppet_character` + `PlayerData.get_available_characters`;
    `vitals.auto_retire` game_clock task is the backstop. No resurrection path exists.
  - `award_death_kudos(giver_account, dead_character) -> DeathKudosResult` (`death_kudos.py`) —
    capped graceful-death channel on account kudos: GM/staff max(20, 50% lifetime spend),
    participants max(1, 5%), aggregate cap 100% of spend, post-cap floors 1/20; window
    death→retire; offscreen = staff-only. Surfaces: `GiveDeathKudosAction`/`kudos death <name>`.
  - `seed_survivability_content()` (`seeds.py`, cluster `survivability`) — the production seeding
    that makes every tier fire: foundational CapabilityTypes, Unconscious effects, Bleeding Out
    stages, knockout/default-death/default-wound pools, dream room, death KudosSourceCategory,
    the three wound conditions + their TreatmentTemplates (#2644, see below).
  - `ensure_wound_conditions()` (#2644) — seeds three mechanical wound `ConditionTemplate`s
    (vocabulary, not lore content, mirroring `ensure_bleeding_out_condition`): **Lingering Ache**
    (`ConditionCheckModifier` on the vitals-owned Endurance CheckType, -5), **Crippling Wound**
    (`ConditionCapabilityEffect` on `limb_use`, -15), **Bleeding Wound** (`ConditionDamageOverTime`,
    severity-scaled, authored but not wired into the default pool — see `ensure_default_wound_pool`'s
    docstring for the documented single-default choice). `ensure_default_wound_pool` wires the
    partial/failure outcomes to Lingering Ache / Crippling Wound via APPLY_CONDITION effects
    (`update_or_create` on the pool row so a stale pre-#2644 description self-corrects on re-run).
  - `ensure_wound_treatment_content()` (#2644) — one `TreatmentTemplate` per wound condition
    (`treat_lingering_ache`/`treat_crippling_wound`/`treat_bleeding_wound`), `target_kind=PRIMARY`,
    reuses the vitals-owned Endurance CheckType (documented fallback — no Medicine/first-aid
    CheckType exists in seeded content), modest `anima_cost`, `once_per_wound_per_helper=True` +
    `once_per_scene_per_helper=False`.
- **Pool constants (`world/vitals/constants.py`):** `POOL_BLEED_OUT_TERMINAL`,
  `POOL_ABANDONMENT_ENEMY`, `POOL_ABANDONMENT_PVP`, `POOL_ABANDONMENT_ENVIRONMENTAL` (seeded via
  `world.vitals.factories`; `abandonment_enemy` includes a `captured_alive` CAPTURE outcome);
  #2287: `POOL_KNOCKOUT`, `POOL_DEFAULT_DEATH`, `POOL_DEFAULT_WOUND`, `BLEED_OUT_STAGE_SPECS`,
  `DREAM_ROOM_KEY`/`DREAM_ROOM_TAG`. #2644: `WOUND_LINGERING_ACHE_NAME`, `WOUND_CRIPPLING_NAME`,
  `WOUND_BLEEDING_NAME`, `NEVER_TO_FULL_FRACTION` (Decimal, default 0.75 — the attrition
  invariant's tunable fraction; a plain constant, not an admin-config field, mirroring
  `PERMANENT_WOUND_THRESHOLD`'s precedent).
- **Design invariants:** ADR-0049 (guarded pool, no unconditional death); ADR-0023 extended to the
  death layer (PC source can never produce death); ADR-0004 extended to dying state (grace window
  counts round_number beats, not wall-clock); plummet exempt from hold/abandonment; ADR-0156
  (double-bounded mend — once-per-healer-per-wound + never-to-full fraction — heals are real but
  the party is always net-weaker for having fought; never time-based or passive).
- **Source:** `src/world/vitals/`
- **Details:** `src/world/vitals/CLAUDE.md` · `docs/roadmap/combat.md` (§Phase 8, Phase 9)

### Relationships
Track-based character-to-character regard, conditions, situational modifier gating, and
writeup kudos/complaint feedback.

- **Models:** `RelationshipCondition`, `RelationshipTrack` (+ `RelationshipTier`,
  `HybridRelationshipType`), `CharacterRelationship`, `RelationshipTrackProgress`,
  `RelationshipUpdate` (temporary points + capacity), `RelationshipDevelopment`
  (permanent points, 7/week), `RelationshipCapstone` (permanent + capacity),
  `RelationshipChange` (track-to-track redistribution), `GrievanceOption` (#1429),
  `RelationshipBump` (#1699 — ambient ±1 nudge anchored to an Interaction;
  `UniqueConstraint(relationship, interaction)` is the whole anti-spam cap);
  **writeup feedback (#1537):** `WriteupKudos` (subject's non-revocable commendation;
  awards kudos to the author), `WriteupComplaint` (bad-faith-RP flag for staff triage;
  `resolved` bool; zero player signal)
- **Key Fields:** `CharacterRelationship.affection` (signed sum), track
  `capacity` / `developed_points`; `UpdateVisibility` (private/shared/gossip/public);
  `RelationshipTrack.system_key` (#1699 — `TrackSystemKey.REGARD`/`FRICTION` on the two
  generic system tracks ambient bumps write to; null on authored tracks);
  `CharacterRelationship.developed_signed_sums` (#2034 — `(positive_sum, negative_sum)`
  split of `developed_absolute_value` by `track.sign`, cached path; consumed by
  `world.magic`'s fraught pull term, see ADR-0110)
- **Pattern:** `RelationshipCondition.gates_modifiers` (M2M to ModifierTarget) — conditions activate/deactivate situational modifiers
- **Examples:** "Attracted To" gates Allure modifier, "Fears" gates Intimidation bonus
- **Services:** `create_first_impression`, `create_development`, `create_capstone`,
  `redistribute_points` (`services.py`) — the four positive relationship-building verbs;
  `apply_relationship_bump(*, source, target, interaction, valence, source_emoji=None)`
  (#1699) — permanent ungated `BUMP_POINTS` (±1) onto the Regard/Friction system track
  (capstone write-shape: capacity + developed together), deduped per interaction;
  `give_writeup_kudos(*, giver_account, writeup)` — commend a writeup, awards kudos to
  author (warn-skips when `"relationship_writeup"` `KudosSourceCategory` not seeded);
  `file_writeup_complaint(*, complainant_account, writeup, reason)` — file a bad-faith-RP
  complaint for staff triage
- **Exceptions:** `WriteupFeedbackError` base + `WriteupNotSharedError`,
  `NotWriteupSubjectError`, `CannotCommendOwnWriteupError`, `AlreadyCommendedError`,
  `WriteupNotVisibleError`; `RelationshipBumpError` base + `AlreadyAcknowledgedError`,
  `SystemTracksNotSeededError` (#1699) — each with `user_message` for 400 API responses
- **Seeds:** `relationship_scale` cluster (#1699, `world/seeds/relationship_scale.py`) —
  Regard/Friction system tracks, 4 `RelationshipTier` bands each at 25/100/500/2000
  (names PLACEHOLDER), starter `ReactionEmoji` rows (👍 neutral, ❤️ +1, 😠 −1)
- **Player surface (#1485, #1537):** all four verbs plus kudos/complaint are reachable
  from both web and telnet — the web `RelationshipUpdateViewSet` POST endpoints
  (`first_impression` / `develop` / `capstone` / `redistribute` / `kudos` / `complaint`)
  and the telnet `relationship <subverb>` namespace both dispatch the Actions via
  `action.run()` (ADR-0001). Read serializers expose `kudos_count` + `viewer_has_kudosed`
  on every writeup row. No consent gate — these describe the caller's regard, they do not
  compel the target's behavior (ADR-0024). FK direction: feedback lives in relationships,
  not on the kudos primitive (ADR-0010). No denormalized kudos count (ADR-0014).
- **Ambient bumps (#1699):** telnet `relationship plus|neg <name>` (aliases `rel/plus`,
  `rel/neg`) backfill-anchor to the target's most recent unacknowledged visible pose in
  the active scene; web valenced `ReactionEmoji` reactions bump the pose's author
  directly (`InteractionReactionViewSet.create` side-effect, `bump_applied` in the
  response). Both dispatch `RelationshipBumpAction` (key `"relationship_bump"`). Not
  consent-gated (private write to the actor's own regard, ADR-0024); bumps render only
  in the actor's own relationship views; the target is never notified.
- **Writeup list route (#2031):** `RelationshipUpdateViewSet` also mixes in `ListModelMixin`
  for `GET /api/relationships/relationship-updates/` — narrow (not a general writeup
  browser): tenure-scoped to `RelationshipUpdate` rows whose parent relationship's `target`
  is a character the requesting account currently holds a **RosterTenure** on, SHARED/PUBLIC
  visibility only. `?relationship=`/`?track=`/`?subject_character=<CharacterSheet pk>`
  filters (`RelationshipUpdateFilter`); the last narrows a multi-character account down to
  one owned sheet. Frontend: the commend button on the "Writeups" subsection of
  `RelationshipsSection` (`frontend/src/components/character/RelationshipsSection.tsx`, own-
  sheet gated), fed by `frontend/src/relationships/` (`api.ts`/`queries.ts`), POSTs
  `{writeup_type: "update", writeup_id}` to `.../kudos/`. A "Report" button beside Commend
  opens `WriteupComplaintDialog` (#2159, `frontend/src/relationships/components/`), which
  POSTs `{writeup_type, writeup_id, reason}` to `.../complaint/` — zero follow-up read
  surface, matching `WriteupComplaint`'s staff-only visibility.
- **Writeup timeline action (#2159):** `GET .../relationship-updates/timeline/` merges
  Update/Development/Capstone history into one type-tagged (`kind`), `-created_at`-ordered,
  paginated feed. Exactly one of two mutually exclusive params (both/neither → 400):
  `?about_character=<CharacterSheet pk>` — non-PRIVATE writeups about that character from
  any author, plus PRIVATE ones where the caller is the author or the subject (the
  queryset-level generalization of `services._can_view_writeup`, entirely DB-side, no
  Python row filtering); `?relationship=<CharacterRelationship pk>` — one relationship's
  full history incl. PRIVATE, source-owner-only (tenure join; 404 missing, 403 non-source).
  Implementation: each writeup model's queryset is projected to a shared column shape and
  combined via `.union()` (per-branch `.order_by()` clears `Meta.ordering` — SQLite
  rejects `ORDER BY` inside a union branch).
- **RelationshipPanel (#2159):** the "Ties" subsection of `RelationshipsSection`, replacing
  the old free-text `CharacterData.relationships` Notes list. Branches on `isMyCharacter`
  (`frontend/src/relationships/components/RelationshipPanel.tsx`), mirroring
  `CharacterRelationshipViewSet`'s author-private scoping (ADR-0117): own sheet renders
  `OwnRelationshipsList` — `GET .../relationships/?source=<sheet pk>` (list serializer, no
  `track_progress`) for target/affection rows, each expandable (Radix `Accordion`, lazy —
  no N+1 up front) into `GET .../relationships/<id>/` (detail serializer, for
  `track_progress` points/tiers) plus the `?relationship=` timeline arm for full history,
  and buttons opening `RelationshipWriteupDialog` in development/capstone/redistribute
  modes (`target_persona_id` resolved via `GET /api/personas/?character_sheet=`, since the
  list/detail relationship serializers only carry the target's CharacterSheet pk, not a
  Persona pk). Foreign sheet renders `ForeignRelationshipTimeline` — the `?about_character=`
  arm only, type-tagged, deliberately no numeric fields (`RelationshipTimelineEntry` itself
  carries none).
- **Automatic affection shifts (#1697, boon mode #2540):** `AffectionShift` model +
  `apply_affection_shift(*, source, target, scene, effect, amount, boon=None)` — the generic
  valence-signed success consequence (`EffectType.SHIFT_AFFECTION`, handler in
  `world/mechanics/effect_handlers.py`, `ConsequenceEffect.affection_amount`): a
  successful Flirt (+5) / Seduce (+50, PLACEHOLDER) moves the TARGET's regard toward
  the actor on the system tracks; gated offensive actions carry
  negative amounts onto Friction. Two provenance modes, exactly one per row
  (`affection_shift_has_provenance` CheckConstraint): effect-keyed rows keep the
  `UniqueConstraint(relationship, scene, effect)` diminishing-returns rule — first success
  per scene per pair shifts, repeats no-op — while boon-keyed rows (a granted Boon's
  `-BOON_AFFECTION_COST` drain, charged by the `boon` resolver) dedup on the Boon
  OneToOne itself, so serial granted boons stack even within one scene. Shifted points
  never decay — the drain persists until rebuilt through play (Apostate's ≥3-months
  ruling is automatic). Seeded in `world/seeds/social_actions.py`.
- **Affection-tier difficulty ladder (#1697):** `resolved_base_difficulty`
  (`world/scenes/social_difficulty.py`) derives its bands from the #1699 system-track
  `RelationshipTier` thresholds (Regard for warm, Friction for hostile) — one tier
  easier/harder per band crossed, neutral = Normal (fallback constants when unseeded).
  Also applies `ConditionTemplate.exploitable_tiers` — the exploitable-state seam:
  checks rolled at a Smitten bearer resolve 2 tiers easier (PLACEHOLDER); Smitten's
  other teeth (Melee Defense penalty via `ConditionCheckModifier`, Force ×2 damage via
  `ConditionDamageInteraction` riding #2018) + the Attractive distinction's allure
  grant (base allure = sum of allure modifiers) are seed rows in
  `social_actions`/`social_relationships`.
- **Admin:** `WriteupComplaint` registered for staff triage (no player-facing complaint UI)
- **Actions:** `GiveWriteupKudosAction` (key `"give_writeup_kudos"`),
  `FileWriteupComplaintAction` (key `"file_writeup_complaint"`),
  `RelationshipBumpAction` (key `"relationship_bump"`, #1699)
  (`actions/definitions/relationships.py`)
- **Integrates with:** mechanics (modifier gating), character_sheets (CharacterSheet FK),
  scenes (optional `linked_scene` defaults to the caller's active scene), progression
  (XP + `award_kudos`)
- **Source:** `src/world/relationships/`; frontend: `frontend/src/relationships/` +
  `frontend/src/components/character/RelationshipsSection.tsx`

---

## Core Infrastructure

### Actions
Self-contained game actions that own prerequisites, execution, and events.

- **Key Classes:** `Action` (base dataclass), `Prerequisite`, `ActionResult`, `ActionAvailability`
- **Registry:** `get_action(key)`, `get_actions_for_target_type(target_type)`, `ACTIONS_BY_KEY`
- **Target Types:** `SELF`, `SINGLE`, `AREA`, `FILTERED_GROUP`
- **Concrete Actions:** `LookAction`, `InventoryAction`, `SayAction`, `PoseAction`, `WhisperAction`, `GetAction`, `DropAction`, `GiveAction`, `TraverseExitAction`, `HomeAction`, `EquipAction`, `UnequipAction`, `PutInAction`, `TakeOutAction`, `UseItemAction`, `ActivatePermitAction`, `GrantItemAction` (JUNIOR-tier GM narrative item grant, #707/#2117), `GMAwardDistinctionAction` (`registry_key="gm_award_distinction"`, JUNIOR-tier GM distinction award/rank-up, telnet `grant_distinction`, wraps `distinctions.grant_distinction`, #2037), `MoveToPositionAction`, `SetTheStageAction`, `PerformRitualAction` (ritual dispatch — SERVICE/FLOW runs immediately; CEREMONY creates `PendingRitualEffect`), `WeaveThreadAction` (CEREMONY finisher — consumes pending Rite of Weaving effect, calls `weave_thread`), `ImbueThreadAction` (CEREMONY finisher — consumes pending Rite of Imbuing effect, calls `spend_resonance_for_imbuing`), `RestAction` (fatigue rest — spend AP to gain `well_rested`; gated by own home + outside combat, #1491/#1524), `CreateFirstImpressionAction` / `CreateDevelopmentAction` / `CreateCapstoneAction` / `RedistributePointsAction` (relationship-building verbs — record first impressions, develop permanent points, mark capstones, redistribute between tracks; shared by telnet `CmdRelationship` and web `RelationshipUpdateViewSet`, #1485), `GiveWriteupKudosAction` / `FileWriteupComplaintAction` (writeup feedback — subject commends a writeup; any viewer files a bad-faith complaint for staff triage; shared by `CmdRelationship` and `RelationshipUpdateViewSet`, #1537), `StagePropAction` / `StagePropertyAction` (`registry_key="stage_prop"`/`"stage_property"`, `actions/definitions/gm_props.py`, #2503) — GM improv: materialize a curated `ItemTemplate` as a physical prop in the room, or tag an existing object with a curated `Property`; gated on the room's active scene GM/owner or staff; shared by telnet `CmdStage` (`stage prop <template>` / `stage property <property> [=<target>]`, `commands/gm_props.py`)
- **WORLD_INTERACTION backend (#2503):** a fifth `ActionBackend` (alongside CHALLENGE, COMBAT,
  REGISTRY, SCENE_ADAPTIVE) for bare-object affordances synthesized by `get_available_actions`'s
  second source (see the Mechanics section). `ActionRef` carries `application_id` +
  `target_object_id` instead of `challenge_instance_id`; `dispatch_player_action` re-validates
  the pair, mints a `ChallengeInstance` via `instantiate_challenge`, then resolves through the
  unchanged `resolve_challenge()`. See `docs/architecture/action-template-pipeline.md`.
- **Pattern:** `action.run(actor, **kwargs)` → applies enhancements → emits `EventName.ACTION_INTENT` (cancellable, skipped when `actor is None`) → **enforces prerequisites (hard gate)** → charges AP/fatigue → executes → runs post-effects → emits `EventName.ACTION_RESULT` → returns `ActionResult` (#3418, ADR-0243)
- **Prerequisites:** `get_prerequisites()` is load-bearing; `run()` calls `check_availability()` against post-enhancement kwargs. Prerequisites read action-specific kwargs via `context["kwargs"]`. Shipped: `StaffOnlyPrerequisite`, `MinimumGMLevelPrerequisite` (#2117 — staff bypass + `GMProfile.level` >= a configured `GMLevel` tier, generalizing `world.combat.scaling.validate_stakes_requirement`'s pattern; gates `SetTheStageAction`/`PemitAction` at STARTING and `SetSituationAction`/`GrantItemAction` at JUNIOR), `HoldsItemPrerequisite`, `ItemUsablePrerequisite`, `OnUseTargetPrerequisite`.
- **Two built-in gates run BEFORE `get_prerequisites()`** (`Action.check_availability`, `base.py`): the dead gate (#2287 — a dead actor is refused every action key except `DEAD_ALLOWED_ACTION_KEYS`'s spectator/off-ramp whitelist), then the offscreen-act gate (#3412, ADR-0246 — `actions.offscreen_gate.offscreen_act_state(sheet, action_key)`, consulted only when the dead gate didn't already refuse; a character in a degraded lifecycle state — CAPTURED/unconscious/DEAD/RETIRED/UNKNOWN — gets ROUTED or BLOCKED instead of ALLOWED for the narrow `OFFSCREEN_ACT_KEYS` set of "2.5 acts": journal entries, character goals, persona swaps, proclamations; every other key resolves ALLOWED with zero lifecycle read). Neither is opt-in — both apply to every action automatically.
- **Integrates with:** service functions (direct calls), commands (telnet compatibility), flows (the generic `ACTION_INTENT`/`ACTION_RESULT` pair, #3418 — authored triggers filter on `payload.action_key`)
- **Not Yet Built:** `SyntheticAction` model, `CharacterCapabilities` facade, on-demand availability endpoint
- **Telnet convergence convention (ratified #1337):** the three player-action dispatch
  families and the seam each telnet command must converge on with the web — Family 1
  `dispatch_player_action()`, Family 2 consent services, Family 3 a real `Action` on
  `action.run()`. See [unified-player-action.md §10](../architecture/unified-player-action.md#10-telnet-convergence-convention--three-player-action-families-ratified-1337).
- **Source:** `src/actions/`

### Flows
Database-driven game logic engine for complex branching sequences, plus the reactive layer that powers triggers/scars/wards.

- **Models:** `FlowDefinition`, `FlowStepDefinition`, `FlowStack`, `Event`, `TriggerDefinition`, `Trigger`, `TriggerData`
- **Trigger fields:** `obj` (typeclass owner), `source_condition` (optional, null = system-installed; set when a `ConditionInstance` installed the trigger), `source_stage` (optional stage gate), `additional_filter_condition` (JSON DSL), `priority`. **No `scope` field** - self-vs-target-vs-bystander is expressed via filters
- **Key Classes:** `FlowStack` (with depth cap + cancellation), `FlowExecution`, `FlowEvent`, `SceneDataManager`, `TriggerHandler` (per-owner cached_property; pure provider — its sole public method is `triggers_for(event_name) -> list[Trigger]`)
- **Reactive Entry Points:**
  - `emit_event(event_name, payload, location, *, parent_stack=None)` (`flows/emit.py`) — **single unified dispatch path**. Walks `[location, *location.contents]`, calls `triggers_for(event_name)` on each owner, priority-sorts the combined list globally (descending), dispatches synchronously on one `FlowStack`, stops on `CANCEL_EVENT`. Used by service functions, typeclass hooks, and `EMIT_FLOW_EVENT` flow steps alike
  - `EventName` (`flows/constants.py`, a `TextChoices`) — canonical event-name constants for the
    reactive layer; grows as new domains wire in events (see `docs/systems/flows.md`'s Event
    Catalog for the documented MVP subset)
  - `PAYLOAD_FOR_EVENT` (`flows/events/payloads.py`) — event-name → payload dataclass map; PRE payloads are mutable, POST payloads frozen. AE payloads use `targets: list`
  - `evaluate_filter(spec, payload, *, self_ref)` (`flows/filters/evaluator.py`) — JSON filter DSL: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `contains`, `has_property`, `has_capability`, plus `and`/`or`/`not`. Bare `"self"` (and `self.<attr>`) resolves to the trigger's owner
  - **Filter idioms** (see `docs/systems/flows.md` for details): `{"path": "target", "op": "==", "value": "self"}` = self-only (replaces `scope=SELF`); `{"path": "target", "op": "!=", "value": "self"}` = bystander-only; no target filter = room-wide (replaces `scope=ROOM`/`ANY`)
  - `register_pending_prompt`, `resolve_pending_prompt`, `timeout_pending_prompt` (`flows/execution/prompts.py`) — Twisted Deferred-backed player prompts (no DB rows)
  - `classify_source(obj) -> DamageSource` (`world/combat/damage_source.py`) — discriminated union for damage attribution
- **New Flow Action Steps:** `CANCEL_EVENT`, `MODIFY_PAYLOAD`, `PROMPT_PLAYER`, `EMIT_FLOW_EVENT` (routes through `emit_event()`), `EMIT_FLOW_EVENT_FOR_EACH` (in `FlowActionChoices`). `DEAL_DAMAGE` / `REMOVE_CONDITION` steps are deferred — emit a flow event that calls the relevant service function instead.
- **Typeclass Hooks:** `Character.at_attacked`, `Character/Room/Object.at_pre_move`/`at_post_move` — wired in `typeclasses/` to call `emit_event`. The `trigger_handler` cached property is installed via `ObjectParent` mixin. EXAMINE_PRE/EXAMINED are the one exception — they emit from the action layer (`actions.definitions.examine_extras.gather_examine_extras`, the `LookAction` seam), not a typeclass hook; see ADR-0213.
- **Object States:** `BaseState`, `CharacterState`, `RoomState`, `ExitState` — ephemeral wrappers with permission methods (`can_move`, `can_traverse`) and appearance rendering
- **Service Functions:** `send_message`, `message_location`, `send_room_state`, `move_object`, `check_exit_traversal`, `traverse_exit`, `get_formatted_description`, `show_inventory` — accept `BaseState` directly (no `FlowExecution` dependency)
- **Where events are emitted:** `world/combat/services.py` (damage/attack/incap/death), `world/conditions/services.py` (apply/stage-change/remove), `world/magic/services.py` (technique pre-cast/cast/affected), and the typeclass move/examine hooks
- **Critical Note:** `FlowDefinition`/`FlowStepDefinition`/`TriggerDefinition` are content-exportable via `NaturalKeyMixin` + `CONTENT_MODELS` (#2663), so the lore repo can author the trigger→flow→step wiring that `ConditionTemplate.reactive_triggers` references. The `ensure_*` palette seeds in `world/magic/effect_palette_content.py` remain test/E2E fixtures only; real content ships as lore-repo fixtures. Flow step parameters use name-based lookups (e.g. `threat_pool_name`) rather than raw PKs so they are identity-stable across environments.
- **Authoring API (#3417):** `flows.catalog` (`STEP_ACTION_SPECS`, `event_catalog()`, `service_function_catalog()`, `FILTER_OPS`) is the hand-declared single source of truth for the step-parameter schemas that only exist implicitly in handler bodies; `flows.step_validation.validate_step_tree` (no DRF import) enforces it against an authored step tree. DRF CRUD mounted at `api/flows/` (`catalog/`, `flows/`, `trigger-definitions/`, `triggers/`) via `FlowDefinitionViewSet`/`TriggerDefinitionViewSet`/`TriggerViewSet`/`DslCatalogViewSet`; reads are `IsGMOrStaff`, writes `IsAdminUser` (staff-only v1). `FlowDefinitionWriteSerializer.steps` does a full-tree replace keyed on author-chosen `client_id`/`parent_client_id` (not DB pks); zero-step drafts and exactly-one-root are the only shape rules. `FlowDefinitionDetailSerializer.interactions` (`flows.interactions.flow_interactions`) cross-references what runs a flow, what it emits and who listens, and what it calls. Staff wire `ConditionTemplate.reactive_triggers` via `PATCH api/conditions/templates/{id}/set_reactive_triggers/`. Frontend: `/staff/flows-builder`. Zero new models. Details: [flows.md](flows.md#authoring-api-3417).
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
- **Media (#2408):** `Media` (renamed from `PlayerMedia`) unifies player-uploaded
  and staff-authored art in one model — role is derived from `player_data`
  (null ⇒ staff-authored), not a stored flag; staff rows additionally carry a
  nullable, unique `slug` for natural-key addressing from the lore-repo content
  pipeline (see ADR-0146). `PageBackground` (`slot: PageBackgroundSlot` — HOMEPAGE /
  ROSTER / CG_STAGE / GAME_CLIENT, unique — → `art: Media | None`, `SET_NULL`) maps
  a named page slot to a background `Media` row; read via `GET /api/backgrounds/`.
- **Pattern:** Extend Evennia models without modifying library code
- **Integrates with:** accounts, characters, Evennia core, codex (`CodexEntry.art`),
  character_creation (`StartingArea.crest_art`, `Beginnings.art`)
- **Source:** `src/evennia_extensions/`
- **Details:** [evennia_extensions.md](evennia_extensions.md)

### Dev Seed Orchestrator
Production-callable seed layer for populating sane defaults on a fresh dev install.

- **Entry Point:** `world.seeds.database.seed_dev_database(*, verbose=False) -> SeedReport` — calls every registered cluster seeder in sequence; idempotent (create-if-missing semantics throughout, never overwrites).
- **Config prerequisites (#2724, ADR-0171):** `world.seeds.database.load_content_first()` — the pre-cluster half of `seed_dev_database()`, split out so `test_no_content_slop`'s guard can snapshot row counts *between* the content load and the cluster loop — runs `world.seeds.config_prerequisites.CONFIG_PREREQUISITES` (`dict[str, Callable[[], None]]`, shaped like `CLUSTER_SEEDERS`, 12 entries) BEFORE `core_management.content_fixtures.load_world_content()`. Each entry is a row the code names by string literal (e.g. fatigue's `"fatigue_willpower"` CheckType, the shared "Technique Cast" `ActionTemplate` lore `Technique` fixtures FK by natural key) — declaring the dependency here means a lore fixture always wins over the code default (`load_entries` upserts) and the row never lands inside the seeder-guard's measurement window. Registering a helper here does not remove its existing gameplay call site; both stay idempotent. See `docs/systems/magic.md`'s "Content-vs-config boundary" section and `docs/systems/checks.md`'s "Seeded Compositions" section for the two content-model cases this closes.
- **Cluster registry:** `world.seeds.clusters.CLUSTER_SEEDERS` — `dict[str, Callable]` keyed by cluster name, in seed order: `"checks"` (resolution spine, first), `"magic"`, `"items"`, `"combat"`, `"consent"`, `"character_creation"` (CG-world content, last — after `magic`, which provides the starter-Gift/resonance `finalize_character` picks). Add a new cluster by appending an entry here. `seeded_models()` (flat representative-content list for row-count tracking) and `seeded_models_by_cluster()` (per-cluster inventory for the admin hub) are the two read shapes.
- **Surfaces:**
  - `arx seed dev` — CLI entry point (management command `src/core_management/management/commands/seed.py`; `--verbose` flag prints per-cluster row deltas).
  - Django admin **"Load sane defaults"** button (`src/web/admin/seed_views.py`) — superuser-only; runs `seed_dev_database()` and flashes a success/error message; redirects to the Game Setup hub on success.
  - Django admin **"Game Setup"** hub (`src/web/admin/game_setup_views.py`, `_game_setup/` URL, `admin_game_setup` name) — superuser-only landing page ("Welcome to a new Arx-based instance"): the clone→seed→tweak→export flow, a per-cluster content inventory (via `seeded_models_by_cluster()`) with live row counts, and links to the Big Button, Export/Import, and the World authoring apps. Header link visible to superusers next to the Big Button.
- **Cluster masters:** `src/world/seeds/clusters.py` imports the seed cluster masters (`seed_magic_dev`, `seed_items_dev`, etc.) from `world.seeds.game_content` — relocated there from `integration_tests.game_content` by roadmap task 3.2 (#1220). The `integration_tests.game_content.magic` compatibility facade that kept old test imports working is gone (#2973 Task 4) — every caller imports `world.seeds.game_content.magic` directly. The natively-owned clusters (`checks`, `consent`, `character_creation`) live directly under `src/world/seeds/`.
- **Key modules:** `database.py` (orchestrator), `clusters.py` (per-cluster dispatch + inventory helpers), `checks.py` (`seed_check_resolution_tables()` — the checks spine), `consent.py` (`seed_social_consent_categories()`), `character_creation.py` (`seed_character_creation_dev()` — 12 stat Traits + Rosters unconditionally; Species/Gender/HeightBand/Build/forms/distinctions/Realm/StartingArea/Beginnings/TarotCard/Path all content-repo-owned or gated behind `SEED_SAMPLE_CONTENT`, #2698), `types.py` (`SeedReport` dataclass).
- **Tests:** `src/world/seeds/tests/` — idempotency, non-overwrite, and playable-slice regression (including `TestSeededCharacterCreation` — `finalize_character` runs end-to-end on a seeded-only DB).
- **Source:** `src/world/seeds/`
- **Details:** [seed-and-integration-tests.md](../roadmap/seed-and-integration-tests.md) (Phase 3)

### Game Tuning & Game Ops Dashboards (#1220 / #1221)
Admin-hosted, superuser-only HTMX dashboards for difficulty tuning/simulation and live-game analytics.

- **Game Tuning** (`/admin/_tuning/`, `admin_tuning`) — six HTMX-fragment panels: checks
  probability distributions (`web/admin/tuning/checks_analytics.py` —
  `compute_chart_distributions`, `compute_matchup`), consequence-pool inspector
  (`consequence_analytics.py` — `inspect_pool`, `list_pools`), condition danger ranking
  plus a DE column (`condition_analytics.py` — `compute_condition_danger`;
  `condition_power_analytics.py` — `build_condition_power_panel`, #3390), a Monte Carlo
  party-vs-boss simulation form (`SimulationRunForm` in `web/admin/tuning/views.py`),
  a technique combat-power league table (#3279: `technique_analytics.py` —
  `build_technique_panel`, over
  `world.magic.services.technique_power_eval.evaluate_all_with_reference(EvalContext) ->
  (list[TechniquePowerReport], ReferenceFrame)`; types in
  `world/magic/types/technique_power.py`), and a capability DE-per-point league table
  (#3390: `capability_power_analytics.py` — `build_capability_power_panel`, over
  `world.magic.services.capability_power_eval.evaluate_all_capabilities_with_reference`).
  The evaluator prices every technique payload family in expected damage-equivalent per
  cast (ADR-0223) with per-valuation provenance
  (FORMULA/PARSED/ESTIMATE/UNPRICED_DISPEL/UNPRICEABLE/INERT_PAYLOAD), a baseline vs
  matched-anchor covenant-role band via the shared pure helpers
  `blend_power_contribution`/`specialty_power_contribution`
  (`world/magic/services/power_terms.py`), and mitigation magnitudes parsed from
  MODIFY_PAYLOAD reactive triggers via `protective_magnitude`
  (`world/magic/services/targeting.py`). #3390 (ADR-0239) extracted the row-independent
  DE formula core into `world/magic/services/de_valuation.py` and its shared
  `compute_reference_frame(EvalContext) -> ReferenceFrame` median-baseline-attack
  bootstrap, so the standalone condition (`world/magic/services/condition_power_eval.py`
  — `evaluate_condition`) and capability
  (`world/magic/services/capability_power_eval.py` — `evaluate_capability`) evaluators
  price against the exact same currency — never a second, drifting implementation.
- **Simulator:** `world.combat.simulation.run_party_vs_boss_simulation(SimulationParams) -> SimulationReport`
  drives the real `world.combat.services.resolve_round` pipeline through synthetic,
  locationless encounters inside nested transaction savepoints that are always rolled
  back (isolation contract in the module docstring) — nothing it does is ever persisted,
  and existing `EncounterScalingConfig` tuning is never overwritten.
- **Game Ops** (`/admin/_ops/`, `admin_ops`) - six panels: progression, economy,
  story/GM, and reports-queue analytics (`web/admin/tuning/metrics.py` —
  `progression_series`, `economy_series`, `story_series`, `reports_snapshot`, etc.), a
  refresh-on-demand Technical Health panel (`tech_health.py` - `collect_tech_health`:
  idmapper RAM, process RSS/CPU, open system errors, deploy SHA), and a required-content
  sentinel panel (`required_content.py`, #3444) - `_declarations()` is the single place
  a new content dependency (a code path's hard dependency on a specific authored
  database row) gets registered, and `collect_required_content()` probes the live
  database for each one, since no repo artifact can answer the question (ADR-0238). See
  `docs/adr/0251-content-dependencies-are-a-live-db-registry.md`.
- **Content-repo load:** `web/admin/content_load_views.py` — superuser upsert of the
  maintainers' private content repository (`CONTENT_REPO_PATH` env var) via
  `core_management.content_fixtures.load_world_content`; linked from the Game Setup
  hub. Domains (`DOMAIN_BUILDERS`, `core_management/content_fixtures.py`): `stats`/
  `skills` → `traits.Trait` (#944); `npc_roles` → `npc_services.NPCRole`, `items` →
  `items.ItemTemplate`, `building_kinds` → `buildings.BuildingKind`, `decoration_kinds` →
  `buildings.DecorationKind` (#2266) — every domain upserts by a DB-unique `name`.
  **#2688 adds four prose domains** whose content is authored as per-entry markdown
  instead of fixture JSON, keyed under `content/` because build-domain and
  reference-canon directory names share one namespace in the content repo:
  `content/codex_entries` → `codex.CodexEntry`, `content/beginnings` →
  `character_creation.Beginnings`, `content/starting_areas` →
  `character_creation.StartingArea`, `content/traditions` → `magic.Tradition`.
  `codex.CodexEntry` is the only multi-prose domain: `## Lore` → `lore_content`
  and `## Mechanics` → `mechanics_content`, with **at least one** required rather
  than all (`CodexEntry.clean()` needs only one, and 25 of 28 authored entries have
  no mechanics content). Every single-prose domain keeps the whole-body-to-one-field
  rule unchanged. `export_to_content_repo` writes these four back **as markdown and
  emits no JSON for them** (`MARKDOWN_EXPORT_DOMAINS`), so each model keeps exactly
  one home — and the export is **field-scoped**: only author-owned fields are
  written, so admin-tuned columns (`share_cost`, `learn_*`, `display_order`,
  `is_public`/`is_featured`) are never round-tripped into frontmatter. An optional
  model field must stay optional in its builder, or export can emit a file the
  builder then rejects (regression-tested: `StartingArea.realm` is nullable, and
  `default_starting_room` round-trips because the fallback-room bootstrap needs it).
  `CONTENT_MODELS` (`core_management/content_export.py`) additionally covers
  `character_creation.startingarea`, `evennia_extensions.roomsizetier`, and
  `weather.climate` (#2436/#2448) now that all three carry `NaturalKeyMixin`, plus
  `character_creation.beginnings` and `character_creation.cgexplanation` (Arx
  beginnings content; canonical prose lives in the lore repo's `beginnings/arx.md`),
  and — #2474 — `magic.resonance`/`magic.gift`/`magic.technique`/
  `magic.pathgiftgrant`/`magic.traditiongiftgrant` (the CG starter-catalog models;
  `Technique`'s natural key is `(gift, name)`, `unique_technique_gift_name`, since
  `name` alone collides across gifts). `core_management.content_fixtures.load_entries`
  gained M2M natural-key resolution and stale-field tolerance (an object referencing
  a field the current model no longer has is skipped with a warning, not a crash) to
  carry this content across schema drift. `world.seeds.database.seed_dev_database()`
  now loads content BEFORE any `CLUSTER_SEEDERS` entry runs (previously content load
  had no home in the dev-seed flow at all) and raises `ContentError` if
  `CONTENT_REPO_PATH` is unset/invalid, before writing anything — no silent skip, no
  synthetic in-repo catalog fallback (ADR-0142). See `docs/systems/magic.md`'s "CG
  Starter Gift/Technique Catalog" section for the full seed-ordering/error-handling
  detail; the retired `seed_starter_gift_catalog()` is replaced by
  `MagicContent.create_starter_gift_catalog()` (test-only factory stand-in) for
  suites without a real content-repo checkout.
  #2486 extends that catalog allowlist further: `Technique`'s payload rows
  (`TechniqueDamageProfile`, `TechniqueAppliedCondition`/`RemovedCondition`,
  `TechniqueCapabilityGrant`/`Requirement`, plus the global `TechniqueOutcomeModifier`,
  keyed on `outcome` alone), `magic.restriction`, `magic.portalanchorkind`, and
  `species.speciesgiftgrant` — see `docs/systems/magic.md`'s "Content pipeline"
  section for the full model list and natural keys. M2M resolution happens BEFORE the
  `update_or_create` write, so an unresolvable M2M target defers or skips the whole
  entry rather than leaving a half-loaded row with an empty M2M set.
- **Content credit (#2980, ADR-0196):** every prose-bearing content model (83 of
  them, `world/migrations/0105_credited_content.py`) inherits the abstract
  `CreditedContent` (`world.contributors.models`), four nullable columns
  (`written_by`/`written_on`/`reviewed_by`/`reviewed_on`) pointing at
  `ContentContributor`, a content model in its own right (natural key `name`,
  registered in `CONTENT_MODELS`). The credit columns round-trip on both
  pipeline paths with no extra plumbing: fixture-JSON rows carry them as
  ordinary `fields`, and the four markdown domains carry them as frontmatter
  keys (`_apply_credit_meta` in `content_fixtures.py`), coercing a
  `yaml.safe_load`-parsed date to an ISO string before `write_fixtures`
  serializes it, since `json.dumps` rejects a bare `datetime.date`. The account
  link lives on `evennia_extensions.PlayerData.contributor` (nullable
  OneToOne), not on `ContentContributor`, per ADR-0010. Which text fields
  count as prose at all is an exhaustive, test-guarded classification in
  `core_management/prose_fields.py`, not a name heuristic, which missed nine
  models on a first pass. `tools/prose_report.py` (`just prose-report`) walks a
  content-repo checkout with no Django and no database and reports the
  writer/reviewer backlog per domain.
- **Load conflicts (#3017, ADR-0201):** a credited row (`written_by` set) whose incoming corpus
  value differs from the DB on any field is frozen rather than overwritten -
  `content_fixtures._upsert_fixture_object` skips the write and reports a one-line diagnostic in
  `result.conflicts`; the admin's Load Conflicts pages (`web/admin/content_conflict_views.py`)
  are the only way back, via a typed-natural-key delete-then-reload, one row at a time, never a
  bulk resolve. The same freeze reaches `grid_import`'s credited `TriggerDefinition` refresh
  branch and `world.weather.seed`'s credited `WeatherEmit` upserts. Separately,
  `world.seeds.sample_content.assert_sampling_allowed()` refuses `SEED_SAMPLE_CONTENT` invention
  once any `CONTENT_MODELS` table already has a row within the same `seed_dev_database()` press.
  See `src/core_management/CLAUDE.md`'s "Load conflicts" section and ADR-0201.
- **Row-level export and content session (#3018):** a superuser-only "Export to content repo"
  button on any change form (`web/templates/admin/change_form.html`, gated by
  `web/admin/templatetags/content_export_tags.py`'s `CONTENT_MODELS`/`MARKDOWN_EXPORT_DOMAINS`
  membership check) writes `core_management.content_export.export_single_row()`'s output onto a
  shared branch (`core_management.content_session.SESSION_BRANCH`), one commit per row behind a
  digest-guarded diff confirm, then bundles the accumulated commits into a single pull request
  via the shared `core_management.github_rest` REST client. See the "Row export and content
  session" section in `src/web/admin/CLAUDE.md` and `src/core_management/CLAUDE.md`.
- **Grid content export/import (#2436/#2448):** rooms/areas are no longer deferred —
  `Area`/`RoomProfile` gained permanent identity keys (`slug`/`fixture_key`) and a
  `GridOrigin` export gate (see the Areas section above). `core_management.grid_export.
  export_grid_bundles()` writes one JSON bundle per `origin=AUTHORED` area to
  `<content_root>/fixtures/grid/<area-slug>.json` (area row + fixture-keyed rooms +
  exits + `authored:`-sourced sidecar rows); `core_management.grid_import.
  load_grid_bundles()` is the inverse — four passes (areas topologically by parent
  slug, rooms by `fixture_key`, exits by `(source fixture_key, key)`, sidecars scoped
  per bundle), report-never-delete for any AUTHORED row absent from the bundles. The
  two pipelines don't run independently: a content fixture (e.g. `StartingArea`) can
  reference a room by natural key before the grid bundle that creates it has loaded,
  so `core_management.content_fixtures.load_world_content(content_root) ->
  WorldLoadResult` sequences (1) content fixtures with `load_entries(...,
  defer_unresolved=True)` — an unresolved natural-key FK is queued, not fatal — (2)
  `load_grid_bundles()`, (3) `_retry_deferred()` (#2486): repeated deferral-on passes
  until a pass resolves nothing new (a fixpoint, not a single retry) — needed because
  catalog fixtures can chain ≥2 levels deep against alphabetical load order (e.g.
  grant→technique→gift→resonance, where a one-shot retry only settles the first
  level) — followed by one final deferral-off pass so a genuine gap still lands in
  `skipped`. Both `tools/build_content_fixtures.py --load` and the admin Load view
  call this driver, not a bare `load_entries`. `core_management.content_repo`
  (`resolve_content_root()`/`load_dotenv_content_path()`) is the one canonical
  content-repo path resolver every export/push/load call site uses. See ADR-0140
  (bundle format + rejected alternatives) and `docs/evennia-quirks.md`'s #946 entry
  (why upsert, not `loaddata`).
  Invariant (#2448 review fix): an AUTHORED room's `area` must itself be AUTHORED (never
  NULL or GM/player-owned) — `export_grid_bundles()` only walks rooms reachable through an
  AUTHORED area, so an unhoused AUTHORED room is silently unexportable otherwise;
  `grid_export.find_unhoused_authored_rooms()` is the one query both the exporter (raises)
  and the `--check`/admin-preview surfaces (warn) share. `world.seeds.character_creation.
  ensure_canonical_fallback_room()` houses the canonical fallback starting room in a
  reserved AUTHORED area (`slug="arx"`) for exactly this reason.
- **Strict-mode health gate (#2501):** `tools/build_content_fixtures.py --load --strict`
  exits `7` if any `world_result.skipped` entry isn't covered by
  `<content_root>/fixtures/KNOWN_DRIFT.txt` (one substring pattern per line, `#`-comment
  and blank lines ignored; absent file = no known drift). `core_management.content_health`
  (`group_skips`, `load_known_drift`, `partition_skips`, `render_health_report`) is the
  pure-python layer this rides — import-safe without Django, same convention as
  `content_fixtures.py`. A health report (per-source skip counts, known-drift count, and
  every unexpected skip verbatim) always prints after the load summary, `--strict` or not,
  so a silent-skip regression (the #2501 root cause — 350 rows dropped with no signal) is
  visible even on a plain `--load`. `--strict` requires `--load`. A credited-row load conflict
  (#3017, ADR-0201) never affects the `--strict` exit code - it is a distinct outcome from a
  skip, reported separately.
  `CONTENT_MODELS` (`core_management/content_export.py`) also gained
  `mechanics.application`, `mechanics.prerequisite`, `mechanics.property`, and
  `mechanics.propertycategory` — the loader was already dynamic (any `NaturalKeyMixin`
  model can be fixture-loaded); this only widens the **export** allowlist to cover the
  Capabilities & Challenges catalog.
- **No-cruft corpus renames (#3162):** the upsert discipline above only creates/updates
  by natural key, so renaming a content row in the lore repo and reloading orphans the
  old-named row rather than renaming it. `core_management.content_fixtures.
  apply_content_renames(content_root)` reads `<content_root>/fixtures/RENAMES.json`
  (shape `{"<app_label.model>": {"Old Name": "New Name", ...}}`, absent file → `[]`)
  and `load_world_content` applies it FIRST, before the content fixtures load. Each
  directive renames a row whose single-field `"name"` natural key matches `Old` to
  `New`, unless a row already named `New` exists (idempotent) or no row named `Old`
  exists (nothing to do); a directive naming a composite-natural-key model raises
  `ContentError` rather than silently skipping. `WorldLoadResult.renames_applied`
  carries every rename actually applied this run; both `tools/build_content_fixtures.py
  --load` and the admin Load view print/flash it.
- **Row-level export filters (#2724, ADR-0171):** `CONTENT_MODELS` is a model-level
  allowlist — some registered models mix staff/lore-authored rows with per-player rows a
  service function synthesizes (a personal anima `magic.Ritual`, the per-character
  `checks.CheckType` `ensure_character_magic_check_type` creates). De-registering the
  model would also stop exporting the staff-authored rows, so
  `core_management.content_export.EXPORT_FILTERS` (`dict[str, dict[str, object]]`)
  applies a row-level predicate on top of the allowlist, via
  `queryset.filter(**kwargs)`: `magic.ritual` → `author_account__isnull=True`,
  `checks.checktype` → `owner_sheet__isnull=True`, `checks.checktypetrait` →
  `check_type__owner_sheet__isnull=True`, `evennia_extensions.media` →
  `slug__isnull=False` (pre-existing behavior). Plain filter-kwargs rather than
  `django.db.models.Q`, deliberately — `content_export.py` promises to import cleanly
  without Django configured, and every predicate here is a single AND-only lookup. See
  `docs/systems/checks.md`'s "Seeded Compositions" section and `docs/systems/magic.md`'s
  "Content pipeline" section for the two cases, and ADR-0171 for why this is a real owner
  column rather than a name-pattern exclusion.
- **Authoring Workbench (#3019):** a superuser-only dashboard (`_authoring/`,
  `admin_authoring`) surfacing a worst-first prose backlog queue across every
  `core.app_domains.credited_content_models()` model, a prose-only row editor
  with a guided first-run contributor setup gate, a related-entries/prose-
  mentions pane, and reference search over the database plus opt-in staff-
  docs/Arx I file corpora. See the "Authoring Workbench" section in
  `src/web/admin/CLAUDE.md`.
- **Stock-admin credit complement (#3020):** every registered credited-model admin
  gets a `credit_status` changelist filter and linked column
  (`world/contributors/admin.py`'s `CreditStatusListFilter`/`credit_status`),
  attached uniformly by `web/admin/apps.py`'s `_attach_credit_admin_extras`, a
  `web_admin.E001` system check (`web/admin/checks.py`'s
  `check_credited_admin_fieldsets`) that catches a fieldset missing credit
  coverage, and an "Open in Authoring Workbench" deep link on the change form
  (`web/admin/templatetags/authoring_tags.py`, built from the shared
  `web/admin/authoring/links.py`'s `workbench_editor_url`).
- **Operator guide:** `docs/systems/content-authoring.md` - the end-to-end staff
  walkthrough (load, find gaps, edit/credit, row export, session PR, conflict
  resolution) across #3017-#3020.
- **Permissions:** every view superuser-only (`web.admin.tuning.views.superuser_required`,
  mirroring `game_setup_views.py`'s gate).
- **Source:** `src/web/admin/tuning/`, `src/web/admin/content_load_views.py`,
  `src/core_management/grid_export.py`, `src/core_management/grid_import.py`,
  `src/core_management/content_repo.py`, `src/world/combat/simulation.py`.
- **Details:** [tuning.md](tuning.md)

---

## Player Submissions & Staff Inbox

Player-to-staff contact surfaces plus the unified staff triage inbox.

- **Models** (`world.player_submissions.models`): `PlayerFeedback`, `BugReport` (optional
  GitHub-issue mirror via `github_issues.py`), `PlayerReport` (conduct), `SystemErrorReport`
  (auto-captured runtime errors, #1164 — deduplicated by `signature`, occurrence-counted),
  `Petition` (#2288 — emergency-only structured staff contact: `PetitionCategory`
  UNFAIR_DEATH / SCENE_CONDUCT_EMERGENCY / STUCK_UNPLAYABLE / OTHER_EMERGENCY, per-category
  required refs, one OPEN petition per account via partial unique constraint),
  `SubmitterStanding` (#2288 — per-account track record: `actioned_count` /
  `dismissed_count` / `ignored_count` + `is_ignored` perma-ignore bit).
- **Services** (`world.player_submissions.services`): `run_safely` / `report_error`
  (the #1164 error-capture boundary — never silent-suppress), `submit_petition`
  (one-open gate + category-ref validation), `resolve_petition` / `record_resolution`
  (stamps `SubmitterStanding`; `PlayerFeedbackViewSet.perform_update` stamps the same
  counters on feedback resolution), `set_ignored`, `kudos_total_for` /
  `sender_context` (kudos + standing columns for triage).
- **Endpoints:** `/api/player-submissions/` — `feedback/`, `bug-reports/`,
  `player-reports/`, `system-errors/`, `petitions/` (create/list/retrieve scoped
  self-or-staff; staff `resolve` action validates REVIEWED/DISMISSED; staff
  `ignore-sender` action flips the silent perma-ignore bit; `sender_context`
  serializes staff-only so the ignore bit never leaks to the sender).
- **Web:** player `/petition` page (`PetitionPage` — category picker with
  per-category refs, one-open notice, own-petition history; linked from the
  Profile menu beside feedback/bug-report); staff `StaffPetitionDetailPage`
  (`/staff/petitions/:id` — resolve with notes, sender track record,
  perma-ignore toggle); `StaffInboxPage` gains the Petitions category, sender
  kudos/standing chips, a sender-kudos sort, and the show-ignored reveal.
  Telnet: `petition` is a pointer + own-status check only
  (`commands/account/staff_contact.py`), never a filing surface.
- **Staff inbox** (`world.staff_inbox`): `get_staff_inbox(categories, include_ignored)`
  aggregates open items from every source into `InboxItem` rows (petition items carry
  `sender_context`; petitions from `is_ignored` senders are silently excluded unless
  `include_ignored=True`), `get_account_submission_history` for per-account drill-down.
  Endpoint `/api/staff-inbox/` (`IsAdminUser`).
- **Source:** `src/world/player_submissions/`, `src/world/staff_inbox/`

---

## Downtime Announcements (#3194)

Players get warned before the game goes down — staff-declared maintenance
windows plus the host's automatic security reboot, derived live from systemd's
scheduled-shutdown file rather than typed twice.

- **Models** (`world.downtime.models`): `DowntimeWindow` (`starts_at`,
  `expected_duration_minutes`, player-facing `message`, `canceled_at`;
  authored in the admin, the `RegistrationConfig` staff-surface pattern).
- **Services** (`world.downtime.services`): `get_next_downtime()` — merges the
  next un-canceled window with the scheduled reboot parsed from
  `settings.SCHEDULED_SHUTDOWN_FILE` (`/run/systemd/shutdown/scheduled`);
  returns the frozen `PlannedDowntime` dataclass or None.
- **Endpoints:** `/api/downtime/next/` (public GET, polled by the banner).
- **Web:** `DowntimeBanner` in `Layout` — 5-minute poll, renders within 24h of
  the window, flips to in-progress copy once it starts.
- **Source:** `src/world/downtime/`
- **Details:** [downtime.md](downtime.md)

## Registration (#3054)

Invitation-gated account registration — closed by default; staff issue per-email
single-use invites or flip a DB-singleton toggle to open registration for early
access, no deploy required.

- **Models** (`world.registration.models`): `RegistrationConfig` (singleton pk=1,
  `registration_open` bool, mirrors `world.scenes.SceneRoundDefaultsConfig`),
  `AccountInvite` (`email`, unique `token` via `secrets.token_urlsafe(32)`,
  `invited_by` PROTECT, `expires_at`, `redeemed_at`/`redeemed_by`, `revoked_at`,
  `note`; derived `status` property — `InviteStatus` PENDING/REDEEMED/REVOKED/
  EXPIRED, never stored), `AccountMailFailure` (#3193 — ledger of failed
  account-mail sends, written by the adapter's `send_mail` catch, read-only
  admin).
- **Services** (`world.registration.services`): `issue_invite` (active-invite
  dedup), `revoke_invite`, `signup_allowed` (the neutral bool predicate — never
  distinguishes *why* signup is refused), `redeem_invite` (stamps redemption from
  the adapter's `save_user`), `record_mail_failure`, `build_verification_link`
  (#3193 — on-demand allauth HMAC key for an unverified address; raises
  `AlreadyVerifiedError` when there is nothing to verify).
- **Adapter seam:** `evennia_extensions.adapters.ArxAccountAdapter
  .is_open_for_signup` overrides the previously-unused allauth hook, re-parsing
  the already-cached `request.body` JSON to read `email`/`invite_token` (the
  headless `SignupView.post` calls this hook before the validated `SignupInput`
  exists). Proven at the real endpoint by journey tests, not just unit tests.
- **Endpoints:** `/api/registration/status/` (public GET, `{"open": bool}`, no
  invite enumeration); `/api/staff/invites/` (staff `IsAdminUser` — issue/list/
  retrieve + `revoke` action); `/api/staff/verification-link/` (#3193 — staff
  POST `{email}` → verification URL for an unverified account, audit-logged).
- **Mail resilience (#3193):** `ArxAccountAdapter.send_mail` catches every
  provider failure — a mail outage must not 500 signup or login; failures land
  in `AccountMailFailure` and the client tolerates non-JSON error bodies.
- **Web:** `RegisterPage` (invite field auto-filled from `?invite=`, invite-only
  notice when closed with no token); `StaffInvitesPage` (`/staff/invites`, linked
  from the Staff Hub) — issue/list/filter/revoke/copy-link + Copy Verification
  Link (#3193).
- **Settings:** `NEW_ACCOUNT_REGISTRATION_ENABLED = False` closes telnet `create`;
  connect-screen copy points telnet users at the website.
- **Adjacent (already built, verified via anti-reinvention pass):** the staff
  manual-verify fallback for a Resend misdelivery already exists —
  `EmailAddressAdmin.mark_as_verified`/`mark_as_unverified` in
  `evennia_extensions/admin.py`.
- **Source:** `src/world/registration/`, `src/evennia_extensions/adapters.py`
- **Account settings (#3591):** `/profile/account` lets a signed-in player change
  email and password and manage two-factor authentication (2FA), all through
  `allauth.headless` endpoints (no home-grown credential views). The one
  first-party field is `PlayerData.block_telnet_login_with_2fa` (opt-in on top of
  opt-in 2FA, read by `Account.authenticate`, written by
  `GET`/`PATCH /api/account/security-settings/`); TOTP secrets and recovery-code
  seeds are encrypted at rest by `MFA_ADAPTER = evennia_extensions.mfa_adapter
  .ArxMFAAdapter` under `MFA_SECRETS_KEY`, checked at startup and by the
  `mfa-secrets-key` required-content probe. See ADR-0266 (telnet block is a
  second opt-in) and ADR-0267 (dedicated encryption key), and registration.md's
  "Account settings" section for endpoints and runbooks.
- **Details:** [registration.md](registration.md)

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

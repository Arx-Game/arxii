# Magic System

**Status:** in-progress
**Depends on:** Traits, Progression, Relationships, Combat, Crafting (for fashion/resonance)

## Overview
Magic in Arx II is deeply personal and relationship-driven. A character's magical power grows from who they are, who they connect with, and how the world perceives them. The system ties together affinities, resonances, gifts, techniques, and threads into a cohesive magical identity that evolves throughout play.

## Core Mechanics

### Intensity and Control
Every technique has two core stats: **intensity** (raw power) and **control** (safety/precision). These are base values on the technique, modified at runtime by resonance, affinity bonuses, combat escalation, and audere states.

- When intensity exceeds control, effects become unpredictable and anima cost can spike
- If actual anima cost exceeds the character's pool, the excess deals damage to the caster
- This creates the heroic sacrifice mechanic — push for maximum power at the risk of self-destruction
- Higher-tier techniques have disproportionately more intensity relative to control, making them inherently more volatile

### Aura → Power (affinity alignment + resonance standing)
Aura and resonance feed technique **power** through the `aura_power_term` stage of the
power pipeline, tuned via the `AuraPowerConfig` singleton (staff-authored; zero
defaults = disabled). Two combined axes:
- **Affinity alignment:** the caster's `CharacterAura` percentage in the affinity
  matching the technique's resonance(s), scaled by `affinity_alignment_bonus`
- **Resonance standing:** `CharacterResonance.lifetime_earned` (the monotonic standing
  earned from scene endorsements — the "aura farming" loop) scaled by
  `resonance_standing_bonus`, clamped by `resonance_standing_cap` (per-level caps: #853)

Standing uses lifetime earned, never spendable balance, so spending resonance never
weakens the aura. (The old fixed per-10-resonance intensity/control conversion was
retired by the resonance pivot.)

### Combat Escalation (not yet built — #872)
In serious boss fights, intensity auto-escalates each round. Characters make control checks to keep control in pace. Relationship events (true love threatened, ally falls) can spike intensity dramatically. Emotional state (anger, desperation) also feeds intensity. This mirrors superhero/fantasy boss fight pacing — things only escalate, never reset.

Escalation is complementary to Strain and Audere: it builds pressure naturally so big
dramatic moments never happen on round one, and the climax expresses through clashes,
Soulfray, and — at peak drama — an Audere or Audere Majora offer. Only the
player-triggered levers (Strain, Audere) exist in code today; the round-over-round
build and event-driven spikes are #872.

### No Healing, Shielding Instead
Restoration mechanics are counter to the tension-building combat design. Shielding prevents damage without undoing escalation. Healing is absent by design.

### Anima
Magical resource. Each technique has a base anima cost. In combat, active techniques drain anima per round. Out of combat, techniques drain once and fade on room leave or hourly cron. Anima recovery is handled through personalized rituals.

## Key Design Points
- **Affinities:** Three magical alignments (Celestial, Primal, Abyssal) expressed as percentages of a character's aura
- **Resonances:** Personal magical themes mapped to ModifierTargets — a character's magical "vibe" that strengthens specific abilities
- **Gifts:** Thematic power collections that capture a character's magical identity. Named symbolically (e.g., "Flames of the Defiant"). Serve as containers for techniques
- **Cantrips:** Simplified, staff-curated techniques for CG. A cantrip IS a baby technique — same mechanical system (intensity, control, anima cost, effect type, style), just preset at low values. At CG finalization, a cantrip creates a real Technique in the character's Gift
- **Techniques:** Magical abilities with intensity, control, level, style, effect type, and anima cost. The primary way magic manifests in gameplay. Cantrips are the starting point; full technique creation unlocks post-CG
- **Threads:** Magical relationships between characters. Bond strength feeds magical power — characters who are deeply connected are magically stronger together. Tying a thread to a technique gives better resonance-to-stat conversion for that technique
- **Motifs:** A character's magical aesthetic — the imagery and symbolism that defines their magic
- **Facets:** Hierarchical imagery/symbolism nodes. Items and fashion can have facets that map to character resonances, creating the fashion-to-power feedback loop
- **Traditions:** Magical schools/lineages that provide templates and community
- **Reincarnation/Atavism:** Past life tracking that can influence current magical development
- **Magic feeds off perception:** How others see a character influences their magical strength. "Aura farming" — making a dramatic entrance at a ball — is literally a viable strategy
- **Audere Majora:** Temporarily grants access to intensity far beyond control. Maximum drama, maximum risk. Feeds the "battered down, break through" heroic arc

## Effect Types
Known effect categories (will expand as combat develops):
- **Weapon enhancement** — adds damage to weapon attacks (flame blade)
- **Ranged attack** — standalone damage, scales with intensity (fire bolt)
- **Buff** — applies beneficial conditions
- **Debuff** — applies/removes/counters detrimental conditions
- **Defense** — self-warding and warding others
- **Utility** — non-combat effects (illusions, environmental manipulation, grid effects)

Some abilities cross categories (poison touch = attack + subtle assassination tool) and will need the restriction/tag system to express.

## What Exists
- **Models:** CharacterAura, CharacterResonance (reshaped per Spec A §2.2 —
  balance + lifetime_earned), Gift, CharacterGift, Technique,
  CharacterTechnique, TechniqueStyle, EffectType, Restriction, IntensityTier,
  CharacterAnima, AnimaRitualPerformance (ritual FK now points to magic.Ritual
  with execution_kind=SCENE_ACTION; CharacterAnimaRitual removed), Motif,
  MotifResonance, MotifResonanceAssociation, Facet, CharacterFacet,
  **Thread** (new discriminator + typed-FK design, Spec A §2.1),
  **ThreadPullCost**, **ThreadXPLockedLevel**, **ThreadLevelUnlock**,
  **ThreadPullEffect**, **ThreadWeavingUnlock**, **CharacterThreadWeavingUnlock**,
  **ThreadWeavingTeachingOffer**, **Ritual**, **RitualComponentRequirement**,
  **ImbuingProseTemplate**, Tradition, CharacterTradition,
  CharacterAffinityTotal, Reincarnation, Cantrip, **TechniqueCapabilityGrant**,
  **TechniqueCapabilityRequirement**.
  CombatPull / CombatPullResolvedEffect live in `world/combat` but are
  part of the Spec A surface.
- **Capability grant integration:** TechniqueCapabilityGrant links Techniques to CapabilityTypes (from conditions app) with `base_value + (intensity_multiplier * intensity)` formula. This feeds into the mechanics app's action generation pipeline — when a character has a Technique that grants a Capability, the system can match it against Properties on Challenges to surface available approaches
- **Capability requirement gate (#595):** `TechniqueCapabilityRequirement` (Technique FK + CapabilityType FK + `minimum_value`) authors per-technique prerequisites. `technique_performable(character, technique)` returns False when any requirement is unmet. `declare_action` and the performable-technique filter gate on this, so a character who loses a required capability (e.g., awareness zeroed by Unconscious) can no longer use techniques that need it
- **Cantrip-technique alignment** — cantrip templates produce real Techniques with intensity/control at CG finalization
- **APIs:** Full viewsets and serializers
- **Frontend:** CantripSelector for CG magic stage
- **Tests:** Extensive coverage of affinity totals, anima rituals, techniques, styles, restrictions, motifs, effect types, character magic, services, resonance integration

## CG Magic Flow
See `docs/plans/2026-03-01-magic-revamp-design.md` for the original revamp design and
`docs/plans/2026-03-02-cantrip-technique-alignment.md` for the cantrip-technique alignment.

**Summary:** Player picks a staff-curated cantrip (grouped by archetype, filtered by Path). Behind the scenes, a real Technique with intensity/control/anima cost is created in the character's Gift. Player sees name + description + optional flavor (element/damage type). Mechanical stats are hidden.

**Post-CG progression unlock order:** cantrip (L1) → resonance discovery (L2) → thread weaving + motif (L3) → technique development + anima ritual (L4) → second gift (L5) → deeper magic (L6+)

## What's Needed for MVP

### Technique Use Flow (Design Spec Complete)
**Spec:** `docs/architecture/technique-use-pipeline.md`

The core "I use Flame Lance" pipeline, connecting magic to the existing resolution
infrastructure. Four scopes planned:

**Scope #1 — Technique Use Flow (DONE):**
- Anima cost calculation: `effective_cost = max(base_cost - (control - intensity), 0)`
- Safety checkpoint when anima would go negative (explicit opt-in to life force drain)
- Anima deduction with select_for_update
- Capability value enhancement from runtime intensity
- Soulfray condition applied on overburn (severity scaled to deficit)
- Mishap rider consequences when intensity > control (non-lethal)
- `use_technique()` orchestrator wrapping the existing resolution pipeline

**Scope #2 — Runtime Modifiers and Audere (DONE):**
**Spec:** `docs/architecture/runtime-modifiers-audere.md`

What was built:
- **CharacterEngagement** — first-class model for "what is this character doing that
  has stakes" (OneToOne to ObjectDB, SharedMemoryModel). Observable by other characters.
  Carries process modifier fields (intensity_modifier, control_modifier) for transient
  combat/escalation bonuses that vanish when the engagement ends.
- **Two modifier streams** feeding `get_runtime_technique_stats()`: identity bonuses
  via CharacterModifier (technique_stat ModifierTargets) and process bonuses via
  CharacterEngagement fields. Keeps permanent identity bonuses separate from transient
  process state.
- **Social safety control bonus** when character has no active engagement (magic is
  much safer outside stakes). Authored value, applied directly (not a modifier record).
- **IntensityTier.control_modifier integration** — looked up based on resulting
  runtime intensity after all modifiers.
- **AudereThreshold config model** — authored gates (minimum intensity tier, minimum
  Soulfray stage) and effect values (intensity bonus, anima pool expansion,
  soulfray multiplier). All tunable without code changes.
- **Audere condition lifecycle** — triple-gate eligibility check (intensity tier +
  Soulfray stage + engagement), offer/accept flow with atomic modifier writes, end/cleanup
  with safe reversion. Triggered by intensity-changing events, not during technique use.
- **Soulfray acceleration** — overburn Soulfray severity multiplied by warp_multiplier during
  Audere, reported in TechniqueUseResult.
- **7 integration tests** in RuntimeModifierTests covering the full pipeline.

Documented for future (hook points built, logic not implemented):
- Resonance/affinity bonuses (needs fashion, environment, Gift-resonance filter)
- Technique revelation during Audere (needs Path progression)
- Audere Majora threshold-crossing (needs tier advancement)
- Relationship event intensity spikes (needs combat events, Thread integration)
- Escalation tick triggers (owned by future combat/missions/challenges)
- Contextual modifier evaluation (Trigger-like system for situational bonuses)

**Scope #3 — Soulfray Progression & Consequence Streams (DONE):**
**Spec:** `docs/architecture/soulfray-progression-design.md`

What was built:
- **Severity-driven stage advancement** — `ConditionStage.severity_threshold` enables
  conditions that progress by accumulated severity (not just time). New
  `advance_condition_severity()` service function increments severity and advances
  stage when thresholds are crossed, supporting stage-skipping on large jumps.
- **Soulfray severity accumulation** — `SoulfrayConfig` model holds anima ratio threshold
  and severity scaling. `calculate_soulfray_severity()` converts post-deduction anima
  state to Soulfray severity. Below the threshold ratio, severity ramps with depletion;
  deficit casting adds additional severity.
- **Soulfray-stage-driven safety checkpoint** — Step 3 of `use_technique()` now warns
  based on the character's current Soulfray stage (not anima deficit). First entry into
  Soulfray is unwarned — the "oh no" moment comes on the next cast.
- **Stage consequence pools** — `ConditionStage.consequence_pool` FK fires per
  technique use while at that stage. Consequence selection uses a secondary
  resilience check (magical endurance), modified by both stage-specific
  `ConditionCheckModifier` penalties (escalating per stage) and technique check
  outcome via `TechniqueOutcomeModifier`. Players have agency via skill.
- **Control mishap pools** — `MishapPoolTier` maps control deficit ranges to
  consequence pools. Non-lethal only — imprecision effects independent of Soulfray.
- **MAGICAL_SCARS effect type** — stub handler in the consequence effect system.
  When selected from a Soulfray stage pool, applies a placeholder condition. Future
  work replaces the stub with full alteration resolution considering resonances
  and affinity.
- **9 integration tests** in `SoulfrayProgressionTests` covering the full three-stream
  pipeline: Soulfray accumulation, stage advancement, resilience checks, safety
  checkpoints, control mishaps, technique outcome modifiers, and the full
  combined flow.

**Scope #4 — Technique-Enhanced Social Actions (DONE):**

What was built:
- **Full consequence pipeline for social actions** — All 6 social actions (intimidate, persuade, deceive, flirt, perform, entrance) now use `start_action_resolution()` with consequence pools instead of bare pass/fail checks. Mundane actions can now apply conditions (any effect type available to challenges: conditions, properties, codex grants, etc.)
- **Technique enhancement system** — Players can attach a technique to a social action via `ActionEnhancement` records. The technique wraps the action in `use_technique()`, deducting anima, evaluating Soulfray, and checking for control mishaps. Technique effects (conditions, properties) are rendered as distinct results from social outcomes
- **Available-actions endpoint** — `GET /api/action-requests/available/` returns social actions with pre-calculated technique enhancement options, anima costs, and Soulfray stage warnings for informed player decisions
- **Frontend enhancement selection** — ActionPanel displays technique enhancements per action with cost display and Soulfray warning confirmation flow before technique use
- **Deferred follow-up: enhancement payload not yet folded into unified actions endpoint** — The social-action availability surface (`GET /api/action-requests/available/`) returns an enhancement-rich payload (anima costs, Soulfray warnings, `AvailableEnhancement` lists). The unified actions endpoint (`GET /api/actions/characters/<id>/available/`) returns plain `PlayerAction` descriptors without enhancement data. ActionPanel currently fetches both and joins them client-side by action key. A future task should fold the enhancement data into `PlayerAction` so the unified endpoint is self-contained.
- **Layered result display** — ActionResult shows both social outcome and technique effects as distinct results, making the layered action pipeline transparent to players
- **Integration tests** — Comprehensive tests covering mundane consequences, enhanced pipeline, validation, and available-actions filtering

**Scope #5 — Magical Alteration Resolution (DONE):**

What was built:
- **Three new models** — `MagicalAlterationTemplate` (OneToOne on `ConditionTemplate`,
  carries magic-specific metadata: tier, origin affinity/resonance, library flag,
  visibility), `PendingAlteration` (queued unresolved scars with status lifecycle
  OPEN → RESOLVED / STAFF_CLEARED, scene + triggering-state snapshot), and
  `MagicalAlterationEvent` (immutable provenance audit log). Single migration covers
  all three. Plan/spec at `docs/architecture/magical-alteration-plan.md`.
- **MAGICAL_SCARS handler rewrite** — `_apply_magical_scars` in
  `src/world/mechanics/effect_handlers.py` no longer applies a placeholder condition.
  It calls `create_pending_alteration()`, which queues a `PendingAlteration` and
  defers the actual `ConditionInstance` until the player resolves it.
- **Same-scene escalation** — successive overburns within the same scene upgrade the
  open `PendingAlteration` in place rather than stacking. Higher tier wins; the
  triggering-state snapshot updates to the latest. Different scenes still create
  separate pendings.
- **Progression gate** — `has_pending_alterations(sheet)` is checked by
  `world.progression.services.spends.spend_xp_on_unlock`; XP/unlock spending raises
  `AlterationGateError` until all pendings are RESOLVED or STAFF_CLEARED.
- **Service layer** — `create_pending_alteration`, `resolve_pending_alteration`,
  `staff_clear_alteration`, `validate_alteration_resolution`, `get_library_entries`,
  `has_pending_alterations`. Resolution is atomic: schema validation → template
  creation/lookup → condition instance application → event log → pending status update,
  all in one transaction with rollback on apply failure.
- **Two resolution paths** — *library pick* (player selects an existing staff-curated
  `MagicalAlterationTemplate` matching their tier/affinity/resonance, applied as-is)
  and *author from scratch* (player provides name, descriptions, weakness/resonance/
  social-reactivity magnitudes, visibility flag — validated against `ALTERATION_TIER_CAPS`
  per-tier ceilings). Library path is duplicate-checked.
- **Constrained-authoring schema validation** — `validate_alteration_resolution` enforces
  per-tier caps on weakness magnitude, resonance bonus magnitude, social reactivity
  magnitude, visibility-required flag, and minimum description length. First instance of
  the constrained-authoring pattern (structured form → ceiling check → atomic effect
  creation) intended to be reused for techniques and consequences.
- **REST API** — `PendingAlterationViewSet` (account-scoped queryset) at
  `/api/magic/pending-alterations/` with `GET` list/retrieve, `POST {id}/resolve/`
  (dispatches library vs scratch by payload), and `GET {id}/library/` (returns
  tier-matched templates ordered by affinity match).
- **Comprehensive test coverage** — model unit tests, service tests (creation,
  escalation, resolution, gate, staff-clear, atomic rollback), validation tests
  (both paths, all caps), view tests (APITestCase + setUpTestData + force_authenticate),
  handler tests, and 12 end-to-end pipeline integration tests in
  `src/integration_tests/pipeline/test_alteration_pipeline.py` driving the full chain
  `use_technique → Soulfray accumulation → consequence pool → MAGICAL_SCARS handler →
  PendingAlteration → resolve_pending_alteration → ConditionInstance + event + gate
  release`. `MagicContent.create_alteration_content()` extends the integration-test
  game-content factory with library entries (with effect rows) plus a wired Soulfray
  consequence pool and stage.
- **Scope boundary preserved** — passive effects only. Reactive side effects on the
  scar template (cold-iron triggers, holy-ground reactions) remain Scope 5.5.

Decoupling: Standalone. Does NOT depend on Scope 6 (Soulfray recovery). Shipped on
the `magical-scars` branch.

**Resonance Pivot — Spec A (Threads + Currency + Rituals + Mage Scars rename) — DONE:**

**Spec:** `docs/architecture/resonance-threads.md`

This is the first of a four-spec resonance pivot (A, B, C, D). Spec A
pivots Resonance from a passive rank to a per-resonance **currency** that
gets earned from identity-expressive RP, spent to develop **Threads**
(anchors to specific traits/techniques/items/rooms/relationship-tracks/
relationship-capstones), and spent again to **pull** on those threads
during actions for authored mechanical payoff.

What was built (Phases 0–17, 19 phases total counting Phase 18 — this
completion note):

- **Legacy 5-axis Thread family deleted.** `magic.Thread` (old),
  `ThreadType`, `ThreadJournal`, `ThreadResonance`, and
  `CharacterResonanceTotal` removed. `is_soul_tether` migrated to
  `CharacterRelationship`. Journaling preserved via relationships-app
  writeups plus a new `JournalEntry.related_threads` M2M for
  non-relationship threads.
- **New `Thread` model.** Discriminator (`target_kind`) + five typed FK
  columns (`target_trait`, `target_technique`, `target_object`,
  `target_relationship_track`, `target_capstone`) — exactly one populated,
  matching the discriminator. All FKs are PROTECT. Triple-layer integrity:
  `clean()`, per-kind CheckConstraints, per-kind partial UniqueConstraints.
  `retired_at` provides soft-retire.
- **CharacterResonance reshaped (Spec §2.2).** Collapsed identity +
  currency into one model. `balance` (spendable, no cap) and
  `lifetime_earned` (monotonic audit) replaced the old
  `scope`/`strength`/`is_active` shape; row existence now replaces
  `is_active`. Re-FK'd from ObjectDB → CharacterSheet.
- **Resonance economy services.** `grant_resonance` (lazy-create row on
  earn; Spec C will author the gain surfaces), `spend_resonance_for_imbuing`
  (greedy advancement through `developed_points` → `level`; stops at
  XP-lock boundaries and effective cap), `spend_resonance_for_pull`
  (combat and ephemeral paths, §3.8 duration model),
  `preview_resonance_pull` (read-only wire preview),
  `resolve_pull_effects` (runtime resolver), `cross_thread_xp_lock`
  (pays XP at a boundary), `weave_thread` (create Thread after unlock
  check), `update_thread_narrative`, `imbue_ready_threads` /
  `near_xp_lock_threads` / `threads_blocked_by_cap` (UI hints),
  `compute_thread_weaving_xp_cost`, `accept_thread_weaving_unlock`
  (records purchase with Path-aware pricing), plus `recompute_max_health_with_threads`
  and `apply_damage_reduction_from_threads` for VITAL_BONUS routing.
- **Pull-cost / XP-lock / Effect / Ritual authored catalogs.**
  `ThreadPullCost` (per-tier data knobs; formula lives in the service),
  `ThreadXPLockedLevel` (boundary price list), `ThreadPullEffect`
  (authored template keyed (`target_kind`, `resonance`, `tier`,
  `min_thread_level`); effect_kind chooses the payload column —
  `FLAT_BONUS` / `INTENSITY_BUMP` / `VITAL_BONUS` with `vital_target` /
  `CAPABILITY_GRANT` / `NARRATIVE_ONLY`), `ImbuingProseTemplate` (fallback
  prose), `Ritual` + `RitualComponentRequirement` (SERVICE or FLOW
  dispatch, component consumption).
- **ThreadWeaving acquisition family.** `ThreadWeavingUnlock` (authored
  catalog; discriminator + typed FKs; per-kind partial unique +
  CheckConstraints), `CharacterThreadWeavingUnlock` (per-character
  purchase; unique per (character, unlock); captures Path-multiplied
  `xp_spent`), `ThreadWeavingTeachingOffer` (teacher offer; mirrors
  CodexTeachingOffer).
- **CombatPull / CombatPullResolvedEffect.** Live in `world/combat`.
  Persist committed pulls across round transitions and request boundaries.
  Resolved effects are a frozen child-table snapshot (no JSONField);
  mid-round authoring edits can't retroactively alter a committed pull.
  One pull per participant per round (unique_together).
- **VITAL_BONUS routing.** Tier-0 VITAL_BONUS rows are passive (always
  on while the anchor exists — enforced automatically by Thread's
  PROTECT FKs, see `CharacterThreadHandler.passive_vital_bonuses`
  docstring). Tier 1+ VITAL_BONUS rows persist under the standard
  pull-duration model. MAX_HEALTH folds into `recompute_max_health_with_threads`
  as an addend; DAMAGE_TAKEN_REDUCTION applies on the combat
  `DamagePreApply` hook. Pull expiry uses clamp-not-injure semantics
  (current HP clamps to the new max; it never injures).
- **PerformRitualAction with dual dispatch.** Actions-layer wrapper that
  validates components, then dispatches either via a registered service
  path (Imbuing being the first) or via FlowDefinition. Enforces
  component consumption atomically.
- **API surface (Spec §4.5).** ThreadViewSet (GET/POST/DELETE, soft-retire
  on DELETE; CRUD gated on thread ownership via `character_sheet_id`),
  ThreadPullPreviewView (POST `/thread-pull-preview/`),
  RitualPerformView (POST `/rituals/perform/`, resolves primitive kwargs
  → model instances), ThreadWeavingTeachingOfferViewSet (GET), reshaped
  CharacterResonanceViewSet.
- **Per-character handlers (Spec §3.7).** `character.threads`
  (`CharacterThreadHandler` — cached thread list with passive
  VITAL_BONUS aggregation), `character.resonances`
  (`CharacterResonanceHandler` — cached `{resonance_pk: row}` dict;
  `balance(resonance)`, `lifetime(resonance)`, `get_or_create`,
  `most_recently_earned` for Mage Scars origin derivation),
  `character.combat_pulls` (`CharacterCombatPullHandler` in
  `world/combat` — active pulls + `active_pull_vital_bonuses`).
- **Mage Scars rename (§7.2).** Display-only — class names and table
  names unchanged; verbose_names + CLI strings + docs updated.

**Resonance Pivot — Spec C (Resonance Gain Surfaces) — DONE:**

**Spec:** `docs/architecture/resonance-gain.md`

Spec C implements the gain surfaces — the authored systems where characters earn resonance
through IC roleplay (pose endorsements, scene entry, residence trickle, outfit wear).
Complements Spec A's resonance-as-currency spending pipeline. Pairs endorsements with
an audit ledger (typed-FK `ResonanceGrant`), configurable tuning, and daily/weekly schedulers.

What was built:

- **Models:** `ResonanceGainConfig` (singleton per-site tuning: weekly pot, scene-entry
  grant, residence/outfit trickling, same-pair daily cap, settlement day), `PoseEndorsement`
  (character A endorses pose by character B; 8-check precondition gate), `SceneEntryEndorsement`
  (immediate flat grant on room entry, captures persona snapshot), `ResonanceGrant` (typed-FK
  audit ledger keyed on source: POSE_ENDORSEMENT, SCENE_ENTRY, RESIDENCE_TRICKLE, OUTFIT_TRICKLE;
  discriminator pattern ensures atomic grant journaling). Room resonance data lives in the
  locations cascade as `LocationValueModifier` rows with `key_type=RESONANCE` (the former
  `RoomAuraProfile` / `RoomResonance` tag models were retired during the cascade unification
  refactor — see docs/plans/2026-05-14-room-cascade-resonance-unification.md).
- **Services:** `grant_resonance(..., source=GainSource.X, typed_fk_kwargs)` — typed-FK signature
  with atomic ledger write; `create_pose_endorsement` — 8 preconditions (not self/alt/whisper/
  private/claimed/duplicate/active-engagement/masqueraded); `create_scene_entry_endorsement`
  — immediate flat grant, persona_snapshot capture; `settle_weekly_pot` — ceil-divide budget
  across earning characters, idempotent; `residence_trickle_tick` — daily residence trickle
  orchestrator; `resonance_daily_tick` — master daily tick (residence + outfit stub);
  `resonance_weekly_settlement_tick` — weekly pose-settlement orchestrator;
  `tag_room_resonance` / `untag_room_resonance` — aura profile management;
  `set_residence` / `get_residence_resonances` — residence FK + intersection queries;
  `account_for_sheet` / `get_resonance_gain_config` — helpers.
- **APIs:** `PoseEndorsementViewSet` (POST to create with precondition gate; DELETE if unsettled);
  `SceneEntryEndorsementViewSet` (POST to create only; DELETE deferred with `ResonanceGrantReversal`);
  `ResonanceGrantViewSet` (read-only, user-scoped with staff bypass for audit);
  `CharacterSheet` serializer exposes `current_residence` FK.
- **Admin:** `ResonanceGainConfig` singleton admin (has_add_permission False when row exists);
  read-only ledger admin for `ResonanceGrant`;
  read-only admins for endorsements; staff-grant admin action on `CharacterResonance`.
- **Scheduler:** `magic.resonance_daily` (24h interval); `magic.resonance_weekly_settlement`
  (7d interval, settable day via config).
- **Tuning knobs** (on `ResonanceGainConfig`): `weekly_pot_per_character` (default 20),
  `scene_entry_grant` (default 4), `residence_daily_trickle_per_resonance` (default 1),
  `outfit_daily_trickle_per_item_resonance` (default 1, unused until Items),
  `same_pair_daily_cap` (default 0 = disabled), `settlement_day_of_week` (default 0 = Monday).
- **Test coverage:** 9 integration tests exercising the full pipeline (pose settlement,
  scene entry grant, alt guard, masquerade, residence trickle, outfit stub, tuning,
  whisper exclusion, DELETE lifecycle); 50+ unit tests across models, services, API, admin.

Deferred (follow-up PRs):

- Scene-entry endorsement retraction (`ResonanceGrantReversal` sibling model — pose
  endorsement DELETE already ships).
- `+enter` command implementation (Spec C only reads `pose_kind=ENTRY`).
- Item authoring + outfit tick activation (ships with Items system).
- Public leaderboard (default-private ledger now, opt-in public later).

Decoupling: Standalone. Does NOT depend on Scope 5.5 (reactive layer) or Scope 6
(Soulfray recovery). Shipped on the `resonance-spec-c-gain-surfaces` branch.

Not in Spec C (authored separately): Spec B (Relational Resilience, Soul Tether,
Ritual Capstones), Spec D (Ritual-grade items + ITEM / ROOM anchor cap formulas —
Imbuing against ITEM/ROOM currently raises `AnchorCapNotImplemented`).

**Resonance Pivot — Spec D PR1 (Fashion Facets + Covenant Gear) — DONE:**

**Spec:** `docs/architecture/items-fashion-mantles.md`
**Branch:** `spec-d-items-fashion-mantles-design`

PR1 of four: wires the facet + covenant data layer into the resonance/modifier pipeline.
No crafting UI yet; the outfit trickle is now live.

What was built:

- **`FACET` and `COVENANT_ROLE` `TargetKind` values** added to `world.magic.constants.TargetKind`.
  `Thread.target_facet` (FK to `magic.Facet`) and `Thread.target_covenant_role` (FK to
  `covenants.CovenantRole`) typed FKs added to the discriminator family.
- **FACET anchor cap formula** (Spec D §6.1) in `compute_anchor_cap`:
  `min(lifetime_earned // ANCHOR_CAP_FACET_DIVISOR, path_stage × ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE)`
  — earned resonance gates how much anchor capacity a facet thread can accrue, with a
  per-path-stage hard ceiling.
- **COVENANT_ROLE anchor cap** (Spec D §6.3): `current_level × 10` — scales with
  the character's current covenant level.
- **Worn-items gate on `spend_resonance_for_pull`** — FACET-kind threads check
  `character.equipped_items.item_facets_for(facet)` before allowing a pull; raises
  `NoMatchingWornFacetItemsError` (with `user_message`) if no matching worn item exists.
- **FACET-aware scaling in `resolve_pull_effects`** — `ThreadPullEffect` tier-0 passive
  rows for FACET threads scale by worn-item attachment quality tier.
- **`outfit_daily_trickle_for_character(sheet) -> int`** — iterates worn items, matches
  `ItemFacet.facet` against character's `CharacterResonance` rows, and issues typed
  `ResonanceGrant` rows (`source=OUTFIT_TRICKLE`, `outfit_item_facet` FK). Returns count
  of grants issued.
- **`outfit_item_facet` typed FK on `ResonanceGrant`** — Spec C shipped the model with an
  OUTFIT_TRICKLE source; PR1 activates it by populating the FK. The discriminator pattern
  enforces exactly one typed FK is non-null per source kind.
- **`resonance_daily_tick()` wired** — now calls `outfit_daily_trickle_for_character`
  alongside the existing residence trickle, completing the Spec C deferred outfit stub.
- **Typed exceptions:**
  - `NoMatchingWornFacetItemsError` (`world.magic.exceptions`) — raised by
    `spend_resonance_for_pull` for FACET threads with no worn matching item
  - `CovenantRoleNeverHeldError` (`world.covenants.exceptions`) — raised by
    `weave_thread` when `target_kind=COVENANT_ROLE` and character has never held the role

Decoupling: Depends on Items (EquippedItem + ItemFacet models) and Covenants
(CharacterCovenantRole). Does NOT depend on Spec B. Shipped on the
`spec-d-items-fashion-mantles-design` branch.

Deferred to PR2–PR4: crafting UI for attaching facets, ITEM/ROOM anchor cap formulas
(still raises `AnchorCapNotImplemented`), mantle system (covenant group attunement),
fashion combat integration.

**Scope #5.5 — Reactive Foundations (DONE — branch `design/reactive-layer`):**

Shipped the reactive layer wedge: events are now emitted at damage, attack,
move, examine, condition-lifecycle, and technique-cast moments; triggers
install from `ConditionInstance` rows and are served by a per-owner
`TriggerHandler` cached on the typeclass. Dispatch is **unified** —
`emit_event(event_name, payload, location)` performs one location walk,
calls `triggers_for(event_name)` on every owner reached, priority-sorts
the combined list globally (descending), and dispatches synchronously on
one `FlowStack`, stopping on cancellation. There is no `scope` field and
no ROOM-vs-PERSONAL split; self-vs-target-vs-bystander semantics come
from JSON filters (`{"path": "target", "op": "==", "value": "self"}` and
friends — the evaluator resolves bare `"self"` to the trigger owner).
Filters are a JSON DSL (`==`, `!=`, `contains`, `has_property`, `in`,
`>`/`<`); AE payloads carry a `targets: list` and emit once through the
same path; flow authors get new action steps (`CANCEL_EVENT`,
`MODIFY_PAYLOAD`, `PROMPT_PLAYER`, plus `EMIT_FLOW_EVENT` that also
routes through `emit_event`); player prompts suspend via Twisted
`Deferred` with no DB rows and resume via the `@reply` account command.
`DEAL_DAMAGE` / `REMOVE_CONDITION` flow steps were deferred — flows can
still trigger those side effects today by emitting a flow event that
calls the existing `apply_damage_to_participant` / `remove_condition`
service functions.

Plan: `docs/superpowers/plans/2026-04-17-reactive-layer-implementation.md`.
Spec: `docs/architecture/reactive-layer-foundation.md`.
Key new modules: `flows/trigger_handler.py`, `flows/emit.py`,
`flows/events/`, `flows/filters/`, `flows/execution/prompts.py`,
`world/combat/damage_source.py`. 29 integration tests cover damage-source
discrimination, cross-character filters, AE topology, stage cascades,
cancellation tiers, and async prompt resolution. The 10 previously
authored-but-skipped tests are now ALL ACTIVE and passing (#527/#528), closed via:
examine-decoration `sections` on the mutable `ExaminePrePayload` + render-back in
`return_appearance`; `Persona.properties` and `Technique.properties` M2Ms to
`mechanics.Property` with `has_property()` accessors; a `shares_covenant` filter op
(covenant membership via the existing `CharacterCovenantRoleHandler`);
`MODIFY_PAYLOAD` `min`/`max` ops; and an opt-in per-scene usage cap in dispatch
(`TriggerHandler` fire counter + `_dispatch_usage_limit`). Remaining follow-ups:
#524 (pre-cast *modify*-payload — cancel already works), #525 (defilement), #526
(scar presence-escalation), and wiring `TriggerHandler.reset_scene_counts` to a
scene-boundary event.

**Power vs Intensity (epic #633, Issue 0 = #524 — Direction B complete via #639):**
Introduced a derived, never-stored `power` value distinct from channeled `intensity`. The
pre-cast `TECHNIQUE_PRE_CAST` `MODIFY_PAYLOAD` path closes the discarded-edit gap (#524).
Intensity still solely drives anima cost, mishap, resonance attribution, and Soulfray (a
ward never reduces it). Power is recomputed each cast via `_derive_power`
(`world/magic/services/techniques.py`).

**#639 — Direction B ordered pipeline + power ledger (DONE):**

What was built: `_derive_power` now returns a transient **`PowerLedger`**
(`world/magic/types/power_ledger.py` — `PowerLedger` / `PowerLedgerEntry` /
`PowerLedgerBuilder`) instead of a scalar. The ledger records every contribution as an
attributed, ordered stage; `ledger.total` is the effective power. The pipeline builds in
this order: **BASE** (channeled intensity from `get_runtime_technique_stats`, which folds
identity + process modifiers, Audere, and tier) → **MULTIPLIER** (the `power_multiplier`
pool, applied as a single aggregate `×(1+Σ%/100)` to BASE; immunity-blocked sources
excluded) → **FLAT** (per-source additive power modifiers via `get_modifier_breakdown` +
per-condition rows via `get_condition_modifier_breakdown`; immunity-blocked excluded) →
**TERM** (`get_power_term_providers()`; level, aura, and thread all live — see #768) → **ENVIRONMENT**
(cast-time `evaluate_resonance_environment` AMPLIFY magnitude only; OPPOSED penalty stays
in the existing Step 10 backfire; ALIGNED persistent boon flows through FLAT/condition —
double-count guards in both cases; evaluate-once per cast). In the combat resolver:
**COMBAT_PULL** (INTENSITY_BUMP pulls added on top) → **PENETRATION** (a graded check
vs the target's `barrier_strength`; `get_penetration_factor` looks up the authored
`PenetrationOutcomeFactor` ladder: `factor=0` → power set to 0 with "ward (bounced)",
`factor=1.00` → clean penetration recorded without power change, partial/overpen →
`multiply` entry; damage-type resistance is soaked once downstream, never here) →
**CLAMP** (floor at 0). A pre-cast reactive `MODIFY_PAYLOAD` edit to `payload.power`
appends a **REACTIVE** entry to reconcile the ledger. The ledger rides the
`TechniquePreCastPayload` / `TechniqueCastPayload` / `TechniqueAffectedPayload` event
payloads, and combat narration folds a concise ward/environment outcome clause via
`render_action_outcome_narration` (`world/combat/interaction_services.py`). The recompute
invariant is preserved — power is never stored. Research + candidate-directions report:
`docs/architecture/power-intensity-research.md`. Architecture reference (as-built):
`docs/architecture/power-derivation.md`.

**#768 — aura & thread power-term providers (DONE):**

The two remaining `PowerStage.TERM` providers are now live (joining `level_power_term`):

- **`aura_power_term`** — staff-tunable via the `AuraPowerConfig` singleton (zero
  defaults = disabled). Two combined axes: *affinity alignment* (the caster's
  `CharacterAura` percentage in the affinity matching the technique's resonance(s),
  proportional to `affinity_alignment_bonus`) and *resonance standing* — the
  "aura farming" loop: `CharacterResonance.lifetime_earned` (the monotonic standing
  earned from scene reactions via the Spec C endorsement system) × `resonance_standing_bonus`,
  clamped by `resonance_standing_cap`. Uses `lifetime_earned` (not spendable `balance`)
  so spending resonance never weakens the aura.
- **`thread_power_term`** — out-of-combat per-thread `INTENSITY_BUMP` contribution, the
  RP analog of the combat `COMBAT_PULL` path. Reuses the existing `resolve_pull_effects`
  scaler over `ApplicableThread`s (tier-0 passive + declared paid pulls), so out-of-combat
  and combat scaling agree.

Wiring: `build_cast_applicable_threads` (`services/cast_threads.py`) computes a cast's
in-scope passive threads (via `_anchor_in_action`) plus an optional `CastPullDeclaration`;
`use_technique` threads them into `_derive_power` and charges a declared pull (after the
soulfray/pre-cast gates, before anima deduction). The two non-combat scene callers
(`scenes/cast_services.py`, `scenes/action_services.py`) opt in; combat is unchanged.
Per-level softcaps/hardcaps on the resonance-standing axis remain a deferred follow-up.

**#854 — player-facing cast pull declaration (DONE):** the public cast API threads a
`cast_pull` end-to-end: `TechniqueCastCreateSerializer` takes a nested
`pull {resonance_id, tier, thread_ids}` (validated for ownership/resonance/retired/
duplicates; hostile casts reject it — combat owns `CombatPull`), the view builds the
`CastPullDeclaration`, and the immediate route charges it in-line via `use_technique`
step 3c. Benign-PENDING casts persist the declaration on `SceneCastPullDeclaration`
(OneToOne to `SceneActionRequest` + threads M2M) and re-check payability at consent —
no longer payable (drained balance / retired threads / preview-to-charge race) degrades
to a visible fizzle note in the OUTCOME pose, never an error. The cast dialog reuses
`ThreadPullPicker` with the `applicable-pulls` cast context, constrained to one
`(resonance, tier)` group per cast.

Scope 5.5 is the deliberate "light up flows/triggers" PR. It must follow Scope 5
**sooner rather than later** — mage scars without reactive side effects are
half a feature, and every later system that wants reactive behavior is blocked
on the same plumbing. This is the wedge that turns paper architecture into
real infrastructure.

What to build:
- **Event seeding and emission at reactive moments.** At minimum: character
  arrival in a room (`character_arrived_in_room`), technique use
  (`technique_used`), social interaction targeting a character (`social_targeted`),
  damage taken (`damage_taken`). Each event carries a payload rich enough for
  trigger filters — destination Property names, technique affinity, source
  identity, damage type, etc.
- **Service function surface for flows.** Concrete service functions that
  FlowDefinitions can call: `force_check(target, check_type, difficulty)`,
  `apply_condition(target, template, severity)`, `deal_damage(target, type, amount)`,
  `emit_observer_message(scene, text)`. Mirrors the pattern in
  `flows/service_functions/`.
- **ConditionTemplate → TriggerDefinition M2M.** Add `reactive_triggers` as
  an M2M from `ConditionTemplate` to `flows.TriggerDefinition`. When a condition
  is applied to a character, any TriggerDefinitions on the template get
  instantiated as `Trigger` rows on the character's `ObjectDB` and registered
  with the room's `TriggerRegistry` on entry. When the condition is removed,
  triggers go with it. This lives on the condition (not on
  `MagicalAlterationTemplate`) so distinctions, races, items, curses, and any
  other condition source benefit from the same plumbing.
- **Reference content.** 2-3 fully-authored reactive scars exercising the loop
  end-to-end: e.g., an Abyssal-aligned character with the "Hallowed Rejection"
  scar takes a forced check on entering rooms with the `holy_ground` Property,
  applying a `Burning` condition on failure. These are the integration tests
  that prove the plumbing works.
- **Documentation pass.** A new `docs/roadmap/reactive-layer.md` (or section in
  `capabilities-and-challenges.md`) describing the event surface, payload
  conventions, the service function set, and how to author triggers. This is
  cross-cutting infra; every later consumer needs the reference.

Key design questions to resolve during brainstorm:
- What's the minimum event surface for MVP, and what's the naming convention?
  (Event names are global — once we ship them, renaming is painful.)
- Should event payloads carry resolved Property name lists, or just object PKs
  the trigger flow has to look up? (Affects trigger filter ergonomics vs.
  payload size.)
- How does trigger registration handle scenes vs. the grid? `TriggerRegistry`
  lives on rooms today — does it apply during scene RP, or do scenes get their
  own registry?
- Does `force_check` block flow execution (synchronous resolution) or fire
  asynchronously into a player prompt? Affects how reactive side effects compose.
- How do we prevent trigger storms? (Same character with five reactive scars
  entering a room shouldn't fire 20 nested flows.)

Dependencies:
- Flows/triggers infrastructure (live — `flows/` app, fully implemented)
- Scope 5 ships first so the `MagicalAlterationTemplate.reactive_triggers` link
  exists as the first real consumer

Decoupling: Sequenced AFTER Scope 5, but unblocks far more than magic. Combat
reactions, cursed items, environmental hazards, divine wrath, allergies, observer
reactions, and any future "something happens when X" feature flows through
this PR's plumbing.

**Scope #6 — Soulfray Recovery & Decay (DONE):**
**Spec:** `docs/architecture/soulfray-recovery.md`

What was built:
- **Generalised condition-level decay** — `ConditionTemplate.passive_decay_per_day`,
  `passive_decay_max_severity`, and `passive_decay_blocked_in_engagement` data-drive
  the scheduler. `decay_condition_severity()` retreats through stages when severity
  falls below the current stage's threshold (inverse of `advance_condition_severity`).
  `decay_all_conditions_tick()` iterates every opted-in condition, skipping anyone in
  an active `CharacterEngagement`. No Soulfray-specific code in the scheduler path.
- **Stage-entry aftermath** — `ConditionStage.on_entry_conditions` M2M grants other
  conditions when a stage is entered. `ConditionTemplate.parent_condition` FK anchors
  aftermath templates to their originator. Soulfray stages 2–5 wire to `soul_ache`,
  `arcane_tremor`, and `aura_bleed`; `decay_condition_severity` + `resolve_condition`
  handle cleanup as stages retreat.
- **Generic Treatment system** — `TreatmentTemplate` + `TreatmentAttempt` + `TreatmentTargetKind`
  (`AFTERMATH_CONDITION` | `PENDING_ALTERATION`). `perform_treatment()` handles both
  paths: aftermath severity reduction, and Mage Scar `PendingAlteration` tier reduction
  (`reduce_pending_alteration_tier`). Helper-gated (once per helper/target/scene),
  bond-gated via an existing Thread anchored to a relationship track/capstone,
  resonance-cost via `CharacterResonance.balance`, and scene-gated (participants only,
  no active engagement). Failure risks giving the helper Soulfray severity of their own.
- **Anima Ritual service** — `perform_anima_ritual()` in `magic/services/anima.py`
  rolls a CheckOutcome-tiered budget and spends it on (a) reducing Soulfray severity
  (priority), then (b) refilling the character's anima pool. Crit forces anima to max
  regardless of leftover budget. Once-per-scene per-character; scene-active and
  out-of-engagement gates. Returns a frozen `RitualOutcome` dataclass.
- **Daily anima regen tick** — `anima_regen_tick()` refills each `CharacterAnima` by
  a configured amount. Blocked for any character whose active condition stages carry
  the `blocks_anima_regen` property; also blocked while the character is in a
  `CharacterEngagement`. Returns a frozen `AnimaRegenTickSummary`.
- **Scheduler integration** — both ticks registered as daily tasks on the
  world-clock scheduler, matching the AP-regen shape. Idempotent and data-driven;
  no Soulfray FK in the scheduler.
- **5-stage Soulfray + re-seeded Audere gate** — Soulfray's authored stage list
  extended from 3 to 5 (Fraying → Tearing → Ripping → Sundering → Unravelling) for
  tuning headroom. Stages 2+ carry `blocks_anima_regen`. `AudereThreshold.minimum_warp_stage`
  re-seeds to Ripping (stage 3+) so Audere's gate semantics are unchanged.
- **`magic/models.py`, `services.py`, `types.py` → packages** — split the three
  monoliths into thematic submodules (`models/`, `services/`, `types/`) to keep the
  new ritual/regen code tidy alongside existing thread/weaving content.
- **Seed content factories** — `SoulfrayContentFactory`, `SoulfrayStabilizeAftermathTreatmentFactory`,
  `MageScarReductionTreatmentFactory`, aftermath condition factories
  (`SoulAcheTemplateFactory`, `ArcaneTremorTemplateFactory`, `AuraBleedTemplateFactory`),
  and `wire_soulfray_aftermath()` for tests and future admin seeding.
- **End-to-end integration test** in `src/world/magic/tests/integration/test_soulfray_recovery_flow.py`
  covering accumulation → aftermath application → stabilization → ritual recovery →
  anima regen gating → decay-alone-cannot-recover-stage-2 boundary.

Decoupling: Standalone. Does NOT depend on Scope 5.5 (reactive layer). Shipped on the
`scope-6-soulfray-recovery` branch.

Deferred to later scopes:
- No healing magic (post-scene restoration beyond anima ritual)
- Web/CLI surfaces for ritual + stabilization (service-layer only for now)
- Abyssal corruption as long-term consequence of abyssal magic overuse
- Character loss deferral during Audere (needs combat/mission lifecycle)

**Scope #7 — Corruption (DONE — branch `scope-7-corruption`):**
**Spec:** `docs/architecture/corruption.md`

Foundation for resonance-corruption — the identity-loss risk parallel to
Soulfray's exhaustion injury. Non-Celestial casting accrues per-resonance
corruption; staging mirrors Scope 3+6's condition machinery; terminal
stage (Subsumption) locks the character from protagonism without removing
them from play. Lays the interception hooks Spec B (Soul Tether) will
mediate against.

What was built:
- **Per-resonance counters on `CharacterResonance`** — `corruption_current`
  (mutable; drives stage progression) and `corruption_lifetime` (monotonic
  audit; achievement-tracking surface). Mirrors the existing
  `balance` / `lifetime_earned` pattern.
- **`MagicalAlterationTemplate` kind discriminator** — extended Scope 5's
  alteration model with `kind: TextChoices(MAGE_SCAR | CORRUPTION_TWIST)`,
  plus nullable `resonance` FK + `stage_threshold` populated only for
  CORRUPTION_TWIST rows. Per-discriminator CheckConstraints + `clean()`
  enforce shape. Existing PendingAlteration / library-pick-or-author
  resolution flow handles both kinds without code changes; the XP-spend
  gate (`AlterationGateError`) blocks pendings of either kind.
- **`CorruptionConfig` singleton tuning surface** — affinity coefficients
  (Celestial 0, Primal 0.2, Abyssal 1.0), per-tier coefficients (1× …
  16× from tier 1 to tier 5), push multipliers (deficit / mishap / Audere).
  All staff-tunable via Django admin; no code changes for retuning.
- **Generalized resist-checked stage advancement** — wired the
  existing-but-unused `ConditionStage.resist_check_type` and
  `resist_difficulty` fields into `advance_condition_severity`. Added one
  new field `advancement_resist_failure_kind` (TextChoices,
  ADVANCE_AT_THRESHOLD default for back-compat; HOLD_OVERFLOW for new
  resist-gated content). When HOLD_OVERFLOW + non-null resist_check_type,
  threshold crossings fire a `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`
  reactive event (Scope 5.5 surface, mutable payload for trigger-driven
  difficulty adjustment), then run a resist check; pass holds at the
  prior stage with severity over threshold (pressure mounts), fail
  advances. `SeverityAdvanceResult` gained an `outcome: AdvancementOutcome`
  field (NO_CHANGE / HELD / ADVANCED) — additive; existing destructuring
  callers untouched.
- **Soulfray retrofit** — single data migration sets resist_check_type
  ("Magical Endurance"), per-stage difficulties (8 / 10 / 18 / 25 for
  stages 2-5), and HOLD_OVERFLOW on Soulfray's existing stages. Audere
  remains accessible because stages 1→2 and 2→3 carry low DCs by design;
  the resist check meaningfully gates only the Sundering / Unravelling
  cascade. Reversible.
- **Atomic accrual + reduction services in
  `world/magic/services/corruption.py`** — `accrue_corruption(*, sheet,
  resonance, amount, source, ...)` increments both fields,
  lazy-creates the per-resonance Corruption ConditionInstance only when
  stage 1 threshold is first crossed (sub-threshold accrual leaves no
  condition row), advances the condition via the new resist-check path,
  emits CORRUPTION_ACCRUING (pre-mutation, for Spec B interception),
  CORRUPTION_ACCRUED, CORRUPTION_WARNING (stage 3-4 with explicit
  "character loss" copy), PROTAGONISM_LOCKED (stage 5 entry).
  `reduce_corruption(...)` decrements `corruption_current` (clamped),
  syncs the condition via Scope 6's `decay_condition_severity` (with
  `_skip_corruption_sync=True` guard to prevent recursion when called
  from decay), emits PROTAGONISM_RESTORED on lock exit. Both atomic
  with `select_for_update`.
- **Scope 6 decay extension** — `decay_condition_severity` now calls
  `reduce_corruption` (with `_from_decay=True`) when the condition's
  template has non-null `corruption_resonance`, keeping
  `corruption_current` synced as severity decays. Clean recursion guard
  via the two complementary `_from_decay` / `_skip_corruption_sync`
  flags. Non-Corruption conditions decay unchanged.
- **`ConditionTemplate.corruption_resonance` FK** — non-null marks a
  template as Corruption-kind, drives both the `is_protagonism_locked`
  detection query and the decay-time field sync. Single FK addition;
  preserves backward compat (defaults to NULL).
- **`CharacterSheet.is_protagonism_locked` cached_property** —
  aggregates over future autonomy-loss systems (today: stage-5 Corruption
  ConditionInstance presence; future: berserker terminal, possession,
  etc. extend the OR). Consumer-system gates check the aggregate, not
  the corruption-specific query.
- **Atonement Rite content** — authored Ritual + service function
  (SERVICE-dispatched; FLOW dispatch deferred until the flow system's
  vocabulary covers affinity-in-set checks natively). Self-targeting
  only; performer must be Celestial-affinity-primary or Primal-affinity-
  primary (Abyssal cannot lead); effective only at stages 1-2 (stage 3+
  recovery deferred to Spec B / future Mission rituals). Refusal paths
  raise typed exceptions (`AtonementAffinityError`,
  `AtonementStageOutOfRange`, `AtonementTargetError`) with
  `user_message` / SAFE_MESSAGES allowlist per project pattern.
- **Reference Corruption ConditionTemplate factories** — `Wild Hunt`
  (Primal) and `Web of Spiders` (Abyssal) reference content with full
  5-stage authoring (per-stage severity_threshold, resist_check_type,
  HOLD_OVERFLOW failure_kind, per-affinity DC curves), plus 2
  CORRUPTION_TWIST `MagicalAlterationTemplate` rows per
  (resonance, stage 2/3/4) for the Pending alteration library pool.
  `author_reference_corruption_content()` is the idempotent seeder.
- **Six consumer-system gates** for `is_protagonism_locked` — Spec C
  resonance gain (endorsements raise validation errors for either-side
  lock; trickle/settlement ticks skip locked sheets), progression XP
  spend (raises `ProtagonismLockedError`), AP regen tick (pre-fetches
  locked-character IDs once, skips silently — no N+1), stories
  participation (raises on protagonist-add; existing all-or-nothing
  participation level — no PROTAGONIST/NPC distinction yet),
  scene initiation (raises on player-driven scene creation), resonance
  currency spends (`spend_resonance_for_imbuing` and
  `spend_resonance_for_pull` raise).
- **Audere advisory** — Audere offer flow now includes an explicit
  `advisory_text` containing the literal phrase "character loss" when
  the casting character has any resonance at corruption stage 3+. Stage
  3+ resonances are surfaced by name so the player can make an informed
  push-or-back-off choice.
- **Integration test suite** — 18 scenarios in
  `src/world/magic/tests/integration/test_corruption_flow.py`: lazy
  condition creation, lifetime monotonicity across accrue+reduce, no-
  template no-op, lock entry/exit, Atonement happy paths + refusal
  paths, decay sync, risk-transparency event emission, and full per-cast
  pipeline coverage (Abyssal accrual, Celestial skip, lazy creation
  through the cast pipeline, CORRUPTION_WARNING emission via cast,
  no-sheet NPC silent skip).
- **Pre-existing factory bug fix exposed during integration testing** —
  `ConditionStageFactory.severity_multiplier` formula was tied to
  factory.Sequence's `stage_order` value, overflowing
  DecimalField(max_digits=4, decimal_places=2) once the sequence climbed
  past ~199. Cycled stage_order in 1..5 via modulo. Existing tests that
  set stage_order explicitly are unaffected; the modulo only governs the
  auto-generated default.

Decoupling: Standalone for foundation work (does NOT depend on Spec B,
Scope 5.5 reactive layer is leveraged but not required). Spec B (Soul
Tether) builds on this scope's interception hooks: `CORRUPTION_ACCRUING`
event for redirect, `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` for
tether-mediated resist support, `reduce_corruption` for tether-mediated
rescue rituals, and trace-corruption-to-Sineater via the same
`accrue_corruption` primitive.

Per-cast hook follow-up (DONE):
- **`TechniqueUseResult` extended** with `technique`, `was_deficit`,
  `was_mishap`, `was_audere`, `resonance_involvements`, and
  `corruption_summary` fields. The per-resonance attribution splits
  runtime intensity equally across the gift's resonances (impl-phase
  resolution per spec §10.1 — modifier system does not track
  per-resonance source attribution; equal split matches the §6.1
  target curve). `thread_pull_resonance_spent` reads from active
  `CombatPull` rows for the casting character.
- **`accrue_corruption_for_cast` per-cast orchestrator** — implements
  the spec §3.1 formula (affinity coefficient × tier coefficient ×
  push multipliers, ceil-rounded). Skips Celestial, zero-involvement,
  and zero-tick cases. Returns `CorruptionAccrualSummary`.
- **Pipeline wiring** — Step 9 of `use_technique` calls the orchestrator
  after Soulfray accumulation and mishap rider, before reactive event
  emission. NPCs without a `CharacterSheet` skip silently.
- **Cast-pipeline integration tests** in
  `test_corruption_flow.py:FullCastPipelineCorruptionTests` (5 scenarios,
  see test suite count above).

**Resonance Pivot — Spec B (Soul Tether) — DONE:**

**Spec:** `docs/architecture/soul-tether.md`
**Branch:** `spec-b-soul-tether-design`

Soul Tether is a bond mechanic between two PCs that mediates the Corruption risk a Sinner
accrues from non-Celestial casting. The Sinner's `RELATIONSHIP_CAPSTONE` Thread carries
**the Hollow** — a draining capacity buffer that absorbs incoming corruption; the Sineater
eats sins out of the Hollow via a Sinner-initiated, Sineater-accepted Sineating action.

What was built:

- **Schema:** `Thread.hollow_current` (Hollow capacity buffer), `CharacterResonance.lifetime_helped`
  (monotonic Sineater counter). Two audit models: `Sineating` (records every
  offer/accept/decline cycle with units, anima/fatigue cost, and resonance) and
  `SoulTetherRescue` (records stage-3+ rescue ritual outcomes with before/after stage and
  severity reduced). Migration 0040 / 0041 / 0042.
- **Constants:** `CORRUPTION_RESISTANCE` added to `ThreadPullEffect.EffectKind`. `SoulTetherRole`
  TextChoices in `constants.py`. `SOUL_TETHER_FORMED` / `SOUL_TETHER_DISSOLVED` event names in
  `flows/constants.py`.
- **Services (`world/magic/services/soul_tether.py`):**
  - `accept_soul_tether` — formation Ritual Capstone (affinity gate, unlock gate, idempotency
    check, Sinner Thread auto-weave, `SoulTetherActive` ConditionInstance install,
    trigger installation).
  - `dissolve_soul_tether` — stub dissolution (tears the bond, retires tether Threads, removes
    ConditionInstance + triggers, emits `SOUL_TETHER_DISSOLVED`).
  - `request_sineating` — Sinner-initiated offer (per-scene cap, hollow-max enforcement,
    fires `PROMPT_PLAYER` to Sineater with `SineatingOffer` payload).
  - `resolve_sineating` — Sineater `@reply` resolution (atomic: deducts anima/fatigue,
    increments `hollow_current` and `lifetime_helped`, writes `Sineating` audit row, fires
    achievement stats).
  - `perform_soul_tether_rescue` — stage-3+ rescue ritual (check roll, Strain cost,
    resonance cost, `reduce_corruption` calls, `SoulTetherRescue` audit, achievement stats).
  - `soul_tether_redirect_handler` — reactive subscriber on `CORRUPTION_ACCRUING`; drains
    `hollow_current` to absorb incoming corruption before it accrues to the Sinner; emits
    replacement CORRUPTION_ACCRUING events for overflow; cancels the original event when
    fully absorbed.
  - `soul_tether_stage_advance_prompt` — reactive subscriber on
    `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`; fires `PROMPT_PLAYER` to Sineater with
    `StageAdvanceBonusOffer` payload letting them commit reservoir capacity or take Strain
    to bonus the Sinner's resist check.
  - `resolve_stage_advance_prompt` — Sineater `@reply` resolution for stage-advance prompt.
- **`CORRUPTION_RESISTANCE` effect resolution** — passive tier-0 `ThreadPullEffect` rows on
  Sineater's `RELATIONSHIP_CAPSTONE` Thread; value derived from `lifetime_helped` for that
  resonance. Applied in `accrue_corruption` on the Sineater's own casting path only.
- **Authored content (factories):** `TetherStrainTemplate` (ConditionTemplate for Sineater
  Strain), `SoulTetherActiveTemplate` (ConditionTemplate installed on Sinner at formation;
  carries reactive trigger M2M), `accept_soul_tether` Ritual, `soul_tether_rescue` Ritual,
  `soul_tether_redirect` TriggerDefinition, `soul_tether_stage_advance_prompt`
  TriggerDefinition. All wired via `wire_soul_tether_content()` factory orchestrator.
- **Relationship side:** `RelationshipCapstone.is_ritual_capstone` BooleanField +
  `RelationshipCapstone.ritual` FK (nullable) added to support capstone-gated ritual dispatch.
- **API endpoints:** `POST /api/magic/soul-tether/accept/`,
  `POST /api/magic/soul-tether/<id>/dissolve/`,
  `POST /api/magic/soul-tether/<id>/sineat/request/`,
  `POST /api/magic/soul-tether/<id>/sineat/respond/`,
  `POST /api/magic/soul-tether/<id>/rescue/`,
  `GET /api/magic/soul-tether/<id>/detail/`.
- **Tests:** 207 tests across 7 test files: model integrity (34), service logic (82),
  reactive subscriber behaviour (27), API endpoints (25), corruption resistance (14),
  achievement stats (11), and 14 end-to-end integration tests covering the full loop
  (formation → Sineating → redirect → rescue → dissolution).

Key architectural decisions:
- Passive corruption decay companion shipped in same phase (Scope 7 `decay_all_conditions_tick`
  now also calls `reduce_corruption` when decaying Corruption-kind conditions), completing
  the decay loop that Scope 7 deferred.
- Sineater's `RELATIONSHIP_CAPSTONE` Thread remains optional: `lifetime_helped` accumulates
  regardless; resistance benefit gates on Thread presence. XP-anti-pattern: every spend
  benefits the spender.
- Redirect handler uses `cancel_event` + replacement events for overflow rather than partial
  accrual, keeping the CORRUPTION_ACCRUING pipeline clean and consistent.
- Stage-advance bonus is opt-in (`PROMPT_PLAYER`) — Sineater chooses whether to commit
  reservoir capacity or take Strain at dramatic moments.

Not in this spec (deferred to follow-up):
- Relational Resilience, Ritual of Devotion, Ritual of Betrayal.

Not in this scope (deferred): non-Corruption stage 3+ recovery rituals
(Spec B authors via the same `reduce_corruption` primitive), public
corruption leaderboards (`corruption_lifetime` enables this surface but
no API ships now), Mission-driven cleansing quests, and other
autonomy-loss systems (berserker, possession, mind-control) which
share the protagonism-lock aggregator but design independently.

**Soul Tether UI (DONE — branch `soul-tether-ui`):**

**Plan:** `docs/superpowers/plans/2026-05-04-soul-tether-ui-plan.md`

Web-first frontend for the Soul Tether backend (Spec B). Makes the full Sineating loop,
stage-advance rescue, and bond visibility playable without the `@reply` telnet path.

What was built:

**Generic ritual infrastructure (frontend `src/rituals/`):**
- `RitualViewSet` (`GET /api/magic/rituals/`) — read-only list of rituals filtered by
  `ritual_key`. Adds `input_schema` JSONField to `Ritual` model (nullable; holds JSON
  Schema for structured ritual parameters) with migration 0043.
- `src/rituals/` module skeleton: `api.ts`, `types.ts`, `queries.ts` (`useRituals`,
  `usePerformRitual`), field components (`ResonancePickerField`, `PersonaPickerField`,
  `ScenePickerField`, `TargetCharacterField`, `NumberField`, `BooleanField`,
  `SelectField`), `RitualForm` orchestrator, `RitualPerformDialog`, `RitualCard`,
  `RitualsListPage`, and `/rituals` route. First consumer: `accept_soul_tether` (RELATIONSHIP_CAPSTONE
  capstone action). The infrastructure is generic — future rituals wire in via the
  same `input_schema` + `RitualForm` pipeline.

**Soul Tether–specific surfaces (frontend `src/magic/`):**
- `HollowBar` — visual capacity bar showing `hollow_current / hollow_max` for a
  Sinner's Thread with tooltip breakdown.
- `SineatingInbox` — Sineater's inbox polling `usePendingSineatingOffers()` with
  an Accept/Decline action row per offer.
- `SineatingRequestDialog` — Sinner-side dialog for submitting a Sineating request;
  calls `useRequestSineating()`.
- `SoulTetherRescuePrompt` — Sineater prompt for stage-advance offers; polls
  `usePendingStageAdvanceOffers()`, filters client-side by `expires_at`, renders
  Confirm/Decline buttons that call `useRespondToStageAdvance()`.
- `SoulTetherStatusPanel` — read-only bond summary panel (role badge, corruption
  stage, strain stage, hollow bar) driven by `useSoulTetherDetail()`.
- `ThreadList` — minimal read-only thread inventory pulled from `useThreads()`.
- `queries.ts` / `api.ts` / `types.ts` — typed wrappers for all soul-tether REST
  endpoints (`getSoulTetherDetail`, `getPendingSineatingOffers`,
  `getPendingStageAdvanceOffers`, mutations for sineating/request, sineating/respond,
  rescue, stage-advance/respond, dissolve).

**Backend additions (Spec B follow-up, same branch):**
- `Ritual.input_schema` — JSONField on `Ritual` model; used by the frontend to
  render ritual-specific parameter forms generically.
- `RitualViewSet` — `GET /api/magic/rituals/` with `ritual_key` filter.
- `RelationshipCapstone` list endpoint with `is_ritual_capstone` filter, enabling
  the rituals page to surface capstone-gated rituals for the character.
- `SineatingPendingOffer` and `PendingStageAdvanceOffer` — persistence models
  (SharedMemoryModel) that store server-side prompts so the Sineater's browser can
  poll and act without needing a live WebSocket connection. Includes TTL staleness
  checks and co-location (shared scene) guards. Migrations 0044–0047.
- `is_soul_tether` filter on `CharacterRelationshipViewSet` — lets the
  Relationships page load only tether bonds for the status panel.

**Integration (Phase 4 mounts):**
- `RelationshipsSection` (character sheet) embeds `SoulTetherStatusPanel`; calls
  `useMyTetherBonds()` (filtered `CharacterRelationship` query) to find the
  caller's soul tether bonds and passes relationship IDs to the panel.
- `SceneDetailPage` mounts `SineatingInbox` and `SoulTetherRescuePrompt` side-by-side
  in the scene sidebar, polling on a 30-second interval so offers surface without a
  page refresh.

**Explicit non-goals (deferred):**
- Per-resonance Strain UI (SineatingInbox shows anima/fatigue cost; resonance
  context omitted for now).
- Dissolve UX beyond a minimal action button (no confirmation modal; treat as tertiary).
- Audit/history display for past Sineating cycles.
- Thread weaving and Thread pull UI (ThreadList is read-only).

**Anima Ritual UI (DONE — branch `anima-ritual-design`):**

**Plan:** `docs/superpowers/plans/2026-05-XX-anima-ritual-ui-plan.md`

Closes the loop on the anima ritual mechanic built in Scope 6, making it playable entirely
from the web interface. Delivers the social-hook mechanic (the ritual can only be performed
with another PC present), unifies the model surface, adds a knowledge-layer gating model, and
wires the full frontend surface via the existing generic ritual infrastructure from the Soul
Tether UI branch.

What was built:

- **Knowledge layer — `AnimaRitualKnowledge` model** (`world/magic/models/anima.py`):
  SharedMemoryModel linking `CharacterSheet` to `AnimaRitual` with a `source` TextChoices
  field (PERSONAL / TAUGHT / STAFF_GRANTED). Gating model — `perform_anima_ritual()` refuses
  to proceed without a `AnimaRitualKnowledge` row for the requesting character. `provision_player_anima_ritual()`
  extended to write the knowledge row at the same time it creates the ritual; all existing
  characters who already have a ritual record get a backfill via data migration.

- **`AnimaRitual` model unification** — prior to this branch, `perform_anima_ritual()` in
  `world/magic/services/anima.py` looked up the ritual via a legacy `CharacterAnimaRitual`
  join model. That model has been removed; the service now queries `AnimaRitual` directly
  via `AnimaRitualKnowledge`. Migration removes the old table.

- **`SceneActionRequest` snapshot fields** — `action_key` and `action_label` snapshot columns
  added to the `SceneActionRequest` model. The resolver registry decodes `action_key` on
  the accepting side without requiring the original action to still be in the scene's
  available-action list.

- **Action-key resolver registry** (`world/magic/resolvers.py`) — `@register_resolver(key)`
  decorator pattern; `resolve_action_request(request)` dispatches to the matching handler.
  Anima ritual is the first registered resolver: `"anima_ritual"` → `resolve_anima_ritual()`.

- **Generic Kudos award** (`world/kudos/services.py` → `award_kudos_for_action_request()`) —
  one Kudos point to the accepting character whenever a `SceneActionRequest` is accepted.
  Scoped to action-request acceptances only; not a general-purpose kudos surface.

- **Anima ritual resolver + service refactor** — `resolve_anima_ritual()` loads both
  characters, validates co-location, calls `perform_anima_ritual()`, awards one Kudos to
  the target, and returns a typed `AnimaRitualResolveResult`. The service function is
  unchanged; the resolver layer handles the social-hook semantics.

- **CG integration + placeholder grants** — `finalize_character()` in
  `world/character_creation/services/finalization.py` now calls
  `provision_player_anima_ritual()` for newly finalized characters (Path → Skill → Ritual
  lookup chain). Beginnings are handled with a manual walk (Option A) rather than a separate
  reconciliation pass. Placeholder grants: `accept_soul_tether` still awards a flat Kudos
  grant (stub) — this is a content/lore decision deferred to staff, not a technical gap.

- **Frontend** (`frontend/src/rituals/AnimaRitualCard.tsx` and scene integration):
  - `AnimaRitualCard` — renders the anima ritual action in the scene's available-actions
    list: ritual name, brief description, anima cost, a target-character picker (scoped
    to scene participants), and a "Perform Ritual" button that calls `usePerformAnimaRitual()`.
    Only visible to the character who owns the ritual (not to other participants).
  - `AnimaRecoveryPanel` — shown to the ritual performer after acceptance: displays
    `RitualOutcome` (Soulfray reduction, anima refilled, roll tier). Slides in via
    `ActionResult` extension on the `SceneDetailPage`.
  - Target character receives a generic `SceneActionRequest` consent prompt via the
    existing `ActionRequestInbox` component. The prompt carries NO anima-specific
    labeling — it appears as a generic social action request.
  - `usePerformAnimaRitual()` / `useAcceptAnimaRitual()` typed React Query mutations
    wired to the backend endpoints.

Interim status notes:
- **`accept_soul_tether` placeholder grants**: the `accept_soul_tether` service currently
  awards a flat stub Kudos grant rather than content-curated ritual grants. This is a
  lore/content call for staff; the grant mechanism is in place.
- **Beginnings in finalize (Option A)**: `finalize_character()` walks Beginnings using a
  manual skill lookup rather than a `reconcile_beginnings()` reconciliation pass.
  Option B (reconciliation) remains a possible follow-up if Beginnings logic grows more
  complex.

**Magic-in-combat API fixes + unified player-action interface (DONE — branch `unified-action-interface`):**

Two long-standing combat-magic integration bugs fixed and the unified action interface delivered.
See `docs/roadmap/combat.md` Phase 7 for the full unified interface spec. Magic-specific items:

- **`offense_check_type` bug fixed** — combat-cast techniques now source `offense_check_type`
  from `technique.action_template` (the authored check type). Previously the serializer fell
  back to `None`, causing declared spells to deal 0 damage through the REST API.
- **`focused_ally_target` declarable** — self-cast and ally-targeting techniques are now
  fully declarable via the `declare_action` endpoint. Previously the API rejected
  `focused_ally_target` with a serializer error.
- **`ActionDispatchError` typed exception** — `_run_actions` raises a typed exception with
  `user_message`; `resolve_round` returns 400 with the message. Closes the raw exception
  propagation path.
- **E2E regression test** — full API cycle (create encounter → declare spell → resolve round →
  assert damage + condition) guards the combat-magic path against future regressions.
- **Unified player-action read/dispatch** — `GET /api/actions/characters/<id>/available/`
  and `POST .../dispatch/` merge challenge + combat backends. The WebSocket `execute_action`
  message now routes through the same `dispatch_player_action` function. ActionPanel and
  ActionAttachment both repointed to the unified endpoint.

**Standalone technique cast — cast→pose→log→outcome (BUILT — branch `feature-772-standalone-technique-cast`, issue #772):**

A PC can cast a standalone technique directly from a scene, outside of an enhanced social action.
`request_technique_cast` in `world/scenes/cast_services.py` routes three ways per the
consent/combat/immediate matrix:

- **Self / no-target / same-persona** → resolves immediately via the full technique pipeline
  (`use_technique` + `start_action_resolution`), persists a RESOLVED `SceneActionRequest`, and
  authors a Narrator OUTCOME `Interaction` (mode=OUTCOME, persona.is_system=True) in the scene.
  The cast-level `PowerLedger` (BASE + ENVIRONMENT stages) is surfaced in the OUTCOME pose
  narration — amplifying resonant environments produce an "— the place's resonance swells the
  working." clause.
- **Benign technique at another PC** → creates a PENDING `SceneActionRequest` for consent.
  `respond_to_action_request` (in `world/scenes/action_services.py`) dispatches to
  `resolve_accepted_cast` on ACCEPT; the full pipeline resolves and a Narrator OUTCOME pose is
  authored. DENY sets status=DENIED with no pose.
- **Hostile (damage) technique at another PC** → calls `seed_or_feed_encounter_from_cast`
  (in `world/combat/cast_seed.py`) to seed or feed a `CombatEncounter` in DECLARING status,
  with the caster as an active participant and the technique as their opening
  `CombatRoundAction.focused_action`. Since #777, a hostile cast that would pull an
  unacknowledged target into a feedable EXTREME/LETHAL encounter instead creates a PENDING
  consent request (risk gate); ACCEPT seeds combat and records an
  `EncounterRiskAcknowledgement`, DENY leaves the target out. Fresh seeds stay MODERATE
  and ungated.

What was built (`src/` paths relative to repo root):
- `world/scenes/cast_services.py` — `request_technique_cast`, `derive_cast_difficulty`,
  `_route_immediate_cast`, `_route_benign_cast`, `_route_hostile_cast`,
  `create_cast_outcome_pose`, `resolve_accepted_cast`.
- `world/combat/cast_seed.py` — `seed_or_feed_encounter_from_cast` (reuses existing combat
  services; no new combat machinery).
- `world/magic/services/hostility.py` — `is_technique_hostile` classifier (damage profile
  presence).
- `world/scenes/types.py` — `CastResult` dataclass.
- `world/magic/narration.py` — `render_cast_outcome_narration` + `power_outcome_clause`
  (shared with future regular-cast paths).
- `world/scenes/action_models.py` — `SceneActionRequest.technique` FK +
  `is_standalone_cast` property; `respond_to_action_request` dispatch extended.
- API: `GET /api/castable-techniques/` (castable-techniques endpoint) +
  `POST /api/action-requests/cast/` (cast dispatch endpoint).
- Frontend: cast flow wired into `ActionPanel` / `ActionAttachment` (branch `feature-772`).
- `world/scenes/tests/test_cast_integration.py` — end-to-end SQLite-tier integration test
  covering all three branches (self-cast RESOLVED + OUTCOME pose; benign ACCEPT/DENY;
  hostile encounter seeded with `CombatRoundAction.focused_action`).

Cross-references:
- **#639 power ledger surfaced** — the `PowerLedger` built by `use_technique`'s ordered
  resolution pipeline is now threaded into scene-cast OUTCOME poses. See "Scope #5.5" and
  "#639" entries above for ledger internals.
- **#766 ledger panel data seam** — the cast-result API payload carries `power_ledger` so
  the full ledger panel has its data source.
- **#859 immediate ledger surface (DONE)** — the cast dialog renders `PowerLedgerPanel`
  straight from the immediate-cast response (`CastResponse.result.power_ledger`), and
  standalone ACTION cards (`PoseUnit` State 3, scene *and* combat) carry a chip-expand
  affordance that lazily fetches the caster-gated `action-outcome-details` for that one
  interaction — no follow-up pose needed. The cast response also exposes
  `action_interaction` (the id whose persisted ledger backs the gated endpoint).

**Key design principles (apply across all scopes):**
- Anima is a safety margin, not a gate. Magic always works. Deficit costs life force.
- Risk is always explicit. Character death warnings use those exact words.
- The technique always works. Mishaps are additional, not replacements.
- Higher intensity is genuinely better. Cost/risk is the trade-off.
- Control is efficiency. High control = cheap/free casting with no side effects.

### Other MVP Needs
- **Post-CG magic progression UI** — level-gated unlocks for resonances, threads, techniques, motifs, gifts
- **Budget-based technique builder** — DONE (#537): unrestricted core (`build_technique`/`create_technique`), `AuthoringPolicy` layer (staff advisory, player enforced), `price_design` + `TechniqueBudgetConfig`/`TechniqueTierBudget` config models, `author`/`price` viewset actions, and `TechniqueBuilderForm` with staff/player modes. GM calibration and multi-alt character picker deferred.
- **Thread system UI — DONE (branch `thread-spending-ui-design`):**

  What was built:
  - Backend: 5 new endpoints (`cross_xp_lock`, `accept teaching offer`, `pull-commit`,
    `hub-summary`, `rooms-by-property`) + `Ritual.client_hosted` flag + cap fields
    on `ThreadSerializer` + alt-guard helper consolidated into `services/auth.py`.
  - Frontend: `/threads` hub with prospect badges, `/threads/:id` detail with
    imbue / XP-lock / pull-preview / rename / retire panels, `/threads/teaching`
    for accepting Weaving teaching offers, multi-step Weave Thread Wizard
    (FACET + COVENANT_ROLE enabled in v1; TRAIT/TECHNIQUE/ROOM/Relationship
    kinds stubbed pending picker hooks).

  What's deferred:
  - TRAIT / TECHNIQUE / ROOM / RELATIONSHIP_TRACK anchor pickers — **SHIPPED (#538):**
    `ThreadHubSummary` now carries `weavable_traits`, `weavable_techniques`,
    `room_property_ids`, and `weavable_relationship_track_ids`; all four pickers are wired
    in `WeaveThreadWizard` (`frontend/src/magic/components/threads/WeaveThreadWizard.tsx`).
  - `ThreadPullDialog` (multi-thread pull) — **SHIPPED (#539):** `ThreadPullDialog`
    (`frontend/src/magic/components/threads/ThreadPullDialog.tsx`) is wired into
    `PullEffectPreview` and mounted in the YourTurn combat panel in
    `frontend/src/combat/components/panels/YourTurn.tsx`.
  - E2E smoke test for `/threads`.
  - Teacher display name in `TeachingOfferCard` (currently shows "Teacher #N").
- Aura farming mechanics — how perception at scenes feeds into resonance strength
- Fashion-to-resonance integration (requires Items & Crafting systems —
  designed in `docs/architecture/items-fashion-mantles.md`,
  implementation phased across 4 PRs)
- **Style / motif / aura magical-significance axis (post-Spec D, dedicated future spec).**
  Resonance + facets cover *what* a character's magic is about; they don't cover
  *vibe* — "seductive," "beguiling," "menacing," "regal," "feral." Existing
  `Motif`/`MotifResonance`/`MotifResonanceAssociation` models in
  `world/magic/models/motifs.py` are scaffolding without a coherent system.
  Spec D's Section 13.3 has the design sub-questions that the future spec needs
  to answer. **Important design intent:** flamboyant fashion (battle lingerie
  on a Sword warrior, paladin getup, evil-sorceress robes) should be a *strong*
  mechanical axis — this is intentional, not flavor garnish.
- Magical discovery through gameplay — unpredictable moments during RP where magic manifests
- Thread strengthening through relationship development
- Tradition gameplay (beyond CG templates — what traditions do during play)
- **Covenants** — magically-empowered adventuring parties. Role mechanics
  + COVENANT_ROLE Thread anchor + gear compatibility shipped (Spec D PR1);
  covenant entity / formation ritual / lifecycle still post-MVP. See
  `docs/roadmap/covenants.md` for the full picture.

## Resonance-Environment Interaction

**Status: SHIPPED (universal path redesign on branch `resonance-environment-universal-path`)**
**Specs:**
- `docs/architecture/resonance-environment-interaction.md` (original slice — primitive, AffinityInteraction, authored injury conditions)
- `docs/architecture/resonance-environment-universal-path.md` (universal-path redesign — supersedes the Magically-Attuned subscriber approach)

### Lore

- **The Abyss corrupts.** Abyssal magic infects and corrupts the worldly — both primal *casters*
  and primal *places*. It is the aggressor toward the Primal.
- **The Celestial is too pure for the world.** It does not corrupt; it is repelled by worldly
  things and only ever gets rejected or pushed out when away from celestial places. Celestial
  places reject all worldly magic.
- **Rock-paper-scissors, not symmetric opposition.** Primal beats Celestial beats Abyssal beats
  Primal. Each interaction is a *directed* relationship — asymmetric per ordered
  (caster-affinity, place-affinity) pair. No off-diagonal NEUTRAL cells: every pairing interacts.

### The 9 directed AffinityInteraction pairs

Stated as "**caster affinity** casting in **place affinity** → outcome." These are authored
`AffinityInteraction` rows (staff-tunable data, not hard-coded logic).

| # | Caster | Place | Valence | Kind | Default aggressor | Severity |
|---|--------|-------|---------|------|-------------------|----------|
| 1 | Celestial | Celestial | ALIGNED | AMPLIFY | environment (boon to caster) | 1.0 |
| 2 | Celestial | Abyssal | OPPOSED | REJECT | environment (harms working) | strong (1.0) |
| 3 | Celestial | Primal | OPPOSED | REPEL | environment (harms working) | mild (0.3) |
| 4 | Abyssal | Celestial | OPPOSED | REJECT | environment (harms working) — *Hallowed Rejection* | strong (1.0) |
| 5 | Abyssal | Abyssal | ALIGNED | AMPLIFY | environment (boon to caster) | 1.0 |
| 6 | Abyssal | Primal | OPPOSED | CORRUPT | **caster** (caster defiles the place) | strong (1.0) |
| 7 | Primal | Celestial | OPPOSED | REJECT | environment (harms working) | strong (1.0) |
| 8 | Primal | Abyssal | OPPOSED | CORRUPT | environment (place corrupts the caster) | strong (1.0) |
| 9 | Primal | Primal | ALIGNED | AMPLIFY | environment (boon to caster) | 1.0 |

Asymmetries: Abyssal corrupts Primal in both arrangements (#6 defiles a primal place; #8 a
primal caster is corrupted by an abyssal place). Celestial only ever gets rejected or repelled
away from non-celestial places and never corrupts. Celestial places reject all worldly magic.

### Three-layer architecture

| Layer | What | Form |
|---|---|---|
| **Mechanism** | `evaluate_resonance_environment()` primitive + two core services | `world/magic/services/resonance_environment.py` — peers of `accrue_corruption_for_cast` |
| **Tuning** | 9 `AffinityInteraction` rows + scalar coefficients + authored pools/tiers | `AffinityInteraction` model + `ResonanceEnvironmentConfig` singleton + `AffinityInteraction.consequence_pool` FK + `ResonanceAlignmentBoonTier` rows |
| **Content** | authored injury conditions (OPPOSED) + named buff conditions (ALIGNED) | existing Tempered/Singed/Burning/Hallowed Burn/Cast Disrupted templates selected by consequence pool; new named boon `ConditionTemplate`s per affinity/magnitude band |

The primitive is a core magic-physics mechanism. Universal magic-physics is a core service,
not a flow or trigger. Authored content (consequence pools, boon tiers) is data — staff-tunable
rows on the existing `AffinityInteraction` table, not code changes.

### What shipped

**The anti-pattern removed:** the 2026-05-15 slice used a "Magically Attuned" baseline
`ConditionTemplate` on every magic-capable PC to subscribe them to a `TriggerDefinition`/
`FlowDefinition` pair. This is wrong by construction — a `ConditionInstance` row on every PC
encodes a universal fact (this character is magical) that is already derivable from whether
a `CharacterAura` exists. A flow/trigger is for authored, sequenced content and genuine
per-entity exceptions; it must not model a baseline process that applies to all casters.
The 2026-05-16 redesign removes the marker condition, trigger, flow, and the seeding of all
three. The pipeline test no longer applies any condition in `setUp` — it exercises the
production path directly.

**What replaced it:**

- **`magical_profile(character_sheet) -> CharacterAura | None`** — derived predicate in
  `world/magic/services/resonance_environment.py`. Returns the character's `CharacterAura`
  or `None` (Quiescent). Magic-capability is derived from the aura's existence, never
  asserted or stored. No grant mechanism, no backfill, no idempotency guard needed.
- **`ResonanceEnvironmentEffect` result shape** — extended with two fields:
  `interaction: AffinityInteraction | None` (the resolved row, carried out of the primitive
  so no service re-queries it) and `backfire_difficulty: int` (relocated from the deleted
  flow adapter into the primitive).
- **`resonance_environment_for_cast(*, caster_sheet, room_profile, technique)`** — OPPOSED
  backfire service. Called from the technique-use orchestrator
  (`world/magic/services/techniques.py`, "Step 10") immediately after
  `accrue_corruption_for_cast`. Gated by `magical_profile`. Resolves the OPPOSED consequence
  via `select_consequence_from_result` over `AffinityInteraction.consequence_pool` (a new
  nullable FK, migration `magic/0064`) at config-derived `backfire_difficulty`. Emits no
  event, runs no flow.
- **`refresh_resonance_alignment(*, character_sheet) -> None`** — ALIGNED presence-buff
  service. Called from `Character.at_post_move` on arrival. Idempotently clears any prior
  alignment buff (using `ResonanceAlignmentBoonTier.objects.boon_condition_templates()` cached
  set), evaluates `evaluate_resonance_environment(technique=None)`, and applies the named buff
  `ConditionTemplate` for the highest matching `ResonanceAlignmentBoonTier` band via Python
  `max()` over `interaction.cached_alignment_boon_tiers`. Also called from
  `Character.at_pre_move(destination=None)` and `Character.at_post_unpuppet` for clean
  teardown.
- **`clear_resonance_alignment(*, character_sheet) -> None`** — explicit-clear variant
  (step-1 logic extracted); called on departure and logout.
- **`ResonanceAlignmentBoonTier`** — new authored model (migration `magic/0064`). FK to
  `AffinityInteraction` (must be ALIGNED diagonal row) + `min_magnitude` + FK to
  `ConditionTemplate`. `UniqueConstraint` on `(affinity_interaction, min_magnitude)`.
  `clean()` validates the interaction is ALIGNED. No `Meta.ordering` — selection is Python
  `max()` over a cached list.
- **`obj.conditions` cached handler** (`ConditionHandler` / `CharacterConditionHandler` in
  `world/conditions/handlers.py`, installed as `@cached_property` on `ObjectParent`).
  `CharacterConditionHandler.active` mirrors `get_active_conditions`. `.invalidate()` wired
  into all `world/conditions/services.py` mutation sites. The movement service's clear step
  intersects the character's already-cached condition instances against the cached boon
  template set — no per-move query.
- **Seed rework** — `integration_tests/game_content/magic.py` drops the Magically-Attuned
  condition, universal trigger, and universal flow seeding; seeds OPPOSED `ConsequencePool` +
  `Consequence` + `ConsequenceEffect` rows for the celestial-place pairs (#4/#7) and ALIGNED
  `ResonanceAlignmentBoonTier` rows with named buff `ConditionTemplate`s for the abyssal/
  abyssal pair (#5).
- **Pipeline test rework** — `setUp` applies no condition. The test exercises the real
  production path: OPPOSED subtests cast in the celestial cascade room and assert the correct
  injury `ConditionInstance` per `CheckOutcome` tier; ALIGNED subtests move the caster into
  the abyssal-aligned room and assert the named buff is applied, cleared on departure, and
  swapped on affinity-change.

**Retained unchanged:** the `evaluate_resonance_environment` primitive logic, the 9
`AffinityInteraction` rows, `ResonanceEnvironmentConfig`, the `endure_hallowed_ground`
`CheckType`/`ResultChart`, and the Tempered Against Light / Singed / Burning / Hallowed Burn /
Cast Disrupted `ConditionTemplate`s.

### What's deferred (primitive already supports it — additive, not re-architecture)

1. **~~"Magically Attuned" production grant~~** — **SUPERSEDED/REMOVED.** This deferred item
   from the 2026-05-15 spec is not implemented as a grant; the entire marker-condition
   approach was replaced by the derived `magical_profile` predicate (see
   `docs/architecture/resonance-environment-universal-path.md`). No
   grant is needed: magic-capability is derived from `CharacterAura` presence, which is
   created unconditionally at CG finalization by `finalize_magic_data()`.
2. ~~**Presence-escalation for scarred characters**~~ — **DONE (#526).** `EventName.MOVED`
   emitted from `at_post_move`; `Room.dominant_affinity` property; `apply_condition_by_name`
   flow-step helper; filter-propagation fix in `_install_reactive_side_effects`. Reference
   pipeline: `wire_scar_escalation_trigger()` in `world/magic/factories.py`. No scar-specific
   Python — escalation is pure authored data via `ConditionTemplate.reactive_triggers` M2M.
3. ~~**Defilement (CASTER_DOMINANT)**~~ — **DONE (#525).** A strong Abyssal caster who
   overpowers an opposed place (Primal #6 or Celestial #4) DEFILES it: degrades the place's
   dominant opposed cascade resonance (floored at effective 0), spreads the casting
   technique's Abyssal resonance(s) onto the room (repeated defilement flips the room to
   Abyssal "corrupted ground"), and accrues extra caster→world corruption via the existing
   interceptable `CORRUPTION_ACCRUING` event (a Sinner's Hollow absorbs it with zero new
   wiring). Gated by a data flag `AffinityInteraction.caster_dominance_defiles` (authored
   True only on #4/#6) so non-Abyssal casters never defile; `_compute_direction` runs the
   strength split for `flag OR CORRUPT`; the reject/repel backfire is suppressed when
   defilement fires (a strong Abyssal caster defiles a Celestial place instead of taking
   Hallowed Burn — a weak caster still burns). Row mutation goes through a shared
   `upsert_room_resonance_modifier` (Sanctum refactored onto it). Service:
   `world/magic/services/defilement.py`, fired at `use_technique` Step 10. The same
   machinery would support a future Celestial→Abyssal "purification" interaction (spreads
   Celestial, accrues 0 corruption — Celestial's coefficient is already 0).
4. **Brother's richer formula** — steps 5–7 of the v1 formula are deliberately simple. His
   follow-up enriches the primitive body (technique-resonance opposition weighting,
   multi-resonance place weighting). Call sites, `AffinityInteraction` data,
   `ResonanceEnvironmentConfig`, the consequence pools, and the boon-tier rows do not change.
5. **`TECHNIQUE_PRE_CAST` block/modify variant** *(fundamental — core reactive capability)*
   — a true pre-cast intercept that can block or modify the cast before it resolves; needs
   cancel/modify-payload semantics in the reactive layer. v1's post-resolve backfire is a
   deliberate scoping simplification (environment reacts *after* the working fires), **not**
   a substitute for the environment being able to stop/alter a cast. This is foundational
   capability work, not an indefinite deferral.

### Recommended next steps (priority order)

The deferred items above, ordered by recommended sequence with rationale and ownership:

1. ~~**Presence-escalation for scarred characters**~~ — **DONE (#526).** General primitives
   added: `EventName.MOVED` emitted from `at_post_move`; `Room.dominant_affinity` property;
   `apply_condition_by_name` flow-step helper; filter-propagation fix in
   `_install_reactive_side_effects`. Reference pipeline: `wire_scar_escalation_trigger()` in
   `world/magic/factories.py`. No scar-specific Python — escalation is pure authored data via
   `ConditionTemplate.reactive_triggers` M2M.
2. **`TECHNIQUE_PRE_CAST` block/modify variant** *(Tehom/core; fundamental)* — a true
   pre-cast intercept that can **block or modify** a working *before* it resolves. This
   is a foundational reactive-layer capability, **not** a nice-to-have: v1's post-resolve
   backfire (the environment reacts *after* the working fires) was a deliberate scoping
   simplification, never a substitute for the environment being able to stop or alter a
   cast. Needs cancel / modify-payload semantics in the reactive layer. Sequence as core
   capability work, not "defer until a concrete need."
3. ~~**Defilement (CASTER_DOMINANT)**~~ — **DONE (#525).** A strong Abyssal caster overpowering
   an opposed place (Primal #6 or Celestial #4) degrades its cascade, spreads Abyssal taint
   (flipping the room to corrupted ground over repeated casts), and routes extra caster→world
   corruption through `CORRUPTION_ACCRUING` so a Sinner's Hollow absorbs it (the
   social-responsibility layer). Data-gated by `caster_dominance_defiles`; defile replaces the
   reject backfire for a dominant caster. See deferred-item #3 above for the full surface.
4. **Brother's richer formula** *(brother; no urgency)* — enriches the primitive body
   (technique-resonance opposition weighting, multi-resonance places). v1 is functional;
   do when brother prioritizes. Zero change to call sites / data / authored content. (This
   one *is* genuinely brother's — the per-resonance weighting is his deferred follow-up.)

### Cross-reference: combat clash-of-wills

The combat **Clash** mechanic (see `docs/roadmap/combat.md` → "Clash of Wills") is now
**SHIPPED** on branch `clash-design`. As designed, it reuses the same `AffinityInteraction`
rows and `ResonanceEnvironmentConfig` tuning from this section — `affinity_tilt` in
`src/world/combat/clash.py` applies the directed RPS matrix to each round's PC progress
delta without authoring any parallel opposition table.

### Strain mechanism (breadcrumb — Clash is the v1 consumer)

The **Strain mechanism** — anima committed *beyond* a technique's base cost to escalate
clash contributions — is built general in `src/world/combat/clash.py` and threaded into
`use_technique` via an additive `strain_commitment: int = 0` kwarg and a corresponding
extension to `calculate_effective_anima_cost`. The diminishing-returns conversion curve
(anima → progress delta) is tuned via the `StrainConfig` singleton in
`world/combat/models.py`.

The sole v1 consumer is Clash: `commit_to_clash` passes the PC's declared anima
commitment as the strain amount when it calls `use_technique` in clash-commit mode.

**Regular-cast Strain is SHIPPED** (#776 closed 2026-06-09 after a verify-against-code
audit; this paragraph previously claimed it "remains a deferred follow-up" — stale).
The standalone-technique-cast UI landed in #772 (`request_technique_cast`,
`POST /api/action-requests/cast/`, `ActionPanel` cast flow); the per-cast strain
slider with anima-capped validation lives in `ActionPanel.tsx`; non-clash strain
accrues via `Interaction.strain_committed` with soulfray accrual (tested in
`magic/tests/test_non_clash_strain.py`, PR #574); and `StrainConfig` is read in the
non-clash fatigue path (`fatigue/services.py`). Whether clash-tuned `StrainConfig`
*values* suit regular casts is an open tuning judgment, not missing code.

---

## Notes

### Cross-reference: Aspect Focus & Path Evolution
See `character-progression.md` → "Aspect Focus as Path Evolution Guide" for a future design idea where players choose an aspect to lean into, guiding both check bonuses and path evolution. This touches magic because aspect weights feed into the check resolution pipeline alongside affinity/resonance mechanics.

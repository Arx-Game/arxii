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

### Affinity Bonuses (via Resonance)
Resonance points feed into technique stats through affinity alignment:
- **Celestial:** every 10 resonance → +2 control (precise magic)
- **Primal:** every 10 resonance → +1 intensity, +1 control (balanced magic)
- **Abyssal:** every 10 resonance → +2 intensity (powerful magic)
- Rounded up

### Combat Escalation
In serious boss fights, intensity auto-escalates each round. Characters make control checks to keep control in pace. Relationship events (true love threatened, ally falls) can spike intensity dramatically. Emotional state (anger, desperation) also feeds intensity. This mirrors superhero/fantasy boss fight pacing — things only escalate, never reset.

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
  CharacterAnima, CharacterAnimaRitual, AnimaRitualPerformance, Motif,
  MotifResonance, MotifResonanceAssociation, Facet, CharacterFacet,
  **Thread** (new discriminator + typed-FK design, Spec A §2.1),
  **ThreadPullCost**, **ThreadXPLockedLevel**, **ThreadLevelUnlock**,
  **ThreadPullEffect**, **ThreadWeavingUnlock**, **CharacterThreadWeavingUnlock**,
  **ThreadWeavingTeachingOffer**, **Ritual**, **RitualComponentRequirement**,
  **ImbuingProseTemplate**, Tradition, CharacterTradition,
  CharacterAffinityTotal, Reincarnation, Cantrip, **TechniqueCapabilityGrant**.
  CombatPull / CombatPullResolvedEffect live in `world/combat` but are
  part of the Spec A surface.
- **Capability integration:** TechniqueCapabilityGrant links Techniques to CapabilityTypes (from conditions app) with `base_value + (intensity_multiplier * intensity)` formula. This feeds into the mechanics app's action generation pipeline — when a character has a Technique that grants a Capability, the system can match it against Properties on Challenges to surface available approaches
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
**Spec:** `docs/superpowers/specs/2026-03-29-technique-use-flow-design.md`

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
**Spec:** `docs/superpowers/specs/2026-03-30-scope2-runtime-modifiers-audere-design.md`

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
**Spec:** `docs/superpowers/specs/2026-03-31-scope3-warp-progression-design.md`

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
- **Layered result display** — ActionResult shows both social outcome and technique effects as distinct results, making the layered action pipeline transparent to players
- **Integration tests** — Comprehensive tests covering mundane consequences, enhanced pipeline, validation, and available-actions filtering

**Scope #5 — Magical Alteration Resolution (DONE):**

What was built:
- **Three new models** — `MagicalAlterationTemplate` (OneToOne on `ConditionTemplate`,
  carries magic-specific metadata: tier, origin affinity/resonance, library flag,
  visibility), `PendingAlteration` (queued unresolved scars with status lifecycle
  OPEN → RESOLVED / STAFF_CLEARED, scene + triggering-state snapshot), and
  `MagicalAlterationEvent` (immutable provenance audit log). Single migration covers
  all three. Plan/spec at `docs/superpowers/plans/2026-04-12-scope5-magical-alteration-resolution.md`.
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

**Spec:** `docs/superpowers/specs/2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md`
**Plan:** `docs/superpowers/plans/2026-04-19-resonance-pivot-spec-a-threads-and-currency.md`

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

**Spec:** `docs/superpowers/specs/2026-04-23-resonance-pivot-spec-c-gain-surfaces-design.md`
**Plan:** `docs/superpowers/plans/2026-04-23-resonance-pivot-spec-c-gain-surfaces.md`

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
  discriminator pattern ensures atomic grant journaling), `RoomAuraProfile` (FK to RoomProfile;
  one-to-one), `RoomResonance` (through-M2M from `RoomAuraProfile` to `ResidualResonance`).
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
  `RoomAuraProfile` with inline `RoomResonance`; read-only ledger admin for `ResonanceGrant`;
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
Spec: `docs/superpowers/specs/2026-04-16-reactive-layer-design.md`.
Key new modules: `flows/trigger_handler.py`, `flows/emit.py`,
`flows/events/`, `flows/filters/`, `flows/execution/prompts.py`,
`world/combat/damage_source.py`. 29 integration tests cover damage-source
discrimination, cross-character filters, AE topology, stage cascades,
cancellation tiers, and async prompt resolution; 10 are authored-but-skipped
pending follow-up infrastructure (covenant relationships, Property M2M on
Technique, trigger usage-cap fields, mutable `ExaminedPayload`).

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
**Spec:** `docs/superpowers/specs/2026-04-21-magic-scope-6-soulfray-recovery-design.md`

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
**Spec:** `docs/superpowers/specs/2026-04-25-magic-scope-7-corruption-design.md`

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
- **Integration test suite** — 13 scenarios in
  `src/world/magic/tests/integration/test_corruption_flow.py`: lazy
  condition creation, lifetime monotonicity across accrue+reduce, no-
  template no-op, lock entry/exit, Atonement happy paths + refusal
  paths, decay sync, risk-transparency event emission. Per-cast accrual
  scenarios are excluded pending the deferred per-cast hook (see below).
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

Deferred (gated on a follow-up that extends `TechniqueUseResult`):
- **Per-cast accrual hook into `use_technique`** — `accrue_corruption_for_cast`
  per-cast orchestrator and the wiring into the technique pipeline. Spec
  §10.1 flagged the risk: `TechniqueUseResult` does not expose
  per-resonance involvement (stat_bonus contribution + thread-pull
  resonance spent). Implementing the orchestrator requires extending
  `TechniqueUseResult` (and `use_technique` itself) to surface that
  breakdown. The per-resonance formula is fully specified in §3.1 and
  the service shape is sketched in the plan; just unblocks once the
  technique pipeline exposes the inputs. No architectural changes
  needed in the corruption foundation — just the missing input.
- **Soul Tether (Spec B)** — the redirect mechanic, Sineater asymmetry,
  rescue rituals.
- **Cast-pipeline integration tests** — wait on the per-cast hook above.

Not in this scope (deferred): non-Corruption stage 3+ recovery rituals
(Spec B authors via the same `reduce_corruption` primitive), public
corruption leaderboards (`corruption_lifetime` enables this surface but
no API ships now), Mission-driven cleansing quests, and other
autonomy-loss systems (berserker, possession, mind-control) which
share the protagonism-lock aggregator but design independently.

**Key design principles (apply across all scopes):**
- Anima is a safety margin, not a gate. Magic always works. Deficit costs life force.
- Risk is always explicit. Character death warnings use those exact words.
- The technique always works. Mishaps are additional, not replacements.
- Higher intensity is genuinely better. Cost/risk is the trade-off.
- Control is efficiency. High control = cheap/free casting with no side effects.

### Other MVP Needs
- **Post-CG magic progression UI** — level-gated unlocks for resonances, threads, techniques, motifs, gifts
- **Budget-based technique builder** — replaces restriction-based power for post-CG technique creation
- Thread system UI integration (models exist, needs frontend)
- Aura farming mechanics — how perception at scenes feeds into resonance strength
- Fashion-to-resonance integration (requires Items & Crafting systems)
- Magical discovery through gameplay — unpredictable moments during RP where magic manifests
- Thread strengthening through relationship development
- Tradition gameplay (beyond CG templates — what traditions do during play)
- **Covenants** — magically-empowered adventuring parties (see below)

## Covenants (Post-MVP)

Covenants are magically-empowered oaths — blood rituals that enshrine each participant's role and bind them to a shared goal. Every covenant has a sworn objective that all members commit to achieving together. The magic is real: the oath grants power, and the roles shape how that power manifests.

**Covenant types — not one-size-fits-all:**
- **Covenant of the Durance** — The foundational type. An adventuring party swears to support each other as they pursue the Durance (their overarching story of magical discovery). Long-lived, deeply personal, built around relationship bonds
- **Covenant of Battle** — Formed for a specific war or battle scene. Assigns war roles that empower participants for large-scale conflict. Shorter-lived, can stack with a character's existing Durance covenant. Dissolved when the battle ends or objective is achieved
- **Other types TBD** — The covenant framework should support different oath types with different durations, goals, and role sets. A covenant of investigation, a covenant of vengeance, a trade pact — anywhere a sworn magical oath with defined roles makes narrative sense

**Three foundational archetypes (for Durance covenants):** Sword (offense) / Shield (defense) / Crown (support). At early levels, players pick from these three basic roles. As the covenant or members level up, specialized sub-roles unlock within each archetype. Battle covenants and other types may have their own role sets. Specific role names TBD.

**Key constraints:**
- Roles are unique within a covenant — no two members hold the same role
- Covenant bonds function like enhanced Threads with shared resonance
- Covenant role influences which techniques are empowered during group content
- Covenant-level progression unlocks group abilities
- Battle covenants stack with Durance covenants — a character can be in both simultaneously

**Dependencies:** Thread system UI, group content (missions/combat), post-CG technique system, role definitions.

## Notes

### Cross-reference: Aspect Focus & Path Evolution
See `character-progression.md` → "Aspect Focus as Path Evolution Guide" for a future design idea where players choose an aspect to lean into, guiding both check bonuses and path evolution. This touches magic because aspect weights feed into the check resolution pipeline alongside affinity/resonance mechanics.

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
- **Models:** CharacterAura, CharacterResonance, Gift, CharacterGift, Technique, CharacterTechnique, TechniqueStyle, EffectType, Restriction, IntensityTier, CharacterAnima, CharacterAnimaRitual, AnimaRitualPerformance, Motif, MotifResonance, MotifResonanceAssociation, Facet, CharacterFacet, Thread, ThreadType, ThreadJournal, ThreadResonance, Tradition, CharacterTradition, CharacterAffinityTotal, CharacterResonanceTotal, Reincarnation, Cantrip, **TechniqueCapabilityGrant**
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

**Scope #6 — Soulfray Recovery & Decay (TODO):**

Soulfray severity currently only accumulates — there is no mechanism for it to go down.
This scope adds the recovery side: time-based decay, ritual-driven recovery, and the
"anima fade out of combat" behavior the world-clock roadmap has been waiting on.

What to build:
- **`decay_soulfray_severity(character)`** service — decrements severity by a configured
  amount per tick, retreating through stages when severity drops below the current
  stage's threshold. Inverse of `advance_condition_severity()` from Scope 3.
- **`SoulfrayConfig.decay_rate`** — authored field for base decay per unit time.
  Consider separate rates for in-scene vs out-of-scene vs post-ritual.
- **Weekly / periodic hook** — wire decay into the `weekly_rollover` orchestrator
  (or a faster tick) via the world-clock scheduler. Task registry pattern, idempotent,
  matches AP regen shape.
- **Ritual-driven recovery** — `AnimaRitualPerformance.apply_recovery()` (or similar)
  consumes the existing CharacterAnimaRitual + AnimaRitualPerformance records and
  decrements Soulfray severity as one of the outcomes. Scene-linked, so ritual
  performance in RP has a concrete mechanical effect.
- **`CharacterAnima` anima recovery too** — while we're here, make the existing
  `last_recovery` field actually drive anima pool recovery on the same scheduler tick.
  This is the "anima fade out of combat" item from the world-clock deferred list.
- **Engagement-aware recovery** — Soulfray should NOT decay while a character has an
  active high-stakes CharacterEngagement (combat, mission). Recovery is a between-scenes
  phenomenon, not a mid-fight one.
- **Integration test** in `src/integration_tests/pipeline/` exercising: character
  overburns into Soulfray stage 2, performs a ritual (factory-built), severity drops,
  stage retreats to 1. A second test covers time-based decay via the scheduler tick.
  A third covers engagement blocking decay.

Key design questions to resolve during brainstorm:
- Does decay ever fully clear Soulfray, or does it asymptote toward stage 1 so some
  lingering magical fatigue remains until a proper ritual?
- Does ritual recovery require the character to be OUT of engagement, or can it happen
  mid-arc as a dramatic pause?
- Should decay rate scale with resonance/affinity (some characters recover faster)?
- Does the scheduler hook run weekly (GameWeek-aligned) or daily (AP-regen-aligned)?
  This affects how "spiky" recovery feels.
- Do we need a "soulfray history" audit trail, or is live severity enough?

Dependencies:
- World-clock scheduler (live — `GameWeek`, `weekly_rollover`, task registry exist)
- CharacterAnimaRitual / AnimaRitualPerformance (live)
- Soulfray stage progression from Scope 3 (live — reuse `ConditionStage.severity_threshold`)

Decoupling: Standalone. Does NOT depend on Scope 5 (alteration resolution). A separate PR.

Deferred to later scopes:
- Abyssal corruption as long-term consequence of abyssal magic overuse
- Character loss deferral during Audere (needs combat/mission lifecycle)

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

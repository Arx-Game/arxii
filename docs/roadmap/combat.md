# Combat

**Status:** in-progress
**Depends on:** Traits, Skills, Magic, Conditions, Mechanics, Relationships (for combo attacks)

## Reserved terminology: "clash"

**"Clash" is a reserved term for a specific planned combat feature and MUST NOT be
used to name any other concept anywhere in the codebase** (function names, variables,
model names, design docs, comments). The reserved meaning: an opposed/contested
combat mechanic where two combatants pour magical energy into overpowering each
other (the "beam struggle" trope) — each side escalates effort to make their side
win and strike the opponent (a clash of wills).

For unrelated opposing-resonance / environmental-rejection concepts (e.g. casting an
opposing-affinity technique in a hostile-aura room) use **"backfire"** (the term used
in `docs/plans/2026-05-14-room-cascade-resonance-unification.md` for the deferred
"technique pre-cast backfire trigger"), or "rejection" / "dissonance" / "backlash".
Never "clash". When naming a new mechanic, ask: does this involve two sides
contesting magical energy to overpower each other in combat? If not, it is not a
"clash".

**When the clash-of-wills feature IS built, reuse the resonance-environment work — do
not reinvent it.** `docs/architecture/resonance-environment-interaction.md`
already models directed, asymmetric affinity opposition as authored `AffinityInteraction`
rows (the RPS cycle: Primal > Celestial > Abyssal > Primal, with per-pair `valence` /
`kind` / `severity_multiplier`). A combat clash between opposed-affinity casters
(Abyssal vs Celestial, Primal vs Abyssal, etc.) is the *caster-vs-caster* analogue of
the *caster-vs-place* interaction: it should consume the same `AffinityInteraction`
matrix and the same valence/severity concepts (and likely the `ResonanceEnvironmentConfig`
tuning surface) rather than authoring a parallel opposition table. The clash feature adds
the contested-escalation mechanic on top; the affinity-opposition substrate is shared.

## Overview
Combat is always Players vs. the Bad Guys — no PVP killing. Three distinct combat modes serve different scales and narrative purposes, all designed to create heroic moments and reward teamwork over solo power.

## Key Design Points

### Asymmetrical by Design
Party Combat is NOT symmetrical like tabletop RPGs. PCs do not fight mirrored opponents.
The opposition does not have character sheets with capabilities. Instead:
- **Offensive round:** PCs pick actions and resolve attacks against the opposition
- **Defensive round:** The opposition acts via threat patterns; PCs make defensive checks
- NPCs have behaviors, threat patterns, and soak values — not mirrored PC sheets
- The only symmetrical PC-vs-NPC combat is a special Duel variant (high-drama 1v1 to the death)

### Three Combat Modes (each with variations)
- **Party Combat:** The main form. Asymmetrical — PCs vs opposition (boss, minions, swarm).
  Intentionally impossible to solo; combos and covenant roles (party roles) are fundamental.
  Designed for heroic team-up arcs: characters get battered, pushed to the edge, and break
  through with Audere Majora. Variations range from "victory lap against fodder" to
  "unwinnable last stand where a PC sacrifices to save the party."
- **Battle Scenes:** Large-scale abstracted conflicts with variations: army vs army (PCs on
  one side), all PCs vs kaiju-scale opponent. Fixed rounds, victory points, mass participants.
  Similar feel (mass combat) but stylistic differences within.
- **Duels:** Normally non-lethal PC vs PC sparring, slow-paced with pose integration. But also
  supports high-drama lethal 1v1 (PC vs significant NPC) — the only symmetrical combat mode.

### Risks and Stakes
Every encounter defines Risks (personal to character) and Stakes (world-level):
- **Risks:** Character death, harm to loved ones, identity-threatening losses, minor injury
- **Stakes:** Organization reputation (low), regional consequences (mid), fate of the world (high)
- Encounter design ranges from "easy victory lap" to "the fight you can't win but must fight"

### Round Structure
One unified round — no artificial offensive/defensive split.

1. **Declaration** — All PCs declare their focused action + passives simultaneously. NPC
   actions are determined automatically. PCs may or may not see NPC intentions (who they
   target, what they're doing) based on IC mechanical abilities (spells, techniques, etc.).
2. **Resolution** — Actions resolve in covenant rank order:
   - Ranks 1-2: Fastest covenant roles (e.g., scout/striker archetypes)
   - Ranks 3-12: Other covenant roles in speed order
   - ~Rank 15: NPCs (safely after most PCs)
   - ~Rank 20: No covenant role (unbuffed normal humans)
   - Slow debuffs/effects add ranks (e.g., +10) to resolution order
   - Fast PCs can kill minions before they act, or buff allies before the boss resolves

### Three-Category Actions
Each round, a PC has three action categories: **Physical, Social, Mental**.
- PC picks ONE **focused action** in one category (their main action for the round)
- The other two categories get **passive defaults** — small buffs/support chosen per round
- Example: "Massive Shadow Sword" (physical focus) + "Tactical Orders" (social passive, group
  combat buff) + "Keep It Together" (mental passive, defensive buff vs mental attacks)
- Focused actions cost fatigue in their category + anima for magical techniques
- Passives let characters express personality in combat (what they say/think while fighting)

### Covenant Roles
Combat archetypes assigned when a covenant (adventuring party) is formed via IC ritual.
- Static for the duration of combat — not altered on the fly
- Can be changed between combats via a new ritual
- Each role has a fixed speed rank determining resolution order
- Roles also determine combo eligibility and party synergy mechanics
- Specific roles and speed rankings are future content — enum stubs for now

### NPC Tiers
Five distinct NPC types with different mechanical treatment:
- **Swarm** — mass of fodder, swarm-count based (no individual HP), no soak. PCs mow through
  them. Danger is attritional volume. Simple stat block.
- **Mook** — individual minions with modest stats. Between swarms and elites. Individually
  manageable but can overwhelm in numbers.
- **Elite** — individual HP, some soak, may require one combo to take down. Roughly paired
  1:1 against PCs as independent challenges. Extraordinary attacks or abilities.
- **Boss** — massive HP, high soak, probing/combo/phase system. The centerpiece encounter.
  Essentially immune until probed enough for combos to land. Multiple phases.
- **Hero Killer** — staff-only tier. Kaiju, gods, endgame threats that PCs cannot defeat.
  Triggers narrative "you must run" state rather than combat engagement. Uses specific
  narrative rules, not just massive stats. Not available to normal GMs.

### Boss Soak and Combo Mechanics
Bosses (and to a lesser degree Elites) use the soak/probing/combo system:
- Soak threshold ignores attacks below a damage floor
- Every attack that hits (even soaked) builds a **probing defenses** counter
- When probing reaches a threshold, combo attacks that bypass soak become available
- Combos require multiple PCs coordinating — valueless for solo players
- Landing a combo can advance the boss to the next **phase** (different stage of the fight)
- This creates the escalating tension loop: probe → combo → phase shift → harder patterns

### Encounter Scaling (backend engine + tuning SHIPPED — #566)
Difficulty is hybrid: base from story context, adjusted by party composition. GMs mostly
pick a tier (Swarm/Mook/Elite/Boss), name it, describe it, and the system fills in
appropriate defaults based on party strength and story risk level. GMs have limited control
over exact difficulty — the system handles most of it to ensure consistency across GMs.
C-style consequence pools are better suited for abstract mission challenges (e.g., assassinate
an NPC at a bar) where concrete NPC objects aren't needed.

**SHIPPED (#566) — scaling engine + GM tuning surface (React builder deferred):**
- **Authored config tables** (`world/combat/models.py`, all mirroring `FleeTierModifier`/
  `FleeConfig`): `OpponentTierTemplate` (per `OpponentTier`: base health/soak/probing,
  swarm defaults, barrier, boss phase count — **closes the Mook/Elite stat-default
  differentiation deferred from #875**); `RiskScalingModifier` (per `RiskLevel` multiplier);
  `StakesLevelRequirement` (per `StakesLevel` gate); `EncounterScalingConfig` (pk=1 singleton:
  party-scaling coefficients). All staff-tunable in Django admin; defaults supplied by
  `seed_scaling_defaults()` in factories (double as test setup + seed data, applied by the
  planned startup-page mechanism).
- **Scaling formula** (`world/combat/scaling.py`): `compute_opponent_stat_block(tier, encounter)`
  returns a frozen `OpponentStatBlock` (+ generated boss `PhaseSpec`s). `max_health` scales by
  `risk_mult × party_mult`, soak by risk, swarm count by party; HERO_KILLER returns its
  template base **unscaled** (unbeatable sentinel). **Difficulty keys off party size + average
  primary character level ONLY** — never threads/relationships/covenants/facets/fashion, so
  thread-rich parties are simply stronger, not matched by tougher enemies (invariant test).
- **Stakes is a gate, not a stat multiplier:** `validate_stakes_requirement(encounter, gm)`
  enforces a per-stakes minimum party average level + minimum GM trust, **reusing the existing
  `stories` trust system** (`PlayerTrust.gm_trust_level`, `TrustLevel`) — no new GM-auth concept.
- **Wiring + API:** `add_opponent` auto-fills omitted stats (and boss phases) from the formula
  when `max_health` is omitted (explicit values always win); read-only
  `GET /api/combat/{id}/opponent-defaults/?tier=…` previews the computed block + a non-blocking
  stakes verdict; `AddOpponentSerializer` enforces the stakes gate on create.
- **DONE (#1165) — outlier-aware scaling + Mentor's Vow:**
  `compute_party_profile` now calls `effective_combat_level(sheet)` per ACTIVE
  participant. `effective_combat_level` (in `world/covenants/mentorship.py`) returns
  the raw primary level normally, but when the sheet is party to an active, non-graduated
  **Mentor's Vow bond** (`MentorBond`), it returns a bond-adjusted level: a low-level
  sidekick is pulled up to just below their mentor's level; a high-level mentor is
  pulled down to just above their sidekick's level — both clamped to the covenant
  band `[covenant.level ± band_width]`. The party average and scaling formula are
  computed on the adjusted values, so a mentor/sidekick pair no longer distorts the
  encounter budget. The bond is created via a consensual BILATERAL_SERVICE ritual
  (`MentorsVowRitualFactory`). Graduation (adjusted party's real level re-enters the
  band) dissolves the bond at `begin_declaration_phase`. The #566 invariant —
  difficulty keys off level and party size only, never threads/relationships/covenants/
  facets/fashion — is preserved and test-covered. In-combat role bonuses also read the
  bond-adjusted level (`level_override` via `bond_adjusted_level`) so a suppressed
  mentor's bonus shrinks and an elevated sidekick's grows.
- **Deferred (follow-ups):** React GM encounter-builder page; stakes→reward-severity
  routing; rich per-phase boss authoring beyond auto-generated default phases.

### Health Pool and Damage
Health is separate from fatigue — fatigue degrades effectiveness, health degrades survival.

**Health pool sources (SHIPPED — #1256):** `max_health = base_max_health + thread_addend`.
The thread addend is the sum of active VITAL_BONUS tier-0 ThreadPullEffect contributions
(`recompute_max_health_with_threads`). `base_max_health` on `CharacterVitals` is NULLABLE:
`None` → derived on read via `derive_base_max_health`; a set value → authored fixed-base
override that **bypasses derivation entirely** (class/stamina/covenant terms do NOT apply
when an override is set).

**`derive_base_max_health(character_sheet) -> int`** computes three terms, all reading
`effective_combat_level(sheet)` so a bonded sidekick's elevation or mentor's cap flows in:

- **class_term:** sum of `ClassStageHealthRate.health_per_level` for each level 1 through
  `effective_combat_level`, where the stage per level is resolved via
  `stage_for_level(level)` (breakpoints: L1 → PROSPECT, L3 → POTENTIAL, L6 → PUISSANT,
  L11 → TRUE, L16 → GRAND, L21 → TRANSCENDENT). `ClassStageHealthRate` rows are authored
  per `(CharacterClass, PathStage)`. Zero when no primary class is assigned.
- **stamina_term:** `stamina trait value × VitalsConsequenceConfig.stamina_to_health_weight`
  (default 3 HP per Stamina point; staff-tunable in admin).
- **covenant_term:** `covenant_role_health(character, level)` — sums
  `level × CovenantRoleBonus.bonus_per_level` over all ENGAGED covenant roles whose
  `CovenantRoleBonus` rows target the `max_health` `ModifierTarget`. One DB query; no
  query-in-loop. Forward-compat: armor keys on the ENGAGED role, so the future
  per-resonance role variants (#1277) swap which role's bonus applies without touching
  this formula — the thread level selects the variant, never feeds a health number
  directly (no double-count with the thread addend path).

**Recompute triggers:** character-creation finalize (full health at creation),
`set_primary_class_level`, mentor-bond establish/dissolve, covenant role
engagement/membership change (engage/disengage/end/change role).

**Follow-up:** #1277 — per-resonance role variants; no health architecture change needed.

**Thread survivability engine (SHIPPED — #1175, #1250, #1251, #1252):** Thread investment
contributes a universal passive survivability bonus across every vector likely to kill a
character, via `survivability_baseline(character, vital_target)`. Formula:
`round(cap × S / (S + half))` where `S = coefficient × Σ depth(t) × coherence_factor(t)`
(breadth × depth, soft-capped). Parameters are authored per `VitalBonusTarget` in
`ThreadSurvivabilityTuning` (staff-tunable; defaults: DR cap=20 half=8; HP cap=80 half=10;
DEATH_SAVE/KNOCKOUT_RESIST/PERMANENT_WOUND_RESIST cap=15 half=8). Wired vectors:
- **DR + max-health (#1175):** baseline subtracts from incoming damage / adds to max health.
- **Threshold saves (#1250):** the death / knockout / permanent-wound baselines feed each tier's
  roll `extra_modifiers` in `process_damage_consequences`, improving the odds of avoiding the
  bad outcome.
- **Universal damage reduction (#1251):** thread DR now also reduces non-combat damage —
  condition DoT (`_apply_round_tick_damage`) and traps/effect consequences (`_deal_damage`) —
  not just combat. (Since all damage routes its threshold rolls through
  `process_damage_consequences`, hazard/DoT *saves* come from #1250 automatically.)
- **Fashion/motif coherence amplifier (#1252):** each thread's contribution is multiplied by the
  fashion coherence of *its own* resonance (`motif_coherence_bonus`), capped at
  `coherence_max_multiplier`; an uncoordinated wardrobe is inert (no penalty).

Thread-rich parties are simply stronger — encounter difficulty scales on **party size + average
level ONLY** (invariant from #566; unaffected by this engine).

**Wound ladder** (descriptive, added to character description):
- 90%+ health: "Perfectly healthy"
- Escalating descriptions down to 0%: bruised → battered → ... → "death's door"

**Threshold effects:**
- Hit > 50% of total health: chance of permanent wounds/scars
- Below 20% health: chance of knockout per hit, increased by high fatigue/collapse risk
- 0% health: chance of death per hit, high chance of permanent wounds/scars
- Magical damage at 0%: chance of mage scars (Soulfray-related)
- All threshold checks modified by roll modifiers as usual

**Audere triggers:** Health is the primary Audere domain — risk of character loss is the
core trigger. Fatigue compounds danger (collapse risk when health is low) but Audere
moments come from being on the edge of death, not from being tired.

**Damage resolution:** When an NPC action targets a PC, the PC makes a defensive check
(physical/social/mental matching the attack type). NPC attack power sets base damage;
the PC's check result modifies it (great success = no damage, partial = reduced, failure =
full, critical failure = extra). NPC attacks are relatively static — what matters is
PC rolls and abilities. Effort level on defense adds fatigue pressure (spend high effort
to defend better but drain your pools faster). Focus stays on PCs as active agents.

### Other Design Points
- **No symmetrical PVP:** Frees balance to focus on "feels cool" rather than "perfectly fair"
- **Magic is predominant:** Gifts should greatly move the needle. Higher Path steps and threshold crossings should feel transformative in combat
- **Relationship bonuses in combat:** Romance gives collaborative bonuses; if one partner is near death, the other gets an overwhelming bonus nudging them toward an Audere Majora. Rivalries give intensity bonuses. Party bonds improve coordination
- **Level considerations:** Need caps to prevent low-level characters from feeling worthless, while still allowing them to participate meaningfully
- **Fatigue integration:** Combat actions drain fatigue pools by category, creating attrition pressure that builds toward collapse/Audere moments

## What Exists
- **Combat models:** CombatEncounter (`scene` FK — **required, NOT NULL, PROTECT**; every encounter
  carries a scene, #1236), CombatOpponent (with optional Persona FK for story NPCs), CombatParticipant
  (lightweight join table: encounter + character_sheet + covenant_role), EncounterRiskAcknowledgement
  (one row per character per encounter — voluntary-entry consent record, #777), BossPhase,
  ThreatPool/ThreatPoolEntry, CombatRoundAction, CombatOpponentAction, ComboDefinition, ComboSlot,
  ComboLearning
- **Combat services:** Encounter lifecycle (add_participant, add_opponent, begin_declaration_phase), NPC action selection from weighted threat pools, damage resolution with soak/probing/bypass, PC damage writing directly to CharacterVitals, resolution order by covenant role speed_rank, combo detection/upgrade/revert, round orchestrator (resolve_round), defensive check integration (resolve_npc_attack), boss phase transitions (check_and_advance_boss_phase)
- **Vitals system (world.vitals):** CharacterVitals is the single source of truth for character health (health, max_health) and the binary mortality marker `life_state` (ALIVE/DEAD). `CharacterStatus` (ALIVE/UNCONSCIOUS/DYING/DEAD) and `dying_final_round` / `unconscious_at` are removed — incapacitation and dying are now conditions (see below). `is_dead` / `is_alive` / `can_act` service functions replace the old field reads. `derive_character_status` recomputes a coarse read-only label at wire time
- **Covenants system (world.covenants):** CovenantRole lookup table with speed_rank, CovenantType (DURANCE/BATTLE), RoleArchetype (SWORD/SHIELD/CROWN). Combat reads covenant roles for resolution order — speed is never denormalized onto participants. **Covenant-role armor-soak gate (#1174):** `apply_equipped_armor_soak` splits worn armor into compatible/incompatible buckets; soak = `compat_physical + max(incompat_physical, resonant_pool)`, where the resonant pool scales on character level — incompatible armor competes against the resonant pool rather than stacking additively.
- **Bulk condition application:** `bulk_apply_conditions` batches DB queries (~5 total regardless of target/condition count) for efficient multi-target condition application from NPC attacks. Combat uses this instead of per-target loops
- **Supporting systems:** Conditions app has combat-relevant fields (affects_turn_order, draws_aggro, turn_order_modifier, aggro_priority). Mechanics app has modifier collection/stacking, plus the Challenge/Situation system and action generation pipeline. Checks app has the roll resolution engine (perform_check)
- **Capability/Application system:** Properties on enemies/environments, Applications matching character Capabilities to available combat actions, ChallengeApproach with required_effect_property for fine-grained constraints. Action generation auto-surfaces what each character can do in a given combat situation
- **Magic integration:** TechniqueCapabilityGrant connects magic techniques to capabilities. TraitCapabilityDerivation connects stats to capabilities. Combos link to EffectType and Resonance from magic app
- **Magic — pull integration (Spec A):** `CombatPull` records each resonance spend tied to a
  combat round; `CombatPullResolvedEffect` carries the resolved effect rows for audit and
  replay. `VITAL_BONUS` effects route through the `DamagePreApply` hook during damage
  resolution (additive to soak), and pull expiry uses clamp-not-injure semantics so an
  expiring HP buff never drops the character below their current health. Pull costs are
  paid up-front via `spend_resonance_for_pull`. See `docs/systems/magic.md` for the full
  model lineup.
- **Survivability pipeline (world.vitals.services):** `process_damage_consequences()` is the system-agnostic entry point for damage consequences. Uses `perform_check` with scaled difficulty for knockout (below 20% health), death (at or below 0%), and permanent wound (hit > 50% max health) checks. Callable by combat, missions, traps, or any damage source
- **DEAL_DAMAGE effect handler:** Connected — `ConsequenceEffect` with `EffectType.DEAL_DAMAGE` applies damage to CharacterVitals and triggers the survivability pipeline. Works for combat, missions, traps, and challenges
- **Combat REST API:** Full endpoint set at `/api/combat/` — GM lifecycle (begin_round,
  resolve_round, add/remove participant, add opponent, pause), player actions (declare, ready,
  combo upgrade/revert, my_action, available_combos), and participation (join, flee).
  Covenant-scoped action visibility. Permission classes: IsEncounterGMOrStaff,
  IsEncounterParticipant, IsInEncounterRoom. **Encounter list/retrieve read gate (#1041, simplified
  in #1236):** `CombatEncounterViewSet._filter_readable()` restricts list and retrieve to encounters
  whose scene is viewable by the caller (`Scene.objects.viewable_by(user)`). Staff bypass full
  queryset. The participant union and null-scene staff-only branch are gone — every encounter
  carries a required scene, so scene visibility subsumes participant membership. Effect/power-ledger
  details are separately gated by `combat.permissions.can_view_encounter_effects` (staff, scene
  GM, or encounter participant — stricter than scene visibility by design).
- **Round pacing:** Timed mode (default, configurable minutes with auto-resolve), Ready mode (all players mark ready), Manual mode (GM triggers). Timer task runs every 30 seconds via game clock scheduler
- **Participation:** PCs in the room can self-join active encounters. Flee resolves as a graded check at round resolution with authored tier difficulty, ally cover bonuses, and pool-routed failure consequences (#878)
- **Tests:** 599 tests across combat, vitals, conditions, mechanics, checks, and covenants
- **Admin:** Full Django admin with inlines for all combat, vitals, and covenant models

## What's Needed for MVP

### Party Combat (first priority) — Phases 1–9 complete
Full design: `docs/plans/2026-04-05-party-combat-design.md`

**Design-intent gaps with no phase yet (audited 2026-06-09, tracked):**

- ~~**Combat escalation engine**~~ **DONE (#872):** intensity builds across rounds
  toward a climax via authored `EscalationCurve` rows (nullable
  `CombatEncounter.escalation_curve` FK; null = no escalation). Each escalating
  round, `begin_declaration_phase` ticks every ACTIVE participant's combat
  `CharacterEngagement`: `escalation_level += 1`,
  `intensity_modifier += curve.intensity_step`, and a graded control pace check
  (authored `pace_check_type` + difficulty fields, banded on
  `CheckOutcome.success_level`) decides how much `control_modifier` keeps up.
  Failure is lag-only — the widening deficit expresses through the existing
  per-cast pipeline (anima-cost spikes → Soulfray → `select_mishap_pool` →
  Audere gates); no parallel resolution path. Combat now **owns the engagement
  lifecycle**: `add_participant`/`join_encounter`/`begin_declaration_phase`
  create COMBAT engagements (mechanics' `begin_engagement`), flee/removal/
  cleanup delete them (`end_engagement`) — this also opened the Audere
  engagement gate in production and removed the unengaged +10 social-safety
  control bonus inside combat. Relationship spikes ride the reactive layer:
  seeded `escalation_spike_on_incapacitated`/`_on_killed` TriggerDefinitions
  (`wire_escalation_content()` in combat factories) install on the encounter
  room and spike bonded survivors' intensity
  (`RelationshipTrack.fuels_escalation_spikes` + per-curve point gate);
  CHARACTER_INCAPACITATED now emits on the band *transition* only (one beat,
  no per-hit re-emission; force_death emits the death event alone). API:
  escalation fields on participant + encounter detail serializers (curve is
  GM-writable); frontend renders an escalation strip in RoundFlow. Integration
  test `test_escalation_integration.py` proves the build-to-climax arc
  (rounds escalate → costs spike → Soulfray mounts → `PendingAudereOffer`
  fires). Deferred: near-death (not just fallen) spikes, scene-EMIT tick
  narration, risk-level→default-curve GM tooling.
- **Audere offer/accept player surface** — shipped (#873): qualifying casts persist a
  `PendingAudereOffer` row; players see and answer it via the REST inbox/respond
  endpoints (`/api/magic/audere/`) and the combat-panel ceremony dialog (auto-opens on
  a pending offer, active-Audere strip while it burns); encounter cleanup ends Audere
  via `end_audere` (reverting the intensity modifier and anima-pool expansion) and
  deletes unanswered offers
- ~~**Passive action defaults are mechanically no-ops**~~ **DONE (#874):** the
  secondary defend/buff/debuff/combo-opening passives are now mechanically real
  end-to-end. A PC's two non-focused categories each carry a passive technique
  that resolves with **no roll** — `_apply_passive_technique` applies the
  technique's authored conditions with severity from
  `compute_severity(effective_power=technique.intensity,
  success_level=row.minimum_success_level)` to SELF / ALLY / ENEMY targets, and
  grants combo-opening probing (new `Technique.combo_opening_probing` column +
  `increment_probing` helper) when authored. `_resolve_passive_actions` runs in
  `resolve_round` **before** focused resolution so defensive passives land ahead
  of incoming attacks (mitigation flows through the existing
  `ConditionResistanceModifier` path). The frontend dispatches the focused action
  and each passive as separate `/dispatch/` calls carrying an `action_slot`
  discriminator (on the COMBAT `ActionRef`) plus `effort_level`; backend
  `_record_combat_declaration` does a **slot-aware read-merge-write** so the
  separate dispatches converge onto one `CombatRoundAction` row, with the
  focused-vs-passive XOR resolved authoritatively on the backend regardless of
  arrival order. Four authored passive archetypes
  (defend / buff / debuff / combo-opening) ship as FactoryBoy chains; a
  defensive-passive damage-delta integration test proves mitigation lands before
  the attack resolves.
- ~~**NPC tier mechanics**~~ **DONE (#875):** Swarm and Hero Killer now have
  differentiated mechanics. **Swarm** uses per-opponent count pools
  (`swarm_count`/`max_swarm_count`/`body_toughness`/`bodies_per_attack` on
  `CombatOpponent`, null for other tiers): damage ignores soak and clears
  `max(1, raw // body_toughness)` bodies (DEFEATED at 0), and offensive volume
  scales attritionally — `select_npc_actions` emits
  `clamp(ceil(swarm_count / bodies_per_attack), 1, acting_PCs)` attacks/round
  (the one-action-per-opponent unique constraint was dropped; `resolve_round`
  resolves every swarm action). Those attacks **fan across distinct PCs**
  (#983): single-target selection rotates round-robin per attack, so a swarm
  spreads over the party rather than dogpiling the first PC — realizing the
  intent behind capping the count at acting-PC count. **Hero Killer** is
  unbeatable: damage never sets
  DEFEATED, `_classify_encounter_outcome` forbids VICTORY while one is present, so
  the only resolution is fleeing (FLED via the existing flee pipeline). A derived
  `CombatEncounter.forced_escape` property drives a "you must run" banner in the
  combat UI. Mook/Elite stat-default differentiation **shipped in #566** (per-tier
  `OpponentTierTemplate` rows feed the scaling formula — see Encounter Scaling above).
- ~~**Encounter aftermath**~~ **DONE (#876):** completion runs through a single
  `complete_encounter` seam: a typed `EncounterOutcome`
  (victory/defeat/fled/abandoned, classified at completion) + `completed_at` on
  the encounter; per-PC aftermath via authored `EncounterAftermathRule` cells
  keyed (outcome, risk_level) with check_type + base_difficulty + pool, resolved
  through the flee idiom (`select_consequence` → `apply_resolution` →
  `record_consequence_outcome` anchored to a ceremonial Narrator OUTCOME line in
  the pose log); per-opponent `aftermath_pool` FK fired deterministically for
  DEFEATED opponents on victory; `ENCOUNTER_COMPLETED` reactive event (the
  Legend/loot/story hook — combat never awards XP); `combat.encounters_won/
  lost/fled` counters; GM `POST /end/` endpoint (sole ABANDONED producer);
  outcome banner + GM end control in the combat panel
- ~~**Flee is an auto-succeed stub**~~ **DONE (#878):** flee resolves as a graded
  check at round resolution (`_resolve_flee`): authored difficulty via the
  `FleeConfig` singleton + per-`OpponentTier` `FleeTierModifier` rows (Hero Killer
  +20 — the #875 lever), ally COVER declarations add an authored `cover_bonus`
  through the shared modifier seam, and PARTIAL/FAILURE/BOTCH route through a
  seeded consequence pool (PARTIAL = escape at a cost; a successful escape skips
  later same-round NPC hits). New `cover` endpoint + web declaration UI
  (Flee/Cover controls in YourTurn). Starter pool is label-only until authored
  condition content lands.

**Phase 1 (complete):** Foundation models and core services
- CombatEncounter, CombatOpponent, CombatParticipant, BossPhase models
- ThreatPool/ThreatPoolEntry NPC behavior models
- CombatRoundAction, CombatOpponentAction per-round tracking
- Encounter lifecycle services (add_participant, add_opponent, begin_declaration_phase)
- NPC action selection from weighted threat pools with targeting
- Damage resolution with soak, probing, and bypass mechanics
- PC damage with health thresholds (knockout, death, permanent wound eligibility)
- Resolution order service (covenant rank sorting with speed modifiers)
- FactoryBoy factories and 66+ tests
- Django admin with inlines

**Phase 2 (complete):** Combo system and round orchestration
- ComboDefinition, ComboSlot, ComboLearning models with admin and factories
- Combo detection (detect_available_combos) matching declared actions by effect type + resonance
- Combo upgrade/revert lifecycle (upgrade_action_to_combo, revert_combo_upgrade)
- Full round resolution orchestrator (resolve_round: declaration → detection → resolution → consequences, atomic transaction)
- Defensive check integration (resolve_npc_attack using perform_check with success-level damage multipliers)
- Boss phase transitions on health percentage triggers (check_and_advance_boss_phase)
- Speed-rank-based resolution order (PCs by covenant role speed_rank, NPCs at rank 15, no-role at rank 20)
- Vitals extraction: CharacterStatus enum and health thresholds moved to world.vitals (CharacterStatus later removed in Phase 8)
- BaseEvenniaTest replaced with TestCase in all combat tests
- Denormalization cleanup: CombatParticipant stripped to join table (health/status/speed removed), CombatEncounter dropped story/episode FKs (derivable from scene), CombatOpponent gained optional Persona FK for story NPCs
- CharacterVitals is the health authority: combat reads/writes health directly, no sync step
- 599 total tests across combat, vitals, conditions, mechanics, checks, and covenants

**Phase 3 (complete):** Survivability pipeline, DEAL_DAMAGE handler, REST API, pacing
- Survivability pipeline in world.vitals.services — knockout/death/wound checks via perform_check with scaled difficulty
- DEAL_DAMAGE effect handler connected — non-combat damage (traps, spells, consequences) flows through vitals
- Combat REST API — CombatEncounterViewSet with GM lifecycle, player actions, participation endpoints
- Round pacing system — timed/ready/manual modes with auto-resolve timer task
- Join/flee participation — PCs self-join from room, flee stub (auto-succeeds)
- Nullable focused_action for passives-only rounds (AFK/fleeing players)
- Permanent wound pool routing stubbed pending content authoring

**Phase 4 (complete):** Magic pipeline integration (damage path)
- Combat-cast techniques route through `use_technique` for damage. Anima deduction, soulfray, mishap rolls, TECHNIQUE_PRE_CAST/CAST events, reactive scar interception, and corruption checks all fire on combat-cast attacks
- `CombatTechniqueResolver` (frozen dataclass) is the resolve_fn. Active `CombatPull` FLAT_BONUS effects feed offense check `extra_modifiers` per Spec A §5.8
- See `docs/architecture/combat-magic-integration.md`

**Phase 5 (complete):** Non-attack effect routing + CombatOpponent identity refactor
- **Non-attack techniques apply conditions in combat.** `TechniqueAppliedCondition` through model authors which conditions a technique applies, with formula-based severity and duration scaling: `base + intensity_mult × effective_intensity + per_extra_sl × max(0, SL − min_sl)`. Buff, Defense, Movement, and Debuff techniques are now functional in combat
- **Attack techniques can also apply conditions.** A "Burning Strike" can do damage AND apply Burning via the same authoring path
- **`compute_effective_intensity` aggregates** technique.intensity + active `INTENSITY_BUMP` pull contributions; opens future hooks for item/condition/environmental modifiers without signature changes
- **Ally / self targeting on `CombatRoundAction`.** `focused_target` renamed to `focused_opponent_target`; new `focused_ally_target` FK to CombatParticipant. XOR-validated in `clean()`. Self-cast = ally target = caster's participant
- **`bulk_apply_conditions` accepts per-entry severity/duration/stack_count** via `BulkConditionApplication` dataclass. Replaces the predecessor's shared-knobs signature; per-target formula values now expressible in one batched call
- **`CombatOpponent` → `ObjectDB` linkage with multi-layered safeguards.** FK with SET_NULL (was OneToOne until #778 — a PC can back opponent rows across many encounters; per-encounter uniqueness enforced by a conditional UniqueConstraint), `objectdb_is_ephemeral` flag, DB CheckConstraint, model `clean()` with four checks, `add_opponent` chokepoint with `full_clean()`, and `cleanup_completed_encounter` re-check before deletion. Persona-bearing NPCs and pre-existing ObjectDBs (PvP, named NPCs without persona) are never destroyed by combat cleanup
- **`CombatNPC` typeclass** for encounter-scoped ephemeral mooks. Created at `add_opponent` with `existing_objectdb=None, persona=None`; lives at `encounter.room`; cleaned up at `cleanup_completed_encounter`
- **`CombatEncounter.room` FK** added — ephemeral CombatNPCs are placed here at creation
- **TECHNIQUE_AFFECTED fires uniformly** on every target including mooks (lifesteal-style on-affected reactive triggers now work against generic NPCs)
- **Round-tick wiring.** `process_round_start` / `process_round_end` now called from `begin_declaration_phase` / `resolve_round` for active participants and active opponents — conditions in combat actually decay and DoT-tick
- **`declare_action` target validation.** XOR check, target-kind alignment with technique authoring (SELF/ALLY interchangeable), damage-only requires opponent target
- See `docs/architecture/combat-conditions.md`

**Phase 6 (complete):** Damage scaling by effective intensity
- **Per-technique damage authoring.** New `TechniqueDamageProfile` through-model. Same formula shape as `TechniqueAppliedCondition` and `TechniqueCapabilityGrant`: `base_damage + intensity_multiplier × effective_intensity + per_extra_sl × max(0, SL − min_sl)`. Authors knob each row independently.
- **Multi-component damage authoring.** A "slashing fire sword" gets two profile rows (one slashing, one fire). Each applies as a separate damage event with its own resistance lookup. Two-DAMAGE_PRE_APPLY / two-DAMAGE_APPLIED per cast.
- **Damage types end-to-end.** `TechniqueDamageProfile.damage_type` and `ThreatPoolEntry.damage_type` (FKs to existing `DamageType`). `apply_damage_to_opponent` and `apply_damage_to_participant` accept `damage_type: DamageType | None` and apply resistance lookup. `_resolve_npc_action` passes `threat_entry.damage_type` (closes the long-standing TODO).
- **`ConditionResistanceModifier` is now consumed.** Wired through a new `CharacterConditionHandler` (mirrors `CharacterCombatPullHandler`) — caches active condition instances + their resistance modifiers; service functions never call `.filter()` on the related manager. Negative `modifier_value` = vulnerability (target takes more damage).
- **`CharacterConditionHandler` invalidation** is wired into every condition-mutation service (`apply_condition`, `bulk_apply_conditions`, `process_round_start/end`, `process_action_tick`, `remove_condition`, `clear_all_conditions`, `suppress_condition`, `unsuppress_condition`, `advance_condition_severity`, `decay_condition_severity`, `process_damage_interactions`).
- **`DamageSuccessLevelMultiplier` lookup table** replaces inline full/half/zero thresholds. Tunable in admin without code changes. Defaults seeded by the planned startup-page mechanism (and by factories in tests).
- **`DamagePreApplyPayload` / `DamageAppliedPayload` `damage_type` migrated** from `str` to `DamageType | None` FK. Closes the long-standing conflation where `attack_category` (PHYSICAL/SOCIAL/MENTAL — a check category) was being passed as the damage type.
- **`TechniqueCapabilityGrant.calculate_value` extension.** Accepts keyword-only `effective_intensity` override for future Challenge-in-combat work where pull bumps should affect Capability values.
- **`add_opponent` Character-typeclass guard.** `existing_objectdb` must be a Character typeclass instance — raises `TypeError` otherwise. Damage path's `opponent.objectdb.conditions` access can never miss the handler.
- **`bypass_soak` stays combo-only.** Architectural rule: solo casts never bypass soak. The `TechniqueDamageProfile` model has no `bypass_soak` field; `_apply_damage` never passes `bypass_soak=True`.
- See `docs/architecture/damage-scaling.md`

**Phase 7 (complete):** Magic-in-combat fixes + unified player-action interface
**Branch:** `unified-action-interface`
**Design spec:** `docs/architecture/unified-player-action.md`

Two deliverables in one branch:

*Magic-in-combat fixes (Phase 1):*
- **`offense_check_type` sourced from `technique.action_template`** — declared combat spells
  now use the technique's authored check type instead of falling back to a bare `None`.
  Previously, combat-cast techniques dealt 0 damage via the REST view path.
- **`focused_ally_target` declarable via API** — `declare_action` serializer now validates
  and accepts `focused_ally_target` (FK to CombatParticipant). Self-cast and ally-targeting
  techniques are fully declarable over the REST API.
- **Typed `ActionDispatchError`** — `_run_actions` now raises `ActionDispatchError` (with
  `user_message`) and the `resolve_round` view returns a 400 response with the message,
  instead of letting unhandled exceptions propagate.
- **E2E regression test** — `test_e2e_combat_magic_api.py` drives the full
  create-encounter → declare-spell → resolve-round cycle, asserting damage lands and
  condition is applied.

*Unified player-action interface (Phases 2–3):*
- **`RoundContext` ABC + resolver** — combat-agnostic tempo seam. `RoundContext`
  carries `round_number`, `declaration_open` flag, and `character` (CharacterSheet).
  `get_round_context(character_sheet)` returns a concrete `CombatRoundContext` when
  the character is in a declaration-phase encounter; `None` otherwise. Future
  non-combat turn providers slot into the same seam without changing call sites.
- **`RoundChallengeDeclaration` bridge** — deferred challenge declarations (challenge
  approach + capability source) stored per (encounter, participant, challenge_instance)
  triplet. `record_declaration()` is mutually exclusive with focused-action declarations
  (XOR). `resolve_round` processes these as a post-pass in initiative order after all
  focused/passive actions resolve.
- **`PlayerAction` / `ActionRef` descriptors** — `PlayerAction` is the unified wire type
  for "what can this character do right now": `backend` (CHALLENGE/COMBAT/REGISTRY),
  `display_name`, `description`, `difficulty`, `prerequisite_met`,
  `prerequisite_reasons`, `check_type`, `action_template`, `ref`. `ActionRef` is the
  opaque dispatch token.
- **`get_player_actions(character_sheet, location)`** — merges three backends into one
  scored list: challenge approaches (from `get_available_actions`), declarable combat
  actions (when declaration window is open), and REGISTRY actions (checkless utility
  actions; excluded from the scored list but dispatchable).
- **`dispatch_player_action(character_sheet, ref, **kwargs)`** — single routing function
  that validates current availability, checks round-gating, and routes to the correct
  backend handler.
- **`GET /api/actions/characters/<id>/available/`** — returns the merged `PlayerAction`
  list. Replaces the old `GET /api/mechanics/characters/<id>/available-actions/` endpoint
  (which is deleted). Frontend repointed to the new URL.
- **`POST /api/actions/characters/<id>/dispatch/`** — dispatches by `ActionRef`. Same
  permission class (`IsCharacterOwner`) as the read endpoint.
- **WebSocket `execute_action`** — now routes through `dispatch_player_action`. The legacy
  `action_key`/`technique_id` shape is normalised into an `ActionRef` at the WS layer;
  single dispatch path for REST and WS.
- **Superseded mechanics endpoint removed** — `GET /api/mechanics/characters/<id>/available-actions/`
  and its serializer are deleted. `ActionPanel` and `ActionAttachment` fetch from the
  unified endpoint.

*Known deferred seams (design follow-ups, not implementation gaps):*
- **REGISTRY actions excluded from the scored list** — REGISTRY is checkless utility; the
  actions are dispatchable but intentionally absent from `get_player_actions` scored
  output.
- **Enhancement-rich social surface not yet folded in** — `GET /api/action-requests/available/`
  returns per-action `AvailableEnhancement` lists (anima costs, Soulfray warnings).
  The unified endpoint returns plain `PlayerAction` descriptors without enhancement data.
  `ActionPanel` fetches both and joins client-side. Follow-up: fold enhancement data into
  `PlayerAction` so the unified endpoint is self-contained. (See magic.md Scope 4 deferred note.)
- **Consequence→challenge spawn not yet wired** — the unified read surfaces spawned
  challenges when that lands; no interface change will be needed.
- **General (non-combat) turn provider — built (#520).** The `SceneRound` provider in
  `world/scenes` implements the `RoundContext` seam alongside combat: opt-in / GM /
  danger rounds, a shared per-target tick orchestrator, and **deferred-declaration
  turn-taking** — in a social (opt-in/GM) round, declarations gather within the round
  and resolve together in **initiative order** once every participant *present in the
  room* has declared or (implicitly) passed; a GM may force-resolve, and an absent/idle
  participant is an implicit pass that never blocks the round. Resolution is only ever
  triggered by a turn-costing action (never a timer), so an idle scene never advances —
  the AFK-safety guarantee. See `world/scenes/round_context.py`,
  `world/scenes/round_services.py`, and the `SceneActionDeclaration` bridge.
- **Frontend targeted-action routing gap** — `PlayerAction` has no `is_targeted` /
  target-spec field. `ActionPanel` currently uses `prerequisite_met` as a proxy for
  whether to enable the dispatch button, leaving the targeted-action UI path effectively
  unreachable. A future descriptor field (e.g. `is_targeted`) is needed to route the
  frontend correctly to the consent/target-picker flow. Design follow-up.

**Phase 8 (complete):** Decouple incapacitation and dying from vitals (#595)

The old model stored incapacitation and dying as enum values in `CharacterVitals.status` / `dying_final_round`. Phase 8 replaces this with the capability/agency model and condition-based survivability:

- **`CharacterVitals` reduced to life/death** — `CharacterStatus` enum removed along with `status`, `dying_final_round`, and `unconscious_at` fields. Only `life_state` (ALIVE/DEAD) remains as the binary mortality marker. Two migrations: `0003_migrate_status_to_life_state` (data migration from old enum) and `0004_remove_charactervitals_*` (field removal).
- **`can_act` service** — coarse round-participation gate: `not dead AND awareness > 0`. An Unconscious PC has awareness zeroed → can_act False. A dying-but-conscious PC keeps awareness → can_act True. Degrades gracefully if awareness capability is not seeded.
- **Unconscious condition** — non-progressive `ConditionTemplate` (name=`"Unconscious"`) with a `ConditionCapabilityEffect` that zeroes the `AWARENESS` foundational capability. Applied by `process_damage_consequences` on a failed knockout check. SQLite-compatible (no DISTINCT ON).
- **Bleeding-Out condition** — progressive `ConditionTemplate` (name=`"Bleeding Out"`, `has_progression=True`) applied by `process_damage_consequences` on a failed death check. Does NOT impair awareness — dying characters remain conscious and can act.
- **`advance_bleed_out`** — called once per round from `resolve_round` for every participant with an active Bleeding-Out condition. Each round the character rolls a stage resist check; failure advances the stage. Failure at the terminal stage calls `_mark_dead`, writing `life_state=DEAD`.
- **`FoundationalCapability` constants and `CapabilityType.innate_baseline`** — `conditions.constants` defines `FoundationalCapability.AWARENESS` (and stubs for MOBILITY / COGNITION). `CapabilityType.innate_baseline` is the per-type default value when no explicit derivation row exists. `get_effective_capability_value` sums innate_baseline + derivation rows + active condition effects.
- **`TechniqueCapabilityRequirement` + `technique_performable`** — per-technique capability requirements (`Technique` FK + `CapabilityType` FK + `minimum_value`). `technique_performable(character, technique)` returns False when any requirement is unmet. `declare_action` and `_get_performable_techniques` gate on this.
- **Combat eligibility rewired** — `declare_action` raises if `can_act` is False. `_get_combat_participants_who_can_act` filters to participants where can_act is True. `_check_encounter_completion` uses can_act (not status) to determine whether all PCs are down.

**Known follow-ups:**
- **Consequence-pool reconciliation** — knockout/wound/death resolution is reconciled onto the pool pipeline in Phase 9 (#560/#561). The deferred pool plumbing for encounter outcomes shipped in #876 as `CombatOpponent.aftermath_pool` + `EncounterAftermathRule`.
- **Frontend status surface** — the `derive_character_status` wire label is a placeholder. #521 built the vitals sheet panel (VitalsPanel + `GET /api/vitals/<id>/`, surfacing health/fatigue/status); the richer condition-aware status surface (showing Unconscious / Bleeding-Out / other conditions to the player) remains tracked in #522.

**Phase 9 (complete):** Reconcile survivability consequences onto the consequence-pool pipeline (#560, #561)

Phase 8 made knockout/dying condition-driven but left `process_damage_consequences` resolving them through a parallel binary-pass/fail + ad-hoc-difficulty path. Phase 9 reconciles that resolution onto the existing rank → `CheckOutcome`-tier → `ConsequencePool` pipeline already used by challenges and clashes:

- **`resolve_vitals_consequence(character, check_type, target_difficulty, pool)`** — thin wrapper over `resolve_pool_consequences` → `select_consequence` → `apply_resolution`. `select_consequence` rolls the check, filters to the rolled `CheckOutcome` tier, weights the survivors, and applies the selected `Consequence`'s effects. `build_outcome_display` is built from the full resolved pool (all tiers), independent of which outcome was selected.
- **New pool surfaces** — `DamageType.wound_pool` / `death_pool` FKs to `ConsequencePool` (nullable); `VitalsConsequenceConfig` singleton (mirrors `StrainConfig` / `ClashConfig`) holding `knockout_pool` + `default_wound_pool` + `default_death_pool`. Schema migrations only — no data migration (dev DB is disposable pre-production).
- **Seeded checks** — Endurance (shared: knockout + wound) and Death (distinct) `CheckType`s, self-seeded via `_ensure_*` on first use so a fresh DB never crashes. Every pool lookup may return `None` on an unseeded DB → the branch skips cleanly.
- **Reconciled resolution** — knockout resolves the knockout pool (applies Unconscious); permanent wound resolves `DamageType.wound_pool` (tiered PERMANENT-wound conditions; replaces the `_select_and_apply_wound` stub); death resolves `DamageType.death_pool` (tiered outcomes apply Bleeding-Out / lesser conditions). Bleeding-Out remains one pool outcome; `advance_bleed_out` still drives dying→dead, unchanged. No `SET_LIFE_STATE`.
- **Call sites wired** — `combat/services.py` `_resolve_npc_action` and `mechanics/effect_handlers.py` `_apply_deal_damage` now pass the threat's real `damage_type`; the vestigial `*_check_type` params are dropped. `DamageConsequenceResult` flags (`knocked_out` / `dying` / `wounds_applied`) preserved for callers.

### Risk-acknowledgement gate + cast-seed hardening (SHIPPED — 2026-06-10, #777/#778)

A hostile standalone cast can no longer drag an unacknowledged PC into an EXTREME/LETHAL
encounter, and the cast-seed entry path survives repeat targeting:

- **#778 hardening:** `CombatOpponent.objectdb` OneToOne→FK + conditional
  `UniqueConstraint(encounter, objectdb)`; `seed_or_feed_encounter_from_cast` reuses an
  existing ACTIVE opponent row (raises ValueError on DEFEATED/FLED targets) instead of
  crashing on the old one-row-per-PC-ever constraint. Caster re-declaration in the same
  round updates the `CombatRoundAction` in place (covered by tests).
- **#777 gate:** `EncounterRiskAcknowledgement` records voluntary entry (self-join via
  `join_encounter`, hostile-cast initiation, consent-accept; GM `add_participant` records
  nothing). `encounter_requiring_risk_acknowledgement` (cast_seed.py) gates
  `_route_hostile_cast`: a hostile cast at an unacknowledged target of a feedable
  EXTREME/LETHAL encounter becomes a PENDING `SceneActionRequest` (the existing consent
  pipeline + `ConsentPrompt` UI with a risk warning via `combat_risk_level` serializer
  field); ACCEPT seeds combat and records the target's ack, DENY leaves them out. Fresh
  seeds stay MODERATE and ungated (the #772 ambush path is unchanged). Threshold lives in
  `RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT` (combat/constants.py).
- No frontend join surface exists yet, so the join-confirm dialog from the spec was
  dropped; the server-side ack in `join_encounter` covers normal join.

### Open Encounters (future — builds on Party Combat)
- Spontaneous combat for any number of participants, drop-in/drop-out
- Nullable covenant, participants can join/leave mid-fight
- Same combat primitives, different encounter structure

### Battle Scenes (future — separate system)
- Mass combat VP system with variations (army vs army, all PCs vs kaiju)
- Fixed rounds, victory point tracking, mass participant handling
- Risk/reward action choices per round

### Duels (SHIPPED — Phase 1, 2026-06-18)

**Status: SHIPPED**
**Plan:** `docs/superpowers/plans/2026-06-18-duels-phase-1.md` (ephemeral)
**Issue:** #568 — `EncounterType.DUEL` over the existing combat engine.

Duels are built by reuse, not a parallel engine. Two **structural** paths:

- **Non-lethal PC-vs-PC sparring** — the comic-book convention. Each duelist is a
  `CombatParticipant` (declares actions) *and* is mirrored by a passive ephemeral
  `CombatOpponent` (`mirrors_participant`) that the other attacks — reusing the shipped
  PC-as-opponent wrapping (`cast_seed.py`). Damage only ever lands on the mirror surface,
  so **real `CharacterVitals` are never touched: a PC can never kill or injure another PC**
  (a hard invariant, enforced at creation). Ends at mirror `DEFEATED` or `YIELD`.
- **Lethal PC-vs-significant-NPC** — the only mode where a PC's real vitals are at stake.
  Existing 1-v-1 party-combat path with `risk_level=LETHAL`; the PC must acknowledge the
  risk before declaring (the explicit risk surface).

**Backend shipped (`world/combat/`):** `EncounterType.DUEL`, `CombatManeuver.YIELD`,
`DuelChallengeStatus`, `CombatEncounter.is_lethal` (derived) + `duel_winner` FK,
`CombatOpponent.mirrors_participant` (passive, excluded from NPC action selection),
`DuelChallenge` model; duel services in `combat/duels.py` (`create_pvp_duel`,
`create_lethal_duel`, `resolve_duel_end`, `yield_duel`, challenge accept/decline/withdraw,
`assert_duel_lethality_valid`); YIELD maneuver + lethal-duel acknowledge-before-declare
guard wired into `resolve_round`/`declare_action`; duel-state serializers.

**Non-lethal cap (`world/magic/`):** a single `lethal` flag threaded through
`use_technique` → `deduct_anima`/soulfray so a non-lethal duel draws no overburn deficit,
clamps soulfray below any death-risk stage, and never fires a `character_loss` consequence.

**Web-first actions:** `challenge` (social-consent-gated) / `accept` / `decline` /
`withdraw` / `yield` / `acknowledge_risk`. **Frontend:** `combat/duels/DuelChallengeControls`
(+ yield / acknowledge controls), reusing the existing combat round UI + dispatch.

### Duels — Phase 2 (SHIPPED — 2026-06-20)

**Status: SHIPPED**
**Issues:** #1180 (inbox + prompt), #1181 (outgoing affordance), #1182 (crediting/threading fixes).

- **Incoming-challenge inbox (#1180):** `GET /api/combat/duel-challenges/` —
  `DuelChallengeViewSet` (read-only, filters/pagination/permissions) returns the caller's
  PENDING challenges (`?role=incoming|outgoing`), scoped to played characters via
  `played_character_sheet_ids`, reusing `DuelChallengeSerializer`. The frontend
  `useDuelChallengeInbox` hook feeds `CombatScenePage`, replacing the
  `hasPendingIncomingChallenge={false}` stub. Accept/decline/withdraw now accept an optional
  `challenge_id` kwarg so the UI targets a specific challenge when a PC has several pending.
- **Outgoing affordance (#1181):** a "Challenge to a duel" item on `PersonaContextMenu`,
  dispatching the `challenge` registry action with the target persona id. `ChallengeAction`
  resolves a Persona pk → character ObjectDB (web path; telnet/tests still pass ObjectDB).
  `PersonaSerializer.allow_social_actions` mirrors the consent gate (`_tenure_blocks_actor`
  with `category=None`) so the affordance hides for opted-out targets and for self; the
  backend still enforces the full gate at dispatch.
- **Crediting / threading fixes (#1182):** `_increment_completion_counters` credits a DUEL
  win only to `encounter.duel_winner` (loss to the other duelist; abandoned duel credits
  neither) instead of every ACTIVE participant; `commit_to_clash` threads
  `lethal=clash.encounter.is_lethal` into `use_technique` so the non-lethal cap holds on the
  clash path (latent today — PvP mirror surfaces never form a clash).

**Still open (tracked):**
- Sheet-driven symmetric NPC duellist (the lethal variant reuses the threat-pool opponent).

### Every Combat Encounter Carries a Scene (SHIPPED — 2026-06-20, #1236)

**Status: SHIPPED**
**Issue:** #1236

Every `CombatEncounter` is now guaranteed to have an associated `Scene`. The `scene` FK is
`NOT NULL` with `on_delete=PROTECT` — an encounter cannot exist without a scene, and a scene
with an active encounter cannot be deleted.

**What was built:**

- **Scene invariant at DB level:** `CombatEncounter.scene` flipped from nullable SET_NULL to
  required NOT NULL PROTECT. Factory default updated; null-scene tests retired.
- **Find-or-create at encounter start (duels):** `create_pvp_duel` / `create_lethal_duel` call
  `ensure_scene_for_location(room, privacy_mode=...)` from `scenes.place_services`. Privacy is
  room-derived: `PUBLIC` if `room.room_profile.is_public`, else `PRIVATE`. An existing active
  scene in the room is inherited (its privacy_mode is preserved).
- **Participation convergence:** `_create_participant` calls
  `ensure_scene_participation(encounter.scene, character_sheet.character)` from
  `scenes.interaction_services` so every fighter is a first-class recorded `SceneParticipation`.
  Called from `add_participant` and `join_encounter`.
- **Read-gate simplification:** `CombatEncounterViewSet._filter_readable()` is now
  `scene__in=Scene.objects.viewable_by(user)` (staff bypass + scene-visibility only). The
  participant union and the null-scene staff-only branch are eliminated.

**Deviation from original spec:** privacy derivation lives at the combat call site (explicit
`privacy_mode` passed to the helper) rather than as the helper's default — the conservative
side of the spec's flagged place-behavior change. A global `Scene.clean()` privacy↔room
invariant remains out of scope (follow-up).

### Unified Combat UI (SHIPPED — 2026-05-24)

**Status: SHIPPED**
**Phases:** 0–12 of `docs/superpowers/plans/2026-05-23-unified-combat-ui.md`
**Branch:** `clash-cleanup-notes`

The web-first combat interface is live. Players can declare actions, view the
encounter state, see clash meters, and read pose-linked action outcomes through
the React frontend.

**Backend shipped:**

- `actions/`: clash-contribution dispatch wired in `dispatch_player_action` (Phase 0)
- `world/scenes/`: `InteractionAction` bridge model + factory + tests (Phase 1); `auto_link_pose_to_actions` service + POSE submit endpoint integration (Phase 2); `thumbnail_media_url` on PersonaSerializer with FK select_related (Phase 4); `action_links` field on InteractionSerializer with Prefetch (Phase 9); `without_pose_link` filter (Phase 10)
- `world/magic/`: `InapplicabilityReason` enum, `compute_thread_applicability` service, `POST /api/magic/applicable-pulls/` endpoint (Phase 3)
- `world/combat/`: `clashes` field on EncounterDetailSerializer + ClashStateSerializer + Prefetch (Phase 8); `GET /api/combat/action-outcome-details/?action_interaction_ids=...` endpoint (Phase 9); full UI round-trip integration test (Phase 12)

**Frontend shipped (all under `frontend/src/`):**

- `components/PersonaAvatar.tsx` (Phase 4)
- `actions/ActionDeclarationCard.tsx` + types + tests (Phase 5)
- `magic/components/threads/ThreadPullPicker.tsx` + `PullDetailModal.tsx` + `useApplicablePulls` hook (Phase 6)
- `combat/CombatTurnPanel.tsx` + `sections/YourTurn.tsx` (Phase 7)
- `combat/sections/{ResonanceBudget,VitalPools,CombatantsList,ActiveState,RoundFlow}.tsx` (Phase 8)
- `scenes/components/PoseUnit.tsx` + `PoseUnitDetailPanel.tsx`; updated `SceneMessages.tsx` (Phase 9)
- `scenes/components/PendingActionAttachments.tsx` + `hooks/usePendingUnlinkedActions.ts` (Phase 10)
- `combat/pages/CombatScenePage.tsx` at `/scenes/:id/combat` (Phase 11)
- `e2e/combat.spec.ts` Playwright smoke test (Phase 12)

**Carry-forward status (verified against code 2026-06-09):**

Shipped since the original list:

- `CombatRoundAction → Interaction` join FK + `interaction_timestamp` — **DONE**: `GET /api/combat/action-outcome-details/` enumerates real effects (`views_outcome_details.py`). Surfacing the ledger on standalone cast cards (no linking pose yet) — **#859 DONE**: `PoseUnit` State 3 (shared by scene + combat) gained the chip-expand affordance that lazily fetches outcome details for the standalone ACTION's own interaction id.
- Deep-link routing for outcome-detail effects — **#551 DONE**: outcome-effect deep links open a Redux-driven `DeepLinkModalHost` routing 5 kinds (combo/opponent/participant/condition/clash); added read-only `GET /api/conditions/instances/<pk>/`.
- Fatigue pools — **#552 DONE**: `ParticipantSerializer` exposes physical/social/mental fatigue (current + capacity); `VitalPools` renders real values. Fatigue costs are charged on resolution (`apply_fatigue`).
- Conditions on combatant rows — **#553 DONE**: visibility-filtered `active_conditions` on both serializers; `CombatantsList` badges deep-link to the condition modal.
- ActiveState Commit/Lend buttons — **#555 DONE**: ActiveState is read-only; the clash-commit path lives in YourTurn's `ClashContributionRow` (no parallel surface).
- Focused-category resolution — **DONE** (#558/#614): sourced from the technique's authored `action_category`; the `passive-physical` stub is gone.
- `ClashStateSerializer` — **DONE**: exposes `contributors` and `side_favored`.
- `lend-to-clash` / `CLASH_SUPPORT` — **REJECTED BY DESIGN (#559)**: a clash binds to the focused action only; there is no passive-contribution concept. Do not re-add a Lend surface.
- Single-target focused attacks — **#1001a DONE**: the focused slot's `TargetPicker` (was a Phase-5 kind-`<select>` placeholder) now lists real combatants from the encounter; `YourTurn` threads the chosen target into the focused dispatch as `focused_opponent_target_id` (CombatOpponent PK) / `focused_ally_target_id` (CombatParticipant PK). `CombatRoundContext.record_declaration` resolves those ids to instances scoped to the encounter (forged-id safety) and persists them via `declare_action`. `OpponentSerializer` exposes `objectdb_id` so the card maps the applicable-pulls `target_object_id` correctly.
- Auto-expand pose units on critical events — **#996 DONE**: `InteractionActionLinkSerializer` exposes `has_critical_effect` (cheap, N+1-safe signal: the linked `CombatRoundAction`'s `focused_opponent_target` is DEFEATED, derived from a prefetch — no condition queries); `PoseUnit` initialises its expanded state from `action_links.some(l => l.has_critical_effect)`. The `is_critical` row highlight shipped earlier in #1004.
- Clash strain→power story in the outcome panel — **#977 DONE** (backend `#858`): `PoseUnitDetailPanel` renders a one-line `ClashContributionStory` (`strain → power → progress`) above the power-ledger card for clash outcomes (`progress_delta != null`). `power` is omitted when the viewer can't see the ledger (gated to null server-side); negative `progress_delta` (botch-backfire) renders as a loss. The intensity/multiplier breakdown stays in the `PowerLedgerPanel` card below.

Still open (tracked):

- `submit_pose` REST endpoint does not broadcast via WebSocket — #878
- Per-player preference toggle for critical-event auto-expand (#996 ships it always-on) — no issue yet
- `CombatOpponent` portrait FK — NPC avatars are initial-letter-only (no issue yet)
- Outcome-panel scoping/visibility polish — #866
- Scene-side adoption of `<ActionDeclarationCard>` (no `ScenePull` envelope) — out of this spec's scope
- Positioning/zones integration (#530–#533), mobile responsive layout — out of scope

---

### Clash of Wills (SHIPPED — branch `clash-design`)

**Status: SHIPPED**
**Branch:** `clash-design`
**Spec:** `docs/architecture/clash-design.md`
**Plan:** `docs/architecture/clash-implementation-phases.md`

The reserved "clash" mechanic is built. A **Clash** is a multi-round contested
struggle inside a `CombatEncounter`: PCs pour effort into overpowering — or enduring
— a magical or physical force across multiple rounds while the opposition pushes back.
It is the beam-struggle trope generalised: locked blades, wave against wave, holding a
monster pinned while it thrashes, shielding the party from a sustained barrage,
grinding through a fortress-wall of magic. The clash layer adds a progress meter,
multi-PC aggregation, and threshold resolution on top of the existing `use_technique`
pipeline — anima cost, overburn → Soulfray, mishap riders, reactive events, and
corruption all fire normally for every clash contribution.

**The five flavors:**

| Flavor | What it is | PC role |
|---|---|---|
| **Clash** (archetype) | Two forces head-on, each straining to overpower | offensive vs. offensive |
| **Suppress** | PCs sustain a lock condition on the NPC while it tries to break free | PC sustaining |
| **Break Free** | PCs push out of a lock the NPC placed on them | PC escaping |
| **Ward** | PCs endure a sustained NPC attack across its duration | PC defending |
| **Break** | PCs grind through a magical barrier around the NPC | PC offensive vs. static defense |

All five share the same meter primitive (`Clash` model with a `flavor` discriminator
over four meter shapes). Suppress and Break Free are the same LOCK meter viewed from
opposite sides: `lock_pc_role` (`SUSTAINING` / `ESCAPING`) determines which threshold
the PCs are driving toward.

**Strain is the lever.** A clash is won by committing anima past the safety margin —
gritting your teeth and pushing. The escalation cost is Soulfray and, ultimately, the
Audere offer. This is the heroic-tragic arc the magic system is built around.

**Models added:**

- `Clash` — encounter FK, flavor, lock_pc_role (nullable), progress, pc_win_threshold,
  npc_win_threshold (nullable), status (ACTIVE/RESOLVED), started_round, resolved_round,
  resolution enum (PC_DECISIVE / PC_MARGINAL / MUTUAL / NPC_MARGINAL / NPC_DECISIVE /
  ABANDONED), resolution_consequence_pool FK, per_round_consequence_pool FK (nullable),
  npc_opponent FK to `CombatOpponent`, initiator FK to `CharacterSheet`. Discriminator
  integrity enforced with `clean()` + DB `CheckConstraint`s.
- `ClashRound` — child of `Clash` per round: pc_progress_delta, npc_progress_delta,
  progress_after.
- `ClashContribution` — child of `ClashRound` per PC: character FK, action_slot
  (FOCUSED/PASSIVE), anima_committed, technique FK (nullable), check_outcome,
  progress_delta, was_overburn, was_audere, soulfray_severity_accrued.
  `UniqueConstraint(clash_round, character)` enforces one contribution per PC per round.
- `ClashContributionDeclaration` — staging model: PCs declare clash intent before the
  round resolves; cleared after `resolve_round`.
- `StrainConfig` — singleton tuning surface for the diminishing-returns curve knobs
  (per-anima base conversion, tier breakpoints). Staff-tunable via Django admin without
  code changes.
- `ClashConfig` — singleton: tier→delta table, per-flavor default thresholds, NPC
  contribution weight per-round defaults.

**Schema additions on existing models:**

- `Technique.clash_capable` BooleanField — marks techniques that can be used as clash
  contributions.
- `ThreatPoolEntry` fields for NPC clash behavior: clash commitment weight and
  per-flavor eligibility.
- `CombatOpponent` FK to `Clash` (nullable) — tracks the active clash this opponent is
  a side of.
- `ComboDefinition.clash_prerequisite` FK (nullable) — a combo can require an active
  clash on a specific opponent as its prerequisite gate.
- `ConditionTemplate` clash-state fields — clash state as an authored condition gate;
  combo prerequisite checking reads these.

**Service layer (`src/world/combat/clash.py`):**

- `strain_to_progress(anima_committed, config) -> int` — applies the diminishing-returns
  curve to convert anima commitment to a progress delta.
- `commit_to_clash(clash, participant, anima_committed, technique, action_slot) -> ClashContributionResult`
  — runs the PC contribution through `use_technique` in clash-commit mode (a custom
  `resolve_fn` that captures `CheckOutcome` rather than applying damage), records
  `ClashContribution`.
- `npc_round_contribution(clash, round_number) -> int` — derives NPC progress delta from
  the opponent's threat pool entries and current boss phase; never snapshotted.
- `affinity_tilt(clash, pc_sheet) -> Decimal` — applies the `AffinityInteraction` matrix
  (the RPS cycle) to a signed severity multiplier on the PC's progress delta; reuses the
  same authored `AffinityInteraction` rows as the resonance-environment work.
- `aggregate_clash_round(clash, round_contributions, npc_delta) -> ClashRoundResult` —
  sums PC deltas (with affinity tilt), subtracts NPC delta, advances the meter, writes
  `ClashRound`, checks thresholds.
- `fire_clash_per_round(clash, clash_round_result) -> None` — fires the per-round
  consequence pool on threshold crossings and incremental milestones.
- `resolve_clash(clash, resolution) -> ClashResolutionResult` — resolves the clash,
  selects from the resolution consequence pool, marks `RESOLVED`.
- `detect_clash_opportunities(encounter) -> list[ClashOpportunity]` — inspects active
  opponents and their threat patterns to surface available clash flavor opportunities
  to the declaration panel.
- `run_clash_round(encounter, round_number) -> list[ClashRoundResult]` — top-level
  orchestrator called from `resolve_round`'s clash post-pass.

**`services.py` additions:**

- `declare_clash_contribution(participant, clash, anima_committed, technique, action_slot)` —
  writes a `ClashContributionDeclaration`; XOR-validated against focused-action declaration.
- `_resolve_clashes(encounter, round_number)` — post-pass in `resolve_round` (mirrors
  `_resolve_declared_challenges`); calls `run_clash_round` for every active clash.

**Player-facing surface:** `_clash_contribution_actions(encounter, participant)` emits
`PlayerAction` descriptors (backend=CLASH, `ActionRef` token) for the unified action
interface. The dispatch handler is a flagged follow-up — the read path surfaces what is
available, but the dispatch route is gated with `UNKNOWN_ACTION_REF` until the handler
ships.

**Affinity matrix integration:** `affinity_tilt` consumes the same 9 directed
`AffinityInteraction` rows (the RPS cycle: Primal > Celestial > Abyssal > Primal) as
the resonance-environment work — no parallel opposition table was authored.

**Combo prerequisite gating:** `ComboDefinition.clash_prerequisite` is checked by the
existing combo detection pipeline (`detect_available_combos`). A boss combo that can
only land while a Clash is in progress is expressible in data — no code change to the
detection logic.

**End-to-end pipeline integration:** clash contributions run through the full
`use_technique` → Soulfray accumulation → Audere offer → Mage Scar pipeline. The
`TECHNIQUE_CAST` / `TECHNIQUE_PRE_CAST` reactive events fire for each contribution;
`accrue_corruption_for_cast` runs. An Audere-during-clash scenario is exercised in the
integration test suite.

**Test coverage:**

- `test_clash_models.py` — model unit tests: constants, `StrainConfig` / `ClashConfig`
  singletons, `Clash` discriminator integrity (flavor/lock_pc_role CheckConstraints),
  `ClashRound` / `ClashContribution` constraints, schema additions.
- `test_clash_services.py` — service unit tests: strain conversion curve,
  `affinity_tilt` (all 9 AffinityInteraction pairs), `commit_to_clash` overburn path,
  `npc_round_contribution` threat-pool derivation, `aggregate_clash_round` meter
  advancement, threshold detection, `resolve_clash` consequence-pool selection.
- `test_clash_round_orchestration.py` — round orchestration: `run_clash_round`
  multi-PC aggregation, `_resolve_clashes` post-pass in `resolve_round`, initiative
  ordering, per-round consequence pool firing.
- `test_clash_flavors.py` — per-flavor end-to-end scenarios: Clash (PC decisive / NPC
  decisive / mutual), Suppress (sustained lock held vs. broken), Break Free (escape
  succeeds / fails), Ward (ward endures / collapses), Break (barrier ground down /
  abandoned).
- `test_clash_audere.py` — Audere-during-clash: overburn triggers Audere offer, Audere
  intensity bonus feeds into the contribution check, Soulfray accumulates.

**Known follow-ups / deferred:**

- **Clash-contribution dispatch handler** — **DONE**: `_dispatch_clash_contribution`
  (`src/actions/player_interface.py`) routes clash declarations through the unified
  action interface; the `UNKNOWN_ACTION_REF` gate is gone. FOCUSED-only by design (#559).
- **Positioning / zone-aware POV filtering** — clash visibility (who can see the meter,
  which contributions are shown to which players) depends on the positioning/zones model
  that is not yet settled. See `docs/plans/2026-05-21-positioning-zones-design-notes.md`.
- **Fury lever** — **DONE** (#567): the control-lowering / rage escalation lever, Strain's
  sibling. A player declares a `FuryTier` + a `fury_anchor` (a bonded harmed entity); bond
  strength (`get_relationship_tier`) caps the tier and scales an intensity bonus. Fury lowers
  runtime control via a `control_penalty` param on `use_technique` (feeding the existing
  mishap + anima-cost paths) in exchange for intensity riding the existing
  `power_intensity_bonus` — no fatigue of its own. A provocation-scaled control-retention
  check (Composure/Willpower, per `FuryConfig`) decides lucid-vs-Berserk; lost control applies
  a Berserk `ConditionTemplate` (severity by tier, decays over rounds). Audited on
  `Interaction.fury_committed` + the `CommittingDeclaration` mixin (clash + non-clash). Fury is
  restricted to technique casts. The "Restore to Sense" ally-recovery action is authored,
  effect-tested, and **live-dispatchable** on the scene consent path (#1172): accepting the
  request fires its `RemoveConditionOnCheckConfig`, removing the target ally's Berserk
  condition end-to-end.
- **Frontend / web UI** — the backend is complete; the declaration panel and round-by-round
  clash visibility UI is a follow-up.

### Shared Future Work (combat-adjacent)
- **Encounter scaling / GM tooling** — difficulty from story context + party composition, encounter builder
- **Relationship modifier integration** — romance bonuses, rivalry intensity, party bond effects
- **Audere Majora trigger conditions** — health thresholds feeding into Audere system
- **Combo content authoring** — staff tools for creating/testing combo definitions
- **Knockout/death roll services** — DONE in Phase 8: `process_damage_consequences` applies Unconscious/Bleeding-Out conditions via `perform_check` on threshold failures. Permanent wound routing remains stubbed pending content authoring
- **Permanent wound application** — connect permanent_wound_eligible to ConditionTemplate instances
- **Combat UI carry-forward** — see Unified Combat UI section above for the known remaining items

### Narrative Status in Character Descriptions (future)

When a character is wounded, fatigued, or otherwise visibly affected, their
appearance to other characters should reflect it — narrative text appended
to their description, e.g. *"She looks pale and unsteady, leaning on the
wall."* This belongs to combat's domain because the source data is vitals /
fatigue / conditions which combat owns. Hooks into the perception layer's
appearance template (`CharacterState` already exposes display-component
methods like `get_display_worn`; add a sibling `get_display_status` that
reads from vitals/fatigue/conditions and returns the narrative line).

Out of scope for the visible-worn-equipment slice — that one only adds
visible equipment to the look output; the appearance template gets a
`{status}` slot ready for this work but renders empty until this
follow-up lands.

### Positioning Model — Phase 1 (SHIPPED — #530)

Room-anchored spatial graph with capability-gated movement, occupancy tracking, and a
playable move action. Works across combat, social scenes, and non-combat events — not
tied to the combat subsystem.

**Location:** `src/world/areas/positioning/`

**What ships:**

- **Models:** `Position` (named region anchored to a room, discriminated by `PositionKind`),
  `PositionEdge` (traversable adjacency between two `Position` nodes; optional
  `gating_challenge` FK → `mechanics.ChallengeInstance`, `is_passable` flag),
  `ObjectPosition` (OneToOne occupancy record mirroring `db_location`)
- **Authoring/query services:** `create_position` / `remove_position` /
  `connect_positions` / `disconnect_positions` / `edge_between` /
  `reachable_positions` / `adjacent_open_positions`
- **Placement + movement services:** `place_in_position` (unconditional placement),
  `move_to_position` (validates adjacency, passability, active-gating via Challenge
  system, and MOVEMENT capability via `get_effective_capability_value`),
  `force_move_to_position` (staff/consequence bypass), `position_of`
- **Challenge reuse:** spatial obstacles (locked gates, difficult terrain) use the
  existing `ChallengeInstance` system — no parallel obstacle model built
- **Combat integration:** derived `current_position` property on `CombatParticipant`
  and `CombatOpponent` (reads `ObjectPosition` for the underlying ObjectDB)
- **Playable action:** `MoveToPositionAction` surfaced through `get_player_actions`
  and dispatched via `ActionRef` with a `position_id` token — slots into the
  unified player-action interface shipped in Phase 7

**Deferred to follow-up issues (still open):**

- Occupancy-screening reachability (crowded-position filtering)
- Zone-aware targeting (#533), POV visibility (#531), combat-UI positioning rendering (#532)

### Positioning — Blueprints + Non-Combat Scene UI (SHIPPED — #1017)

GM terrain-blueprint authoring and non-combat scene positioning, building on Phase 1.

**Location:** `src/world/areas/positioning/` (models, services, serializers) +
`src/actions/definitions/positioning.py` + `src/world/scenes/serializers.py` +
`frontend/src/scenes/components/` + `frontend/src/combat/components/`

**What ships:**

- **Abstract bases:** `PositionNodeBase` (name/kind/description) and `PositionEdgeBase`
  (`is_passable` + canonical-order validation) — `Position`/`PositionEdge` now inherit them
- **Blueprint models:** `PositionBlueprint` (GM-authored layout; `name` unique),
  `BlueprintPosition` (blueprint FK; mirrors `Position` node), `BlueprintEdge`
  (blueprint FK; mirrors `PositionEdge`)
- **RoomProfile link:** `RoomProfile.default_blueprint` (nullable FK → `PositionBlueprint`;
  `evennia_extensions`) — a room's preferred terrain layout
- **Blueprint authoring services:** `create_blueprint` / `add_blueprint_position` /
  `connect_blueprint_positions` / `remove_blueprint`
- **Staging service:** `instantiate_blueprint(blueprint, room, *, replace=False)` —
  clones a blueprint's position graph into a room's live `Position`/`PositionEdge` graph
  atomically; refuses if already staged (unless `replace=True`); refuses replace when occupied
- **Staff action:** `SetTheStageAction` (`registry_key="set_the_stage"`,
  `StaffOnlyPrerequisite`) — instantiates the room's blueprint via `ActionRef`
  with a `blueprint_id` field; surfaced via `get_player_actions` when
  `RoomProfile.default_blueprint` is set
- **Shared serializers** moved to `positioning/serializers.py`:
  `PositionSummarySerializer`, `PositionAdjacencyItemSerializer`,
  `PersonaPositionSerializer` (combat imports these)
- **Scene API:** `SceneDetailSerializer` gains `positions`, `position_adjacency`,
  `persona_positions`
- **Frontend:** `MovementActions` (shared component extracted to
  `frontend/src/combat/components/`) + `RoomPositionsPanel` (scene detail,
  `frontend/src/scenes/components/`) — renders positions, persona placement, move
  action, and staff "Set the stage" control

**Deferred to follow-up (needs `instantiate_situation()`):**

- Gated blueprint edges: `BlueprintEdge` has no `gating_challenge`; the staging service
  skips gating. Full gated-edge instantiation requires `instantiate_situation()` to mint
  `ChallengeInstance`s.

### Positioning — Dynamic Reshaping, Aerial Layer, Gated Crossings (SHIPPED — #1018)

Battlefield mutation via consequence effects, flight, chasms, and approach-based
gated-edge crossing. Builds on the Phase-1 and Blueprint (#1017) positioning base.

**Location:** `src/world/areas/positioning/` + `src/world/checks/constants.py` +
`src/world/mechanics/effect_handlers.py` + `src/world/mechanics/factories.py`

**What ships:**

- **`Position.elevation_anchor`** (self-FK, null=floor/top-level) — links each AERIAL or
  CHASM position to the ground node directly below it
- **`PositionKind.CHASM`** — a below-ground region; entering one triggers `maybe_emit_fall`
  which emits `EventName.FELL` into the reactive layer
- **Aerial layer services:**
  - `materialize_aerial_layer(room)` — idempotent: for each non-AERIAL position X, creates
    `"Above X"` (AERIAL, `elevation_anchor=X`) with a vertical edge X↔Above X; mirrors every
    ground horizontal edge as a passable, ungated aerial edge (flight bypasses all obstacles)
  - `teardown_aerial_layer(room)` — delete all AERIAL positions (cascade edges + occupancy)
    once no airborne occupants remain
  - `enter_aerial(objectdb)` — materialize layer + move to AERIAL twin + set `"aerial"`
    `ObjectProperty`
  - `leave_aerial(objectdb)` — return to `elevation_anchor` ground position, clear property,
    teardown layer when empty
  - `maybe_emit_fall(objectdb, position)` — emit `EventName.FELL` when entering a CHASM;
    returns `True` if emitted
- **`"aerial"` Property seed** — `AerialPropertyFactory` in `world/mechanics/factories.py`
  (get-or-create by name; doubles as seed and test factory)
- **Dynamic-reshaping `EffectType`s** (dispatched via `apply_resolution`):
  - `CREATE_POSITION` — carve a new position node and optionally connect + place occupant
  - `MOVE_TO_POSITION` — force-move a target; destination resolved via `PositionDestination`
  - `SEVER_EDGE` — disconnect a named edge (skips gracefully if absent)
  - `CONNECT_EDGE` — connect two named positions (idempotent)
  - `GRANT_FLIGHT` — call `enter_aerial` on the resolved target
  - `REMOVE_FLIGHT` — call `leave_aerial` on the resolved target
- **`PositionDestination`** enum (`world/checks/constants.py`): `ACTOR_POSITION` /
  `GATING_FAR_SIDE` / `NAMED` — determines how `MOVE_TO_POSITION` locates its destination
- **`ConsequenceEffect` positioning columns** — `position_name`, `position_name_b`,
  `position_kind`, `position_description`, `position_destination`,
  `position_connect_from_actor`, `position_place_occupant`
- **Gated-edge crossing via approach:** `PERSONAL` resolution mode lets one character cross a
  gated edge (the `ChallengeInstance` stays active for others); a `MOVE_TO_POSITION` /
  `GATING_FAR_SIDE` consequence on the approach pool executes `force_move_to_position` to
  the far side; gated edges surface as locked entries in the player's move list

**Built (#1228 — reactive catch + AFK-safe plummet):**

- **Reactive fall consumer** — `EventName.FELL` is consumed by a room-owned Evennia trigger
  (`install_fall_triggers` / `wire_fall_triggers`) that calls `begin_plummet`. Capability-gated
  catch: any character with a catch capability (`fly`, `teleport`, `telekinesis`, `acrobatics`,
  or any future authored `CatchCapability` row) gets a `Catch the Faller` challenge; passing ends
  the plummet immediately. The catch roster is pure data — no code change needed to add a new
  catch-capable skill. Seed functions `ensure_fall_content()` (in `plummet_content.py`) and
  `wire_fall_triggers()` (in `factories.py`) are idempotent get-or-create; they double as test
  setup and staff seed content, mirroring the `ensure_poison_content` pattern.
- **AFK-safe multi-round plummet** — `begin_plummet` / `advance_plummet` / `end_plummet` in
  `src/world/areas/positioning/plummet.py`. Each round tick calls `advance_plummet` via the
  scene-round orchestrator; the plummeting character descends one level down the
  `elevation_anchor` chain. When `anchor is None` (ground reached), `end_plummet` fires
  `process_damage_consequences` through the existing survivability pools (graded fall impact,
  not binary). Tempo is action-driven — no wall-clock advancement.
- **`PositionEdge.blocks_flight`** flag — `BooleanField(default=False)` on `PositionEdge`;
  `connect_positions(..., blocks_flight=True)` sets it. Aerial-layer traversal skips edges
  where the flag is set, enabling anti-air terrain design without capability checks in code.

### Cross-System Dependencies (not owned by combat)
- **Covenants (world.covenants)** — needs: full covenant/party model (formation, ritual, membership), covenant passive bonuses, covenant armor/thread integration, API + frontend for covenant management
- **Vitals (world.vitals)** — needs: integration with non-combat damage sources (poison, spells, exhaustion), death/unconscious state transitions from non-combat contexts (e.g., dream-walking, traps). Built (#521): VitalsPanel on the character sheet + owner/staff-gated `GET /api/vitals/<id>/` read endpoint. Built (#520 Phase 5): exhaustion — fatigue-collapse `strain_damage` now routes to real health via `apply_exhaustion_damage` → `process_damage_consequences` (shared `resolve_fatigue_collapse`), fired by the live technique cast path and by a non-cast over-capacity trigger on scene-round resolution (`tick_round_for_targets`). Built (#520 Phase 4): poison content — a `Poison` `DamageType` plus an acute staged `Poisoned` condition (per-round damage-over-time that scales with severity/stacks and progresses through stages) and a `Slow Poison` long-term variant, seeded idempotently in-code by `world.conditions.services.ensure_poison_content()` (get_or_create; no fixture or data migration). `ConditionDamageOverTime.is_long_term` splits acute (per-round) DoT from long-term/chronic DoT; the shared round-tick orchestrator `tick_round_for_targets` applies acute condition DoT to health via `process_damage_consequences`, so acute poison can wound, knock out, or kill in or out of combat. Built (#520 Phase 7): long-term capped chronic-effect tier — `batch_chronic_effect_tick()` (the daily `conditions.chronic_daily` scheduler task) advances long-term DoT through `apply_clamped_chronic_damage`, reducing health directly, clamped strictly above the knockout floor, never routing through the survivability pipeline and skipping characters in an active combat/scene round. The chronic tier can never knock out or kill (AFK-safety). Built (#520 Phase 8, closes #523): non-combat transition-matrix integration tests — `world/vitals/tests/test_transition_matrix.py` asserts that each damage source (poison tick, trap hit, exhaustion strain) drives Bleeding-Out at the death threshold and Unconscious at the knockout threshold, and that bleed-out can only advance via `tick_round_for_targets` (active-round end tick), never via the long-term chronic tier
- **Conditions** — permanent wounds/scars as ConditionTemplates with authored content

## Design Document

See `docs/plans/2026-04-05-party-combat-design.md` for the full Party Combat design.

## Notes

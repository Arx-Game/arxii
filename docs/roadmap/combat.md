# Combat

**Status:** in-progress
**Depends on:** Traits, Skills, Magic, Conditions, Mechanics, Relationships (for combo attacks)

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

### Encounter Scaling (future — GM tooling, not core combat)
Difficulty is hybrid: base from story context, adjusted by party composition. GMs mostly
pick a tier (Swarm/Mook/Elite/Boss), name it, describe it, and the system fills in
appropriate defaults based on party strength and story risk level. GMs have limited control
over exact difficulty — the system handles most of it to ensure consistency across GMs.
C-style consequence pools are better suited for abstract mission challenges (e.g., assassinate
an NPC at a bar) where concrete NPC objects aren't needed.

### Health Pool and Damage
Health is separate from fatigue — fatigue degrades effectiveness, health degrades survival.

**Health pool sources:** Stamina (slight contribution) + Path level (large) + covenant role
armor bonuses + woven magical thread protection. Magical power is the dominant factor.

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
- **Combat models:** CombatEncounter (scene + risk/stakes), CombatOpponent (with optional Persona FK for story NPCs), CombatParticipant (lightweight join table: encounter + character_sheet + covenant_role), BossPhase, ThreatPool/ThreatPoolEntry, CombatRoundAction, CombatOpponentAction, ComboDefinition, ComboSlot, ComboLearning
- **Combat services:** Encounter lifecycle (add_participant, add_opponent, begin_declaration_phase), NPC action selection from weighted threat pools, damage resolution with soak/probing/bypass, PC damage writing directly to CharacterVitals, resolution order by covenant role speed_rank, combo detection/upgrade/revert, round orchestrator (resolve_round), defensive check integration (resolve_npc_attack), boss phase transitions (check_and_advance_boss_phase)
- **Vitals system (world.vitals):** CharacterVitals is the single source of truth for character health (health, max_health), life state (CharacterStatus: ALIVE/UNCONSCIOUS/DYING/DEAD), and dying_final_round. Health thresholds, wound descriptions, health_percentage, and wound_description properties all live here. Combat reads/writes vitals directly — no syncing or denormalization
- **Covenants system (world.covenants):** CovenantRole lookup table with speed_rank, CovenantType (DURANCE/BATTLE), RoleArchetype (SWORD/SHIELD/CROWN). Combat reads covenant roles for resolution order — speed is never denormalized onto participants
- **Bulk condition application:** `bulk_apply_conditions` batches DB queries (~5 total regardless of target/condition count) for efficient multi-target condition application from NPC attacks. Combat uses this instead of per-target loops
- **Supporting systems:** Conditions app has combat-relevant fields (affects_turn_order, draws_aggro, turn_order_modifier, aggro_priority). Mechanics app has modifier collection/stacking, plus the Challenge/Situation system and action generation pipeline. Checks app has the roll resolution engine (perform_check)
- **Capability/Application system:** Properties on enemies/environments, Applications matching character Capabilities to available combat actions, ChallengeApproach with required_effect_property for fine-grained constraints. Action generation auto-surfaces what each character can do in a given combat situation
- **Magic integration:** TechniqueCapabilityGrant connects magic techniques to capabilities. TraitCapabilityDerivation connects stats to capabilities. Combos link to EffectType and Resonance from magic app
- **Survivability pipeline (world.vitals.services):** `process_damage_consequences()` is the system-agnostic entry point for damage consequences. Uses `perform_check` with scaled difficulty for knockout (below 20% health), death (at or below 0%), and permanent wound (hit > 50% max health) checks. Callable by combat, missions, traps, or any damage source
- **DEAL_DAMAGE effect handler:** Connected — `ConsequenceEffect` with `EffectType.DEAL_DAMAGE` applies damage to CharacterVitals and triggers the survivability pipeline. Works for combat, missions, traps, and challenges
- **Combat REST API:** Full endpoint set at `/api/combat/` — GM lifecycle (begin_round, resolve_round, add/remove participant, add opponent, pause), player actions (declare, ready, combo upgrade/revert, my_action, available_combos), and participation (join, flee). Covenant-scoped action visibility. Permission classes: IsEncounterGMOrStaff, IsEncounterParticipant, IsInEncounterRoom
- **Round pacing:** Timed mode (default, configurable minutes with auto-resolve), Ready mode (all players mark ready), Manual mode (GM triggers). Timer task runs every 30 seconds via game clock scheduler
- **Participation:** PCs in the room can self-join active encounters. Flee mechanic (stub — auto-succeeds, Phase 4 will add checks and covering actions)
- **Tests:** 599 tests across combat, vitals, conditions, mechanics, checks, and covenants
- **Admin:** Full Django admin with inlines for all combat, vitals, and covenant models

## What's Needed for MVP

### Party Combat (first priority) — Phase 1 complete (foundation)
Full design: `docs/plans/2026-04-05-party-combat-design.md`

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
- Vitals extraction: CharacterStatus enum and health thresholds moved to world.vitals
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

### Open Encounters (future — builds on Party Combat)
- Spontaneous combat for any number of participants, drop-in/drop-out
- Nullable covenant, participants can join/leave mid-fight
- Same combat primitives, different encounter structure

### Battle Scenes (future — separate system)
- Mass combat VP system with variations (army vs army, all PCs vs kaiju)
- Fixed rounds, victory point tracking, mass participant handling
- Risk/reward action choices per round

### Duels (future — separate system)
- Normally non-lethal PC vs PC sparring with pose integration
- Special variant: lethal 1v1 PC vs significant NPC (only symmetrical combat mode)

### Shared Future Work (combat-adjacent)
- **Combat REST API** — endpoints for encounter lifecycle, action declaration, combo upgrade, round resolution
- **Combat UI** — web-first interface for all combat modes (declaration panel, resolution display, combo prompts)
- **Encounter scaling / GM tooling** — difficulty from story context + party composition, encounter builder
- **Relationship modifier integration** — romance bonuses, rivalry intensity, party bond effects
- **Audere Majora trigger conditions** — health thresholds feeding into Audere system
- **DEAL_DAMAGE effect handler** — connect stubbed handler to combat health system
- **Combo content authoring** — staff tools for creating/testing combo definitions
- **Knockout/death roll services** — actual rolls using eligibility flags from damage resolution
- **Permanent wound application** — connect permanent_wound_eligible to ConditionTemplate instances

### Cross-System Dependencies (not owned by combat)
- **Covenants (world.covenants)** — needs: full covenant/party model (formation, ritual, membership), covenant passive bonuses, covenant armor/thread integration, API + frontend for covenant management
- **Vitals (world.vitals)** — needs: integration with non-combat damage sources (poison, spells, exhaustion), vitals display on character sheet frontend, death/unconscious state transitions from non-combat contexts (e.g., dream-walking, traps), API endpoints for vitals status
- **Conditions** — permanent wounds/scars as ConditionTemplates with authored content

## Design Document

See `docs/plans/2026-04-05-party-combat-design.md` for the full Party Combat design.

## Notes

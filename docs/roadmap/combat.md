# Combat — Status

**Status:** core party and duel combat ship end-to-end; the authored effect palette shipped (#1584,
combat-wired for battlefield shaping by #2206); the frontier is embodied combat (companions, mounts,
war) and *proving* the WIRED-UNPROVEN paths — not the round engine.

This is the combat **status map**. Per-capability tiers, the MVP bar, and sequencing live in the
[`player-capability-ledger.md`](player-capability-ledger.md) (the spine — read it first). The
scope-by-scope build record is archived in [`combat-build-history.md`](combat-build-history.md). When
this doc, the ledger, and the code disagree, the **code wins**, then the ledger.

## MVP bar (the no-improv tenet)

Anything a player should plausibly do in a fight — or any event that can happen (a war) — must have a
real system; never a GM winging it. A combat capability is "done" only when an **E2E asserts the
outcome** (a closed issue or a "SHIPPED" line is not proof). See the ledger's governing tenets.

## What's PROVEN (trust these)

- Damage technique cast at an NPC drops its health (telnet → resolve_round).
- DEFEND halves / INTERPOSE zeroes incoming damage.
- SUCCOR shelters a named ally from a round-ticked environmental hazard, in both combat and
  non-combat scene rounds (#1744, ADR-0069) — the environmental-DoT sibling of INTERPOSE.
- **Guardian reactions — best-of check selection and technique-guardian BARRIER (#2207),
  two journey tests.** Interpose's Melee-Defense twin (seeded per interpose capability,
  `interpose_content.py`) is reachable on the REAL dispatch path:
  `dispatch_capability_reaction(select_best_check_rating=True)` rates each guardian's real
  available reaction actions via `compute_check_rating` and picks the higher-rated one, never
  inventing an action — proven by a duelist-statted guardian rolling Melee Defense and a
  reflexes-statted guardian rolling Reflexes (`InterposeBestOfCheckRealPathTest`,
  `world/combat/tests/test_guardian_reactions.py`). **That test is `@tag("postgres")`** —
  `apply_condition`'s capability grant uses DISTINCT ON, so its first real gate is CI parity,
  not the local SQLite fast tier. Separately, a guardian can declare Interpose "with" a known
  protective technique (`declare_interpose(technique=...)`); the BARRIER flavor's real
  resolution (guardian's own cast check via `resolve_cast_check_type`, anima debited instead
  of fatigue, ally damage zeroed) is journey-proven (`TechniqueGuardianBarrierResolutionTest`,
  SQLite tier). See ADR-0118 for why the technique-guardian roll happens outside
  `use_technique`.
- **Redirects — away / chosen-enemy / volatile-object detonation (#2210, ADR-0124),
  SQLite tier.** A guardian's REDIRECT-flavor technique (Mirror Ward-style reflection —
  previously rejected at declaration, now the third resolved flavor alongside BARRIER
  and BLINK) declares its saved-damage destination at `declare_interpose` time:
  `redirect_opponent_target` (a `CombatOpponent`, structurally never a PC — ADR-0023) or
  `redirect_object_target` (an ObjectDB that must be "volatile" — carries an
  `ObjectProperty` whose `Property` has a `PropertyDetonation` sidecar,
  `world.mechanics.services.volatile_object_property`). At resolution,
  `saved = amount_before - payload.amount` after the shared tri-level grade routes to
  the destination — clean-enemy full amount, partial-enemy half, defeated-enemy or
  consumed/moved/position-less object degrades to "away" (the universal fallback).
  Volatile-object detonation fires `PropertyDetonation.consequence_pool` at every
  combatant positioned there (new `world.room_features.trap_services.
  fire_pool_at_characters`) then deletes the triggering `ObjectProperty` — one-shot.
  Journey-proven end-to-end (`world/combat/tests/test_redirect_resolution.py`,
  `actions/tests/test_combat_maneuvers.py::InterposeRedirectDispatchSeamTest` —
  the last one drives the real `InterposeAction.run()` seam, not just the service
  call). Telnet: `combat interpose [ally] [with <technique>] [into <destination>]`.
  Web: the Guard panel's technique picker no longer excludes `redirect`; picking one
  reveals a destination select sourced from `EncounterDetailSerializer.
  volatile_objects` + `encounter.opponents`.
- Escalation → Audere offer → accept → real power change.
- Dramatic surge (ally mortal peril / hated foe / high stakes) → provable intensity spike →
  stronger next cast; visible in the web combat panel and telnet room log (#2013).
- Multi-PC group combos (effect-type × resonance).
- **Ward your allies (#2208, ADR-0118).** Aegis Field / Mirror Ward / Phase Step each gained
  an ALLY-single (Aegis Ward, Mirror Vigil, Phase Guard — castable in or out of combat) and an
  ALLY-`FILTERED_GROUP` party-preparation variant (Aegis Communion, Mirror Communion, Phase
  Communion — out-of-combat only, consent-free per ADR-0045; party `anima_cost` is 2x the
  single variant's), reusing the existing three `ConditionTemplate` rows with no new
  ConditionTemplates/triggers/flows. Both reactive-cost paths (fire and round upkeep) now
  debit the caster (`ConditionInstance.source_character`), falling back to the bearer for
  self-cast wards, so an ally ward strains its caster rather than a free ride for the ally;
  an upkeep payer who can't afford the round cost lapses the ward. No in-combat party AoE —
  deliberately not built.
- **Rampart living barriers (#2209, epic #2040 decision 3, ADR-0125).** A position-anchored
  `Rampart` entity (`world.areas.positioning`) with a shared `integrity`/`max_integrity` pool
  covers everyone at its `Position`, faction-blind like ADR-0109's obstacles. Interception
  (`apply_rampart_interception`) chips it at the top of both damage-application seams, before
  `DAMAGE_PRE_APPLY` and ahead of personal reactives/Guardian reactions; a sustained barrage
  instead opens a WARD `Clash` bound to the Rampart (`Clash.rampart`), whose progress syncs
  the same integrity pool. Four authored elemental profiles (Stone/seal-edges, Wind/missile-
  ward, Fire/melee-retaliation, Thorn/grasping) ship via the effect palette
  (`ensure_rampart_content`), each with its own "Raise Rampart" technique. Crack-state
  (INTACT/CRACKED/CRUMBLING) renders on the tactical map as a colored ring
  (`PositionMapNode`, #2209).
- **On-use items as a round action (#2023/#2120).** `combat use <item> [on <target>]`
  (telnet) and `POST /api/combat/{pk}/use_item/` (web) both declare a USE_ITEM
  `CombatRoundAction` through the shared `combat_use` REGISTRY action; round resolution
  dispatches the real `UseItemAction` with the declared target threaded through (a healing
  potion declared on an ally provably lands on the ally, not the user — the #2120
  target-forwarding fix) and decrements the item charge (journey tests in
  `world/combat/tests/test_combat_maneuvers_e2e.py` + `test_use_item_maneuver.py`).
- **Ready-mode early resolution (#2120).** In `PaceMode.READY`, the round resolves the
  moment every ACTIVE participant is ready (`maybe_resolve_on_ready`, wired into
  `combat ready` / the web `ready` endpoint via `ReadyAction`); a lone ready participant
  provably does not trigger it (`world/combat/tests/test_pace_mode_ready.py`). TIMED keeps
  the game-clock sweep; MANUAL keeps GM-only resolution.
- **Tactical placement, end-to-end (#2005).** Voluntary `take_position` (entry onto the
  position graph), GM `gm_place_in_position` (unchecked staging teleport), and positioned
  opponent spawn (`add_opponent(..., position=...)`) close the last placement gaps —
  ADJACENT-reach technique gating now binds against a real, populated position graph rather
  than defaulting everyone to the same spot (journey test in `world/combat/tests/
  test_declare_reach_gate.py`). Full telnet parity: `position` / `position <name>`
  (`CmdPosition`) lists/takes/moves the same way the web position panel does.
- **Technique-driven combat entrance (#2183, ADR-0113).** A hostile technique cast made
  as an entrance (`enter <technique>=<target>`) seeds/feeds the encounter exactly like a
  normal declared hostile cast, additionally stamping `CombatRoundAction.from_entrance`
  so round resolution can fire the GM-facing Dramatic Moment Suggestion check once the
  real success level is known (`_maybe_suggest_entrance_dramatic_moment`,
  `world/combat/services.py`; journey test:
  `world/scenes/tests/test_entrance_cast_threading.py`
  ::`test_accepted_hostile_entrance_declaration_marked_from_entrance`). A *benign*
  entrance cast that lands on an already-embattled ally seats the caster into the fight
  (`seed_or_feed_encounter_from_benign_intervention`) with no opponent row and no stakes
  lock — the cast already resolved standalone; this only adds the intervener to the
  scene's live encounter. See [magic.md](../systems/magic.md#technique-entrance-2183).
- **Tactical encounter map — spatial rendering (#2006).** The position graph (#2005) is
  now rendered, not just listed: `TacticalMap` (`frontend/src/areas/components/`), a
  read-only `@xyflow/react` canvas with occupant avatars per node, edges styled by
  passability/gating, and click-to-move via the existing `move_to_position`/
  `take_position` actions. `SceneTacticalMap` replaced the old `RoomPositionsPanel`
  text-list UI on the scene page; `CombatTacticalMap` mounts as a "Map" tab in
  `CombatRail`'s right rail (default tab stays "Your Turn") — `CombatRail` renders
  in-scene on `/scenes/:id` (#2197; the dedicated `CombatScenePage` route is gone).
  Both `SceneDetail`
  and `EncounterDetail` now serve the full node+edge graph (`position_nodes`/
  `position_edges`, via the new `position_graph(room)` service) — unlike the
  ADJACENT-reach-only `position_adjacency`, this keeps impassable/gated edges so
  obstacles are visible. See [areas.md](../systems/areas.md#frontend-built--wired).
- **Cast-position targeting for the position-consuming effect palette (#2206).**
  Barricade/Phase Jump/Force Grip previously embedded a placeholder
  `destination_position_id=0` at seed time (no runtime destination selection); a player
  now declares a real `areas.Position` (single point for Phase Jump/Force Grip, an
  endpoint pair for Barricade) at cast-declaration time. `resolve_cast_position_params`
  validates room-scope + technique reach; the three FKs (`cast_destination`/
  `cast_position_a`/`cast_position_b`) persist on the `CombatRoundAction` and are
  forwarded through `CombatTechniqueResolver._apply_conditions` into the shared
  `apply_technique_conditions` seam. Root-cause fix in the conditions layer: position ids
  are now stamped onto the `ConditionInstance` (`_stamp_cast_positions`) **before**
  `CONDITION_APPLIED` fires, replacing a post-hoc helper that raced same-event reactive
  handlers — this also fixed the previously-broken non-combat live path. Frontend: a
  reach-greyed, shape-aware Positions picker in `ActionDeclarationCard` plus map-click
  picking on the tactical map. Telnet needed no changes — #2019's `position=` grammar now
  actually reaches validation/persistence in combat. Journey-tested at the round seam
  (`world/combat/tests/test_cast_position_declaration.py`: foreign-room rejection +
  full declare → resolve → condition → sealed-edge for Barricade). Non-combat web casting
  still has no position picker (telnet-only there). See
  [magic.md](../systems/magic.md) (Effect Palette) and [INDEX.md](../systems/INDEX.md)
  (Combat § "Cast-position targeting") for the full wiring.
- **3-PC party vs. a factory boss — the full break-bar/phase/enrage journey (#2095).**
  One `resolve_round`-driven test proves the whole boss-anatomy chain (#2016, ADR-0102)
  in order: solo attacks fully soaked while the guard is unbroken → a landed combo chips
  the break bar to 0 and opens a vulnerability window (soak bypassed) → crossing a
  phase's health trigger while still in that window transitions the boss and spawns its
  authored reinforcements → a later phase transition stamps an enraged
  `damage_multiplier` (proven via a real before/after NPC-damage comparison, not just a
  field read) → the break bar re-breaks in the final phase, opening a second window →
  the party finishes the boss off with `vulnerability_rounds_remaining > 0` still true at
  the kill. Also proves enemy-NPC condition application (`ThreatPoolEntry
  .conditions_applied` landing on the attacked PC — see the WIRED-UNPROVEN entry below
  for why that's now PROVEN, not the reverse "onto the boss" direction). Scenario
  composed by `BossFightScenarioFactory` (`world/combat/factories.py`); journey test:
  `src/integration_tests/test_boss_fight_journey.py`.
- **Boss-fight structure: diversity-weighted break accrual, lieutenant gate, pacing floor,
  break celebration (#2642, ADR-0155).** Extends #2016/#2095's break-bar anatomy so a boss
  fight reads as suppress-the-court → break-the-wall → the earned one-shot without anyone
  authoring acts. `BreakBarContribution` persists one row per qualifying feed (DAMAGE / COMBO
  / HOLD — a PC-side LOCK-clash win / DEBUFF — a new behavior-altering condition on the boss /
  SUPPRESSION — a reinforcing lieutenant newly suppressed), replacing the retired flat
  per-actor chip; `CombatOpponent.reinforces` (self-FK) marks a lieutenant, whose active
  presence proportionally slows depletion (never a hard block); `minimum_break_bar_threshold()`
  clamps a boss's authored threshold to the Soulfray staging depth so the anima → Soulfray →
  audere arc has room to play out; BOSS-tier opponents resist a decisive Parley calm by one
  success-level step; the break broadcasts a celebration naming every distinct contributor.
- **Combat offense standalone-cast flavor catalog (#1995).** A PHYSICAL technique's
  standalone cast (not a combat round) can pick a curated consequence-pool flavor
  ("Brutal"/"Precise") off the "Melee Attack" `ActionTemplate`, mirroring magic's
  #1320 catalog — see `docs/systems/magic.md`. Deliberately **not** wired into combat
  ROUND resolution, which never reads `ActionTemplate.consequence_pool` (ADR-0130).
- **Wind-as-mechanic combat consumer (#1555, ADR-0129).** The WIND exposure axis
  (`world.locations.services.felt_exposure`, `StatKey.WIND`, provider #1522) gets its combat
  reader: `wind_penalty(felt) -> int` (`world/combat/constants.py`) bands felt WIND —
  CALM (<15) → 0, BREEZY (15-39) → -5, WINDY (40-69) → -10, GALE (70+) → -20 — into a
  SCENE-sourced "Wind" `ModifierContribution`. Missile-classified attacks only: PC offense
  (`CombatTechniqueResolver._roll_check`) applies the penalty when the attacker's strongest
  equipped weapon is RANGED/THROWN (the same `_select_equipped_weapon` pick the damage path
  uses); melee/lance skip the `felt_exposure` lookup entirely. Symmetric NPC side
  (`resolve_npc_attack`) adds the same-magnitude positive bonus to the PC's defense roll when
  the attacking `ThreatPoolEntry.delivery` is MISSILE; flat `base_damage` entries with no
  defense roll are untouched. See `docs/systems/INDEX.md`'s "Combat" section for the full
  wiring.

- **Death & unconsciousness core slice (#2287, ADR-0131).** The survivability pipeline's
  content + player experience: the `survivability` seed cluster makes knockout/death actually
  fire in production (knockout/default-death/default-wound pools, Bleeding Out staged authoring,
  Unconscious capability-zeroing, foundational awareness/movement/limb_use CapabilityTypes —
  all previously test-factory-only, so combat could never KO or kill on a real DB); the wake
  arc (`attempt_wake` — per-round Endurance checks easing over time/healing, guaranteed-wake
  deadline, dreamside perception in the liminal dream room until #2290's dream realm); the
  death moment (condolence delivery + death-scene stamp); the ghost interlude
  (dead-action whitelist, scene/IC-day emit window); the retire off-ramp (player/staff/auto);
  and capped death-kudos. Unit/service-tier proven (vitals/actions suites); no combat journey
  test yet — a KO-to-wake / death-to-retire journey is fair game for the journeys list.

## WIRED-UNPROVEN (treat as not-done — write the journey test, fix what it exposes)

- Thread-pull final outcome in combat. (Combo full journey proven in #2017; enemy-NPC
  condition application — the other half of this bullet's old wording — is now proven
  by the #2095 boss-fight journey above: `ThreatPoolEntry.conditions_applied` lands the
  condition on the attacked PC, never on the attacking NPC/boss itself.)
- **Guardian-reaction surfaces beyond the two #2207 journey tests above.** Wired but
  not journey-proven: the technique-guardian BLINK flavor's clean-success ward
  relocation (`force_move_to_position` to the guardian's own position —
  `_try_technique_interpose`); the ALLY-opponent guard path
  (`_try_interpose_for_opponent` in `apply_damage_to_opponent`, shielding a
  summon — ANY-ALLY declarations only, no named-ally FK to a `CombatOpponent`
  yet); telnet `combat interpose [ally] with <technique>` (parses correctly per
  unit coverage, but no end-to-end telnet journey test); and the web Guard panel
  (`YourTurn`'s ward + technique selects) — typechecked/linted, no e2e run
  (Playwright is blocked in this devcontainer for every spec, not specific to
  this feature).

## The combat gaps that define MVP (see the ledger's DO pillar)

- **Effect palette** — SHIPPED (#1584: summon, reflect, incorporeal, sink, telekinesis, teleport,
  obstacle, force-field; combat position-targeting #2206; ally/party ward variants #2208; Rampart
  living barriers #2209). The
  three position-consuming effects (telekinesis/teleport/obstacle → Force Grip/Phase Jump/Barricade)
  have real runtime destination selection for combat (#2206) — the non-combat web cast path still
  lacks a position picker. Remaining per-effect follow-ups live in the capability ledger, not here.
- **Charm / switch-sides** an enemy NPC; **negotiate / parley** an NPC down (built in this PR,
  #1590/#1591, ADR-0058); **dispel** a condition.
- **Companions / pets / summons** with breath weapons & ordered abilities.
- **Roles grant techniques** via the one specialization engine (ADR-0055; reverses bonuses-only).
- **War / battle system** — spine landed (#1592): `Battle` (1:1 Scene extension),
  abstract unit attrition + VP accumulation, `BattleRoundContext` seam, GM + player REGISTRY
  actions, `CmdBattle` telnet namespace, E2E `test_battle_telnet_e2e.py`. Peril/rescue +
  AFK override shipped (#1733). Resources/units/terrain/tactics + type-matchups shipped
  (#1711). Command hierarchy + the Champion shipped (#1710). Campaign-stakes propagation
  (battle outcome → Story beat resolution) shipped (#1785); win-gated Legend (battle
  outcome → `societies.LegendEntry`, a separate `world.battles.legend_wiring` seam —
  25/12 decisive/marginal victory event for the winning side, 15-value standout deeds
  for either side) shipped (#2184, ADR-0122). Battle-flow actions (rout/rally/repel/hold, second
  BattleUnit.morale resource, BattlePlace.controlled_by objective) shipped (#1712). Siege
  warfare: Fortification objectives + BREACH/FORTIFY + persistent
  Building.fortification_level investment (#1713). Naval-ship vertical slice shipped
  (#1714): `BattleVehicle` (unit+place pair), REPOSITION declaration gated on vehicle
  commander, overlap-gated cross-vehicle targeting (`places_overlap` — the boarding
  gate), hull-breach/living-mount-defeat ejection + drowning/falling hazard. The
  persistent half shipped (#1832, ADR-0086): `ShipDetails` (a per-kind `Building`
  extension — hull IS `fortification_level`) with commission/upgrade/repair Projects
  and ship-as-sanctum bonuses, `materialize_ship_as_battle_vehicle` snapshotting into
  #1714's `BattleVehicle` for one `Battle`, and a battle-conclusion hook
  (`apply_ship_battle_outcome`) writing `needs_repair` back onto the persistent ship
  when its hull is breached — see [ships.md](../systems/ships.md). Airship/
  dragon/kraken remain data variants (`VehicleKind`) pending their own end-to-end
  pass — no dedicated content or persistent-ship equivalent yet. REPOSITION's
  movement resolution and telnet subcommand both shipped with #2007 (the
  resolution logic had actually been built since #1714 — only the
  Action-layer/telnet wiring was missing).
  Live strategic battle map shipped (#2009): read-only REST aggregate
  (`GET /api/battles/`, `GET /api/battles/<pk>/`, scene-visibility-gated) + a
  slim `BATTLE_STATE` WS ping (`{battle_id, round_number}`, sent post-commit
  on round transitions/conclusion) driving a React Flow map page at
  `/scenes/:id/battle` — see [battles.md](../systems/battles.md#web-surface-2009).
  Deferred: a post-conclusion battle writeup page (#1735), which should reuse
  `BattleDetailSerializer`'s aggregate shape rather than authoring a second one.
  GM battle staging shipped (#2010, ADR-0111): the setup layer had **no** mutation
  path at all before this (a Battle could only exist via admin/tests/factories). A
  JUNIOR-trust GM now stands one up from an admin-authored catalog —
  `BattleMapBlueprint`/`BlueprintBattlePlace`/`BlueprintFortification` and
  `BattleUnitTemplate`/`BattleUnitTemplateCapability` — via `create_battle` /
  `stage_battle_map` / `spawn_battle_units` / `enlist_battle_participant` /
  `browse_battle_catalog` (`world.battles.staging`), the `battle create/stage/spawn/
  enlist/maps/units` telnet subverbs, a read-only catalog REST API
  (`world.gm.permissions.HasGMTrust`, new JUNIOR-tier DRF permission class), and a
  minimal `StagingPanel` on the `/scenes/:id/battle` map page. A starter catalog (2
  blueprints, 3 unit templates) ships via the "battles" seed cluster — see
  [battles.md](../systems/battles.md#staging-2010).
  Battle movement shipped (#2007): `BattleActionKind.MOVE` — self-move,
  commander-ordered unit move (reuses #1710's command-tier gate), and withdrawal —
  moves a `BattleParticipant`/`BattleUnit` between existing fronts via multi-round,
  MOVEMENT-capability-bounded transit; `BattlePlace.movement_cost` consumed for the
  first time as check-difficulty. `WITHDRAWN` (`BattleParticipantStatus`) wired for
  the first time. Web click-to-move on the #2009 strategic map deferred — not yet
  scoped.
  Fleet/swarm math shipped (#1841): `BattleUnit.individual_count` (a #1794 data
  point, previously inert) now drives a banded flat check penalty against the swarm
  (`swarm_strike_modifier`, negative like ELITE quality — numbers resist breaking)
  folded into the modifier stack, plus proportional body
  loss off `individual_count` on STRIKE/ROUT attrition (`_apply_swarm_losses`) —
  see [battles.md](../systems/battles.md#swarm-math-1841) and ADR-0123. Capital
  ships (#1714/#1832) stay on their own per-hull Fortification track — swarm math
  is for hordes/packs/flocks, not vessels.
- Mounts / charging shipped at personal scale (#1843): mount/dismount riding
  companions (`world.companions.services.mount_companion`/`dismount_companion`,
  a seeded verb-gating "Mounted" condition, no passive bonuses), `CombatManeuver
  .CHARGE` (force-move onto a distant opponent then attack, with flat
  check/damage bonuses doubled for a `GearArchetype.LANCE`), and `CombatManeuver
  .JOUST` (2-participant DUEL-only mounted lance pass, graded by opposed
  success_level margin into unhorse/lesser-hit/tie bands). Flying, and any
  battle-scale (war) mounted/cavalry mechanics, remain P2/unscoped. Ranged /
  archery enforcement shipped (#2011): REACH_N multi-hop reach, offensive-only elevation bonus, attack-cover via PositionShelter.applies_to_attacks.

## Reserved term: "clash"

"Clash" is reserved for the shipped opposed-magic contest (two combatants pouring anima to overpower
each other). Do **not** reuse the word for any other concept (models, vars, docs). For
opposing-affinity / environmental rejection use "backfire" / "rejection" / "dissonance".

## Design principles (condensed; ADRs hold the why)

- Players vs. the Bad Guys — **no PvP killing** (ADR-0023); asymmetrical PvE, NPCs have no sheets (ADR-0038).
- One round framework, three modes (ADR-0002); one focused + up to two secondary actions (ADR-0003);
  tempo is action-driven, AFK-safe (ADR-0004).
- **Enforced** impossible to solo — combos and covenant roles are fundamental; built for heroic team-up
  arcs that climax in Audere Majora. Enforced by the boss break bar (#2016, ADR-0102): a secondary
  health pool damaged only by team play (combos + distinct-PC distinct-effect-type hits).
  The combo invariant (#2051, ADR-0107) hard-blocks <2-slot combos at save time and runtime;
  BOSS-tier opponents with legend-paying aftermath require an authored `wall_breaker_combo` FK.
  **Vows as combat roles** (#2022, ADR-0108, re-scoped by ADR-0149): a character's engaged
  `CovenantRole` drives combat power through a four-layer model. **Layer 1** (#2529, shipped):
  the role is a SWORD/SHIELD/CROWN weighted blend, not a single archetype pick, driving an
  always-on baseline cast power term plus **stat power** scaling with the COVENANT_ROLE thread
  level (`VowStatScaling`, unchanged); role-granted **specialized techniques** that resolve
  are unaffected. **Layer 2** (#2443, shipped): per-vow technique specialty —
  `CovenantRoleTechniqueSpecialty` rewards casts matching a role's specialized
  `TechniqueFunction`s (a shared, code-defined vocabulary also consumed by Layer 4) via the
  always-on `covenant_role_specialty_power_term`; unlike the blend/action-scaling anchor-only
  rule, sub-role rows ADD to the parent's. **Layer 3** (#2533, shipped): each engaged vow
  authors a `DefenseStyle` (GEAR_SOAK/EVASION/BARRIER) plus a
  `CovenantRoleDefenseProfile.gear_additive_tenths` fraction — `gear_additive_fraction(character)`
  (MAX fraction across engaged roles) scales the compatible bucket in
  `apply_equipped_armor_soak`, once, so a vow whose defense style isn't gear can dial down how
  much armor stacks on top of it. `VowGearScaling` (the never-seeded per-archetype gear
  multiplier short-circuited to 0 by #2529) is removed — subsumed by the single authored
  fraction. **Layer 4** (#2536, ADR-0151/0152/0153, all three slices shipped — Layer 4, and the
  four-layer model, is now complete): the deterministic-situational-perk machinery — "the point
  of vows", consuming the same `TechniqueFunction` vocabulary Layer 2 introduced; its first perk
  set must give every `DefenseStyle` a distinct shine-situation per the 2026-07-20 niche ruling.
  Slice 1: a code-defined `Situation` library + evaluator registry (`world.covenants.perks`),
  the `VowSituationalPerk`/`VowSituationalPerkSituation`/`VowSituationalPerkRung` authoring
  models (beneficiary SELF/COVENANT_ALLIES/WHOLE_GROUP, no negative magnitudes —
  structural), `POWER_BONUS` (`vow_situational_power_term`) and `CHECK_BONUS`
  (`perform_check`'s `situation_ctx`) delivery, and the dual-dispatch presentation
  contract (a firing perk announces as a loud line in BOTH the web client and bare
  telnet — WS interaction payload + a direct `location.msg_contents()` text companion). Slice 2:
  `TIER_FLOOR`/`BOTCH_IMMUNITY` outcome guarantees — a character can't botch at their
  specialization; absolute, never thread-scaled. Slice 3: three `VowSituationalPerk` scope
  columns (mission/battle-action-kind) narrowing WHEN a fired perk applies; `situation_ctx`
  threaded into every mission check and Battle warfare roll; five new `Situation` values
  (`CHAMPION_DUEL`, `COMBAT_OPENED_FROM_PARLEY`, `AMBUSH_UNDERWAY`, `ALLY_INTERCEPTED_FOR_ME`,
  `ATTACKER_AFFINITY`); the defense-side seam (`resolve_npc_attack` threads `SituationContext
  .attacker`, making perks live on defense rolls for the first time); and dormant-vow messaging
  (ruling 2's "loud OFF state" — a disengaged vow that would have answered announces so,
  holder-only, never the room). #2623 (ADR-0154) follow-up parameterizes the situation library:
  `SituationRequirementMixin`'s four typed columns (`threshold_percent`/`count_threshold`/
  `affinity`/`origin_side`) on both `VowSituationalPerkSituation` and `VowSituationalPerkRung`,
  a per-situation `SITUATION_PARAM_SPECS` allowed/required contract, `ATTACKER_AFFINITY`
  authorable against any `AffinityType` axis (was Abyssal-only), and
  `CombatEncounter.initiated_by_pc_side` recording who sprang a fight for `origin_side`-gated
  ambush/parley perks. When the vow dims (#2051), the engaged flag drops and every
  layer's contribution returns to 0 — which is why soloing legend content is lethal.
- Magic is predominant; relationship bonuses matter; **difficulty scales on party size + average level
  only** (ADR-0037); combat merits Legend, never XP (ADR-0036).

## Deeper detail & history

- Capability tiers + MVP slate: [`player-capability-ledger.md`](player-capability-ledger.md)
- Build history (the old combat.md): [`combat-build-history.md`](combat-build-history.md)
- Decisions: [`../adr/README.md`](../adr/README.md) (esp. 0002–0004, 0023, 0036–0040, 0046, 0055, 0057)

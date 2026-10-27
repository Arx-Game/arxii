# Combat glossary

**CombatEncounter**:
The top-level container for one fight — an `AbstractRound` subclass carrying its required scene, room, encounter type, risk level, stakes, and typed outcome. It owns the participants, opponents, clashes, and per-round action ledger.
_Avoid_: battle, fight (as a model name), combat session

**CombatParticipant**:
A PC's enrolment in a `CombatEncounter` (one per character per encounter), tracking status (active/fled/removed), covenant role, and the character's per-round strain budget.
_Avoid_: combatant, fighter, player (for the PC's encounter row)

**CombatOpponent**:
An NPC entity in a `CombatEncounter`, defined by its `OpponentTier`, health/soak/probing stats, threat pool, and (for bosses) phases. The NPC analogue of a `CombatParticipant`.
_Avoid_: enemy, monster, mob, NPC participant

**Maneuver**:
A special non-technique declaration a PC can make for a round (`CombatManeuver`: FLEE, COVER, YIELD, INTERPOSE, SUCCOR, RALLY, DEMORALIZE, TAUNT, PARLEY, CHARGE, JOUST) — a verb that is neither a technique cast nor a clash commit. Each is a real Action on the shared dispatch seam.
_Avoid_: special move, stance, command

**Charge** (#1843):
The CHARGE maneuver — a mounted PC (see `world/companions/AGENT_GLOSSARY.md`'s Mounted entry) closes distance to a declared opponent >= 1 hop away, then attacks. Resolution force-moves the rider onto the opponent's position and falls through to the normal weapon-attack pipeline; `CHARGE_CHECK_BONUS`/`CHARGE_DAMAGE_BONUS` (doubled for an equipped Lance) fold into the existing check-modifier/damage-budget seams — never a bespoke bonus path. Requires Mounted; declaring it unmounted or against an already-in-reach target is rejected.
_Avoid_: rush, gap-close, sprint attack

**Joust** (#1843):
The JOUST maneuver — a mounted, Lance-armed opposed pass between exactly two Mounted+Lance-equipped duelists in a DUEL encounter. One opposed check per side, graded by the `success_level` gap: a decisive gap unhorses the loser (double Lance damage + Unhorsed + a forced dismount), a narrow gap deals single Lance damage without unhorsing, a tie jars both with no damage. Not declarable outside a 2-participant DUEL, and not declarable unless both sides already hold Mounted + a Lance.
_Avoid_: tilt (period term, not used in code/UI), lance charge (that's Charge, above)

**Unhorsed** (#1843):
The seeded `ConditionTemplate` applied to a JOUST's decisive-margin loser, which force-dismounts them (`world.companions.services.dismount_companion`, called directly by the resolver — no reactive trigger needed).
_Avoid_: dismounted (that's the state after Unhorsed resolves, not the condition's own name), thrown

**Morale**:
A first-class depletable resolve pool on `CombatOpponent` (#2015), mirroring war-scale `BattleUnit.morale`. The derived state (STEADY/FALTER/BREAK) is read via `morale_state_for` - never stored. Falter weakens NPC output in `select_npc_actions`; Break sets `OpponentStatus.FLED`. Mindless opponents (`OpponentTierTemplate.has_morale=False`) resist morale checks with a flat difficulty modifier - not an immunity; a powerful enough roll breaks through (Arx's "power can do the impossible" tenet). A technique can also shake the enemies it lands on by its own **technique morale effect** (#4619): after the cast's damage, each enemy opponent it resolves on loses the row's amount, a mindless tier takes `SpectacleConfig.mindless_percent` of it, and allies, charmed enemies and fled or defeated opponents are skipped. See the magic glossary.
_Avoid_: willpower, resolve (as a field name — `morale` is the canonical column)

**Rally**:
The social-combat maneuver by which a PC inspires an ally by rolling presence + Performance + Oratory to apply a short-lived `Inspired` buff, and on a great success restoring morale to ally-side summon opponents. A benefit, so consent-free (ADR-0024). Whatever the roll, the ally then gets a **Rolled surge** (`RALLIED`) banded by the Rally roll's outcome (#4737). Rally is the only encouragement verb built; implore and challenge are not.
_Avoid_: inspire (as the maneuver name), buff, motivate

**Demoralize**:
The social-combat maneuver by which a PC breaks an opponent's nerve — rolling presence + Persuasion + Intimidation against the target's Composure to deplete morale. Mindless foes resist but are not immune. Targets NPCs only.
_Avoid_: intimidate (that name is the CheckType), frighten, cow

**Taunt**:
The social-combat maneuver by which a PC draws an NPC's aggro by rolling wits + Persuasion + Intimidation to accumulate threat on the existing `ThreatRecord` seam, biasing the NPC's target selection toward the taunter next round. Aimed at another player character it is instead one roll, the target's: the **Taunt Potency** is the taunter's check rating for the Taunt check type (no dice, nothing spent), the target rolls the tuned check (Composure) against it and gets a **Rolled surge** (`TAUNT_RECEIVED`) (#4737).
_Avoid_: mock, aggro (colloquial). Not **Provoke** (below): Taunt biases an NPC's choice through threat, Provoke removes the choice.

**Provoke** (#4584):
A condition with `ConditionTemplate.forces_attack_on_source` on an NPC opponent: it attacks only the condition's source (`source_character`), from the round after the condition lands (the hard form of Taunt's soft threat bias). An active engagement lock wins; a source who is down, untargetable or out of the fight leaves the opponent choosing as normal; charmed, turned and summoned opponents ignore it. Read by `select_npc_actions` through `provoking_source_by_target`.
_Avoid_: taunt (the soft, threat-based maneuver), aggro, lock (an engagement lock is a different, duel-style hold)

**Mark** (`CombatMark`, #2664, player surface #4603):
A participant's pointer at one opponent for this round, laid with `combat mark <opp>` or the opponent menu's "Mark". It gives no bonus by itself; it pays off only for covenant-mates whose vow perks read `TARGET_IS_MARKED_BY_ALLY`. A free act: it uses none of the marker's round action. One per participant per round; marking again moves it.
_Avoid_: target lock, tag, focus. Not an **EngagementLock** (a duel-style hold that narrows an NPC's targeting).

**Parley**:
The social-combat maneuver by which a PC talks a foe down mid-fight — rolling charm + Persuasion + Seduction against the target's Composure to apply a disposition delta (via `apply_social_disposition_delta`), calm the opponent on a decisive success, or yield a broken foe on a critical success. Gated: the opponent must be faltering/broken or the PC must hold sufficient standing. Even mindless targets can be parleyed with — a breakthrough grants a fleeting mind (Sharlotte charming a lake).
_Avoid_: negotiate, bargain, persuade (that name is the CheckType)

**Yield**:
The maneuver by which a PC concedes — in a duel the yielding PC loses immediately. PvP is structurally non-lethal (yield / knockout), so yielding ends the contest without injury or death.
_Avoid_: surrender, forfeit, submit, defeat

**Interpose**:
The maneuver by which a PC stands ready to step in front of an attack aimed at an ally and intercept it (a clean block). It costs fatigue only on the round it actually fires; an armed-but-never-triggered interpose costs nothing. See `world/scenes/AGENT_GLOSSARY.md`'s Sudden Harm entry for the out-of-combat sibling, which arms via a bootstrapped scene round instead of a `CombatRoundAction`. Interpose is the **mundane case** of the more general Guardian reaction (below): a plain `declare_interpose(technique=None)` rolls best-of Reflexes/Melee Defense instead of a declared protective technique.
_Avoid_: block, guard (for a declared Interpose; a condition-made guard is a **Standing guard**, below), intercept, bodyguard

**Guardian reaction** (#2207):
The declared protect-with-technique reaction a PC arms via `declare_interpose(participant, ally=None, technique=None)`. Two mechanically distinct resolution branches share the one declaration field (`CombatRoundAction.focused_action`, reused rather than adding a parallel column):
- **Mundane** (`technique=None`, Interpose's original shape): dispatches through `world.mechanics.reactions.dispatch_capability_reaction(select_best_check_rating=True)`, which picks the higher-rated of the guardian's *real* available reaction approaches (Reflexes vs. Melee Defense, via `compute_check_rating`) — deterministic, zero extra rolls, never inventing an action outside `get_available_actions`'s output (ADR-0032). Costs fatigue on fire.
- **Technique-guardian** (`technique=<a known, learned Technique classifying to a protective flavor>`): resolved by `world.combat.services._try_technique_interpose`, which rolls the guardian's own cast check (`resolve_cast_check`) instead of a capability-reaction challenge, and pays a flat `ConditionTemplate.reactive_anima_cost` (fizzle if unaffordable: no roll, no charge, narrated to the guardian and the room, #3574) instead of fatigue. See ADR-0118 for why this rolls outside `use_technique`. Grading (clean/partial/fail) is shared with the mundane path via `_grade_interpose_damage`; a clean BLINK-flavored block relocates the ward to the guardian's position; a REDIRECT-flavored block sends the saved amount to the declared destination (see **Redirect**, below).

`world.magic.services.targeting.protective_flavor(technique)` classifies a technique's reactive-trigger handler into `barrier` (absorb_pool) / `blink` (blink_dodge) / `redirect` (reflect_damage) by walking its authored condition→reactive-trigger→flow data — no new authored field. A guardian can also shield an ALLY-allegiance `CombatOpponent` (a summon) — but only via the *any-ally* (`ally=None`) declaration, since `focused_ally_target` FKs `CombatParticipant` and cannot name a `CombatOpponent` directly (a named-ally guard of a summon is a follow-up).
_Avoid_: guardian ward, protect action

**Standing guard** (#4584, ADR-4584-A):
A condition with `ConditionTemplate.source_guards_bearer`: its source (`source_character`) tries the mundane interpose on every hit on the bearer without declaring anything, from the round after the condition lands. She still takes her own turn. It counts as one of her reactions this round (a harder roll each time, #4676) and against the hit's answer cap (`ABSORPTION_CAP_PER_MOMENT`) and pays interpose fatigue at very low effort. A guardian who declared any Interpose that round acts only through her declaration; a guard cast on its own bearer never interposes; PC wards in combat only. Read by `_try_interpose` through `guardians_by_target`.
_Avoid_: bodyguard maneuver, auto-interpose

**Strike-back** (#4584):
The `ConditionTemplate.retaliation_damage` / `retaliation_damage_type` / `retaliation_condition` fields, read by `strike_back` directly where combat damage lands on a PC bearer (`_answer_with_strike_backs`): the NPC that dealt the blow takes the damage and/or is laid the condition with the ward's source as its source. Never strikes a PC. Not a flow or trigger, and a success is not narrated (only a fizzle is).
_Avoid_: thorns, reflect (`reflect_damage` bounces the blow's own amount before it lands; strike-back adds fixed damage after)

**Redirect** (#2210):
A REDIRECT-flavor Guardian reaction's saved-damage destination, declared at
`declare_interpose` time (ADR-0032/0122) via `CombatRoundAction.redirect_opponent_target`
(FK `CombatOpponent` — structurally never a PC, ADR-0023) or `redirect_object_target`
(FK ObjectDB, must be **Volatile** — see `world/mechanics/AGENT_GLOSSARY.md`). Both null
(or the declared destination no longer valid at resolution — the enemy defeated, the
object moved or already detonated) means "away," the universal fallback: the saved
amount (`amount_before - payload.amount` after grading) simply vanishes with a
deflection broadcast. A chosen-enemy redirect applies the saved amount via
`apply_damage_to_opponent(..., bypass_pre_apply=True)` (the ADR-0060 loop guard); a
volatile-object redirect fires the object's `PropertyDetonation.consequence_pool` at
every combatant positioned there, then deletes the triggering `ObjectProperty` —
one-shot, never reusable.
_Avoid_: reflect target, bounce destination, deflection target

**Succor**:
The maneuver by which a PC shelters a specific ally from a round-ticked environmental hazard (sunlight, poison gas) this round — the environmental-DoT sibling of Interpose (which blocks an incoming attack, not a lingering hazard). Always names a specific ally; there is no "any ally" path like Interpose has, since environmental shelter is "I'm sheltering THIS person," not "I'll block whichever hazard lands on someone." Resolves through the same graded capability-check spine as Interpose.
_Avoid_: shelter (as the maneuver name), cover, shield, protect

**Wind-up** (#2637, ADR-0161):
A telegraphed NPC attack: `ThreatPoolEntry.windup_rounds > 0` commits to a `PendingOpponentAttack`
at declaration instead of a same-round `CombatOpponentAction`, telegraphs on both clients, then
matures `windup_rounds` rounds later through the ordinary NPC-attack pipeline. Pre-armed, not a
mid-round interrupt — the same declaration-time-commitment shape Interpose uses, mirrored for the
NPC side. See `world/covenants/AGENT_GLOSSARY.md`'s Wind-up / Interception (wind-up) / Callout
(wind-up) entries for the interception rider and the auto-callout role flag.
_Avoid_: charge-up, cast time (a caster's own resolution delay, not an authored multi-round threat).

**Reaction Economy** (#2639, ADR-0161):
`CombatParticipant.reactions_used` counts a participant's reactions this round (dodges,
guards, catches; reset each `begin_declaration_phase`). It has no cap since #4676: each one
makes her next reaction's roll harder by `MovementConfig.reaction_difficulty_step`.
`DamagePreApplyPayload.answers_consumed` vs `ABSORPTION_CAP_PER_MOMENT` (2, per landing
hit, regardless of who fired) still caps the shared interpose fire seam. Standing defenses
(absorb/reflect/blink/strike-back, their own `reactive_anima_cost`, ADR-0060) sit outside both
budgets; a **Standing guard** does not (ADR-4584-A).
A declined guardian is told privately why (#3574, ADR-0271); the table is not.
_Avoid_: reaction points, action economy (this is specifically the interpose-family reaction
budget, not a general action-point system).

**Dodge** (#4676, ADR-4676):
A character's automatic reaction to an NPC attack, from a capability whose
`CapabilityType.reaction_reach` is not `none` (or a Phase Step ward). It is her defense roll
with that capability's value as a bonus, costs anima or physical fatigue
(`reaction_cost_kind`), and is harder by one `reaction_difficulty_step` per reaction already
made this round. A dodge that at least partly succeeds may move her (her **Dodge plan**).
_Avoid_: evade (the defense check itself), blink (one way of dodging), parry.

**Dodge plan** (#4676):
`CombatParticipant.dodge_enabled` and `dodge_landing`, set while declaring (`combat_dodge`):
dodge in place, land in a place her reach covers, or do not dodge. Private to her; reset each
round. _Avoid_: dodge target, escape route.

**Area attack** (#4676):
An NPC attack whose `ThreatPoolEntry.covers_place` is set: it hits everyone standing in its
place, and only leaving the place escapes it. A wound-up one fixes its **covered place** when
telegraphed. _Avoid_: AOE, splash (the room-wide `TargetingMode.ALL` is a different thing).

**Sustained Action** (#2705, ADR-0190):
The PC-side mirror of Wind-up: a `SustainedAction` row committing a PC to a multi-round
technique wind-up (`Technique.windup_rounds > 0`) or a ritual conducted under fire
(`RitualCheckConfig.sustained_rounds > 0`), declared in one round and maturing
`resolves_round - declared_round` rounds later. Pre-armed, not a mid-round interrupt — the
same declaration-time-commitment shape Wind-up mirrors from Interpose/ADR-0118, extended to
the PC side rather than reopened (ADR-0161 still governs: Concentration is rolled ONCE, at
declaration, never per landing hit). Sustaining occupies the participant's action — a new
declaration is blocked while an earlier round's `SustainedAction` is still pending
(`_validate_no_pending_sustained`), because `CombatRoundAction`'s
`unique_action_per_participant_per_round` constraint means a same-round declaration would
collide with maturation's clone. Unlike Wind-up there is no damage ramp: a held commitment
resolves at full effect or fizzles entirely — see Absorption Budget, below. A PC's own
sustained action erodes the same way an NPC's wind-up does — a landing hit adds a
`downgrades` — see `world/covenants/AGENT_GLOSSARY.md`'s Interception (wind-up) entry, which
covers both sides' shared downgrade vocabulary.
_Avoid_: channeled action, casting time (a caster's own resolution delay, not an authored
multi-round commitment), concentration (that's the CheckType rolled to set the budget, not
the commitment itself).

**Absorption Budget** (#2705, ADR-0190):
`SustainedAction.absorption_budget` — how many landing hits a sustained action survives
before it breaks with no refund. Written once at declaration from a single Concentration
roll (`roll_sustained_absorption_budget`, via `perform_check_with_modifiers` so the 26
authored `ConditionCheckModifier` rows on Concentration actually apply — plain
`perform_check` would silently make them inert): `clamp(SUSTAINED_BASE_ABSORPTION (2) +
CheckResult.success_level, SUSTAINED_MIN_ABSORPTION (0), SUSTAINED_MAX_ABSORPTION (4))`.
Clamped because `CheckOutcome.success_level` is an authored -10..+10 field with no
lore-authored ladder pinning it; Base 2 puts a clean Success at 3, exactly matching
ADR-0161's `WINDUP_FIZZLE_DOWNGRADES` — a competent PC's commitment is as durable as an
NPC's telegraphed wind-up. Never recomputed after declaration.
_Avoid_: absorption cap (that's `ABSORPTION_CAP_PER_MOMENT`, the unrelated per-landing-hit
Reaction Economy budget above), damage threshold, HP.

**Clash**:
The reserved combat primitive for a multi-round contest in which two sides pour magical energy into overpowering each other (the "beam-struggle" trope) — the clash of wills. Modelled by `Clash` with a flavor discriminator (CLASH / LOCK / WARD / BREAK). The word "clash" is reserved for this feature and must not name any other concept.
_Avoid_: contest, struggle, beam struggle, push (colloquial in code for Clash's tug-of-war progress — see `clash.py` — but ambiguous with Strain and Knockback; prefer "clash"); backfire / rejection / dissonance for unrelated opposing-resonance effects

**Dramatic Surge**:
A discontinuous, one-shot jump to `CharacterEngagement.intensity_modifier` at a dramatic combat beat: a bonded ally entering mortal peril, a bonded companion falling (its ALLY `CombatOpponent` defeated, #3575), a hated NPC foe entering the fight, a high-stakes encounter igniting, or (#3387) a SENIOR GM manually spotlighting a beat the automatic detectors miss (`SurgeTriggerKind.GM_MANUAL`, via `GMTriggerDramaticBeatAction`), written through the single shared `apply_dramatic_surge` primitive and deduped per (encounter, participant, trigger kind, subject) via `DramaticSurgeRecord`: once per encounter for the fixed-amount kinds, but once per round per subject for the four rolled kinds (`DramaticSurgeRecord.repeat_round` is set, ADR-4737; see **Rolled surge**). A manual trigger's `reason` is staff-facing provenance on the record, never broadcast. Narrated generically in the combat log; never names the bond, label, subject, or (for a manual trigger) the GM's stated reason.
_Avoid_: clash (reserved, see above), spike (ambiguous with the pre-existing #872 grief "spike" internals — "surge" is the player-facing term), burst, power-up

**Rolled surge** (#4737, ADR-4737):
A Dramatic Surge whose size comes from a roll with degrees instead of a fixed curve amount. Four kinds (`ROLLED_SURGE_TRIGGER_KINDS`): `TAUNT_RECEIVED`, `RALLIED`, `ALLY_HURT` and `STEELED` (#4738). A player character rolls; the roll's outcome picks a **Degree Band** and `apply_rolled_surge` writes the band's intensity and control change through `apply_dramatic_surge`, with the outcome, potency, control change, the condition actually applied and a `cause` line kept on the `DramaticSurgeRecord`. A rolled kind may surge again each round (once per round per subject; an NPC taunt has no subject, so one per player character per round) and only in an encounter that has an escalation curve (ADR-0098). A band that scales to 0 intensity with no control change and no condition writes nothing; with a control change or condition it is written without a room line. The surged player's character is sent a roll caption such as `Composure check vs taunt potency 14 · Partial · Intensity +3` once the round commits (control only when it changed, the condition last; a hurt ally's difficulty is a "bond difficulty" and its intensity is "scaled by the wound"); the room only gets the generic narration, and the round payload shows the roll fields and the **Surge Cause** to the surged player's owner, GMs and staff. All four kinds are inert until staff author a Surge Tuning per kind with bands, and the Ally Hurt kind also needs the staff-authored flow and trigger definition rows.
_Avoid_: spike, buff, power-up

**Steeling yourself** (#4738):
The combat verb (`combat steel`, `combat_steel`) by which a player character rolls the `STEELED` Surge Tuning's check to raise her own intensity by the outcome's Degree Band. An immediate act, once a round, not the declared action. It costs `StrainConfig.steel_fatigue_cost` fatigue from `steel_fatigue_category` (a failed roll still costs) unless she holds a **free steel** (`CharacterEngagement.free_steels`), which a successful Rally grants (`free_steels_per_encouragement`) and which ends with the fight; the ally who gave them is credited in `free_steels_given_by` and named in the chip. The once-a-round limit is `CharacterEngagement.last_steeled_round`, so a band that gives nothing still spends the round.
_Avoid_: self-buff, psych up

**Surge Tuning** (#4737):
The authored `SurgeTuning` row for one rolled surge kind (unique per `trigger_kind`): the `check_type` rolled, a `potency_base` and, for Ally Hurt, a `potency_per_depth` (difficulty = base + per_depth x relationship depth). No row for a kind means that beat does not surge (the Required content probe `surge-tuning` reports it). Ally Hurt reads the potency pair and Steeled reads `potency_base` (`clean` refuses a non-zero value elsewhere). For `RALLIED` the roll is the tuning's `check_type` made by the rallier against the fixed `RALLY_BASE_DIFFICULTY`; with no tuning the Rally check is found by name, and no surge is written.
_Avoid_: surge config, surge rule

**Degree Band** (#4737):
A `SurgeDegreeBand` row: what one roll outcome does for one Surge Tuning (`intensity`, `control_change`, an optional `condition`). One band per outcome; a roll with no band of its own takes the nearest worse band, or the lowest. A better outcome never gives a lower beneficial number, checked as a set on save (`surge_bands.validate_surge_bands`, the model `clean` and the admin inline formset). A compulsion such as Goaded is an ordinary authored `ConditionTemplate` attached to a band; it is a debuff with its own effects, not a code term and not a targeting lock.
_Avoid_: tier, step, result row

**Taunt Potency** (#4737):
`ThreatPoolEntry.taunt_potency`: the number a targeted player character rolls Composure against when an NPC opponent uses that entry. An entry with a taunt potency deals no damage and carries no defense check, on-hit pool or applied conditions (`clean` rejects them), the NPC does not roll, and it acts on player characters only. It is per pool entry because the entry is what an opponent does. Between players the potency is the taunter's check rating for the Taunt check type, clamped at 0 (an owner call of 2026-10-27), not a rolled result.
_Avoid_: taunt difficulty, taunt damage

**Surge Cause** (#4737):
`DramaticSurgeRecord.cause`: the line the surged player, GMs and staff read for a rolled surge, written when it happened ("Mira taunts Tomas.", "Mira rallies Tomas.", the opponent's authored taunt line as the room is told it, or "Tomas, bonded to Mira, loses 60% of their health."). Third person with persona names, never the character sheet label, because GMs and staff read the same line for someone else's beat. Every other viewer reads only the generic curve line, so the cause never names a bond, a foe or a roll to them.
_Avoid_: reason (that is the staff-stated provenance of a GM_MANUAL surge), provenance

**Escalation intensity**:
`CharacterEngagement.intensity_modifier`. The one lever the escalation tick, every
`SurgeTriggerKind` beat, and `AudereThreshold.intensity_bonus` write. Drives anima cost,
Soulfray and the Audere gates.
_Avoid_: intensity bonus

**Vulnerability power bonus**:
`BreakBarConfig.intensity_bonus` -> `CombatOpponent.vulnerability_intensity_bonus` ->
`power_intensity_bonus`. Extra power a PC technique derives while a broken boss is inside
its vulnerability window. Never touches escalation intensity.
_Avoid_: intensity bonus (ambiguous with Escalation intensity, above), vulnerability bonus

**Boss beat** (#3445, ADR-0250):
A phase transition, enrage, or break-bar break; each fires its own `SurgeTriggerKind`
(`BOSS_PHASE` / `BOSS_ENRAGE` / `BOSS_BREAK`) for every ACTIVE PC, once per boss per phase.
_Avoid_: boss event, phase spike

**Phase line** (#3552):
The room narration a boss phase transition broadcasts: the phase's authored `BossPhase.description` when set, else a generic shift line, plus an enrage line when the new phase hits harder. Not curve-gated; distinct from the boss beat's generic surge narration, which never names the boss.
_Avoid_: phase announcement, transition surge

**Held back** (#3552):
An ACTIVE PC in the resolution order with no `CombatRoundAction` this round under TIMED or MANUAL pace; the round's OUTCOME output names them ("X holds back."). A sustaining participant is committing, not holding back.
_Avoid_: skipped, idle, AFK

**Edge / Setback** (GM fiat, #3387):
A curated, catalog-safe one-round nudge a GM applies through the existing `gm_apply_condition` lever — two authored `ConditionTemplate` rows (`world/conditions/gm_edge_content.py`) delivering a ±10 `ConditionCheckModifier` scoped to the Combat `CheckCategory`, `scales_with_severity=True`, expiring at the end of the round applied. Not a new mechanism — no bespoke GM-fiat modifier system exists or should exist alongside it.
_Avoid_: buff/debuff (generic — Edge/Setback name this specific GM-fiat lever), bonus/penalty

**Strain**:
Anima a PC commits beyond a technique's effective cost floor, converted by a diminishing-returns curve (`StrainConfig`) into a power/intensity bonus passed to the cast. Strain scales the technique's power and progress delta — never the check roll.
_Avoid_: push, overcharge, effort (effort modifies the roll; strain scales power)

**CombatPull**:
A per-(participant, round) commit envelope capturing the resonance, tier, and threads a participant spends on a thread pull during combat. Resolved effects are snapshotted so mid-round authoring edits cannot retroactively change a committed pull.
_Avoid_: thread pull (the in-combat record specifically), draw

**ThreatPool**:
A named collection of the possible actions an NPC can take in a round (`ThreatPoolEntry` rows); a boss phase or opponent draws its behaviour from its assigned pool.
_Avoid_: action list, move set, aggro pool

**BossPhase**:
One stage of a boss fight (`BossPhase`) with its own threat pool, soak, probing threshold, and health trigger; a boss progresses through its phases as its health crosses each trigger.
_Avoid_: stage, form, tier (tier is the opponent's power class)

**OpponentTier**:
The power class of an NPC opponent (`OpponentTier`: SWARM, MOOK, ELITE, BOSS, HERO_KILLER), seeding its baseline stat budget. SWARM uses count/body-toughness mechanics; HERO_KILLER is the unbeatable presence.

**Opponent level** (`CombatOpponent.level`, #2707, ADR-0166):
A `CombatOpponent`'s power level on the same 1-30 scale as a PC's class level — a
SEPARATE axis from `OpponentTier`: a level 3 BOSS and a level 20 MOOK are both coherent
(tier is the opponent's *role/budget class*; level is where it sits on the same
power-scaling axis a PC uses). Opposes a PC's checks through `world.checks.services
.level_opposition` at every combat call site (offense, penetration, and NPC-attack
defense) and is public in the opponent payload, so a threat readout can be built on it.
Since #3384, `level_opposition` also folds in the opponent's own active
`ConditionCheckModifier` rows (via `opponent_condition_opposition`), so a debuff
applied to the opponent lowers the difficulty it presents on the same call sites.
Auto-scaled spawns default to the encounter's average party level; a GM setting it
deliberately low is how a soloable or upset-victory boss is authored.
_Avoid_: tier (that's `OpponentTier`, a different axis — see above), rank, difficulty
(for the NPC's class), CR/challenge rating

**Consider** (`consider_opponent`, #2716):
A narrative threat readout verb — the DikuMUD/EverQuest `/consider` descendant.
Runs a PERCEPTION check opposed by the opponent's level via `level_opposition`;
the `success_level` (−10 to +10) maps to accuracy. Failures produce **confidently
wrong** bands (off by 1–3 steps), not silence — the player can't distinguish
accurate from inaccurate readings. One cached reading per (participant, opponent)
per encounter — no re-rolls (`ConsiderReading` model). An enhancement capability
(`CovenantRole.enhances_assessment`, initially the Sage role) grants finer 9-band
readings + health/condition axes; the check still gates accuracy. The
`bias_direction()` seam is data-driven via the "consider_bias_direction"
`ModifierTarget` — the Overconfident distinction's `DistinctionEffect`
(`value_per_rank=-1`) biases toward underestimates; any source can bias
direction by writing a `CharacterModifier` against this target (#2752).
The distinction also applies a -2 check penalty via a
consider-scoped `ModifierTarget`, and `consider_opponent` routes through
`collect_check_modifiers` (the central aggregator). Web-first REST endpoint on
`CombatEncounterViewSet`; telnet `consider` command follows.
_Avoid_: assess, appraise, threat-level (use **consider**), accuracy rating

**Lieutenant** (#2642):
An NPC opponent whose `reinforces` self-FK points at a BOSS-tier opponent. While active
(ACTIVE status, morale not BREAK, no behavior-altering condition, not pinned in an ACTIVE
`EngagementLock`, acted this round), each lieutenant slows the boss's break-bar depletion —
the **lieutenant gate** divides a round's depletion by `1 + active_unsuppressed_reinforcers`.
A parked/idle lieutenant (didn't act this round) never gates. This is the "suppress the court"
half of the boss-fight's emergent three-act shape (ADR-0160).
_Avoid_: minion, add (that's the reinforcement-spawn mechanism, a different thing — a lieutenant
is authored on the opponent row, not spawned by a phase transition), sub-boss

**Break-bar contribution** (`BreakBarContribution`, #2642):
A per-round audit row (mirrors `ClashContribution`'s shape) recording one feed that chipped a
boss's break bar — `BreakContributionKind`: DAMAGE, COMBO, HOLD (a PC-side LOCK-clash win
against the boss), DEBUFF (a new behavior-altering condition landed on the boss), SUPPRESSION
(a reinforcing lieutenant newly suppressed). Depletion is diversity-weighted: 1 unit per
distinct (actor, kind) pair this round, doubled for a (kind, effect_type) pair's first-ever
occurrence in the encounter — replacing the retired flat per-actor chip (ADR-0160).
_Avoid_: break-bar chip/tick (the old flat mechanism's name — don't reuse for the new per-row
audit record)

**Party Profile**:
An immutable level-only snapshot of the active party (`PartyProfile`: party_size + avg_level) feeding the encounter-scaling formula. Difficulty scales on party size and average level only — never on threads, relationships, or other narrative richness.
_Avoid_: party stats, party power, party rating

**Focused action**:
The single primary action a PC commits in a round — the one that matches a combo slot and carries the round's main intent. A round is one focused action plus up to two secondary actions.
_Avoid_: main action, primary (use "focused" specifically)

**Secondary action**:
A supporting action a PC takes alongside the focused action (physical and/or social), up to two per round. The non-focused action type.
_Avoid_: passive

**Round combo**:
A combo as the round in progress sees it (`RoundCombo`, from `scan_round_combos`, #3553): every slot listed with its requirement and either the participant filling it or "open". A complete round combo is an available combo (the upgrade candidate); a partial one is shown only when an active PC in the encounter knows the combo, so hidden combos are never hinted at.
_Avoid_: partial combo (say "round combo with open slots"), combo preview

**Open slot**:
A combo slot no declared focused action fills yet this round. The "needs one more: Defense" hint is the list of open slots' requirement labels.
_Avoid_: empty slot, missing slot

**Allegiance (stored vs effective)** (#4091, ADR-4091 amending ADR-0059):
Two different reads of the same word. **Stored** is `CombatOpponent.allegiance`
(`CombatAllegiance`: `ENEMY` default, `ALLY`), mutable, written once at creation for
a summon or companion, and never touched by a charm. **Effective** is
`effective_allegiance`/`effective_allegiances` (`world.npc_services.allegiance`): the
stored value composed with whatever allegiance-flagged conditions the bearer carries
right now (charmed, turned, calmed), the value that actually decides targeting and
victory. A charmed enemy stays stored ENEMY forever; only its effective allegiance
changes while the charm holds. No condition ever writes the stored field.
_Avoid_: faction, team, side (as model names); "allegiance" alone when the stored vs
effective distinction matters to the sentence

**Turned** (`Allegiance.TURNED`, #4091):
An effective allegiance meaning the bearer attacks its own former side's other
opponents, never a PC and never itself. Set by a condition whose
`ConditionTemplate.sets_allegiance = TURNED`. Distinct from a charmed
(`ALLY_OF_CASTER`) opponent, which fights FOR the party instead.
_Avoid_: switched sides, flipped, defected (informal narration only; the state is
Turned)

**Won over** (`OpponentStatus.WON_OVER`, #4091):
What a `CombatOpponent` becomes at encounter victory when it carries an effective
allegiance other than ENEMY (charmed, turned, or calmed) rather than being beaten
down. A won-over opponent never counts toward "any hostile remain," so a field where
every remaining enemy is won over ends as an ordinary VICTORY; its authored
aftermath pool fires on that victory the same way a `DEFEATED` opponent's does. Won
over is a status stamped once, at the moment the fight ends; the allegiance that
earned it can keep changing (settled, broken, lapsed) afterward.
_Avoid_: pacified, converted, subdued (for the status specifically; "charmed" /
"turned" / "calmed" name HOW it was won over)

**Bind window** (`bind_window_open`, #4091):
Whether a charmed nameless (ephemeral, persona-less) `CombatOpponent` is still
eligible to be bound as a companion after the fight: open exactly while its charmer
remains in the same room. Shared by the digest row's `can_bind` flag, telnet
`companion promote`, and `promote_summon_to_companion`'s charmed-enemy path, so
all three agree. A nameless charmed body with a closed bind window is deleted by
the lapse sweep or scene finish rather than kept with nothing to do.
_Avoid_: bind timer, charm window (the window is about the charmer's presence, not
a countdown)

**Settled round** (#4120, ADR-4120):
What a round-counted condition on a combatant becomes when the fight ends:
`cleanup_completed_encounter` calls `settle_round_effects`, converting the remaining rounds into
a real-time expiry. Combat owns the trigger; the clock and the non-lethal tick live in
conditions (see its glossary). A charm or hold converted this way is what the lapse sweep sees.
_Avoid_: frozen condition, leftover rounds

**Summon**:
An ALLY `CombatOpponent` conjured during combat by a technique. It has `allegiance=ALLY`,
`summoned_by` (FK → `CharacterSheet`), and `bond_expires_round`; it attacks ENEMY opponents
via `CombatOpponentAction.opponent_targets`. "Summon" means this specific bonded ALLY; the
general concept of a combat companion is "ally combatant".
_Avoid_: familiar, pet, companion (for the in-combat summon row specifically)

**Reactive interceptor**:
A mutation-only `DAMAGE_PRE_APPLY` flow handler that can reduce or nullify an incoming hit —
force-field (absorb_pool, priority 10), reflect (reflect_damage, priority 20), or blink
(blink_dodge, priority 30). Force-field and reflect find their condition by field, never by its name (#4572). Each sets `payload.amount = 0` on success; lower-priority
interceptors guard `if payload.amount <= 0: return`. Cost: `reactive_anima_cost` per fire;
can't pay → fizzle, attack lands. No `CANCEL_EVENT` child step (ADR-0060).
_Avoid_: cancel-event interceptor, reactive cancel, shield handler

**Knockback**:
A deterministic on-hit effect that shoves the defender one Position away from the attacker, authored via `ThreatPoolEntry.on_hit_consequence_pool` firing a `MOVE_TO_POSITION`/`AWAY_FROM_ACTOR` consequence effect. Fires only after the #1273 Interpose seam resolves — a clean block prevents it for free.
_Avoid_: push ("push" is already ambiguous with Strain and Clash's tug-of-war progress — see those entries), shove, displace

**ThreatRecord**:
A per-(opponent, participant) threat score accumulated from real events: damage dealt, taunts (#2015), protective actions. The substrate for NPC target selection: `HIGHEST_THREAT` sorts candidates by threat value, and `SPECIFIC_ROLE` prioritizes SHIELD-archetype PCs then breaks ties by threat. An active `EngagementLock` narrows the locked NPC's targeting to just the locked PC. A PC's active `draws_aggro` conditions add their summed `aggro_priority` to its threat with every opponent at selection time (#4572); that bonus is read, never stored as a `ThreatRecord`.
_Avoid_: aggro table, hate list, enmity

**EngagementLock**:
A declarable foil pairing between one PC and one opponent within a group encounter (#2020). While ACTIVE, the NPC's targeting is narrowed to just the locked PC (the provable-targeting guarantee). An optional `clash` FK links to the metered contest (Clash) when one opens between the locked pair — the lock orchestrates the pairing, the Clash is the struggle. Lock formation is autonomous (threat threshold) or PC-initiated (`combat engage`). Interference by a non-locked PC is a narrative payoff, not a penalty.
_Avoid_: duel lock, mark, fixate (use for the pairing specifically), taunt (taunt is the threat verb, not the lock)

**Foil**:
An NPC opponent designated to pair off against a specific PC in a rival duel within a group fight — the dramatic thread inside the melee. Marked by `has_foil_behavior=True` on `CombatOpponent` with a lower `auto_lock_threshold` so the pairing forms readily from threat accumulation.
_Avoid_: rival, nemesis (narrative terms — use "foil" for the mechanical pairing)

**Rampart** (#2209, epic #2040 decision 3):
A projected living barrier covering a `Position` — the model itself is owned by
`world.areas.positioning` (see that app's `AGENT_GLOSSARY.md`; ADR-0125 for why it's an
entity, not per-bearer conditions). Combat owns interception: `apply_rampart_interception`
runs at the top of both damage-application seams — `apply_damage_to_participant` and
`_resolve_opponent_pre_apply` (the opponent-side pre-apply resolver) — **before** the
`DAMAGE_PRE_APPLY` event emits, so a Rampart chips first and personal reactive interceptors
(force-field/reflect/blink) and Guardian reactions only ever see what's left after it. A
sustained attack (`is_sustained_attack`) against a covered position instead opens a WARD
`Clash` bound to the Rampart (`Clash.rampart`), which drains the same integrity pool as the
meter — interception no-ops while that Clash is ACTIVE (the no-double-drain rule).
_Avoid_: ward, barrier, bulwark, shield wall (all already claimed elsewhere)

**Strike delivery** (`StrikeDelivery`, #2209):
How a strike reaches its target — `MELEE` or `MISSILE` — carried on `ThreatPoolEntry.delivery`
(NPC threat-pool entries; default `MELEE`) and passed through to
`apply_damage_to_participant`/`apply_rampart_interception` alongside `is_area`
(`targeting_mode != SINGLE`). A Wind-element Rampart's `MISSILE_WARD` signature reads
`delivery`/`is_area` directly: bonus resist against `MISSILE`, penalty against area strikes.
Also the field the Wind band (below) keys its symmetric NPC-side bonus on.
_Avoid_: attack type, damage delivery, hit type

**Wind band** (#1555, ADR-0129):
The banded reading of a room's felt WIND exposure (`world.locations.services.felt_exposure`,
`StatKey.WIND`) that a missile check consumes: CALM (<15) → 0, BREEZY (15-39) → -5, WINDY
(40-69) → -10, GALE (70+) → -20 (`wind_penalty`, `world/combat/constants.py`). Authored as
bands, not a raw per-point scale, so a player can reason about "it's windy" rather than a bare
number. Applies as a SCENE `ModifierContribution` labeled "Wind": negative on a PC's missile
(RANGED/THROWN-equipped) offense check, and the same magnitude positive on a PC's defense
check against a `StrikeDelivery.MISSILE` NPC attack — the gale punishes both sides' aim
equally. Melee/lance attacks and flat (no defense-roll) NPC damage never consult it.
_Avoid_: wind penalty (that's `wind_penalty`, the function — "wind band" is the concept),
weather modifier (too broad — this is WIND specifically, not the general exposure cascade)

**BondCombatBonus**:
The relationship co-combat passive (#2021, ADR-0109, mechanism amended by ADR-0308). While a PC and a bonded character are co-combatants and the ally is `ParticipantStatus.ACTIVE`, the PC gains the **claimed tier**'s authored `RelationshipTier.combat_bonus` as a `ModifierContribution(RELATIONSHIP)` on every combat check — provided the PC's own side has claimed at least `BondCombatConfig.min_tier` (#3957 replaced the cube-root-of-developed-points magnitude and the `min_developed_absolute_value` floor; both columns are dropped). Soul-tethered pairs get `soul_tether_multiplier ×` that bonus. Directed (one-sided): only the character who invested gets the bonus. Drops when the ally falls (handing off to #2013's grief spike). Also scales INTERPOSE/SUCCOR capability checks via `bond_bonus(actor, protected)` → `extra_modifiers`.
_Avoid_: bond buff, ally bonus (use "bond combat bonus" or "co-combat passive")

**Aftermath digest** (#3551):
The per-participant summary of what a fight changed, assembled at `complete_encounter`'s
conclusion from rows the completion seam already wrote (aftermath `ConsequenceOutcome`,
`ConditionInstance`, `LegendEntry`, `BeatCompletion`), never persisted as its own row.
`build_aftermath_digest` reads the consequence, legend and beat rows bounded by
`[completed_at, completed_at + AFTERMATH_ATTRIBUTION_WINDOW)` so a read-time rebuild
does not pick up a later fight in the same scene; conditions are bounded by
`[encounter.created_at, completed_at + AFTERMATH_ATTRIBUTION_WINDOW)`, so that same
upper edge also keeps a later fight's condition out of an earlier digest.
`render_aftermath_digest` turns the digest into the private Narrator line and telnet
message `deliver_aftermath_digests` sends to each ACTIVE or FLED participant. Conditions
cleared mid-fight report nothing (their rows are gone and the pose log already narrated
them); only conditions still held that were applied during the encounter show. The legend
line ("Deed remembered") only ever reports an authored deed row, since legend settles at
the end of a story from its outcomes, never per fight.
_Avoid_: aftermath report, post-combat summary, combat recap

**Spectacle** (#4147, ADR-4147):
An earned display of power that shakes the enemies who witness it: each witness loses morale once per caster and move, and allied NPCs regain some. Earned, never declared: nothing authors a "clever play" tag.
_Avoid_: awe, dread, intimidation (that is the CheckType), scare, fear effect

**Spectacle kind** (#4147):
What kind of display shook the witnesses: Audere entry, Ultimate, Crossing, Critical technique, Devastating action (`SpectacleKind`). Each has its own base hit in `SpectacleConfig`. Distinct from **Spectacle reaction** (`SpectacleReaction`: shaken, faltering, broken, heartened), which only picks the authored flavour line.
_Avoid_: display type, fear source

**Standoff** (#4145):
The pre-round state of a `CombatEncounter` in which the party reads and talks down groups of opponents before the first round. Its terms (Group, Drive, Cause, Regard rule, Spark, Terms, Approach) live in `src/world/standoffs/AGENT_GLOSSARY.md`.
_Avoid_: parley phase

**Added-effect firing** (`VowAddedEffectFiring`, #4581):
Play state: one row recording that a combat participant's covenant vow fired a once-per-round or once-per-fight added effect in a given round. The participant is the holder whose vow carried the effect, not necessarily the caster (an ally's cast can fire the holder's effect). Written only by a cast that landed; a new fight starts with an empty ledger because a participant row belongs to one encounter. The effect itself is a covenants term: see the covenants glossary's "Vow added effect".
_Avoid_: cooldown, charge, spent flag (a boolean on the participant was the rejected shape).

**Hop budget** (#4607, slice 2 of #4576):
How many hops a combatant may move in one round. A player character's comes from the movement capability (`hops_for`: one hop per `MOVEMENT_PER_HOP` points, at least one, at most `MAX_HOPS_PER_ROUND`; a value of 0 gives none) and is counted on `CombatParticipant.hops_used`, which resets when declaration opens. A PC may move only while the round is DECLARING; while it resolves or between rounds the move is refused, and outside an active encounter moving is free. An opponent's budget is its creature template's `speed_hops`.
_Avoid_: movement points, speed (speed is the resolution-order rank), action economy

**Tactics level** (#4607):
How a creature thinks in a fight (`CreatureTactics`: MINDLESS, CUNNING, TACTICAL), authored on its `CreatureTemplate` and inherited by every opponent spawned from it. An opponent with no template is CUNNING. The tactics ladder (`npc_tactics.py`, #4609) reads it: every level retreats when broken and runs for cover from an attacker it cannot answer; a MINDLESS creature always bashes a wall in its way, never goes around or retargets, never uses a grounding entry and never waits; CUNNING and TACTICAL bash only a wall the group can bring down in `bash_rounds_limit` rounds, otherwise go around or toward another enemy, wait once when nothing gets them nearer, and spend a grounding entry on a flier they cannot otherwise reach; a TACTICAL one prefers cover that keeps an ally beside it.
_Avoid_: AI level, intelligence, difficulty

**Move plan** (`CombatOpponentMove`, #4607):
Play state: the movement plan for one opponent in one round (`OpponentMoveKind`: ADVANCE, SHELTER, BASH, RETREAT, WAIT), written at selection for every active opponent that is not winding up, calmed or a duel mirror, even one with no attack it can use. It is advisory: in the opponent's slot `run_move_plan` (#4609) carries it out against live positions (ADVANCE through `advance_opponent`, SHELTER to cover, BASH a wall, RETREAT away from every enemy, WAIT holds a waiting strike), moves up to its hop budget, and only then are its attack rows re-fit to the targets still in reach. An opponent never moves after its first attack in a round (strike then stay). The ladder that picks the kind is `npc_tactics.py`. See ADR-4607-A and ADR-4609-A.
_Avoid_: AI move, pathing order, NPC intent

**Waiting strike** (#4608, slice 3 of #4576):
A melee strike held for the first enemy that comes into reach or attacks. A PC declares it as the round's one action (`CombatManeuver.AWAIT_OPENING`, "Wait for an opening"; telnet `combat await <technique>`, web `combat_await_opening`) with a technique whose reach is SAME or ADJACENT; an NPC holds one through a WAIT move plan. It fires at most once a round (`fire_waiting_strikes`): when an NPC ends a hop in the waiter's reach (arrival), or before an attack on the waiter resolves while the attacker stands in reach. Arrival comes first, so an enemy that walks in and attacks draws it once. It runs the normal technique pipeline; costs are charged only when it fires, and one that never fires costs the action and is named after the round ("{name} waited for an opening that never came."). A strike that stops the mover cancels its move and attack. "Fired" is derived for a PC (the row's `focused_opponent_target` is the enemy struck) and stored for an NPC (`CombatOpponentMove.fired`).
_Avoid_: ready, readied action, hold, held action, overwatch, riposte (ready and hold already mean other things here)

**Unanswerable attacker** (#4609, slice 4 of #4576):
A fighter whose attack this round is aimed at an opponent (a player's declaration, or another opponent's attack row) and that the opponent cannot hit back with any threat entry it would use, even after spending its hop budget: an archer in the air out of a walker's reach, say. Derived each time, never stored. An opponent hit by one runs for a roofed or screened position out of its reach (SHELTER), whatever its tactics level, and each hit it lands costs the opponent `NpcTacticsConfig.unanswered_hit_morale` (the spectacle settings' share for a tier without morale). An unplaced fighter is always answerable.
_Avoid_: kiter, untouchable, ranged threat

**Progress guarantee** (#4609, ADR-4607-A):
In every resolved round every active opponent that is not winding up, calmed or a duel mirror does something a player can see: an attack, a move, a blow at a wall, a held waiting strike, or leaving the fight. Judged on what happened, not on what selection wrote (the property test `integration_tests/fuzz/test_npc_progress_fuzz.py`). The one exception is the physically stuck opponent (no route, no breakable wall, nobody in reach, no wait left), whose slot says "{name} strains against {barrier}.".
_Avoid_: anti-idle rule, no-stall rule

**Bash** (#4609):
An opponent's move plan to break the wall in its way (`OpponentMoveKind.BASH`): it walks to the wall's near end and strikes it once with its hardest melee entry, `base_damage` times its damage multiplier with no defence roll, through `damage_barrier`. Chosen when the group can bring the wall down within `bash_rounds_limit` rounds (the summed best melee chip of its side within a hop of the wall), always by a mindless creature, and by a cunning or tactical one when nothing else gets it nearer and it has already waited once (ADR-4609-A). If the wall fell before its slot it closes in and strikes whoever is in reach instead.
_Avoid_: siege, breach (a breach is a challenge approach)

**Encounter state ping** (`combat_encounter_state`, #4644):
The slim WS message `{encounter_id, round_number}` (`CombatEncounterStatePayload`) sent after a combat change commits: once per resolved round, and after any move in a room with an open encounter. It carries no encounter data; the client refetches the REST encounter, so the battle map shows where everyone stands. The combat counterpart of the battles' BATTLE_STATE ping (ADR-0095).
_Avoid_: combat push, encounter sync, live map update

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
A first-class depletable resolve pool on `CombatOpponent` (#2015), mirroring war-scale `BattleUnit.morale`. The derived state (STEADY/FALTER/BREAK) is read via `morale_state_for` — never stored. Falter weakens NPC output in `select_npc_actions`; Break sets `OpponentStatus.FLED`. Mindless opponents (`OpponentTierTemplate.has_morale=False`) resist morale checks with a flat difficulty modifier — not an immunity; a powerful enough roll breaks through (Arx's "power can do the impossible" tenet).
_Avoid_: willpower, resolve (as a field name — `morale` is the canonical column)

**Rally**:
The social-combat maneuver by which a PC inspires an ally — rolling presence + Performance + Oratory to apply a short-lived `Inspired` buff, and on a great success restoring morale to ally-side summon opponents. A benefit, so consent-free (ADR-0024).
_Avoid_: inspire (as the maneuver name), buff, motivate

**Demoralize**:
The social-combat maneuver by which a PC breaks an opponent's nerve — rolling presence + Persuasion + Intimidation against the target's Composure to deplete morale. Mindless foes resist but are not immune. Targets NPCs only.
_Avoid_: intimidate (that name is the CheckType), frighten, cow

**Taunt**:
The social-combat maneuver by which a PC draws an NPC's aggro — rolling wits + Persuasion + Intimidation to accumulate threat on the existing `ThreatRecord` seam, biasing the NPC's target selection toward the taunter next round.
_Avoid_: provoke, mock, aggro (colloquial)

**Parley**:
The social-combat maneuver by which a PC talks a foe down mid-fight — rolling charm + Persuasion + Seduction against the target's Composure to apply a disposition delta (via `apply_social_disposition_delta`), calm the opponent on a decisive success, or yield a broken foe on a critical success. Gated: the opponent must be faltering/broken or the PC must hold sufficient standing. Even mindless targets can be parleyed with — a breakthrough grants a fleeting mind (Sharlotte charming a lake).
_Avoid_: negotiate, bargain, persuade (that name is the CheckType)

**Yield**:
The maneuver by which a PC concedes — in a duel the yielding PC loses immediately. PvP is structurally non-lethal (yield / knockout), so yielding ends the contest without injury or death.
_Avoid_: surrender, forfeit, submit, defeat

**Interpose**:
The maneuver by which a PC stands ready to step in front of an attack aimed at an ally and intercept it (a clean block). It costs fatigue only on the round it actually fires; an armed-but-never-triggered interpose costs nothing. See `world/scenes/AGENT_GLOSSARY.md`'s Sudden Harm entry for the out-of-combat sibling, which arms via a bootstrapped scene round instead of a `CombatRoundAction`. Interpose is the **mundane case** of the more general Guardian reaction (below): a plain `declare_interpose(technique=None)` rolls best-of Reflexes/Melee Defense instead of a declared protective technique.
_Avoid_: block, guard, intercept, bodyguard

**Guardian reaction** (#2207):
The declared protect-with-technique reaction a PC arms via `declare_interpose(participant, ally=None, technique=None)`. Two mechanically distinct resolution branches share the one declaration field (`CombatRoundAction.focused_action`, reused rather than adding a parallel column):
- **Mundane** (`technique=None`, Interpose's original shape): dispatches through `world.mechanics.reactions.dispatch_capability_reaction(select_best_check_rating=True)`, which picks the higher-rated of the guardian's *real* available reaction approaches (Reflexes vs. Melee Defense, via `compute_check_rating`) — deterministic, zero extra rolls, never inventing an action outside `get_available_actions`'s output (ADR-0032). Costs fatigue on fire.
- **Technique-guardian** (`technique=<a known, learned Technique classifying to a protective flavor>`): resolved by `world.combat.services._try_technique_interpose`, which rolls the guardian's own cast check (`resolve_cast_check_type`) instead of a capability-reaction challenge, and pays a flat `ConditionTemplate.reactive_anima_cost` (fizzle if unaffordable: no roll, no charge, narrated to the guardian and the room, #3574) instead of fatigue. See ADR-0118 for why this rolls outside `use_technique`. Grading (clean/partial/fail) is shared with the mundane path via `_grade_interpose_damage`; a clean BLINK-flavored block relocates the ward to the guardian's position; a REDIRECT-flavored block sends the saved amount to the declared destination (see **Redirect**, below).

`world.magic.services.targeting.protective_flavor(technique)` classifies a technique's reactive-trigger handler into `barrier` (absorb_pool) / `blink` (blink_dodge) / `redirect` (reflect_damage) by walking its authored condition→reactive-trigger→flow data — no new authored field. A guardian can also shield an ALLY-allegiance `CombatOpponent` (a summon) — but only via the *any-ally* (`ally=None`) declaration, since `focused_ally_target` FKs `CombatParticipant` and cannot name a `CombatOpponent` directly (a named-ally guard of a summon is a follow-up).
_Avoid_: guardian ward, protect action

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
The two budgets gating the shared interpose fire seam (`_dispatch_interpose_action`):
`CombatParticipant.reactions_used` vs `REACTIONS_PER_ROUND` (1, per-participant, reset each
`begin_declaration_phase`) and `DamagePreApplyPayload.answers_consumed` vs
`ABSORPTION_CAP_PER_MOMENT` (2, per-landing-hit, regardless of who fired). Standing defenses
(absorb/reflect/blink — their own `reactive_anima_cost`, ADR-0060) sit outside both budgets.
A declined guardian is told privately why (#3574, ADR-0271); the table is not.
_Avoid_: reaction points, action economy (this is specifically the interpose-family reaction
budget, not a general action-point system).

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
A discontinuous, one-shot jump to `CharacterEngagement.intensity_modifier` at a dramatic combat beat — a bonded ally entering mortal peril, a bonded companion falling (its ALLY `CombatOpponent` defeated, #3575), a hated NPC foe entering the fight, a high-stakes encounter igniting, or (#3387) a SENIOR GM manually spotlighting a beat the automatic detectors miss (`SurgeTriggerKind.GM_MANUAL`, via `GMTriggerDramaticBeatAction`) — written through the single shared `apply_dramatic_surge` primitive and deduped per (encounter, participant, trigger kind, subject) via `DramaticSurgeRecord`. A manual trigger's `reason` is staff-facing provenance on the record, never broadcast. Narrated generically in the combat log; never names the bond, track, subject, or (for a manual trigger) the GM's stated reason.
_Avoid_: clash (reserved, see above), spike (ambiguous with the pre-existing #872 grief "spike" internals — "surge" is the player-facing term), burst, power-up

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

**Allegiance**:
Which side a `CombatOpponent` fights on — `ENEMY` (hostile to PCs, the default) or `ALLY`
(fights for the party). Allegiance is mutable: a summon spell creates an ALLY opponent; future
charm / switch-sides effects flip an existing ENEMY to ALLY. Both cases use the same field on
the same model; no parallel model is needed (ADR-0059).
_Avoid_: faction, team, side (as model names)

**Summon**:
An ALLY `CombatOpponent` conjured during combat by a technique. It has `allegiance=ALLY`,
`summoned_by` (FK → `CharacterSheet`), and `bond_expires_round`; it attacks ENEMY opponents
via `CombatOpponentAction.opponent_targets`. "Summon" means this specific bonded ALLY; the
general concept of a combat companion is "ally combatant".
_Avoid_: familiar, pet, companion (for the in-combat summon row specifically)

**Reactive interceptor**:
A mutation-only `DAMAGE_PRE_APPLY` flow handler that can reduce or nullify an incoming hit —
force-field (absorb_pool, priority 10), reflect (reflect_damage, priority 20), or blink
(blink_dodge, priority 30). Each sets `payload.amount = 0` on success; lower-priority
interceptors guard `if payload.amount <= 0: return`. Cost: `reactive_anima_cost` per fire;
can't pay → fizzle, attack lands. No `CANCEL_EVENT` child step (ADR-0060).
_Avoid_: cancel-event interceptor, reactive cancel, shield handler

**Knockback**:
A deterministic on-hit effect that shoves the defender one Position away from the attacker, authored via `ThreatPoolEntry.on_hit_consequence_pool` firing a `MOVE_TO_POSITION`/`AWAY_FROM_ACTOR` consequence effect. Fires only after the #1273 Interpose seam resolves — a clean block prevents it for free.
_Avoid_: push ("push" is already ambiguous with Strain and Clash's tug-of-war progress — see those entries), shove, displace

**ThreatRecord**:
A per-(opponent, participant) threat score accumulated from real events — damage dealt, taunts (#2015), protective actions. The substrate for NPC target selection: `HIGHEST_THREAT` sorts candidates by threat value, and `SPECIFIC_ROLE` prioritizes SHIELD-archetype PCs then breaks ties by threat. An active `EngagementLock` narrows the locked NPC's targeting to just the locked PC.
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
The relationship co-combat passive (#2021, ADR-0109). While a PC and a bonded character (relationship above `BondCombatConfig.min_developed_absolute_value`) are co-combatants and the ally is `ParticipantStatus.ACTIVE`, the PC gains `int(mechanical_bonus)` (cube root of developed absolute value) as a `ModifierContribution(RELATIONSHIP)` on every combat check. Soul-tethered pairs get `soul_tether_multiplier × mechanical_bonus`. Directed (one-sided): only the character who invested gets the bonus. Drops when the ally falls (handing off to #2013's grief spike). Also scales INTERPOSE/SUCCOR capability checks via `bond_bonus(actor, protected)` → `extra_modifiers`.
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

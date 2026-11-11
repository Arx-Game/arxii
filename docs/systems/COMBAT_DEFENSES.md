# Combat Defense Composition

Three defense modes layer in the damage pipeline. They compose — they are not
mutually exclusive. A character in plate with a force-field still rolls evasion
first; evasion scales the amount, then barrier/DR/soak layer on top.

## Authored defense piercing (#4575)

Damage profiles carry three independent authoring controls:

- `ignores_soak` skips NPC soak and PC worn armor and covenant/resonant soak.
  Generic thread damage reduction always applies and cannot be bypassed by any
  attack type; it is the character survivability baseline. Soak is removed down to zero; an unarmored
  target takes no bonus damage. Armor skipped by the hit takes no absorption wear.
- `resistance_shift` is a nonnegative point shift for this typed hit only:
  `effective_resistance = current_resistance - resistance_shift`. A shift of 5
  changes resistance 8 to 3, neutral 0 to vulnerability -5, and vulnerability -4
  to -9. Untyped damage has no resistance to shift. The target's stored defenses
  never change; lasting vulnerability is authored as a condition.
- `bypasses_wards` on any effective profile bypasses the whole technique's
  `barrier_strength` penetration contest, including its associated conditions and
  other damage rows. Variant, active signature and eligible vow-added-effect profiles participate. The ward
  is not consumed and ordinary offense/effect success gates still apply.

Defaults are false/0/false, preserving existing content. These controls do not skip
reactive damage events, ramparts, position cover or lethality rules. The PC damage
service accepts the same hit controls as the NPC service; this adds no new PvP
technique-targeting route. Authored soak piercing keeps ordinary probing; the
existing combo-only `bypass_soak` flag still suppresses combo probing.

## Damage pipeline

```
NPC attack (ThreatPoolEntry.base_damage)
  → [evasion check]        scales base_damage by multiplier         (#1994)
  → Rampart interception   position-covering barrier chips first      (#2209)
  → DAMAGE_PRE_APPLY       barrier absorb_pool, reflect, DEFEND halve (#1584)
                           (Guardian reactions also resolve here, after
                            the target's own DAMAGE_PRE_APPLY trigger band)
  → on-hit consequence     fires threat entry's on_hit_consequence_pool
  → thread DR              flat subtraction                           (#1175)
  → damage-type resistance condition-sourced resistance modifier
  → armor soak             flat subtraction, role-gated, by type      (#508/#1174/#5026)
  → health
```

**Armor stands only against the damage types it covers (#5026, owner ruling, ADR-5026-B).**
This holds on every hit in the game, player and NPC, Strike and technique, on both seams
(`apply_damage_to_participant`, `apply_damage_to_opponent`). Every worn piece stops a
Physical hit (untyped damage is Physical, #4742); a hit of another type meets only the pieces
whose `ItemTemplate.also_protects_against` lists that type (`_equipped_armor_soak_pieces`,
`is_physical` in `world/combat/services/equipment/armor_soak.py`). The resonant pool (covenant
role, facets, mantles, motif, covenant level) stands against every type. An ordinary NPC's
`soak_value` stops Physical only (its other protections are resistances); a walled opponent
(`has_wall` in `world/combat/services/damage/soak.py`: Boss or Hero Killer tier, or any
opponent with a probing threshold) keeps its soak against every type, and damage gets past
that wall only the way it did before: probing, combos (`bypass_soak`, `wall_breaker_combo`)
and the break bar's vulnerability window, which zeroes soak and resistance. `target_soak_of`
reads the soak for the hit's own type, so a "target's soak" damage input agrees.

## A form's resistance is paid per blow (#5066 decision 18)

A resistance condition a technique she cast put on herself, one of that technique's own
authored applied conditions (a smoke form), is not a standing
buff: each blow it softens in `apply_damage_to_participant` is a `use_technique` cast of that
technique (`world/combat/services/damage/form_resistance.py`, `cast_forms_for_blow`), paid
through the deficit and Soulfray path behind her "dodge even into Soulfray" answer and never
lethal for an away player. The roll scales the condition's authored resistance for that blow
(`scaled_strength`: failure 0, bare success the authored amount, +50% a level by default); the
difference rides `resistance_shift`. `paid_per_blow` excludes a passive's condition (source
description `PASSIVE_SOURCE_PREFIX`), the condition a price inflicts on its payer, and
anyone else's ward, and a condition a covenant vow's added effect applied while riding her
cast (it carries the cast technique as provenance but is not the technique's own condition,
`_is_technique_own_condition`): those stay flat and free. So do covenant role defenses and
every thread's standing tier-0 bonus she is not pulling: they are her baseline, always there
(maintainer, 2026-11-11), and nothing charges anima or rolls for them per blow. Damage-over-time ticks, hazards and battle damage read
even the form flat, because only blows are cast (maintainer ruling 2026-11-11). NPC
resistance is flat. Revisit note: if per-blow payment makes barrier and mitigation types too
weak against swarms, pay them by damage absorbed instead.

## Evasion (check → multiplier)

The PC rolls a defense check; the success level scales incoming damage.

- **Sourced from:** `ThreatPoolEntry.defense_check_type` (nullable FK to
  `CheckType`). When null, the attack applies flat `base_damage` with no
  defense roll.
- **Default seed:** `Melee Defense` CheckType = `agility (1.00) + Melee Combat
  (1.00) + weapon specializations (owned-only)`. Seeded by
  `world.seeds.combat_checks.seed_combat_check_content()`.
- **Multiplier mapping** (`world/combat/constants.py`):

  | success_level | multiplier | effect |
  |---|---|---|
  | ≥ 2 | 0.0× | full dodge |
  | 1 | 0.5× | partial dodge |
  | 0 | 1.0× | hit |
  | ≤ -1 | 1.5× | critical hit |

- **Modifier seam:** `resolve_npc_attack` routes the defense check through
  `collect_check_modifiers` — fashion, covenant-role, equipment, and condition
  modifiers all apply to defense, exactly as they do for offense.
- **Opposed difficulty (#2707, ADR-0166):** the defense check now carries a real
  `target_difficulty` instead of a flat 0 — `world.checks.services.level_opposition`
  scores the attacking `CombatOpponent.level` (and its aspect match against the
  defending PC's Path) against the roll, so a level-20 opponent's attack is
  structurally harder to evade than a level-2 opponent's identical attack, not just
  bigger-hitting. Offense and penetration checks are opposed the same way, in the
  reverse direction (the acting PC's roll is opposed by the *target's* level). See
  `docs/systems/checks.md`'s "Opposed checks" section for the shared helper and its
  deliberate exclusivity rule.

## Dodging and area attacks (#4676, slice 4 of #4651)

**The automatic dodge [BUILT & WIRED] (#4676, #5066, ADR-5066).** A character dodges an NPC
attack that carries a defense check when one of her capability sources matches an
`Application` with `dodges` set (`source_matches_application`: the application's capability,
held above its innate baseline, carrying its required effect property), or a Phase Step ward is
on her (`world/combat/services/reactions.py`, called from `resolve_npc_attack`). A technique
matches by its own `Technique.properties`, so a `teleport` technique that grants `traversal`
dodges by blinking on any gift. Each dodge is one use of that source
(`make_dodge` through `use_movement_source`, `world/combat/services/movement_use.py`):

- **With a technique** it is a `use_technique` cast of it: the technique's own anima cost, paid
  through the deficit and Soulfray path (never skipped for lack of anima), its own cast check
  rolled unopposed with the round's related FLAT_BONUS pulls, and its power plus related
  INTENSITY_BUMP pulls. The roll sets the use's strength (`scaled_strength`: the grant's
  `calculate_value` at that power, plus `MovementConfig.strength_per_success_level_percent` per
  success level above a bare success; a failure gives none and the dodge does not go off).
  The strength is added to her defense roll and, through `reach_for_strength`, sets how far she
  may land; a roll that falls short of her planned landing dodges in place.
- **With anything else** (trained ability, a condition, species, a distinction) it costs
  `MovementConfig.dodge_fatigue_cost` physical fatigue and its value is the bonus.
- **A Phase Step ward** keeps its own payer rule (`_try_spend_reactive`, #2208).

Two answers protect her. With `CombatParticipant.dodge_into_soulfray` off, a technique dodge that
would overspend her anima or deepen her Soulfray does not go off and costs nothing; the Soulfray
check-in on her turn asks her to set it (`world/combat/services/dodge_check_in.py`). And an
automatic dodge is never lethal for a player who is not connected: the cast runs non-lethal.
Each reaction she has already made this round takes `MovementConfig.reaction_difficulty_step`
off the roll (`reaction_penalty`); there is no cap. The defense roll's "Dodge" line names the
source, its roll, strength, anima and any Soulfray (`dodge_label`). With no MovementConfig row
the field defaults apply.

**Auto-pull for defense [BUILT & WIRED] (#5066).** With `CombatParticipant.auto_pull_defense` on,
the first time she is attacked in a round with no pull of her own, her saved defensive pull
(`defense_pull_tier`) is committed before a technique dodge rolls
(`world/combat/services/auto_pull.py`). It pulls every thread, of any resonance, that relates to
the dodge and is not already working for her on the defense roll, each paid from its own
resonance (maintainer ruling 2026-11-11); when nothing is left it commits and charges
nothing.

**The same power on her turn [BUILT & WIRED] (#5019, #5066).** A source matching an application
with `way_of_moving` Blinks (and no `dodges`) moves her on her turn, past walls and enemies, for
one hop (`MoveToPositionAction` blinks when walking cannot reach the place: `blink_source_to`,
`_blink` in `actions/definitions/positioning.py`). It is one use of that source like a dodge: a technique blink
is a cast of it, in a fight or out of one, and its roll's strength sets which places she can
reach; she lands on her choice when it is in reach, else at the reachable place nearest it, and a
failed roll leaves her in place, paid. Too little anima never stops her: the cast overspends into
Soulfray. It is not a reaction, so it does not make her later dodges that round harder. Another
source pays physical fatigue in a fight and nothing outside one. Staff need no blink capability:
a technique marked `teleport` that grants `traversal` reaches the Blink applications; see
`docs/systems/areas.md` "Blinking".

**The dodge plan.** `CombatParticipant.dodge_enabled` and `dodge_landing`, set while
declaring through `combat_dodge` (`DodgePlanAction`; telnet `combat dodge [<place>|here|off]`;
web Your Turn "If you're attacked this round"). A landing must be a place one of her dodge
sources reaches at its standing strength (`dodge_landing_options`, through `reach_for_strength`
and `reachable_landings(current, reach, way=...)`: in place; a neighbouring place, two places or
anywhere in the room; a blinking or phasing source crosses walls within reach, a flying one adds
the air above an unroofed place). A dodge whose roll at least partly succeeds
(`DEFENSE_REDUCED_THRESHOLD`) moves her there (`force_move_to_position`); otherwise she stays.
With no landing she dodges in place, and an away player, who sets nothing, dodges in place too.
Each round `begin_declaration_phase` turns dodging back on and clears the landing; the settings
below stand for the whole fight.

Beside it sit her standing dodge settings (`dodge_settings`, `DodgeSettingsAction` in
`actions/definitions/dodge_settings.py`; telnet `combat dodgewith <technique>|default`,
`combat dodgedefault <technique>`, `combat autopull <tier>|off`, and
`accept|decline dodgesoulfray` for the check-in): which technique answers her dodges in this
fight (`dodge_technique`; unset falls back to her saved `CharacterTechnique.default_dodge`, at
most one per character, then her strongest source), `dodge_into_soulfray`, and the auto-pull
with its saved tier. The participant payload's `dodge_plan` carries all of it
(`techniques` with each one's `cost_line`, `technique_id`, `into_soulfray`, `auto_pull`,
`auto_pull_tier`, `soulfray_check_in`) and reaches its owner only.

**Area attacks.** `ThreatPoolEntry.covers_place` hits everyone in the target's place
(`world/combat/services/npc/area_attacks.cover_place`, run before reach in
`_resolve_npc_action`). A wound-up one fixes its place when telegraphed
(`PendingOpponentAttack.covered_position`, copied to `CombatOpponentAction.covered_position`
at maturation) and the encounter payload's `pending_attacks` names it, so the map tints the
place and Your Turn warns whoever stands there. Only leaving escapes it: walking out on her
turn, or a dodge whose landing is outside the place (that dodge, at least partly
successful, takes no damage). With no landing outside, she does not dodge it (no cost) and
takes the plain defense roll.

**Guarding and catching.** Interpose and the Sent Flying catch count as reactions too, with
no cap; interpose's roll takes the same penalty. A guardian's repeat answer in one round
resolves a fresh Interpose challenge instance (`world.mechanics.reactions._fresh_reaction_instance`),
since a character resolves one instance once.

## Rampart interception (position-anchored barrier)

A `Rampart` (#2209) covering the target's `Position` chips first — upstream of every
personal defense above, and before `DAMAGE_PRE_APPLY` even emits.

- **Handler:** `apply_rampart_interception` (`world/combat/services/`), called at the top
  of `apply_damage_to_participant` and `_resolve_opponent_pre_apply`.
- **Content seed:** `ensure_rampart_content()` in `world/magic/effect_palette_content.py`
  (Stone/Wind/Fire/Thorn elemental profiles).
- **Scope:** position-anchored, faction-blind (ADR-0109) — covers everyone standing there,
  not a single bearer. See `docs/systems/areas.md`'s "Rampart — Living Barriers" section
  and ADR-0125 for the full model + firing-order detail.

## Guardian interpose precedence (declared and standing)

A hit on a PC ward is answered by at most one guardian. `_try_interpose`
(`world/combat/services/damage/interception.py`) tries, in order:

1. **Declared Interpose naming the ward** (`CombatRoundAction`), by participant id.
2. **Standing guards** (#4584, ADR-4584-A): a `source_guards_bearer` condition on the ward
   makes its source a guardian (`guardians_by_target`, oldest condition first), if she is
   an active participant, is not the ward, and **declared no Interpose this round**. A
   guardian with a declaration (naming this ward, another ward, or anyone) is tried only
   through it, so she is never tried twice for one hit. A guard cast on its own bearer never
   interposes.
3. **Declared guard-anyone Interpose**, by participant id.

All three reach the same tail, `_attempt_guardian_interpose`, so a standing guard counts
as one of her reactions this round (each one makes her next roll harder by
`MovementConfig.reaction_difficulty_step`, no cap, #4676) and against
`ABSORPTION_CAP_PER_MOMENT`, and pays interpose fatigue
(physical, very low effort: she declared nothing to read an effort from). She still takes
her own turn.

**Interpose fatigue rises per reaction [BUILT & WIRED] (#4810).** A mundane interpose
(declared or standing) charges its first cost, `INTERPOSE_BASE_FATIGUE_COST` x the effort
multiplier (floored at 1), times `(1 + step x reactions she already made this round)`, with
the step `MovementConfig.reaction_difficulty_step` (`interception.rising_reaction_cost`).
The effort scaling comes first so the floor cannot swallow the rise: a declared interpose
and a standing guard are both very low effort, and scaling after the rise floored all three
of 3, 9, 15 to 1. With the defaults a first, second and third interpose cost 1, 3 and 5 at
very low effort and 3, 9 and 15 at medium. A technique interpose
pays its anima as before. A guardian who cannot act (`can_act`: knocked unconscious, though still
ACTIVE) is never tried. An unavailable guardian falls through to the next; an attempt, even
a failed roll, ends the search. Standing guards cover PC wards in combat only: not an ALLY summon
ward, and not Sudden Harm outside combat. Absorb, reflect, blink and strike-back stay
outside both budgets (ADR-0161). A guard laid in round N holds from round N+1.

A standing guard that is declined by either budget uses the same private decline line as a
declared one (`_narrate_reaction_declined`, below).

## Defense styles: evasion, barrier, mitigation (#4809, slice 5 of #4759) [BUILT & WIRED]

`world.covenants.defense.defense_style_for(character)` returns a `DefenseResolution`
(`style`, `armor_share_tenths`). Both come from the character's `CombatStyle`
(`CharacterSheet.combat_style`); with no style, `style` is None and all armor counts (the
behavior before #4759). Until #4975 a character with no style fell back to the engaged
vow's `CovenantRoleDefenseProfile`; that table is gone (ADR-4975).

- **Armor share.** `apply_equipped_armor_soak` scales armor by the share once. The combat
  style's share reaches ALL worn armor, both compatibility buckets.
- **Evasion** defends through the automatic dodge below, unchanged. The dodge stays
  capability-driven for every style (#4651 decision 2: movement reads capabilities, never
  their source), so evasion's difference from the others is its lower armor share.
- **Barrier.** While an NPC blow resolves against a barrier defender, `absorb_pool` rolls
  `barrier_absorb_fraction` before it absorbs. The roll is the attack's own defence check
  (the threat entry's `defense_check_type`, the same difficulty and gathered modifiers,
  without the dodge bonus). On the defence ladder, 2 or more takes the whole blow, 1 takes
  half, and anything lower takes none. The ward is paid either way. With no NPC blow, or for
  any other style, the ward absorbs automatically as before.
- **Mitigation** (stored `gear_soak`). Armor soaks as normal. When the attacker's level
  beats the defender's `current_level` by more than `MovementConfig.mitigation_level_gap_cap`
  (default 3), `mitigation_leak_percent` (default 50) of what the armor stopped leaks back
  through (`mitigation_leak`).

`resolve_npc_attack` hands the defense to the damage pipeline through the
`npc_hit_defense` context variable (`NpcHitDefense`), entered beside `dodge_roll_active`.
It is only set for a barrier or mitigation defender, and it applies only to that
defender's own hit, never an interposer's. Journey:
`src/integration_tests/test_defense_style_journeys.py`.

## The healer's reactive save [BUILT & WIRED] (#4810)

`world/combat/services/damage/reactive_save.py`, called last in
`_run_pre_apply_interceptors` (after interposes and companion defense). When a blow's
pre-damage amount would drop a PC from above the knockout line to it or below, the first
ACTIVE participant of the same fight (by participant id) who can act, shares an active
covenant with her, holds an engaged vow with a `CovenantRoleTechniqueSpecialty` for
`TechniqueFunction.MEND` (resolved role or its anchor) and knows a technique tagged Mend,
and can pay, softens it. The gate is that capability, never a vow name; holding it is the
opt-in, as a dodging power is (no per-round toggle). The blow is cut to leave the ally
one point above the knockout line, by at most `MovementConfig.reactive_save_max_cut` percent
(default 50) of the blow. It is a reaction: `record_reaction` counts it, it
takes nothing from her declaration, it counts against `ABSORPTION_CAP_PER_MOMENT`, and it
costs `MovementConfig.dodge_anima_cost x (1 + reaction_difficulty_step x reactions_used)`
anima (non-lethal: she must hold that much). Both sides get a private line. "Would drop"
reads the amount before thread reduction, resistance, armor and cover, which run later.

## Barrier (force-field absorb)

A `DAMAGE_PRE_APPLY` interceptor drains a `ConditionInstance.absorb_remaining`
buffer.

- **Handler:** `absorb_pool` (`world/magic/services/effect_handlers.py`,
  priority 10). Mutation-only — overflow still lands.
- **Content seed:** `ensure_force_field_content()` in
  `world/magic/effect_palette_content.py` (Aegis Field).
- **Scope:** SELF — the trigger filter fires when `payload.target == bearer`.
- **Barrier defenders roll (#4809):** against an NPC blow, a barrier-style defender's ward
  takes all, half or none of the blow by a defence check (see "Defense styles" above).
- **Cost:** flat `reactive_anima_cost` billed to the applier (ADR-0118 reactive-costs); an
  instance with `soulfray_consented` (#3573) pays into deficit through `deduct_anima` and
  accrues Soulfray on every fire, so a caster can hold a ward for an ally past zero anima
  at their own soul's expense.

## When a defense does not fire (#3574, ADR-0271)

Every reactive protection that fizzles, lapses or is declined keeps its mechanical
no-op shape and narrates it. Private lines go through
`world.scenes.interaction_services.narrate_privately` (Narrator whisper, WS + telnet);
room lines go through `_broadcast_commitment_line` (combat, WS + telnet) and never carry
numbers.

| Event | Where | Who is told |
|---|---|---|
| Technique-guardian cannot pay `reactive_anima_cost` | `_narrate_technique_interpose_fizzle` (`world/combat/services/`) | guardian (private, names the unguarded ally); room (soft line) |
| Reaction declined by `ABSORPTION_CAP_PER_MOMENT` | `_narrate_reaction_declined` (`_attempt_guardian_interpose`, `_try_catch_sent_flying`), declared or standing guard | guardian only (private) |
| Ward lapses at upkeep | `_narrate_upkeep_lapse` (`drain_reactive_upkeep`) | payer (private, why); bearer if different (private, that); room |
| Standing ward cannot pay its fee | `_narrate_reactive_fizzle` (`world/magic/services/effect_handlers.py`, from `_try_spend_reactive`) | payer (private, why); bearer if different (private, that); room only inside an encounter |

The Guard panel (`YourTurn.tsx`, `guard-unaffordable-hint`) warns a guardian before the
round when their anima is below the selected technique's fee and Soulfray consent is off.

## Strike-back (answers after the hit lands)

Not part of the pre-apply pipeline: once a hit has landed on a PC and `DAMAGE_APPLIED` is
emitted, `_answer_with_strike_backs` (`world/combat/services/damage/damage.py`) calls
`strike_back` for each of the bearer's wards with `retaliation_damage` or
`retaliation_condition` (#4584). It only answers an NPC (`CombatOpponent`) attacker, pays the
ward's `reactive_anima_cost` (a fizzle is narrated per the table above), and its damage
counts as duel interference and probing as rampart retaliation does. A successful strike is
not narrated (known gap). It is outside both reaction budgets.

## Mitigation (armor soak + thread DR)

Flat damage reduction applied after evasion and barrier.

- **Thread DR:** `apply_damage_reduction_from_threads`
  (`world/magic/services/threads.py`). Subtracts a survivability baseline
  derived from thread investment.
- **Armor soak:** `apply_equipped_armor_soak(character, damage, damage_type)`
  (`world/combat/services/`). Only pieces that cover the hit's type count (#5026, above). Role-gated — compatible covenant-role armor
  adds on top; incompatible armor competes with a resonant pool via `max`.
  The share comes from `defense_style_for(character)`: a `CombatStyle`'s
  `armor_share_tenths` scales all worn armor; with no style, all armor counts. Which armor is
  "compatible" is the style's too (#4975): a weapon or armor kind must be listed on the style
  with the held vow, while clothing and jewelry always are. A mitigation defender's armor leaks part of what it stopped against an
  attacker past the level gap (see "Defense styles" above).
  See `docs/systems/covenants.md`'s "Defense styles + gear compatibility through the combat style" for detail.

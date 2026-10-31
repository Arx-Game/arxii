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
  → armor soak             flat subtraction, role-gated               (#508/#1174)
  → health
```

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

**The automatic dodge [BUILT & WIRED].** A character dodges an NPC attack that carries a
defense check when a capability she holds above its innate baseline has a
`CapabilityType.reaction_reach` other than `none`, or a Phase Step ward is on her
(`world/combat/services/reactions.py`, called from `resolve_npc_attack`). The dodge is her
defense roll with that capability's value added as a bonus (as a challenge adds its
capability source, ADR-0145), so the roll's normal degrees decide the hit. It costs
`MovementConfig.dodge_anima_cost` anima, or `dodge_fatigue_cost` physical fatigue when the
capability's `reaction_cost_kind` is `fatigue`; a Phase Step ward charges through its own
payer rule (`_try_spend_reactive`, #2208). If she cannot pay she does not dodge. Each
reaction she has already made this round takes `MovementConfig.reaction_difficulty_step`
off the roll (`reaction_penalty`); there is no cap. With no MovementConfig row the field
defaults apply (2 anima, 1 fatigue, step 2).

**The dodge plan.** `CombatParticipant.dodge_enabled` and `dodge_landing`, set while
declaring through `combat_dodge` (`DodgePlanAction`; telnet `combat dodge [<place>|here|off]`;
web Your Turn "If you're attacked this round"). A landing must be a place her strongest
reach covers (`dodge_landing_options`: in place; adjacent over open edges; airborne adds the
air above her place when that layer exists and the place is not roofed; any place). A dodge
whose roll at least partly succeeds (`DEFENSE_REDUCED_THRESHOLD`) moves her there
(`force_move_to_position`); otherwise she stays. With no landing she dodges in place. An away
player dodges in place too. The plan resets each round in `begin_declaration_phase`. The
participant payload's `dodge_plan` reaches its owner only.

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
her own turn. A guardian who cannot act (`can_act`: knocked unconscious, though still
ACTIVE) is never tried. An unavailable guardian falls through to the next; an attempt, even
a failed roll, ends the search. Standing guards cover PC wards in combat only: not an ALLY summon
ward, and not Sudden Harm outside combat. Absorb, reflect, blink and strike-back stay
outside both budgets (ADR-0161). A guard laid in round N holds from round N+1.

A standing guard that is declined by either budget uses the same private decline line as a
declared one (`_narrate_reaction_declined`, below).

## Barrier (force-field absorb)

A `DAMAGE_PRE_APPLY` interceptor drains a `ConditionInstance.absorb_remaining`
buffer.

- **Handler:** `absorb_pool` (`world/magic/services/effect_handlers.py`,
  priority 10). Mutation-only — overflow still lands.
- **Content seed:** `ensure_force_field_content()` in
  `world/magic/effect_palette_content.py` (Aegis Field).
- **Scope:** SELF — the trigger filter fires when `payload.target == bearer`.
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
- **Armor soak:** `apply_equipped_armor_soak`
  (`world/combat/services/`). Role-gated — compatible covenant-role armor
  adds on top; incompatible armor competes with a resonant pool via `max`.
  As of #2533, the compatible bucket is scaled once by
  `gear_additive_fraction(character)` (`world.covenants.services`) — the MAX
  `CovenantRoleDefenseProfile.gear_additive_tenths` fraction across the
  character's engaged roles, `1` (fully additive) with no profile. A vow whose
  `DefenseStyle` is EVASION or BARRIER rather than GEAR_SOAK ("Mitigation") can author a lower
  fraction so its own defense substitutes for gear instead of stacking with it.
  See `docs/systems/covenants.md`'s "Defense styles + gear substitution" for detail.

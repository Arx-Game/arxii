# Combat Defense Composition

Three defense modes layer in the damage pipeline. They compose — they are not
mutually exclusive. A character in plate with a force-field still rolls evasion
first; evasion scales the amount, then barrier/DR/soak layer on top.

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

## Rampart interception (position-anchored barrier)

A `Rampart` (#2209) covering the target's `Position` chips first — upstream of every
personal defense above, and before `DAMAGE_PRE_APPLY` even emits.

- **Handler:** `apply_rampart_interception` (`world/combat/services.py`), called at the top
  of `apply_damage_to_participant` and `_resolve_opponent_pre_apply`.
- **Content seed:** `ensure_rampart_content()` in `world/magic/effect_palette_content.py`
  (Stone/Wind/Fire/Thorn elemental profiles).
- **Scope:** position-anchored, faction-blind (ADR-0109) — covers everyone standing there,
  not a single bearer. See `docs/systems/areas.md`'s "Rampart — Living Barriers" section
  and ADR-0125 for the full model + firing-order detail.

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
| Technique-guardian cannot pay `reactive_anima_cost` | `_narrate_technique_interpose_fizzle` (`world/combat/services.py`) | guardian (private, names the unguarded ally); room (soft line) |
| Reaction declined by `REACTIONS_PER_ROUND` / `ABSORPTION_CAP_PER_MOMENT` | `_narrate_reaction_declined` (`_dispatch_interpose_action`, `_try_catch_sent_flying`) | guardian only (private) |
| Ward lapses at upkeep | `_narrate_upkeep_lapse` (`drain_reactive_upkeep`) | payer (private, why); bearer if different (private, that); room |
| Standing ward cannot pay its fee | `_narrate_reactive_fizzle` (`world/magic/services/effect_handlers.py`, from `_try_spend_reactive`) | payer (private, why); bearer if different (private, that); room only inside an encounter |

The Guard panel (`YourTurn.tsx`, `guard-unaffordable-hint`) warns a guardian before the
round when their anima is below the selected technique's fee and Soulfray consent is off.

## Mitigation (armor soak + thread DR)

Flat damage reduction applied after evasion and barrier.

- **Thread DR:** `apply_damage_reduction_from_threads`
  (`world/magic/services/threads.py`). Subtracts a survivability baseline
  derived from thread investment.
- **Armor soak:** `apply_equipped_armor_soak`
  (`world/combat/services.py`). Role-gated — compatible covenant-role armor
  adds on top; incompatible armor competes with a resonant pool via `max`.
  As of #2533, the compatible bucket is scaled once by
  `gear_additive_fraction(character)` (`world.covenants.services`) — the MAX
  `CovenantRoleDefenseProfile.gear_additive_tenths` fraction across the
  character's engaged roles, `1` (fully additive) with no profile. A vow whose
  `DefenseStyle` is EVASION or BARRIER rather than GEAR_SOAK can author a lower
  fraction so its own defense substitutes for gear instead of stacking with it.
  See `docs/systems/covenants.md`'s "Defense styles + gear substitution" for detail.

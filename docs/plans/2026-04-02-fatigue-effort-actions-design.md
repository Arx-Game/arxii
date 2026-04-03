# Fatigue, Effort Levels, and Character Actions Design

**Date:** 2026-04-02
**Status:** Approved design, ready for implementation

## Overview

Characters have three fatigue pools (physical, social, mental) that accumulate as
they perform actions during RP. Fatigue degrades performance through threshold-based
penalties and risks collapse at extreme levels. Players choose an effort level for
each action (halfhearted, normal, all out) that scales both cost and effectiveness.
All values feed into the existing modifier system for extensibility.

## Design Principles

- Fatigue is tactical (IC daily), not strategic (AP is the weekly resource)
- Each pool is independent — physical exhaustion doesn't affect social checks
- Visible effort levels create RP opportunities (the lazy swordmaster, the desperate scholar)
- Collapse risk rewards dramatic moments through intensity bonuses
- "Heroic by design" — you can always try, but pushing past your limits has real consequences

---

## 1. New Stats

Three new stats added to complete the endurance row across categories, plus Luck
as a meta stat. Perception and Willpower reclassified from their current categories
to Meta.

### Stat Grid (12 stats, 4 categories)

| Physical | Social | Mental | Meta |
|----------|--------|--------|------|
| Strength | Charm | Intellect | Luck |
| Agility | Presence | Wits | Perception |
| Stamina | Composure | Stability | Willpower |

### New Stats

- **Composure** (Social) — Social endurance. Poise under social pressure, resistance
  to embarrassment, ability to maintain a social facade over extended interactions.
- **Stability** (Social) — Mental endurance. Sustained focus, resistance to mental
  strain, ability to maintain concentration under duress.
- **Luck** (Meta) — Mechanical impact TBD (intentionally kept low-impact to avoid
  being overpowered). Included primarily for RP flavor.

### Reclassified Stats

- **Perception** — moved from Social to Meta. Awareness and observation.
- **Willpower** — moved from Mental to Meta. Determination and grit. Adds a minor
  bonus to ALL three fatigue capacities.

---

## 2. Fatigue System

### Three Independent Pools

Each character has three fatigue values that start at 0 and accumulate as actions
are performed. Higher fatigue = worse performance in that domain.

- **Physical Fatigue** — from physical actions (combat, athletics, labor)
- **Social Fatigue** — from social actions (persuade, seduce, entrance, perform)
- **Mental Fatigue** — from mental actions (research, puzzle-solving, magic, analysis)

Each pool is independent. High physical fatigue does not affect social or mental checks.

### Capacity

Base capacity = endurance stat * 10 + willpower * 3.

- Physical capacity = `Stamina * 10 + Willpower * 3`
- Social capacity = `Composure * 10 + Willpower * 3`
- Mental capacity = `Stability * 10 + Willpower * 3`

Well Rested condition adds +50% to all three capacities.

Multipliers are tunable and plugged into the modifier system — distinctions, spells,
and conditions can adjust capacity.

### Threshold Zones

Percentage of capacity determines the penalty zone:

| Zone | Range | Check Penalty | Collapse Risk |
|------|-------|---------------|---------------|
| Fresh | 0-40% | None | None |
| Strained | 41-60% | Light (-1) | None |
| Tired | 61-80% | Moderate (-2) | None |
| Overexerted | 81-99% | Heavy (-3) | On normal/all-out actions |
| Exhausted | 100%+ | Extreme (-4) | High on normal, near-certain on all-out |

Penalties apply only to checks using the fatigued pool's domain. All penalty values
are ModifierTarget-compatible for adjustment by distinctions, conditions, and spells.

### IC Daily Reset

Fatigue resets to 0 at IC dawn (6:00 AM IC time, aligned with the dawn TimePhase).
Cron announces the new IC day. If a character is in an active scene when dawn occurs,
their reset is deferred until the scene ends.

### Rest Command

- Usable once per IC day, must be at home (character's residence)
- Costs 10 AP
- Grants "Well Rested" condition: +50% fatigue capacity on next day's reset
- Messages: "You set some time aside to rest today." / "Time has already been set
  aside to rest today."
- The condition persists until consumed by the next dawn reset

---

## 3. Effort Levels

Three tiers that scale cost, check modifier, and collapse risk.

| Effort | Fatigue Cost | Check Modifier | Collapse Risk | Visible Tag |
|--------|-------------|----------------|---------------|-------------|
| Halfhearted | ~30% of base | -2 | None (safe even when exhausted) | `[Halfhearted ...]` |
| Normal | 100% of base | None | Yes, when overexerted/exhausted | `[Action Name]` |
| All Out | ~200% of base | +2 | High when overexerted, near-certain when exhausted | `[All Out ...]` |

All values (cost multiplier, check modifier, collapse threshold) are plugged into the
modifier system. Distinctions, spells, conditions, and social effects can adjust them.

---

## 4. Collapse Mechanic

When a character performs a normal or all-out action while overexerted or exhausted,
collapse risk triggers.

### Two-Stage Sequence

**Stage 1: Endurance Check**
- Roll the relevant endurance stat (Stamina for physical, Composure for social,
  Stability for mental) against the current fatigue level
- Difficulty scales with how far past the overexerted threshold they are
- If passed → action completes normally, no collapse

**Stage 2 (on failure): Power Through or Collapse**
- Player is prompted: "Your body/composure/mind is failing. Go unconscious, or
  power through?"
- **Accept unconsciousness** → character goes unconscious, scene continues without them
- **Power through** → Willpower check with bonuses from:
  - **Intensity** (high in combat/life-or-death moments)
  - **Dramatic context** (GM-assigned bonuses for narrative weight)
  - If Willpower succeeds → stay conscious, take strain damage scaled to
    `(current_fatigue - capacity) / capacity`
  - If Willpower fails → unconscious AND take the strain damage

### Strain Damage

Small base amount scaled by overexertion ratio. The further past capacity, the more
damage. Formula (tunable):

`strain_damage = base_strain * (current_fatigue - capacity) / capacity`

Where `base_strain` is a constant per fatigue type (physical strain = HP damage,
social strain = reputation/composure condition, mental strain = confusion/daze condition).

---

## 5. Character Actions in RP

### Action Format

All character actions are displayed as a structured header + freeform player writing:

```
[Halfhearted Making an Entrance]
Crucible slouches through the doorway, barely bothering to look up from
examining her nails. "Oh. You're all here. How... lovely."
```

```
[All Out Intimidate → Lord Vex]
The temperature drops. Crucible's eyes flare with barely-contained power as
she steps into Lord Vex's space. "You will tell me where the artifact is.
Or I will find someone else who knows."
```

The system tags the effort level and action name. The content is entirely player-written.
Other players see the tag and know the mechanical context.

### Action Categories

Actions are assigned to a fatigue pool and have a base fatigue cost:

**Physical Actions:**
- Combat actions (attack, defend, grapple)
- Athletic actions (climb, sprint, lift)
- Endurance actions (forced march, hold position)

**Social Actions:**
- Intimidate — applies Fear condition
- Seduce — applies Attracted condition (renamed from Entrance)
- Persuade — applies Convinced condition
- Deceive — applies Misled condition
- Flirt — applies Charmed condition
- Perform — applies Inspired condition
- Making an Entrance — aura farming, radiates presence/resonance
- Flourish — showcases accomplishment, adds resonance to gear/self

**Mental Actions:**
- Research — knowledge checks, codex investigation
- Analyze — puzzle-solving, deduction
- Channel — magical focus, technique preparation
- Strategize — tactical planning, battle preparation

### Contested vs Uncontested

- **Contested actions** (Intimidate, Seduce, Persuade, Deceive, Flirt) — require
  target consent. Target player sets difficulty (deny/easy/standard/hard) and receives
  kudos for being a good sport. Apply conditions on success.
- **Uncontested actions** (Making an Entrance, Flourish, Perform, Research, Analyze,
  Combat) — no target consent needed. Results apply to self or environment.

### Condition Application

Each contested social action maps to a condition it applies on success. Conditions
have limits on:
- Whether you can attempt it (prerequisites, cooldowns)
- How many times per scene/day
- Whether the target has already been affected by this condition recently

---

## 6. Development Points Integration

Actions feed development points for the traits they use. The existing `perform_check`
hook flags traits as "used" — the weekly cron converts usage to development points.

Each action type naturally exercises specific traits:
- Intimidate → Presence, Composure (attacker), Willpower (defender)
- Seduce → Charm, Composure
- Research → Intellect, Stability
- Combat → Strength/Agility + weapon skills, Stamina

Effort level affects development: going all-out on an action earns slightly more
development points than halfhearted attempts (you learn more by pushing yourself).

---

## 7. Modifier System Integration

All tunable values are implemented as ModifierTargets so they can be adjusted by
distinctions, spells, conditions, and equipment:

- `fatigue_capacity_physical`, `fatigue_capacity_social`, `fatigue_capacity_mental`
- `fatigue_cost_halfhearted`, `fatigue_cost_normal`, `fatigue_cost_allout`
- `effort_bonus_halfhearted`, `effort_bonus_allout`
- `collapse_threshold` (shifts when collapse risk begins)
- `strain_damage_multiplier`
- `fatigue_penalty_strained`, `fatigue_penalty_tired`, etc.

This enables things like:
- A "Second Wind" spell that reduces fatigue penalties for 1 scene
- A "Tireless" distinction that gives +20% physical fatigue capacity
- A "Berserker" condition that removes collapse risk but doubles strain damage
- Equipment that reduces fatigue cost for specific action types

---

## 8. Data Model Summary

### New Models

- **CharacterFatigue** — per-character fatigue state (physical, social, mental current
  values). Possibly a OneToOne on the character.
- **FatigueReset** — tracks deferred resets for characters in scenes at dawn
- **WellRestedCondition** — or use existing condition system if it supports this

### Modified Models

- **Trait** — add Composure, Stability, Luck stats. Reclassify Perception and
  Willpower to Meta category.
- **Interaction** — already has ACTION mode. Actions with effort level create
  ACTION-mode interactions with the effort/action metadata.

### Modifier System

- New ModifierTargets for all fatigue-related tunable values
- Existing CharacterModifier system handles the rest

---

## 9. Implementation Priority

1. **New stats** (Composure, Stability, Luck) + Perception/Willpower reclassification
2. **Fatigue model** (CharacterFatigue with three pools)
3. **Fatigue capacity calculation** (stat-based + modifier-based)
4. **Effort level system** (cost scaling, check modifier, visible tags)
5. **Fatigue threshold penalties** (zone calculation, check penalty application)
6. **IC daily reset cron** (dawn-aligned, scene deferral)
7. **Rest command** (AP cost, Well Rested condition)
8. **Collapse mechanic** (two-stage: endurance check → willpower power-through)
9. **Action pipeline integration** (wire fatigue cost/penalty into existing check system)
10. **Social action conditions** (map each action to a condition type)
11. **Development point hooks** (trait usage flagging from actions)

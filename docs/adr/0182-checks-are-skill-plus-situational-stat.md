# Checks are skill + situational stat

Date: 2026-07-31
Status: Accepted
Supersedes: the "stat + skill" formulation in `docs/roadmap/design-tenets.md`

## Context

Issue #2757 identified that the CheckType catalog had two implicit shapes —
skill-constant (Melee Attack = strength + Melee Combat) and stat/situation-constant
(Break and Enter = strength + Athletics) — with no rule for which to use when
authoring a new check. This ambiguity caused real damage: the #2691 legacy audit
found 15 vaguely-named CheckTypes with no composition, and 142 of 191
`ConditionCheckModifier` rows targeting checks nothing rolled.

The deeper problem: the stat was fixed per CheckType, so a knife-fighter and a
warhammer-wielder both rolled "Melee Attack = strength" — the character concept
had no mechanical reflection.

## Decision

A CheckType's identity is its skill; the stat is situational. The calling system
determines the stat from physical context (weapon type, barrier type) and passes
it via a `stat_override` keyword-only parameter on `perform_check`.

- `stat_override=None` (the default) is byte-identical to pre-#2757 behavior.
- When set, `_calculate_trait_points` replaces the CheckType's STAT-type traits
  with the override stat's value, borrowing the weight from the first STAT trait.
- SKILL-type traits always contribute.
- Valid only for checks with 0 or 1 STAT-type traits; 2+ stat checks log a warning.

Physical-action checks merge to one-per-skill: "Melee Attack" + "Melee Defense"
→ "Melee Combat"; "Break and Enter" + "Escape Through Window" → "Athletics".
Social, investigation, resist, and multi-stat checks stay separate.

## Consequences

- One skill investment covers multiple stat situations (a Melee Combat specialist
  fights with agility or strength depending on weapon).
- Modifier targeting at the CheckType level covers all stat variants; stat-specific
  targeting is covered by equipment-level and capability-level mechanisms.
- The weapon→stat mapping is authored content, not engine logic — it can be
  refined from the coarse initial `GearArchetype` mapping to a finer weapon-class
  mapping in a content follow-up. **Done (#2858, superseded #2879 — see ADR-0189):**
  `ItemTemplate.weapon_class` now FKs to a `WeaponClass` lookup table carrying a
  weighted strength/agility blend (replacing #2858's small/medium/heavy override),
  taking precedence over the archetype map, with null falling back to it, so the
  refinement rolls out per-template as content is authored rather than as an
  engine change.
- The GM ad-hoc check model (ADR-0110) uses the default stat — the question of
  whether GMs should select from a stat palette or whether checks should emerge
  from authored situations is a separate follow-up.

# ADR-4783-A: A modifier targets a declared effect; maneuver effects are a fixed catalog

**Date:** 2026-10-31
**Status:** Accepted (spec approved on #4783)
**Issue:** #4783. Amends ADR-0126 (the flat Charge numbers) and ADR-0149 and ADR-0108 (the vow-only
action scaling table, now removed). Relates ADR-0010 (FK direction) and ADR-0007 (no JSON fields).

## Decision

A maneuver (Charge, Cover, Succor, Interpose, Rally) declares its numbers as named **effects**,
and a modifier from any source points at an effect through a `ModifierTarget`.

- **A modifier targets a declared effect.** The eight effects are rows of `ManeuverEffect` (`key`,
  `base_value`, staff `notes`). A target in the "maneuver effect" category scopes to one effect
  (`scope_maneuver_effect`) or to one kind of effect across every maneuver (`scope_effect_kind`),
  exactly one of the two; a target with neither matches nothing. Vows, distinctions, crafted
  recipe modifiers, facet and mantle crossing-choice conditions and active conditions all reach an
  effect through the same target (a facet's own flat bonus does not), and `effect_value(sheet, key)` is
  the one reader: base value plus the matching modifier totals, never below 0, and partial
  protection never above 100.
- **Maneuver effects are a fixed catalog, with no situation table.** Maneuvers stay verbs that
  code fires at set moments. Only their numbers moved into rows, so staff can see and change them.
  The admin has no add and no delete and the key is read-only; code finds a row by `key`, never by
  name. There is no lookup table that picks an effect from the circumstances: a circumstance lives
  in the source (a condition that lasts a while) or in the target's scope, never in a separate
  "when" on the modifier.
- **Each effect kind fixes the unit of every modifier that targets it (decision 8).** To hit,
  damage, reach, escape bonus, partial protection, morale and surge intensity each have one unit
  (points, hops, percentage points). A broad target such as "damage, any maneuver" therefore adds
  the same sort of number everywhere it applies. If a kind turns out to need two units, it is
  split in two. The kind is derived from the key by a constant map, not stored.
- **A modifier on an effect is a flat amount for now (decision 9).** A sized modifier ("Large at
  level 6") needs a value table per effect kind, and filling those tables is tuning, so it waits.
  A distinction effect with a size on a maneuver effect target is refused by `clean()` ("Maneuver
  effects take flat amounts only; clear the size."), and so is a rank size row on such an effect,
  so a sized amount can never silently count as its flat value.
- **Derived amounts are their own later design (decision 10).** A source row choosing what its
  number scales from is not built. The fixed-input forms keep working: per thread level, per
  character level, per condition severity.
- **Targets keep holding their own scope links (decision 11).** `ModifierTarget` already carries
  seven specific-system links (`target_trait`, `target_being`, `target_damage_type` and others);
  the two new scope columns follow it rather than moving the link to a table on the specific side.
- **Vow scaling on an effect counts the shown thread level.** A thread's stored level is ten times
  the level a player sees. A stat is stored the same way, so a stat bonus multiplies the stored
  level; a maneuver effect is in natural units (damage, percent, hops, morale), so a vow's bonus
  on an effect target multiplies the shown level (stored // 10). Other categories keep the stored
  level. `vow_stat_scaling_bonus` also reads rows on both an engaged role and its anchor role, so a
  holder who graduated to a sub-role keeps their scaling, with the thread level read from the
  anchor. Vow scaling reads the holder's engaged PRIMARY roles only; a secondary or minor vow adds
  nothing to an effect.
- **The Rally roll line says "surge +N".** When a rallier's surge intensity is above 100% the extra
  intensity is noted on the ally's roll line as "surge +N". It is the intensity the effect added,
  from any source, so the note no longer says "vow scaling".

`CovenantRoleActionScaling`, `CovenantScaledAction`, `covenant_role_action_scaling_bonus`,
`FleeConfig.cover_bonus` and the constants `CHARGE_CHECK_BONUS`, `CHARGE_DAMAGE_BONUS`,
`CHARGE_MAX_HOPS`, `FLEE_COVER_BONUS` and the combat `RALLY_MORALE_PER_LEVEL` are gone. The battle
Rally keeps its own `RALLY_MORALE_PER_LEVEL`: it is a different action, a unit-level battle
command.

## Why

Staff could not author "+3 to Charge damage" or "this vow makes the partial protection you give
allies stronger". A maneuver's parts were numbers written into code, and the one vow table that
tried to scale them made each row guess which part of the maneuver it meant, and only vows could
use it. Naming each part as an effect gives every source one thing to point at, at any breadth, and
nothing changes except that effect. With no modifier anywhere every maneuver gives the numbers it
gave before (the catalog rows carry today's values).

The scope links stay on the target because a target that later combines two scopes (a gift and an
opponent property) would otherwise have to be found by joining across several link tables, one per
scope, on every read of every modifier. The two new columns are separate foreign key and choice
columns, not the identity links that `target_resonance` and `target_damage_type` are, so a later
slice can add "technique", "damage type" and "opponent property" scopes the same way.

## Amendment, 2026-10-31 (#4822, slice 2 of #4783)

Technique scopes landed as the "later slice" decision 11 expected: five more nullable columns on
`ModifierTarget` (`scope_technique`, `scope_gift`, `scope_technique_function`, `scope_damage_type`,
`scope_resonance`), not link tables, and two new effect kinds (condition severity, condition
duration). They combine, an unset scope means any, and a technique scope needs a kind and no single
maneuver effect, so the decision 8 unit rule holds. A kind-only damage target is counted once in a
Charge: the technique's own damage term reads it, and the Charge damage effect reads only targets
scoped to "Charge: damage". Opponent scopes remain #4823; decisions 9 and 10 (flat amounts only,
derived amounts later, #4824) are unchanged.

## Amendment, 2026-10-31 (#4823, slice 3 of #4783)

Opponent scopes landed as the third "later slice" decision 11 expected: two more nullable foreign
key columns on `ModifierTarget` (`scope_opponent_property`, `scope_opponent_condition`), not link
tables, with the technique scopes' rules: they combine, an unset scope means any, and they need a
kind and no single maneuver effect. They narrow damage, condition severity and condition duration.
What an opponent "has" is read once per opponent and only while an opponent-scoped target exists:
a property is a stored `ObjectProperty`, one an active condition's template or current stage
grants, or a character's primary persona tag; a condition is an active, unsuppressed instance.
Condition bonuses are worked out per target rather than once per cast, so a cast that lands one
condition on several targets can give each a different amount. Single maneuver effects and to hit
take no opponent scope, and decisions 9 and 10 are unchanged.

## Rejected

- **Link tables on the specific side (ADR-0010's preference).** One table per scope, each pointing
  at `ModifierTarget`, keeps the general model free of imports, but a target combining scopes then
  needs a join across all of them, and the reader would query each table per effect read. The
  general model here already imports the specific ones, so the dependency cost is already paid.
- **A situation table that picks an effect.** A table mapping circumstances to effects would make
  maneuvers data-driven in a way staff cannot reason about, and would re-create what a condition
  already is. Maneuvers stay fixed verbs.
- **Folding the numbers into technique effect rows.** Those rows are per technique and carry power
  scaling maneuvers do not use; the owner chose a separate catalog.
- **A separate "when" on a modifier.** The circumstance belongs to the source or to the target's
  scope.
- **Keeping the vow-only action scaling table.** It could scale only maneuvers a vow named, by
  guessing which part it meant; vow stat scaling rows on effect targets say the same and more.
- **Sized modifiers and derived amounts in this change.** Both need tuning tables or a source
  design of their own.

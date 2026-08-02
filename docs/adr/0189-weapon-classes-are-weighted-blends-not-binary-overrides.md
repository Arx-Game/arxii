# Weapon classes are weighted blends, not binary overrides

#2858 gave `ItemTemplate` a `weapon_class` small/medium/heavy override that replaced a
combat check's STAT trait wholesale by gear archetype — a tabletop artifact where most
weapons are actually a strength/agility mix, not a pure pick. #2879 (2026-08-01
crafting/equipment design session) replaces the binary override with a proper
`WeaponClass` lookup table carrying a `strength_tenths` weight (0-10; agility is 10 minus
it), so an off-stat weapon contributes a visible slice of offense instead of being
worthless.

## Decision

`WeaponClass` is a `SharedMemoryModel` lookup table (`name`, `strength_tenths`,
`gear_archetype` — advisory only, `default_damage`), FK'd from `ItemTemplate.weapon_class`
(nullable, `PROTECT` — null falls back to the coarser `GearArchetype` stat map). The
check-resolution seam (`world.checks.services._calculate_trait_points_with_override`)
accepts an `int` `stat_override` (0-10) alongside its pre-existing `str` (single trait
name) form and substitutes `(strength * w + agility * (10-w)) / 10` for the check's STAT
trait. The 2+ STAT-trait guard added in #2757 is kept for both the `str` and `int`
forms — a substituted value, blended or not, still can't correctly replace two
independently-weighted STAT traits.

## Rejected alternatives

Keeping the small/medium/heavy `TextChoices` override and adding a third "mixed" bucket
was rejected because a fixed bucket count still can't express the grid's real spread (0/10
through 9/1) without either coarse buckets or an explosion of enum members. Removing the
2+ STAT-trait guard for the blend path was rejected as a real regression risk for the
(currently rare, but documented) dual-STAT check case.

## Consequences

Existing `ItemTemplate` rows using the small/medium/heavy override (3 of the seed
catalog's reference templates — Longsword, Greatsword, Recurve Bow) were reclassified to
named `WeaponClass` rows; no data migration was needed since the dev DB carries no other
meaningful `weapon_class` values pre-production (ADR-0013). The weapon-class catalog is
admin/seeder-authored content, like the rest of the reference item catalog
(`world/seeds/game_content/items.py`'s `get_or_create` pattern) — not lore-repo content:
`items.WeaponClass` and `items.ItemTemplate` are not in `CONTENT_MODELS`, so authoring the
full 15-class grid there would first require adding both to that registry.

> Status: accepted · Source: #2858, #2879 · Confidence: built and wired —
> `world.items.models.WeaponClass`, `ItemTemplate.weapon_class`,
> `world.combat.stat_mapping.weapon_stat_override`,
> `world.checks.services._calculate_trait_points_with_override`. The full 15-class weapon
> grid is not yet authored as content.

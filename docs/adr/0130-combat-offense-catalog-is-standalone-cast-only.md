# The combat offense flavor catalog applies to standalone casts; combat rounds deliberately do not consume ActionTemplate.consequence_pool

`world.combat.seeds_offense` (#1995) mirrors `world.magic.seeds_cast`'s base-pool +
curated-catalog pattern for the combat "Melee Attack" `ActionTemplate`: a base
"Combat: Melee Offense" `ConsequencePool` (3 canonical tiers) plus two curated flavor
children ("Brutal", "Precise"), each with its own `ActionTemplate` (same `check_type`/
`pipeline`/`target_type` as the base — only `consequence_pool` differs).
`resolve_cast_action_template` (`world.magic.services.technique_builder`) picks up the
combat catalog exactly as it already did the magic one: a PHYSICAL technique's chosen
flavor validates against `get_combat_offense_catalog()`, everything else against
`get_technique_cast_catalog()`.

This catalog is reachable ONLY through the standalone-cast resolution pipeline
(`actions.services.start_action_resolution` → `_run_main_step` → `get_effective_consequences`),
which a PHYSICAL technique reaches by resolving its `action_template` — the same seam a
non-PHYSICAL technique already used for the magic catalog. **Combat ROUND resolution
does not read `ActionTemplate.consequence_pool` at all** — it resolves its own
combat-specific pools (`on_hit_consequence_pool`, `resolution_consequence_pool`,
`per_round_consequence_pool`, `break_in_consequence_pool` on combat models) through a
separate code path (`world.combat.services`/`world.combat.clash`) that never touches
`start_action_resolution`. Wiring the base pool onto "Melee Attack" (`consequence_pool`
was previously always `None`) is therefore safe for combat rounds — they were never
reading that field and still aren't.

**Rejected alternative:** resolve a weighted flavor pick inline during combat round
resolution (i.e. thread the chosen `ConsequencePool` through the round's own
consequence machinery so a PC's flavor choice colors their round-by-round hits, not
just standalone casts). Rejected because combat rounds are the hottest resolution loop
in the game — every participant, every round — and this catalog's job is graded flavor
text for a single roll, not round-scale damage/effect resolution; folding it in would
mean a second weighted-consequence draw per technique use inside that loop for a
purely cosmetic payoff, doubling resolution cost where it's least affordable. Standalone
casts (where the catalog already lives for magic techniques) pay this cost once, outside
any hot loop.

> Status: accepted · Source: issue #1995 · Related: ADR-0096 (casts roll the caster's
> personal check in every path); extends the #1320 magic technique-cast catalog pattern

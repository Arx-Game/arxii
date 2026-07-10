# GM battle staging is catalog-pick-and-instantiate, with parallel blueprint/live models

A JUNIOR-trust GM stands up a Battle from `BattleMapBlueprint`/`BattleUnitTemplate` catalog
rows (#2010) rather than authoring terrain/fortification layouts or unit stat blocks
free-form at stage time — the same catalog-first shape ADR-0110 already governs for
situations/challenges/checks: build the catalog, make it fast to search
(`browse_battle_catalog`), and gate invention itself. `stage_battle`/
`instantiate_battle_blueprint`/`spawn_units_from_template` (`world.battles.staging`) only
ever *copy* an existing, admin-authored catalog row onto a live `Battle`'s own rows — no
staging Action accepts a free-form terrain type, fortification kind, or unit stat block.

The catalog is a second, parallel set of models (`BattleMapBlueprint` →
`BlueprintBattlePlace` → `BlueprintFortification`; `BattleUnitTemplate` +
`BattleUnitTemplateCapability`) rather than reusing `BattlePlace`/`Fortification`/
`BattleUnit` with a nullable `battle` FK. A blueprint's places/fortifications have no
battle to belong to and no `BattleSide` to resolve `defending_side` against yet —
`BlueprintFortification.defending_side_role` stores the *role* (`ATTACKER`/`DEFENDER`)
and is only resolved to a concrete `BattleSide` at instantiation time
(`instantiate_battle_blueprint`). A nullable-FK reuse would force every live-battle query
and every #1711-#1794 modifier-stack read to filter out catalog rows, and would let a
blueprint's rows accidentally participate in round resolution if a filter were missed.
Two small, explicit catalog models (mirroring `PositionBlueprint`/`BlueprintPosition`/
`BlueprintEdge`'s shape in `world.areas.positioning`, #2005-#2011) keep the catalog and
the live-battle graph structurally incapable of crossing.

This extends ADR-0081 (battle terrain lives on `BattlePlace`, not the room
`Position`/`PositionEdge` graph) and ADR-0085 (`BattlePlace` gains an internal, battle-scoped
coordinate plane) rather than reversing either: `BattleMapBlueprint` still targets
`BattlePlace`'s own shape (`terrain_type`/`movement_cost`/`x`/`y`/`footprint_radius`), not a
room position graph, and staging still produces location-less battles by default
(`stage_battle`'s `location` kwarg is opt-in — see `staging.py`'s module docstring).

Rejected: **reusing `PositionBlueprint`** (`world.areas.positioning`, the room-scoped
tactical-position blueprint #2005-#2011 built) for battle maps — it applies a template to a
*room*'s `Position`/`PositionEdge` graph, which is exactly the abstraction ADR-0081 kept
separate from mass battles (hundreds of PCs, abstract fronts, no positional room to anchor
to); reusing it would re-litigate that decision by the back door. Rejected: **GM free-form
authoring at stage time** (an open terrain-type/fortification-kind/unit-stat text form) —
the precedent ADR-0110 already rejected for checks/situations for the same reason: it
produced inconsistent, non-canonical rulings across tables in Arx I. A GM who wants a new
map/unit shape authors it once in the catalog (admin), then every table reaches the same
row.

> Status: accepted · Source: #2010 · Related: ADR-0081 (location-less battles,
> `BattlePlace` vs. the room position graph), ADR-0085 (`BattlePlace`'s internal
> coordinate plane, additive to ADR-0081), ADR-0110 (GM content is catalog + adaptation,
> never invention — the precedent this extends into battle staging)

# Positioning glossary

**Position kind**:
The classification of a position node within a room's spatial graph: PRIMARY (the default open region), FEATURE (an authored sub-region like a balcony, altar, or pit), ELEVATED (a raised rim such as a catwalk), AERIAL (a flight-only twin layer auto-created above ground positions), CHASM (a below-ground drop reached by falling), and the reserved BARRIER_SIDE (dynamic carving).
_Avoid_: position type, terrain type, zone kind

**Blueprint**:
A reusable, room-independent template of position nodes and edges that a GM authors once and instantiates onto any room to generate a live position graph, used for staging non-combat scenes.
_Avoid_: layout, template map, stage preset

**Aerial layer**:
The flight-only twin graph materialized above a room's ground positions — each ground node gains an "Above <name>" twin connected by a vertical edge, with horizontal aerial edges mirroring ground adjacency but all freely passable so airborne objects fly over walls and gates. It exists only while airborne objects occupy the room and is torn down when the last one lands.
_Avoid_: flight layer, sky layer, air zone

**Plummet**:
The escalating fall that begins when an entity enters a CHASM position and the FELL event fires: it ensures a danger SceneRound, applies the staged "Plummeting" condition to the faller, and instantiates a "Catch the Faller" challenge, descending each round until caught or resolved.
_Avoid_: fall, drop, falling

**Knockback** (combat term, not positioning-owned):
See `world/combat/AGENT_GLOSSARY.md` — positioning provides the `AWAY_FROM_ACTOR` destination primitive; combat owns the term and authoring surface.

**Take a position** (#2005):
An unplaced actor's voluntary first entry onto a room's position graph — restricted to PRIMARY/FEATURE positions (the ground entry kinds) and gated on the MOVEMENT capability, via `take_position()`/`TakePositionAction`/telnet `position <name>`. Distinct from moving (`move_to_position`, which requires already being placed and an edge to the destination) and from GM placement (`place_in_position`, the unchecked primitive that bypasses both restrictions).
_Avoid_: enter a position, join the grid, spawn onto the graph

**Rampart** (#2209, epic #2040 decision 3):
A projected living barrier — a `Rampart` model row one-to-one on the `Position` it covers, with a shared `integrity`/`max_integrity` pool, a `RampartElementProfile` FK (Stone/Wind/Fire/Thorn, each an authored damage-resistance/vulnerability set plus one signature behavior), and a `crack_state` property (INTACT/CRACKED/CRUMBLING) that drives the tactical map's ring rendering. Position-anchored and faction-blind, like ADR-0109's conjured obstacles — it covers everyone standing there, not a chosen side. Combat owns the interception/clash-wiring seam; see `world/combat/AGENT_GLOSSARY.md`. See ADR-0125 for why it's an entity rather than per-bearer group conditions.
_Avoid_: ward, barrier, bulwark, shield wall (all already claimed by other systems)

**Wall integrity** (#4606, slice 1 of #4576):
How much damage a conjured wall on a `PositionEdge` can still take before it falls and the edge opens (`integrity`/`max_integrity`; both null = indestructible, as staff-authored edges are). A spell wall is raised with integrity from its cast; a Rampart's seal has none of its own and reads the Rampart's pool through `source_rampart`, so the Rampart's collapse, expiry or teardown opens every edge it sealed. `damage_barrier` is the one seam that lowers it; its caller for a plain wall is an NPC's bash (#4609, see the combat glossary), and `is_breakable_barrier` / `barrier_integrity` read it for the bash test. Distinct from getting past a wall through its gating challenge (the climb or smash, ADR-0109), which opens the edge without touching integrity: the **walker rule** (`edge_blocks_crossing`) reads a sealed edge whose challenge is resolved as open.
_Avoid_: wall HP, barrier health, hardness

**Traversal** (#4607, slice 2 of #4576):
How a mover crosses the position graph (`CreatureTraversal`: WALKS, CLIMBS, LEAPS, FLIES). A walker crosses only what the walker rule leaves open. A climber or leaper also crosses a wall that has a way past it (an active gating challenge) for one extra hop, and the two differ in narration only. A flier also uses the aerial layer, so it passes over any wall that does not block flight. A hard seal stops everyone on the ground. `edge_crossing_cost` turns an edge and a traversal into hops, and `find_path` routes over it. Staff set it on a creature template; it is not derived from tier.
_Avoid_: movement mode, locomotion, move type

**Held ground** (#4663):
A position a ready enemy stands in, seen from the mover's side (`held_position_ids_against`: for a PC the places of ACTIVE ENEMY opponents; for an opponent, the places of acting participants and ALLY opponents). A player character who enters it, however she moves on the ground (landing included), stops there and loses the rest of the round's hops (NPC walkers and climbers stop; NPC fliers and leapers pass); the mover's own place is never held against her. Routing treats it as the end of a route (`stop_at`). It is passed by a roll (see **Pass**), not by moving through it.
_Avoid_: blocked place, zone of control, chokepoint

**Pass** (#4663):
The roll a character with a matching capability makes to get past held ground (`attempt_pass`, `PassHeldGroundAction`, `position/pass <name>`) against the `MovementConfig.held_ground_challenge` template. Clean and partial both end in the held place with her hop spent (partial carries the template's authored consequence, which must target `self` to hit her); stopped ends there with no hops left. Distinct from getting past a wall's gating challenge, which opens an edge for everyone.
_Avoid_: dodge, break through, slip past

**Player traversal** (#4663):
A player's `CreatureTraversal` set, read from her capabilities: WALKS always, plus each `CapabilityType.traversal` whose capability she holds above its `innate_baseline` (`player_traversals`). It replaces a staff-set creature field for players, so a flier from a species modifier and one from a technique move the same way. See **Traversal**.

**Hop** (#4607):
One step along a `PositionEdge`, the unit of movement on the battle map. Crossing a wall with a way past it costs a climber or leaper two hops, and taking off into the aerial layer or landing costs one.
_Avoid_: tile, step (in code). A **square** is not a hop; see **Square**.

**Strike reach** (#4607):
Whether a strike lands from one position on another, by its delivery (`strike_reaches`): melee needs the same or an adjacent position, and a missile reaches anywhere in the room. A combatant with no position is always in reach. PC techniques keep their own reach value through `technique_can_reach`; both read `position_reachable`.
_Avoid_: range, line of attack

**Roofed position** (#4608, slice 3 of #4576):
A position with overhead cover (`is_roofed`). No strike of any reach or delivery passes between it and any AERIAL position (`roof_between`), even its own aerial twin across the vertical edge, and no mover flies straight down into it or up out of it: a flier lands beside it and walks in. A forced landing ignores the roof. A position fact, not a shelter row (ADR-4608-A).
_Avoid_: covered position (cover means shelter rows and the cover maneuver), indoors

**Screened position** (#4608):
A position that breaks line of sight (`screens_ranged`). A missile or room-wide strike at someone there must come from that position or one beside it (`screen_blocks`); melee is unaffected. Walls and Ramparts do not block line of sight.
_Avoid_: concealed, hidden (concealment is a casting term), blind

**Grounding** (#4608):
Knocking a flier out of the air (`REMOVE_FLIGHT`, `ground_flier`). It is a fall through the plummet rules, not the soft landing `leave_aerial` gives: a character gets the catch window and lands at the end-of-round tick; a combat opponent lands at once with the fall damage on its health. The fall has no source, so it never kills.
_Avoid_: landing, knockdown

**Place area** (#4670, slice 1 of #4651):
The rectangle a place is drawn as on the battle map, in map squares: `area_x`, `area_y`, `area_w`, `area_h` on `Position` and `BlueprintPosition`. All four are set or all four are null; a width and height are at least 1. A place with no area is drawn as a derived 3x2 box and takes no square. Drawing only: the place stays the rule.
_Avoid_: zone, room box, region

**Square** (#4670):
One cell of the battle map's grid. A token stands on a square inside its place's area (`ObjectPosition.square_x`, `square_y`, both or neither). `step_to_square` moves to another square of the same place for free; a move that names no square clears it. Drawing only: no hop, reach, hold or roll reads a square. Not a **Hop**.
_Avoid_: tile, cell, hex, grid position

**Map terrain** (#4670):
A named ground look (`MapTerrain`: a name and tile art) that staff set on a place so the map draws wood planks or flagstones under its area. Drawing only: no rule, roll or cost reads it.
_Avoid_: tile, ground type, biome, floor

**Feature type** (#4675, slice 3 of #4651):
A staff-authored catalog row (`FeatureType`) for a thing a place can hold that a stunt uses: a chandelier, a rope, a balcony rail. It names its art, its **reach** and the challenge template that is rolled against. Defined once, attached to any place. Not the `world/room_features` app, which means lab stations and other room fittings.
_Avoid_: prop, fixture, room feature, obstacle (a conjured obstacle blocks an edge; a feature opens a way)

**Feature** (#4675):
A feature type standing in one place (`PositionFeature`), optionally on one of the place's squares; `BlueprintFeature` is the same on a blueprint place and is copied when the blueprint is staged. A GM adds and removes live ones with `gm_attach_feature` and `gm_detach_feature`. Drawing only apart from the stunts it offers.
_Avoid_: prop, fixture, object

**Reach** (#4675):
The rule on a feature type for where a stunt from it can end, measured from the feature's own place: ADJACENT (any edge, passable or not), ANY_PLACE, SAME_TYPE (another place with the same feature) or ELEVATED_ADJACENT. Distinct from hop and strike reach (see **Traversal**).
_Avoid_: range, destinations rule

**Stunt** (#4675):
Using a feature in your own place to reach another place by rolling the feature type's challenge (`perform_stunt`). The approach is the strongest her capabilities match. A clean or partial result moves her; a miss leaves her where she was and applies the template's consequences. Either way a declaring round spends one hop, and landing in held ground stops her. NPCs do not make stunts.
_Avoid_: trick, jump, special move

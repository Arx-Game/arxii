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

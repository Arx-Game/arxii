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

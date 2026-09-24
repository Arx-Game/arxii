# ADR-0109: Relationship bond combat bonus is unconditional and cube-root-scaled

#2021 wires the orphaned `CharacterRelationship.mechanical_bonus` (cube root of
developed absolute value) into combat as a co-combat passive. The bonus follows
ADR-0092's unconditional-investment principle: any active, consented relationship
above an authored floor qualifies — rival or lover alike, positive or negative
track. The bonus is flat per-check (not compounding), applied to all combat
checks (offense, defense, flee, clash), and drops when the bonded ally falls
(handing off to #2013's grief spike). Soul Tether grants a config-multiplied
strongest tier via one lookup in the same passive.

The rejected alternative was positive-track-only qualification (only net-positive
affection relationships grant the bonus). This was ruled out because it
contradicts ADR-0092's established principle that PC-to-PC investment is rewarded
unconditionally — the "enemies to lovers" design goal requires that a rival
fighting beside their rival gets the same modest bonus as a lover beside their
lover.

**Amended by ADR-0308 (#3957, 2026-09-21).** The *principle* above is unchanged — bond
investment is rewarded unconditionally, rival or lover alike — but the mechanism it names is
gone. `CharacterRelationship.mechanical_bonus` and `BondCombatConfig.min_developed_absolute_value`
were dropped with the track/points shape (`src/world/migrations/0150_ties_redrawn.py`). Today
`bond_combat_bonus` qualifies a side whose **claimed** `tier` reaches `BondCombatConfig.min_tier`
and grants that tier's authored `RelationshipTier.combat_bonus`, still flat per check, still
one-sided, still doubled by a live soul tether, still dropping when the ally falls. Read
`combat_bonus` wherever this ADR says "cube root of developed absolute value", and "claimed tier
at or above `min_tier`" wherever it says "above an authored floor".

> Status: accepted · Source: #2021, ADR-0092

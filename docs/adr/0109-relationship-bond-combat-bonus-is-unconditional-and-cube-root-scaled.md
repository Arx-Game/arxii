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

> Status: accepted · Source: #2021, ADR-0092

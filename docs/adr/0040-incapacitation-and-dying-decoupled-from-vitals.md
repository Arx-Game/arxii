# Incapacitation & dying decoupled from a single vitals enum

Mortality (`CharacterVitals.life_state`: alive/dead) is split from capability and consciousness, which
are modeled as conditions (Unconscious, Bleeding Out) rather than as rungs of one
`ALIVE→DYING→DEAD` ladder; we rejected the single-enum ladder. A linear enum made states like "dying
but still conscious" unrepresentable, so the axes are kept independent.

> Status: accepted · Source: #595 · Confidence: derived-from-roadmap, verify against code

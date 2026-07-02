# Succor is a RoundContext capability; location shelter is a hard gate, not arithmetic resistance

An ally protecting a target from a round-ticked environmental hazard (Succor) is a method on the
`RoundContext` protocol (`get_cover_for`), implemented per concrete round family — combat extends
`CombatRoundAction`'s existing maneuver machinery, scene rounds extend `SceneActionDeclaration` — rather
than a new cross-domain model. `world.conditions`/`world.vitals` only ever see a plain float multiplier,
never a combat- or scene-specific type, so the round-tick DoT path stays domain-agnostic (ADR-0015: no
GFK/polymorphism; ADR-0016: share via abstract base/seam, not duplicated models). Separately, a
location's shelter against a hazard (`LocationValueOverride`/`Modifier`'s new `DAMAGE_TYPE` axis) is a
hard gate on whether the hazard-triggering condition is ever applied at all (mirroring the existing
`RoomProfile.is_outdoor` gate), not an arithmetic resistance value — it answers "does the hazard reach
this place," a different question from "how much damage gets through," which stays
`ConditionResistanceModifier` arithmetic per ADR-0073. We rejected modeling location-shelter as a
`ConditionResistanceModifier` (conflating the two questions) and rejected a new cross-domain Succor
model (a GFK or dual-FK bridge, which ADR-0015/0016 already forbid for this exact shape).

> Status: accepted · Source: issue #1744

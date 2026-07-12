# ADR-0122: Rampart is a position-anchored entity, not per-bearer group conditions

**Status:** Accepted (2026-07-12) · **Issue:** #2209 (Guardian epic #2040 decision 3)

A projected barrier (`Rampart`, `world/areas/positioning/models.py`) is modeled as its own
entity — one row per covered `Position` (`OneToOneField`), one `integrity`/`max_integrity`
pool, an `element_profile` FK for its authored damage-type resistances and signature
behavior, and a `crack_state` property — rather than as a `ConditionInstance` applied to
each bearer standing at the position. A single shared pool gives the AE (area-effect) soak
cap the epic ratified ("integrity *is* the AE absorption cap — no separate per-round cap"):
every strike of a multi-target attack against the covered position draws down the same
number, so a barrage can crack or collapse the barrier exactly once, not once per bearer.
It is also directly map-renderable (`position_graph`'s `rampart_*` node fields drive the
tactical map's crack-state ring) and a natural WARD-Clash meter subject (a sustained barrage
opens a Clash whose meter is the Rampart's own integrity) — both need one canonical number to
read and drain, not an aggregate over N per-bearer rows. Coverage is faction-blind, matching
ADR-0109's obstacle rule: the Rampart doesn't know or care who is standing at its position.
Rejected alternative: a `ConditionTemplate` applied to every bearer at the position (mirroring
personal reactive defenses). That fragments the integrity pool per-bearer (no shared AE cap
without a separate aggregation step), is invisible to the map (conditions aren't graph nodes),
and has no single subject for a Clash meter to bind to — it would need its own synthetic
aggregate entity anyway, at which point the entity should just be the Rampart itself.

> Status: accepted · Source: issue #2209, epic #2040 decision 3 · Confidence: built & tested
> (`world/areas/positioning/tests/test_ramparts.py`,
> `world/combat/tests/test_rampart_interception.py`, SQLite tier); firing order: Rampart
> interception runs before personal reactives and Guardian reactions (see
> `docs/systems/COMBAT_DEFENSES.md`); extends ADR-0109 (faction-blind coverage).

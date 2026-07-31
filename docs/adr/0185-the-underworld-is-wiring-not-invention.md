# ADR-0185: The underworld is wiring, not invention

**Status:** Accepted (built #2862; extends ADR-0184)

**Decision.** The criminal arc connects dormant machinery rather than building
parallel systems, designed from the sale backwards. **Substances**: Dust and
Haze ride the #2852 `INTOXICATE` seam via an intoxicant override (the effect's
existing `condition_template` column selects the ladder; the pass-out roll
fires only when the ladder reaches pass-out depth — Hazed structurally cannot
drop anyone), and Dusted's Gone Under lands the built Unconscious machinery,
whose dreamside-perception rule makes "Dream Dust" mechanically literal at
zero cost. **Production**: `CraftingRecipe.required_feature_kind` generalizes
the LAB hardcode so illicit refinement gates on the Workshop of Iniquity
(already authored for exactly this); the first `MaterialCategory` content and
drug precursor templates make ingredients real. **Selling**: the fence — the
game's first sell-to-NPC path (`MarketStall.stall_kind=FENCE`,
`sell_to_fence`) — pays a cut of `ItemTemplate.value` (its first consumer),
takes hot goods, and gives the seeded-but-dormant `contraband`/`smuggling`
CrimeKinds their first live heat producers, weighted by AreaLaw. **Turf**:
`NeighborhoodTurf` (the arc's one new model — area O2O at NEIGHBORHOOD level,
controlling org, grip) is moved by the ORPHANED gang-turf project machinery
(zero callers since #2418) plus mission PROJECT lines; control writes the
dead `StatKey.CRIME` (whose first reader scales guard-encounter pressure) and
re-targets CRIME_KICKUP streams; a push against held ground opens a
Retaliation crisis (CRIMINAL_ORG audience) — the NPC gang fights back through
the crisis engine, and the seeded spy-counterplay templates compose.
**Missions**: seven RESTRICTED criminal templates on a covert board (taught,
never listed; org-membership availability rule), the first `MissionCategory`
rows, failure-tier `CRIME_WATCH` heat lines, turf missions feeding the
project sink, and a standing smuggling route as a `TaskTemplate` with a
linked mission — the tasking system's dual-execution bridge exercised as
designed.

**Rejected alternatives.** (a) A contraband flag on items — illegality stays
act-level (CrimeKind × AreaLaw), the standing architecture. (b) A Gang model —
gangs are Organizations with the (finally seeded) `gang` type; NPC-run means
no player members, not new machinery. (c) A patrol/route simulation for
smuggling — the mission chain + the recurring task cover it; customs is
deferred. (d) Turf via `GangTurfDetails.target_area` alone — explicitly
flavor-only by its own docstring; control needed a real state row.
(e) PvP-gang turf — deferred until its own consent design pass; the NPC fight
proves the loop.

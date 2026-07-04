# Building renovation swaps the catalog BuildingKind row, not per-building flags

`BUILDING_RENOVATION` (#1858) re-points an existing `Building.kind` to a different
admin-authored `BuildingKind` row on completion, rather than mutating boolean
flags on `Building` itself. The nine descriptive flags (`is_occult`,
`is_fortified`, etc.) live on `BuildingKind` — a shared, staff-authored catalog
row (`name` unique, `on_delete=PROTECT`) — and `world/buildings/AGENT_GLOSSARY.md`
explicitly defines them as "cosmetic/filter flag[s] on the *catalog*, for
search/flavor, carrying no mechanical weight," distinct from per-building
numeric investments like `fortification_level`. Flipping a flag on the shared
row would affect every building of that kind, and duplicating the flag set onto
`Building` would create two sources of truth and contradict the glossary.

So a renovation models *kind swaps* (manor → "Occult Manor"), not single-flag
deltas: designers author the target `BuildingKind` rows ("Witchy Manor" with
`is_occult`, and other combinations), and a renovation project re-points to one.
The handler uses set-once idempotency (mirrors `FortificationUpgradeDetails`),
with no ordering guard — unlike fortification's monotonic "never downward" rule,
a catalog-kind label has no numeric ladder, so a later renovation may re-point to
any target kind, including back to the original.

Rejected: (A) synthesizing a derived `BuildingKind` row per renovation — would
pollute the staff-authored catalog with player-generated rows, break `name`
uniqueness and Area whitelists/permit offers, and treat a player renovation as
new catalog taxonomy, which the glossary says flags are *not*. (B) per-building
override flags on `Building` — contradicts the glossary's catalog-level stance
and denormalizes. If single-flag deltas ever become desired, that is a separate
`needs-design` discussion (likely a `BuildingFlagOverride` model), not this ADR.

> Status: accepted · Source: #1858 (slice of #673) · Related: glossary
> `world/buildings/AGENT_GLOSSARY.md` (BuildingKind flags are catalog cosmetic tags)

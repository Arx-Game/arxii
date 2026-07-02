# Building size is a space budget rooms spend from, not a flat room cap

`Building.target_size` now indexes `BuildingSizeTier` to snapshot a **space budget**
(`Building.space_budget`, in room-size units), and each room carries a `RoomSizeTier`
(`RoomProfile.size`) whose units it spends from that pool. This supersedes the shipped
Plan-3 formula `max_rooms = BuildingKind.rooms_per_size_tier × target_size` — both
`max_rooms` and `rooms_per_size_tier` were removed (#670, ratified on the issue's
2026-06-24/25 design checkpoint). Room size becomes a mechanical attribute (the unit
ladder is also the shared contract for the future creature-size stat: entry gating and
combat range), and builders trade room *count* against room *grandeur* freely — ten
modest rooms or one vast hall from the same budget. Rooms within budget are instant and
free (construction/extension projects already paid for the space); growing the budget is
the `BUILDING_EXTENSION` project. We rejected keeping the flat room count (a cap on
count makes every room the same size mechanically, so "vast ballroom vs. cramped cell"
would stay pure fiction, and per-kind `rooms_per_size_tier` tuning double-encoded what
kind flags + budget already express). Budget-tier magnitudes are PLACEHOLDER
admin-editable rows (super-linear by design: one big build ≈ 2× two half-size builds)
awaiting the economy pass.

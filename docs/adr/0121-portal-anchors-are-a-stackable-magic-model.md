# Portal anchors are a stackable magic-app model, not a RoomFeatureKind

`PortalAnchor` (#2222) is a plain `world.magic` model (FK to `RoomProfile`, PROTECT FK to
`PortalAnchorKind`), not a `room_features.RoomFeatureInstance` or a
`buildings.RoomDecoration`. `RoomFeatureInstance` was rejected because its `room_profile` is a
`OneToOneField` — one feature per room, full stop — while a single room can (and, per the
anchor-kind catalog design, should) hold more than one active anchor kind at once (a Mirror
*and* a Doorway in the same hall); the `dissolved_at` soft-delete precedent it carries was
worth mirroring, its cardinality was not. `RoomDecoration` was rejected on shape, not
cardinality — it IS stackable (plain FK to `room_profile`) but its whole contract is
materializing a `DecorationKind`'s amenity/affinity as room-scoped `LocationValueModifier`
rows; it carries no `is_network_open`/owner-tenant reachability gate, no link to a
`Technique.travel_anchor_kind`, and living in `world.buildings` would put a
technique-gated-travel primitive on the wrong side of the specific→general FK-direction rule
(ADR-0010) — `world.magic` would need to import `world.buildings` for a mechanic that is
entirely about known techniques and anchor kinds, not comfort/amenity. `PortalAnchorKind` is
the small staff-authored catalog (arrival/departure verbs per medium — Mirror, Doorway, ...);
each installed `PortalAnchor` names its own kind, so many gifts can each unlock travel through
one medium without a parallel catalog per gift.

> Status: accepted · Source: issue #2222 · Related: ADR-0010 (FK direction specific→general)

# Relationship reads are scoped to the caller's own outbound rows, plus a soul-tether carve-out

`CharacterRelationshipViewSet` previously had no viewer scoping at all — any authenticated
account could list or retrieve any pair's numeric relationship state (affection, track
points, tiers) via `/api/relationships/relationships/`. We scoped `get_queryset` so a caller
only reads rows where `source` is one of their own (tenure-owned) characters, or the row is
`is_soul_tether=True`. Numeric relationship state is author-private — it is the caller's own
private read on how *their* character feels, not a public fact about the pair — while the
prose is already visibility-gated separately (`RelationshipUpdate.visibility` following
`UpdateVisibility`, unaffected by this change); soul-tether rows stay universally readable
because the Soul Tether panel rendered on a foreign character's sheet depends on reading them.
We rejected leaving the open read in place: it was a silent OOC information leak (any account
could read any pair's affection/tracks) that telnet's `relationship show` never allowed —
`CmdRelationship` has always required the caller's own puppet as one side of the query.

> Status: accepted · Source: #2159

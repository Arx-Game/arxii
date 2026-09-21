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

**Amended by ADR-0308 (#3957, 2026-09-21).** The redesign that replaced tracks with labels
replaced this all-or-nothing scoping with four server-decided audiences
(`relationships.constants.TieAudience`, applied in `relationships.reads`): the caller still
owns their own side, but **the other side of a tie now reads** the labels the declarer let them
see (Clandestine or Public), the pair's pooled depth, both claimed tiers and the depth
breakdown — what this ADR called "numeric relationship state" is, for those two people, a
shared fact about the pair. What stays private is narrower and sharper: `affection` and
`conflict` are emitted only to the owner and to staff, and a **third party** reads Public
labels and the summary and no number at all — a tie with no open Public label is absent from
their list and 404s on retrieve, never 403, so the refusal never confirms the tie exists. The
soul-tether carve-out survives unchanged. The prose half of the original reasoning moved:
`RelationshipUpdate.visibility`/`UpdateVisibility` are gone with the writeup models, and the
prose about a tie is journal entries about the other character, gated by the journals' own
visibility rule (ADR-0307, #3941).

> Status: accepted · Source: #2159

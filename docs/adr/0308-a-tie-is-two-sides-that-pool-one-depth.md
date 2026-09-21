# ADR-0308: A tie is two sides that pool one depth; labels carry awareness and history, never points

**Status:** Accepted (2026-09-21, #3957).

A tie between two characters is two directed `CharacterRelationship` rows, one per side, and
each side holds any number of `RelationshipLabel` rows naming a staff-authored
`RelationshipType` ("Lover", "Rival", "Mentor"). A label carries an awareness stage that only
ever moves forward — `LabelAwareness` PRIVATE → CLANDESTINE → PUBLIC, or PRIVATE → PUBLIC
directly — and its own history: `shift_label` ends the old row and creates a new one whose
`replaced` self-FK points back at it, `end_label` sets `ended_at` and the label shows as
former, and nothing ever deletes a label. Each side *adds* depth — `scene_depth` from the
first scene the two share in a game week, `invested_depth` from a weekly AP allocation, each
award audited by a `RelationshipDepthTransaction` — and the tie's depth is the two sides'
sum (`CharacterRelationship.pair_depth()`), so a side that invests alone still deepens the
tie for both. Each side claims its own `tier` against that pooled depth, one rung at a time,
by marking one of its own journal entries about the other as the capstone and spending
`RelationshipGrowthConfig.xp_per_tier × the new tier` — the `RelationshipCapstone` row is the
receipt, and the tier is *claimed*, never reached automatically. `affection` and `conflict`
are two unsigned gauges on the side row, moved only by play (bumps, Flirt/Seduce shifts,
grievances, boon drains, the NPC mirror) through `move_gauges` and never set by a player.
Mutuality is derived, never stored: `is_mutual` is true when both sides hold counterpart
labels (`RelationshipType.counterpart`, null meaning the type pairs with itself) at
Clandestine or Public, each declared under a roster tenure that is still open. Visibility is
four audiences decided server-side (`TieAudience`): the owner sees everything including
Private labels and both gauges; the other side sees Clandestine and Public labels, the pooled
depth, the tiers and the breakdown, and no gauges; a third party sees Public labels and the
Summary and *no number at all*, and a tie with no open Public label is absent for them
entirely (a 404 from the tie read, never a 403, so absence and refusal are indistinguishable);
staff see everything.

Rejected alternatives. **Per-label points** (the outgoing `RelationshipTrackProgress` shape,
capacity plus developed points per track): there is nothing for a player to "earn as Kin", and
the inference trick the per-track numbers served — reading someone's feelings off which track
they had invested in — died with the one-sided relationship page the redesign replaced; one
depth per pair is the fact that actually grows from play. **A pair-level model** (one row per
unordered pair carrying shared depth and shared labels): every piece of state here is genuinely
per side — my labels, my tier, my gauges, my summary — and the magic anchors (`Thread
.target_relationship`) and the combat bond would have had to hang off a derived sum rather than
a row a character owns. **Keeping `scenes.Rivalry` beside the Rival label**: two spellings of
one consent, which would drift the moment a player declared one and not the other, so the model
and its viewset were deleted and `ConsentMode.RIVALS` now reads `mutual_hostile`. **Deletable
labels**: a misclick would erase a relationship's history, so End is a timestamp and Change is a
new row that remembers its predecessor. **Reversible awareness**: a known thing cannot be unsaid
in character, so `advance_awareness` raises `AwarenessBackwardError` rather than hiding a label
someone has already read. **Hybrid combo types** (`HybridRelationshipType`, "Frenemy"): several
labels on one side already carry that fact, and a combo row adds a second vocabulary nobody
authored against. **Relationship writeups beside journals** (`RelationshipUpdate` /
`RelationshipDevelopment` / `RelationshipCapstone` prose, plus `WriteupKudos` and
`WriteupComplaint`): one prose channel — journal entries about a character (#3941) — and the
capstone is one of those entries marked through a receipt.

Cross-references. ADR-0024 (relationship declarations are not consent-gated: they describe the
caller's own side and compel nothing) still holds, and Decision 9 rides on it — a *mutual*
hostile declaration is what opens antagonism, not a one-sided one. **ADR-0117 is amended, not
superseded**: numeric state is no longer author-private alone; the other side of a tie reads the
known labels, the pooled depth and both tiers, while the gauges stay owner-and-staff-only and
third parties still read no number. ADR-0092 and ADR-0110 keep their curves, but their inputs
change: the relationship-bond pull term keys on `pair_depth()`, fraught on
`min(affection, conflict)`, devotion on pooled depth past its threshold. ADR-0307's
`can_retort` now reads `mutual_hostile` rather than "either direction on a negative track",
narrowing exactly where that ADR said the relationships pass would narrow it.

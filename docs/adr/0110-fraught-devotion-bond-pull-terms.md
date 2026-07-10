# ADR-0110: Fraughtness and devotion are additive, sign-aware terms on the relationship-bond pull, not new mechanics

#2034 adds two additive terms to `relationship_bond_modulation`
(`world/magic/services/pull_modulation_relationship.py`, ADR-0092), which stays
sign-blind in its base term (`developed_absolute_value`, magnitude only). **Fraughtness**
rewards a bond invested heavily in BOTH positive and negative tracks at once — a love/hate
dynamic — keyed on `min(pos_sum, neg_sum)` from the new `CharacterRelationship
.developed_signed_sums` property (a (positive_sum, negative_sum) split of the same cached
`developed_points` measure `developed_absolute_value` already sums, read off the existing
`cached_track_progress` path — never a fresh query); a bond lopsided entirely in one
direction earns nothing here. **Devotion** rewards a bond so overwhelmingly deep that
`developed_absolute_value` clears a threshold well past the base curve's own
half-saturation point, keyed on `max(0, developed_absolute_value - devotion_threshold)` —
depth alone, per Tehom's 2026-07-06 ratification, with **no ritual or ceremony gate**: a
bond's mechanical devotion bonus tracks its raw investment, not whether the pair ever
staged a scene about it. Both terms reuse `_soft_cap` (`world/magic/services/threads.py`)
with their own tuning columns on the existing `RelationshipBondPullTuning` singleton
(`fraught_coefficient`/`fraught_cap`/`fraught_half_saturation`,
`devotion_threshold`/`devotion_coefficient`/`devotion_cap`/`devotion_half_saturation`) —
defaults are conservative: both caps are 10, half the base `cap` (20), and
`devotion_threshold` is 60, 2× the base `half_saturation` (30) — the point where the
generic curve is already ≥⅔ saturated, so only genuinely extreme bonds earn the second
wind. Two alternatives were rejected: driving bonuses off `HybridRelationshipType` rows
(Frenemy, etc.) — those catalog rows are display vocabulary for the relationship screen,
not a mechanical substrate, and coupling the pull to them would make the bonus depend on
staff-authored labeling rather than the underlying point investment; and detecting a
sign-*flip transition* (a bond that recently crossed from net-negative to net-positive or
back) — this needs point-history the model doesn't retain and would retro-punish a bond
that has since stabilized, the opposite of what a "second wind" term should reward.
**Considered, not built:** a future term reading `RelationshipCapstone.points` to fold
capstone-specific investment in — Tehom: "we might do something with the capstones for
them, but it's tricky, not sure there's enough there for us to build on" (paraphrase); no
capstone hook exists and none should be added speculatively. This ADR covers only the
power half of #2034; the expression half — a ceremony beat at RELATIONSHIP_TRACK /
RELATIONSHIP_CAPSTONE thread crossings — is #1991 (merged). Both new terms surface in
`preview_resonance_pull` automatically, with no extra wiring, because the preview and
commit paths already share the one `apply_target_modulation` seam (the #2035 target-parity
fix).

> Status: accepted · Source: #2034, ADR-0092, #1991

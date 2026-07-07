# ADR-0098: Custody is story-declared narrative-structure protection, distinct from player boundaries

## Context

#2001 needed a way for a GM to declare an NPC, item, faction, or location "load-bearing" for
their story — protected from being killed, captured, staked, or spent by actors at *other*
tables — so a nemesis doesn't get unceremoniously bumped off as a miniboss at someone else's
table. `world.boundaries` (`PlayerBoundary`/`TreasuredSubject`, ADR-0086) already solves an
adjacent-looking problem: a *player* flags a subject whose loss would hurt, gated by consent
sign-off. The two features share the same typed-subject-FK shape (`subject_sheet`/
`subject_item`/`subject_society`/`subject_organization`/`subject_label`, mirroring `Stake`) and
the same `_subject_identity` matching helper — inviting the question of whether custody should
just be a new `TreasuredSubject` visibility mode or owner type instead of a new model.

## Decision

**Custody (`StoryProtectedSubject` + `CustodyClearance`, `world.stories`) and boundaries
(`PlayerBoundary`/`TreasuredSubject`, `world.boundaries`) stay two separate systems on two
separate axes, never merged:**

- **Who declares it, and why.** A `TreasuredSubject` is *player*-declared OOC emotional safety —
  a player may not even know who an NPC really is, and the point is a heads-up + opt-in
  sign-off before their own attachment gets staked against. A `StoryProtectedSubject` is
  *GM/story*-declared narrative-structure protection — the GM is asserting "this asset belongs
  to my plot," independent of any single player's feelings about it.
- **Who it protects against.** A `TreasuredSubject` gates one player's own stake exposure
  (`TreasuredSignoff` before *that player's* stake can activate). Custody gates every *other
  story's* actors — participants in the protecting story, and staff, are exempt by
  construction; everyone else needs an active `CustodyClearance` at sufficient scope
  (APPEAR < HARM < REMOVE).
- **Ownership model.** `TreasuredSubject.owner` is a `RosterTenure` (one persona's own
  attachment, follows that character). `StoryProtectedSubject.story` is a `Story` FK (follows
  the plot, not any character) — a GM authors it once for the whole story, not per-character.
- **Lifecycle.** A `TreasuredSubject` match never blocks by itself, only requires sign-off —
  losing a treasured NPC is often exactly the beat the player opted into. A
  `StoryProtectedSubject` match blocks outright (`CustodyVerdict.allowed=False`) absent a
  clearance — the GM is asserting a hard "not without asking me first," not offering an
  opt-in.

Both reuse the identical typed-subject-FK vocabulary and `_subject_identity` comparison
(`world/stories/services/boundaries.py`) deliberately — same shape, same matching primitive,
different declarer/target/lifecycle. Sharing the comparison function is reuse without merging
the two systems.

## Rejected

- **A new `TreasuredSubject` visibility mode or owner type for GM-declared protection**,
  instead of a new `StoryProtectedSubject` model. Rejected: `TreasuredSubject` is owned by
  `RosterTenure` and gates one player's own stake exposure via sign-off; custody must gate
  *every other story's* actors uniformly via a hard block + clearance ladder, a materially
  different enforcement shape that a mode flag on the existing model would blur rather than
  clarify — a future reader would have to reason about two unrelated consent models sharing
  one table.
- **A single unified "protection" model** parameterized by declarer (player vs. GM). Rejected
  for the same reason ADR-0086 rejects folding `PlayerBoundary`'s `HARD_LINE`/`ADVISORY` split
  into `TreasuredSubject`: the mechanisms (auto-block-with-clearance vs. flag-with-sign-off)
  are different enough that a shared shape would need per-declarer branching at every read/write
  site instead of two small, legible services.

> Status: accepted · Source: #2001; extends ADR-0086 (content boundaries split enforcement
> from communication), ADR-0010 (FK direction specific→general).

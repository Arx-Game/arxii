# Concealment carries an OOC-only, identity-free "someone is watching" guarantee, separate from IC detection

`#1225` introduced the first mechanism (`ConditionCategory.conceals_from_perception`) that lets a
character be physically present but IC-unperceivable to others. `docs/roadmap/design-tenets.md`'s
"Players are always aware when another player can see their RP" tenet already set the floor but left
"the detailed invisibility-as-an-IC-effect mechanic" as TBD. This ADR fills it.

Two independent axes:

1. **IC detection is per-observer and gradable via checks.** A concealed target's `ConditionInstance`
   tracks which observers have detected it (`detected_by`); `can_perceive` respects this per-actor.
   Detecting is a real contest (the Search check), not automatic.
2. **OOC transparency is unconditional, un-checkable, and identity-free.** Whenever an
   unseen-observation grant (this condition; a future scrying/remote-viewing feature) is active on a
   scene, every player connected to that scene gets an OOC-channel notice that an unseen observer is
   present — never naming who, never embedded in IC pose/room text, never gated by any roll, and
   persisted as scene state so a player can't miss it through bad connection timing.

Consequences: true, permanently-silent invisibility against other players is not a feature this game
will ever ship — any future "undetectable" mechanic must still fire the OOC tell. IC "can my character
tell" and OOC "does the player know" are permanently decoupled; UI must render the OOC tell distinctly
from IC narrative text (a system banner, not a pose).

Supersedes/clarifies: fills the TBD in `docs/roadmap/design-tenets.md`'s "Players are always aware..."
tenet; corrects its illustrative example, which read as IC-flavored prose.

> Status: accepted · Source: #1225 spec revision

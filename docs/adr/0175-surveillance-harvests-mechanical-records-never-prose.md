# ADR-0175: Surveillance harvests mechanical records, never prose; one listener seat per room

## Status

Accepted (issue #2820, phases 3–4)

## Context

Spy networks post standing informants in rooms where other players RP. The
design tenet "players are always aware when another player can see their RP"
forbids any mechanic that reports pose text a player didn't know was being
watched — the Arx 1 failure mode was intimate RP leaking through abstract spy
reports, which reads as a personal violation, not gameplay.

## Decision

1. **Prose is structurally not an input.** Listener buzz accrues only from the
   room's mechanical residue — scenes held there and scene-anchored `Secret`
   rows minted there (`_room_residue`); harvests reference the minted Secret
   itself. A scene that produced no mechanical record produced nothing for any
   spy, no matter what was written. This kills the violation case at the
   pipeline level rather than by policy: there is no code path from
   `Interaction` text to a harvest. (Project owner: the abstraction boundary is
   "a murder generates a murder clue"; never "the NPC reports the poses.")
2. **One active listener per room.** The pre-existing `(room, role)`
   partial-unique on `NPCAssignment` is kept for LISTENER rather than relaxed.
   Prime posts become contested scarce seats, and the counterplay design
   (flip the sitting listener) presumes a single seat to fight over.

## Rejected

- **Pose-content summarization** (any flavor, however abstracted) — violates
  the awareness tenet; unacceptable regardless of filter quality.
- **Parallel listeners per room per network** — removes seat scarcity, breaks
  the flip-centric counterplay loop, and multiplies quiet-room bookkeeping.

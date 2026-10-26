# ADR-4676: Reactions cost and escalate with no cap, and dodges read capabilities

**Date:** 2026-10-25
**Status:** Accepted
**Issue:** #4676 (slice 4 of #4651)
**Supersedes in part:** ADR-0161 (the one-reaction-per-round budget), ADR-4584-A (a standing
guard spending "her one reaction"), and Phase Step's game-picked destination (ADR-0118).

## Decision

A character dodges an NPC attack automatically when a capability she holds above its innate
baseline has a `CapabilityType.reaction_reach`, or a Phase Step ward is on her. The dodge is
her defense roll with that capability's value as a bonus, so a strong capability makes avoiding
the hit the usual result while the roll keeps its normal degrees. It costs anima, or physical
fatigue when the capability's `reaction_cost_kind` says so, and each reaction already made this
round (dodges, guards, catches) takes `MovementConfig.reaction_difficulty_step` off the next
reaction's roll. `REACTIONS_PER_ROUND` is removed: there is no cap. Where she lands is her own
dodge plan, set while declaring; Phase Step follows that plan and, against an NPC attack, its
all-or-nothing cancel becomes the defense roll. A place-covering attack is escaped only by
leaving the place.

## Why

The owner ruled movement reads capabilities, never their sources (#4651 decision 2), that
reactions cost and get harder rather than stop at a cap (decision 7), and that a strong mover
should usually not be hit, with the distance optional (decisions 5 and 6). A cap made a
teleporter shot three times defenceless after the first; the escalating roll lets her keep
dodging at a rising price, which is what the owner described ("after two or three, much less
so"). Reading the reach and cost from fields on the capability keeps it data, not names.

## Rejected

Keeping the cap and adding dodges beside it (a dodge would then be one free reaction, and
guarding would compete with it for one slot). Mid-round prompts to choose a landing per attack
(rounds resolve all at once, decision 6). A separate "dodge" model per source (technique,
species, ward), which would reintroduce source-based rules.

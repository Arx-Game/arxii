# XP buys unlocks that gate acquisition, never grant it

Experience points are spent **only** to purchase unlocks that remove a gate — permission to reach
level X, to raise a thread to level X, to acquire gift X, to gain threadweaving for Y — and **never**
to directly grant the capability; acquisition is always a separate step behind the unlocked gate.
This ratifies the established authored-`*Unlock`-catalog + per-character-`Character*Unlock`-receipt
pattern (`ClassLevelUnlock`, `ThreadWeavingUnlock`, `ThreadLevelUnlock`, all debiting the single
account-level `ExperiencePointsData`) as the universal XP contract. We rejected XP-buys-the-thing-
directly because separating unlock from acquisition keeps advancement legible, lets non-XP gates
(story, ritual, RP) co-gate the same step, and stops XP from becoming a pay-to-win shortcut.

> Status: accepted · Source: design discussion 2026-06-27 · Confidence: verify against code — pattern exists in `world/progression`

# ADR-4609-A: NPC tactics read derived facts, and their numbers live in a staff row

**Date:** 2026-10-24
**Status:** Accepted
**Issue:** #4609 (slice 4 of #4576)

## Decision

The tactics ladder (`combat/services/npc/npc_tactics.py`) stores nothing new about what an
opponent has been through. Who is hitting an opponent is read from this round's player
declarations and attack rows aimed at it. Whether it can answer them is computed from its
threat entries and live positions. The one-wait cap comes from last round's move row, and the
retreat count from the move rows before it. The three numbers the ladder turns on (how many
rounds a group may take to bash a wall down, how many rounds a broken opponent backs away
before it leaves, and the morale an unanswered hit takes) sit in a one-row staff table,
`NpcTacticsConfig`, beside `SpectacleConfig` and `ClashConfig`. The parent spec put them in
`constants.py`. The constants stay only as the row's starting values.

Three readings were made where the spec left room. "Hit this round" counts an attack aimed at
the opponent this round, landed or still to come, because selection runs before anyone
strikes. Ratified decision 9 says a creature attacked by a flier it cannot reach runs for
cover at once. "No hostile can strike it by reach" is melee reach: what a player will strike
with next round is not known, and the round limit ends the rest. When nothing gets the
opponent nearer, a cunning or tactical one waits once before it bashes a wall it cannot
break in time, and bashes it the round after, when the wait cap stops a second wait. That
follows ratified decision 2 ("An NPC that can knock a wall down does so. Otherwise it skips
the wall or finds a way around, depending on intelligence.") and Scenario 1 ("a cunning wolf
would judge it unbreakable ... With none, it would wait once, then advance as near as it
can"), over the technical section's zero-hop list, which put the desperate bash first. A
mindless one never waits and bashes at once. Either way no round is empty: the wait is a
held waiting strike, and the bash that follows lowers the wall.

## Rejected

Recording hits, waits and retreat counts on the opponent row. Each copy is a second home for a
fact the move and action rows already hold, and a copy can go stale. Code constants for the
three numbers. Tuning lives in the database where staff can change it after play (the combat
config rows), and a constant needs a deploy.

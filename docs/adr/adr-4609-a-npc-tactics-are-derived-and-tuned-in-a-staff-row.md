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
cover at once. "No hostile can strike it by reach" counts ranged reach (the owner's ruling,
2026-10-24, replacing a melee-only first reading): a player character reaches it when any of
its known combat-ready techniques does, through the declaration's own reach rule
(`technique_can_reach`, roofs and screens included), and a hostile opponent when one of its
threat entries' deliveries does (`strike_reaches`). So a broken opponent an archer can still
shoot keeps backing away and leaves only at the retreat limit. Whether it is cornered (an
enemy in arm's reach and nowhere farther to go) stays a melee question. When nothing gets the
opponent nearer, a cunning or tactical one waits once before it bashes a wall it cannot
break in time, and bashes it the round after, when the wait cap stops a second wait. That
follows ratified decision 2 ("An NPC that can knock a wall down does so. Otherwise it skips
the wall or finds a way around, depending on intelligence.") and Scenario 1 ("a cunning wolf
would judge it unbreakable ... With none, it would wait once, then advance as near as it
can"), over the technical section's zero-hop list, which put the desperate bash first. A
mindless one never waits and bashes at once. Either way no round is empty: the wait is a
held waiting strike, and the bash that follows lowers the wall.

A broken opponent no longer turns FLED when the round is planned. It shows ACTIVE until
its own slot in the round, backs away there over real hops, and turns FLED at the end of
that walk when no enemy reaches it or the retreat limit is hit. `resolve_round` checks
whether the encounter is over after every slot has run, so a rout or victory the flight
causes still ends the fight in the same round. Off the map, or with no enemy on it, a
broken opponent still flees when the round is planned, as before. One that breaks while
winding up writes no plan until the blow lands (the telegraph is its action, as the spec's
wind-up rule says), then retreats the round after.

## Rejected

Recording hits, waits and retreat counts on the opponent row. Each copy is a second home for a
fact the move and action rows already hold, and a copy can go stale. Code constants for the
three numbers. Tuning lives in the database where staff can change it after play (the combat
config rows), and a constant needs a deploy.

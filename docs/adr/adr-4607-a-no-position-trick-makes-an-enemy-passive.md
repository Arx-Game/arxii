# ADR-4607-A: In an automated encounter, no position trick makes an enemy passive

**Date:** 2026-10-24
**Status:** Accepted
**Issue:** #4607 (slice 2 of #4576)

## Decision

An enemy in an encounter with no GM present always acts. A wall, a gap or a height changes
what it does, never whether it does anything. Selection writes a move plan
(`CombatOpponentMove`) for every active opponent every round, including one with no attack
it can use. In its slot the opponent moves along a real path, up to its creature
template's hop budget, and then attacks whoever its strikes reach. Melee needs an adjacent
or shared position, and missiles reach the whole room. Player characters spend hops from
the same budget, so moving during a round is no longer free. Walls block both sides
(ADR-0109 stands). Later slices add the remaining responses, built on the move plan: bash a
wall, take cover, wait for an opening, or retreat.

## Rejected

Faction-aware walls, which let a party's wall stop only enemies. Leaving enemies passive
behind walls, as before this slice, where an opponent with no stored attack never reached
the resolve loop. Either one turns a barrier into a way to win a fight with no risk, and
combat in a mission or a dangerous place has to stay a real contest. This is not an
anti-farming rule. Killing at no risk is not how anyone progresses here.

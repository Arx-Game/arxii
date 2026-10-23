# ADR-4584-A: A standing guard spends the guardian's reaction

**Date:** 2026-10-23
**Status:** Accepted (spec approved on #4573)
**Issue:** #4584 (relates #2639, #4573). Revisits ADR-0161 for guards only.

## Decision

A condition with `source_guards_bearer` makes its source a guardian of its bearer. On every hit
on the bearer the guardian tries the same mundane interpose a declared Interpose rolls, through
the shared tail `_attempt_guardian_interpose` in
`world/combat/services/damage/interception.py`. Because it is the shared tail, a standing guard
counts against `REACTIONS_PER_ROUND` (the guardian's one reaction a round) and against
`ABSORPTION_CAP_PER_MOMENT` (the answers one hit can draw), and it pays interpose fatigue at
very low effort. Without a declaration there is no effort to read, so the physical category at
very low effort stands in. The guardian still takes her own turn; nothing is declared for the
guard.

Order on one hit: declared Interpose naming the ward, then standing guards (oldest condition
first), then guard-anyone declarations. A guardian who declared any Interpose that round
(naming this ward, another ward, or anyone) acts only through her declaration, so she is tried
at most once per hit and her declared technique and effort are the ones used. A guard cast on
its own bearer never interposes. A standing guard covers player-character wards in combat only:
not an ALLY summon ward, and not Sudden Harm outside combat.

Absorb, reflect, blink and strike-back stay outside both budgets, as ADR-0161 left them. They
pay their own `reactive_anima_cost` and fire from the condition, not from a person standing
beside the ward.

## Why this revisits ADR-0161

ADR-0161 left standing defenses outside both budgets and flagged the call as worth revisiting
"if a future situation lets a standing condition and a declared reaction meaningfully compete
for the same hit". A guard is that situation: it is a standing condition whose effect is a
person's reaction. Left outside the budgets, one guardian would answer every hit of a round for
free, and a declared Interpose beside it would be a second free answer. The guard is a
guardian doing what a declared Interpose does, so it spends what a declared Interpose spends.

## Rejected

Leaving the guard outside the budgets: the case above, and it would make a cheap condition
strictly better than the declared maneuver it imitates. Forming a declared `CombatRoundAction`
for the guardian each round: she would lose her own turn to a condition someone else cast, and
a declaration would have to be minted and torn down every round for a state that outlives the
round.

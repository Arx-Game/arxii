# ADR-0150: Weekly income lands before upkeep drains

**Status:** Accepted (2026-07-20)
**Issue:** #2609

## Context

`buildings.weekly_upkeep` sinks directly from `CharacterPurse`. `weekly_rollover` —
which runs `run_weekly_economy()` and therefore wages, income, asset yields, and
contract settlement — lands money in that same purse. Both are weekly.

Until now their relative order was an accident twice over: upkeep was registered with
no weekly anchor (it drifted on a rolling 7-day interval while the rollover stayed
pinned to Sunday), and ordering within a shared tick fell out of `register_task` call
order — two lines hundreds apart in `tasks.py`, with nothing marking the relationship
as load-bearing. Whether a player could afford their own upkeep was partly a function
of server restart timing.

Fixing the nondeterminism forced the question the accident had been hiding: which
order is actually correct.

## Decision

**Income lands first; upkeep drains after.** Encoded as `CronPhase` bands on
`CronDefinition` — `ECONOMY = 200` before `UPKEEP = 300` — with
`buildings.weekly_upkeep` sharing the rollover's anchor so the two fall due in the
same tick at all.

This deliberately **inverts** the pre-existing behaviour, which ran upkeep first.

## Rationale

Upkeep-first puts the sweep on the wrong side of the paycheck. A character living
paycheck-to-paycheck has a near-empty purse at week's end, so obligations-first makes
missed upkeep — and the arrears and condition-tier slide that follow — the *guaranteed*
weekly outcome rather than the coin flip it was before. Determinism would have locked
in the bad branch.

Income-first is the purse-level analogue of the debt philosophy already recorded for
org treasuries in #927: *"honest debtors never manage debt, they just see smaller
incomes… over-leverage bottoms out at zero spendable income, never offscreen loss."*
A player experiences a smaller effective paycheck. They never experience an
unpreventable slide toward losing their home.

## Alternatives rejected

**Keep upkeep first (the status quo).** Preserves existing behaviour, but only by
preserving an accident — and the accident is the harmful branch. The status quo had no
argument behind it beyond line numbers.

**Fold upkeep into `weekly_rollover_task`'s processor list.** Guarantees ordering
without a phase field. Rejected: each `CronDefinition` owns a `ScheduledTaskRecord`
carrying an `enabled` flag that staff toggle from admin, plus its own `last_run_at`.
Making upkeep a processor destroys that independent staff control and its
observability.

**A bare `order: int` on `CronDefinition`.** Simpler than a named enum, but bare
numbers carry no rationale, everything defaults to the same value, and the failure mode
is `order=95` hacks squeezed between neighbours.

**Declarative `runs_after` dependencies with a topological sort.** More precise and
self-validating — cycles would become startup errors. Rejected as disproportionate
machinery for ~36 tasks, almost none of which have an ordering opinion at all.

## Consequences

- A character short on funds sees a reduced net paycheck rather than an arrears hit,
  in the common case.
- Ordering is now declared, not emergent. New tasks land in `CronPhase.DEFAULT` and are
  unaffected; the sort is stable, so registration order still breaks ties within a band.
- `SNAPSHOT = 100` exists for tasks that must read balances *before* income moves. It has
  no members yet — it is the seam the "Somehow Always Broke" economic distinction
  (#2540) needs to capture a start-of-week baseline, and is declared here so that
  feature does not have to renumber the bands.
- Phases only order tasks that are already due in the same tick. A task must share an
  anchor with its neighbours for its band to have any effect — the two halves are
  independent and both required.

# NPCStanding carries debt and petition-failure-streak, not CourtPact

When a Court servant's emergency thread-bond draw (#1718) exceeds their earned
grant ceiling, the excess becomes debt, and repeated failed petitions eventually
provoke the master's escalated displeasure. Both facts live on `NPCStanding`
(`debt`, `debt_baseline_affection`, `debt_baseline_missions_completed`,
`consecutive_failed_petitions` — `world/npc_services/models.py`) — the already-general
per-(PC persona, NPC persona) durable disposition row (ADR-0058) — rather than on
`CourtPact`, which is Court-specific. `court_grant_ceiling` (`world/covenants/court_grant.py:61`)
and the two Court-specific consumers — the formal-petition effect handler
(`world.npc_services.effects.raise_court_grant`) and the emergency thread-bond draw
(`_resolve_emergency_draw`, `world/combat/pull_helpers.py:242`) — are the only current
callers, but any future "petition an NPC for something risky" feature (a mentor, a
merchant, a fence) can reuse the same debt-incur/derive-on-read-repay/failure-streak
substrate (`incur_npc_debt` / `outstanding_debt` / `record_petition_outcome`,
`world/npc_services/services.py:675-738`) without touching Court code.

We rejected putting these fields on `CourtPact`: it would silo the mechanic to Court
negotiation specifically, forcing a near-identical duplicate model the next time a
similar "ask an NPC for risky aid" feature ships — the exact parallel-implementation
smell ADR-0016 warns against.

Debt repayment is derive-on-read (`outstanding_debt` nets a baseline snapshot against
current affection/mission progress at read time), not push-notified from
`world.npc_services`/`world.missions` into `world.covenants` on every affection gain or
mission completion — that would invert the ADR-0010 dependency direction (the general
apps must not know about the specific Court consumer).

The consecutive-failure-streak counter (`record_petition_outcome`,
`world/npc_services/services.py:724`) mirrors `Contract.consecutive_missed`
(`world/currency/models.py:549`) — a plain increment-on-failure/reset-on-success counter
that reports threshold-crossing to the caller — rather than the condition/corruption
stage-advance mechanism (`advance_condition_severity`), which accumulates a magnitude and
crosses stage thresholds rather than counting same-size consecutive failures with a
reset-on-success.

`emergency_draw_max_bonus` (`CourtGrantConfig`, `world/covenants/models.py:988`) also
proved to mean "how far the draw may exceed the ceiling," not "a cap on the raw
requested bonus" — the clamp is `min(requested_bonus, court_grant_ceiling(...) +
emergency_draw_max_bonus)` (`world/combat/pull_helpers.py:326-330`). That's a naming/usage
clarification rather than a placement decision, but it's recorded here since it governs
how debt gets incurred in the first place: only the amount past the ceiling (not past
`emergency_draw_max_bonus` alone) is debited via `incur_npc_debt`.

> Status: accepted · Source: issue #1718 · Confidence: high — verified against
> `world/npc_services/models.py` (`NPCStanding`), `world/covenants/court_grant.py`,
> `world/combat/pull_helpers.py`, `world/currency/models.py:549`
> (`Contract.consecutive_missed` precedent) on branch
> `feature-1718-court-pact-convince-the-master-check-siz`.

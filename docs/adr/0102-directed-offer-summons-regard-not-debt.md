# ADR-0102: Directed-offer summonses — regard, not debt, is the price of refusal

## Status

Accepted — 2026-07-08

## Context

Issue #2050 (child of #2043) needed a mechanism for a Court master to direct a
wish at a *specific* servant — a targeted mission offer the servant can accept
or decline. The existing offer system is pool-drawn (the player picks from
available offers); there is no directed-offer primitive. The design session
(2026-07-07) ratified five decisions:

1. The wish is a **directed offer** with an explicit refuse-or-obey moment.
2. **The master remembers** — refusal drops affection + bumps a streak; crossing
   the threshold fires the master's escalation pool.
3. The primitive is **generic** on `npc_services` (any NPCRole can direct an
   offer); the Court layer adds its escalation config.
4. v1 creation is **GM/staff-driven**, primary surface is **mid-scene**.
5. **Player-originated summonses** are the anticipated next step, not v1.

## Decision

The summons is a generic directed-offer primitive on `npc_services` with an
explicit refuse-or-obey moment. Refusal is paid in **regard** (affection drop +
refusal streak → escalation pool via `apply_pool_deterministically`), **never in
debt** — debt keeps its single meaning (the price of drawn power). The accept
path delegates to the existing `resolve_offer` → `issue_mission` rails, so
eligibility and the risk-acknowledgement gate stay intact with zero new wiring.

The intended extension is a persona-creator variant (player-originated
summonses — the heist recruiter). Rejected alternatives:
- **Covenant-local implementation** — would duplicate the offer rails and
  violate ADR-0010 (covenants consume npc_services).
- **Debt-as-disobedience** — conflates two unrelated economic pressures and
  muddies the grant-ceiling formula.
- **Drop-without-ceremony** — the refuse-or-obey beat is the dramatic point; a
  silent drop eliminates player agency.

## Consequences

- `OfferSummons` is a new model on `npc_services`; any `NPCRole` can direct an
  offer at a persona. Court escalation config (`summons_refusal_escalation_threshold`
  + `summons_refusal_escalation_pool`) lives on `CourtGrantConfig`.
- `NPCStanding.consecutive_refused_summons` is a new streak field, sibling of
  `consecutive_failed_petitions` (generic per ADR-0085).
- The expiry cron (5-minute sweep) treats timeout as a refusal.
- Player-originated summonses are deferred — the model schema permits non-MISSION
  kinds, but the `clean()` gate limits v1 to MISSION.

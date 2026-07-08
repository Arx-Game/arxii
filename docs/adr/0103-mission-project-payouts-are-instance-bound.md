# ADR-0103: Mission→Project payouts are instance-bound

**Date:** 2026-07-08
**Status:** Accepted

## Context

Issue #2045: missions should be able to advance a `Project`. An authored
`MissionTemplate` cannot FK a *runtime* `Project` (templates are reusable;
projects are live instances that complete and disappear). The binding must
happen at issuance, not at authoring time.

## Decision

Mission→project payouts are **instance-bound** per ADR-0085's shape: the
binding is `MissionOfferDetails.target_project` (authored per-offer) copied
to `MissionInstance.target_project` at issuance — exactly how `source_beat`
works. Reward lines carry only the progress amount. The PROJECT branch in
`apply_deed_rewards` follows the CHECK precedent: record
`Contribution(kind=MISSION)` → bump `project.current_progress` →
`maybe_complete_immediately`.

Provenance: `Contribution` gains only the `kind=MISSION` choice — no FK
into missions. The missions side records the link
(`MissionDeedRewardLine.project_contribution` nullable FK→
`projects.Contribution`, specific→general per ADR-0010/0085).

Soft-skip at payout, loud refusal at issuance: if the bound project is
non-ACTIVE or the FK has gone null (SET_NULL) by report time, the PROJECT
branch does not raise into the report transaction — it skips the line,
notifies the player in the report text, and logs. Issue-time remains a hard
refusal (unbound instance + PROJECT lines).

## Rejected alternatives

- **Template→project FK:** repeatable templates can't FK a runtime project.
- **Project-kind auto-match:** "advances any ACTIVE project of kind X" —
  too magical, no designer control over which project.
- **Silent no-op on unbound PROJECT lines:** violates the no-silent-drop rule.
  Instead: loud refusal at issuance, soft-skip-with-notice at payout.

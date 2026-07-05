# GANG_TURF resolves TIERED_PERIOD via a per-kind resolver registry, not a shared accessor

`GANG_TURF` (#1891, slice of #673) is the first `TIERED_PERIOD` `Project` kind. The
original projects spec described the tier-selection path ("tier reached = highest
`tier_thresholds` entry whose progress was crossed") but never implemented it —
`scan_active_projects` only transitioned ACTIVE → RESOLVING and never mapped
progress → tier → `resolve_project`; every `resolve_project` call was manual, in
tests. So this slice had to build that path, and a generalization decision came with
it: how do future `TIERED_PERIOD` kinds (WAR_FUNDING, CITY_DEFENSE) plug in?

The chosen seam is a **per-kind tiered-resolver registry** in
`world/projects/services.py`, mirroring the existing `register_kind_handler` /
`get_kind_handler` pair exactly — same shape, same `apps.py ready()` registration
site. Each `TIERED_PERIOD` kind registers its own resolver (`resolve_gang_turf`,
`resolve_war_funding`, …) that reads its own per-kind details, selects the tier,
and calls `resolve_project`. `scan_active_projects` looks up the registered
resolver for a project's kind the same tick it transitions to RESOLVING; a kind
with no registered resolver (a not-yet-implemented future kind) is left RESOLVING
— today's behavior, no regression. No kind-agnostic `details` accessor or shared
interface is introduced; the GANG_TURF accessor lives in `world/societies/gang_turf.py`
behind the registry.

Two further decisions this ADR ratifies:

1. **`tier_thresholds` as related rows.** The original spec deferred the field
   shape ("related table vs structured field — JSONField is banned"). This slice
   pins it: `GangTurfTierThreshold` related rows (FK → `GangTurfDetails`, FK →
   `traits.CheckOutcome`, `min_progress`). Selection is a pure-Python linear scan
   over the already-fetched rows ordered by `-min_progress` (mirrors
   `societies.types.ReputationTier.from_value`), not a DB filter — consistent with
   the `SharedMemoryModel` identity-map pattern. Seeded rows always include a
   `min_progress=0` baseline failure tier so every graded project maps to exactly
   one tier; `resolve_project`'s `success_level >= 0` rule then marks it FAILED.

2. **Per-project error isolation in `scan_active_projects`.** The new in-loop
   resolver call wraps each project's transition + resolve in
   `transaction.atomic()` with `try/except`. Without this, a project that entered
   RESOLVING then failed to resolve would be stranded — `scan_active_projects`
   only scans ACTIVE, so a stranded RESOLVING project has no recovery path. With
   the rollback, a handler failure leaves the project ACTIVE (retryable next tick,
   15-min) and the tick's other projects still resolve.

Rejected: (A) a generic `resolve_tiered_period_project` in the shared module that
hardcodes `project.gang_turf_details` — self-contradictory (generic name, kind-
specific body) and would force every future kind to refactor a shared function.
(B) per-tier columns on the details model — denormalizes the ladder and forces a
schema change per tier count. (C) a `ProjectTierThreshold` TextChoices enum
instead of reusing `CheckOutcome` rows — contradicts the carried #673 decision
(codebase consistency; `resolve_project` already keys off `success_level`).

> Status: accepted · Source: #1891 (slice of #673) · Related: spec's
> anti-reinvention ledger (the "first TIERED_PERIOD kind" gap), ADR-0020
> (spec-on-issue).

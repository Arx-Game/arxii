# Stakes are menu-first, calibrated by band, not freehand-authored per table

A GM builds a beat's stakes contract by instantiating `Stake` rows from the
`StakeTemplate` catalog (`world/stories/models.py`) — named, `subject_kind`-typed
wagers bounded to a `min_risk`/`max_risk` range — rather than writing severity and
scope from scratch each time. `RiskCalibration` then enforces, per `RenownRisk`
tier, a `severity_floor_total` (a beat can't wager a token stake at HIGH risk),
a `severity_ceiling` (no single stake can exceed what its tier licenses — no
"everyone dies" at LOW), and the `max_fuse_hops` chain-rule bound (ADR-0076).
`validate_stakes_readiness` checks every declared stake against these bands
before a contract is considered ready. Custom (freehand) stakes remain possible
via `StakeSubjectKind.CUSTOM` with `Stake.template = null`, but that path is
trust/staff-gated at the serializer layer, not the unrestricted default.

The goal is that stakes feel *consistent regardless of which GM is running the
table* — a HIGH-risk beat means roughly the same thing whether GM A or GM B
authored it, because both are drawing from the same catalog and both are capped
by the same bands. We rejected the alternative of freehand stakes with
after-the-fact staff review: review-after-the-fact only catches outliers once
they've already reached players, and in practice drifts silently across tables
as each GM calibrates by feel rather than a shared reference. Gating severity
and reachability at declaration time (readiness, not review) keeps the
inconsistency from ever reaching a player-facing beat.

> Status: accepted · Source: #1770; extends ADR-0067 (Beat.risk is the stakes
> wager declaration), pairs with ADR-0076 (chain rule) and ADR-0077 (effective
> risk)

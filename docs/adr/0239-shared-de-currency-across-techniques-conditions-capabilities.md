# One shared DE currency and reference frame across techniques, conditions, and capabilities

ADR-0223 priced techniques in damage-equivalents (DE) but left conditions and
capabilities unpriced — a `ConditionTemplate`'s DE existed only entangled inside
whatever technique cast it, and capability grants priced flat 0 ("no cast seam"). #3390
extends the same currency to both, and every instrument now anchors on ONE shared
`compute_reference_frame(context)` (extracted from the technique evaluator's own pass-1
median-baseline-attack bootstrap into `world/magic/services/de_valuation.py`) rather
than each instrument deriving its own reference median — a second, independently-drifting
"1 DE" would defeat the entire point of a shared currency. The rejected alternative was
letting the condition and capability evaluators compute their own reference frames (simpler
per-module, but two panels could silently disagree on what "1 DE" means as content changes).

A capability's DE-per-point uses a documented linear estimate — each authored
`CheckTypeCapabilityModifier.weight` treated directly as a marginal `roll_modifier`
shift — rather than the full truncated/largest-remainder allocation
(`world.checks.services._capability_point_allocation`), because that allocation is only
meaningful against a real character's simultaneous capability set, which doesn't exist
for "one abstract point of capability X." A capability with zero authored bridge rows
prices 0 DE with an explicit `no_authored_bridge` flag (today, every capability — no
production seeder authors these rows yet) rather than crashing or silently omitting it,
so "genuinely worth nothing" stays distinguishable from "nobody's wired it into a check
yet." Standalone condition valuation deliberately excludes the team-damage-percent lane
and stage-scoped DoT rows (both need technique-wrapper context — a target_kind, or a
cast's own duration/severity distribution — that a bare `ConditionTemplate` doesn't
carry); both surface as named `UNPRICEABLE` gap rows, not silent zeros.

> Status: accepted · Source: issue #3390

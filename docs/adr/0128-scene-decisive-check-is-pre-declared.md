# 0128 — Scene decisive-check is pre-declared, not post-hoc

> Status: accepted · Date: 2026-07-12

## Context

Issue #1748 needs a way for a GM to mark a specific check within a social/
negotiation scene as that scene's decisive check for a linked `Beat`, so its
graded `CheckOutcome` propagates to `record_outcome_tier_completion` — the
same seam combat (PR2) and missions (PR3) use.

Unlike combat and missions, scenes have no single, unambiguous completion
point. A scene can have many social checks (persuade, intimidate, deceive...).
The GM needs to identify which one was decisive.

Two approaches were considered:
- **Pre-declared**: GM marks "the next check is decisive" before it resolves
- **Post-hoc**: GM picks the decisive check after the scene, from among
  resolved checks

Additionally, freeform scenes have no encounter-start or mission-issue seam,
so stakes contract activation must happen at some point during the scene.

## Decision

**Pre-declared marking.** The GM creates a `DecisiveCheckMarker` before the
decisive check resolves. When the next graded social check produces a
`CheckOutcome`, it triggers the marker.

**Any graded check wins.** No check-type or initiator filtering for MVP. The
GM trusts themselves to time the marker creation right before the decisive
interaction.

**Stakes activation rides marker creation.** `DecisiveCheckMarker` creation
calls `activate_stakes_for_scene` — the same function combat uses — so the
stakes contract locks before the check resolves. This is the freeform-scene
equivalent of encounter creation or mission acceptance.

## Rationale

1. Pre-declared matches the combat/mission pattern (activate at commit,
   resolve at completion) and satisfies the activation requirement naturally.
2. "Any graded check wins" is the simplest MVP. Cancel + re-create is the
   recovery path if a wrong check triggers the marker.
3. Stakes activation must precede resolution to compute effective risk.
   Marker creation is the natural commit moment for freeform scenes.

## Consequences

- Check-type filtering is a YAGNI follow-up if false triggers become a problem.
- Post-hoc marking requires persisting CheckOutcome on SceneActionRequest
  (currently transient) — deferred as a future enhancement.
- The hook fires at three resolution-path call sites (consent social action,
  direct social action, benign standalone cast) to cover all paths that
  produce a `CheckOutcome` in a scene context.

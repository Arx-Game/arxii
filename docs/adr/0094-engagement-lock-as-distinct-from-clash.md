# ADR-0094: Engagement Lock is distinct from Clash

**Date:** 2026-07-07
**Status:** Accepted
**Context:** #2020

## Context

The foil duels feature (#2020) needs a pairing between one PC and one opponent
within a group encounter. The existing `Clash` model (with its LOCK flavor)
handles metered contests — progress, thresholds, per-round contributions. The
question was whether to reuse Clash for the foil pairing or create a separate
model.

## Decision

Create a separate `EngagementLock` model. The lock is a targeting pairing
(who fights whom) with a lifecycle and drama-hook seam. Clash is a metered
struggle (the back-and-forth). They compose: `EngagementLock.clash` (nullable
FK) links to a Clash when one opens between the locked pair.

## Rationale

- Clash is fundamentally a **metered contest** (progress, win thresholds,
  per-round contributions from both sides). A foil pairing has no meter —
  it's a targeting override with an interference cost.
- The glossary reserves "clash" for the metered contest; conflating would
  violate the canonical term.
- The iff constraints on Clash (flavored fields) would need another exception
  for a no-meter flavor.
- The lock needs its own lifecycle (status, initiated_by, break_reason) and
  drama-hook seam (flow events) that don't fit on Clash.

## Consequences

- Two models where one might have sufficed, but with clear separation of
  concerns: pairing vs. struggle.
- The nullable `clash` FK on `EngagementLock` is the composition point.

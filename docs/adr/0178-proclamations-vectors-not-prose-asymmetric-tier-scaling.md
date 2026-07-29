# ADR-0178: Proclamations use vectors-not-prose with asymmetric tier scaling

**Date:** 2026-07-29
**Status:** Proposed
**Issue:** #2842

## Context

Issue #2842 adds public proclamations — a character declares a position
aligned to an authored stance archetype, and the world reacts. The design
extends ADR-0175 (surveillance harvests mechanical records, never prose):
no agent ever parses RP text. Prose is for players; vectors are for mechanics.

The existing `PhilosophicalArchetype` model already implements the six-axis
principle dot product for deed-judgment. Proclamations need a sibling table
with the same field shape but independent vocabulary — a stance is a declared
position, not a deed judgment.

## Decision

1. **Vectors-not-prose:** `StanceArchetype` carries six `{axis}_delta` fields
   (same shape as `PhilosophicalArchetype`). The dot product against each
   society's principles produces the reputation delta. `Proclamation.prose`
   is a display-only TextField — never read by any mechanic.

2. **Asymmetric tier scaling:** an oratory/persuasion check determines the
   outcome tier. For aligned societies (dot > 0), reputation gain scales with
   success level — a failed roll wins nobody. For opposed societies (dot < 0),
   reputation loss is mitigated by success and taken in full on failure.

3. **Domain edicts ride proclamations:** `EdictKind` carries a payload
   (`income_gross_pct`, `weekly_unrest_delta`, `weekly_upkeep_coppers`) that
   applies while a `DomainEdict` is active. Enacting = issuing the kind's
   inherent stance as a proclamation (the social bill) + the standing payload
   (the mechanical bite).

4. **Sibling table, not a shared table:** `StanceArchetype` and
   `PhilosophicalArchetype` are separate models with the same field shape.
   Vocabularies grow independently; a stance is never also a deed-judgment
   archetype.

## Consequences

- A failed proclamation costs the issuer nothing with aligned societies but
  offends opposed ones fully — the asymmetric design rewards skill with allies
  while making public statements risky with adversaries.
- Edict payloads are PLACEHOLDER tuning constants, adjustable on reseed
  without row churn (`update_or_create`).
- Org-level principle overrides (`{axis}_override`) are a future extension;
  v1 applies deltas through the society path only.

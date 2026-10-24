# ADR-4619-A: A technique shakes morale through its own payload row

**Date:** 2026-10-23
**Status:** Accepted
**Issue:** #4619 (slice 5 of #4573)

## Decision

A technique's own morale effect is a one-to-one, prose-free payload row
(`TechniqueMoraleEffect`) with a draft copy (`TechniqueDraftMoraleEffect`). It holds a base
amount, a share of the cast's effective power, a step per success level above a minimum, and
that minimum. Combat reads it in the technique resolver, after damage, over the opponents the
cast resolved on, and removes the computed amount from each enemy. It adds no roll: it reads
the cast's existing check result. Allies, charmed enemies and opponents that are fled or
defeated are skipped, and a mindless tier takes the configured share of the amount. The
row makes a technique hostile and enemy-aimed like any other hostile payload. The builder
prices it per point like damage (`payload_base_cost` plus the computed amount times
`damage_unit_cost`), reusing existing config columns; the figure is a tuning value.

## Rejected

Morale columns on `Technique`: every effect a cast has is a payload row with a draft copy, and
a column would give morale its own authoring and summary path. A "fear" `DamageType`: it would
push the health code into a morale branch, and damage soak and resistance mean nothing to
morale. A condition: it needs an authored name, and this row has no prose to author.

# ADR-0109: Obstacle Both-Sides Block + Counterplay

**Date:** 2026-07-10
**Status:** Accepted

## Context

Issue #2019 builds battlefield-shaping magic (conjured walls/Barricades).
The positioning graph's `PositionEdge` is combat-agnostic. The question: should
conjured walls block based on faction (allies pass, enemies blocked) or block
all movement with counterplay?

## Decision

Conjured walls block **all** movement (both allies and enemies). Every
conjured obstacle attaches a `gating_challenge` (climb/smash) for counterplay.
No faction/allegiance field is added to `PositionEdge`.

## Rationale

- Matches the "real tactical consequence" vision — a Barricade can trap allies.
- Keeps the positioning graph combat-agnostic (no allegiance coupling).
- Reuses existing `gating_challenge` machinery (no new model).
- Faction-passable behavior can be added per-technique in future content
  without a model change.

## Consequences

- Players must be careful about positioning allies behind walls.
- The gating challenge provides the escape valve (anyone can climb/smash).
- Duration + encounter-end teardown ensures no permanent graph corruption.

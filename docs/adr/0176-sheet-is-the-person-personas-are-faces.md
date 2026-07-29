# ADR-0176: The sheet is the person; personas are faces — identically for PCs and NPCs

## Status

Accepted (issue #2827)

## Context

NPCs existed as four unrelated models (Functionary placement, NPCAsset
relationship, Standing body, Story sheet) with copy-based one-way
transitions — promotion literally deactivated the source and minted a new
identity, so nothing survived moving up or down the ladder, staff work
scaled per placement, and masked NPCs (a covert-org member whose "real
identity" should be discoverable) had no coherent representation.

## Decision

One spine, one rule, both populations: **`CharacterSheet` is the true
identity and is never itself a social surface; personas are faces on it.**
PRIMARY is the default public face; a mask is another persona on the same
sheet (ESTABLISHED = durable alias, TEMPORARY = one-scene veil). Memberships,
standing, reputation, and regard key per-persona (the leaky-mask design);
secrets anchor to the sheet; piercing a mask is the existing
`PersonaDiscovery` + `PERSONA_LINK` clue machinery — for NPCs exactly as for
PCs. NPC tiers are **layers on the spine** (placement link → asset claims →
body → pilot → roster entry), added and retired by services; demotion retires
layers and nothing hard-deletes, because persona-anchored history is the
record. Tier-1 instantiation mints the sheet+primary persona at first
engagement (ADR-0058's ephemeral→durable seam) and is the one moment identity
is created.

## Rejected

- **A parallel NPC-identity model** (NPC-specific name/mask tables) — two
  identity systems for one social fabric; mask-piercing gameplay would need
  duplicate machinery.
- **Persona-as-spine** (no sheet until later tiers) — personas require a
  sheet today, and secrets/discovery anchor to sheets; a persona-only NPC
  would fork every anchor.
- **Copy-on-promotion (status quo)** — identity discontinuity is what made
  promotion/demotion heavy and rostering impossible.

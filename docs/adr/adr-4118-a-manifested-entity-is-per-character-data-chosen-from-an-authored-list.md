# ADR-4118: A manifested entity is per-character data, chosen from an authored list

**Issue:** #4118 · **Related:** ADR-4098 (ultimates are flagged techniques), ADR-0010 (FK
direction), the flow-payload `summon_ally` (ADR-0059).

## Context

Arx 1 GMs ruled that some techniques bring a bound entity into a fight: a devotee's god
arrives, or a Beastlord's companion. Two characters casting the same technique bring
different entities, because each is bonded to a different being or companion. A technique is
shared catalog data, so the choice cannot live on it as a single entity.

## Decision

The technique carries an authored list of options (`TechniqueManifestOption`: a
`WorshippedBeing` or a `CompanionArchetype`, plus a tier). A character's own choice is
per-character data on their version of the technique (`CharacterManifestation`, unique per
character and technique), picked from that list and constrained by their bonds: it is valid
only while the character is a devotee of the being or owns an unreleased companion of the
archetype. The cast resolves it at runtime (`manifest_bound_entity`), so a lapsed bond
manifests nothing.

## Rejected

A per-technique entity FK (`Technique.manifests -> WorshippedBeing`). One technique row then
names one entity, so supporting several players means duplicating the technique per player,
which breaks the shared catalog, the ultimate reveal (keyed on the technique) and every
authored-once rule. The FK direction also points from the general primitive to the
specific one.

## Consequences

The choice is set by GM or staff in the admin; there is no character-creation picker and no
manifestation outside combat. A being option's tier needs an `OpponentTierTemplate` row or
the cast raises, which rolls back the whole `resolve_round` for every participant until
staff add the row (and the avatar's move into the caster's room can show in memory while
the database has it elsewhere); the `manifest-tier-templates` dashboard probe flags it.
We chose the sentinel over a guard on purpose. The flow-payload
threat-pool `summon_ally` is a separate mechanism and stays.

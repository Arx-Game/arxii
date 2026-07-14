# ADR-0125: BattleUnit is a thin join over MilitaryUnit — no denormalized stats

**Status:** accepted · **Date:** 2026-07-14 · **Source:** #2216

## Context

Issue #2216 ("Army food provisioning") revealed a deeper gap: the codebase had
no persistent military unit model. `BattleUnit` existed only inside a `Battle`
— it carried all identity and stats (name, descriptor, quality, commander,
strength, morale, individual_count, properties, capabilities) but was destroyed
when the battle ended. The roadmap explicitly flagged this: "war covenants exist
but have nowhere to resolve into: no Battle/Army/Regiment model."

The user wanted persistent units tied to domains/orgs/lords that can form armies
and project into battles. The original issue (food provisioning) cannot be built
until persistent units exist, so #2216 was reframed to deliver the foundation.

## Decision

`BattleUnit` is refactored to a **thin join record** referencing a persistent
`MilitaryUnit`. All identity and stats live on `MilitaryUnit` — the single
source of truth (per ADR-0014: "source data stays the single truth; we rejected
denormalized synthesized rows"). `BattleUnit` keeps only battle-scoped link
state: `battle`, `side`, `place`, `transit_x/y`, `transit_target_place`,
`status`, and a `military_unit` FK.

Read access is transparent via `@property` proxies on `BattleUnit`
(`unit.strength` delegates to `unit.military_unit.strength`). Write access is
explicit: resolution code writes through `unit.military_unit.strength = ...`
and saves the MilitaryUnit. This minimizes changes to the resolution engine
while keeping the model honest.

`BattleUnitCapability` (the through-model for capabilities M2M) is removed —
capabilities live on `MilitaryUnit` via `MilitaryUnitCapability`. The
`BattleUnitTemplate` catalog (staff-authored unit stat blocks for staging) is
unchanged — it's a catalog, not a live unit.

A new `Army` model groups `MilitaryUnit`s via `ArmyMembership` (join/leave
through-model). Armies persist across battles and can be disbanded.

## Consequences

- Battle results (strength/morale losses) now persist on MilitaryUnit after a
  battle ends — units carry their wounds forward.
- Enemy/summoned units become transient MilitaryUnits with null `owner_org`.
- The data migration (0031) creates MilitaryUnit rows for existing BattleUnits
  and copies all fields, capabilities, and properties.
- Resolution code has one extra `military_unit.save()` per STRIKE/ROUT/RALLY —
  query-count budgets were raised by 2 to accommodate.
- `effective_capability()` and `has_property()` on BattleUnit are proxy methods
  delegating to MilitaryUnit — callers (resolution.py modifier stack,
  vehicle speed, MOVE distance) work unchanged.

## Follow-ups (deferred)

- Army food provisioning (original #2216 scope — standing army food consumption
  from domain FoodStockpile, morale+strength penalties when short).
- Battle integration (Army→BattleSide deployment at staging, post-battle
  result flowback).
- Defense role (standing units vs PvE threats — brigands, monsters, Afflicted
  Hordes).
- Magical identity/mantles (banners, magical significance, covenant
  resurrection ties).

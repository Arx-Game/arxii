# Ship is a per-kind Building extension; hull reuses fortification_level

`ShipDetails` (#1832) decorates `buildings.Building` via a OneToOne primary key —
composition over inheritance, the same pattern `Covenant` uses over `Organization` —
rather than a standalone Ship model with its own Area/room/ownership plumbing. Its
hull stat IS `Building.fortification_level`, reused directly (a hull upgrade is a
`FORTIFICATION_UPGRADE` Project, not a new Ship-specific Project kind): a ship is
fortified in exactly the sense a keep is, and duplicating that ladder would diverge
in balance and upgrade UX for no reason. Two more decisions travel with this one:
(1) `world.ships.battle_wiring.apply_ship_battle_outcome` is registered as a
**battle-conclusion hook** (`world.battles.conclusion_hooks
.register_battle_conclusion_hook`) — a new registry pattern in `battles`, mirroring
`register_kind_handler`'s shape but for end-of-`Battle` side effects; `battles`
still imports nothing from `ships` (ADR-0010) — the hook is registered *by* ships at
its own app-ready time, not called *into* by battles. Rejected: a conditional
import/dispatch inside `conclude_battle` itself, which would have made `battles`
aware of every downstream consumer of its conclusion event. (2) A ship's sanctum
bonus (`ship_sanctum_bonus`/`ship_sanctum_capabilities`) is **snapshotted once at
`materialize_ship_as_battle_vehicle` time**, not read live during battle rounds —
a battle can run for many rounds and a live pull-gate would need the ship's real
room state reachable mid-battle, which the ephemeral `BattleVehicle`/`BattlePlace`
pair was deliberately built not to require (ADR-0081/ADR-0085's abstract-front
model). Rejected: a live per-round sanctum lookup, which would reintroduce a
room-graph dependency mass battles can't carry.

> Status: accepted · Source: #1832 · Related: ADR-0010 (FK/import direction),
> ADR-0081/ADR-0085 (BattlePlace's room-independent abstraction)

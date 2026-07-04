# Ships glossary

Domain-local vocabulary for `world.ships` (persistent upgrades, repair, and the
covenant-scale combat bridge, #1832). Root terms live in `AGENT_GLOSSARY_MAP.md`;
the battle-vehicle vocabulary (`BattleVehicle`, `places_overlap`, REPOSITION/BREACH)
lives in `world/battles/AGENT_GLOSSARY.md` — this file only covers what's specific
to the persistent side.

- **Ship** — a `ShipDetails` row decorating a maritime `buildings.Building`
  (composition, mirrors `Covenant`↔`Organization`). Persists between battles;
  distinct from a `BattleVehicle`, which is the ephemeral in-battle snapshot a
  Ship materializes into. _Avoid:_ vessel (fine in prose, not as a model/var name
  — `ShipType`/`ShipDetails` are the canonical identifiers), boat.
- **ShipType** — the open, staff-authored catalog of ship categories (Sloop,
  Brigantine, Galleon) a Ship commissions against; carries PLACEHOLDER base
  stats. _Avoid:_ ship class, hull class.
- **ShipDetails** — the concrete per-Building ship row: persistent
  `handling_level`/`armament_level` investment, `crew_capacity`/`cargo_capacity`,
  `needs_repair`. The hull stat is NOT stored here — see "Hull" below.
  _Avoid:_ Ship (as a model name — the model is `ShipDetails`, matching the
  `*Details`-decorates-`Building` convention `ShipConstructionDetails` etc. share).
- **Hull** — `Building.fortification_level`, reused directly as the ship's hull
  stat (ADR-0086); a hull upgrade is a `FORTIFICATION_UPGRADE` Project, not a
  ship-specific kind. _Avoid:_ hull_level, hull points (no such field exists —
  don't invent one; read `ShipDetails.effective_hull()`).
- **ShipDeployment** — the durable link between a persistent `ShipDetails` and
  the ephemeral `BattleVehicle` it materialized into for one `Battle`. One row
  per (ship, battle) deployment. _Avoid:_ ship instance, deployment record.
- **Materialize** — the one-way translation
  (`battle_bridge.materialize_ship_as_battle_vehicle`) from a persistent Ship
  into a fresh `BattleVehicle` for a specific `Battle`: snapshots hull/handling/
  armament (+ sanctum bonus) at that moment. Not reversible and not re-run
  mid-battle — the snapshot is deliberately static for the battle's duration
  (ADR-0086). _Avoid:_ deploy, spawn (deploy is reserved for the resulting
  `ShipDeployment` row's narrative sense, not the verb for this operation).
- **Ship-as-sanctum** — a ship's deck room can carry an ordinary `SanctumDetails`
  installation exactly like any other room; `ship_sanctum_bonus`/
  `ship_sanctum_capabilities` read its woven SANCTUM threads into a
  `ShipStatBonus` and level-3+ capability grants, snapshotted at materialize
  time (never a live pull-gate during battle — ADR-0086). A ship has at most one
  sanctum room for MVP. _Avoid:_ ship sanctuary, blessed ship.
- **needs_repair** — the persistent damage flag `ShipDetails` carries after its
  materialized `BattleVehicle`'s hull was breached in battle, written back by
  the `apply_ship_battle_outcome` battle-conclusion hook on `conclude_battle`.
  Gates further `SHIP_UPGRADE`/hull-upgrade investment until a `SHIP_REPAIR`
  Project clears it. _Avoid:_ damaged, sunk (sinking is the in-battle hull-breach
  event; `needs_repair` is its persistent aftermath).
- **Battle-conclusion hook** — the registry
  (`world.battles.conclusion_hooks.register_battle_conclusion_hook`) `ships`
  registers `apply_ship_battle_outcome` into at app-ready time; every hook runs
  inside `conclude_battle` after beat resolution. A new pattern in `battles`
  (mirrors `register_kind_handler`'s shape) introduced by this system so
  `battles` never needs to import `ships` (ADR-0010). _Avoid:_ battle callback,
  post-battle listener.

## Explicitly out of scope (deferred, not built here — see roadmap)

- **familiar** — reserved for a future combat-summon/companion mechanic; a Ship
  is not a familiar and should never borrow that word.
- **clash** — reserved for the shipped opposed-magic contest (see
  `world/battles/AGENT_GLOSSARY.md`); never reuse for ship-vs-ship combat, which
  is REPOSITION/BREACH, not a Clash.
- **crew** (as named NPCs), **cargo** (as tracked goods), and **sea travel** — a
  Ship's `crew_capacity`/`cargo_capacity` are numbers, not systems; out-of-combat
  travel doesn't exist yet. See `docs/roadmap/planned-systems.md` /
  `docs/roadmap/crafting-economy.md`.

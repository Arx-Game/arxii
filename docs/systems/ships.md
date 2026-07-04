# Ships (#1832)

**Status:** shipped (persistent upgrades + repair + ship-as-sanctum + covenant-scale
combat bridge). Follow-up to **#1714** (the battle-time-only `BattleVehicle` naval
vertical slice — see [battles.md](battles.md#battlevehicle)), which had no
persistence, crew roster, or out-of-combat existence. This system gives a ship a
persistent life *between* battles: commission it, invest in it, sanctify it, sail it
into a `Battle` as a materialized `BattleVehicle`, and repair it afterward.

## Design

A ship is a **per-kind extension of `buildings.Building`** — composition over
inheritance, the same pattern `Covenant` uses over `Organization`. `ShipDetails`
decorates a `Building` (maritime `BuildingKind`, seeded as `"Vessel"`) via a
OneToOne primary key; the ship's hull stat is **`Building.fortification_level`**
itself — reused, not duplicated (see ADR-0086). The ship's one room (the "Main
Deck") is an ordinary `RoomProfile`/`Area`-backed entry room, so a sanctum can be
installed on it exactly like any other room (ship-as-sanctum).

Construction deliberately does **not** route through the permit/contribution
pipeline in `world.buildings.services` — permits, material contributions, and
size tiers are a House-specific authoring surface a ship commission doesn't use.
It reuses only the low-level Area/Building/entry-room steps
(`world.buildings.services.create_entry_room`).

## Models (`world.ships.models`)

- **`ShipType`** — open catalog (staff-authored, mirrors `BuildingKind`) of ship
  categories (Sloop, Brigantine, Galleon — seeded via `factories.ensure_ship_types()`).
  Carries PLACEHOLDER base stats: `base_hull`, `base_handling`, `base_armament`,
  `base_crew_capacity`, `base_cargo_capacity`.
- **`ShipDetails`** — the per-Building ship extension. `building` (OneToOne PK →
  `buildings.Building`), `ship_type` FK, `handling_level`/`armament_level`
  (persistent investment, raised via `SHIP_UPGRADE` Projects), `crew_capacity`,
  `cargo_capacity`, `needs_repair` (set when the ship's battle vehicle is
  breached; gates further upgrades). Methods: `effective_handling()` = base +
  `handling_level * HANDLING_PER_LEVEL`; `effective_armament()` similarly;
  `effective_hull()` = `self.building.fortification_level`.
- **`ShipDeployment`** — links a persistent `ShipDetails` to its in-battle
  `BattleVehicle` for one `Battle`. Lives in `ships` (not `battles`) per
  ADR-0010: the FK points from the more specific/dependent system at the
  reusable battle primitive, keeping `battles` free of a `ships` import.
- **`ShipConstructionDetails`** / **`ShipUpgradeDetails`** / **`ShipRepairDetails`**
  — per-Project payload rows, each a OneToOne PK onto the driving
  `projects.Project` with a nullable `applied_at` idempotency marker the
  completion handler sets exactly once. Mirror the shape of
  `world.buildings.models.FortificationUpgradeDetails`.

## Services (`world.ships.services`)

- **`start_ship_construction(persona, ship_type, name, covenant=None) -> Project`**
  — opens a `SHIP_CONSTRUCTION` Project. `persona` is the commissioning/funding
  persona (credited as `Building.owner_persona` regardless of covenant);
  `covenant`, when given, is the eventual deed-holder — `complete_ship_construction`
  transfers the ship's Area ownership to it via `transfer_ownership`, on top of
  (not instead of) crediting `persona`.
- **`complete_ship_construction(project, outcome_tier=None) -> ShipDetails`** —
  the `SHIP_CONSTRUCTION` kind handler (registered at app-ready time). Spawns the
  `Area` + `Building` (maritime kind, `fortification_level=ship_type.base_hull`)
  + one entry room ("Main Deck") + `ShipDetails`, exactly once (claim idiom on
  `ShipConstructionDetails.applied_at`).
- **`start_ship_upgrade(persona, ship, stat, target_level) -> Project`** /
  **`complete_ship_upgrade`** — a `SHIP_UPGRADE` Project raising `handling` or
  `armament` to `target_level` (a `ShipUpgradeStat` value); monotonic max-set on
  completion (mirrors `fortification_services.start_fortification_upgrade`).
  Raises `ShipNeedsRepairError` if the ship needs repair first, or
  `ShipUpgradeError` for an invalid stat / non-increasing target.
- **`start_ship_hull_upgrade(persona, ship, target_level) -> Project`** — a ship's
  hull *is* `Building.fortification_level`, so this is a thin wrapper (after the
  same `needs_repair` gate) delegating straight to
  `buildings.fortification_services.start_fortification_upgrade`
  (`FORTIFICATION_UPGRADE` kind — no separate ship-hull Project kind exists).
- **`start_ship_repair(persona, ship) -> Project`** / **`complete_ship_repair`** —
  a `SHIP_REPAIR` Project that clears `ShipDetails.needs_repair`.

All four completion handlers are registered with
`world.projects.services.register_kind_handler` in `ShipsConfig.ready()` and are
idempotent via the same `applied_at`-claim idiom used across `world.buildings`.

## Ship-as-sanctum (`world.ships.sanctum_bonus`)

A ship has at most one sanctum room for MVP — the sanctum system needs no ship
awareness of its own; `ship_sanctum_bonus(ship)` / `ship_sanctum_capabilities(ship)`
locate the active `SanctumDetails` installed on one of the ship's rooms (matched
by `feature_instance.room_profile.area == ship.building.area`) and read its woven
SANCTUM `Thread`s:

- **`ship_sanctum_bonus(ship) -> ShipStatBonus`** — sums active woven SANCTUM
  thread levels into a `ShipStatBonus(hull, handling, armament)`. PLACEHOLDER
  mapping: all three fields equal the summed thread levels — a per-resonance
  split is a later content pass.
- **`ship_sanctum_capabilities(ship) -> list[Resonance]`** — the distinct
  resonances of woven SANCTUM threads at level ≥ 3, each unlocking a
  PLACEHOLDER `BattleUnitCapability` at materialize time (see below).

The bonus is **snapshotted at materialize time, not read live** during battle —
see ADR-0086.

## The combat bridge (`world.ships.battle_bridge`)

**`materialize_ship_as_battle_vehicle(ship, battle, side, place_name=None) ->
BattleVehicle`** is the one-way translation from the persistent `ShipDetails`
into the battle system's ephemeral `BattleVehicle` (paired `BattleUnit` +
`BattlePlace` + hull `Fortification`, per #1714/#1713). Called once per ship per
battle deployment:

1. `create_battle_vehicle(..., vehicle_kind=VehicleKind.SHIP, is_structural=True)`
   builds the vehicle; a `ShipDeployment` links it back to `ship`.
2. The hull `Fortification`'s integrity is overwritten from
   `ship.building.fortification_level + bonus.hull` (a damaged ship — `needs_repair`
   — takes a `DAMAGED_HULL_DISCOUNT` integrity penalty).
3. A `speed` `BattleUnitCapability` is set to `ship.effective_handling() +
   bonus.handling` — read by REPOSITION (`world.battles.resolution`).
4. `BattleUnit.strength` is set to `ship.effective_armament() + bonus.armament`.
5. Each level-3+ sanctum resonance grants a PLACEHOLDER
   `sanctum_<resonance>` `BattleUnitCapability`.

From here the ship is an ordinary `BattleVehicle` — REPOSITION/BREACH/sinking/
ejection all run through the existing `world.battles` machinery unmodified (see
[battles.md](battles.md#battlevehicle)).

## The repair writeback (`world.ships.battle_wiring`)

**`apply_ship_battle_outcome(battle)`** is registered as a
**battle-conclusion hook** (`world.battles.conclusion_hooks
.register_battle_conclusion_hook`, called from `ShipsConfig.ready()`) — the new
pattern this system introduces in `battles`, mirroring
`world.projects.services.register_kind_handler`'s registry shape but for
end-of-`Battle` side effects rather than Project completion. `conclude_battle`
runs every registered hook after resolving beats; this one walks every
`ShipDeployment` tied to the battle and, for each whose hull `Fortification`
ended up `breached`, sets `ShipDetails.needs_repair = True` — gating further
`SHIP_UPGRADE`/hull-upgrade investment until a `SHIP_REPAIR` Project clears it.
`battles` imports nothing from `ships` — the hook registry keeps the coupling
one-way (ADR-0010; see ADR-0086 for why a new registry rather than an `if
importlib.util.find_spec("world.ships")` branch in `battles` itself).

## Telnet (`commands.ships.CmdShip`, key `ship`)

One `DispatchCommand` routing four subverbs through `dispatch_player_action` —
the same REGISTRY seam the web will use — to the Actions in
`actions/definitions/ships.py`:

```
ship                                            — status hub
ship status [ship_id=<n>]                       — status hub, or one ship's report
ship commission ship_type=<name> [covenant=<name>] name=<ship name>
ship upgrade stat=handling|armament|hull level=<n> [ship_id=<n>]
ship repair [ship_id=<n>]
```

`commission` resolves `ship_type`/`covenant` to model instances in the command
(mirrors `crafting_station.py`'s `feature_kind`/`room_profile` contract);
`upgrade`/`repair`/`status` resolve their target ship inside the Action itself
(`_resolve_ship` — explicit `ship_id`, else the actor's current room) and the
command only forwards `ship_id` when supplied. `name=` is a greedy token (must
come last) so a ship name may contain spaces.

## Actions (`actions/definitions/ships.py`, all REGISTRY, `category="ships"`)

- **`CommissionShipAction`** (key `commission_ship`, `target_type=SELF`) — gated
  by `HasCharacterSheetPrerequisite` only (no existing ship to own yet). Wraps
  `start_ship_construction`.
- **`UpgradeShipAction`** (`upgrade_ship`) / **`RepairShipAction`** (`repair_ship`)
  — gated by `IsShipOwnerPrerequisite` (persistent investment only the owner may
  authorize). `UpgradeShipAction` dispatches `hull` to
  `start_ship_hull_upgrade` and `handling`/`armament` to `start_ship_upgrade`.
- **`ShipStatusAction`** (`ship_status`) — read-only, ungated.

**`IsShipOwnerPrerequisite`** (`actions/prerequisites.py`) resolves the target
ship the same way `_resolve_ship` does, then checks ownership: direct
(`ship.building.owner_persona`, set for every commissioning persona regardless
of covenant) or covenant-held (`world.locations.services.is_owner` walks the
ship's entry room's `LocationOwnership` cascade, set by `transfer_ownership`
when a covenant is the deed-holder — covers any current member).

## REST API (`world/ships/{views,serializers,filters,urls}.py`)

Read-only for now — writes stay on `action.run()` via telnet (a web dispatch
endpoint is a fast-follow once the frontend needs one):

- `GET /api/ship-types/` — `ShipTypeViewSet` (open catalog, unpaginated).
- `GET /api/ships/` / `GET /api/ships/<id>/` — `ShipViewSet`, scoped to the
  requesting user's active persona's owned ships (direct or covenant-held,
  mirroring `IsShipOwnerPrerequisite`'s ownership definition). `ShipDetailsFilterSet`
  filters on `ship_type`/`needs_repair`. `ShipDetailsSerializer` exposes the
  effective stats (`effective_handling`/`effective_armament`/`effective_hull` —
  computed, never duplicated arithmetic) plus owner persona/covenant.

## Cross-app dependencies

`world.buildings` (Building/BuildingKind/entry room — a ship IS a maritime
Building), `world.areas` (Area + ownership transfer), `world.projects` (the four
Project kinds + `register_kind_handler`), `world.battles` (`create_battle_vehicle`,
`BattleUnitCapability`, `Fortification`, `register_battle_conclusion_hook` — see
ADR-0010: `ships` depends on `battles`' reusable primitives, never the reverse),
`world.magic` (`SanctumDetails`/`Thread`/`Resonance` — read-only, no `magic`→`ships`
import), `world.locations` (`transfer_ownership`/`is_owner`), `world.scenes`
(`Persona`), `world.covenants` (`Covenant` as an optional deed-holder).

## Deferred (not in this system's scope)

Out-of-combat sea travel, a crew roster beyond `crew_capacity` (a number, not
named NPCs), mission integration, cargo mechanics beyond `cargo_capacity` (a
number, not tracked goods), and familiars/companion-style summon mechanics —
see `docs/roadmap/planned-systems.md` and `docs/roadmap/crafting-economy.md`.

**Source:** `src/world/ships/`

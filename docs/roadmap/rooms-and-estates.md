# Rooms, Buildings & Estates

**Status:** Room Builder shipped (#670 — PR1 backend + PR2 web builder)
**Depends on:** Areas (data layer), Items (containers, ownership), Roster (character ownership)

## Built (2026-07-01, #670 PR1 — Room Builder backend)

- **Space-budget model (ADR-0075):** `BuildingSizeTier` (Hut 50 → Citadel 5000,
  PLACEHOLDER) → `Building.space_budget`; rooms carry `RoomSizeTier` units
  (Micro 2 → Expanse 2500 — the shared ladder the future creature-size stat
  reads) and spend from the pool. Replaced `max_rooms`.
- **The builder:** owner-gated dig (stub: direction + name, `like=` exemplar
  copy), resize, remove (evicts to `Building.entry_room`, connectivity-guarded),
  exit link/unlink/rename; cosmetic grid coords + telnet ASCII `room/map`.
- **Project kinds:** `BUILDING_EXTENSION` (grow the budget through the funded
  contribution pipe) and `INTERIOR_DESIGN` (commission an admin-authored polish
  `ProjectTemplate` against building or room — finally wires the #676 polish
  machinery to a player verb).
- **Tenancy + primary home:** owner assigns/ends room tenancies
  (`LocationTenancy` is the one tenancy model now); tenants designate a
  primary home (Arx-1 `addhome`) that anchors `prestige_from_dwellings`
  (home room polish + building polish iff you own the home's building —
  replaced the portfolio-sum/double-count) and syncs the #1514 residence.
- **Telnet:** the `room` family (`room/dig`, `/desc`, `/name`, `/size`,
  `/public`, `/addexit`, `/removeexit`, `/renameexit`, `/drop confirm`,
  `/map`, `/home`, `/tenant`, `/evict`, `/extend`, `/decorate`), aliases
  `build` + legacy `manageroom`.
## Built (2026-07-02, #670 PR2 — building-manager API + web builder)

- **Web-addressable actions:** structural builder actions take an explicit
  `room_id` anchor (`to_room_id`/`exit_id` for links), prerequisite-gated on
  the resolved room, so the canvas operates building-wide; new `place_room`
  action for cosmetic map re-placement (drag).
- **Read API** (`/api/buildings/`): owner-gated manager payload (rooms +
  sizes + grid + tenancies, exits, budget, floors), the for-room resolver
  RoomPanel uses (permission booleans only), room-size-tier + decoration-
  template catalogs. Writes stay on action dispatch.
- **Web builder** (`frontend/src/buildings/`): "Manage Building" on RoomPanel
  opens a full-screen React Flow canvas — rooms on the grid, click a ghost
  cell to dig (direction prefilled), drag to re-place, exit-pair edges,
  floor switcher, budget meter — with a room detail panel (identity, size,
  exits, tenants, duplicate-via-`like=`, remove w/ stranded-room guard
  surfaced) and dialogs for decoration commissions + budget extensions.
  Tenants get "Set as Home" on RoomPanel.

## Built (2026-07-02, #1469 — discoverable throwback styles)

- Style tiers: default (living-realm) vs discoverable throwback
  (`is_default=False`, higher `prestige_bonus`, `cost_multiplier` knob —
  PLACEHOLDER magnitudes; charging deferred to the economy pass).
- Discovery composes the existing clue→codex→RESEARCH pipeline (ADR-0079):
  research the style's clue → contributors learn its codex entry →
  `can_build_style` opens → `room/style <name>` / `set_building_style` action
  dresses the building (climate affinities re-sync via `set_building_style`).
- Owned home building's style now feeds dwelling prestige. Ratified out of
  scope (Apostate, 2026-07-02): ship styles, caste vernaculars, out-of-place
  social reads.

## Built (2026-07-06, #1930 — condition tiers replace polish decay; ADR-0093)

- `Building.condition_tier` ladder (Decayed…**Excellent**…Immaculate;
  Immaculate name ratified by Apostate) with per-tier prestige multiplier
  (5%–200% PLACEHOLDER, tuning ledger §6) — missed upkeep now accrues
  **capped arrears first**, then slides tiers after a grace window; it never
  mutates polish/feature rows. The #676 decay curve + never-wired
  restoration half are deleted.
- Above-normal shine is a temporary spend, and the Grand Preparation is a
  **funded cleanup project** (`BUILDING_PREPARATION`): its cost is a
  proportion of the house's prestige (25%/50% PLACEHOLDER, floored),
  bankrolled via `project/donate` and sped along with AP Household Command
  checks ("Direct the Household" ContributionMethod). Completion climbs
  Excellent → Extravagantly Polished → Immaculate; dwell-decays back in ~a
  week unless the ultra-upkeep premium holds Immaculate; an underfunded
  lapse fizzles. Recovery: `settle_upkeep_arrears` + `refurbish_building`
  (priced restore to Excellent). Owner action family (telnet + web):
  `settle_building_arrears` / `refurbish_building` / `prepare_building` /
  `toggle_ultra_upkeep`.
- Mothballing: 90d-inactive owners' buildings hide from the grid
  (`is_public` snapshot/restore) and freeze accrual — ghost towns are
  authored; returning players face a bounded bill and a dulled-but-intact
  home. "Dormant" retired from buildings vocabulary.
- Renown payload shows only the qualitative `condition_label` (public
  fiction); financial state is owner-only.

## Built (2026-07-02, #1514 close-out — owner build-HUD + fixture verbs)

- `room_exposure_breakdown(room)` — per-axis pressure/mitigation/net (the
  build-to-win readout: "COLD +6, −4 hearth = +2 residual").
- Fixture verbs `place_room_fixture`/`remove_room_fixture` (+ telnet
  `room/fixture`/`room/removefixture`) — comfort decorations finally have a
  player caller; 3 PLACEHOLDER kinds seeded.
- Owner build-HUD in the web builder (ComfortSection on the room panel,
  backed by `manager/room/<id>/comfort/`).
- Deliberately not built: websocket room-state comfort duplication (the
  inhabitant surfacing shipped as #1522's REST widgets + weather echo);
  Chilled/Soaked threshold conditions (Tehom's integration, per the spec).

## Built (2026-07-10, #2036 — residence declaration + room aura tagging)

- **Residence declaration widened:** `set_primary_home` now also writes
  `CharacterSheet.current_residence` (the daily resonance-trickle gate, `world/magic`'s
  Spec C) alongside the #1514 Evennia `home`, and accepts org-derived owner/tenant
  standing — not only a direct `LocationTenancy` row — by minting a personal tenancy
  first (`grant_tenancy`) when the persona's only standing comes from a shared
  family/org/Academy grant. `end_tenancy` clears `current_residence` when the ended
  tenancy was the declared residence. `CmdHome`'s `home/set` switch was consolidated
  onto the same `SetPrimaryHomeAction` seam `room/home` and the web "Set as Home" button
  use (previously a duplicated, drifted hand-rolled check).
- **Room aura tagging (a room's declared magical character):** `room/aura <resonance>` /
  `room/aura clear <resonance>` (`TagRoomResonanceAction`/`UntagRoomResonanceAction`,
  web `RoomAuraPicker`) write/remove a `LocationValueModifier(key_type=RESONANCE)` row —
  the same aura a resident's residence trickle reads. Gated by `IsRoomTenantPrerequisite`,
  widened to owner-OR-tenant standing (previously a direct tenancy row only); tagging
  additionally requires the caller has claimed that resonance.
- **Zero-manual-step CG on-ramp:** `StartingArea.grants_residence_tenancy` (an authored
  per-area toggle) auto-grants a starting-room `LocationTenancy` at CG finalization,
  which auto-defaults both Evennia `home` and `current_residence` — a new character
  reaches the trickle gate with no manual player step.
- See `world/magic/CLAUDE.md` "Residence declaration + room aura tagging" for the full
  declare→tag→tick mechanism, including the intentional emergent synergy where a
  Sanctum's Ritual of Homecoming writes the same `LocationValueModifier` row shape onto
  its own room.

## Overview

Rooms are the spatial substrate of the world. Buildings and estates are
collections of rooms that a character (or organization) owns and can develop.
This domain is about **what owning a room/building/estate gets you** —
the IC affordances that wealth and territory unlock — not the meta-task of
building rooms (that lives in [Tooling](tooling.md)).

## Key Design Points

- **Ownership has consequences.** Owning a room is not just a tag; it should
  unlock things. Decoration, furnishing, NPCs, security, special-purpose rooms
  (lab, vault, ballroom, smithy), location for housing valuables, place to
  hold events with reduced cost, etc. **Lab is now a real, implemented
  crafting-station kind** — a second Room Feature (`RoomFeatureServiceStrategy.LAB`)
  with a durability gate/wear/repair economy over `run_crafting_recipe` (#1234; see
  [crafting-economy.md](crafting-economy.md) and `docs/systems/items.md`). Vault,
  ballroom, smithy, and the other special-purpose kinds remain still-future.
- **Estates aggregate rooms.** A noble's manor isn't a single room — it's a
  collection of connected rooms that share an ownership boundary. Estate-level
  features (servants, security, prestige) operate at this scope.
- **Servants & retrievers** — owned NPCs that perform errands within the
  spaces their owner controls. Examples:
  - **Outfit retrieval:** "wear my Court Attire" from a parlor while the
    wardrobe is in the dressing room → servant fetches it. Room echo:
    *"A maid bows and departs to fetch your evening gown."* Delay before
    the equip lands.
  - **Item fetch:** "bring me my sword" — servant retrieves any owned item
    from any room in the same estate.
  - **Bath / meal / refreshment preparation** — servants set up scenes,
    delivering pose-relevant ambience.
  - **Carrying messages** between rooms in the estate.
  - **Guard / announce** behaviors when visitors enter.
  Servants are an alternative path that widens reach checks beyond
  same-room. The default path stays "you must be in reach" — servants
  layer on top, intercept the `NotReachable` failure case, queue the
  delayed action with appropriate echoes, and complete the original
  intent.
- **Building decoration** — interior design contributes to room "stats"
  (resonance, fashion, prestige, comfort) that affect events held there.
  See [Tooling](tooling.md) for the building/decorating mechanics.
- **Vaults & valuables storage** — secured rooms that protect items from
  theft. Owner-only access with exception lists.
- **Special-purpose rooms** — lab, smithy, library, gallery — give bonuses
  to relevant activities performed inside them.

## What Exists

- **Areas system** (`src/world/areas/`) — `Area`, hierarchical containment,
  `AreaClosure` materialized view for fast ancestor queries
- **Room creation tooling** in `src/commands/` and via Evennia builder
  commands

## Stats substrate (designed 2026-05-09 — `world.locations`)

Foundational data layer for ambient room state — crime, order, cleanliness,
lighting, noise, traffic, with cascade through the area hierarchy and
per-row decay/growth on modifiers. See
`docs/plans/2026-05-09-location-stats-design.md` for the full design.

**Key ideas:**
- Two models — `LocationValueOverride` (rare absolute claims that cut the
  cascade) and `LocationValueModifier` (common additive contributions that
  stack and decay). Each row carries either a stat (`stat_key`, StatKey
  TextChoices) or a resonance (FK to `magic.Resonance`), gated by `key_type`.
- Most-specific Override wins; absent any Override, all Modifiers in the
  chain sum + per-stat default, clamped to bounds (resonance reads start
  from 0 and are not clamped)
- `RoomProfile.is_outdoor` controls whether weather-system writes apply
- One polymorphic read service: `effective_value(room, *, stat_key=..., resonance=...) -> int`
- Many other consumer systems (encounter generator, DC modifier, weather,
  magic, events bonuses) plug in over time

## Climate → comfort (#1514, in progress)

Mechanical climate + a build-to-win comfort loop (motivated by the Arx-1 "Great Mango
Incident": flavour-only weather let a Caribbean open-air manor be built in four-season Arx).
Make climate *mechanical* so the world enforces theme through play, and let players win
against it by building — never a GM veto, just more work. Full design + anti-reinvention
ledger in issue **#1514**; security/access half (windows-as-egress, guards/defenses) split to
**#1515**.

- **Model:** typed **exposure axes** (`StatKey.COLD`/`HEAT`/`WET`/`WIND` in
  `EXPOSURE_STAT_KEYS`), each floored at 0 on the existing location-stats cascade — the floor
  *is* the "counters never harm" guarantee. Climate/weather/style push axes up; counter-fixtures
  push them down; `comfort_score(room)` reads the inverse of the summed *felt* residuals.
- **Slice 1 (done):** the COLD/HEAT axes + `room_discomfort` / `comfort_score` reads.
- **Slice 2 (done):** WET/WIND axes + **enclosure** (`RoomProfile.enclosure`,
  `RoomEnclosure` OPEN_AIR/ROOFED/WALLED/SEALED) gating the weather axes via `felt_exposure`
  (a roof stops rain, walls stop wind; temperature always seeps).
- **`ArchitecturalStyle` (done):** `ArchitecturalStyle` + `StyleAffinity` rows on `world.buildings`,
  with a `Building.architectural_style` FK and `set_building_style` materializing the affinities as
  cascade modifiers on the building's Area. Lore lives in a linked `CodexSubject`.
- **Decorations + comfort-level engine + in-room readout (done):** stackable `DecorationKind`/
  `RoomDecoration` (mitigation + amenity), `comfort_level` (1–10 from a wide points pool), the
  `comfort` command.
- **Residence + comfort→AP-regen (done):** primary residence reuses Evennia `home` (`home/set`,
  auto-default on first rent/acquire); `world.locations.comfort_effect` materializes
  `comfort_level − 5` as a flat `CharacterModifier` on the ap-regen targets, recomputed only on
  comfort-change events (home / style / decoration) and read for free by the regen cron.
  Widened #2036 to also declare `CharacterSheet.current_residence` (the resonance-trickle
  gate) and accept org-derived standing — see "Built (2026-07-10, #2036 — residence
  declaration + room aura tagging)" above.
- **Climate baseline (#1522, done):** `world.weather.Climate` — a per-region signed
  `temperature`/`moisture` baseline, designated via `Area.climate` and resolved
  most-specific-wins (`get_effective_climate`, mirrors realm). It decomposes onto the
  COLD/HEAT/WET/DRY exposure axes and folds into `felt_exposure` *before* the 0-floor (so a
  cooling fixture fights a desert's heat). A global per-month temperature curve
  (`MONTH_TEMPERATURE_SHIFT`, read off the IC `game_clock`) rides on top — a temperate region
  crosses into real winter cold while a tropical region's high baseline keeps "no real winter."
  Added the `DRY` exposure axis. `WIND` is deliberately *not* climate-driven (transient
  weather/magic only).
- **Transient weather (#1522, done — the dynamic driver):** `WeatherType` (climate-temp-band
  gated, `is_automated`, weighted) + `WeatherTypeExposure` + `WeatherEmit` (season/phase-gated) +
  `RegionWeatherState` (resolved most-specific-wins). `roll_region_weather` writes decaying
  source-tagged WET/WIND modifiers over the climate baseline; a `game_clock` cron rolls each
  climate region every 2 real hours (≈6 IC) and echoes one emit to online occupants as a
  `NarrativeCategory.WEATHER` message. A `time`/`weather` telnet command, a
  `GET /api/weather/conditions/` endpoint, and a React `WeatherWidget` in the top bar surface it;
  echoes are squelchable per-player (`narrative.UserCategoryMute`). The 7 types + 263 emits are
  seeded from the Arx-1 corpus. `FeastDay` forces special weather (Eclipse / Moon Madness)
  world-wide on recurring IC dates — the GM-lever automation.
- **Wind-as-mechanic combat consumer (#1555, ADR-0129, done):** `wind_penalty(felt)` banded
  SCENE check modifier (CALM/BREEZY/WINDY/GALE) on missile offense checks and the symmetric
  PC defense bonus vs. a MISSILE NPC attack — see `docs/systems/INDEX.md`'s "Combat" section.
- **Later slices:** comfort→**Conditions** ("Chilled/Soaked", Tehom-coordinated `comfort_penalty`),
  re-seed-as-upsert for edited emits, the web owner **build-HUD**, and inhabitant/owner surfacing.

## What's Needed for MVP

- **Stats substrate** — designed (see above); ready to implement
- **Ownership + tenancy model** — see "Ownership design notes" below; deferred
  to its own brainstorm
- **Room installations as system markers** — see below; each installation
  unlocks its own gameplay system and warrants its own design
- Decoration/furnishing system — items placed in rooms confer stats
- Estate-level aggregation — "ownership of all rooms in this area"
- **Servant entity** — NPC tied to an area + owner, capable of fetch
  errands. Generalizes to outfit retrieval, item fetch, scene preparation,
  message-carrying. Composes on top of existing reach checks: when an
  action raises `NotReachable` and the actor owns the area + has servants,
  intercept and queue a delayed servant action with room echoes.
- Property purchase / construction economy
- Per-room stat application during scenes (events use room stats for
  bonuses)
- Vault security rules — access lists, theft mechanics

## Ownership design notes (deferred — see 2026-05-09 brainstorm)

Captured during the location-stats design brainstorm; needs its own design pass.

- **Polymorphic owner-of-record:** rooms / buildings / higher-tier areas can
  be owned by either a **character** (Persona / RosterEntry) or an
  **organization** (noble house, adventuring party / covenant, crime family,
  guild). Likely uses `DiscriminatorMixin` on the ownership row.
- **Assigned-occupant separate from owner:** a noble house owns the manor
  (building); the head of house assigns a bedroom (room) to a noble. The
  noble has IC affordances over the bedroom but the building owner retains
  override authority and can revoke / reassign. Same model covers
  apartment rentals (landlord ↔ tenant) and inn rooms (innkeeper ↔ traveler).
  Tenancy is time-bound (lease term, indefinite-with-revocation).
- **IC affordances unlocked by ownership/assignment:** decoration
  permissions, vault access, servant assignment, defense installation
  rights — downstream consumers that read ownership state when checking
  permissions.
- **Org-side spans apps that don't all exist yet:** covenants are partially
  shipped; noble-house and crime-family entities don't yet have models.
  The ownership model should accept any qualifying organization type via
  the discriminator pattern, even before all org systems land.

## Room installations — each is its own gameplay system

Captured during the location-stats design brainstorm. Originally listed as
"decorative / invested features" in a unified bucket, but each item below
unlocks a distinct gameplay loop and warrants its own design pass:

- **Defenses** → invasion / break-and-enter / home defense gameplay
- **Anti-spy installations** → espionage gameplay loop
- **Research stations** → codex entry research & lore discovery
- **Combat arenas** → sparring-tier combat
- **Forges / alchemy benches / libraries** → crafting bonuses
- **Lairs / hideouts** → criminal organization gameplay
- **Vaults** → secured-storage rules

The shared abstraction these need — beyond the ambient stats substrate —
is a way to mark a room as "system-bearing" (this room has installation X)
and expose that to the consuming system. The marker pattern should land
when the first installation system materializes; it shouldn't be designed
in advance of any concrete system.

## Notes

- The servant/retrieval pattern was scoped out of the Outfit Phase A PR and
  parked here. When this domain gets active, the outfit-retrieval case is
  the easiest wedge to demo the system, since the Outfit model + apply
  service already raise `NotReachable` cleanly when the wardrobe is in
  another room.
- The 2026-05-06 player-and-GM brainstorm called out the need for a new
  `docs/roadmap/rooms.md` to absorb the rooms-as-system layer (state +
  installations + ownership). Until that consolidation happens, this file
  hosts the rooms-related backlog.

# Rooms, Buildings & Estates

**Status:** skeleton
**Depends on:** Areas (data layer), Items (containers, ownership), Roster (character ownership)

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
  hold events with reduced cost, etc.
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
- **Climate baseline (#1522, slice 1 done):** `world.weather.Climate` — a per-region signed
  `temperature`/`moisture` baseline, designated via `Area.climate` and resolved
  most-specific-wins (`get_effective_climate`, mirrors realm). It decomposes onto the
  COLD/HEAT/WET/DRY exposure axes and folds into `felt_exposure` *before* the 0-floor (so a
  cooling fixture fights a desert's heat). A global per-month temperature curve
  (`MONTH_TEMPERATURE_SHIFT`, read off the IC `game_clock`) rides on top — a temperate region
  crosses into real winter cold while a tropical region's high baseline keeps "no real winter."
  Added the `DRY` exposure axis. `WIND` is deliberately *not* climate-driven (transient
  weather/magic only).
- **Transient weather (#1522, slices 2a–2b done):** `WeatherType` (climate-temp-band gated,
  `is_automated`, weighted) + `WeatherTypeExposure` + `WeatherEmit` (season/phase-gated) +
  `RegionWeatherState` (resolved most-specific-wins). `roll_region_weather` writes decaying
  source-tagged WET/WIND modifiers over the climate baseline; a `game_clock` cron rolls each
  climate region every 2 real hours (≈6 IC) and echoes one emit to online occupants as an
  ATMOSPHERE narrative (frontend-routable). A `time`/`weather` telnet command, a `GET /api/weather/conditions/` endpoint, and a React
  `WeatherWidget` in the top bar surface it; echoes are squelchable per-player
  (`narrative.UserCategoryMute` on the `WEATHER` category). The 7 types + 263 emits are seeded
  from the Arx-1 corpus. `FeastDay` forces special weather (Eclipse / Moon Madness) world-wide on
  recurring IC dates — the GM-lever automation. **Remaining:** wind-as-mechanic combat consumer
  (**#1555**, Tehom's domain — the WIND provider side is done); re-seed-as-upsert for edited emits.
- **Later slices:** stackable comfort **decorations** (not `RoomFeatureInstance` — that's OneToOne),
  the comfort-level/effect engine (comfort→AP-regen, comfort→Conditions [Tehom-coordinated]), and
  the inhabitant/owner surfacing.

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

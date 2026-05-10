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
- Two models — `LocationStatOverride` (rare absolute claims that cut the
  cascade) and `LocationStatModifier` (common additive contributions that
  stack and decay)
- Most-specific Override wins; absent any Override, all Modifiers in the
  chain sum + per-stat default, clamped to bounds
- `RoomProfile.is_outdoor` controls whether weather-system writes apply
- One read service: `effective_stat(room, stat_key) -> int`
- Many other consumer systems (encounter generator, DC modifier, weather,
  magic, events bonuses) plug in over time

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

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

## What's Needed for MVP

- Room/area ownership model — character or organization claims an area
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

## Notes

- The servant/retrieval pattern was scoped out of the Outfit Phase A PR and
  parked here. When this domain gets active, the outfit-retrieval case is
  the easiest wedge to demo the system, since the Outfit model + apply
  service already raise `NotReachable` cleanly when the wardrobe is in
  another room.

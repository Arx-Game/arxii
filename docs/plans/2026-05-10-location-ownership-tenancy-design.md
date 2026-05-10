# Location Ownership and Tenancy — Design

**Status:** validated brainstorm; ready to implement
**Date:** 2026-05-10
**App home:** `world.locations` (alongside the LocationStat substrate)
**Depends on:** `world.areas` (Area, AreaClosure), `evennia_extensions` (RoomProfile),
`world.scenes` (Persona), `world.societies` (Organization),
`core.mixins.DiscriminatorMixin`

## Why this exists

The 2026-05-09 location-stats brainstorm captured ownership as a deferred
sibling concern. The roadmap in `docs/roadmap/rooms-and-estates.md` documents
the nuance: rooms / buildings / higher-tier areas can be owned by characters
or organizations, but assigned-occupant relationships (a noble's bedroom, an
apartment rental, an inn room) are a separate, time-bound relationship that
the building owner can revoke. This design provides the substrate for both
relationships so downstream systems (decoration, locks, vaults, eviction
flows, inheritance) can plug in over time.

It is **not** a design for: lock state, decoration permissions, vault rules,
inheritance on character death, rent / lease economics, or any specific
gameplay loop. Each of those is a follow-up.

## Bedrock decisions

### Two-layer model: Ownership and Tenancy

These are orthogonal relationships with different lifecycles and access
surfaces.

- **Ownership** — "this party holds the deed/title/claim of right." Cascades
  through the area hierarchy: owning a Building implies owning every Room
  within unless a more-specific level overrides. Liege/vassal relationships
  are just nested ownership at sub-areas, naturally captured by the cascade
  resolver.
- **Tenancy** — "this party has been granted use of a specific space by the
  owner, can be revoked." Per-target grant. Time-bound or
  indefinite-with-revocation. Multiple concurrent tenancies allowed (married
  couple jointly, lease holder + roommate, communal bunkroom).

The two are explicitly distinct from "who is in this room right now" — that's
physical presence handled by Evennia's location pointer and the scene system.

### Holder polymorphism: Persona OR Organization

Owners and tenants can be either:

- A **Persona** (`world.scenes.Persona`) — IC identity. Per the no-alt-outing
  hard rule, all owner/tenant displays use persona, never account.
- An **Organization** (`world.societies.Organization`) — already covers noble
  houses, guilds, gangs, businesses, secret societies, commoner families,
  differentiated via `OrganizationType`. Future covenants that need to own
  bases can either become a new OrganizationType or get a third FK slot —
  out of scope for v1.

Implementation note: `world.covenants.Covenant` exists as its own concrete
model after Slice A (PR #432-adjacent). For v1 ownership, covenants are NOT
direct holders — adventuring parties owning bases as a gameplay loop is not
yet specced. If needed, the cleanest future path is folding covenants under
Organization with a `covenant` type.

### Cascade rule for Ownership

Same most-specific-wins rule as `LocationStatOverride`:

1. Walk closure from the room outward (Room → Building → Neighborhood → Ward
   → City → Region → Kingdom → ...).
2. Most-specific level with an active Ownership row (`ended_at IS NULL`) is
   the effective owner.
3. If no level in the chain has an active Ownership row → unowned (wilderness,
   abandoned ruin, public street where the Crown's row was never authored).

Multiple historical (`ended_at IS NOT NULL`) rows per location are fine —
they form the audit trail.

### Tenancy semantics: collected, not most-specific-wins

Tenancy does NOT follow the cascade-pick-one rule. Tenancy is a grant of a
specific space; multiple grants at multiple levels can all apply.

For a query "who are the current tenants of this room?", collect:
- Active room-level tenancies where `room_profile = this`
- Active area-level tenancies where `area_id` is in this room's ancestor
  closure

All applicable rows return. A noble who has tenancy of the entire west wing
(an Area) AND a maid who has tenancy of the laundry room within that wing
(a Room) are both valid concurrent tenants of the laundry room.

Tenancies in v1 typically target Rooms (apartment unit, inn room, noble's
bedroom). Building-level tenancy is supported (single-family rental, guild
renting an entire building). Higher-level tenancy is allowed by the schema
but unusual and not enforced.

## Schema

```python
# world/locations/constants.py — add to existing file

class HolderType(models.TextChoices):
    """Discriminator for owner/tenant rows: which holder FK is active."""

    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
```

```python
# world/locations/models.py — append to existing models

class LocationOwnership(DiscriminatorMixin, SharedMemoryModel):
    """Who holds the deed/title/claim to a location.

    Cascades via AreaClosure — most-specific row wins. Liege/vassal nesting
    is just multiple rows at different tiers; the cascade resolver picks
    the most-specific automatically.

    Historical rows are kept (ended_at != NULL); the partial-unique
    constraint enforces at most one active owner per location.
    """

    DISCRIMINATOR_FIELD = "parent_type"   # AREA / ROOM
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    # Inherits from DiscriminatorMixin, but the holder also needs validation.
    # We use a second clean() block to enforce holder discriminator.

    parent_type     = CharField(choices=LocationParentType.choices, max_length=10)
    area            = FK("areas.Area", null=True, related_name="ownership_records")
    room_profile    = FK("evennia_extensions.RoomProfile", null=True,
                         related_name="ownership_records")

    holder_type     = CharField(choices=HolderType.choices, max_length=20)
    holder_persona      = FK("scenes.Persona", null=True, related_name="ownership_records")
    holder_organization = FK("societies.Organization", null=True,
                             related_name="ownership_records")

    acquired_at     = DateTimeField(default=timezone.now)
    ended_at        = DateTimeField(null=True, blank=True)
    notes           = CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["area"],
                condition=Q(area__isnull=False) & Q(ended_at__isnull=True),
                name="unique_active_ownership_per_area",
            ),
            UniqueConstraint(
                fields=["room_profile"],
                condition=Q(room_profile__isnull=False) & Q(ended_at__isnull=True),
                name="unique_active_ownership_per_room",
            ),
        ]
```

```python
class LocationTenancy(DiscriminatorMixin, SharedMemoryModel):
    """A granted, time-bound right to use a specific location.

    Does NOT follow most-specific-wins cascade. Multiple concurrent
    tenancies are valid. The ``current_tenants`` read collects all
    applicable rows (room-level + ancestor-area-level).

    Historical rows are kept (ends_at != NULL). The "current" filter is
    ``ends_at IS NULL OR ends_at > now()``.
    """

    DISCRIMINATOR_FIELD = "parent_type"
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    parent_type     = CharField(choices=LocationParentType.choices, max_length=10)
    area            = FK("areas.Area", null=True, related_name="tenancy_records")
    room_profile    = FK("evennia_extensions.RoomProfile", null=True,
                         related_name="tenancy_records")

    tenant_type     = CharField(choices=HolderType.choices, max_length=20)
    tenant_persona      = FK("scenes.Persona", null=True, related_name="tenancies")
    tenant_organization = FK("societies.Organization", null=True,
                             related_name="tenancies")

    started_at      = DateTimeField(default=timezone.now)
    ends_at         = DateTimeField(null=True, blank=True,
                                     help_text="NULL = indefinite, revocable.")
    notes           = CharField(max_length=200, blank=True)

    # No uniqueness — multiple concurrent tenants OK
    # Indexes for current-tenant queries
    class Meta:
        indexes = [
            Index(fields=["area", "ends_at"]),
            Index(fields=["room_profile", "ends_at"]),
        ]
```

### A note on the second discriminator (holder_type)

The existing `DiscriminatorMixin` validates exactly-one-FK-set against a
single discriminator field. Both Ownership and Tenancy have *two*
discriminators: parent (Area XOR Room) and holder (Persona XOR Organization).

Two options:
1. Use the mixin's `parent_type` discriminator and add a second `clean()`
   override on each model that validates the holder pair.
2. Generalize the mixin to support multiple discriminator fields.

For v1, **option 1** — keep the mixin simple, add per-model `clean()` for
the holder check. Generalizing the mixin can come later if a third
multi-discriminator model materializes.

## Read services

```python
# world/locations/services.py — append

def effective_owner(room: ObjectDB) -> LocationOwnership | None:
    """Cascade-resolve the owner of a room, walking closure outward.

    Returns the most-specific active LocationOwnership row, or None
    if the chain has no active ownership at any level.

    Algorithm:
      1. Resolve room.room_profile and its area. If profile missing,
         return None (cannot cascade).
      2. Look up the area's ancestors via AreaClosure.
      3. Filter LocationOwnership for `room_profile=profile OR area_id IN
         ancestor_ids`, plus `ended_at IS NULL`.
      4. Most-specific wins: room-level beats area-level; among areas,
         smallest level (most specific) beats larger.
    """


def current_tenants(room: ObjectDB) -> QuerySet[LocationTenancy]:
    """Return all currently-active tenancies that apply to this room.

    Includes room-level tenancies where `room_profile = this`, plus
    area-level tenancies where `area_id` is in this room's ancestor
    closure. Filters out tenancies past their `ends_at`.
    """
```

These mirror the LocationStat read pattern. 2 queries each (closure
ancestors + ownership/tenancy fetch). Use `select_related` on
`area`, `holder_persona`, `holder_organization` (and tenant equivalents)
so consumers walking `.holder_persona.name` don't pay an N+1.

## What v1 ships

- New `HolderType` TextChoices in `world/locations/constants.py`
- `LocationOwnership` and `LocationTenancy` models with constraints, indexes,
  and second-discriminator `clean()` overrides
- One auto-generated migration (`0002_*` since the wedge already shipped
  `0001_initial`)
- `effective_owner(room)` and `current_tenants(room)` services in
  `world/locations/services.py`
- Auto-generated Django admin with help text on the Ownership-vs-Tenancy
  distinction
- Factories with `on_org` / `on_room` / `with_lease` traits
- App `CLAUDE.md` updated with the new layer
- Tests covering: discriminator validation (parent + holder for both
  models), partial-unique on active ownership, cascade resolution
  (room-level beats area-level, deeper area beats shallower, no row →
  None), tenancy collection from ancestor areas, ends_at filtering for
  current vs expired

## What v1 explicitly defers

| Item | When to add |
|---|---|
| Convenience write helpers (`transfer_ownership`, `grant_tenancy`, `evict`) | When repeated patterns emerge in consumers |
| Bulk read variants (`effective_owners_for_rooms`) | When a bulk consumer (where-command coloring, dashboards) materializes |
| Permissions checks (`can_decorate(persona, room)`, `can_lock(persona, room)`) | When decoration / lock systems land |
| Rent amount / lease term structured fields | With the economy system |
| Inheritance on character death | Separate progression / story system |
| Eviction-flow service (notification, grace period, cleanup) | When the eviction UX is specced |
| API exposure (REST endpoints, frontend) | When a frontend consumer materializes |
| Covenant as a third holder type | When adventuring parties own bases — until then, it's a deferred call between "add covenant FK" or "fold covenants under Organization" |
| Ownership transfer audit ledger (separate `LocationOwnershipTransfer` table) | When investigation / forensics tooling lands |

## Out of scope — separate brainstorms

- **Liege/vassal authority** — the schema captures nested ownership, but the
  *authority lifecycle* (when can a liege revoke a vassal's holding? what
  triggers escheat? how does inheritance work?) is a political-feudal
  system that needs its own design.
- **Eviction notification UX** — telling tenants their lease is up, grace
  periods, dispute flows.
- **Decoration / installation permission gating** — the rooms-and-estates
  roadmap captures this as a downstream "what does ownership unlock?"
  domain. Each installation system will plug in here.
- **Vault security** — owner-controlled access lists with exception cases.
  Builds on Ownership but is its own design.
- **Rent / income economy** — what does ownership generate? what do tenants
  pay? Lives in the broader economy system.

## Test plan

- **Discriminator validation:**
  - Cannot create Ownership with both `area` and `room_profile` set
  - Cannot create Ownership with neither
  - Cannot create Ownership with both `holder_persona` and `holder_organization` set
  - Cannot create Ownership with neither holder
  - Same four cases for Tenancy
- **Partial uniqueness:**
  - Cannot have two active Ownership rows for the same `area`
  - Cannot have two active Ownership rows for the same `room_profile`
  - Active + historical rows for the same target are fine
  - Multiple active Tenancies for the same target are fine
- **Cascade for Ownership:**
  - Room with own ownership beats Building-level ownership
  - Building beats Neighborhood beats Ward (most-specific area wins)
  - No ownership in chain → returns None
  - Historical (ended) rows are not considered
- **Tenancy collection:**
  - Room-level tenancy returned for that room
  - Area-level tenancy returned for any room within
  - Multiple concurrent room-level tenancies all returned
  - Expired tenancies (`ends_at < now`) excluded
  - Active + indefinite (`ends_at IS NULL`) included
  - Tenancy on an unrelated area not returned
- **Holder access:**
  - `LocationOwnership.get_active_target()` returns Persona or Organization
    correctly via the existing DiscriminatorMixin method (extended for the
    holder discriminator)

## Cross-cutting notes

- All concrete models inherit `SharedMemoryModel`. Trust the identity map.
- Service uses absolute imports; type annotations on all functions.
- TextChoices in `constants.py`.
- Migration named for the `locations` app label (NOT `world.locations`).
- Help text on every key field surfaces the Ownership-vs-Tenancy distinction
  for staff using the admin.
- `world/locations/CLAUDE.md` updated to document the new layer.

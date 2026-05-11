# Location Permissions Helpers — Design

**Status:** validated brainstorm; ready to implement
**Date:** 2026-05-11
**App home:** `world.locations` (extends existing services)
**Depends on:** `world.locations` (LocationOwnership, LocationTenancy,
`effective_owner`, `current_tenants`), `world.scenes` (Persona),
`world.societies` (Organization, OrganizationMembership)

## Why this exists

The ambient-stats and ownership-tenancy substrates shipped in PRs #432
and #434 are ready but have no consumers. Every downstream system that
needs to gate behavior on "who has standing at this location" — decoration,
locks, vaults, eviction, installation permissions — would otherwise have
to reimplement the same persona-or-org-membership walk.

This wedge provides the canonical first consumer of the ownership and
tenancy substrate: a small set of relationship-lookup helpers that answer
"does this persona have owner / tenant standing at this room?" Specific
permission checks (`can_decorate`, `can_evict`, `can_install`, etc.) live
in their consuming systems where the rules naturally belong.

It is **not** a design for:
- Specific gameplay permissions (decoration, locks, vault access, etc.)
- Rank-aware filtering ("rank 1-2 only can evict")
- DRF permission classes
- API endpoints
- Bulk variants

Each is a downstream concern.

## Bedrock decisions

### Relationship lookups, not action checks

The substrate exposes "who has standing here," not "who can perform action
X here." Each downstream system has different rules:

- **Decoration**: owner or tenant
- **Eviction**: owner only, and rank-gated within owning org
- **Lock from non-occupants**: owner OR tenant of this specific room
- **Install a vault**: owner only, rank 1-2 in owning org
- **View audit history**: owner only, plus staff

Encoding these rules in the substrate would put the wrong layer in charge.
Decoration rules live in the decoration system; eviction rules live in the
eviction system. The substrate just answers the relationship lookup, and
each system composes specific checks on top.

### Org membership counts as standing

Most real ownership in the game is via Organizations (noble houses, guilds,
gangs, businesses, secret societies, commoner families — see
`OrganizationType` in `world.societies`). If `is_owner` only matched direct
persona-to-persona FKs, every downstream system would reimplement the
membership walk.

`OrganizationMembership` (in `world.societies.models`) has no lifecycle
fields (no `left_at`, no `is_active`). Departures are model deletes via
CASCADE. So "current member" = "exists in the table." No soft-leave filter
needed.

### Rank filtering is downstream's concern

The substrate does NOT gate on `OrganizationMembership.rank`. A rank-5
member of a noble house counts as having owner standing per the substrate
— but eviction or vault-installation rules in their consuming systems
will filter further on rank. Downstream systems already have to read
membership for rank; pushing rank logic into the substrate would duplicate
that read pointlessly.

### Strict persona scoping — no alt-piercing

Per the no-alt-outing hard rule, all helpers are strictly persona-scoped.
If LordAiden's primary persona owns the manor, his alt persona (e.g.,
"Captain Storm") is NOT recognized as an owner — even though they share
a CharacterSheet. This falls out naturally from FK filtering on persona
exactly. Tests explicitly verify the no-alt-piercing case.

## Service surface

```python
# world/locations/services.py — append

def _persona_organization_ids(persona: "Persona") -> set[int]:
    """Return the set of organization IDs this persona is a current member of.

    Membership is presence in OrganizationMembership — there are no
    soft-leave fields on that model, so a row in the table is a current
    membership. Departures are model deletes.
    """


def ownership_for(
    persona: "Persona", room: "DefaultObject"
) -> LocationOwnership | None:
    """Return the cascade-resolved LocationOwnership row that gives this
    persona standing at this room, or None.

    Standing exists when:
      - The cascade-resolved owner is this persona directly (holder_type
        is PERSONA and holder_persona_id == persona.pk), OR
      - The cascade-resolved owner is an Organization this persona is a
        current member of.

    Does NOT consider OrganizationMembership.rank — downstream consumers
    that need rank filtering (eviction, installation permissions, etc.)
    read it themselves.

    Query budget: 3 (2 for effective_owner + 1 for org_ids; the org_ids
    fetch is skipped on PERSONA-holder matches via short-circuit).
    """


def is_owner(persona: "Persona", room: "DefaultObject") -> bool:
    """True when ``ownership_for(persona, room)`` returns a row."""


def tenancies_for(
    persona: "Persona", room: "DefaultObject"
) -> "QuerySet[LocationTenancy]":
    """Return the QuerySet of currently-active tenancies that give this
    persona standing at this room.

    Includes:
      - Direct persona tenancies (tenant_type=PERSONA,
        tenant_persona=persona), AND
      - Organization tenancies where this persona is a current member of
        the tenant_organization.

    Builds on ``current_tenants(room)`` which already filters for active
    tenancies and collects across the room + ancestor-area chain.

    Query budget: 3 (2 for current_tenants closure walk + tenancy fetch,
    1 for org_ids).
    """


def is_tenant(persona: "Persona", room: "DefaultObject") -> bool:
    """True when ``tenancies_for(persona, room).exists()``."""
```

## Implementation sketch

```python
def _persona_organization_ids(persona):
    return set(
        OrganizationMembership.objects.filter(persona=persona)
        .values_list("organization_id", flat=True)
    )


def ownership_for(persona, room):
    row = effective_owner(room)
    if row is None:
        return None
    if row.holder_type == HolderType.PERSONA:
        return row if row.holder_persona_id == persona.pk else None
    # HolderType.ORGANIZATION
    if row.holder_organization_id in _persona_organization_ids(persona):
        return row
    return None


def is_owner(persona, room):
    return ownership_for(persona, room) is not None


def tenancies_for(persona, room):
    org_ids = _persona_organization_ids(persona)
    return current_tenants(room).filter(
        models.Q(tenant_persona=persona)
        | models.Q(tenant_organization_id__in=org_ids)
    )


def is_tenant(persona, room):
    return tenancies_for(persona, room).exists()
```

## What v1 ships

- 5 functions in `src/world/locations/services.py` (1 private helper + 4 public)
- `OrganizationMembership` imported from `world.societies.models`
- Tests covering the relationship matrix and the query budget
- `world/locations/CLAUDE.md` updated with the new layer

## What v1 explicitly defers

| Item | When to add |
|---|---|
| Specific permission checks (`can_decorate`, `can_evict`, `can_install`, etc.) | When their consuming systems land |
| Rank-aware filtering | Downstream — each consumer reads rank from `OrganizationMembership` directly |
| DRF permission classes | When API consumers materialize |
| Bulk variants (`is_owner_of_any`, etc.) | When a bulk consumer appears |
| Convenience write helpers (transfer_ownership, evict, etc.) | Separate brainstorm — design doc for ownership/tenancy flagged this |
| Multi-persona bridging ("this character's other personas") | Explicitly forbidden by no-alt-outing hard rule |
| Audit-history visibility checks | Out of scope; downstream |
| Recursive org structure (sub-orgs of orgs) | Out of scope; `world.societies` doesn't model this today |

## Test plan

- **Direct persona ownership:**
  - `ownership_for(owner_persona, room)` returns the row; `is_owner` True
  - `ownership_for(stranger_persona, room)` returns None; `is_owner` False
- **Organization ownership + persona membership:**
  - `ownership_for(member_persona, room)` returns the row; `is_owner` True
  - `ownership_for(non_member_persona, room)` returns None; `is_owner` False
- **No ownership in the chain:**
  - `ownership_for(any_persona, room)` returns None
- **Cascade interaction:** Building owned by org, room cascades to building.
  - `ownership_for(org_member, room)` returns the building-level row
- **No-alt-piercing:** Primary persona owns the manor; alt persona of the
  same character returns None.
- **Direct persona tenancy:**
  - `tenancies_for(tenant_persona, room)` returns the row
  - `is_tenant` True
- **Organization tenancy + persona membership:**
  - `tenancies_for(org_member_persona, room)` returns the row
  - Non-member returns empty
- **Multiple tenancies, partial match:**
  - Room has 1 building-level org tenancy + 2 room-level persona tenancies
  - `tenancies_for(building_org_member, room)` returns only the org tenancy
  - `tenancies_for(room_tenant_persona, room)` returns only their direct tenancy
- **Expired tenancy excluded** — implicit via `current_tenants` already filtering
- **Query budget:**
  - `is_owner(persona_owner, room)` with PERSONA-holder match: assertNumQueries(2)
    (effective_owner runs 2; the org_ids fetch is skipped via short-circuit)
  - `is_owner(persona_member, room)` with ORGANIZATION-holder match: assertNumQueries(3)
  - `tenancies_for(persona, room)` consumed: assertNumQueries(3)

## Cross-cutting notes

- The `ownership_for` short-circuit when the holder is a Persona avoids
  the org_ids fetch — a free optimization that takes the common case
  ("did this individual persona buy the inn room") down to 2 queries.
- The substrate is strictly read-side. Writes still go through `objects.create()`
  on the underlying models per the existing CLAUDE.md guidance, until the
  deferred transfer/evict helpers land.
- Per project memory: tests must enforce the documented query budget via
  `assertNumQueries`. The previous adversarial review caught this category
  as one we keep missing.

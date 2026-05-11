# Location Lifecycle Write Helpers — Design

**Status:** validated brainstorm; ready to implement
**Date:** 2026-05-11
**App home:** `world.locations` (extends existing services)
**Depends on:** `world.locations` (LocationOwnership, LocationTenancy)

## Why this exists

Both the location-ambient-stats and location-ownership-tenancy design
docs explicitly deferred convenience write helpers, flagging the
deferral as a known footgun. The current pattern for transferring
ownership is:

1. Find the existing active row for the target location
2. Set `ended_at = now()` on it and save
3. Create a new row with the new holder
4. Wrap (1)-(3) in `transaction.atomic` so concurrent readers don't see
   "no active owner" between steps

Every caller has to remember this protocol exactly. Get the order wrong
and the partial-unique constraint fires. Skip the atomic and a reader
mid-transfer sees a momentary unowned state. The CLAUDE.md note about
this is real but easy to miss.

This wedge closes the gap with three small helpers in
`world.locations.services` so the protocol lives in one place and
downstream callers (decoration, eviction UX, inheritance, transfer
tooling, GM admin commands) consume a stable API instead of
reimplementing the dance.

It is **not** a design for:
- Permission checks (who can transfer / evict) — caller's concern
- Eviction notification / grace periods — separate UX system
- Inheritance on character death — separate progression hook
- DRF endpoints / API exposure — when consumers materialize
- Audit trail with structured `transferred_by_persona` — `notes` text
  field covers v1; add structured audit later if forensics tooling
  needs it
- Bulk variants

## Bedrock decisions

### Three helpers, explicit kwargs

```python
def transfer_ownership(
    *,
    area: Area | None = None,
    room_profile: RoomProfile | None = None,
    to_persona: Persona | None = None,
    to_organization: Organization | None = None,
    notes: str = "",
    transferred_at: datetime | None = None,
) -> LocationOwnership

def grant_tenancy(
    *,
    area: Area | None = None,
    room_profile: RoomProfile | None = None,
    tenant_persona: Persona | None = None,
    tenant_organization: Organization | None = None,
    ends_at: datetime | None = None,
    notes: str = "",
) -> LocationTenancy

def end_tenancy(
    tenancy: LocationTenancy,
    *,
    ended_at: datetime | None = None,
) -> LocationTenancy
```

Explicit kwargs (not auto-detection from types) make call sites readable
and validation localized:

```python
transfer_ownership(area=ward, to_organization=house_stark, notes="conquest of 1234")
grant_tenancy(room_profile=apartment, tenant_persona=traveler, ends_at=next_week)
end_tenancy(tenancy)
```

### `transfer_ownership` handles both claim and transfer

The protocol is identical whether the location currently has an active
owner or not — end whatever exists (if any), create the new row, wrap
atomically. Conflating "claim" and "transfer" into one operation
reduces API surface and matches the substrate semantics (the
partial-unique constraint is on active ownership, not on transfer
history).

If a caller has a permission rule like "only the current owner can
authorize a transfer," that's their gate to install before calling
`transfer_ownership`. The substrate doesn't enforce it.

### `end_tenancy` is one operation, not two

Eviction (owner kicks tenant out) and voluntary departure (tenant
leaves) use the same code path: set `ends_at`. The semantic distinction
is purely the caller's UX concern — substrate doesn't model "kicked
out" vs "moved out."

Future systems may want to record the reason / actor on tenancy
closure. For v1 the `notes` field on the row covers it; structured
fields are a follow-up.

### No permission checks in substrate

These helpers don't call `is_owner` or anything else. They just perform
the write. Callers MUST gate access first (via `is_owner`,
`OrganizationMembership.rank`, or whatever the consuming system
requires). Mixing permission gating into the substrate would force
downstream systems to either bypass it (defeating the point) or live
with the substrate's rules (forcing one access policy on every system).

### No actor parameter in v1

The plan considered adding `actor_persona` as a structured field on
each lifecycle operation. v1 defers this — the existing `notes` text
field can carry actor info ("transferred by Lord Aiden") for now. When
forensics tooling materializes and the audit trail needs to be
structured, we add a real FK column on both models with a migration.

## Implementation sketch

```python
# world/locations/services.py — append

def transfer_ownership(
    *,
    area: "Area | None" = None,
    room_profile: "RoomProfile | None" = None,
    to_persona: "Persona | None" = None,
    to_organization: "Organization | None" = None,
    notes: str = "",
    transferred_at: "datetime | None" = None,
) -> LocationOwnership:
    """Atomically transfer (or claim) ownership of a location.

    Ends the current active LocationOwnership row (if any) and creates
    a new row with the new holder. Wrapped in transaction.atomic so the
    "no active owner" window never appears to concurrent readers.

    Handles both first-time claims (no current owner) and transfers
    (current owner ended, new owner created).

    Caller is responsible for permission gating — substrate does not
    check authority to transfer.
    """
    _validate_location_kwargs(area, room_profile)
    _validate_holder_kwargs(to_persona, to_organization)

    parent_type = (
        LocationParentType.AREA if area is not None else LocationParentType.ROOM
    )
    holder_type = (
        HolderType.PERSONA if to_persona is not None else HolderType.ORGANIZATION
    )
    when = transferred_at if transferred_at is not None else timezone.now()

    with transaction.atomic():
        existing_qs = LocationOwnership.objects.filter(ended_at__isnull=True)
        if area is not None:
            existing_qs = existing_qs.filter(area=area)
        else:
            existing_qs = existing_qs.filter(room_profile=room_profile)
        existing = existing_qs.first()
        if existing is not None:
            existing.ended_at = when
            existing.save()

        return LocationOwnership.objects.create(
            parent_type=parent_type,
            area=area,
            room_profile=room_profile,
            holder_type=holder_type,
            holder_persona=to_persona,
            holder_organization=to_organization,
            acquired_at=when,
            notes=notes,
        )


def grant_tenancy(
    *,
    area: "Area | None" = None,
    room_profile: "RoomProfile | None" = None,
    tenant_persona: "Persona | None" = None,
    tenant_organization: "Organization | None" = None,
    ends_at: "datetime | None" = None,
    notes: str = "",
) -> LocationTenancy:
    """Create a new LocationTenancy row.

    Multiple concurrent tenancies on the same location are valid by
    design — no conflict check. Caller is responsible for permission
    gating (only owners should grant tenancy).
    """
    _validate_location_kwargs(area, room_profile)
    _validate_tenant_kwargs(tenant_persona, tenant_organization)

    parent_type = (
        LocationParentType.AREA if area is not None else LocationParentType.ROOM
    )
    tenant_type = (
        HolderType.PERSONA if tenant_persona is not None else HolderType.ORGANIZATION
    )
    return LocationTenancy.objects.create(
        parent_type=parent_type,
        area=area,
        room_profile=room_profile,
        tenant_type=tenant_type,
        tenant_persona=tenant_persona,
        tenant_organization=tenant_organization,
        ends_at=ends_at,
        notes=notes,
    )


def end_tenancy(
    tenancy: LocationTenancy,
    *,
    ended_at: "datetime | None" = None,
) -> LocationTenancy:
    """End a tenancy by setting ``ends_at``.

    Covers eviction and voluntary departure — the code path is
    identical and the semantic distinction is the caller's concern.
    Idempotent: re-calling on an already-ended tenancy overwrites
    ``ends_at`` to the new value. The new value can be in the past
    (eviction effective immediately) or in the future (planned end of
    lease).
    """
    tenancy.ends_at = ended_at if ended_at is not None else timezone.now()
    tenancy.save()
    return tenancy
```

Two private validators (one per discriminator pair) keep the bodies
clean.

## What v1 ships

- 3 public helpers + 2 private validators in
  `src/world/locations/services.py`
- Tests covering:
  - `transfer_ownership` as claim (no current owner) and as transfer
    (existing owner)
  - Old + new rows have matching timestamps when caller passes none
  - Caller-supplied `transferred_at` is honored
  - Validation: missing both / passing both for parent and holder
  - Atomicity: after successful transfer, exactly ONE active row exists
  - Partial-unique constraint not violated under transfer
  - `grant_tenancy` happy paths (persona + org, area + room)
  - `grant_tenancy` validation errors
  - Multiple concurrent tenancies after multiple grants
  - `end_tenancy` sets `ends_at` to now() by default and to supplied
    value when given
  - `end_tenancy` idempotency (callable twice with different times)
- `world/locations/CLAUDE.md` updated to point at these helpers as the
  canonical write API

## What v1 explicitly defers

| Item | When to add |
|---|---|
| Permission gating inside helpers | Never — caller's concern |
| Structured `actor_persona` field on operations | When forensics tooling lands |
| Eviction notification / grace period | With the eviction UX system |
| Inheritance on character death | Separate progression hook |
| Bulk variants (`transfer_multiple`, `end_all_tenancies_on`) | When a bulk consumer materializes |
| DRF actions / API endpoints | When frontend consumers exist |
| Tenancy "renew" helper | When a real renewal flow surfaces |
| Recording the **previous** holder explicitly on the new row | If the audit trail needs richer cross-row linking |

## Test plan

- **transfer_ownership: claim**
  - No existing owner → new row created; `ended_at IS NULL`
- **transfer_ownership: transfer**
  - Existing owner → existing row gets `ended_at = when`; new row created with `acquired_at = when`
  - The two timestamps are identical when caller doesn't pass `transferred_at`
  - When caller passes `transferred_at`, BOTH timestamps use that value
- **transfer_ownership: atomicity**
  - After successful transfer, `LocationOwnership.objects.filter(active...).count() == 1`
- **transfer_ownership: validation errors**
  - No parent / both parents → `ValueError`
  - No holder / both holders → `ValueError`
- **grant_tenancy: happy paths**
  - Persona tenant on room
  - Organization tenant on area
  - With `ends_at` set (planned lease)
  - Without `ends_at` (indefinite)
- **grant_tenancy: validation errors**
  - Same four cases
- **grant_tenancy: multiple concurrent**
  - Three grants on same room, all active, no conflict
- **end_tenancy: defaults to now**
- **end_tenancy: honors supplied timestamp**
- **end_tenancy: idempotent re-end overwrites**
- **end_tenancy: returns the same instance** (not a re-fetch)

## Cross-cutting notes

- All operations preserve the existing audit-history pattern: history
  rows are kept; the `ended_at` / `ends_at` filter is what defines
  "current."
- The validators raise `ValueError` (Python's standard, not
  `ValidationError`) — these are programmer-error conditions, not
  user-input validation. Caller code at API layers maps to appropriate
  HTTP responses.
- `transaction.atomic` only wraps `transfer_ownership` because it's the
  only multi-statement operation. `grant_tenancy` is a single INSERT;
  `end_tenancy` is a single UPDATE.
- Helpers are type-annotated (typed app). Imports for `Area`,
  `RoomProfile`, `Persona`, `Organization`, `datetime` live under
  `TYPE_CHECKING` to avoid runtime cost.

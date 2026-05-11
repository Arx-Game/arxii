"""Read services for the location ambient stats cascade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models, transaction
from django.utils import timezone

from evennia_extensions.models import RoomProfile
from world.areas.models import AreaClosure
from world.locations.constants import (
    STAT_CLAMPS,
    STAT_DEFAULTS,
    HolderType,
    LocationParentType,
    StatKey,
)
from world.locations.models import (
    LocationOwnership,
    LocationStatModifier,
    LocationStatOverride,
    LocationTenancy,
)
from world.societies.models import OrganizationMembership

if TYPE_CHECKING:
    from datetime import datetime

    from django.db.models import QuerySet
    from evennia.objects.objects import DefaultObject

    from world.areas.models import Area
    from world.scenes.models import Persona
    from world.societies.models import Organization


def _room_profile_and_ancestors(
    room: DefaultObject,
) -> tuple[RoomProfile | None, list[int]]:
    """Resolve a room's RoomProfile and ancestor area ids.

    Returns (profile, ancestor_ids) where profile is None if the room
    has no RoomProfile, and ancestor_ids is the list of area ids in
    this room's area's closure (including the room's own area at depth
    0). When the profile exists but area is None, ancestor_ids is [].

    Callers handle their own empty-result semantics (return default,
    None, or .objects.none()) based on the returned profile.
    """
    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist:
        return None, []

    area = profile.area
    ancestor_ids: list[int] = []
    if area is not None:
        ancestor_ids = list(
            AreaClosure.objects.filter(descendant_id=area.pk).values_list("ancestor_id", flat=True)
        )
    return profile, ancestor_ids


def _persona_organization_ids(persona: Persona) -> set[int]:
    """Return organization IDs this persona is a current member of.

    OrganizationMembership has no lifecycle fields (no left_at, no
    is_active) — departures are model deletes. So presence in the table
    is current membership.
    """
    return set(
        OrganizationMembership.objects.filter(persona=persona).values_list(
            "organization_id", flat=True
        )
    )


def _validate_location_kwargs(area: Area | None, room_profile: RoomProfile | None) -> None:
    """Raise ValueError unless exactly one of (area, room_profile) is set."""
    if (area is None) == (room_profile is None):
        msg = "Must pass exactly one of area or room_profile."
        raise ValueError(msg)


def _validate_holder_kwargs(persona: Persona | None, organization: Organization | None) -> None:
    """Raise ValueError unless exactly one of (persona, organization) is set.

    Used by both ownership (holder) and tenancy (tenant) helpers — both have
    the same Persona-XOR-Organization shape.
    """
    if (persona is None) == (organization is None):
        msg = "Must pass exactly one of the persona or organization holder."
        raise ValueError(msg)


def _clamp(value: int, stat_key: StatKey) -> int:
    bounds = STAT_CLAMPS.get(stat_key)
    if bounds is None:
        return value
    low, high = bounds
    return max(low, min(high, value))


def effective_stat(room: DefaultObject, stat_key: StatKey) -> int:
    """Cascade-resolve a single stat for a room, clamped to per-stat bounds.

    Algorithm (2 queries per call: closure walk + override or modifier
    fetch; modifier ``current_value()`` is in-memory math):
      1. Resolve ``room.room_profile`` and its area. If the profile is
         missing, return ``STAT_DEFAULTS[stat_key]`` clamped.
      2. Look up the area's ancestors (and itself) via ``AreaClosure``.
      3. If any ``LocationStatOverride`` exists for the ancestor set or
         the room_profile and matches ``stat_key``, pick the most-specific
         (room > deepest area) and return its value, clamped.
      4. Otherwise sum every ``LocationStatModifier.current_value`` for
         the same scope and ``stat_key``, add ``STAT_DEFAULTS[stat_key]``,
         clamp, return.
    """

    default = STAT_DEFAULTS.get(stat_key, 0)
    profile, ancestor_ids = _room_profile_and_ancestors(room)
    if profile is None:
        return _clamp(default, stat_key)

    # Step 3: most-specific override wins, modifiers ignored.
    overrides = list(
        LocationStatOverride.objects.filter(stat_key=stat_key)
        .select_related("area")
        .filter(models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids))
    )
    if overrides:
        # Specificity: room beats any area; among areas, smaller level wins.
        # AreaLevel uses smaller numbers for more specific tiers (Building=10
        # is most specific).
        room_overrides = [o for o in overrides if o.room_profile_id == profile.pk]
        if room_overrides:
            return _clamp(room_overrides[0].value, stat_key)
        chosen = min(overrides, key=lambda o: o.area.level)
        return _clamp(chosen.value, stat_key)

    # Step 4: sum modifier current_values.
    modifiers = LocationStatModifier.objects.filter(stat_key=stat_key).filter(
        models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids)
    )
    total = default + sum(mod.current_value() for mod in modifiers)
    return _clamp(total, stat_key)


def effective_owner(room: DefaultObject) -> LocationOwnership | None:
    """Cascade-resolve the most-specific active owner of a room.

    Algorithm:
      1. Resolve the room's RoomProfile and its area. If profile is
         missing (or area is None), return None.
      2. Look up area ancestors (and self at depth 0) via AreaClosure.
      3. Filter LocationOwnership for ``room_profile=profile OR
         area_id IN ancestor_ids`` AND ``ended_at IS NULL``.
      4. Most-specific wins: room-level beats area-level; among areas,
         smallest level wins (BUILDING=10 is most specific).

    Returns the LocationOwnership row (caller can call
    ``.get_active_target()`` for the Persona/Organization), or None
    if no active ownership exists in the chain.
    """

    profile, ancestor_ids = _room_profile_and_ancestors(room)
    if profile is None:
        return None

    rows = list(
        LocationOwnership.objects.filter(ended_at__isnull=True)
        .select_related("area", "holder_persona", "holder_organization")
        .filter(models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids))
    )
    if not rows:
        return None

    room_rows = [r for r in rows if r.room_profile_id == profile.pk]
    if room_rows:
        return room_rows[0]
    return min(rows, key=lambda r: r.area.level)


def current_tenants(room: DefaultObject) -> QuerySet[LocationTenancy]:
    """Return all currently-active tenancies that apply to a room.

    Includes:
      - Room-level tenancies where ``room_profile = this`` and active.
      - Area-level tenancies where ``area_id`` is in this room's
        ancestor closure and active.

    "Active" means ``ends_at IS NULL OR ends_at > now()``. Historical
    or expired tenancies are excluded. Multiple concurrent tenancies
    are valid (married couples, roommates, communal access).

    2 queries per call: closure walk + tenancy fetch with tenants
    joined via select_related.
    """

    profile, ancestor_ids = _room_profile_and_ancestors(room)
    if profile is None:
        return LocationTenancy.objects.none()

    now = timezone.now()
    return (
        LocationTenancy.objects.filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))
        .select_related("area", "tenant_persona", "tenant_organization")
        .filter(models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids))
    )


def ownership_for(persona: Persona, room: DefaultObject) -> LocationOwnership | None:
    """Return the LocationOwnership row that gives this persona standing
    at this room, or None.

    Standing exists when:
      - The cascade-resolved owner is this persona directly, OR
      - The cascade-resolved owner is an Organization this persona is a
        current member of.

    Does not consider OrganizationMembership.rank — downstream gating
    on rank is each consumer's responsibility.

    Query budget: 2 queries when the holder is a Persona (short-circuit
    skips the org_ids fetch); 3 when the holder is an Organization.
    """
    row = effective_owner(room)
    if row is None:
        return None
    if row.holder_type == HolderType.PERSONA:
        if row.holder_persona_id == persona.pk:
            return row
        return None
    # HolderType.ORGANIZATION
    if row.holder_organization_id in _persona_organization_ids(persona):
        return row
    return None


def is_owner(persona: Persona, room: DefaultObject) -> bool:
    """True when ``ownership_for(persona, room)`` returns a row."""
    return ownership_for(persona, room) is not None


def tenancies_for(persona: Persona, room: DefaultObject) -> QuerySet[LocationTenancy]:
    """Return the QuerySet of currently-active tenancies that give this
    persona standing at this room.

    Includes:
      - Direct persona tenancies (tenant_persona = this persona)
      - Organization tenancies where this persona is a current member
        of the tenant_organization

    Builds on ``current_tenants(room)`` (which already filters for
    active rows and collects across the room + ancestor-area chain),
    then narrows to rows relevant to this persona.

    Query budget: 3 queries (org_ids + closure walk + tenancy fetch).
    """
    org_ids = _persona_organization_ids(persona)
    return current_tenants(room).filter(
        models.Q(tenant_persona=persona) | models.Q(tenant_organization_id__in=org_ids)
    )


def is_tenant(persona: Persona, room: DefaultObject) -> bool:
    """True when ``tenancies_for(persona, room)`` has any rows."""
    return tenancies_for(persona, room).exists()


def transfer_ownership(  # noqa: PLR0913 — keyword-only XOR-pair API by design
    *,
    area: Area | None = None,
    room_profile: RoomProfile | None = None,
    to_persona: Persona | None = None,
    to_organization: Organization | None = None,
    notes: str = "",
    transferred_at: datetime | None = None,
) -> LocationOwnership:
    """Atomically transfer (or claim) ownership of a location.

    Ends the current active LocationOwnership row (if any) and creates a
    new row with the new holder. Wrapped in transaction.atomic so the
    "no active owner" window never appears to concurrent readers.

    Handles both first-time claims (no current owner) and transfers
    (current owner ended, new owner created). The protocol is identical;
    conflating them reduces API surface.

    Caller is responsible for permission gating — substrate does not
    check authority to transfer.
    """
    _validate_location_kwargs(area, room_profile)
    _validate_holder_kwargs(to_persona, to_organization)

    parent_type = LocationParentType.AREA if area is not None else LocationParentType.ROOM
    holder_type = HolderType.PERSONA if to_persona is not None else HolderType.ORGANIZATION
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

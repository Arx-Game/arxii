"""Read services for the location ambient stats cascade."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

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
    from collections.abc import Iterable
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


def _bulk_room_profiles_and_ancestors(
    rooms: Iterable[DefaultObject],
) -> tuple[dict[int, RoomProfile], dict[int, list[int]], set[int]]:
    """Bulk-resolve RoomProfiles and area ancestors for many rooms.

    Returns three values:
      - room_to_profile: room.pk -> RoomProfile (rooms without a
        profile are absent from this dict)
      - profile_to_ancestor_ids: profile.pk -> list of ancestor area
        ids from the area closure (empty list if profile.area is None)
      - all_ancestor_ids: union of every ancestor id, useful for
        bulk filters like Q(area_id__in=all_ancestor_ids)

    **One SQL query** for profiles + **one** for the area closure
    walk, regardless of room count. RoomProfile is keyed by
    ``objectdb_id`` (its primary key IS the room pk), so we can fetch
    all profiles in a single ``filter(objectdb_id__in=...)`` instead
    of relying on the per-room reverse OneToOne accessor (which fires
    a separate query per uncached room).
    """
    rooms_list = list(rooms)
    room_pks = [r.pk for r in rooms_list]
    room_to_profile: dict[int, RoomProfile] = {}
    profile_to_area_pk: dict[int, int] = {}
    all_area_pks: set[int] = set()

    profiles = RoomProfile.objects.filter(objectdb_id__in=room_pks)
    for profile in profiles:
        room_to_profile[profile.objectdb_id] = profile
        if profile.area_id is not None:
            profile_to_area_pk[profile.pk] = profile.area_id
            all_area_pks.add(profile.area_id)

    # One closure query for the union of areas.
    closure_rows = AreaClosure.objects.filter(descendant_id__in=all_area_pks).values_list(
        "descendant_id", "ancestor_id"
    )

    descendant_to_ancestors: dict[int, list[int]] = {}
    all_ancestor_ids: set[int] = set()
    for descendant_id, ancestor_id in closure_rows:
        descendant_to_ancestors.setdefault(descendant_id, []).append(ancestor_id)
        all_ancestor_ids.add(ancestor_id)

    profile_to_ancestor_ids: dict[int, list[int]] = {}
    for profile_pk, area_pk in profile_to_area_pk.items():
        profile_to_ancestor_ids[profile_pk] = descendant_to_ancestors.get(area_pk, [])

    return room_to_profile, profile_to_ancestor_ids, all_ancestor_ids


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


class _StatCascadeIndex(NamedTuple):
    """Pre-built lookup indexes for bulk stat resolution.

    Keyed by (profile_pk | area_pk) -> stat_key -> override/modifier(s).
    Built once per ``effective_stats_for_rooms`` call and reused for
    every (room, stat_key) pair in the pass.
    """

    overrides_by_profile: dict[int, dict[str, LocationStatOverride]]
    overrides_by_area: dict[int, dict[str, LocationStatOverride]]
    modifiers_by_profile: dict[int, dict[str, list[LocationStatModifier]]]
    modifiers_by_area: dict[int, dict[str, list[LocationStatModifier]]]


def _build_stat_cascade_index(
    overrides: list[LocationStatOverride],
    modifiers: list[LocationStatModifier],
) -> _StatCascadeIndex:
    """Build profile/area-keyed lookup indexes for stat overrides + modifiers."""
    overrides_by_profile: dict[int, dict[str, LocationStatOverride]] = {}
    overrides_by_area: dict[int, dict[str, LocationStatOverride]] = {}
    for o in overrides:
        if o.room_profile_id is not None:
            overrides_by_profile.setdefault(o.room_profile_id, {})[o.stat_key] = o
        elif o.area_id is not None:
            overrides_by_area.setdefault(o.area_id, {})[o.stat_key] = o

    modifiers_by_profile: dict[int, dict[str, list[LocationStatModifier]]] = {}
    modifiers_by_area: dict[int, dict[str, list[LocationStatModifier]]] = {}
    for m in modifiers:
        if m.room_profile_id is not None:
            modifiers_by_profile.setdefault(m.room_profile_id, {}).setdefault(
                m.stat_key, []
            ).append(m)
        elif m.area_id is not None:
            modifiers_by_area.setdefault(m.area_id, {}).setdefault(m.stat_key, []).append(m)

    return _StatCascadeIndex(
        overrides_by_profile=overrides_by_profile,
        overrides_by_area=overrides_by_area,
        modifiers_by_profile=modifiers_by_profile,
        modifiers_by_area=modifiers_by_area,
    )


def _resolve_stat_for_profile(
    profile: RoomProfile,
    stat_key: StatKey,
    ancestor_ids: list[int],
    index: _StatCascadeIndex,
) -> int:
    """Resolve one (profile, stat_key) from a pre-built index.

    Mirrors the singular ``effective_stat`` cascade rules: most-specific
    override wins (room beats deepest area); otherwise sum modifier
    current_values across the chain plus STAT_DEFAULTS, then clamp.
    """
    # Step 1: most-specific override (room beats deepest area)
    room_override = index.overrides_by_profile.get(profile.pk, {}).get(stat_key)
    if room_override is not None:
        return _clamp(room_override.value, stat_key)
    area_overrides = [
        index.overrides_by_area.get(area_id, {}).get(stat_key) for area_id in ancestor_ids
    ]
    area_overrides = [o for o in area_overrides if o is not None]
    if area_overrides:
        # Smaller area.level wins (BUILDING=10 most specific)
        chosen = min(area_overrides, key=lambda o: o.area.level)
        return _clamp(chosen.value, stat_key)

    # Step 2: sum modifier current_values
    total = STAT_DEFAULTS.get(stat_key, 0)
    for m in index.modifiers_by_profile.get(profile.pk, {}).get(stat_key, []):
        total += m.current_value()
    for area_id in ancestor_ids:
        for m in index.modifiers_by_area.get(area_id, {}).get(stat_key, []):
            total += m.current_value()
    return _clamp(total, stat_key)


def effective_stats_for_rooms(
    rooms: Iterable[DefaultObject],
    stat_keys: Iterable[StatKey],
) -> dict[int, dict[StatKey, int]]:
    """Bulk-resolve stats for many rooms in one pass.

    Returns: {room.pk: {stat_key: int}}.

    One AreaClosure walk for the union of all ancestor area ids (via
    _bulk_room_profiles_and_ancestors), one fetch of LocationStatOverride
    for those ids + room_profiles + stat_keys, one fetch of
    LocationStatModifier for the same scope, then resolves per room in
    Python.

    Rooms with no RoomProfile fall through to STAT_DEFAULTS[stat_key]
    clamped to STAT_CLAMPS[stat_key] for each requested stat_key.

    Query budget: 4 total queries regardless of room count (profiles +
    closure + overrides + modifiers).
    """
    rooms_list = list(rooms)
    stat_keys_list = list(stat_keys)
    if not rooms_list:
        return {}
    if not stat_keys_list:
        # Rooms present but no stat keys → empty per-room dicts
        return {room.pk: {} for room in rooms_list}

    room_to_profile, profile_to_ancestor_ids, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
        rooms_list
    )

    # Bulk fetch overrides matching the union of (room_profiles, ancestor_ids).
    profile_pks = {p.pk for p in room_to_profile.values()}
    overrides = list(
        LocationStatOverride.objects.filter(stat_key__in=stat_keys_list)
        .select_related("area")
        .filter(models.Q(room_profile_id__in=profile_pks) | models.Q(area_id__in=all_ancestor_ids))
    )
    modifiers = list(
        LocationStatModifier.objects.filter(stat_key__in=stat_keys_list).filter(
            models.Q(room_profile_id__in=profile_pks) | models.Q(area_id__in=all_ancestor_ids)
        )
    )
    index = _build_stat_cascade_index(overrides, modifiers)

    result: dict[int, dict[StatKey, int]] = {}
    for room in rooms_list:
        profile = room_to_profile.get(room.pk)
        if profile is None:
            result[room.pk] = {
                stat_key: _clamp(STAT_DEFAULTS.get(stat_key, 0), stat_key)
                for stat_key in stat_keys_list
            }
            continue
        ancestor_ids = profile_to_ancestor_ids.get(profile.pk, [])
        result[room.pk] = {
            stat_key: _resolve_stat_for_profile(profile, stat_key, ancestor_ids, index)
            for stat_key in stat_keys_list
        }
    return result


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


def effective_owners_for_rooms(
    rooms: Iterable[DefaultObject],
) -> dict[int, LocationOwnership | None]:
    """Bulk-resolve owners for many rooms in one pass.

    Returns: {room.pk: LocationOwnership | None}.

    One AreaClosure walk for the union of ancestor area ids (via
    _bulk_room_profiles_and_ancestors), one fetch of active
    LocationOwnership rows for those ids + room_profiles (with
    select_related on area + holders), then most-specific-wins
    selection per room in Python.

    Query budget: 3 total queries regardless of room count (profiles +
    closure + ownership).
    """
    rooms_list = list(rooms)
    if not rooms_list:
        return {}

    room_to_profile, profile_to_ancestor_ids, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
        rooms_list
    )

    profile_pks = {p.pk for p in room_to_profile.values()}

    rows = list(
        LocationOwnership.objects.filter(ended_at__isnull=True)
        .select_related("area", "holder_persona", "holder_organization")
        .filter(models.Q(room_profile_id__in=profile_pks) | models.Q(area_id__in=all_ancestor_ids))
    )

    # Index: profile-level overrides and area-level rows
    by_room: dict[int, LocationOwnership] = {}
    by_area: dict[int, LocationOwnership] = {}
    for r in rows:
        if r.room_profile_id is not None:
            by_room[r.room_profile_id] = r
        elif r.area_id is not None:
            by_area[r.area_id] = r

    result: dict[int, LocationOwnership | None] = {}
    for room in rooms_list:
        profile = room_to_profile.get(room.pk)
        if profile is None:
            result[room.pk] = None
            continue
        # Room-level wins
        if profile.pk in by_room:
            result[room.pk] = by_room[profile.pk]
            continue
        # Among area-level rows, smallest level wins (BUILDING=10 most specific)
        ancestor_ids = profile_to_ancestor_ids.get(profile.pk, [])
        area_rows = [by_area[aid] for aid in ancestor_ids if aid in by_area]
        if area_rows:
            result[room.pk] = min(area_rows, key=lambda r: r.area.level)
        else:
            result[room.pk] = None
    return result


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


def tenancies_for_rooms(
    rooms: Iterable[DefaultObject],
) -> dict[int, list[LocationTenancy]]:
    """Bulk-resolve currently-active tenancies for many rooms.

    Returns: {room.pk: [LocationTenancy, ...]}.

    One AreaClosure walk for the union of ancestor area ids (via
    _bulk_room_profiles_and_ancestors), one fetch of active
    LocationTenancy rows (with select_related on area + tenants),
    then group per room in Python.

    Returns a list per room (not a QuerySet) because grouping in
    Python after the bulk fetch precludes lazy evaluation. Rooms
    without a RoomProfile get an empty list.

    Query budget: 3 total queries regardless of room count (profiles +
    closure + tenancy).
    """
    rooms_list = list(rooms)
    if not rooms_list:
        return {}

    room_to_profile, profile_to_ancestor_ids, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
        rooms_list
    )

    profile_pks = {p.pk for p in room_to_profile.values()}

    now = timezone.now()
    rows = list(
        LocationTenancy.objects.filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))
        .select_related("area", "tenant_persona", "tenant_organization")
        .filter(models.Q(room_profile_id__in=profile_pks) | models.Q(area_id__in=all_ancestor_ids))
    )

    # Index rows by their parent
    by_room: dict[int, list[LocationTenancy]] = {}
    by_area: dict[int, list[LocationTenancy]] = {}
    for t in rows:
        if t.room_profile_id is not None:
            by_room.setdefault(t.room_profile_id, []).append(t)
        elif t.area_id is not None:
            by_area.setdefault(t.area_id, []).append(t)

    result: dict[int, list[LocationTenancy]] = {}
    for room in rooms_list:
        profile = room_to_profile.get(room.pk)
        if profile is None:
            result[room.pk] = []
            continue
        applicable: list[LocationTenancy] = list(by_room.get(profile.pk, []))
        ancestor_ids = profile_to_ancestor_ids.get(profile.pk, [])
        for aid in ancestor_ids:
            applicable.extend(by_area.get(aid, []))
        result[room.pk] = applicable
    return result


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

    Concurrent transfers on the same parent serialize via
    ``select_for_update`` on the existing-row lookup — the losing caller
    waits for the winning transaction to commit, then re-reads the now-
    ended row and proceeds. Concurrent *claims* of a never-owned
    location still race at the INSERT step and rely on the partial-
    unique constraint to surface ``IntegrityError`` for the loser; that
    contention is rare in practice (an area is only claimed once).
    """
    _validate_location_kwargs(area, room_profile)
    _validate_holder_kwargs(to_persona, to_organization)

    parent_type = LocationParentType.AREA if area is not None else LocationParentType.ROOM
    holder_type = HolderType.PERSONA if to_persona is not None else HolderType.ORGANIZATION
    when = transferred_at if transferred_at is not None else timezone.now()

    with transaction.atomic():
        existing_qs = LocationOwnership.objects.select_for_update().filter(ended_at__isnull=True)
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


def grant_tenancy(  # noqa: PLR0913 — keyword-only XOR-pair API by design
    *,
    area: Area | None = None,
    room_profile: RoomProfile | None = None,
    tenant_persona: Persona | None = None,
    tenant_organization: Organization | None = None,
    ends_at: datetime | None = None,
    notes: str = "",
) -> LocationTenancy:
    """Create a new LocationTenancy row.

    Multiple concurrent tenancies on the same location are valid by
    design — no conflict check. Caller is responsible for permission
    gating (only owners should grant tenancy).
    """
    _validate_location_kwargs(area, room_profile)
    _validate_holder_kwargs(tenant_persona, tenant_organization)

    parent_type = LocationParentType.AREA if area is not None else LocationParentType.ROOM
    tenant_type = HolderType.PERSONA if tenant_persona is not None else HolderType.ORGANIZATION
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
    ended_at: datetime | None = None,
) -> LocationTenancy:
    """End a tenancy by setting ``ends_at``.

    Covers eviction AND voluntary departure — the code path is identical
    and the semantic distinction is the caller's UX concern.

    Idempotent: re-calling on an already-ended tenancy overwrites
    ``ends_at`` with the new value. The new value can be in the past
    (eviction effective immediately) or in the future (planned end of
    lease).
    """
    tenancy.ends_at = ended_at if ended_at is not None else timezone.now()
    tenancy.save()
    return tenancy


def ownership_history_for(
    *,
    area: Area | None = None,
    room_profile: RoomProfile | None = None,
) -> QuerySet[LocationOwnership]:
    """Return ALL LocationOwnership rows (active and ended) for a
    location, ordered by acquired_at ascending.

    No closure walk — returns only rows directly attached to this
    location. Caller passes exactly one of (area, room_profile).

    Useful for forensics, GM tooling, and audit log displays.
    """
    _validate_location_kwargs(area, room_profile)
    qs = LocationOwnership.objects.select_related("area", "holder_persona", "holder_organization")
    if area is not None:
        qs = qs.filter(area=area)
    else:
        qs = qs.filter(room_profile=room_profile)
    return qs.order_by("acquired_at", "pk")


def tenancy_history_for(
    *,
    area: Area | None = None,
    room_profile: RoomProfile | None = None,
) -> QuerySet[LocationTenancy]:
    """Return ALL LocationTenancy rows (active and ended) for a
    location, ordered by started_at ascending.

    No closure walk — returns only rows directly attached to this
    location. Caller passes exactly one of (area, room_profile).
    """
    _validate_location_kwargs(area, room_profile)
    qs = LocationTenancy.objects.select_related("area", "tenant_persona", "tenant_organization")
    if area is not None:
        qs = qs.filter(area=area)
    else:
        qs = qs.filter(room_profile=room_profile)
    return qs.order_by("started_at", "pk")


def cleanup_decayed_modifiers(now: datetime | None = None) -> int:
    """Delete LocationStatModifier rows whose current_value() has
    decayed to zero.

    Iterates rows with non-zero change_per_day (zero-rate rows never
    decay), computes current_value() in Python (matching the read-side
    semantics), and deletes those whose value has crossed zero.

    Returns the count of rows deleted.

    Cheap to call from a cron or management command on any cadence —
    rows that haven't decayed yet are skipped without write traffic.

    The caller may pass ``now`` to make the sweep deterministic for
    tests; otherwise the model's current_value() defaults to
    timezone.now().

    Wrapped in transaction.atomic with select_for_update on the
    candidate iteration so concurrent ``applied_at = now()`` refreshes
    can't slip past us — the sweep serializes against modifier writes
    while it runs. Safe for daily-cadence cron; not recommended for
    high-frequency invocation.
    """
    with transaction.atomic():
        candidates = LocationStatModifier.objects.exclude(change_per_day=0).select_for_update()
        to_delete_ids: list[int] = [row.pk for row in candidates if row.current_value(now=now) == 0]
        if to_delete_ids:
            LocationStatModifier.objects.filter(pk__in=to_delete_ids).delete()
        return len(to_delete_ids)

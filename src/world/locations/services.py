"""Read services for the location ambient stats cascade."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from django.db import models, transaction
from django.utils import timezone

from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.models import RoomProfile
from world.areas.models import AreaClosure
from world.conditions.models import DamageType
from world.locations.constants import (
    AP_REGEN_MULTIPLIER_PCT,
    COMFORT_LEVEL_FLOORS,
    COMFORT_LEVEL_MIN,
    ENCLOSURE_SHELTERED_AXES,
    EXPOSURE_STAT_KEYS,
    STAT_CLAMPS,
    STAT_DEFAULTS,
    WEATHER_EXPOSURE_AXES,
    HolderType,
    KeyType,
    LocationParentType,
    StatKey,
)
from world.locations.models import (
    LocationOwnership,
    LocationTenancy,
    LocationValueModifier,
    LocationValueOverride,
)
from world.societies.models import OrganizationMembership
from world.weather.services import (
    climate_exposure_base,
    current_temperature_shift,
    get_effective_climate,
)

# Sentinel distinguishing "climate not supplied, resolve it" from "resolved to no climate".
_UNRESOLVED = object()

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from django.db.models import QuerySet
    from evennia.objects.objects import DefaultObject

    from world.areas.models import Area
    from world.magic.models import Resonance
    from world.scenes.models import Persona
    from world.societies.models import Organization
    from world.weather.models import Climate


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


def _resolve_cascade(
    profile: RoomProfile,
    ancestor_ids: list[int],
    axis_filter: models.Q,
) -> tuple[int | None, int]:
    """Resolve one axis's raw cascade, unclamped (shared by effective_value/felt_exposure).

    Returns ``(override_value, modifier_sum)``: if a most-specific override applies,
    ``override_value`` is its value and ``modifier_sum`` is 0; otherwise ``override_value``
    is None and ``modifier_sum`` is the summed modifier ``current_value``s. Neither the axis
    default nor any clamp is applied here — callers add their base (axis default or climate)
    and clamp, so climate can combine with local modifiers before the 0-floor.
    """
    override_val, positive_sum, negative_sum = _cascade_parts(profile, ancestor_ids, axis_filter)
    if override_val is not None:
        return override_val, 0
    return None, positive_sum - negative_sum


def _cascade_parts(
    profile: RoomProfile,
    ancestor_ids: list[int],
    axis_filter: models.Q,
) -> tuple[int | None, int, int]:
    """One axis's cascade, decomposed: ``(override, positive_sum, negative_sum)`` (#1514).

    ``negative_sum`` is a magnitude (>= 0). The decomposition feeds the owner
    build-HUD's pressure-vs-mitigation readout; ``_resolve_cascade`` recombines
    the parts for the plain summed read.
    """
    overrides = list(
        LocationValueOverride.objects.filter(axis_filter)
        .select_related("area")
        .filter(models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids))
    )
    if overrides:
        room_overrides = [o for o in overrides if o.room_profile_id == profile.pk]
        if room_overrides:
            return room_overrides[0].value, 0, 0
        return min(overrides, key=lambda o: o.area.level).value, 0, 0

    modifiers = LocationValueModifier.objects.filter(axis_filter).filter(
        models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids)
    )
    positive_sum = 0
    negative_sum = 0
    for mod in modifiers:
        current = mod.current_value()
        if current >= 0:
            positive_sum += current
        else:
            negative_sum += -current
    return None, positive_sum, negative_sum


def _resolve_room_climate(profile: RoomProfile | None) -> tuple[Climate | None, int]:
    """The room's effective climate and current seasonal temperature shift (#1522).

    Returns ``(None, 0)`` when the room has no profile/area or no climate is designated
    anywhere up its hierarchy. The seasonal shift is only read when a climate exists.
    """
    if profile is None or profile.area_id is None:
        return None, 0
    climate = get_effective_climate(profile.area)
    if climate is None:
        return None, 0
    return climate, current_temperature_shift()


def effective_value(
    room: DefaultObject,
    *,
    stat_key: StatKey | None = None,
    resonance: Resonance | None = None,
    damage_type: DamageType | None = None,
) -> int:
    """Cascade-resolve a single axis value (stat, resonance, or damage-type shelter) for a room.

    Exactly one of ``stat_key``, ``resonance``, or ``damage_type`` must be provided.

    Stats are clamped to STAT_CLAMPS and start from STAT_DEFAULTS. Resonance and
    damage-type values are not clamped and default to 0.

    Algorithm (2 queries per call: closure walk + override or modifier
    fetch; modifier ``current_value()`` is in-memory math):
      1. Resolve ``room.room_profile`` and its area. If the profile is
         missing, return the axis default (clamped for stats).
      2. Look up the area's ancestors (and itself) via ``AreaClosure``.
      3. If any ``LocationValueOverride`` for the matching axis exists in
         the ancestor set or on the room_profile, pick the most-specific
         (room > deepest area) and return its value (clamped for stats).
      4. Otherwise sum every ``LocationValueModifier.current_value`` for
         the same scope and axis, add the axis default, clamp for stats.
    """
    provided = [stat_key is not None, resonance is not None, damage_type is not None]
    if sum(provided) != 1:
        msg = "Provide exactly one of stat_key, resonance, or damage_type."
        raise ValueError(msg)

    if stat_key is not None:
        default = STAT_DEFAULTS.get(stat_key, 0)
        axis_filter = models.Q(key_type=KeyType.STAT, stat_key=stat_key)
    elif resonance is not None:
        default = 0
        axis_filter = models.Q(key_type=KeyType.RESONANCE, resonance=resonance)
    else:
        default = 0
        axis_filter = models.Q(key_type=KeyType.DAMAGE_TYPE, damage_type=damage_type)

    def _maybe_clamp(value: int) -> int:
        return _clamp(value, stat_key) if stat_key is not None else value

    profile, ancestor_ids = _room_profile_and_ancestors(room)
    if profile is None:
        return _maybe_clamp(default)

    override_val, modifier_sum = _resolve_cascade(profile, ancestor_ids, axis_filter)
    if override_val is not None:
        return _maybe_clamp(override_val)
    return _maybe_clamp(default + modifier_sum)


def hazard_is_covered(room: DefaultObject, damage_type: DamageType, *, threshold: int = 1) -> bool:
    """Whether *room* grants shelter against *damage_type* (#1744).

    A hard gate, not an arithmetic resistance — this answers "does the hazard reach this
    place at all," the same kind of fact ``RoomProfile.is_outdoor`` already answers, not
    "how much damage gets through" (that stays ``ConditionResistanceModifier`` arithmetic,
    per ADR-0073). ``threshold`` lets a future caller require a stronger shelter claim than
    the default "any positive value covers"; v1 callers use the default.
    """
    return effective_value(room, damage_type=damage_type) >= threshold


def room_enclosure(room: DefaultObject) -> RoomEnclosure:
    """The room's enclosure level (#1514); ``WALLED`` (a normal indoor room) if no profile."""
    try:
        return RoomEnclosure(room.room_profile.enclosure)
    except RoomProfile.DoesNotExist:
        return RoomEnclosure.WALLED


class _ExposureContext(NamedTuple):
    """A room's once-resolved state for felt-exposure reads (#1514, #1522).

    Built once per room by ``_exposure_context`` so multi-axis reads (``room_discomfort``,
    ``comfort_summary``) don't re-resolve the profile, climate, or enclosure per axis.
    """

    profile: RoomProfile | None
    ancestor_ids: list[int]
    climate: Climate | None
    temperature_shift: int
    sheltered_axes: frozenset[StatKey]


def _exposure_context(room: DefaultObject) -> _ExposureContext:
    """Resolve a room's profile, effective climate + seasonal shift, and sheltered axes once."""
    profile, ancestor_ids = _room_profile_and_ancestors(room)
    climate, temperature_shift = _resolve_room_climate(profile)
    sheltered_axes = ENCLOSURE_SHELTERED_AXES.get(room_enclosure(room), frozenset())
    return _ExposureContext(profile, ancestor_ids, climate, temperature_shift, sheltered_axes)


def _felt_exposure_for_axis(ctx: _ExposureContext, stat_key: StatKey) -> int:
    """One axis's felt exposure given already-resolved room/climate state (#1514, #1522).

    Folds the regional climate base (for exposure axes) into the same pre-floor sum as the
    local cascade modifiers — so a desert's HEAT base and a cooling fixture's negative HEAT
    modifier combine before the 0-floor. A warded-sanctum override still trumps both climate
    and modifiers. Non-exposure stats fall back to ``STAT_DEFAULTS`` as their base.
    """
    if stat_key in WEATHER_EXPOSURE_AXES and stat_key in ctx.sheltered_axes:
        return 0
    if stat_key in EXPOSURE_STAT_KEYS:
        base = climate_exposure_base(ctx.climate, stat_key, temperature_shift=ctx.temperature_shift)
    else:
        base = STAT_DEFAULTS.get(stat_key, 0)
    if ctx.profile is None:
        return _clamp(base, stat_key)
    override_val, modifier_sum = _resolve_cascade(
        ctx.profile, ctx.ancestor_ids, models.Q(key_type=KeyType.STAT, stat_key=stat_key)
    )
    if override_val is not None:
        return _clamp(override_val, stat_key)
    return _clamp(base + modifier_sum, stat_key)


def felt_exposure(room: DefaultObject, *, stat_key: StatKey) -> int:
    """A room's *felt* exposure on one axis, after enclosure sheltering (#1514, #1522).

    Weather axes (WET, WIND) are fully blocked — felt as 0 — when the room's enclosure
    shelters them (a roof stops rain/snow; walls stop wind). Temperature axes (COLD, HEAT)
    always seep through and are felt in full; insulation against them comes from
    fixtures/style, not enclosure. The room's regional climate baseline (#1522) folds into
    the exposure axes before the 0-floor. Non-weather, non-exposure stats are returned
    unchanged.
    """
    return _felt_exposure_for_axis(_exposure_context(room), stat_key)


def room_discomfort(room: DefaultObject) -> int:
    """Total residual environmental discomfort at a room (#1514, #1522).

    Sums the *felt* exposure axes (``EXPOSURE_STAT_KEYS`` — COLD, HEAT, WET, WIND, DRY): each
    is the regional climate baseline (#1522) plus the local cascade (weather/style up,
    counter-fixtures down), clamped at its 0-floor (a counter zeroes its own axis but never
    goes negative or touches another), then gated by enclosure for the weather axes (a
    sheltered room feels no rain or wind). Climate and the seasonal shift are resolved once
    for the whole room. The sum is always ``>= 0``; 0 means a perfectly comfortable room.
    """
    ctx = _exposure_context(room)
    return sum(_felt_exposure_for_axis(ctx, key) for key in EXPOSURE_STAT_KEYS)


def comfort_points(room: DefaultObject) -> int:
    """A room's raw comfort points (#1514): ``amenities − felt discomfort``.

    The wide pool that maps to a 1–10 level. Amenities (luxury decorations + magical comfort,
    the ``AMENITY`` axis) push it up; felt environmental discomfort pushes it down. Per-character
    inputs (condition penalties/buffs from wounds, fatigue, chilled, protection magic) are NOT
    here — they're passed as ``comfort_offset`` to ``comfort_level`` by the consumer, since the
    room sets the environmental base and the character's conditions adjust it.
    """
    return effective_value(room, stat_key=StatKey.AMENITY) - room_discomfort(room)


def comfort_level_for_points(points: int) -> int:
    """Map raw comfort points to a 1–10 comfort level (#1514).

    Returns the highest level whose points-floor is met (``COMFORT_LEVEL_FLOORS``); below the
    lowest floor is level 1. 5 is neutral. Bands are a PLACEHOLDER author pass — the shape
    (wide, sharp, 5 = "Fine") is fixed, the exact cuts are tunable.
    """
    for floor, level in COMFORT_LEVEL_FLOORS:
        if points >= floor:
            return level
    return COMFORT_LEVEL_MIN


def comfort_level(room: DefaultObject, *, comfort_offset: int = 0) -> int:
    """A room's comfort level (1–10) for an occupant (#1514).

    ``comfort_offset`` is the occupant's net per-character comfort contribution (condition
    penalties − / buffs +), supplied by the caller (e.g. the AP-regen hook reads the character's
    active conditions). Defaults to 0 for a bare environmental read.
    """
    return comfort_level_for_points(comfort_points(room) + comfort_offset)


def ap_regen_multiplier_pct(level: int) -> int:
    """The AP-regen percentage adjustment for a comfort level (#1514) — 0 at neutral (5)."""
    return AP_REGEN_MULTIPLIER_PCT.get(level, 0)


class ComfortSummary(NamedTuple):
    """A room's comfort readout for the in-room mechanical surface (#1514).

    The desc stays the player's trusted flavour; this is the separate *mechanical* readout that
    is the actual arbiter (a player can't write away the cold). ``felt_exposures`` holds only the
    non-zero discomfort axes (after enclosure + mitigation), so the surface lists what's actually
    biting.
    """

    level: int
    points: int
    felt_exposures: dict[StatKey, int]
    amenity: int


def comfort_summary(room: DefaultObject) -> ComfortSummary:
    """Resolve a room's comfort readout (#1514): level, points, the biting exposures, amenity."""
    ctx = _exposure_context(room)
    felt = {key: _felt_exposure_for_axis(ctx, key) for key in EXPOSURE_STAT_KEYS}
    points = comfort_points(room)
    return ComfortSummary(
        level=comfort_level_for_points(points),
        points=points,
        felt_exposures={key: value for key, value in felt.items() if value},
        amenity=effective_value(room, stat_key=StatKey.AMENITY),
    )


class AxisBreakdown(NamedTuple):
    """One exposure axis decomposed for the owner build-HUD (#1514).

    ``pressure`` is what pushes the axis up (climate base + positive cascade
    contributions), ``mitigation`` what pulls it down (fixtures/style, as a
    magnitude), ``net`` the felt value after the 0-floor and enclosure gate.
    ``sheltered`` marks a weather axis the room's enclosure zeroes outright.
    An authored override reports as pure pressure (it IS the value).
    """

    stat_key: StatKey
    pressure: int
    mitigation: int
    net: int
    sheltered: bool


def room_exposure_breakdown(room: DefaultObject) -> list[AxisBreakdown]:
    """Per-axis pressure/mitigation/net for a room — the build-HUD's engine (#1514).

    The gap the owner reads is ``net`` (what's still biting); the mitigation
    column shows their fixtures/style earning their keep. Matches
    ``felt_exposure`` semantics axis-for-axis (same context, same 0-floor,
    same enclosure gate).
    """
    ctx = _exposure_context(room)
    rows: list[AxisBreakdown] = []
    for stat_key in EXPOSURE_STAT_KEYS:
        base = climate_exposure_base(ctx.climate, stat_key, temperature_shift=ctx.temperature_shift)
        sheltered = stat_key in WEATHER_EXPOSURE_AXES and stat_key in ctx.sheltered_axes
        pressure = max(0, base)
        mitigation = max(0, -base)
        if ctx.profile is not None:
            override_val, positive_sum, negative_sum = _cascade_parts(
                ctx.profile,
                ctx.ancestor_ids,
                models.Q(key_type=KeyType.STAT, stat_key=stat_key),
            )
            if override_val is not None:
                pressure, mitigation = max(0, override_val), 0
            else:
                pressure += positive_sum
                mitigation += negative_sum
        net = _felt_exposure_for_axis(ctx, stat_key)
        rows.append(
            AxisBreakdown(
                stat_key=stat_key,
                pressure=pressure,
                mitigation=mitigation,
                net=net,
                sheltered=sheltered,
            )
        )
    return rows


class _StatCascadeIndex(NamedTuple):
    """Pre-built lookup indexes for bulk stat resolution.

    Keyed by (profile_pk | area_pk) -> stat_key -> override/modifier(s).
    Built once per ``effective_stats_for_rooms`` call and reused for
    every (room, stat_key) pair in the pass.
    """

    overrides_by_profile: dict[int, dict[str, LocationValueOverride]]
    overrides_by_area: dict[int, dict[str, LocationValueOverride]]
    modifiers_by_profile: dict[int, dict[str, list[LocationValueModifier]]]
    modifiers_by_area: dict[int, dict[str, list[LocationValueModifier]]]


def _build_stat_cascade_index(
    overrides: list[LocationValueOverride],
    modifiers: list[LocationValueModifier],
) -> _StatCascadeIndex:
    """Build profile/area-keyed lookup indexes for stat overrides + modifiers."""
    overrides_by_profile: dict[int, dict[str, LocationValueOverride]] = {}
    overrides_by_area: dict[int, dict[str, LocationValueOverride]] = {}
    for o in overrides:
        if o.room_profile_id is not None:
            overrides_by_profile.setdefault(o.room_profile_id, {})[o.stat_key] = o
        elif o.area_id is not None:
            overrides_by_area.setdefault(o.area_id, {})[o.stat_key] = o

    modifiers_by_profile: dict[int, dict[str, list[LocationValueModifier]]] = {}
    modifiers_by_area: dict[int, dict[str, list[LocationValueModifier]]] = {}
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


class _ResonanceCascadeIndex(NamedTuple):
    """Pre-built lookup indexes for bulk resonance resolution.

    Mirrors _StatCascadeIndex but keyed by resonance.pk (int) instead of
    stat_key (str). Resonance rows always have ``key_type=RESONANCE`` and
    ``resonance_id`` set; stat-keyed rows are filtered out at fetch time.
    """

    overrides_by_profile: dict[int, dict[int, LocationValueOverride]]
    overrides_by_area: dict[int, dict[int, LocationValueOverride]]
    modifiers_by_profile: dict[int, dict[int, list[LocationValueModifier]]]
    modifiers_by_area: dict[int, dict[int, list[LocationValueModifier]]]


def _build_resonance_cascade_index(
    overrides: list[LocationValueOverride],
    modifiers: list[LocationValueModifier],
) -> _ResonanceCascadeIndex:
    """Build profile/area-keyed lookup indexes for resonance rows."""
    overrides_by_profile: dict[int, dict[int, LocationValueOverride]] = {}
    overrides_by_area: dict[int, dict[int, LocationValueOverride]] = {}
    for o in overrides:
        if o.resonance_id is None:
            continue
        if o.room_profile_id is not None:
            overrides_by_profile.setdefault(o.room_profile_id, {})[o.resonance_id] = o
        elif o.area_id is not None:
            overrides_by_area.setdefault(o.area_id, {})[o.resonance_id] = o

    modifiers_by_profile: dict[int, dict[int, list[LocationValueModifier]]] = {}
    modifiers_by_area: dict[int, dict[int, list[LocationValueModifier]]] = {}
    for m in modifiers:
        if m.resonance_id is None:
            continue
        if m.room_profile_id is not None:
            modifiers_by_profile.setdefault(m.room_profile_id, {}).setdefault(
                m.resonance_id, []
            ).append(m)
        elif m.area_id is not None:
            modifiers_by_area.setdefault(m.area_id, {}).setdefault(m.resonance_id, []).append(m)

    return _ResonanceCascadeIndex(
        overrides_by_profile=overrides_by_profile,
        overrides_by_area=overrides_by_area,
        modifiers_by_profile=modifiers_by_profile,
        modifiers_by_area=modifiers_by_area,
    )


def _resolve_resonance_for_profile(
    profile: RoomProfile,
    resonance_id: int,
    ancestor_ids: list[int],
    index: _ResonanceCascadeIndex,
) -> int:
    """Resolve one (profile, resonance_id) from a pre-built index.

    Mirrors the singular ``effective_value`` resonance path: most-specific
    override wins (room beats deepest area); otherwise sum modifier
    current_values across the chain plus 0 default. No clamping.
    """
    room_override = index.overrides_by_profile.get(profile.pk, {}).get(resonance_id)
    if room_override is not None:
        return room_override.value
    area_overrides_raw = [
        index.overrides_by_area.get(area_id, {}).get(resonance_id) for area_id in ancestor_ids
    ]
    area_overrides = [o for o in area_overrides_raw if o is not None]
    if area_overrides:
        chosen = min(area_overrides, key=lambda o: o.area.level)
        return chosen.value

    total = 0  # resonance default
    for m in index.modifiers_by_profile.get(profile.pk, {}).get(resonance_id, []):
        total += m.current_value()
    for area_id in ancestor_ids:
        for m in index.modifiers_by_area.get(area_id, {}).get(resonance_id, []):
            total += m.current_value()
    return total


def effective_values_for_rooms(
    rooms: Iterable[DefaultObject],
    *,
    stat_keys: Iterable[StatKey] | None = None,
    resonances: Iterable[Resonance] | None = None,
) -> dict[int, dict[StatKey | Resonance, int]]:
    """Bulk-resolve cascade values across many rooms for one axis.

    Exactly one of ``stat_keys`` or ``resonances`` must be provided.

    Stat-keyed reads delegate to :func:`effective_stats_for_rooms`.
    Resonance reads share the same 4-query budget: profiles + closure
    + overrides + modifiers, independent of room count.

    Returns: ``{room.pk: {axis_key: int}}`` where axis_key is StatKey or
    Resonance depending on which kwarg was passed. Rooms without a
    RoomProfile fall through to STAT_DEFAULTS (clamped) for stats and
    0 for resonances.
    """
    if (stat_keys is None) == (resonances is None):
        msg = "Provide exactly one of stat_keys or resonances."
        raise ValueError(msg)

    if stat_keys is not None:
        return effective_stats_for_rooms(rooms, stat_keys)  # type: ignore[return-value]

    rooms_list = list(rooms)
    resonances_list = list(resonances) if resonances is not None else []
    if not rooms_list:
        return {}
    if not resonances_list:
        return {room.pk: {} for room in rooms_list}

    resonance_ids = [r.pk for r in resonances_list]
    resonance_by_id = {r.pk: r for r in resonances_list}

    room_to_profile, profile_to_ancestor_ids, all_ancestor_ids = _bulk_room_profiles_and_ancestors(
        rooms_list
    )
    profile_pks = {p.pk for p in room_to_profile.values()}

    overrides = list(
        LocationValueOverride.objects.filter(
            key_type=KeyType.RESONANCE,
            resonance_id__in=resonance_ids,
        )
        .select_related("area")
        .filter(models.Q(room_profile_id__in=profile_pks) | models.Q(area_id__in=all_ancestor_ids))
    )
    modifiers = list(
        LocationValueModifier.objects.filter(
            key_type=KeyType.RESONANCE,
            resonance_id__in=resonance_ids,
        ).filter(models.Q(room_profile_id__in=profile_pks) | models.Q(area_id__in=all_ancestor_ids))
    )
    index = _build_resonance_cascade_index(overrides, modifiers)

    result: dict[int, dict[StatKey | Resonance, int]] = {}
    for room in rooms_list:
        profile = room_to_profile.get(room.pk)
        if profile is None:
            result[room.pk] = dict.fromkeys(resonances_list, 0)
            continue
        ancestor_ids = profile_to_ancestor_ids.get(profile.pk, [])
        result[room.pk] = {
            resonance_by_id[r_id]: _resolve_resonance_for_profile(
                profile, r_id, ancestor_ids, index
            )
            for r_id in resonance_ids
        }
    return result


def effective_stats_for_rooms(
    rooms: Iterable[DefaultObject],
    stat_keys: Iterable[StatKey],
) -> dict[int, dict[StatKey, int]]:
    """Bulk-resolve stats for many rooms in one pass.

    Returns: {room.pk: {stat_key: int}}.

    One AreaClosure walk for the union of all ancestor area ids (via
    _bulk_room_profiles_and_ancestors), one fetch of LocationValueOverride
    for those ids + room_profiles + stat_keys, one fetch of
    LocationValueModifier for the same scope, then resolves per room in
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
        LocationValueOverride.objects.filter(stat_key__in=stat_keys_list)
        .select_related("area")
        .filter(models.Q(room_profile_id__in=profile_pks) | models.Q(area_id__in=all_ancestor_ids))
    )
    modifiers = list(
        LocationValueModifier.objects.filter(stat_key__in=stat_keys_list).filter(
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


def transfer_ownership(  # noqa: PLR0913
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

        ownership = LocationOwnership.objects.create(
            parent_type=parent_type,
            area=area,
            room_profile=room_profile,
            holder_type=holder_type,
            holder_persona=to_persona,
            holder_organization=to_organization,
            acquired_at=when,
            notes=notes,
        )
        # Acquire a room with no home yet → it becomes your home until you change it (#1514).
        # Area-level ownership and org owners are skipped (no single character / not a room).
        maybe_default_residence(to_persona, room_profile)
        return ownership


def grant_tenancy(  # noqa: PLR0913
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
    tenancy = LocationTenancy.objects.create(
        parent_type=parent_type,
        area=area,
        room_profile=room_profile,
        tenant_type=tenant_type,
        tenant_persona=tenant_persona,
        tenant_organization=tenant_organization,
        ends_at=ends_at,
        notes=notes,
    )
    # Rent a room with no home yet → it becomes your home until you change it (#1514).
    maybe_default_residence(tenant_persona, room_profile)
    return tenancy


def _character_for_persona(persona: Persona | None) -> DefaultObject | None:
    """The character (ObjectDB) behind a persona, or None."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    if persona is None:
        return None
    try:
        return persona.character_sheet.character
    except (AttributeError, ObjectDoesNotExist):
        return None


def set_residence(*, character: DefaultObject, room: DefaultObject) -> None:
    """Set a character's primary residence (#1514).

    Reuses Evennia's ``home`` — the location ``CmdHome`` recalls to and the fall-back if the
    current room is destroyed — which is the intended dual meaning for a residence. Permission
    gating (the character has owner/tenant standing in ``room``) is the caller's concern.
    """
    from world.locations.comfort_effect import recompute_comfort_regen_modifier  # noqa: PLC0415

    character.home = room
    recompute_comfort_regen_modifier(character)  # home comfort → AP-regen modifier (#1514)


def _has_chosen_residence(character: DefaultObject) -> bool:
    """Whether the character has a *real* residence vs none / the system default fall-back home.

    Evennia gives every object a default ``home`` (``settings.DEFAULT_HOME``), so "no residence
    yet" is not simply ``home is None`` — it's that *or* the global default.
    """
    from django.conf import settings  # noqa: PLC0415

    home = character.home
    if home is None:
        return False
    default = settings.DEFAULT_HOME
    return default is None or f"#{home.id}" != default


def maybe_default_residence(persona: Persona | None, room_profile: RoomProfile | None) -> None:
    """Default a persona's character home to this room when it has none yet (#1514).

    Called when a persona accepts a room (tenancy/ownership). Per-character (Evennia ``home``),
    triggered by a persona grant; never overwrites a residence the player has already chosen.
    """
    if persona is None or room_profile is None:
        return
    character = _character_for_persona(persona)
    if character is not None and not _has_chosen_residence(character):
        set_residence(character=character, room=room_profile.objectdb)


def assign_room_tenant(
    *,
    persona: Persona,
    room: DefaultObject,
    tenant_persona: Persona,
    ends_at: datetime | None = None,
    notes: str = "",
) -> LocationTenancy:
    """Owner-gated grant of a room tenancy (#670) — the player seam over grant_tenancy.

    Re-checks ownership as a hard boundary (action prerequisites are the
    primary UX gate).
    """
    if not is_owner(persona, room):
        msg = "Only the building's owner can assign tenants."
        raise RoomEditError(msg)
    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist as exc:
        msg = "This room can't hold tenants."
        raise RoomEditError(msg) from exc
    return grant_tenancy(
        room_profile=profile, tenant_persona=tenant_persona, ends_at=ends_at, notes=notes
    )


def end_room_tenancy(*, persona: Persona, tenancy: LocationTenancy) -> LocationTenancy:
    """End a room tenancy (#670): the room's owner (eviction) or the tenant (departure)."""
    room = tenancy.room_profile.objectdb if tenancy.room_profile else None
    is_self = tenancy.tenant_persona_id == persona.pk
    if not is_self and (room is None or not is_owner(persona, room)):
        msg = "Only the room's owner or the tenant can end this tenancy."
        raise RoomEditError(msg)
    return end_tenancy(tenancy)


def set_primary_home(*, persona: Persona, room: DefaultObject) -> LocationTenancy:
    """Designate one of the persona's active room tenancies as their home (#670).

    The Arx-1 ``addhome``: one active primary home per persona (partial unique
    constraint); drives prestige-from-dwellings. Requires a *direct* persona
    tenancy on the room — org/area standing isn't a home. Also syncs the
    character-level residence (#1514 Evennia ``home``: recall + comfort regen)
    so "home" stays one concept with two consumers.
    """
    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist as exc:
        msg = "That isn't a room you could live in."
        raise RoomEditError(msg) from exc
    now = timezone.now()
    tenancy = (
        LocationTenancy.objects.filter(tenant_persona=persona, room_profile=profile)
        .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))
        .order_by("started_at")
        .first()
    )
    if tenancy is None:
        msg = "You'd need a tenancy here first — this room isn't yours to live in."
        raise RoomEditError(msg)
    with transaction.atomic():
        LocationTenancy.objects.filter(tenant_persona=persona, is_primary_home=True).update(
            is_primary_home=False
        )
        tenancy.is_primary_home = True
        tenancy.save(update_fields=["is_primary_home"])
    character = _character_for_persona(persona)
    if character is not None:
        set_residence(character=character, room=room)
    from world.buildings.polish_services import (  # noqa: PLC0415
        recompute_persona_prestige_from_dwellings,
    )

    recompute_persona_prestige_from_dwellings(persona)
    return tenancy


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


@transaction.atomic
def upsert_room_resonance_modifier(
    room_profile: RoomProfile,
    resonance: Resonance,
    *,
    source: str,
    delta: int,
) -> LocationValueModifier:
    """Get-or-create the room-level (room_profile, resonance, source) cascade row and
    add ``delta`` to its value (signed). Returns the row.

    Mechanic only — callers own any cap/floor policy. Uses select_for_update on the
    existing row so concurrent mutators serialize; SharedMemoryModel-safe save.
    """
    row = (
        LocationValueModifier.objects.select_for_update()
        .filter(
            parent_type=LocationParentType.ROOM,
            room_profile=room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            source=source,
        )
        .first()
    )
    if row is None:
        return LocationValueModifier.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room_profile,
            key_type=KeyType.RESONANCE,
            resonance=resonance,
            value=delta,
            change_per_day=0,
            source=source,
        )
    row.value += delta
    row.save(update_fields=["value"])
    return row


def cleanup_decayed_modifiers(now: datetime | None = None) -> int:
    """Delete LocationValueModifier rows whose current_value() has
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
        candidates = LocationValueModifier.objects.exclude(change_per_day=0).select_for_update()
        to_delete_ids: list[int] = [row.pk for row in candidates if row.current_value(now=now) == 0]
        if to_delete_ids:
            LocationValueModifier.objects.filter(pk__in=to_delete_ids).delete()
        return len(to_delete_ids)


# ---------------------------------------------------------------------------
# Owner-facing room editing (#1470) — the player room-editor MVP seam
# ---------------------------------------------------------------------------


class RoomEditError(Exception):
    """A room edit was refused; carries a player-facing ``user_message``.

    Never surface ``str(exc)`` to API responses — use ``exc.user_message``.
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def _has_active_non_public_scene(room: DefaultObject) -> bool:
    """Whether an active, non-PUBLIC scene is running in this room.

    The inverse of the #1287 scene-privacy invariant: a publicly-listed room may
    host only PUBLIC scenes, so a room cannot be *made* public while a
    PRIVATE/EPHEMERAL scene is live in it.
    """
    from world.scenes.constants import ScenePrivacyMode  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415

    return (
        Scene.objects.filter(location=room, is_active=True)
        .exclude(privacy_mode=ScenePrivacyMode.PUBLIC)
        .exists()
    )


def set_room_display_data(
    *,
    room: DefaultObject,
    persona: Persona,
    name: str | None = None,
    description: str | None = None,
    is_public: bool | None = None,
) -> None:
    """Owner-gated edit of a room's display name, description, and public listing.

    Re-checks ownership as a hard boundary (the action prerequisite is the primary
    UX gate). Refuses to make a room public while a non-public scene is active in
    it. Writes name → ``ObjectDisplayData.longname``, description →
    ``permanent_description``, listing → ``RoomProfile.is_public``. Idempotent;
    only the provided fields are touched.
    """
    from evennia_extensions.models import ObjectDisplayData  # noqa: PLC0415

    if not is_owner(persona, room):
        msg = "You don't own this room."
        raise RoomEditError(msg)
    if is_public is True and _has_active_non_public_scene(room):
        msg = "A non-public scene is happening here; it must end before the room can be public."
        raise RoomEditError(msg)

    if name is not None or description is not None:
        display, _ = ObjectDisplayData.objects.get_or_create(object=room)
        if name is not None:
            display.longname = name
        if description is not None:
            display.permanent_description = description
        display.save()
    if is_public is not None:
        profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        profile.is_public = is_public
        profile.save(update_fields=["is_public"])

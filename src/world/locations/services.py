"""Read services for the location ambient stats cascade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from evennia_extensions.models import RoomProfile
from world.areas.models import AreaClosure
from world.locations.constants import STAT_CLAMPS, STAT_DEFAULTS, StatKey
from world.locations.models import LocationStatModifier, LocationStatOverride

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


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
    # Django's OneToOne reverse accessor raises RelatedObjectDoesNotExist
    # (a subclass of RoomProfile.DoesNotExist) when the room has no profile;
    # getattr-with-default doesn't suppress that exception. Project linter
    # also forbids getattr with a literal attribute name (GETATTR_LITERAL).
    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist:
        return _clamp(default, stat_key)

    area = profile.area
    ancestor_ids: list[int] = []
    if area is not None:
        ancestor_ids = list(
            AreaClosure.objects.filter(descendant_id=area.pk).values_list("ancestor_id", flat=True)
        )

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

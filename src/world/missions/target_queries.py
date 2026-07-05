"""ENVIRONMENTAL_DETAIL target-search candidates for MissionGiverTargetSearchAPIView (#882).

Mirrors the Character/Room/Exit exclusion that `MissionGiver.clean()` enforces
at the instance level (models.py, via `is_typeclass`) using a DB-level
substring approximation instead — `is_typeclass` walks the typeclass MRO and
can't run inside a queryset filter. This is the same `db_typeclass_path__contains`
convention already used in `world/forms/models.py` and `world/stories/permissions.py`.
Keep the three names below in sync with `clean()` if a typeclass is ever renamed.
"""

from __future__ import annotations

from django.db.models import QuerySet
from evennia.objects.models import ObjectDB


def environmental_detail_candidates() -> QuerySet[ObjectDB]:
    """ObjectDB rows eligible as an ENVIRONMENTAL_DETAIL giver target."""
    return (
        ObjectDB.objects.exclude(db_typeclass_path__contains="Character")
        .exclude(db_typeclass_path__contains="Room")
        .exclude(db_typeclass_path__contains="Exit")
    )

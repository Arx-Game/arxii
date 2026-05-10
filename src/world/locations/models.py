"""Models for the location ambient stats cascade.

See ``docs/plans/2026-05-09-location-stats-design.md`` for the full design.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from world.locations.constants import LocationParentType, StatKey


class LocationStatOverride(DiscriminatorMixin, SharedMemoryModel):
    """An absolute claim about a stat at a specific area or room.

    Most-specific override in the cascade chain wins. Overrides cut the
    cascade entirely: when any override exists at any level above (or
    equal to) the room, all modifiers are ignored.

    Used **rarely** — for warded sanctums, safehouses, magically
    stabilized chambers, or other deliberate "this is the value, period"
    claims. Most authored values should use ``LocationStatModifier``
    with ``change_per_day=0`` for a permanent additive instead.
    """

    DISCRIMINATOR_FIELD = "parent_type"
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    parent_type = models.CharField(
        max_length=10,
        choices=LocationParentType.choices,
        help_text="Selects which FK (area or room_profile) is active.",
    )
    area = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stat_overrides",
    )
    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stat_overrides",
    )
    stat_key = models.CharField(
        max_length=50,
        choices=StatKey.choices,
        db_index=True,
    )
    value = models.IntegerField(
        help_text=("The absolute value asserted at this level. Final read clamps to STAT_CLAMPS."),
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Location Stat Override"
        verbose_name_plural = "Location Stat Overrides"
        constraints = [
            models.UniqueConstraint(
                fields=["area", "stat_key"],
                condition=models.Q(area__isnull=False),
                name="unique_override_per_area_stat",
            ),
            models.UniqueConstraint(
                fields=["room_profile", "stat_key"],
                condition=models.Q(room_profile__isnull=False),
                name="unique_override_per_room_stat",
            ),
        ]
        indexes = [
            models.Index(fields=["area", "stat_key"]),
            models.Index(fields=["room_profile", "stat_key"]),
        ]

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"Override {self.stat_key}={self.value} @ {target}"

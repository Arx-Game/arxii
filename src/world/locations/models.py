"""Models for the location ambient stats cascade.

See ``docs/plans/2026-05-09-location-stats-design.md`` for the full design.
"""

from __future__ import annotations

from datetime import datetime

from django.db import models
from django.utils import timezone
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

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"Override {self.stat_key}={self.value} @ {target}"


class LocationStatModifier(DiscriminatorMixin, SharedMemoryModel):
    """An additive contribution to a stat at a specific area or room.

    Modifiers stack across the cascade chain. The effective value at a
    room is the sum of every modifier's :meth:`current_value` plus the
    per-stat default, clamped to bounds — provided no override exists in
    the chain.

    Carries its own ``change_per_day`` so consuming systems can model
    decay or growth rates that depend on IC mechanics. Read-time math is
    lazy; rows are not mutated by time passing.
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
        related_name="stat_modifiers",
    )
    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="stat_modifiers",
    )
    stat_key = models.CharField(
        max_length=50,
        choices=StatKey.choices,
        db_index=True,
    )
    value = models.IntegerField(
        help_text=(
            "The magnitude at applied_at. Read-side computes the current "
            "value via change_per_day * days_elapsed."
        ),
    )
    change_per_day = models.IntegerField(
        default=0,
        help_text=(
            "Signed: negative decays toward zero, positive grows away from "
            "zero, zero is permanent. Per-row override of any per-stat "
            "default."
        ),
    )
    source = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Free-text label for the originating system or event. Use to "
            "bulk-clean rows when the source ends "
            "(e.g. ``LocationStatModifier.objects.filter("
            "source='rebellion_1234').delete()``)."
        ),
    )
    applied_at = models.DateTimeField(
        default=timezone.now,
        help_text="Decay anchor. Update this to 'refresh' the modifier.",
    )

    class Meta:
        verbose_name = "Location Stat Modifier"
        verbose_name_plural = "Location Stat Modifiers"
        indexes = [
            models.Index(fields=["area", "stat_key"]),
            models.Index(fields=["room_profile", "stat_key"]),
        ]

    def current_value(self, *, now: datetime | None = None) -> int:
        """Return the lazy decay/growth-resolved value.

        Returns 0 once the modifier has crossed its original sign
        (a positive value decayed past zero, or a negative value grown
        past zero). Otherwise returns ``value + change_per_day * days``.
        """
        if self.change_per_day == 0:
            return self.value
        anchor = now if now is not None else timezone.now()
        elapsed = anchor - self.applied_at
        days = elapsed.total_seconds() / 86400.0
        new_value = self.value + int(self.change_per_day * days)
        if self.value > 0 and new_value <= 0:
            return 0
        if self.value < 0 and new_value >= 0:
            return 0
        return new_value

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"Modifier {self.stat_key}+{self.value} @ {target}"

"""Models for the location ambient stats cascade.

See ``docs/plans/2026-05-09-location-stats-design.md`` for the full design.
"""

from __future__ import annotations

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from world.locations.constants import HolderType, LocationParentType, StatKey


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
        past zero). Also returns 0 unconditionally when ``value`` is 0
        (you can't decay or grow from zero).

        Partial days truncate toward zero — a half-day with
        ``change_per_day=-1`` produces no decay. This is intentional:
        decay/growth advances in whole-day steps. Callers wanting finer
        resolution can use seconds-grained ``applied_at`` updates.
        """
        if self.value == 0 or self.change_per_day == 0:
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


class LocationOwnership(DiscriminatorMixin, SharedMemoryModel):
    """Who holds the deed/title/claim of right to a location.

    Cascades through the area hierarchy via ``AreaClosure``: the
    most-specific active row in the chain wins. Liege/vassal nesting
    is multiple rows at different tiers; the cascade resolver picks
    the deepest naturally.

    Historical rows (``ended_at IS NOT NULL``) are kept as audit trail.
    The partial-unique constraint enforces at most one *active* owner
    per location.

    Note: ``acquired_at`` defaults to ``timezone.now`` at instance
    construction time, not save time. For most flows this is invisible
    (you call ``objects.create()``), but for backfill/import scenarios
    pass ``acquired_at`` explicitly to control the audit timestamp.
    """

    DISCRIMINATOR_FIELD = "parent_type"
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    parent_type = models.CharField(
        max_length=10,
        choices=LocationParentType.choices,
        help_text="Selects which parent FK (area or room_profile) is active.",
    )
    area = models.ForeignKey(
        "areas.Area",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ownership_records",
    )
    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ownership_records",
    )

    holder_type = models.CharField(
        max_length=20,
        choices=HolderType.choices,
        help_text="Selects which holder FK (persona or organization) is active.",
    )
    holder_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ownership_records",
    )
    holder_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ownership_records",
    )

    acquired_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this party ceased to be the owner. NULL = currently active.",
    )
    notes = models.CharField(
        max_length=200,
        blank=True,
        help_text="Free-text provenance: 'via inheritance from House X', 'purchased 1234'.",
    )

    HOLDER_DISCRIMINATOR_FIELD = "holder_type"
    HOLDER_DISCRIMINATOR_MAP = {
        HolderType.PERSONA: "holder_persona",
        HolderType.ORGANIZATION: "holder_organization",
    }

    class Meta:
        verbose_name = "Location Ownership"
        verbose_name_plural = "Location Ownerships"
        constraints = [
            models.UniqueConstraint(
                fields=["area"],
                condition=models.Q(area__isnull=False) & models.Q(ended_at__isnull=True),
                name="unique_active_ownership_per_area",
            ),
            models.UniqueConstraint(
                fields=["room_profile"],
                condition=models.Q(room_profile__isnull=False) & models.Q(ended_at__isnull=True),
                name="unique_active_ownership_per_room",
            ),
        ]

    def clean(self) -> None:
        """Validate BOTH discriminators (parent and holder), collecting all errors."""
        parent_errors = self._validate_discriminator(
            self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP
        )
        holder_errors = self._validate_discriminator(
            self.HOLDER_DISCRIMINATOR_FIELD, self.HOLDER_DISCRIMINATOR_MAP
        )
        errors = {**parent_errors, **holder_errors}
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        target = self.get_active_target_name()
        holder_field = self.HOLDER_DISCRIMINATOR_MAP.get(self.holder_type)
        holder = getattr(self, holder_field, None) if holder_field else None
        holder_name = str(holder) if holder is not None else "(deleted)"
        active = "active" if self.ended_at is None else "historical"
        return f"Ownership of {target} by {holder_name} ({active})"

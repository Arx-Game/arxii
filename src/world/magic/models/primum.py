"""Primum held in the world, and who has sensed or called it up (#5125).

Primum is the raw stuff of a substance. It exists as harvestable stock only where hostile
monsters are: a lair (``PlacePrimum``) or a creature (``CreaturePrimum``). A call-up
(``PrimumCallUp``) is a caster raising a place's Primum by one step for a while, and a sighting
(``PrimumSighting``) is a caster having perceived Primum in a place. Neither call-ups nor
sightings are harvestable.
"""

from __future__ import annotations

from datetime import datetime

from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin

_SUBSTANCE_MODEL = "arxii.Substance"
_ROOM_PROFILE_MODEL = "arxii.RoomProfile"
_CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"


class PlacePrimumManager(NaturalKeyManager):
    """Manager for PlacePrimum with natural key support."""


class PlacePrimum(NaturalKeyMixin, SharedMemoryModel):
    """The Primum a lair holds of one substance (#5125).

    A lair refills very slowly or never. ``stored_amount`` is what was held at ``stamped_at``;
    ``current_amount`` adds whole days of refill since, up to ``capacity``. A finite place never
    refills. The database refuses a ``stored_amount`` above ``capacity``.
    """

    room_profile = models.ForeignKey(
        _ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="primum",
        help_text="The place that holds the Primum.",
    )
    substance = models.ForeignKey(
        _SUBSTANCE_MODEL,
        on_delete=models.PROTECT,
        related_name="places",
        help_text="The substance held.",
    )
    capacity = models.PositiveIntegerField(
        help_text="The most Primum the place can hold of this substance.",
    )
    stored_amount = models.PositiveIntegerField(
        help_text=(
            "How much Primum this place holds. Refill days add to it; "
            "changing it here starts the refill count again."
        ),
    )
    stamped_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the stored amount was last written. Refill counts from here.",
    )
    refill_per_day = models.PositiveIntegerField(
        default=0,
        help_text="Primum the place gains each whole day. 0 means it never refills.",
    )
    is_finite = models.BooleanField(
        default=False,
        help_text="A finite place never refills, whatever its refill per day.",
    )

    objects = PlacePrimumManager()

    class NaturalKeyConfig:
        fields = ["room_profile", "substance"]
        dependencies = [_ROOM_PROFILE_MODEL, _SUBSTANCE_MODEL]

    class Meta:
        verbose_name = "Place primum"
        verbose_name_plural = "Place primum"
        constraints = [
            models.UniqueConstraint(
                fields=["room_profile", "substance"],
                name="magic_placeprimum_room_substance_unique",
            ),
            models.CheckConstraint(
                check=Q(stored_amount__lte=F("capacity")),
                name="magic_placeprimum_stored_within_capacity",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.substance} in {self.room_profile_id}"

    @staticmethod
    def amount_at(  # noqa: PLR0913 - the six stored facts of one row, read as values under lock
        *,
        stored_amount: int,
        stamped_at: datetime,
        refill_per_day: int,
        capacity: int,
        is_finite: bool,
        now: datetime | None = None,
    ) -> int:
        """The Primum a row with these stored facts holds at ``now`` (default: the present).

        A finite place answers ``stored_amount``. Any other place gains ``refill_per_day`` for
        every whole day since ``stamped_at`` and never holds more than ``capacity``. A clock
        reading earlier than ``stamped_at`` counts as no time passed.
        """
        if is_finite:
            return stored_amount
        moment = now if now is not None else timezone.now()
        whole_days = max((moment - stamped_at).days, 0)
        return min(capacity, stored_amount + refill_per_day * whole_days)

    def current_amount(self, now: datetime | None = None) -> int:
        """The Primum this place holds at ``now`` (default: the present)."""
        return self.amount_at(
            stored_amount=self.stored_amount,
            stamped_at=self.stamped_at,
            refill_per_day=self.refill_per_day,
            capacity=self.capacity,
            is_finite=self.is_finite,
            now=now,
        )


class CreaturePrimumManager(NaturalKeyManager):
    """Manager for CreaturePrimum with natural key support."""


class CreaturePrimum(NaturalKeyMixin, SharedMemoryModel):
    """The Primum a kind of creature carries of one substance (#5125).

    A slain creature is harvested once, so this is a single amount, not a stock that refills.
    """

    creature_template = models.ForeignKey(
        "arxii.CreatureTemplate",
        on_delete=models.CASCADE,
        related_name="primum",
        help_text="The creature that carries the Primum.",
    )
    substance = models.ForeignKey(
        _SUBSTANCE_MODEL,
        on_delete=models.PROTECT,
        related_name="creatures",
        help_text="The substance carried.",
    )
    amount = models.PositiveIntegerField(
        help_text="The Primum a slain creature of this kind holds.",
    )

    objects = CreaturePrimumManager()

    class NaturalKeyConfig:
        fields = ["creature_template", "substance"]
        dependencies = ["arxii.CreatureTemplate", _SUBSTANCE_MODEL]

    class Meta:
        verbose_name = "Creature primum"
        verbose_name_plural = "Creature primum"
        constraints = [
            models.UniqueConstraint(
                fields=["creature_template", "substance"],
                name="magic_creatureprimum_template_substance_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.substance} in {self.creature_template_id}"


class PrimumCallUp(SharedMemoryModel):
    """A caster raising a place's Primum of a substance by one step (#5125).

    A call-up belongs to the caster, or to the scene when it is not tied to one caster, and
    vanishes when the caster leaves, logs out, or the scene ends. It is never harvestable.
    """

    room_profile = models.ForeignKey(
        _ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="primum_call_ups",
        help_text="The place the Primum was called up in.",
    )
    substance = models.ForeignKey(
        _SUBSTANCE_MODEL,
        on_delete=models.CASCADE,
        related_name="call_ups",
        help_text="The substance called up.",
    )
    amount_added = models.PositiveIntegerField(
        help_text="The Primum the call-up added to the place.",
    )
    caster = models.ForeignKey(
        _CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="primum_call_ups",
        help_text="The caster who called it up. Set exactly one of caster and scene.",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="primum_call_ups",
        help_text="The scene the call-up lasts for. Set exactly one of caster and scene.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(caster__isnull=False) & Q(scene__isnull=True))
                    | (Q(caster__isnull=True) & Q(scene__isnull=False))
                ),
                name="magic_primumcallup_one_owner",
            ),
            models.UniqueConstraint(
                fields=["room_profile", "substance", "caster"],
                condition=Q(caster__isnull=False),
                name="magic_primumcallup_caster_unique",
            ),
            models.UniqueConstraint(
                fields=["room_profile", "substance", "scene"],
                condition=Q(scene__isnull=False),
                name="magic_primumcallup_scene_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"Call-up of {self.substance_id} in {self.room_profile_id}"


class PrimumSighting(SharedMemoryModel):
    """A character having perceived a substance's Primum in a place (#5125)."""

    character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="primum_sightings",
        help_text="The character who perceived it.",
    )
    room_profile = models.ForeignKey(
        _ROOM_PROFILE_MODEL,
        on_delete=models.CASCADE,
        related_name="primum_sightings",
        help_text="The place it was perceived in.",
    )
    substance = models.ForeignKey(
        _SUBSTANCE_MODEL,
        on_delete=models.CASCADE,
        related_name="sightings",
        help_text="The substance perceived.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "room_profile", "substance"],
                name="magic_primumsighting_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet_id} sensed {self.substance_id} in {self.room_profile_id}"

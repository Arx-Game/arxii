"""Substances and Primum tuning (#5125).

A *substance* is what a major gift works through: fire, ice, shadow. It is a row of its own so
a place, a creature, an item and a gift can all name it, and so no rule ever matches a gift by
name. A substance may name the room condition it grows along (``stat_key`` and ``direction``);
Primum, the raw stuff of a substance, is held by places, creatures and items (see ``primum.py``
and ``world.items.primum_models``).

The tuning here is staff-owned: how many steps of Primum there are and what each is worth
(``PrimumStep``), how summed points become power (``SubstancePowerStep``), and what a rolled
harvest outcome yields (``HarvestOutcome``). Code compares ranks and rows, never names.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.checks.models import OutcomeTierAward
from world.contributors.models import CreditedContent
from world.locations.constants import STAT_CLAMPS, STAT_DEFAULTS, StatKey
from world.magic.constants import SubstanceDirection, SubstanceRelationKind

_SUBSTANCE_MODEL = "arxii.Substance"
_QUALITY_TIER_MODEL = "arxii.QualityTier"


class SubstanceManager(NaturalKeyManager):
    """Manager for Substance with natural key support."""


class Substance(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """One substance a gift can work through, such as fire, ice or shadow (#5125).

    The room condition is optional: a substance with none has no ordinary room reading, so a
    caster is only ever stronger where Primum of it is held. A substance with one grows with
    that condition (shadow with falling light, fire with rising heat).
    """

    name = models.CharField(
        max_length=60,
        unique=True,
        help_text='What lines and cards call it ("fire", "ice", "shadow").',
    )
    stat_key = models.CharField(
        verbose_name="Which room condition feeds it",
        max_length=20,
        choices=StatKey.choices,
        blank=True,
        help_text=(
            "The room condition this substance grows along, such as Lighting for shadow. "
            "Leave blank, with the direction, if no room condition feeds it."
        ),
    )
    direction = models.CharField(
        verbose_name="Stronger when it is",
        max_length=10,
        choices=SubstanceDirection.choices,
        blank=True,
        help_text=(
            "Shadow is stronger when lighting is lower (darker). Water, wind and fire are "
            "stronger when wet, wind and heat are higher. Blank when no room condition "
            "feeds it."
        ),
    )
    property = models.ForeignKey(
        "arxii.Property",
        verbose_name="Property new techniques start with",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substances",
        help_text=(
            "The property a new technique on a gift of this substance starts with ticked, "
            "such as 'shadow'. Only a convenience: untick it on any technique where it does "
            "not belong, and nothing reads it in play."
        ),
    )

    objects = SubstanceManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=((Q(stat_key="") & Q(direction="")) | (~Q(stat_key="") & ~Q(direction=""))),
                name="magic_substance_condition_and_direction_together",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if bool(self.stat_key) != bool(self.direction):
            blank_field = "direction" if self.stat_key else "stat_key"
            errors[blank_field] = (
                "Set the room condition and which way it grows together, or leave both blank."
            )
        elif self.stat_key and self.direction == SubstanceDirection.FALLING:
            low, _high = STAT_CLAMPS[StatKey(self.stat_key)]
            if STAT_DEFAULTS[StatKey(self.stat_key)] - low <= 0:
                errors["direction"] = (
                    "This room condition cannot go below an ordinary room, so a substance "
                    "cannot be stronger when it is lower. Use Lighting for shadow, or pick "
                    "Higher."
                )
        if errors:
            raise ValidationError(errors)


class SubstanceRelationManager(NaturalKeyManager):
    """Manager for SubstanceRelation with natural key support."""


class SubstanceRelation(NaturalKeyMixin, SharedMemoryModel):
    """How two substances stand to one another, related or opposed (#5125).

    The pair is stored once, lower substance id first, so a relation reads the same from either
    side and a pair can never hold two rows. A pair with no row has no standing, and relations
    never chain.
    """

    substance_a = models.ForeignKey(
        _SUBSTANCE_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="One of the two substances. The pair is saved in id order.",
    )
    substance_b = models.ForeignKey(
        _SUBSTANCE_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The other substance.",
    )
    kind = models.CharField(
        max_length=10,
        choices=SubstanceRelationKind.choices,
        help_text=(
            "Related: a caster of one gets a share of the other's benefit. Opposed: the "
            "other works against the caster's own."
        ),
    )

    objects = SubstanceRelationManager()

    class NaturalKeyConfig:
        fields = ["substance_a", "substance_b"]
        dependencies = [_SUBSTANCE_MODEL]

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=Q(substance_a__lt=F("substance_b")),
                name="magic_substancerelation_pair_in_order",
            ),
            models.UniqueConstraint(
                fields=["substance_a", "substance_b"],
                name="magic_substancerelation_pair_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.substance_a} {self.kind} {self.substance_b}"

    def _put_pair_in_order(self) -> None:
        """Swap the two sides so the lower substance id comes first."""
        if (
            self.substance_a_id is not None
            and self.substance_b_id is not None
            and self.substance_a_id > self.substance_b_id
        ):
            self.substance_a_id, self.substance_b_id = self.substance_b_id, self.substance_a_id

    def clean(self) -> None:
        super().clean()
        if self.substance_a_id is not None and self.substance_a_id == self.substance_b_id:
            msg = "A substance cannot stand in relation to itself."
            raise ValidationError({"substance_b": msg})
        self._put_pair_in_order()

    def save(self, *args, **kwargs) -> None:
        self._put_pair_in_order()
        super().save(*args, **kwargs)


class PrimumStepManager(NaturalKeyManager):
    """Manager for PrimumStep with natural key support."""


class PrimumStep(NaturalKeyMixin, SharedMemoryModel):
    """One named step of how much Primum there is, and what it is worth (#5125).

    Modelled on ``KindledStrengthTier``: code compares only ``rank``; ``name`` is the word
    players read and staff may rename it. A place or creature holding at least ``starts_at``
    Primum reads as the highest step it reaches; the step is worth ``points`` toward a caster's
    power. ``item_quality`` ties a step to the quality tier a crafted Primum item carries, so a
    crafted item can be read back as a step.
    """

    rank = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
        help_text="The order of the step (1, 2, 3...). Code knows only this.",
    )
    name = models.CharField(
        max_length=50, unique=True, help_text="The word players read for this step."
    )
    starts_at = models.PositiveIntegerField(
        unique=True,
        help_text="The least Primum a place or creature holds to read as this step.",
    )
    points = models.PositiveSmallIntegerField(
        help_text="The power points a source at this step is worth to a caster.",
    )
    item_quality = models.OneToOneField(
        _QUALITY_TIER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primum_step",
        help_text=(
            "The quality tier a crafted Primum item carries at this step. Blank if no "
            "crafted item reads as this step."
        ),
    )

    objects = PrimumStepManager()

    class NaturalKeyConfig:
        fields = ["rank"]

    class Meta:
        ordering = ["rank"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.rank is None or self.starts_at is None:
            return
        others = type(self).objects.exclude(pk=self.pk)
        if any(o.rank < self.rank and o.starts_at >= self.starts_at for o in others):
            raise ValidationError({"starts_at": "A higher step must start at more Primum."})
        if any(o.rank > self.rank and o.starts_at <= self.starts_at for o in others):
            raise ValidationError({"starts_at": "A lower step must start at less Primum."})


class SubstancePowerStepManager(NaturalKeyManager):
    """Manager for SubstancePowerStep with natural key support."""


class SubstancePowerStep(NaturalKeyMixin, SharedMemoryModel):
    """The power a caster's summed Primum points reach (#5125).

    The row with the highest ``points_reached`` at or below the caster's points wins, so each
    extra source adds less than the one before. A caster below every row gets no power.
    """

    points_reached = models.PositiveIntegerField(
        unique=True,
        help_text="The summed Primum points a caster must reach for this much power.",
    )
    power = models.PositiveSmallIntegerField(
        help_text="The power a caster who reaches these points gains.",
    )

    objects = SubstancePowerStepManager()

    class NaturalKeyConfig:
        fields = ["points_reached"]

    class Meta:
        ordering = ["points_reached"]

    def __str__(self) -> str:
        return f"{self.points_reached} points give {self.power} power"


class HarvestOutcome(OutcomeTierAward):
    """What one rolled outcome of a Primum harvest yields (#5125).

    Reuses the per-outcome award base: ``outcome_tier`` is the rolled ``CheckOutcome``. A
    rolled outcome with no row yields nothing, which is a content gap, not a crash.
    """

    amount_taken = models.PositiveIntegerField(
        help_text="Primum taken out of the place or creature at this outcome.",
    )
    quantity = models.PositiveSmallIntegerField(
        help_text="How many Primum items the harvester receives at this outcome.",
    )
    quality_tier = models.ForeignKey(
        _QUALITY_TIER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The quality tier of the Primum items received.",
    )

    def __str__(self) -> str:
        return f"{self.outcome_tier}: {self.quantity} x {self.quality_tier}"

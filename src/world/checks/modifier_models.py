"""Modifier size fraction, value override, level baseline and taper rows (#4551, #4594, #5093).

A modifier carries a level and a size. These tables, each keyed by a
``ModifierLane`` column, turn that pair into a number and decide how piles of
modifiers add up:

* ``ModifierSizeFraction`` - how much of one level's width a modifier of each size is
  worth (#5093). A modifier's value is its size's fraction times the lane's level width.
* ``ModifierValue`` - an override of that derived value: what a modifier of a given size
  is worth at one exact level, in the lane's own units. Optional; a size and level with
  no row read the derived value.
* ``ModifierLevelBaseline`` - the typical total a character of each level reaches in
  the lane (a check total on a check in their field). One level's width is the step
  between two rows, and on the check lane the rows are the rank ladder.
* ``LevelTier`` - a bonus in check points a character gains on reaching a tier's start
  level, so crossing into a new tier is a jump (#5093).
* ``ModifierTaper`` - which source kinds taper in a lane, and how lightly: each
  further modifier of the kind counts ``ratio`` of the one before, never below
  ``floor`` of its own value.

All three are staff-tuned rows with example values in the seed; an empty table
leaves every modifier at its flat authored value and every pile a plain sum.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.checks.constants import (
    SIZED_MODIFIER_LANES,
    ModifierLane,
    ModifierSize,
    ModifierSourceKind,
)

_LANE_HELP = "The kind of quantity this row values (check points, stats, and later lanes)."


def _require_sized_lane(lane: str, row_noun: str) -> None:
    """Refuse a row in a lane that holds only level baselines (pool, cap and rung lanes)."""
    if lane not in SIZED_MODIFIER_LANES:
        label = ModifierLane(lane).label if lane in ModifierLane.values else lane
        msg = f"The {label} lane holds only level baselines, so it has no {row_noun}."
        raise ValidationError({"lane": msg})


class ModifierSizeFraction(SharedMemoryModel):
    """How much of one level's width a modifier of ``size`` is worth in a lane (#5093).

    A modifier's value is ``fraction`` times the lane's level width at the modifier's
    level, rounded half up and never below 1. A Large check buff at 0.5 is half a rank.
    A size with no row in the lane has no derived value (the modifier keeps its flat
    authored value). A vow's size step reads the difference between two sizes' fractions.
    The target's level is never read.
    """

    lane = models.CharField(
        max_length=20,
        choices=ModifierLane.choices,
        default=ModifierLane.CHECK,
        db_default=ModifierLane.CHECK,
        help_text=_LANE_HELP,
    )
    size = models.PositiveSmallIntegerField(
        choices=ModifierSize.choices,
        help_text="The modifier size this fraction values.",
    )
    fraction = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        validators=[MinValueValidator(Decimal(0))],
        help_text="The share of one level's width this size is worth (example: 0.500 for "
        "half a level).",
    )

    class Meta:
        ordering = ["lane", "size"]
        constraints = [
            models.UniqueConstraint(
                fields=["lane", "size"],
                name="unique_modifier_size_fraction_per_lane_size",
            ),
        ]
        verbose_name = "Modifier size fraction"
        verbose_name_plural = "Modifier size fractions"

    def __str__(self) -> str:
        size_label = ModifierSize(self.size).label
        return f"{self.get_lane_display()}: {size_label} = {self.fraction} of a level"

    def clean(self) -> None:
        super().clean()
        _require_sized_lane(self.lane, "size fractions")


class ModifierValue(SharedMemoryModel):
    """An override of a derived modifier value: a modifier of ``size`` at exactly
    ``level`` is worth ``value`` in the lane's units, whatever its size fraction says.

    Optional (#5093): without a row the value is the size's fraction times the level's
    width. A row covers only its own level, never the levels above it. The value is a
    magnitude; the authored modifier's sign says whether it is a bonus or a penalty. The
    target's level is never read.
    """

    lane = models.CharField(
        max_length=20,
        choices=ModifierLane.choices,
        default=ModifierLane.CHECK,
        db_default=ModifierLane.CHECK,
        help_text=_LANE_HELP,
    )
    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="The modifier level this override applies to.",
    )
    size = models.PositiveSmallIntegerField(
        choices=ModifierSize.choices,
        help_text="The modifier size this row values.",
    )
    value = models.PositiveIntegerField(
        help_text="What the modifier is worth, in the lane's units (check points for the "
        "check lane, stat points as a sheet shows them for the stat lane). A "
        "magnitude: a debuff's authored row supplies the minus sign.",
    )

    class Meta:
        ordering = ["lane", "size", "level"]
        constraints = [
            models.UniqueConstraint(
                fields=["lane", "level", "size"],
                name="unique_modifier_value_per_lane_level_size",
            ),
        ]
        verbose_name = "Modifier value"
        verbose_name_plural = "Modifier value table"

    def __str__(self) -> str:
        size_label = ModifierSize(self.size).label
        return f"{self.get_lane_display()}: {size_label} at level {self.level} = {self.value}"

    def clean(self) -> None:
        super().clean()
        _require_sized_lane(self.lane, "value overrides")


class ModifierLevelBaseline(SharedMemoryModel):
    """The typical total a character of ``level`` reaches in a lane.

    For the check lane, the check total of a character of that level on a check in
    their field. Staff read the value table against it: a value as a share of the
    baseline, and on the check lane as the share of the rank band the baseline sits
    in. Sparse rows read the same way as ``ModifierValue``.
    """

    lane = models.CharField(
        max_length=20,
        choices=ModifierLane.choices,
        default=ModifierLane.CHECK,
        db_default=ModifierLane.CHECK,
        help_text=_LANE_HELP,
    )
    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="The character level this baseline starts at.",
    )
    baseline = models.PositiveIntegerField(
        help_text="The typical total at this level, in the lane's units.",
    )

    class Meta:
        ordering = ["lane", "level"]
        constraints = [
            models.UniqueConstraint(
                fields=["lane", "level"],
                name="unique_modifier_level_baseline_per_lane_level",
            ),
        ]
        verbose_name = "Modifier level baseline"
        verbose_name_plural = "Modifier level baselines"

    def __str__(self) -> str:
        return f"{self.get_lane_display()}: level {self.level} baseline {self.baseline}"


class LevelTier(SharedMemoryModel):
    """A tier of levels that starts with a jump in power (#5093).

    A level's strength is its CHECK baseline plus the ``bonus_points`` of every tier that
    starts at or below it, so going from the last level of one tier to the first of the next
    is worth far more than any step inside a tier. The bonus counts in full: it is added to a
    character's level term, an NPC's opposition and a staff-set difficulty level, never
    multiplied by the level share. It does not change a level's width, so buff sizes and the
    vow step stay the same inside a tier. A database with no rows has no tiers and no jump.
    """

    start_level = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
        help_text="The first level of this tier.",
    )
    bonus_points = models.PositiveIntegerField(
        help_text="Check points added to every level from the tier's start level up, in full. "
        "At the seeded 8-point level width, 24 points is three ranks.",
    )

    class Meta:
        ordering = ["start_level"]
        verbose_name = "Level tier"
        verbose_name_plural = "Level tiers"

    def __str__(self) -> str:
        return f"Tier from level {self.start_level}: +{self.bonus_points} points"


class ModifierTaper(SharedMemoryModel):
    """The light taper for one source kind in one lane.

    Within a roll, the modifiers of this kind on this lane form two piles (bonuses,
    penalties). Each pile counts largest first: the first at full value, each next one
    at ``ratio`` of the weight before it, never below ``floor``. A kind with no row
    does not taper. The character's own standing (rollmod, effort, fatigue, strain,
    soulfray, capabilities) gets no row, and a vow's step is never tapered.
    """

    lane = models.CharField(
        max_length=20,
        choices=ModifierLane.choices,
        default=ModifierLane.CHECK,
        db_default=ModifierLane.CHECK,
        help_text=_LANE_HELP,
    )
    source_kind = models.CharField(
        max_length=20,
        choices=ModifierSourceKind.choices,
        help_text="The source kind whose piles taper in this lane.",
    )
    ratio = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(1))],
        help_text="Each further modifier counts this share of the one before it "
        "(example: 0.8750 for 7/8).",
    )
    floor = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(1))],
        help_text="No modifier counts less than this share of its own value "
        "(example: 0.6667 for 2/3).",
    )

    class Meta:
        ordering = ["lane", "source_kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["lane", "source_kind"],
                name="unique_modifier_taper_per_lane_kind",
            ),
        ]
        verbose_name = "Modifier taper"
        verbose_name_plural = "Modifier tapers"

    def __str__(self) -> str:
        return (
            f"{self.get_lane_display()}: {self.get_source_kind_display()} "
            f"x{self.ratio}, floor {self.floor}"
        )

    def clean(self) -> None:
        super().clean()
        _require_sized_lane(self.lane, "tapers")

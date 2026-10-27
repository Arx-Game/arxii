"""Modifier value table, level baseline and taper rows (#4551, #4594).

A modifier carries a level and a size. These three tables, each keyed by a
``ModifierLane`` column, turn that pair into a number and decide how piles of
modifiers add up:

* ``ModifierValue`` - the value table: what a modifier of a given size is worth at a
  given level, in the lane's own units (check points for the check lane).
* ``ModifierLevelBaseline`` - the typical total a character of each level reaches in
  the lane (a check total on a check in their field). Staff read a value against it,
  as a share and, on the check lane, as rank bands.
* ``ModifierTaper`` - which source kinds taper in a lane, and how lightly: each
  further modifier of the kind counts ``ratio`` of the one before, never below
  ``floor`` of its own value.

All three are staff-tuned rows with example values in the seed; an empty table
leaves every modifier at its flat authored value and every pile a plain sum.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.checks.constants import ModifierLane, ModifierSize, ModifierSourceKind

_LANE_HELP = "The kind of quantity this row values (check points, stats, and later lanes)."


class ModifierValue(SharedMemoryModel):
    """One cell of a lane's value table: a modifier of ``size`` at ``level`` is worth
    ``value`` in the lane's units.

    Rows may be sparse: a modifier reads the row at the highest authored level at or
    below its own, so staff can author levels 1, 5, 10 and so on and fill in later. A
    modifier whose level is below every authored row for its size keeps its flat
    authored value. The value is a magnitude; the authored modifier's sign says
    whether it is a bonus or a penalty. The target's level is never read.
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
        help_text="The modifier level this row starts at (it covers higher levels until "
        "the next authored row).",
    )
    size = models.PositiveSmallIntegerField(
        choices=ModifierSize.choices,
        help_text="The modifier size this row values.",
    )
    value = models.PositiveIntegerField(
        help_text="What the modifier is worth, in the lane's units (check points for the "
        "check lane, internal stat units, x10 the shown stat, for the stat lane). A "
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

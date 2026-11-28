"""Staff tables for the bonus resonance check (#5308).

Every earned resonance gain rolls one bonus check per affinity it pays, and every pull and
kindled cast rolls one for its worth. ``ResonanceGainConfig.bonus_check_type`` names the
check; these two tables say what the result is worth and which stat a source's roll uses
when the act itself did not roll one.
"""

from __future__ import annotations

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.checks.models import OutcomeTierAward
from world.magic.constants import GainSource


class ResonanceCheckAward(OutcomeTierAward):
    """What the bonus resonance check is worth at one roll result.

    A result with no row adds nothing to a gain and leaves a pull worth 100 percent.
    """

    gain_bonus_percent = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "How much this result grows an earned resonance gain, as a percentage of the "
            "amount. 0 leaves it as is, 50 adds half again."
        ),
    )
    spend_worth_percent = models.PositiveSmallIntegerField(
        default=100,
        help_text=(
            "How much a pull or kindled cast is worth at this result, as a percentage. 100 "
            "is full strength, 130 is a third as much again. The affinity's own floor still "
            "applies."
        ),
    )

    class Meta(OutcomeTierAward.Meta):
        verbose_name = "Resonance check award"

    def __str__(self) -> str:
        return (
            f"{self.outcome_tier.name}: gain +{self.gain_bonus_percent}%, "
            f"worth {self.spend_worth_percent}%"
        )


class ResonanceGainSourceStat(SharedMemoryModel):
    """The stat a source's bonus check rolls when the act did not roll one of its own.

    An act that rolled (a Strike, a cast, a worship rite) passes the stat of that roll. A
    gain that comes from no roll, such as a weekly endorsement or a mission reward, rolls
    this stat instead. A source with no row rolls the bonus check type's own stat.
    """

    source = models.CharField(
        max_length=32,
        choices=GainSource.choices,
        unique=True,
        help_text="The kind of gain this stat is rolled for.",
    )
    stat = models.ForeignKey(
        "arxii.Trait",
        on_delete=models.PROTECT,
        limit_choices_to={"trait_type": "stat"},
        related_name="+",
        help_text=(
            "The stat the bonus check rolls for this kind of gain when the act rolled no "
            "stat of its own."
        ),
    )

    class Meta:
        verbose_name = "Resonance gain source stat"
        ordering = ["source"]

    def __str__(self) -> str:
        return self.get_source_display()

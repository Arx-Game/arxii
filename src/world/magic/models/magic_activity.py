"""MagicActivitySkill: which skills each kind of magical roll adds (#4450).

A magical roll keeps its own check type as the base and adds the skills staff map to
its activity here. No skill is named in code; an activity with no row adds nothing.
"""

from decimal import Decimal

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.magic.constants import MagicActivity


class MagicActivitySkill(SharedMemoryModel):
    """One skill staff add to every roll of one magical activity.

    An activity maps to several skills, each with a weight. The same skill may serve
    several activities, but only once per activity.
    """

    activity = models.CharField(
        max_length=40,
        choices=MagicActivity.choices,
        db_index=True,
        help_text="The kind of magical roll this skill is added to.",
    )
    skill = models.ForeignKey(
        "arxii.Skill",
        on_delete=models.PROTECT,
        related_name="magic_activity_rows",
        help_text="The skill added to every roll of this activity.",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Weight multiplies the skill's value before it becomes points. "
        "1.00 is the default.",
    )

    class Meta:
        ordering = ["activity", "skill"]
        verbose_name = "Magic Activity Skill"
        verbose_name_plural = "Magic Activity Skills"
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "skill"],
                name="unique_magic_activity_skill",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_activity_display()}: {self.skill} x{self.weight}"

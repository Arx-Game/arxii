"""Level Stat Point models (#3001).

Every class level past the first grants one spendable stat point. Like
Maturation Points (#2756), the points live in the levels themselves — the
balance is derived (``level - 1`` minus active spends), never stored, so a
level reversal deactivates the affected spends and re-leveling reactivates
them (``world.progression.services.stat_points.sync_level_stat_point_spends``).
Caps reuse the authored ``MaturationStatCap`` table (one cap per stage band;
a stat's ceiling is a property of the stage, not of which point pool paid
for the raise).
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class LevelStatPointSpend(SharedMemoryModel):
    """One spent Level Stat Point: a class level converted into +1 stat.

    ``level_granted`` is the level whose point funded this spend (2..N —
    level 1 is the CG baseline and grants no point). ``is_active`` mirrors
    ``level_granted <= current level`` and is maintained exclusively by
    ``sync_level_stat_point_spends`` (explicit service calls, no signals;
    ADR-0009).
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="level_stat_point_spends",
    )
    trait = models.ForeignKey(
        "arxii.Trait",
        on_delete=models.PROTECT,
        related_name="level_stat_point_spends",
        help_text="The stat this point raised.",
    )
    level_granted = models.PositiveSmallIntegerField(
        help_text="The class level that funded this point (2, 3, ...).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="False while the character's level sits below level_granted.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Level stat point spend"
        verbose_name_plural = "Level stat point spends"
        ordering = ["character_sheet", "level_granted"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "level_granted"],
                name="unique_stat_point_per_level",
            ),
        ]

    def __str__(self) -> str:
        state = "active" if self.is_active else "dormant"
        return f"{self.character_sheet} level {self.level_granted} -> {self.trait} ({state})"

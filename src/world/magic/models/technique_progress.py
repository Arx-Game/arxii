"""Technique learning progress meter models (#2711).

TechniqueProgress: per-(character × technique) development meter. The learner
invests AP across multiple sessions to fill the meter; the technique is
acquired when points_accumulated >= total_required.

TechniqueProgressWeekly: per-week cap tracker, mirroring WeeklySkillUsage.
Prevents blowing all AP in one session.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.achievements.constants import AccessChangeSource


class TechniqueProgress(SharedMemoryModel):
    """Per-(character × technique) development meter (#2711).

    Created by ``charge_and_learn`` (teaching/TRAIN) or ``learn_technique``
    (item/ritual grants) when ``ap_cost > 0``. The learner fills it via
    ``contribute_to_technique_progress`` in subsequent sessions. When
    ``points_accumulated >= total_required``, the meter is consumed and a
    ``CharacterTechnique`` is minted.

    ``total_required`` is snapshotted at creation so later authoring/config
    changes don't retroactively alter in-progress meters.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="technique_progress",
    )
    technique = models.ForeignKey(
        "arxii.Technique",
        on_delete=models.PROTECT,
        related_name="progress_records",
    )
    points_accumulated = models.PositiveIntegerField(
        default=0,
        help_text="Development points accumulated toward the technique.",
    )
    total_required = models.PositiveIntegerField(
        help_text="Total development points required, snapshotted at creation.",
    )
    teacher_tenure = models.ForeignKey(
        "arxii.RosterTenure",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="technique_progress_taught",
        help_text="Teacher RosterTenure when applicable; null for self-directed acquisition.",
    )
    source = models.CharField(
        max_length=30,
        choices=AccessChangeSource.choices,
        help_text="Provenance: how this meter was created.",
    )
    is_cross_path = models.BooleanField(
        default=False,
        help_text=(
            "True when the teacher's Path.style differed from the learner's at "
            "creation. Drives the effective weekly cap."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "technique"],
                name="unique_technique_progress_per_character",
            ),
        ]
        ordering = ["character_sheet", "technique"]
        verbose_name = "Technique Progress"
        verbose_name_plural = "Technique Progress"

    def __str__(self) -> str:
        return (
            f"{self.character_sheet}: {self.points_accumulated}/{self.total_required} "
            f"toward {self.technique.name if self.technique_id else '—'}"
        )


class TechniqueProgressWeekly(SharedMemoryModel):
    """Per-week cap tracker for technique training (#2711).

    Mirrors ``WeeklySkillUsage``. One row per (character, technique, game_week).
    Prevents a learner from blowing all AP in one session.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="technique_progress_weekly",
    )
    technique = models.ForeignKey(
        "arxii.Technique",
        on_delete=models.CASCADE,
        related_name="progress_weekly",
    )
    game_week = models.ForeignKey(
        "arxii.GameWeek",
        on_delete=models.CASCADE,
        related_name="technique_progress_weekly",
    )
    points_contributed = models.PositiveIntegerField(
        default=0,
        help_text="Meter-progress points contributed this week.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "technique", "game_week"],
                name="unique_technique_progress_weekly",
            ),
        ]
        ordering = ["character_sheet", "technique", "game_week"]
        verbose_name = "Technique Progress Weekly"
        verbose_name_plural = "Technique Progress Weekly"

    def __str__(self) -> str:
        return (
            f"{self.character_sheet} → {self.technique.name if self.technique_id else '—'}: "
            f"{self.points_contributed} this week"
        )

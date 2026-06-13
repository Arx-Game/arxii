from typing import ClassVar

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.classes.models import PathStage
from world.magic.constants import MagicMilestoneKind


class MagicProgressionMilestone(SharedMemoryModel):
    """Authored join: which magic feature-kind becomes available at which PathStage,
    and which CodexEntry documents it (drives display + discovery-gating)."""

    stage = models.PositiveSmallIntegerField(choices=PathStage.choices)
    kind = models.CharField(max_length=32, choices=MagicMilestoneKind.choices)
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="progression_milestones",
        help_text="Documents this milestone; supplies title/summary and gates discovery.",
    )
    route_name = models.CharField(
        max_length=64,
        blank=True,
        help_text="Frontend route the milestone CTA targets (e.g. '/threads').",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar[list[str]] = ["stage", "sort_order", "kind"]
        constraints: ClassVar[list] = [
            models.UniqueConstraint(
                fields=["stage", "kind"], name="uniq_milestone_stage_kind"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_stage_display()} — {self.get_kind_display()}"

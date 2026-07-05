"""Thread crossing threshold model (#1885).

Authored catalog rows that gate thread-level advancement across PathStage
crossing levels (3, 6, 11, 16, 21). Mirrors ``ClassLevelUnlock``'s shape but
keyed on ``(target_kind, level)`` so a level-3 GIFT crossing can require
different things than a level-3 COVENANT_ROLE crossing.

Requirements FK to a ``ThreadCrossingThreshold`` via the polymorphic
``thread_crossing_threshold`` field on ``AbstractUnlockRequirement`` (the
generalized base formerly known as ``AbstractClassLevelRequirement``).

See ADR-0090 for the boundary choice and the ADR-0016 (shared base) vs
ADR-0089 (sibling-per-domain) justification.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.classes.models import PathStage
from world.classes.services import stage_for_level
from world.magic.constants import TargetKind


class ThreadCrossingThreshold(SharedMemoryModel):
    """Authored gate at a thread-level PathStage crossing.

    One row per ``(target_kind, level)`` where ``level`` is a crossing level
    (i.e. ``stage_for_level(level) != stage_for_level(level - 1)``). When a
    thread's imbuing loop would advance to ``level``, the loop checks for a
    matching threshold row; if one exists, its requirements must be met before
    the level crosses.

    Fail-open: if no row exists for ``(target_kind, level)``, no gate fires
    (mirrors Durance's ``ClassLevelUnlock.DoesNotExist`` → no gate).
    """

    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        help_text="Thread kind this crossing gate applies to.",
    )
    level = models.PositiveSmallIntegerField(
        help_text=(
            "Internal thread-level scale crossing (3, 6, 11, 16, 21...). "
            "Must be a level where stage_for_level changes."
        ),
    )
    stage = models.PositiveSmallIntegerField(
        choices=PathStage.choices,
        help_text=(
            "Derived PathStage at this level (denormalized for admin "
            "clarity / filtering). Must match stage_for_level(level)."
        ),
    )

    class Meta:
        unique_together: list[str] = ["target_kind", "level"]
        ordering: list[str] = ["target_kind", "level"]

    def clean(self) -> None:
        """Validate that level is a crossing and stage matches."""
        super().clean()
        if self.level < 1:
            msg = "Level must be at least 1."
            raise ValidationError(msg)

        current_stage = stage_for_level(self.level)
        prev_stage = stage_for_level(self.level - 1)

        if current_stage == prev_stage:
            msg = (
                f"Level {self.level} is not a PathStage crossing "
                f"(stage {current_stage} == stage {prev_stage} at level {self.level - 1}). "
                "Crossing levels are 3, 6, 11, 16, 21."
            )
            raise ValidationError(msg)

        if self.stage != current_stage:
            msg = (
                f"Stage field ({self.stage}) does not match stage_for_level({self.level}) "
                f"= {current_stage}."
            )
            raise ValidationError(msg)

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        """Auto-populate stage from stage_for_level if not set."""
        if self.stage is None or self.stage == 0:
            self.stage = stage_for_level(self.level)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.target_kind} crossing at level {self.level}"

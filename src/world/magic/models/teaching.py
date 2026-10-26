"""Tradition teaching-fit tuning (slice 2 of #4659)."""

from django.core.exceptions import ValidationError
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel


class TraditionTeachingConfig(SharedMemoryModel):
    """Singleton tuning for how a Tradition's fit helps a student.

    Lazy-created by ``get_teaching_config()`` in services/teaching_fit.py.
    """

    objects = ArxSharedMemoryManager()

    gift_fit_training_bonus = models.PositiveSmallIntegerField(
        default=10,
        verbose_name="Gift fit training bonus",
        help_text=(
            "Added to a student's magical training when the Tradition favors their "
            "Major Gift. Only given to a student with some training."
        ),
    )
    affinity_fit_training_bonus = models.PositiveSmallIntegerField(
        default=10,
        verbose_name="Affinity fit training bonus",
        help_text=(
            "Added when the Tradition favors the affinity of the student's Gift "
            "resonance. Only given to a student with some training."
        ),
    )
    course_ease_gift_fit = models.PositiveSmallIntegerField(
        default=2,
        verbose_name="Course ease, Gift fit",
        help_text="Lowers the session check's difficulty.",
    )
    course_ease_affinity_fit = models.PositiveSmallIntegerField(
        default=2,
        verbose_name="Course ease, affinity fit",
        help_text="Lowers the session check's difficulty.",
    )

    class Meta:
        verbose_name = "Tradition teaching config"
        verbose_name_plural = "Tradition teaching config"

    def __str__(self) -> str:
        return "Tradition teaching config"

    def clean(self) -> None:
        from world.skills.models import SkillPointBudget  # noqa: PLC0415

        step = SkillPointBudget.get_active_budget().points_per_tier
        errors = {}
        for field in ("gift_fit_training_bonus", "affinity_fit_training_bonus"):
            if getattr(self, field) % step:
                errors[field] = f"Must be a multiple of {step} (one training step)."
        if errors:
            raise ValidationError(errors)

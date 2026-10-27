"""DriftConfig: the staff-tunable singleton for carried drift and the focus contest (#4732).

A character carrying drift toward an affinity other than her aura's dominant one
is contested once the drift passes a threshold. Every number that decides that
lives here, so staff retune it in the admin rather than in code.
"""

from django.core.validators import MinValueValidator
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel


class DriftConfig(SharedMemoryModel):
    """Singleton (pk=1) of thresholds and the focus roll for carried drift.

    The threshold is ``max(threshold_floor, threshold_percent of the dominant
    affinity's balance)``; each ``severity_step`` drift points past it is one
    step of severity on the conflict condition.

    Access via ``get_drift_config()`` in ``world.magic.services.drift``.
    """

    objects = ArxSharedMemoryManager()

    threshold_percent = models.PositiveSmallIntegerField(
        default=50,
        help_text="Carried drift must pass this percent of the dominant affinity's balance.",
    )
    threshold_floor = models.PositiveIntegerField(
        default=20,
        help_text="The threshold never falls below this many drift points.",
    )
    severity_step = models.PositiveIntegerField(
        default=20,
        validators=[MinValueValidator(1)],
        help_text="Drift points past the threshold that add one step of severity.",
    )
    off_aura_pull_steps = models.PositiveSmallIntegerField(
        default=1,
        help_text="Severity steps added when the working affinity is not the aura's dominant one.",
    )
    focus_base_difficulty = models.PositiveSmallIntegerField(
        default=10,
        help_text="Difficulty of the focus roll before any severity steps.",
    )
    focus_difficulty_per_step = models.PositiveSmallIntegerField(
        default=2,
        help_text="Difficulty added to the focus roll per severity step.",
    )
    focus_check_type = models.ForeignKey(
        "arxii.CheckType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The check a character rolls to keep her focus against carried drift.",
    )
    conflict_condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The condition applied when a character fails to keep her focus.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="drift_config_edits",
    )

    def __str__(self) -> str:
        return f"DriftConfig(pk={self.pk})"

"""ActionTemplate and ActionTemplateGate models."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import ActionTargetType, GateRole, Pipeline
from actions.models.consequence_pools import ConsequencePool
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class ActionTemplate(NaturalKeyMixin, SharedMemoryModel):
    """Data-driven resolution specification for authored actions.

    Defines what happens when a character performs a data-driven action:
    which check type to use, which consequence pool to resolve, and
    what pipeline pattern to follow.
    """

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable name (e.g., 'Fire Bolt', 'Pick Lock').",
    )
    description = models.TextField(
        blank=True,
        help_text="Narrative description of this action.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="action_templates",
        help_text="Check type for the main resolution step.",
    )
    consequence_pool = models.ForeignKey(
        ConsequencePool,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_templates",
        help_text="Consequence pool for the main resolution step. Null = check-only action.",
    )
    pipeline = models.CharField(
        max_length=20,
        choices=Pipeline.choices,
        default=Pipeline.SINGLE,
        help_text="Resolution pattern: SINGLE (one check) or GATED (prerequisite checks first).",
    )
    target_type = models.CharField(
        max_length=20,
        choices=ActionTargetType.choices,
        default=ActionTargetType.SELF,
        help_text="What kind of target this action operates on.",
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Frontend icon identifier.",
    )
    category = models.CharField(
        max_length=50,
        help_text="Grouping category (e.g., 'magic', 'combat', 'exploration').",
    )

    class Meta:
        verbose_name = "Action Template"
        verbose_name_plural = "Action Templates"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.pk is None:
            return  # Can't validate gate count before first save
        gate_count = self.gates.count()
        if self.pipeline == Pipeline.SINGLE and gate_count > 0:
            raise ValidationError({"pipeline": "SINGLE pipeline cannot have gates."})
        if self.pipeline == Pipeline.GATED and gate_count == 0:
            raise ValidationError({"pipeline": "GATED pipeline requires at least one gate."})


class ActionTemplateGate(SharedMemoryModel):
    """Optional extra check step that gates an ActionTemplate's main resolution."""

    action_template = models.ForeignKey(
        ActionTemplate,
        on_delete=models.CASCADE,
        related_name="gates",
    )
    gate_role = models.CharField(
        max_length=20,
        choices=GateRole.choices,
        default=GateRole.ACTIVATION,
        help_text="Semantic role of this gate.",
    )
    step_order = models.IntegerField(
        default=0,
        help_text="Execution order (lower = earlier). Negative = before main step.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="action_template_gates",
        help_text="Check type for this gate.",
    )
    consequence_pool = models.ForeignKey(
        ConsequencePool,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_template_gates",
        help_text="Gate-specific consequences. Null = pure go/no-go check.",
    )
    failure_aborts = models.BooleanField(
        default=True,
        help_text="If True, failing this gate stops the pipeline.",
    )

    class Meta:
        verbose_name = "Action Template Gate"
        verbose_name_plural = "Action Template Gates"
        ordering = ["step_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["action_template", "gate_role"],
                name="unique_template_gate_role",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action_template.name} - {self.get_gate_role_display()}"

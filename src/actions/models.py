"""Action enhancement model — database entities that modify base actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import EnhancementSourceType

if TYPE_CHECKING:
    from actions.types import ActionContext


class ActionEnhancement(SharedMemoryModel):
    """A relationship record: "this source modifies this base action in this way."

    The source (a technique, distinction, condition) gates *whether* the
    enhancement activates (via ``should_apply_enhancement``). This model
    owns *what* the enhancement does via ``effect_parameters`` and ``apply()``.

    Exactly one source FK must be non-null, matching ``source_type``.
    """

    base_action_key = models.CharField(max_length=100, db_index=True)
    variant_name = models.CharField(max_length=100)
    # JSONField justified: effect vocabularies vary by enhancement type and no
    # shared schema can cover all combinations. Each enhancement's apply()
    # method interprets its own parameters.
    effect_parameters = models.JSONField(default=dict)
    is_involuntary = models.BooleanField(default=False)

    source_type = models.CharField(
        max_length=20,
        choices=EnhancementSourceType.choices,
    )

    # === Source FKs — exactly one must be non-null, matching source_type ===
    distinction = models.ForeignKey(
        "distinctions.Distinction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="action_enhancements",
    )
    condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="action_enhancements",
    )
    technique = models.ForeignKey(
        "magic.Technique",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="action_enhancements",
    )

    class Meta:
        indexes = [
            models.Index(fields=["base_action_key", "is_involuntary"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="action_enhancement_exactly_one_source",
                condition=(
                    models.Q(
                        source_type=EnhancementSourceType.DISTINCTION,
                        distinction__isnull=False,
                        condition__isnull=True,
                        technique__isnull=True,
                    )
                    | models.Q(
                        source_type=EnhancementSourceType.CONDITION,
                        distinction__isnull=True,
                        condition__isnull=False,
                        technique__isnull=True,
                    )
                    | models.Q(
                        source_type=EnhancementSourceType.TECHNIQUE,
                        distinction__isnull=True,
                        condition__isnull=True,
                        technique__isnull=False,
                    )
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.variant_name} ({self.base_action_key})"

    @property
    def source(self) -> object | None:
        """Return the source model instance based on source_type."""
        if self.source_type == EnhancementSourceType.DISTINCTION:
            return self.distinction
        if self.source_type == EnhancementSourceType.CONDITION:
            return self.condition
        if self.source_type == EnhancementSourceType.TECHNIQUE:
            return self.technique
        return None

    def apply(self, context: ActionContext) -> None:
        """Dispatch all effect configs for this enhancement."""
        from actions.effects import apply_effects  # noqa: PLC0415

        apply_effects(self, context)

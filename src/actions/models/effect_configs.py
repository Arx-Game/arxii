"""Effect config models — FK-backed parameter records for enhancement effects.

Each effect type is a concrete model inheriting from BaseEffectConfig.
An ActionEnhancement can have multiple config rows across different tables,
ordered by execution_order.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import TransformType


class BaseEffectConfig(models.Model):
    """Abstract base for all effect config models.

    Provides the FK back to ActionEnhancement and execution ordering.
    Concrete subclasses add typed fields and FKs specific to their effect type.
    """

    enhancement = models.ForeignKey(
        "actions.ActionEnhancement",
        on_delete=models.CASCADE,
        related_name="%(class)s_configs",
    )
    execution_order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["execution_order"]


class ModifyKwargsConfig(BaseEffectConfig, SharedMemoryModel):
    """Apply a named transform to an action kwarg value.

    Example: transform="uppercase" on kwarg_name="text" uppercases the speech text.
    """

    kwarg_name = models.CharField(max_length=50)
    transform = models.CharField(max_length=20, choices=TransformType.choices)

    class Meta(BaseEffectConfig.Meta):
        pass

    def __str__(self) -> str:
        return f"{self.transform} on {self.kwarg_name}"


class AddModifierConfig(BaseEffectConfig, SharedMemoryModel):
    """Add a key-value modifier to context.modifiers.

    Actions read specific modifier keys during execute(). For example,
    a combat action reads modifiers["check_bonus"].
    """

    modifier_key = models.CharField(max_length=50)
    modifier_value = models.IntegerField()

    class Meta(BaseEffectConfig.Meta):
        pass

    def __str__(self) -> str:
        return f"{self.modifier_key}={self.modifier_value}"


class ConditionOnCheckConfig(BaseEffectConfig, SharedMemoryModel):
    """Apply a condition to the target, gated by a check roll.

    The generic "attempt to put an effect on someone" pattern:
    1. Check immunity (skip if target has immunity_condition)
    2. Roll attacker's check_type vs defender's resistance
    3. On success: apply condition with severity and duration
    4. On failure: optionally apply immunity_condition

    Difficulty resolution:
    - If resistance_check_type is set and the target has traits, compute
      difficulty from the target's weighted trait points.
    - If target_difficulty is set, use it as a fixed fallback (NPCs, missions).
    - If both are set, resistance_check_type takes precedence for real characters.
    """

    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Attacker's check type (weighted trait combination).",
    )
    resistance_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Defender's resistance check type. Null = use target_difficulty.",
    )
    target_difficulty = models.IntegerField(
        null=True,
        blank=True,
        help_text="Fixed difficulty fallback for NPCs/missions.",
    )
    condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Condition to apply on successful check.",
    )
    severity = models.PositiveIntegerField(default=1)
    duration_rounds = models.PositiveIntegerField(null=True, blank=True)
    immunity_condition = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Condition to apply on failed check (short-term immunity).",
    )
    immunity_duration = models.PositiveIntegerField(null=True, blank=True)
    source_description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Narrative label for the condition source (e.g. 'Alluring Whisper').",
    )

    class Meta(BaseEffectConfig.Meta):
        pass

    def __str__(self) -> str:
        return f"{self.condition} via {self.check_type}"

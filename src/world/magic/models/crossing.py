"""Models for thread crossing player choices (generalized, #1990).

When a thread crosses a PathStage threshold (level 3, 6, 11, 16, 21),
the player chooses a resonance-matched aura enhancement from an authored
menu (CrossingOption). The option references an acquisition-agnostic
ConditionTemplate — the buff's effects live on the condition, not on
the option. The choice is recorded as an irreversible receipt
(CrossingChoice) whose payload is read by passive read paths.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import TargetKind


class CrossingOption(SharedMemoryModel):
    """Authored catalog of resonance-matched aura enhancements.

    Staff author one row per (target_kind, resonance, crossing_level, name).
    Each row references a ConditionTemplate (the buff) whose
    ConditionModifierEffect rows define the stat/check modifiers.
    The option is acquisition-agnostic — a buff is a buff.
    """

    target_kind = models.CharField(
        max_length=32,
        choices=TargetKind.choices,
        help_text="Which thread kind this option applies to.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="crossing_options",
    )
    crossing_level = models.PositiveSmallIntegerField(
        help_text="PathStage crossing level (3, 6, 11, 16, 21).",
    )
    name = models.CharField(
        max_length=120,
        help_text="The buff's identity (e.g., 'Smirk of the Spidery Seductress').",
    )
    description = models.TextField(
        blank=True,
        help_text="Staff-authored flavor, examinable by other players.",
    )
    condition_template = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.PROTECT,
        related_name="crossing_options",
        help_text=(
            "The buff being chosen. Its ConditionModifierEffect rows define "
            "the stat/check modifiers. Crossing buffs should only reference "
            "templates carrying ConditionModifierEffect rows."
        ),
    )
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "When a thread skips this crossing (multi-crossing imbue), "
            "this option is picked automatically. One per "
            "(target_kind, resonance, crossing_level)."
        ),
    )
    discovery_achievement = models.ForeignKey(
        "achievements.Achievement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="crossing_options",
    )
    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="crossing_options",
    )

    class Meta:
        unique_together: list[str] = [["target_kind", "resonance", "crossing_level", "name"]]
        ordering: list[str] = ["target_kind", "resonance", "crossing_level", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["target_kind", "resonance", "crossing_level"],
                condition=models.Q(is_default=True),
                name="one_default_crossing_option",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.target_kind} L{self.crossing_level} {self.resonance})"

    def clean(self) -> None:
        """Validate condition_template is set and target_kind is valid."""
        super().clean()
        if not self.condition_template_id:
            msg = "condition_template is required."
            raise ValidationError({"condition_template": msg})


class CrossingChoice(SharedMemoryModel):
    """Irreversible per-thread receipt of a player's crossing choice."""

    thread = models.ForeignKey(
        "magic.Thread",
        on_delete=models.CASCADE,
        related_name="crossing_choices",
    )
    crossing_level = models.PositiveSmallIntegerField(
        help_text="PathStage crossing level (3, 6, 11, 16, 21).",
    )
    option = models.ForeignKey(
        CrossingOption,
        on_delete=models.PROTECT,
        related_name="choices",
    )
    chosen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "crossing_level"],
                name="one_choice_per_thread_per_crossing",
            ),
        ]
        ordering = ["-chosen_at"]

    def __str__(self) -> str:
        return f"Choice(thread={self.thread_id}, L{self.crossing_level}, opt={self.option_id})"


class PendingCrossingOffer(SharedMemoryModel):
    """Poll-able offer created when a thread crosses a threshold.

    Created by the crossing handler; resolved by the player picking an option
    via ResolveCrossingOfferAction (telnet or web). One pending offer per
    thread at a time.
    """

    thread = models.ForeignKey(
        "magic.Thread",
        on_delete=models.CASCADE,
        related_name="pending_crossing_offers",
    )
    crossing_level = models.PositiveSmallIntegerField(
        help_text="PathStage crossing level (3, 6, 11, 16, 21).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["thread"],
                name="one_pending_crossing_per_thread",
            ),
        ]

    def __str__(self) -> str:
        return f"PendingCrossingOffer(thread={self.thread_id}, L{self.crossing_level})"

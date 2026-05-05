"""Soul Tether audit models (Spec B §14.1, §15.1)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class Sineating(SharedMemoryModel):
    """Audit row for a Sineating action (Spec B §7).

    Records both successful and declined offers. ``units_accepted == 0``
    means the Sineater declined.
    """

    sinner_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="sineatings_as_sinner",
    )
    sineater_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="sineatings_as_sineater",
    )
    relationship = models.ForeignKey(
        "relationships.CharacterRelationship",
        on_delete=models.PROTECT,
        related_name="sineatings",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sineatings",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="sineatings",
    )
    units_offered = models.PositiveIntegerField()
    units_accepted = models.PositiveIntegerField(
        help_text="0 = declined; 1..N = accepted that many units.",
    )
    anima_cost = models.PositiveIntegerField(default=0)
    fatigue_cost = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["sinner_sheet", "-created_at"]),
            models.Index(fields=["sineater_sheet", "-created_at"]),
            models.Index(fields=["relationship", "-created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"Sineating({self.sineater_sheet} ate {self.units_accepted}/"
            f"{self.units_offered} from {self.sinner_sheet})"
        )


class SoulTetherRescue(SharedMemoryModel):
    """Audit row for a stage-3+ rescue ritual (Spec B §9, §14.1)."""

    sinner_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="rescues_as_sinner",
    )
    sineater_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="rescues_as_sineater",
    )
    relationship = models.ForeignKey(
        "relationships.CharacterRelationship",
        on_delete=models.PROTECT,
        related_name="rescues",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rescues",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="rescues",
    )
    sinner_stage_at_start = models.PositiveSmallIntegerField()
    sinner_stage_at_end = models.PositiveSmallIntegerField()
    severity_reduced = models.PositiveIntegerField()
    sineater_strain_taken = models.PositiveIntegerField(default=0)
    check_outcome = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["sinner_sheet", "-created_at"]),
            models.Index(fields=["sineater_sheet", "-created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"SoulTetherRescue({self.sineater_sheet} pulled {self.sinner_sheet} "
            f"from stage {self.sinner_stage_at_start} to {self.sinner_stage_at_end})"
        )

"""Soul Tether audit models (Spec B §14.1, §15.1)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class SineatingPendingOffer(SharedMemoryModel):
    """Pending Sineating offer awaiting Sineater response (Task 1.6).

    Persisted so the frontend inbox UI can poll a real endpoint. The row is
    created by ``request_sineating`` and consumed (then deleted) by
    ``resolve_sineating_from_db``.

    Co-location is re-validated at accept time — either character may have left
    the scene since the offer was created. ``resolve_sineating_from_db`` raises
    ``SineatingValidationError`` and deletes the row when either character is no
    longer a participant of ``scene``.

    The unique constraint on ``(sinner_sheet, sineater_sheet)`` ensures at most
    one pending offer per pair. ``request_sineating`` uses ``update_or_create``
    so a repeat request replaces the stale row rather than raising an integrity
    error.
    """

    sinner_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="sineating_offers_sent",
    )
    sineater_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="sineating_offers_received",
    )
    relationship = models.ForeignKey(
        "relationships.CharacterRelationship",
        on_delete=models.CASCADE,
        related_name="sineating_pending_offers",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="sineating_pending_offers",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="sineating_pending_offers",
    )
    units_offered = models.PositiveSmallIntegerField()
    anima_cost_per_unit = models.PositiveSmallIntegerField()
    fatigue_cost_per_unit = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sinner_sheet", "sineater_sheet"],
                name="one_pending_sineating_per_pair",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"SineatingPendingOffer({self.sinner_sheet} → {self.sineater_sheet}, "
            f"{self.units_offered} units)"
        )


class PendingStageAdvanceOffer(SharedMemoryModel):
    """Pending stage-advance bonus offer awaiting Sineater response (Task 1.7).

    Persisted alongside the PROMPT_PLAYER dispatch so the rescue-prompt UI can
    poll a real endpoint. Created by ``soul_tether_stage_advance_prompt`` and
    consumed (then deleted) by ``resolve_stage_advance_prompt_from_db``.

    Two staleness conditions:
    - **TTL**: ``expires_at < now()`` — the stage-advance moment is transient;
      stale prompts are silently expired.
    - **Co-location**: If either PC has left the scene between prompt and
      response, the offer is considered stale.

    The unique constraint on ``(sinner_sheet, sineater_sheet)`` ensures at most
    one pending offer per pair. ``soul_tether_stage_advance_prompt`` uses
    ``update_or_create`` so a repeat prompt replaces a stale row.
    """

    sinner_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="stage_advance_offers_sent",
    )
    sineater_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="stage_advance_offers_received",
    )
    relationship = models.ForeignKey(
        "relationships.CharacterRelationship",
        on_delete=models.CASCADE,
        related_name="pending_stage_advance_offers",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="pending_stage_advance_offers",
        null=True,
        blank=True,
        help_text="Active scene at prompt time; null if no tracked scene was found.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="pending_stage_advance_offers",
    )
    sinner_corruption_stage = models.PositiveSmallIntegerField(
        help_text="The stage the Sinner is currently at when the prompt fires.",
    )
    commit_units_max = models.PositiveSmallIntegerField(
        help_text="Maximum Hollow units the Sineater may commit.",
    )
    strain_cost_per_unit = models.PositiveSmallIntegerField(
        help_text="Strain severity added to the Sineater per committed unit.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="Prompt expires after this time. Stale rows are deleted on next access.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sinner_sheet", "sineater_sheet"],
                name="one_pending_stage_advance_per_pair",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PendingStageAdvanceOffer({self.sinner_sheet} → {self.sineater_sheet}, "
            f"max={self.commit_units_max} units, expires={self.expires_at})"
        )


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

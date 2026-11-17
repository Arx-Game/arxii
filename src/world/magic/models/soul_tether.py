"""Soul Tether audit models (Spec B §14.1, §15.1)."""

from __future__ import annotations

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"
CHARACTER_RELATIONSHIP_MODEL = "arxii.CharacterRelationship"
SCENE_MODEL = "arxii.Scene"
RESONANCE_MODEL = "arxii.Resonance"


class SineatingPendingOffer(SharedMemoryModel):
    """Pending Sineating offer awaiting Sineater response (Task 1.6).

    Persisted so the frontend inbox UI can poll a real endpoint. The row is
    created by ``request_sineating`` (the Sinner's plea, attached to a pose) and consumed
    (then deleted) by ``perform_sineating`` or ``decline_sineating``.

    Co-location is re-validated when the ritual is performed: either character may have left
    the scene since the plea was made. ``perform_sineating`` raises
    ``SineatingValidationError`` and deletes the row when they no longer share an active
    scene.

    The unique constraint on ``(sinner_sheet, sineater_sheet)`` ensures at most
    one pending offer per pair. ``request_sineating`` uses ``update_or_create``
    so a repeat request replaces the stale row rather than raising an integrity
    error.
    """

    sinner_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="sineating_offers_sent",
    )
    sineater_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="sineating_offers_received",
    )
    relationship = models.ForeignKey(
        CHARACTER_RELATIONSHIP_MODEL,
        on_delete=models.CASCADE,
        related_name="sineating_pending_offers",
    )
    scene = models.ForeignKey(
        SCENE_MODEL,
        on_delete=models.CASCADE,
        related_name="sineating_pending_offers",
    )
    resonance = models.ForeignKey(
        RESONANCE_MODEL,
        on_delete=models.PROTECT,
        related_name="sineating_pending_offers",
    )
    units_offered = models.PositiveSmallIntegerField()
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

    The row is only written when ``shared_active_scene`` finds a shared
    active scene for the pair — guaranteeing ``scene`` is always non-null and
    that the co-location check at resolve time has a real scene to validate.

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
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="stage_advance_offers_sent",
    )
    sineater_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="stage_advance_offers_received",
    )
    relationship = models.ForeignKey(
        CHARACTER_RELATIONSHIP_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_stage_advance_offers",
    )
    scene = models.ForeignKey(
        SCENE_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_stage_advance_offers",
        help_text="Active scene at prompt time. Row is only written when a shared scene is found.",
    )
    resonance = models.ForeignKey(
        RESONANCE_MODEL,
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
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="sineatings_as_sinner",
    )
    sineater_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="sineatings_as_sineater",
    )
    relationship = models.ForeignKey(
        CHARACTER_RELATIONSHIP_MODEL,
        on_delete=models.PROTECT,
        related_name="sineatings",
    )
    scene = models.ForeignKey(
        SCENE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sineatings",
    )
    resonance = models.ForeignKey(
        RESONANCE_MODEL,
        on_delete=models.PROTECT,
        related_name="sineatings",
    )
    units_offered = models.PositiveIntegerField()
    units_accepted = models.PositiveIntegerField(
        help_text="0 = declined; 1..N = accepted that many units.",
    )
    corruption_moved = models.PositiveIntegerField(
        default=0,
        help_text="Corruption that left the Sinner.",
    )
    corruption_taken = models.PositiveIntegerField(
        default=0,
        help_text="Corruption that arrived on the Sineater, after their resistance.",
    )
    outcome = models.ForeignKey(
        "arxii.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The outcome of the Sineater's roll. Empty for a declined plea.",
    )
    sinner_resonance_earned = models.PositiveIntegerField(
        default=0,
        help_text="Resonance the Sinner earned in their thread's resonance.",
    )
    sineater_resonance_earned = models.PositiveIntegerField(
        default=0,
        help_text="Resonance the Sineater earned in their thread's resonance.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["sinner_sheet", "-created_at"]),
            models.Index(fields=["sineater_sheet", "-created_at"]),
            models.Index(fields=["relationship", "-created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"Sineating({self.sineater_sheet} took on {self.units_accepted}/"
            f"{self.units_offered} units for {self.sinner_sheet})"
        )


class SoulTetherRescue(SharedMemoryModel):
    """Audit row for a stage-3+ rescue ritual (Spec B §9, §14.1)."""

    sinner_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="rescues_as_sinner",
    )
    sineater_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="rescues_as_sineater",
    )
    relationship = models.ForeignKey(
        CHARACTER_RELATIONSHIP_MODEL,
        on_delete=models.PROTECT,
        related_name="rescues",
    )
    scene = models.ForeignKey(
        SCENE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rescues",
    )
    resonance = models.ForeignKey(
        RESONANCE_MODEL,
        on_delete=models.PROTECT,
        related_name="rescues",
    )
    sinner_stage_at_start = models.PositiveSmallIntegerField()
    sinner_stage_at_end = models.PositiveSmallIntegerField()
    severity_reduced = models.PositiveIntegerField()
    sineater_strain_taken = models.PositiveIntegerField(default=0)
    check_outcome = models.ForeignKey(
        "arxii.CheckOutcome",
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


class MireHolding(SharedMemoryModel):
    """How much corruption a Sineater carries for one Sinner in one resonance (#5177).

    The corruption itself lives where all corruption lives, on the Sineater's
    ``CharacterResonance.corruption_current`` for the resonance. ``amount`` says how much of
    it came from this Sinner, so the holdings in a resonance never sum to more than that
    corruption. Only ``take_on_corruption`` and ``release_mire`` write ``amount``, and
    ``reduce_corruption`` shrinks it when corruption falls for any other reason.

    ``relationship`` is the Sineater's own side toward the Sinner, which is unique per pair
    and outlives a tether being dissolved and formed again. The jackpot and fall counters are
    per tether, not per resonance, so they live on that side
    (``CharacterRelationship.mire_purified_since_payout`` / ``mire_succumbed_since_fall``).
    """

    relationship = models.ForeignKey(
        CHARACTER_RELATIONSHIP_MODEL,
        on_delete=models.CASCADE,
        related_name="mire_holdings",
        help_text="The Sineater's own relationship side toward the Sinner they carry for.",
    )
    resonance = models.ForeignKey(
        RESONANCE_MODEL,
        on_delete=models.PROTECT,
        related_name="mire_holdings",
    )
    amount = models.PositiveIntegerField(
        default=0,
        help_text="Corruption held from this Sinner in this resonance.",
    )

    class Meta:
        ordering = ["relationship", "resonance"]
        constraints = [
            models.UniqueConstraint(
                fields=["relationship", "resonance"],
                name="one_mire_holding_per_relationship_resonance",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"MireHolding({self.relationship.source} carries {self.amount} "
            f"{self.resonance} for {self.relationship.target})"
        )

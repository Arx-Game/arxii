"""Sanctum models — Plan 4 Subsystem F per-kind details for the SANCTUM RoomFeatureKind.

Resonance state for a Sanctum is **NOT** a field on ``SanctumDetails``.
The Ritual of Homecoming grows resonance by writing
``LocationValueModifier`` rows on the Sanctum's ``RoomProfile`` tagged
``source=f"sanctum:{pk}:homecoming"``. The cron tick reads
``effective_value(room_profile, resonance=sanctum.resonance_type)`` — the
cascade-summed total of authored ambient + Sanctum-grown + future
spell/event-source rows — and accumulates payouts into per-weaver
``SanctumPendingPayout`` rows (a "well" the weaver drains by physically
visiting the Sanctum and performing an absorb action).

This model carries only the Sanctum-specific *metadata* the resonance
math doesn't capture: who founded it, which type it's consecrated to,
whether it's personal vs covenant, ritual cooldowns, and the escrow for
sacrifices that hit the per-Sanctum cap.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class SanctumOwnerMode(models.TextChoices):
    """Whether a Sanctum is a personal home or a covenant's sacred ground."""

    PERSONAL = "PERSONAL", "Personal (Persona-owned home)"
    COVENANT = "COVENANT", "Covenant (Organization-owned sacred ground)"


class SanctumDetails(SharedMemoryModel):
    """Per-(SANCTUM RoomFeatureInstance) details payload.

    Created when a Sanctification ritual is performed in an eligible room.
    OneToOne back to the framework's ``RoomFeatureInstance`` — the
    install/upgrade flow lives in ``world.room_features``; the per-kind
    state lives here.
    """

    feature_instance = models.OneToOneField(
        "room_features.RoomFeatureInstance",
        on_delete=models.CASCADE,
        related_name="sanctum_details",
        primary_key=True,
    )
    resonance_type = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="sanctums",
        help_text=(
            "The resonance this Sanctum is consecrated to. Income payouts "
            "(via the cron tick) target this type; Ritual of Homecoming "
            "rows are created against this type; Ritual of Purging changes "
            "it."
        ),
    )
    owner_mode = models.CharField(
        max_length=10,
        choices=SanctumOwnerMode.choices,
        help_text=(
            "PERSONAL Sanctums use ``PERSONAL_OWN`` / ``HELPER`` thread "
            "slots; COVENANT Sanctums use ``COVENANT`` slots. Set at "
            "Sanctification by the ritual variant performed."
        ),
    )
    founder_character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="founded_sanctums",
        help_text=(
            "The CharacterSheet of the witch who performed the Sanctification "
            "ritual that founded this Sanctum. For PERSONAL Sanctums, this is "
            "the ongoing owner; for COVENANT, this is historical identity "
            "(the ongoing authority is the Covenant Organization). Used to "
            "differentiate founder-vs-non-founder Dissolution checks "
            "(non-founder = harder difficulty + larger botch consequences). "
            "Plan 4 §F revised 2026-06-03."
        ),
    )
    last_homecoming_ritual_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set on each successful Homecoming. Soft cooldown + UI display.",
    )
    last_purging_ritual_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set on each successful Purging. UI display + audit.",
    )
    pending_sacrifice_overflow = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text=(
            "Homecoming sacrifice that exceeded the per-Sanctum cap "
            "(owner Path-level × 10 for Personal). Held in escrow; "
            "absorbed by future Homecoming/cron when the cap rises."
        ),
    )

    class Meta:
        constraints = [
            # One PERSONAL Sanctum per CharacterSheet. Plan 4 §F revised 2026-06-03.
            # COVENANT sanctums are not constrained here — each covenant gets
            # one per owned building, enforced at the covenant level.
            models.UniqueConstraint(
                fields=["founder_character_sheet"],
                condition=models.Q(
                    owner_mode=SanctumOwnerMode.PERSONAL,
                    founder_character_sheet__isnull=False,
                ),
                name="sanctum_details_one_personal_per_character_sheet",
            ),
        ]

    def __str__(self) -> str:
        mode = self.get_owner_mode_display()
        return f"Sanctum#{self.feature_instance_id} ({mode}, {self.resonance_type_id})"


class SanctumPendingPayout(SharedMemoryModel):
    """Per-(Sanctum, weaver) pending resonance pool — the "well" Plan 4 §F.

    Cron tick increments the pending fields each tick (clamped to
    ``SANCTUM_PENDING_PAYOUT_CAP`` total). When a weaver physically
    visits the Sanctum's room and performs the absorb action, both
    fields drain to their respective ``grant_resonance`` calls
    (SANCTUM_WEAVING + SANCTUM_OWNER_BONUS as separate ledger rows)
    and reset to 0. No timing pressure on the player; the well is
    patient. No ``is_active`` flag — inertness emerges from the
    cascade (can't reach the room → can't absorb).
    """

    sanctum = models.ForeignKey(
        SanctumDetails,
        on_delete=models.CASCADE,
        related_name="pending_payouts",
    )
    weaver_character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="sanctum_pending_payouts",
        help_text=(
            "The CharacterSheet of the weaver whose income is accumulating. "
            "One row per (sanctum, weaver) pair."
        ),
    )
    pending_weaving = models.PositiveIntegerField(
        default=0,
        help_text="Accumulated income from SANCTUM_WEAVING source. Drained on absorb.",
    )
    pending_owner_bonus = models.PositiveIntegerField(
        default=0,
        help_text="Accumulated income from SANCTUM_OWNER_BONUS source. Drained on absorb.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Bumped on each cron-tick accumulation. UI 'last accrual' display.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sanctum", "weaver_character_sheet"],
                name="sanctum_pending_payout_unique_per_weaver",
            ),
        ]

    def total_pending(self) -> int:
        """Sum of both pending fields. Cap is checked against this total."""
        return self.pending_weaving + self.pending_owner_bonus

    def __str__(self) -> str:
        return (
            f"PendingPayout sanctum={self.sanctum_id} "
            f"weaver={self.weaver_character_sheet_id} "
            f"weaving={self.pending_weaving} bonus={self.pending_owner_bonus}"
        )


SANCTUM_PENDING_PAYOUT_CAP = 1000
"""Per-(sanctum, weaver) cap on total pending (sum of both fields).

The well overflows once filled — further ticks no-op for that weaver
until they absorb. At L1 modest income (~1/day) this cap is ~3 IC years
of stockpile; at L5 endgame (~30/day) it fills in ~33 IC days. Tunable.
"""

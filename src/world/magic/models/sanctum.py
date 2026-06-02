"""Sanctum models — Plan 4 Subsystem F per-kind details for the SANCTUM RoomFeatureKind.

Resonance state for a Sanctum is **NOT** a field on ``SanctumDetails``.
The Ritual of Homecoming grows resonance by writing
``LocationValueModifier`` rows on the Sanctum's ``RoomProfile`` tagged
``source=f"sanctum:{pk}:homecoming"``. The cron tick reads
``effective_value(room_profile, resonance=sanctum.resonance_type)`` — the
cascade-summed total of authored ambient + Sanctum-grown + future
spell/event-source rows — and pays out per weaver.

This model carries only the Sanctum-specific *metadata* the resonance
math doesn't capture: which type the Sanctum is consecrated to, whether
it's personal vs covenant, ritual cooldowns, and the escrow for
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

    Created when a Sanctum install Project resolves. OneToOne back to the
    framework's ``RoomFeatureInstance`` — the install/upgrade flow lives
    in ``world.room_features``; the per-kind state lives here.
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
            "Denormalized from the Building's owner type at install time. "
            "Re-synced by the ownership-transfer service when the Building's "
            "ownership changes. PERSONAL Sanctums use ``PERSONAL_OWN`` / "
            "``HELPER`` thread slots; COVENANT Sanctums use ``COVENANT`` slots."
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

    def __str__(self) -> str:
        mode = self.get_owner_mode_display()
        return f"Sanctum#{self.feature_instance_id} ({mode}, {self.resonance_type_id})"

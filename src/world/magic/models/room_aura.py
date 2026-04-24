"""RoomAuraProfile — room's magical character (Spec C §2.5, §2.6)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class RoomAuraProfile(SharedMemoryModel):
    """Room-side magical extension. Independent of residence.

    Holy sites, abyssal grottos, battle venues, and personal lairs all
    host a RoomAuraProfile if they have magical character. Non-magical
    rooms simply have no aura profile — the OneToOne reverse lookup
    returns None.

    Future: place-of-power flags, ambient-effect fields, decoration refs.
    """

    room_profile = models.OneToOneField(
        "evennia_extensions.RoomProfile",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="room_aura_profile",
    )

    def __str__(self) -> str:
        return f"RoomAuraProfile(room={self.room_profile_id})"


class RoomResonance(SharedMemoryModel):
    """Through-model for RoomAuraProfile ↔ Resonance M2M (Spec C §2.6)."""

    room_aura_profile = models.ForeignKey(
        RoomAuraProfile,
        on_delete=models.CASCADE,
        related_name="room_resonances",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="room_tags",
    )
    set_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Staff/player who tagged this resonance.",
    )
    set_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room_aura_profile", "resonance"],
                name="unique_room_resonance_per_profile",
            ),
        ]

    def __str__(self) -> str:
        return f"RoomResonance(aura={self.room_aura_profile_id}, res={self.resonance_id})"

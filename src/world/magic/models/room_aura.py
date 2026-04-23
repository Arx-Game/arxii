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

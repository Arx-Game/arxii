"""TrickleAccrual: resonance a character's days pile up until an anima ritual (#5308)."""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.magic.constants import TrickleSource


class TrickleAccrual(SharedMemoryModel):
    """One day's trickle of one resonance from one source, waiting to be harvested.

    The daily residence and worn-piece ticks write these instead of granting resonance. An
    anima ritual harvests every waiting row of a character, turns each resonance's total
    into one ``TRICKLE_HARVEST`` grant and stamps ``harvested_at``. An unstamped row is
    waiting: nothing reads it as a balance.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="trickle_accruals",
    )
    resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.PROTECT,
        related_name="trickle_accruals",
    )
    amount = models.PositiveIntegerField(
        help_text="Resonance this day's trickle added to the pile.",
    )
    source = models.CharField(
        max_length=32,
        choices=TrickleSource.choices,
        help_text="Discriminator. Identifies which source FK is populated.",
    )
    room_profile = models.ForeignKey(
        "arxii.RoomProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="trickle_accruals",
        help_text="Set when source is a room residence: the room that trickled.",
    )
    outfit_item_facet = models.ForeignKey(
        "arxii.ItemFacet",
        # PROTECT, like ResonanceGrant.outfit_item_facet: the exactly-one-source check below
        # rejects a nulled FK, so a facet with accruals is soft-removed, never deleted. A
        # facet merge moves its accruals to the keeper first.
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="trickle_accruals",
        help_text="Set when source is a worn piece: the piece's facet that trickled.",
    )
    accrued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    harvested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When an anima ritual turned this trickle into resonance. Null while waiting.",
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["character_sheet", "resonance"],
                condition=Q(harvested_at__isnull=True),
                name="trickle_unharvested_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                name="trickle_accrual_source_shape",
                check=(
                    Q(source="ROOM_RESIDENCE")
                    & Q(room_profile__isnull=False)
                    & Q(outfit_item_facet__isnull=True)
                )
                | (
                    Q(source="OUTFIT_TRICKLE")
                    & Q(outfit_item_facet__isnull=False)
                    & Q(room_profile__isnull=True)
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"TrickleAccrual({self.character_sheet_id}, {self.resonance_id}, {self.amount})"

"""The substance an item carries (#5125).

A Primum item is an ordinary ``ItemInstance`` made from a template that names a substance; a
minted Primum item gets no row here, since its template says what it is. An ``ItemSubstance``
row is written by crafting (``stamp_primum_substances``): when a craft uses up Primum items,
the crafted piece carries their substance at a Primum step, so a worn or held item is read back
without re-deriving it from the materials.

All models set ``Meta.app_label = "arxii"`` (the single collapsed app, #2906).
"""

from __future__ import annotations

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel


class ItemSubstance(SharedMemoryModel):
    """One item carrying one substance at one Primum step (#5125)."""

    item_instance = models.ForeignKey(
        "arxii.ItemInstance",
        on_delete=models.CASCADE,
        related_name="item_substances",
        help_text="The item that carries the substance.",
    )
    substance = models.ForeignKey(
        "arxii.Substance",
        on_delete=models.PROTECT,
        related_name="item_rows",
        help_text="The substance the item carries.",
    )
    step = models.ForeignKey(
        "arxii.PrimumStep",
        on_delete=models.PROTECT,
        related_name="item_rows",
        help_text="The Primum step the item carries it at.",
    )

    class Meta:
        app_label = "arxii"
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "substance"],
                name="items_itemsubstance_item_substance_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_instance_id} carries {self.substance_id}"

"""Ghost-tutor tutelage record (#2460).

A permanent record that a character has summoned a ghostly tutor for a
tradition, making that tradition's signature techniques available through
the existing TRAIN offer at the Academy/Archive.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class GhostTutelage(SharedMemoryModel):
    """Permanent record that a character has summoned a ghostly tutor
    for a tradition (#2460).

    Makes the tradition's signature techniques available through the existing
    TRAIN offer at the Academy/Archive. One per (character_sheet, tradition).
    The summoning ritual is the story-gate; this record is the mechanical
    unlock. Composes with the Path-discovery system (#2603) -- one route into
    tradition knowledge, not the whole progression.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="ghost_tutelages",
        help_text="The character who summoned this tutor.",
    )
    tradition = models.ForeignKey(
        "magic.Tradition",
        on_delete=models.PROTECT,
        related_name="ghost_tutelages",
        help_text="The tradition whose tutor was summoned.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "tradition"],
                name="unique_ghost_tutelage_per_tradition",
            ),
        ]
        verbose_name = "Ghost Tutelage"
        verbose_name_plural = "Ghost Tutelages"

    def __str__(self) -> str:
        return f"GhostTutelage<{self.character_sheet_id} -> {self.tradition_id}>"

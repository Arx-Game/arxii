"""Pre-declared next-path intent (#543). Mutable; consumed by the Crossing offer."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class PathIntent(SharedMemoryModel):
    """A character's declared intention for their next path stage.

    Mutable aspiration, not a receipt: re-declaring overwrites. The Audere
    Majora offer pre-selects this path when it is among the eligible ones.
    """

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="path_intent",
    )
    # NOT named "path": idmapper metaclass shadows that attribute name.
    intended_path = models.ForeignKey(
        "classes.Path",
        on_delete=models.PROTECT,
        related_name="path_intents",
        help_text="The path the character intends to take at their next crossing.",
    )
    declared_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Path Intent"
        verbose_name_plural = "Path Intents"

    def __str__(self) -> str:
        return f"PathIntent(sheet={self.character_sheet_id} → {self.intended_path.name})"

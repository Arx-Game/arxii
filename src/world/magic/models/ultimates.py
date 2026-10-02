"""Known ultimates (#4098): which ultimates a character has discovered at Audere."""

from __future__ import annotations

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel


class KnownUltimate(SharedMemoryModel):
    """A character discovered this ultimate at an Audere or a Crossing.

    Deliberately not a ``CharacterTechnique``: that row means "castable now" and every
    ordinary cast surface reads it. An ultimate is castable only while Audere or Audere
    Majora holds and it is ``readied``, the single pick of the current Audere.
    """

    character = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="known_ultimates",
    )
    technique = models.ForeignKey(
        "arxii.Technique",
        on_delete=models.PROTECT,
        related_name="known_by_characters",
    )
    discovered_at = models.DateTimeField(auto_now_add=True)
    crossing = models.ForeignKey(
        "arxii.AudereMajoraCrossing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ultimates_discovered",
        help_text="The Crossing this was discovered through. Null = a plain Audere.",
    )
    readied = models.BooleanField(
        default=False,
        help_text=(
            "The pick of the character's current Audere: castable while Audere or Audere "
            "Majora holds. Cleared on the next Audere accept, a Crossing and Audere's end."
        ),
    )

    class Meta:
        ordering = ["discovered_at", "pk"]
        verbose_name = "Known Ultimate"
        verbose_name_plural = "Known Ultimates"
        constraints = [
            models.UniqueConstraint(
                fields=["character", "technique"], name="unique_known_ultimate"
            ),
            models.UniqueConstraint(
                fields=["character"],
                condition=models.Q(readied=True),
                name="one_readied_ultimate_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character} knows {self.technique}"

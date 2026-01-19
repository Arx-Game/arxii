"""
Path history models for the progression system.

Tracks which paths a character has selected at each stage milestone.
"""

from django.db import models


class CharacterPathHistory(models.Model):
    """
    Records which path a character selected at each stage milestone.

    A character's path journey is tracked here - e.g.:
    - Stage 1: Path of Steel (Jan 2026)
    - Stage 2: Vanguard (Apr 2026)
    - Stage 3: Scourgeknight (Sep 2026)
    """

    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="path_history",
        help_text="The character this path history belongs to",
    )
    path = models.ForeignKey(
        "classes.Path",
        on_delete=models.PROTECT,
        related_name="character_selections",
        help_text="The path selected by the character",
    )
    selected_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this path was selected",
    )

    class Meta:
        unique_together = ["character", "path"]
        ordering = ["character", "path__stage"]
        verbose_name = "Character Path History"
        verbose_name_plural = "Character Path Histories"

    def __str__(self):
        return f"{self.character.key}: {self.path.name}"

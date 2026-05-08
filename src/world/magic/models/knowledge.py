"""Ritual knowledge tracking models.

Mirrors world.codex.CharacterCodexKnowledge. Tracks which rituals a character
knows and how they came to know them.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class CharacterRitualKnowledge(SharedMemoryModel):
    """Tracks which rituals a character knows.

    Mirrors world.codex.CharacterCodexKnowledge. Tracked at RosterEntry
    level so knowledge survives player changes on a tenure.
    """

    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="known_rituals",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="known_by_records",
    )
    learned_from = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taught_rituals",
        help_text=(
            "Tenure of the character who taught this ritual. NULL when "
            "self-authored or granted by background."
        ),
    )
    learned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["roster_entry", "ritual"],
                name="unique_roster_ritual_knowledge",
            ),
        ]
        verbose_name = "Character Ritual Knowledge"
        verbose_name_plural = "Character Ritual Knowledge"

    def __str__(self) -> str:
        return f"{self.roster_entry}: knows {self.ritual}"

"""Reincarnation: links a character to a past life via the Atavism gift."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.models.gifts import Gift


class Reincarnation(SharedMemoryModel):
    """
    Links a character to a past life via their Atavism gift.

    Created at character finalization when a character has the Old Soul
    distinction. Staff/GMs fill in past_life details later as a story arc.
    Future: past_life fields may be replaced by a FK to a PastLife model
    when multiple characters can share the same historical figure.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="reincarnations",
        help_text="The character who is a reincarnation.",
    )
    gift = models.OneToOneField(
        Gift,
        on_delete=models.CASCADE,
        related_name="reincarnation",
        help_text="The Atavism gift manifesting the past life.",
    )
    past_life_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Name of the past life (filled in by staff/GM).",
    )
    past_life_notes = models.TextField(
        blank=True,
        help_text="Notes about the past life (filled in by staff/GM).",
    )

    class Meta:
        verbose_name = "Reincarnation"
        verbose_name_plural = "Reincarnations"

    def __str__(self) -> str:
        name = self.past_life_name or "Unknown past life"
        return f"Reincarnation of {name} ({self.character})"

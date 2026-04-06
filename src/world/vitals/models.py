"""Models for the vitals system."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.vitals.constants import CharacterStatus


class CharacterVitals(SharedMemoryModel):
    """Persistent character life state and health tracking.

    Tracks the character's current life status (alive, unconscious, dying, dead)
    independently of any specific combat encounter. Combat creates temporary
    health snapshots on CombatParticipant; this model tracks the canonical state.
    """

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="vitals",
    )
    status = models.CharField(
        max_length=20,
        choices=CharacterStatus.choices,
        default=CharacterStatus.ALIVE,
    )
    died_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the character died (permanent death).",
    )
    unconscious_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the character became unconscious.",
    )

    def __str__(self) -> str:
        return f"{self.character_sheet} ({self.get_status_display()})"

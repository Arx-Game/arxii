"""ImpulseShown: the record that a character was told of an impulse in a scene (#5177)."""

from __future__ import annotations

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.magic.constants import ImpulseKind


class ImpulseShown(SharedMemoryModel):
    """One row says a character was told of one resonance's impulse in one scene.

    A character is sent the words of an Intrusive Thoughts impulse, and told that a
    Compulsion pulls at them, once per scene per resonance. The row survives a server
    reload, which is why this is a table and not a memo. It is removed with the scene.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="impulses_shown",
    )
    resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.CASCADE,
        related_name="impulses_shown",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        on_delete=models.CASCADE,
        related_name="impulses_shown",
    )
    kind = models.CharField(max_length=16, choices=ImpulseKind.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "resonance", "scene", "kind"],
                name="one_impulse_shown_per_sheet_resonance_scene_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"ImpulseShown({self.character_sheet_id}, {self.resonance_id}, {self.kind})"

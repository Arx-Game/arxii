"""Clue models (#1144) — the Investigation & Discovery pointer.

A ``Clue`` points at exactly one target worth discovering (a codex entry, a mission,
later a secret/scandal). It never exists without a target — no red herrings, no empty
clues — and the target drives the "you already know this" flag when a clue would
surface. *How* a clue is acquired (room search, triggers, random) and *how* it resolves
(automatic grant vs. a research project) are separate layers that link to this pointer;
this module owns only the pointer and the per-character held-clue record.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from world.clues.constants import ClueResolution, ClueTargetKind


class Clue(DiscriminatorMixin, SharedMemoryModel):
    """A pointer to one discoverable target. Always points at something (invariant).

    Add a new target kind by adding the value to ``ClueTargetKind``, a nullable
    per-kind FK below, and a ``DISCRIMINATOR_MAP`` entry (SECRET/SCANDAL planned, #1143).
    """

    DISCRIMINATOR_FIELD = "target_kind"
    DISCRIMINATOR_MAP = {
        ClueTargetKind.CODEX: "target_codex_entry",
        ClueTargetKind.MISSION: "target_mission",
    }

    target_kind = models.CharField(
        max_length=20,
        choices=ClueTargetKind.choices,
        help_text="Which target this clue points at (selects the active FK).",
    )
    target_codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="clues",
        help_text="The codex entry this clue hints at (target_kind=CODEX).",
    )
    target_mission = models.ForeignKey(
        "missions.MissionTemplate",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="clues",
        help_text="The mission this clue points to (target_kind=MISSION).",
    )

    name = models.CharField(
        max_length=200,
        help_text="Name of the clue (e.g. 'Torn Journal Page'). Player-visible.",
    )
    description = models.TextField(
        help_text="What the player sees when they find this clue. Player-visible.",
    )
    research_value = models.PositiveIntegerField(
        default=1,
        help_text="Progress this clue contributes toward resolving its target.",
    )
    resolution_mode = models.CharField(
        max_length=20,
        choices=ClueResolution.choices,
        default=ClueResolution.AUTOMATIC,
        help_text="How holding this clue becomes having the target.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Clue"
        verbose_name_plural = "Clues"

    def clean(self) -> None:
        super().clean()
        errors = self._validate_discriminator(self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP)
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.name} -> {self.get_active_target_name()}"


class CharacterClue(SharedMemoryModel):
    """A clue a character has acquired (the held-clue record).

    Roster-scoped like codex knowledge: a clue belongs to the character itself, so a
    new player inheriting the character inherits the clues it has found.
    """

    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="clues_held",
    )
    clue = models.ForeignKey(
        Clue,
        on_delete=models.CASCADE,
        related_name="held_by",
    )
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["roster_entry", "clue"]
        ordering = ["-found_at"]
        verbose_name = "Character Clue"
        verbose_name_plural = "Character Clues"

    def __str__(self) -> str:
        return f"{self.roster_entry}: {self.clue.name}"

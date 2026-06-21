"""Class-level advancement receipts.

These record a character's *mechanical* class-level advance. Narratively each
advance is a step in the character's Durance (their life-long story arc); the
ceremony that drives the within-tier case is the Ritual of the Durance, and the
tier-crossing case is Audere Majora. Backend names stay Class/Level.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class AbstractClassLevelAdvancement(models.Model):
    """Shared shape for a single class-level advance (within-tier or crossing)."""

    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    declaration_interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
        help_text="The declaration pose. Soft FK — partitioned table.",
    )
    level_before = models.PositiveSmallIntegerField(
        help_text="Character level immediately before the crossing.",
    )
    level_after = models.PositiveSmallIntegerField(
        help_text="Character level granted by the crossing.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class ClassLevelAdvancement(AbstractClassLevelAdvancement, SharedMemoryModel):
    """Receipt for a within-tier advance via the Ritual of the Durance. Survives death."""

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="class_level_advancements",
    )
    character_class = models.ForeignKey(
        "classes.CharacterClass",
        on_delete=models.PROTECT,
        related_name="durance_advancements",
    )
    officiant = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="officiated_advancements",
        help_text="The trainer who inducted this advance (PC or academy NPC).",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="class_level_advancements",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Class Level Advancement"
        verbose_name_plural = "Class Level Advancements"

    def __str__(self) -> str:
        return (
            f"ClassLevelAdvancement(sheet={self.character_sheet_id}, "
            f"{self.character_class_id}, level {self.level_before}→{self.level_after})"
        )

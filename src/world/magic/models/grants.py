"""Ritual grant tables for character creation.

Five sources that grant CharacterRitualKnowledge rows during CG reconciliation
(Task 1.3). Each is a simple two-FK model mirroring the codex grant pattern
in world.codex.models (BeginningsCodexGrant, PathCodexGrant, etc.).
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class BeginningsRitualGrant(SharedMemoryModel):
    """Rituals granted by a Beginnings choice."""

    beginnings = models.ForeignKey(
        "character_creation.Beginnings",
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["beginnings", "ritual"],
                name="unique_beginnings_ritual_grant",
            ),
        ]
        verbose_name = "Beginnings Ritual Grant"
        verbose_name_plural = "Beginnings Ritual Grants"

    def __str__(self) -> str:
        return f"{self.beginnings} grants {self.ritual}"


# Idmapper metaclass sets attrs["path"] which shadows the "path" FK.
# Same pattern as PathCodexGrant in world.codex.models.
class PathRitualGrant(models.Model):  # noqa: SHARED_MEMORY
    """Rituals granted by a Path choice."""

    path = models.ForeignKey(
        "classes.Path",
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["path", "ritual"],
                name="unique_path_ritual_grant",
            ),
        ]
        verbose_name = "Path Ritual Grant"
        verbose_name_plural = "Path Ritual Grants"

    def __str__(self) -> str:
        return f"{self.path} grants {self.ritual}"


class DistinctionRitualGrant(SharedMemoryModel):
    """Rituals granted by a Distinction."""

    distinction = models.ForeignKey(
        "distinctions.Distinction",
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["distinction", "ritual"],
                name="unique_distinction_ritual_grant",
            ),
        ]
        verbose_name = "Distinction Ritual Grant"
        verbose_name_plural = "Distinction Ritual Grants"

    def __str__(self) -> str:
        return f"{self.distinction} grants {self.ritual}"


class TraditionRitualGrant(SharedMemoryModel):
    """Rituals granted by a Tradition."""

    tradition = models.ForeignKey(
        "magic.Tradition",
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tradition", "ritual"],
                name="unique_tradition_ritual_grant",
            ),
        ]
        verbose_name = "Tradition Ritual Grant"
        verbose_name_plural = "Tradition Ritual Grants"

    def __str__(self) -> str:
        return f"{self.tradition} grants {self.ritual}"


class CodexEntryRitualGrant(SharedMemoryModel):
    """Rituals granted by learning a Codex entry.

    Addition beyond the four codex grant tables — codex entries can unlock
    ritual knowledge in addition to lore knowledge.
    """

    codex_entry = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.CASCADE,
        related_name="ritual_grants",
    )
    ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["codex_entry", "ritual"],
                name="unique_codex_entry_ritual_grant",
            ),
        ]
        verbose_name = "Codex Entry Ritual Grant"
        verbose_name_plural = "Codex Entry Ritual Grants"

    def __str__(self) -> str:
        return f"{self.codex_entry} grants {self.ritual}"

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


# Idmapper metaclass sets attrs["path"] which shadows the "path" FK.
# Same pattern as PathRitualGrant above / PathCodexGrant in world.codex.models.
class PathGiftGrant(models.Model):  # noqa: SHARED_MEMORY
    """Gift + curated starter technique set granted by crossing into a Path.

    The (Path x Gift) -> technique-set leg of ADR-0055 (#1579): the same authored
    Gift yields a different starter set per Path (a warrior-line and a spy-line path
    can both grant Pyromancy, but grant different techniques from it). Minted as
    CharacterGift + CharacterTechnique rows on a path crossing by
    ``world.magic.services.path_magic.grant_path_magic``.
    """

    path = models.ForeignKey(
        "classes.Path",
        on_delete=models.CASCADE,
        related_name="gift_grants",
    )
    gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        related_name="path_grants",
    )
    starter_techniques = models.ManyToManyField(
        "magic.Technique",
        blank=True,
        related_name="granted_by_path_gifts",
        help_text=("Curated subset of this gift's techniques minted on crossing into this path."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["path", "gift"],
                name="unique_path_gift_grant",
            ),
        ]
        verbose_name = "Path Gift Grant"
        verbose_name_plural = "Path Gift Grants"

    def __str__(self) -> str:
        return f"{self.path} grants {self.gift}"

    def clean(self) -> None:
        super().clean()
        # M2M rows are only queryable once the grant row exists (admin / test
        # save-then-validate). Every starter technique must belong to this gift.
        if self.pk:
            mismatched = [t for t in self.starter_techniques.all() if t.gift_id != self.gift_id]
            if mismatched:
                from django.core.exceptions import ValidationError  # noqa: PLC0415

                raise ValidationError(
                    {"starter_techniques": ("Every starter technique must belong to this gift.")}
                )


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

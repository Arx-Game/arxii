"""Prepared per-character Audere text (#4101): the layer above patron and tier.

Authored content (durable, ADR-0237): written by staff in admin or by the
character's table GM. Resolution is field by field (a blank field falls through
to the patron variant, then the tier) in world.magic.services.prepared_text.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from core.models import ArxSharedMemoryModel as SharedMemoryModel


class CharacterCrossingText(SharedMemoryModel):
    """One character's own text for their next Audere Majora crossing."""

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="prepared_crossing_texts",
    )
    vision_text = models.TextField(
        blank=True,
        default="",
        help_text="Shown ONLY to the crossing player. Blank = the patron or tier vision.",
    )
    manifestation_text = models.TextField(
        blank=True,
        default="",
        help_text="The room line for this crossing. Blank = the patron or tier line.",
    )
    deed_title = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Public deed name for this crossing. Blank = the tier's deed title.",
    )
    prepared_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Who wrote it (staff or the character's table GM). Never shown to players.",
    )
    crossing = models.OneToOneField(
        "arxii.AudereMajoraCrossing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_text",
        help_text="Set when a crossing used this text; a used text never fires again.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Prepared Crossing Text"
        verbose_name_plural = "Prepared Crossing Texts"
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet"],
                condition=Q(crossing__isnull=True),
                name="one_unused_prepared_crossing_text_per_character",
            ),
            # The dashes below ARE the forbidden characters this constraint rejects
            # (see "Never an em/en-dash in a name" in CLAUDE.md) — it cannot state
            # its own rule without containing them.
            models.CheckConstraint(
                condition=(
                    ~Q(deed_title__contains="—")  # noqa: IDENT_DASH
                    & ~Q(deed_title__contains="–")  # noqa: IDENT_DASH
                ),
                name="prepared_crossing_deed_title_no_dash",
            ),
        ]

    def __str__(self) -> str:
        return f"CharacterCrossingText(sheet={self.character_sheet_id}, used={self.crossing_id})"


class CharacterSurgeText(SharedMemoryModel):
    """One character's own Audere surge line (no patron layer exists for surges)."""

    character_sheet = models.OneToOneField(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="prepared_surge_text",
    )
    surge_text = models.TextField(
        blank=True,
        default="",
        help_text="Room line when this character surges. {name} = primary-persona name.",
    )
    prepared_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Prepared Surge Text"
        verbose_name_plural = "Prepared Surge Texts"

    def __str__(self) -> str:
        return f"CharacterSurgeText(sheet={self.character_sheet_id})"

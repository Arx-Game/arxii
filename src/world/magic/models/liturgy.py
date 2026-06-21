"""Ritual liturgy: player-facing authored words for specific rituals.

This module holds the authored text content that accompanies a Ritual — the
spoken calls, invocations, and ceremonial language that officiants deliver
during performance.

The words here are public, non-spoiler content. Spoiler-private ceremony text
(e.g. the Audere Majora vision/manifestation wording) lives on
AudereMajoraThreshold and is never duplicated here.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class RitualLiturgy(SharedMemoryModel):
    """Player-facing liturgical text for a Ritual.

    Holds the authored ceremonial words associated with a Ritual row. Each
    Ritual has at most one RitualLiturgy (OneToOne). The opening_call is the
    officiant's spoken invocation at the start of the rite — authored as data,
    not hardcoded in game logic.

    The wording here is public and non-spoiler. Spoiler-private content (such
    as the Audere Majora crossing ceremony) lives on AudereMajoraThreshold
    and is kept denormalized from this model — do not duplicate or reference
    that wording here.
    """

    ritual = models.OneToOneField(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="liturgy",
    )
    opening_call = models.TextField(
        help_text="The officiant's spoken invocation at the opening of the rite.",
    )

    class Meta:
        verbose_name = "ritual liturgy"
        verbose_name_plural = "ritual liturgies"

    def __str__(self) -> str:
        return f"Liturgy for {self.ritual_id}"

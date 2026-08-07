"""Ritual anima pool contributions (#3001).

A ritual with ``anima_requirement > 0`` is powered by a pool that participants
fill by channeling their own anima, opening a vein (prick/gash), or draining a
sacrifice. Contribution rows are the audit trail: they outlive the
``RitualSession`` they were made under (sessions delete on fire), so the FK to
the session is nullable and severs rather than cascading.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import AnimaContributionKind

_CHARACTER_SHEET_FK = "arxii.CharacterSheet"


class RitualAnimaContribution(SharedMemoryModel):
    """One participant's anima payment into a ritual's pool (#3001)."""

    session = models.ForeignKey(
        "arxii.RitualSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anima_contributions",
        help_text="The session this fed; null after the session fires or for solo performs.",
    )
    ritual = models.ForeignKey(
        "arxii.Ritual",
        on_delete=models.PROTECT,
        related_name="anima_contributions",
    )
    contributor = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.PROTECT,
        related_name="ritual_anima_contributions",
        help_text="Who made the payment (the sacrificer, for SACRIFICE rows).",
    )
    kind = models.CharField(max_length=16, choices=AnimaContributionKind.choices)
    amount = models.PositiveIntegerField(help_text="Anima that entered the pool.")
    victim = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ritual_sacrifices_suffered",
        help_text="The drained victim (SACRIFICE only).",
    )
    was_lethal = models.BooleanField(
        default=False,
        help_text="True when a SACRIFICE drain killed the victim (death harvest).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ritual Anima Contribution"
        verbose_name_plural = "Ritual Anima Contributions"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(kind="SACRIFICE", victim__isnull=False)
                    | ~models.Q(kind="SACRIFICE") & models.Q(victim__isnull=True)
                ),
                name="ritual_contribution_victim_only_for_sacrifice",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.contributor} -> {self.ritual} ({self.kind} {self.amount})"

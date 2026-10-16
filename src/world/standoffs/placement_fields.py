"""The per-placement standoff fields an opponent line carries (#4361).

A placement is one authored opponent line: a beat's ``BeatOpponentLine`` or a scenario
option's ``MissionOptionOpponentLine``. Both carry the same edits over their creature
template, so they share this abstract base. Drive edits and switched-off faction rules
are child rows (``OpponentLineDrive``, ``OpponentLineFactionRuleSuppression``). At spawn
the edits are stamped on each ``CombatOpponent`` (``services.placement``).
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models

from world.combat.constants import CauseKind


class PlacementEdits(models.Model):
    """Edits one placement makes over its creature template's standoff profile."""

    cause_override = models.CharField(
        max_length=20,
        choices=CauseKind.choices,
        blank=True,
        help_text="Blank keeps the template's cause; pick another for this placement only.",
    )
    cause_margin_override = models.SmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-99)],
        help_text="Blank keeps the template's cause margin (percent).",
    )
    organization = models.ForeignKey(
        "arxii.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Blank keeps the template's affiliation; pick another for this placement.",
    )

    class Meta:
        abstract = True

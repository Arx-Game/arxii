"""Maturation Point models (#2756).

Maturation Points are the deterministic reward for actually aging: one point
per milestone matured-year (21, 24, 27, ...). The points live in the years
themselves — a ``MaturationSpend`` is active iff its ``milestone_year`` is at
or below the sheet's current ``matured_years``, so age reversal deactivates
the affected spends and re-aging reactivates them
(``world.progression.services.maturation.sync_maturation_spends``).
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.classes.models import PathStage


class MaturationStatCap(SharedMemoryModel):
    """Authored per-stage cap on any single stat's value (PLACEHOLDER tuning).

    Seeded 5/6/11/16/21/26 for PROSPECT..TRANSCENDENT. Caps are display dots
    (stat storage is internal ×10 — #2894; the spend service multiplies at the
    comparison). The cap binds the maturation spend path; CG's
    ``STAT_MAX_VALUE`` (5) is the PROSPECT row enforced at creation time.
    """

    path_stage = models.PositiveSmallIntegerField(
        choices=PathStage.choices,
        unique=True,
        help_text="The stage band this cap applies to.",
    )
    stat_cap = models.PositiveSmallIntegerField(
        help_text="Maximum value any single stat may reach at this stage.",
    )

    class Meta:
        verbose_name = "Maturation stat cap"
        verbose_name_plural = "Maturation stat caps"
        ordering = ["path_stage"]

    def __str__(self) -> str:
        return f"{PathStage(self.path_stage).label} cap {self.stat_cap}"


class MaturationSpend(SharedMemoryModel):
    """One spent Maturation Point: a milestone year converted into +1 stat.

    ``is_active`` mirrors ``milestone_year <= sheet.matured_years`` and is
    maintained exclusively by ``sync_maturation_spends`` — every write to
    ``matured_years`` outside the birthday tick must call it (explicit
    service calls, no signals; ADR-0009).
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="maturation_spends",
    )
    trait = models.ForeignKey(
        "arxii.Trait",
        on_delete=models.PROTECT,
        related_name="maturation_spends",
        help_text="The stat this point raised.",
    )
    milestone_year = models.PositiveSmallIntegerField(
        help_text="The matured-year milestone that funded this point (21, 24, ...).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="False while the character's matured_years sits below milestone_year.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Maturation spend"
        verbose_name_plural = "Maturation spends"
        ordering = ["character_sheet", "milestone_year"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "milestone_year"],
                name="unique_spend_per_milestone",
            ),
        ]

    def __str__(self) -> str:
        state = "active" if self.is_active else "dormant"
        return f"{self.character_sheet} year {self.milestone_year} -> {self.trait} ({state})"

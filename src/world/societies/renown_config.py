"""RenownAwardConfig — shared authored renown-award knobs (#953).

Abstract base carrying the four inputs `fire_renown_award` consumes, so
DramaticMomentType, AudereMajoraThreshold, and the propaganda models (#1621)
don't each re-declare them. Relocated from world.magic.models (#1621): the
config belongs beside `fire_renown_award` in societies, and magic already
imports societies (never the reverse), so consumers in any app can inherit it
without an import cycle.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.societies.constants import RenownMagnitude, RenownReach, RenownRisk


class RenownAwardConfig(SharedMemoryModel):
    """Authored magnitude/risk/reach/archetypes for a renown award."""

    magnitude = models.CharField(
        max_length=20,
        choices=RenownMagnitude.choices,
        default=RenownMagnitude.SMALL,
        help_text="Renown magnitude passed to fire_renown_award.",
    )
    risk = models.CharField(
        max_length=20,
        choices=RenownRisk.choices,
        default=RenownRisk.NONE,
        help_text="Risk level for legend award; NONE means no legend granted.",
    )
    reach = models.CharField(
        max_length=20,
        choices=RenownReach.choices,
        null=True,
        blank=True,
        help_text="Override reach; if null, derived from magnitude default.",
    )
    archetypes = models.ManyToManyField(
        "societies.PhilosophicalArchetype",
        blank=True,
        related_name="%(class)s_renown_configs",
        help_text="Philosophical archetypes forwarded to fire_renown_award.",
    )

    class Meta:
        abstract = True

    def as_renown_award_kwargs(self) -> dict:
        """Return the magnitude/risk/reach/archetypes kwargs for fire_renown_award."""
        return {
            "magnitude": self.magnitude,
            "risk": self.risk,
            "reach": self.reach or None,
            "archetypes": list(self.archetypes.all()),
        }

"""AffinityInteraction directed-pair table for the resonance-environment primitive.

Staff-authored rows tell the system what happens when a caster's magic affinity
meets a place's affinity. Each ordered (source_affinity, environment_affinity)
pair carries a valence, kind, aggressor, and severity multiplier.
"""

from decimal import Decimal

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)


class AffinityInteraction(SharedMemoryModel):
    """An authored directed-pair row read by the resonance-environment primitive.

    source_affinity      — the caster's dominant magic affinity.
    environment_affinity — the place's affinity tag.
    valence              — ALIGNED (amplifies) or OPPOSED.
    kind                 — AMPLIFY / REJECT / REPEL / CORRUPT.
    aggressor            — who acts on whom (ENVIRONMENT or CASTER).
    severity_multiplier  — scales the effect magnitude; default 1.00.

    Unique per ordered (source_affinity, environment_affinity) pair.
    """

    source_affinity = models.ForeignKey(
        "magic.Affinity",
        on_delete=models.PROTECT,
        related_name="interactions_as_source",
        help_text="The caster's magic affinity.",
    )
    environment_affinity = models.ForeignKey(
        "magic.Affinity",
        on_delete=models.PROTECT,
        related_name="interactions_as_environment",
        help_text="The place's affinity.",
    )
    valence = models.CharField(
        max_length=16,
        choices=ResonanceValence.choices,
        help_text="Whether the pair is aligned or opposed.",
    )
    kind = models.CharField(
        max_length=16,
        choices=AffinityInteractionKind.choices,
        help_text="The nature of the interaction (amplify, reject, repel, corrupt).",
    )
    aggressor = models.CharField(
        max_length=16,
        choices=AffinityInteractionAggressor.choices,
        help_text="Whether the environment acts on the caster, or vice versa.",
    )
    severity_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Scales the interaction's effect magnitude.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_affinity", "environment_affinity"],
                name="unique_affinity_interaction_pair",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.source_affinity.name}->{self.environment_affinity.name}: "
            f"{self.valence}/{self.kind}"
        )

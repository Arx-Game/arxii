"""AffinityInteraction directed-pair table and ResonanceEnvironmentConfig singleton
for the resonance-environment primitive.

Staff-authored AffinityInteraction rows tell the system what happens when a
caster's magic affinity meets a place's affinity.

ResonanceEnvironmentConfig is the staff-tunable scalar singleton (pk=1) that
controls the numeric shape of severity calculations and backfire difficulty.
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


class ResonanceEnvironmentConfig(SharedMemoryModel):
    """Staff-tunable singleton (pk=1) for the resonance-environment primitive.

    Scalar coefficients that convert place_magnitude, caster alignment, and
    severity_multiplier into raw severity and backfire check difficulty. All
    values have sane defaults so the low/high room tiers in the story-slice
    seed produce DISTINCT difficulties without any staff configuration.

    Default rationale
    -----------------
    base_coefficient = 1.000
        Neutral pass-through. ``raw_severity = place_magnitude
        * caster_alignment * severity_multiplier * base_coefficient``.
        Staff may scale up (more lethal) or down (forgiving) globally.

    caster_power_scalar = 0.500
        A caster at 100% relevant aura counts as strength 50 on a 0-100
        magnitude scale. This keeps the default balanced_band (10) meaningful:
        a mid-tier caster (strength ~50) vs a low room (magnitude ~10) is
        CASTER_DOMINANT; vs a high room (magnitude ~80) is PLACE_DOMINANT.

    balanced_band = 10
        |caster_strength - place_magnitude| ≤ 10 → BALANCED direction.
        Low rooms (~10) and high rooms (~80) are 70 apart — far outside the
        band — so they always resolve to different directions, guaranteeing
        distinct difficulty paths in the story slice.

    backfire_base_difficulty = 30
        OPPOSED checks start at 30 (moderate challenge, below the typical
        trained-skill ceiling of ~60). Staff can raise for a harsher baseline.

    backfire_difficulty_per_magnitude = 0.500
        Added linearly: ``difficulty = base + round(magnitude * this)``.
        Low room (magnitude 10): +5 → total 35.
        High room (magnitude 80): +40 → total 70.
        The high-room backfire is dramatically harder, producing visibly
        distinct outcomes in the story-slice test matrix.

    Access via ``get_resonance_environment_config()`` in
    ``world.magic.services.resonance_environment``.
    """

    base_coefficient = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text=(
            "Scales place_magnitude * caster_alignment * severity_multiplier "
            "into raw severity. 1.000 is a neutral pass-through."
        ),
    )
    caster_power_scalar = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.500"),
        help_text=(
            "Multiplies caster aura% into the caster-strength proxy used for "
            "the defilement (CASTER_DOMINANT) magnitude comparison. "
            "Default 0.500: 100% aura → strength 50."
        ),
    )
    balanced_band = models.PositiveIntegerField(
        default=10,
        help_text=(
            "|caster_strength - place_magnitude| within this threshold → "
            "BALANCED direction. Default 10."
        ),
    )
    backfire_base_difficulty = models.PositiveIntegerField(
        default=30,
        help_text=(
            "Base target_difficulty for OPPOSED perform_check backfire rolls. "
            "Default 30 (moderate challenge)."
        ),
    )
    backfire_difficulty_per_magnitude = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.500"),
        help_text=(
            "Added to backfire_base_difficulty: "
            "difficulty = base + round(magnitude * this). "
            "Default 0.500: magnitude 10 → +5 (total 35); magnitude 80 → +40 (total 70)."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resonance_environment_config_edits",
    )

    def __str__(self) -> str:
        return f"ResonanceEnvironmentConfig(pk={self.pk})"

"""RelationshipBondPullTuning — singleton tuning surface for relationship-bond
thread-pull modulation (#1849)."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager


class RelationshipBondPullTuning(SharedMemoryModel):
    """Singleton tuning surface (pk=1) for the RELATIONSHIP_TRACK pull-modulation
    saturating curve (#1849), plus the fraught/devotion differential terms (#2034).

    Generic curve: ``bonus = round(cap * S / (S + half_saturation))`` where
    ``S = coefficient * CharacterRelationship.developed_absolute_value``. Access
    via ``get_relationship_bond_pull_tuning()`` — singleton-by-convention, no
    DB-level uniqueness constraint (mirrors ``SoulTetherConfig``).

    Fraught term — rewards a bond that is simultaneously heavily invested in
    BOTH positive and negative tracks (a love/hate dynamic), keyed on the
    smaller of the two signed sub-sums (``CharacterRelationship
    .developed_signed_sums``) so a bond that's lopsided in one direction earns
    nothing here::

        fraught = soft_cap(
            fraught_coefficient * min(pos_sum, neg_sum),
            fraught_cap,
            fraught_half_saturation,
        )

    Devotion term — rewards a bond so overwhelmingly deep that it clears a
    threshold well past the generic curve's own half-saturation point (only
    genuinely extreme devotion earns the second wind)::

        devotion = soft_cap(
            devotion_coefficient * max(0, developed_absolute_value - devotion_threshold),
            devotion_cap,
            devotion_half_saturation,
        )
    """

    objects = ArxSharedMemoryManager()

    coefficient = models.PositiveSmallIntegerField(
        default=1,
        help_text="Linear multiplier on the owner-to-threaded-person bond's "
        "developed_absolute_value.",
    )
    cap = models.PositiveSmallIntegerField(
        default=20,
        help_text="Ceiling the bonus asymptotes toward at very high bond investment.",
    )
    half_saturation = models.PositiveSmallIntegerField(
        default=30,
        help_text="Bond investment score S at which the bonus reaches half of cap.",
    )
    fraught_coefficient = models.PositiveSmallIntegerField(
        default=1,
        help_text="Linear multiplier on min(positive_sum, negative_sum) from "
        "developed_signed_sums — the fraught (love/hate) term's investment score.",
    )
    fraught_cap = models.PositiveSmallIntegerField(
        default=10,
        help_text="Ceiling the fraught bonus asymptotes toward at very high mutual "
        "positive/negative investment.",
    )
    fraught_half_saturation = models.PositiveSmallIntegerField(
        default=30,
        help_text="Fraught investment score at which the fraught bonus reaches half "
        "of fraught_cap.",
    )
    devotion_threshold = models.PositiveSmallIntegerField(
        default=60,
        help_text="developed_absolute_value must exceed this before any devotion "
        "bonus accrues — only genuinely extreme bonds earn the second wind.",
    )
    devotion_coefficient = models.PositiveSmallIntegerField(
        default=1,
        help_text="Linear multiplier on the amount developed_absolute_value exceeds "
        "devotion_threshold — the devotion term's investment score.",
    )
    devotion_cap = models.PositiveSmallIntegerField(
        default=10,
        help_text="Ceiling the devotion bonus asymptotes toward at very high "
        "above-threshold investment.",
    )
    devotion_half_saturation = models.PositiveSmallIntegerField(
        default=30,
        help_text="Devotion investment score at which the devotion bonus reaches "
        "half of devotion_cap.",
    )

    def __str__(self) -> str:
        return f"RelationshipBondPullTuning(pk={self.pk})"

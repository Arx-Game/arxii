"""RelationshipBondPullTuning — singleton tuning surface for relationship-bond
thread-pull modulation (#1849)."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager


class RelationshipBondPullTuning(SharedMemoryModel):
    """Singleton tuning surface (pk=1) for the RELATIONSHIP_TRACK pull-modulation
    saturating curve (#1849).

    ``bonus = round(cap * S / (S + half_saturation))`` where
    ``S = coefficient * CharacterRelationship.developed_absolute_value``. Access
    via ``get_relationship_bond_pull_tuning()`` — singleton-by-convention, no
    DB-level uniqueness constraint (mirrors ``SoulTetherConfig``).
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

    def __str__(self) -> str:
        return f"RelationshipBondPullTuning(pk={self.pk})"

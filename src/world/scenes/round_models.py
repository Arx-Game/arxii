"""Abstract base model for round/encounter lifecycle shared by SceneRound and CombatEncounter."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.scenes.constants import RoundStatus


class AbstractRound(SharedMemoryModel):
    """Shared scalar lifecycle fields for round/encounter models.

    Inherited by ``SceneRound`` (world.scenes) and ``CombatEncounter`` (world.combat).
    Concrete FKs (room, scene) stay on each child because their nullability and
    related_name differ between the two models.
    """

    round_number = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=30,
        choices=RoundStatus.choices,
        default=RoundStatus.BETWEEN_ROUNDS,
    )
    round_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the current declaration phase began.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

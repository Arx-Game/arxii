"""Models for the Companion substrate (#672).

Binding is archetype-selection, not a real in-room-creature target — see the
#672 spec's Decision #15. CompanionArchetype is the staff-authored catalog;
Companion (added in Task 2) is the per-PC bound instance.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.companions.constants import CompanionDomain


class CompanionArchetype(NaturalKeyMixin, SharedMemoryModel):
    """Staff-authored catalog row for a bindable companion archetype.

    A PC binds an instance of an archetype (e.g. "Direwolf") rather than a
    specific in-room creature object.
    """

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    domain = models.CharField(
        max_length=20,
        choices=CompanionDomain.choices,
        default=CompanionDomain.BEAST,
    )
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    bind_difficulty = models.PositiveSmallIntegerField(
        help_text="Feeds perform_check's target_difficulty for the bind attempt.",
    )
    capacity_cost = models.PositiveSmallIntegerField(
        help_text="Companion Capacity consumed while this archetype is bonded.",
    )

    class Meta:
        ordering = ["domain", "name"]
        verbose_name = "Companion Archetype"
        verbose_name_plural = "Companion Archetypes"

    def __str__(self) -> str:
        return self.name

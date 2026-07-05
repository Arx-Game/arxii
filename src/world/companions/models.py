"""Models for the Companion substrate (#672).

Binding is archetype-selection, not a real in-room-creature target — see the
#672 spec's Decision #15. CompanionArchetype is the staff-authored catalog;
Companion (added in Task 2) is the per-PC bound instance.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.combat.constants import OpponentTier
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
    # Combat stats for bridging into encounters/battles (#1873).
    max_health = models.PositiveSmallIntegerField(
        default=30,
        help_text="Max health when bridged into a CombatOpponent (manual mode).",
    )
    soak_value = models.PositiveSmallIntegerField(
        default=0,
        help_text="Damage mitigation when bridged into a CombatOpponent.",
    )
    tier = models.CharField(
        max_length=20,
        choices=OpponentTier.choices,
        default=OpponentTier.MOOK,
        help_text="Opponent tier when bridged into a CombatOpponent.",
    )
    strength = models.PositiveSmallIntegerField(
        default=5,
        help_text="Unit strength when bridged into a BattleVehicle.",
    )

    class Meta:
        ordering = ["domain", "name"]
        verbose_name = "Companion Archetype"
        verbose_name_plural = "Companion Archetypes"

    def __str__(self) -> str:
        return self.name


class Companion(SharedMemoryModel):
    """A PC's bound companion — the persistent, room-present instance.

    Domain lives on ``archetype.domain``, not duplicated here — binding is
    archetype-selection (see the docstring on ``CompanionArchetype``).
    """

    owner = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="companions",
    )
    archetype = models.ForeignKey(
        CompanionArchetype,
        on_delete=models.PROTECT,
        related_name="companions",
    )
    granting_gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.PROTECT,
        related_name="granted_companions",
        help_text="Which Gift's Thread capacity pool this companion is charged against.",
    )
    name = models.CharField(max_length=100)
    objectdb = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companion_rows",
        help_text="The in-world CompanionObject representation. Set at bind, "
        "cleared if destroyed externally or on release.",
    )
    bonded_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-bonded_at"]
        verbose_name = "Companion"
        verbose_name_plural = "Companions"

    def __str__(self) -> str:
        return f"{self.name} ({self.archetype.name})"

    @property
    def is_active(self) -> bool:
        return self.released_at is None


class CompanionDeployment(SharedMemoryModel):
    """Links a persistent ``Companion`` to its in-battle ``BattleVehicle``.

    Lives in ``companions`` (not ``battles``) per ADR-0010: the FK points from
    the more specific/dependent system (companions) at the reusable battle
    primitives, so ``battles`` stays free of a companions import — mirroring
    ``ShipDeployment`` in ``world/ships/models.py``.
    """

    companion = models.ForeignKey(
        Companion,
        on_delete=models.CASCADE,
        related_name="deployments",
    )
    battle = models.ForeignKey(
        "battles.Battle",
        on_delete=models.CASCADE,
        related_name="companion_deployments",
    )
    vehicle = models.OneToOneField(
        "battles.BattleVehicle",
        on_delete=models.CASCADE,
        related_name="companion_deployment",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["battle", "companion"]

    def __str__(self) -> str:
        return f"Deployment of companion {self.companion_id} into battle {self.battle_id}"

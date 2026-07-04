"""Ship system models (#1832).

A ship is a per-kind extension of ``buildings.Building`` (the same pattern as
``Covenant`` extending ``Organization``): ``ShipDetails.building`` is a
OneToOne primary key onto the ``Building`` row, which already carries
``fortification_level`` (the ship's hull stat) and area/ownership plumbing.

``ShipUpgradeDetails``, ``ShipConstructionDetails``, and ``ShipRepairDetails``
mirror the shape of ``world.buildings.models.FortificationUpgradeDetails``: a
OneToOne primary key onto the driving ``projects.Project``, a FK to the
target, and a nullable ``applied_at`` idempotency marker the completion
handler sets exactly once (added in a later #1832 task).
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.ships.constants import ARMAMENT_PER_LEVEL, HANDLING_PER_LEVEL, ShipUpgradeStat

# Cross-app FK string constants — centralized per the buildings/models.py
# convention (single grep target, avoids the duplicated-literal smell).
_PROJECT_FK = "projects.Project"
_PERSONA_FK = "scenes.Persona"
_COVENANT_FK = "covenants.Covenant"


class ShipType(SharedMemoryModel):
    """An authorable category of ship (Sloop, Brigantine, Galleon, ...).

    Open catalog — rows authored by staff, mirroring ``BuildingKind``. Base
    stats are PLACEHOLDER numbers pending balance passes.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    base_hull = models.PositiveSmallIntegerField(
        default=10,
        help_text="PLACEHOLDER baseline hull stat.",
    )
    base_handling = models.PositiveSmallIntegerField(
        default=10,
        help_text="PLACEHOLDER baseline handling stat.",
    )
    base_armament = models.PositiveSmallIntegerField(
        default=10,
        help_text="PLACEHOLDER baseline armament stat.",
    )
    base_crew_capacity = models.PositiveSmallIntegerField(
        default=10,
        help_text="PLACEHOLDER baseline crew capacity.",
    )
    base_cargo_capacity = models.PositiveSmallIntegerField(
        default=10,
        help_text="PLACEHOLDER baseline cargo capacity.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ShipDetails(SharedMemoryModel):
    """Per-Building ship extension — the ship-specific data on a Building.

    Composition over inheritance, mirroring ``Covenant`` extending
    ``Organization``: ``building`` decorates a ``buildings.Building`` (which
    already carries ``fortification_level``, the ship's hull stat) rather
    than duplicating that plumbing here.
    """

    building = models.OneToOneField(
        "buildings.Building",
        on_delete=models.CASCADE,
        related_name="ship_details",
        primary_key=True,
    )
    ship_type = models.ForeignKey(
        ShipType,
        on_delete=models.PROTECT,
        related_name="ships",
    )
    handling_level = models.PositiveSmallIntegerField(
        default=0,
        help_text="Persistent handling investment, raised via a SHIP_UPGRADE Project.",
    )
    armament_level = models.PositiveSmallIntegerField(
        default=0,
        help_text="Persistent armament investment, raised via a SHIP_UPGRADE Project.",
    )
    crew_capacity = models.PositiveSmallIntegerField()
    cargo_capacity = models.PositiveSmallIntegerField()
    needs_repair = models.BooleanField(
        default=False,
        help_text="Set when the ship's battle vehicle is breached; gates a SHIP_REPAIR Project.",
    )

    class Meta:
        ordering = ["building"]
        verbose_name_plural = "Ship details"

    def effective_handling(self) -> int:
        """Base handling plus the persistent per-level handling bonus."""
        return self.ship_type.base_handling + self.handling_level * HANDLING_PER_LEVEL

    def effective_armament(self) -> int:
        """Base armament plus the persistent per-level armament bonus."""
        return self.ship_type.base_armament + self.armament_level * ARMAMENT_PER_LEVEL

    def effective_hull(self) -> int:
        """The ship's hull stat — the underlying Building's fortification level.

        Battle-time integrity (damage state) is derived at the battle bridge,
        not stored here.
        """
        return self.building.fortification_level

    def __str__(self) -> str:
        return f"{self.ship_type.name} (building {self.building_id})"


class ShipDeployment(SharedMemoryModel):
    """Links a persistent ``ShipDetails`` to its in-battle ``BattleVehicle``.

    Lives in ``ships`` (not ``battles``) per ADR-0010: the FK points from the
    more specific/dependent system (ships) at the reusable battle primitives,
    so ``battles`` stays free of a ships import.
    """

    ship = models.ForeignKey(
        ShipDetails,
        on_delete=models.CASCADE,
        related_name="deployments",
    )
    battle = models.ForeignKey(
        "battles.Battle",
        on_delete=models.CASCADE,
        related_name="ship_deployments",
    )
    vehicle = models.OneToOneField(
        "battles.BattleVehicle",
        on_delete=models.CASCADE,
        related_name="ship_deployment",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["battle", "ship"]

    def __str__(self) -> str:
        return f"Deployment of {self.ship} into battle {self.battle_id}"


class ShipUpgradeDetails(SharedMemoryModel):
    """Per-(SHIP_UPGRADE Project) details payload.

    Mirrors ``FortificationUpgradeDetails``: ``target_level`` (not a delta) is
    the natural authoring unit, applied with monotonic max-set semantics on
    completion so a lower-target Project completing after a higher one
    already did can't regress the level. ``applied_at`` is the idempotency
    marker — NULL until the completion handler runs.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="ship_upgrade_details",
        primary_key=True,
    )
    ship = models.ForeignKey(
        ShipDetails,
        on_delete=models.CASCADE,
        related_name="upgrade_details",
    )
    stat = models.CharField(max_length=20, choices=ShipUpgradeStat.choices)
    target_level = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the level was applied; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        ordering = ["project"]
        verbose_name_plural = "Ship upgrade details"

    def __str__(self) -> str:
        return f"Ship upgrade -> {self.stat} level {self.target_level} for ship {self.ship_id}"


class ShipConstructionDetails(SharedMemoryModel):
    """Per-(SHIP_CONSTRUCTION Project) details payload.

    Mirrors ``BuildingConstructionDetails``: the authored intent (type, name,
    owner) for a ship that doesn't exist yet. ``resulting_ship`` is the
    idempotency link — NULL until the completion handler spawns the
    ``ShipDetails`` (and its backing ``Building``) exactly once.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="ship_construction_details",
        primary_key=True,
    )
    ship_type = models.ForeignKey(
        ShipType,
        on_delete=models.PROTECT,
        related_name="construction_details",
    )
    name = models.CharField(max_length=100)
    owner_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="constructed_ships",
    )
    owner_covenant = models.ForeignKey(
        _COVENANT_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="constructed_ships",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the ship was spawned; NULL until the handler runs. Idempotency marker.",
    )
    resulting_ship = models.OneToOneField(
        ShipDetails,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_construction",
    )

    class Meta:
        ordering = ["project"]
        verbose_name_plural = "Ship construction details"

    def __str__(self) -> str:
        return f"Ship construction '{self.name}' ({self.ship_type.name})"


class ShipRepairDetails(SharedMemoryModel):
    """Per-(SHIP_REPAIR Project) details payload.

    Mirrors the other project-details models: ``applied_at`` is NULL until
    the completion handler clears ``ShipDetails.needs_repair`` exactly once.
    """

    project = models.OneToOneField(
        _PROJECT_FK,
        on_delete=models.CASCADE,
        related_name="ship_repair_details",
        primary_key=True,
    )
    ship = models.ForeignKey(
        ShipDetails,
        on_delete=models.CASCADE,
        related_name="repair_details",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the repair was applied; NULL until the handler runs. Idempotency marker.",
    )

    class Meta:
        ordering = ["project"]
        verbose_name_plural = "Ship repair details"

    def __str__(self) -> str:
        return f"Ship repair for ship {self.ship_id}"

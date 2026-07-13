"""Models for the overworld travel system (#1855).

A data-driven route network connecting hub rooms. Players voyage through
hubs, paying AP per leg based on travel time (distance / speed).
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.travel.constants import TravelMode, VoyageStatus

# Cross-app FK string constants — centralized per the buildings/models.py convention.
_ROOMPROFILE_FK = "evennia_extensions.RoomProfile"
_PERSONA_FK = "scenes.Persona"
_SHIPTYPE_FK = "ships.ShipType"
_SHIPDETAILS_FK = "ships.ShipDetails"


class TravelHub(SharedMemoryModel):
    """A room tagged as a travel hub or embarkation point.

    TravelHubs serve two roles:
    - Transit stops (is_transit_stop=True): waypoints in the route graph
      where travelers RP during multi-leg voyages.
    - Embarkation points: rooms where voyages can start/end. Every hub
      is an embarkation point for its travel_modes; is_transit_stop only
      controls whether routes can pass through it as an intermediate waypoint.

    Voyages can only be started or ended at a TravelHub whose travel_modes
    include the voyage's travel method mode. Characters not at a TravelHub
    cannot embark.
    """

    room_profile = models.OneToOneField(
        _ROOMPROFILE_FK,
        on_delete=models.CASCADE,
        related_name="travel_hub",
        primary_key=True,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    travel_modes = models.JSONField(
        default=list,
        help_text=(
            "List of TravelMode values that can use this hub "
            '(e.g. ["LAND", "SEA"]). A pier serves SEA; a city gate serves LAND.'
        ),
    )
    is_transit_stop = models.BooleanField(
        default=True,
        help_text=(
            "If True, this hub appears as a waypoint in route BFS. "
            "If False, it's an embarkation/disembarkation point only."
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Travel Hub"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TravelRoute(SharedMemoryModel):
    """A directed edge in the overworld route graph.

    Connects two TravelHubs. Has distance (abstract units), travel_mode
    (LAND/SEA/AIR), and is_bidirectional. Routes are mode-restricted.
    """

    origin_hub = models.ForeignKey(
        TravelHub,
        on_delete=models.CASCADE,
        related_name="outbound_routes",
    )
    destination_hub = models.ForeignKey(
        TravelHub,
        on_delete=models.CASCADE,
        related_name="inbound_routes",
    )
    distance = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Abstract distance units — feeds the time computation.",
    )
    travel_mode = models.CharField(
        max_length=10,
        choices=TravelMode.choices,
        default=TravelMode.LAND,
    )
    is_bidirectional = models.BooleanField(default=True)
    difficulty_modifier = models.FloatField(
        default=1.0,
        help_text=(
            "Multiplier on travel time for route conditions (mountain pass = 1.5, highway = 0.8)."
        ),
    )
    name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("origin_hub", "destination_hub")]
        verbose_name = "Travel Route"
        ordering = ["origin_hub__name", "destination_hub__name"]

    def __str__(self) -> str:
        label = self.name or f"{self.origin_hub} → {self.destination_hub}"
        return f"{label} ({self.get_travel_mode_display()})"


class TravelMethod(SharedMemoryModel):
    """Staff-authored catalog of travel methods with speeds.

    Ships map to TravelMethod via ShipType. When ship_type is set, the
    method's effective speed for a specific ship is:
    base_speed * (ship.effective_handling() / ship_type.base_handling)
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    travel_mode = models.CharField(
        max_length=10,
        choices=TravelMode.choices,
    )
    base_speed = models.FloatField(
        validators=[MinValueValidator(0)],
        help_text="Distance units per IC hour.",
    )
    ship_type = models.ForeignKey(
        _SHIPTYPE_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="travel_methods",
        help_text=(
            "If set, this method is for a specific ship type. "
            "Speed overridden by effective_handling()."
        ),
    )
    is_default = models.BooleanField(
        default=False,
        help_text="The method every character has by default (On Foot).",
    )

    class Meta:
        verbose_name = "Travel Method"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Voyage(SharedMemoryModel):
    """Tracks a group's progress through a multi-leg overworld route.

    The leader is auto-enrolled as a VoyageParticipant. Each participant
    pays their own AP per leg. The leader initiates leg advancement and
    completion; any participant may abandon (removing only themselves).
    """

    leader = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="led_voyages",
    )
    travel_method = models.ForeignKey(
        TravelMethod,
        on_delete=models.PROTECT,
        related_name="voyages",
    )
    origin_hub = models.ForeignKey(
        TravelHub,
        on_delete=models.SET_NULL,
        null=True,
        related_name="voyages_from",
    )
    destination_hub = models.ForeignKey(
        TravelHub,
        on_delete=models.SET_NULL,
        null=True,
        related_name="voyages_to",
    )
    route_hubs = models.JSONField(
        default=list,
        help_text=(
            "Ordered list of hub PKs forming the computed route. "
            "To compute per-leg travel time/AP, re-query the TravelRoute "
            "edge between consecutive hub PKs (handling bidirectional lookup)."
        ),
    )
    current_leg_index = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=VoyageStatus.choices,
        default=VoyageStatus.IN_TRANSIT,
    )
    ship = models.OneToOneField(
        _SHIPDETAILS_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voyage",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Voyage"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Voyage {self.pk} ({self.status})"


class VoyageParticipant(SharedMemoryModel):
    """M2M through model linking characters to a Voyage."""

    voyage = models.ForeignKey(
        Voyage,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="voyage_participations",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)
    legs_traveled = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("voyage", "persona")]
        verbose_name = "Voyage Participant"

    def __str__(self) -> str:
        return f"{self.persona} on {self.voyage}"

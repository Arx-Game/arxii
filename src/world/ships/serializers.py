"""Read serializers for the ship API surface (#1832 Task 10).

Mirrors ``world/magic/serializers_sanctum.py``'s shape: a lean read-shape for
the player's "my ships" surface. Effective stats are computed via
``ShipDetails.effective_handling()``/``effective_armament()``/``effective_hull()``
(``SerializerMethodField`` — never duplicated arithmetic in the serializer).
"""

from __future__ import annotations

from rest_framework import serializers

from world.ships.models import ShipDetails, ShipType


class ShipTypeSerializer(serializers.ModelSerializer):
    """Read-shape for the authored ``ShipType`` catalog."""

    class Meta:
        model = ShipType
        fields = [
            "id",
            "name",
            "description",
            "base_hull",
            "base_handling",
            "base_armament",
            "base_crew_capacity",
            "base_cargo_capacity",
        ]
        read_only_fields = fields


class ShipDetailsSerializer(serializers.ModelSerializer):
    """Read-shape for a ship on the player's "My Ships" view.

    ``owner_covenant_id``/``owner_covenant_name`` resolve the ship's Area
    ownership cascade (see ``world.locations.services.transfer_ownership`` —
    ``complete_ship_construction`` transfers Area ownership to the
    commissioning covenant's ``Organization``, when one is given). A ship
    with no covenant deed-holder has both as ``None``.
    """

    id = serializers.IntegerField(source="building_id", read_only=True)
    ship_type = ShipTypeSerializer(read_only=True)
    effective_handling = serializers.SerializerMethodField()
    effective_armament = serializers.SerializerMethodField()
    effective_hull = serializers.SerializerMethodField()
    owner_persona_id = serializers.IntegerField(
        source="building.owner_persona_id", read_only=True, allow_null=True
    )
    owner_persona_name = serializers.SerializerMethodField()
    owner_covenant_id = serializers.SerializerMethodField()
    owner_covenant_name = serializers.SerializerMethodField()

    class Meta:
        model = ShipDetails
        fields = [
            "id",
            "ship_type",
            "effective_handling",
            "effective_armament",
            "effective_hull",
            "handling_level",
            "armament_level",
            "crew_capacity",
            "cargo_capacity",
            "needs_repair",
            "owner_persona_id",
            "owner_persona_name",
            "owner_covenant_id",
            "owner_covenant_name",
        ]
        read_only_fields = fields

    def get_effective_handling(self, obj: ShipDetails) -> int:
        return obj.effective_handling()

    def get_effective_armament(self, obj: ShipDetails) -> int:
        return obj.effective_armament()

    def get_effective_hull(self, obj: ShipDetails) -> int:
        return obj.effective_hull()

    def get_owner_persona_name(self, obj: ShipDetails) -> str | None:
        persona = obj.building.owner_persona
        return persona.name if persona is not None else None

    def _covenant_ownership(self, obj: ShipDetails):
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.locations.constants import HolderType, LocationParentType  # noqa: PLC0415
        from world.locations.models import LocationOwnership  # noqa: PLC0415

        row = (
            LocationOwnership.objects.filter(
                parent_type=LocationParentType.AREA,
                area_id=obj.building_id,
                holder_type=HolderType.ORGANIZATION,
                ended_at__isnull=True,
            )
            .select_related("holder_organization__covenant")
            .first()
        )
        if row is None:
            return None
        try:
            return row.holder_organization.covenant
        except ObjectDoesNotExist:
            return None

    def get_owner_covenant_id(self, obj: ShipDetails) -> int | None:
        covenant = self._covenant_ownership(obj)
        return covenant.pk if covenant is not None else None

    def get_owner_covenant_name(self, obj: ShipDetails) -> str | None:
        covenant = self._covenant_ownership(obj)
        return covenant.name if covenant is not None else None

"""Serializers for the Lab station API surface (#1234).

Mirrors ``world/magic/serializers_sanctum.py``'s shape: a read-only
``ModelSerializer`` for status responses, plus plain ``serializers.Serializer``
subclasses for POST body validation on the install/upgrade/repair actions.
"""

from __future__ import annotations

from rest_framework import serializers

from world.items.crafting.models import LabStationDetails


class LabStationDetailsSerializer(serializers.ModelSerializer):
    """Read-shape for LabStationDetails — status endpoint + write-endpoint bodies."""

    level = serializers.IntegerField(source="feature_instance.level", read_only=True)
    is_broken = serializers.BooleanField(read_only=True)

    class Meta:
        model = LabStationDetails
        fields = ["durability", "max_durability", "level", "is_broken"]
        read_only_fields = fields


class LabStationInstallSerializer(serializers.Serializer):
    room_profile_id = serializers.IntegerField()
    target_level = serializers.IntegerField(min_value=1)


class LabStationRepairSerializer(serializers.Serializer):
    restore_points = serializers.IntegerField(min_value=1)


class RoomFeatureProjectStartResultSerializer(serializers.Serializer):
    """Response shape for ``install``/``upgrade``.

    Both routes only ever start a ``Project`` — they do NOT synchronously
    create a ``LabStationDetails`` row, so the response is just the new
    project's pk. Matches ``StartRoomFeatureProjectAction.execute()``'s
    ``ActionResult.data`` (``actions/definitions/room_features.py``).
    """

    project_id = serializers.IntegerField()


class LabStationRepairResultSerializer(serializers.Serializer):
    """Response shape for ``repair``.

    Only the two durability fields ``RepairLabStationAction.execute()``
    actually returns (``actions/definitions/room_features.py``) —
    ``level``/``is_broken`` are NOT part of this response, unlike the
    ``GET`` status endpoint (``LabStationDetailsSerializer``).
    """

    durability = serializers.IntegerField()
    max_durability = serializers.IntegerField()

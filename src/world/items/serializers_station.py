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

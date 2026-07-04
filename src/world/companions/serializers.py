"""Read serializers for the companions API surface (#672)."""

from __future__ import annotations

from rest_framework import serializers

from world.companions.models import Companion, CompanionArchetype


class CompanionArchetypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanionArchetype
        fields = ["id", "domain", "name", "description", "bind_difficulty", "capacity_cost"]
        read_only_fields = fields


class CompanionSerializer(serializers.ModelSerializer):
    archetype = CompanionArchetypeSerializer(read_only=True)

    class Meta:
        model = Companion
        fields = ["id", "name", "archetype", "bonded_at", "released_at"]
        read_only_fields = fields

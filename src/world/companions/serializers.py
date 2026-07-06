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


class BindActionSerializer(serializers.Serializer):
    """Body serializer for the ``POST /api/companions/companions/bind/`` endpoint.

    Mirrors ``HomecomingActionSerializer`` (sanctum) — the view resolves the
    actor via ``PuppetActorMixin`` and calls ``BindCompanionAction().run()``;
    ownership/validity of the gift and archetype is validated inside the Action.
    """

    archetype_id = serializers.IntegerField()
    gift_id = serializers.IntegerField()
    name = serializers.CharField(max_length=100)


class OrderActionSerializer(serializers.Serializer):
    """Body serializer for ``POST /api/companions/companions/{id}/order/`` (#1921)."""

    order_kind = serializers.CharField(max_length=20)
    target_id = serializers.IntegerField(required=False)
    ability_id = serializers.IntegerField(required=False)
    ally_id = serializers.IntegerField(required=False)

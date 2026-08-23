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
    is_present = serializers.SerializerMethodField()

    class Meta:
        model = Companion
        fields = ["id", "name", "archetype", "bonded_at", "released_at", "is_present"]
        read_only_fields = fields

    def get_is_present(self, obj: Companion) -> bool:
        """True when the companion's live object shares the actor's current room (#3294).

        Gates the web composer's "as <companion>" emote toggle. ``actor_location_id``
        is seeded onto the serializer context by ``CompanionViewSet.get_serializer_context``;
        with no resolvable actor location, every companion reads as absent.
        """
        location_id = self.context.get("actor_location_id")
        if location_id is None or obj.objectdb_id is None:
            return False
        return obj.objectdb.db_location_id == location_id


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


class EmoteActionSerializer(serializers.Serializer):
    """Body serializer for ``POST /api/companions/companions/{id}/emote/`` (#3294)."""

    text = serializers.CharField()

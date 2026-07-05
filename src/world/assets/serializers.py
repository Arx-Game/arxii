"""Read serializers for the assets API surface (#1872)."""

from __future__ import annotations

from rest_framework import serializers

from world.assets.models import NPCAsset


class NPCAssetSerializer(serializers.ModelSerializer):
    asset_persona_name = serializers.CharField(source="asset_persona.name", read_only=True)

    class Meta:
        model = NPCAsset
        fields = ["id", "asset_persona_name", "role_context", "status", "created_at"]
        read_only_fields = fields

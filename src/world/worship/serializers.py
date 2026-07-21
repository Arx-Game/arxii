"""Serializers for worship surfaces (#2355).

``WorshippedBeingRefSerializer`` is the public reference shape (id, name,
tradition name) — safe anywhere; it never exposes pools or avatar links.
"""

from rest_framework import serializers

from world.worship.models import Miracle, WorshippedBeing


class WorshippedBeingRefSerializer(serializers.ModelSerializer):
    tradition_name = serializers.CharField(source="tradition.name", read_only=True)

    class Meta:
        model = WorshippedBeing
        fields = ["id", "name", "tradition_name"]


class MiracleSerializer(serializers.ModelSerializer):
    """Staff-facing miracle catalog serializer (#2360)."""

    being_name = serializers.CharField(source="being.name", read_only=True)

    class Meta:
        model = Miracle
        fields = [
            "id",
            "name",
            "description",
            "being_name",
            "resonance_pool_cost",
            "intervention_trigger",
            "favor_threshold",
            "narrative_text",
            "is_active",
            "sort_order",
        ]
        read_only_fields = fields

"""Serializers for worship surfaces (#2355).

``WorshippedBeingRefSerializer`` is the public reference shape (id, name,
tradition name) — safe anywhere; it never exposes pools or avatar links.
"""

from rest_framework import serializers

from world.worship.models import Miracle, WorshippedBeing, WorshipRite


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


class WorshipRiteSerializer(serializers.ModelSerializer):
    """A being's rite as the client shows it (#3777): flavor plus the tier."""

    being_name = serializers.CharField(source="being.name", read_only=True)
    kind_name = serializers.CharField(source="kind.name", read_only=True)
    tier = serializers.IntegerField(source="kind.tier", read_only=True)
    check_type_name = serializers.CharField(source="check_type.name", read_only=True)
    resonance_name = serializers.CharField(source="resonance.resonance.name", read_only=True)

    class Meta:
        model = WorshipRite
        fields = [
            "id",
            "being",
            "being_name",
            "name",
            "description",
            "kind_name",
            "tier",
            "check_type_name",
            "resonance_name",
        ]
        read_only_fields = fields

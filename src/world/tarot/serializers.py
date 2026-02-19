"""Tarot card serializers."""

from rest_framework import serializers

from world.tarot.models import NamingRitualConfig, TarotCard


class TarotCardSerializer(serializers.ModelSerializer):
    """Serializer for TarotCard with computed surname fields."""

    surname_upright = serializers.SerializerMethodField()
    surname_reversed = serializers.SerializerMethodField()

    class Meta:
        model = TarotCard
        fields = [
            "id",
            "name",
            "arcana_type",
            "suit",
            "rank",
            "latin_name",
            "description",
            "description_reversed",
            "surname_upright",
            "surname_reversed",
        ]

    def get_surname_upright(self, obj: TarotCard) -> str:
        return obj.get_surname(is_reversed=False)

    def get_surname_reversed(self, obj: TarotCard) -> str:
        return obj.get_surname(is_reversed=True)


class NamingRitualConfigSerializer(serializers.ModelSerializer):
    """Serializer for the singleton naming ritual configuration."""

    codex_entry_id = serializers.IntegerField(source="codex_entry.id", read_only=True, default=None)

    class Meta:
        model = NamingRitualConfig
        fields = ["flavor_text", "codex_entry_id"]

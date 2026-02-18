"""Tarot card serializers."""

from rest_framework import serializers

from world.tarot.models import TarotCard


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
            "surname_upright",
            "surname_reversed",
        ]

    def get_surname_upright(self, obj: TarotCard) -> str:
        return obj.get_surname(is_reversed=False)

    def get_surname_reversed(self, obj: TarotCard) -> str:
        return obj.get_surname(is_reversed=True)

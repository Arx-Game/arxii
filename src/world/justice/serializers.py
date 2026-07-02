"""Serializers for the justice API (#1765)."""

from rest_framework import serializers

from world.justice.constants import tier_for_value
from world.justice.models import PersonaHeat


class PersonaHeatSerializer(serializers.ModelSerializer):
    """One warrant row on the viewer's own crime tab — tiers only, never the raw number.

    Alleged deeds render as recorded: a false accusation reads the same as a
    true one (falsity is emergent, #1765).
    """

    area_name = serializers.CharField(source="area.name", read_only=True)
    society_name = serializers.CharField(source="society.name", read_only=True)
    tier = serializers.SerializerMethodField()
    tier_label = serializers.SerializerMethodField()
    alleged_deeds = serializers.SerializerMethodField()

    class Meta:
        model = PersonaHeat
        fields = ("id", "area_name", "society_name", "tier", "tier_label", "alleged_deeds")

    def get_tier(self, obj: PersonaHeat) -> str:
        return tier_for_value(obj.value).value

    def get_tier_label(self, obj: PersonaHeat) -> str:
        return tier_for_value(obj.value).label

    def get_alleged_deeds(self, obj: PersonaHeat) -> list[str]:
        titles = {source.deed.title for source in obj.sources.all() if source.deed is not None}
        return sorted(titles)

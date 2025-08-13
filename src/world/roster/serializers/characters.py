"""
Character-related serializers for the roster system.
"""

from django.core.exceptions import ObjectDoesNotExist
from evennia.objects.models import ObjectDB
from rest_framework import serializers


class CharacterGallerySerializer(serializers.Serializer):
    """Serialize a single gallery entry for a character."""

    name = serializers.CharField()
    url = serializers.CharField()


class CharacterSerializer(serializers.ModelSerializer):
    """Serialize character data for roster entry views."""

    name = serializers.CharField(source="db_key")
    age = serializers.IntegerField(
        source="item_data.age", read_only=True, allow_null=True
    )
    gender = serializers.CharField(
        source="item_data.gender", read_only=True, allow_null=True, allow_blank=True
    )
    race = serializers.SerializerMethodField()
    char_class = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    concept = serializers.CharField(
        source="item_data.concept", read_only=True, default=""
    )
    family = serializers.CharField(
        source="item_data.family", read_only=True, default=""
    )
    vocation = serializers.CharField(
        source="item_data.vocation", read_only=True, default=""
    )
    social_rank = serializers.IntegerField(
        source="item_data.social_rank", read_only=True, allow_null=True
    )
    background = serializers.CharField(
        source="item_data.background", read_only=True, default=""
    )
    relationships = serializers.ListField(child=serializers.CharField(), default=list)
    galleries = CharacterGallerySerializer(many=True, default=list)

    class Meta:
        model = ObjectDB
        fields = (
            "id",
            "name",
            "age",
            "gender",
            "race",
            "char_class",
            "level",
            "concept",
            "family",
            "vocation",
            "social_rank",
            "background",
            "relationships",
            "galleries",
        )
        read_only_fields = fields

    def get_race(self, obj):
        """Return race and subrace information from character data."""
        try:
            item_data = obj.item_data
            if item_data is None:
                return {"race": None, "subrace": None}
        except (AttributeError, ObjectDoesNotExist):
            return {"race": None, "subrace": None}

        race_data = {"race": None, "subrace": None}

        race = item_data.race
        if race:
            race_data["race"] = {
                "id": race.id,
                "name": race.name,
                "description": race.description,
            }

        subrace = item_data.subrace
        if subrace:
            race_data["subrace"] = {
                "id": subrace.id,
                "name": subrace.name,
                "description": subrace.description,
                "race": subrace.race.name,
            }

        return race_data

    def get_char_class(self, obj):
        # Placeholder until class system is implemented
        return None

    def get_level(self, obj):
        # Placeholder until leveling is implemented
        return None

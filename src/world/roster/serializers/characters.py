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
        source="item_data.age",
        read_only=True,
        allow_null=True,
    )
    gender = serializers.CharField(
        source="item_data.gender",
        read_only=True,
        allow_null=True,
        allow_blank=True,
    )
    race = serializers.SerializerMethodField()
    char_class = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    concept = serializers.CharField(
        source="item_data.concept",
        read_only=True,
        default="",
    )
    family = serializers.CharField(
        source="item_data.family",
        read_only=True,
        default="",
    )
    vocation = serializers.CharField(
        source="item_data.vocation",
        read_only=True,
        default="",
    )
    social_rank = serializers.IntegerField(
        source="item_data.social_rank",
        read_only=True,
        allow_null=True,
    )
    background = serializers.CharField(
        source="item_data.background",
        read_only=True,
        default="",
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
        """Return species information from character data.

        Species can have a parent for subspecies hierarchy (e.g., Rex'alfar.parent = Elven).
        """
        try:
            item_data = obj.item_data
            if item_data is None:
                return {"species": None}
        except (AttributeError, ObjectDoesNotExist):
            return {"species": None}

        race_data = {"species": None}

        species = item_data.species
        if species:
            species_data = {
                "id": species.id,
                "name": species.name,
                "description": species.description,
            }
            # Include parent info if this is a subspecies
            if species.parent:
                species_data["parent"] = {
                    "id": species.parent.id,
                    "name": species.parent.name,
                }
            race_data["species"] = species_data

        return race_data

    def get_char_class(self, _obj):
        # Placeholder until class system is implemented
        return None

    def get_level(self, _obj):
        # Placeholder until leveling is implemented
        return None

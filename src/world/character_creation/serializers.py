"""
Character Creation serializers.
"""

from rest_framework import serializers

from world.character_creation.models import CharacterDraft, SpecialHeritage, StartingArea
from world.roster.models import Family


class SpecialHeritageSerializer(serializers.ModelSerializer):
    """Serializer for special heritage options."""

    class Meta:
        model = SpecialHeritage
        fields = [
            "id",
            "name",
            "description",
            "allows_full_species_list",
            "family_display",
        ]


class StartingAreaSerializer(serializers.ModelSerializer):
    """Serializer for starting areas with accessibility check."""

    special_heritages = SpecialHeritageSerializer(many=True, read_only=True)
    is_accessible = serializers.SerializerMethodField()

    class Meta:
        model = StartingArea
        fields = [
            "id",
            "name",
            "description",
            "crest_image",
            "is_accessible",
            "special_heritages",
        ]

    def get_is_accessible(self, obj: StartingArea) -> bool:
        """Check if the requesting user can access this area."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.is_accessible_by(request.user)


class FamilySerializer(serializers.ModelSerializer):
    """Serializer for family selection."""

    class Meta:
        model = Family
        fields = ["id", "name", "family_type", "description"]


class SpeciesSerializer(serializers.Serializer):
    """Serializer for species options (stub until Species model exists)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()


class CharacterDraftSerializer(serializers.ModelSerializer):
    """Serializer for character drafts."""

    selected_area = StartingAreaSerializer(read_only=True)
    selected_area_id = serializers.PrimaryKeyRelatedField(
        queryset=StartingArea.objects.all(),
        source="selected_area",
        write_only=True,
        required=False,
        allow_null=True,
    )
    selected_heritage = SpecialHeritageSerializer(read_only=True)
    selected_heritage_id = serializers.PrimaryKeyRelatedField(
        queryset=SpecialHeritage.objects.all(),
        source="selected_heritage",
        write_only=True,
        required=False,
        allow_null=True,
    )
    family = FamilySerializer(read_only=True)
    family_id = serializers.PrimaryKeyRelatedField(
        queryset=Family.objects.all(),
        source="family",
        write_only=True,
        required=False,
        allow_null=True,
    )
    stage_completion = serializers.SerializerMethodField()

    class Meta:
        model = CharacterDraft
        fields = [
            "id",
            "current_stage",
            "selected_area",
            "selected_area_id",
            "selected_heritage",
            "selected_heritage_id",
            "species",
            "gender",
            "pronoun_subject",
            "pronoun_object",
            "pronoun_possessive",
            "age",
            "family",
            "family_id",
            "is_orphan",
            "draft_data",
            "stage_completion",
        ]
        read_only_fields = ["id", "stage_completion"]

    def get_stage_completion(self, obj: CharacterDraft) -> dict[int, bool]:
        """Get completion status for each stage."""
        return obj.get_stage_completion()

    def validate_selected_area(self, value):
        """Ensure user can access the selected area."""
        if value is None:
            return value

        request = self.context.get("request")
        if not request:
            return value

        if not value.is_accessible_by(request.user):
            msg = "You do not have access to this starting area."
            raise serializers.ValidationError(msg)
        return value

    def validate_selected_heritage(self, value):
        """Ensure heritage is valid for selected area."""
        if value is None:
            return value

        # Get the area from the request data or existing instance
        area = None
        if "selected_area" in self.initial_data:
            area_id = self.initial_data.get("selected_area_id")
            if area_id:
                area = StartingArea.objects.filter(id=area_id).first()
        elif self.instance:
            area = self.instance.selected_area

        if area and value not in area.special_heritages.all():
            msg = "This heritage is not available for the selected starting area."
            raise serializers.ValidationError(msg)
        return value


class CharacterDraftCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new draft."""

    class Meta:
        model = CharacterDraft
        fields = ["id"]
        read_only_fields = ["id"]

    def create(self, validated_data):  # noqa: ARG002
        """Create a new draft for the current user."""
        request = self.context.get("request")
        return CharacterDraft.objects.create(account=request.user)

"""
Character Creation serializers.
"""

from rest_framework import serializers

from world.character_creation.models import (
    REQUIRED_STATS,
    STAT_DISPLAY_DIVISOR,
    STAT_MAX_VALUE,
    STAT_MIN_VALUE,
    CGPointBudget,
    CharacterDraft,
    SpecialHeritage,
    SpeciesOption,
    StartingArea,
)
from world.character_sheets.models import Gender, Pronouns
from world.roster.models import Family
from world.roster.serializers import FamilySerializer
from world.species.models import Language, Species, SpeciesOrigin


class SpecialHeritageSerializer(serializers.ModelSerializer):
    """Serializer for special heritage options."""

    # Get name and description from linked Heritage model
    name = serializers.CharField(source="heritage.name", read_only=True)
    description = serializers.CharField(source="heritage.description", read_only=True)
    family_display = serializers.CharField(source="heritage.family_display", read_only=True)

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


class SpeciesSerializer(serializers.ModelSerializer):
    """ModelSerializer for Species model."""

    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)

    class Meta:
        model = Species
        fields = ["id", "name", "description", "parent", "parent_name"]


class LanguageSerializer(serializers.ModelSerializer):
    """Serializer for Language model."""

    class Meta:
        model = Language
        fields = ["id", "name", "description"]


class GenderSerializer(serializers.ModelSerializer):
    """Serializer for gender options."""

    class Meta:
        model = Gender
        fields = ["id", "key", "display_name"]


class PronounsSerializer(serializers.ModelSerializer):
    """Serializer for pronoun sets."""

    class Meta:
        model = Pronouns
        fields = ["id", "key", "display_name", "subject", "object", "possessive"]


class SpeciesOriginSerializer(serializers.ModelSerializer):
    """Serializer for SpeciesOrigin - species variants with stat bonuses."""

    species = SpeciesSerializer(read_only=True)
    stat_bonuses = serializers.SerializerMethodField()

    class Meta:
        model = SpeciesOrigin
        fields = ["id", "name", "description", "species", "stat_bonuses"]

    def get_stat_bonuses(self, obj: SpeciesOrigin) -> dict[str, int]:
        """Get stat bonuses as dictionary."""
        return obj.get_stat_bonuses_dict()


class SpeciesOptionSerializer(serializers.ModelSerializer):
    """Serializer for species options with CG costs and permissions."""

    species_origin = SpeciesOriginSerializer(read_only=True)
    # Convenience accessors for species data
    species = SpeciesSerializer(source="species_origin.species", read_only=True)
    starting_area_id = serializers.IntegerField(source="starting_area.id", read_only=True)
    starting_area_name = serializers.CharField(source="starting_area.name", read_only=True)
    is_accessible = serializers.SerializerMethodField()
    stat_bonuses = serializers.SerializerMethodField()
    starting_languages = LanguageSerializer(many=True, read_only=True)
    display_description = serializers.CharField(read_only=True)

    class Meta:
        model = SpeciesOption
        fields = [
            "id",
            "species_origin",
            "species",
            "starting_area_id",
            "starting_area_name",
            "cg_point_cost",
            "description_override",
            "display_description",
            "stat_bonuses",
            "starting_languages",
            "trust_required",
            "is_available",
            "is_accessible",
        ]

    def get_is_accessible(self, obj: SpeciesOption) -> bool:
        """Check if the requesting user can access this species option."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        try:
            return obj.is_accessible_by(request.user)
        except NotImplementedError:
            # Trust system not yet implemented, allow all
            return True

    def get_stat_bonuses(self, obj: SpeciesOption) -> dict[str, int]:
        """Get stat bonuses as dictionary."""
        return obj.get_stat_bonuses_dict()


class CGPointBudgetSerializer(serializers.ModelSerializer):
    """Serializer for CG point budget configuration."""

    class Meta:
        model = CGPointBudget
        fields = ["id", "name", "starting_points", "is_active"]
        read_only_fields = ["id"]


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
    # Species option with costs and bonuses
    selected_species_option = SpeciesOptionSerializer(read_only=True)
    selected_species_option_id = serializers.PrimaryKeyRelatedField(
        queryset=SpeciesOption.objects.all(),
        source="selected_species_option",
        write_only=True,
        required=False,
        allow_null=True,
    )
    selected_gender = GenderSerializer(read_only=True)
    selected_gender_id = serializers.PrimaryKeyRelatedField(
        queryset=Gender.objects.all(),
        source="selected_gender",
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
    # CG points computed fields
    cg_points_spent = serializers.SerializerMethodField()
    cg_points_remaining = serializers.SerializerMethodField()
    stat_bonuses = serializers.SerializerMethodField()
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
            "selected_species_option",
            "selected_species_option_id",
            "selected_gender",
            "selected_gender_id",
            "age",
            "family",
            "family_id",
            "draft_data",
            "cg_points_spent",
            "cg_points_remaining",
            "stat_bonuses",
            "stage_completion",
        ]
        read_only_fields = [
            "id",
            "cg_points_spent",
            "cg_points_remaining",
            "stat_bonuses",
            "stage_completion",
        ]

    def get_stage_completion(self, obj: CharacterDraft) -> dict[int, bool]:
        """Get completion status for each stage."""
        return obj.get_stage_completion()

    def get_cg_points_spent(self, obj: CharacterDraft) -> int:
        """Get total CG points spent."""
        return obj.calculate_cg_points_spent()

    def get_cg_points_remaining(self, obj: CharacterDraft) -> int:
        """Get remaining CG points."""
        return obj.calculate_cg_points_remaining()

    def get_stat_bonuses(self, obj: CharacterDraft) -> dict[str, int]:
        """Get stat bonuses from selected species option."""
        return obj.get_stat_bonuses_from_heritage()

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

    def validate_draft_data(self, value):
        """Validate draft_data fields, including stat allocations."""
        if not isinstance(value, dict):
            msg = "draft_data must be a dictionary"
            raise serializers.ValidationError(msg)

        # Validate stats if present
        stats = value.get("stats")
        if stats is not None:
            if not isinstance(stats, dict):
                msg = "stats must be a dictionary"
                raise serializers.ValidationError(msg)

            # Validate each stat
            for stat_name, stat_value in stats.items():
                # Check stat name is valid
                if stat_name not in REQUIRED_STATS:
                    msg = f"'{stat_name}' is not a valid stat name"
                    raise serializers.ValidationError(msg)

                # Check value is integer
                if not isinstance(stat_value, int):
                    msg = f"{stat_name} must be an integer, got {type(stat_value).__name__}"
                    raise serializers.ValidationError(msg)

                # Check value is multiple of 10
                if stat_value % STAT_DISPLAY_DIVISOR != 0:
                    msg = f"{stat_name} must be a multiple of {STAT_DISPLAY_DIVISOR}"
                    raise serializers.ValidationError(msg)

                # Check value is in valid range
                if not (STAT_MIN_VALUE <= stat_value <= STAT_MAX_VALUE):
                    msg = f"{stat_name} must be between {STAT_MIN_VALUE} and {STAT_MAX_VALUE}"
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

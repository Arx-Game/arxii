"""
Character Creation serializers.
"""

from rest_framework import serializers

from world.character_creation.models import (
    AGE_MAX,
    AGE_MIN,
    REQUIRED_STATS,
    STAT_DISPLAY_DIVISOR,
    STAT_MAX_VALUE,
    STAT_MIN_VALUE,
    Beginnings,
    CGPointBudget,
    CharacterDraft,
    StartingArea,
)
from world.character_sheets.models import Gender, Pronouns
from world.classes.models import Path, PathStage
from world.forms.models import Build, HeightBand
from world.forms.serializers import BuildSerializer, HeightBandSerializer
from world.roster.models import Family
from world.roster.serializers import FamilySerializer
from world.species.models import Language, Species


class BeginningsSerializer(serializers.ModelSerializer):
    """Serializer for Beginnings options."""

    allowed_species_ids = serializers.PrimaryKeyRelatedField(
        source="allowed_species",
        many=True,
        read_only=True,
    )
    is_accessible = serializers.SerializerMethodField()

    class Meta:
        model = Beginnings
        fields = [
            "id",
            "name",
            "description",
            "art_image",
            "family_known",
            "allowed_species_ids",
            "grants_species_languages",
            "cg_point_cost",
            "is_accessible",
        ]
        # Note: social_rank intentionally NOT included (staff-only)

    def get_is_accessible(self, obj: Beginnings) -> bool:
        """Check if the requesting user can access this option."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.is_accessible_by(request.user)


class StartingAreaSerializer(serializers.ModelSerializer):
    """Serializer for starting areas with accessibility check."""

    is_accessible = serializers.SerializerMethodField()

    class Meta:
        model = StartingArea
        fields = [
            "id",
            "name",
            "description",
            "crest_image",
            "is_accessible",
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
    stat_bonuses = serializers.SerializerMethodField()

    class Meta:
        model = Species
        fields = ["id", "name", "description", "parent", "parent_name", "stat_bonuses"]

    def get_stat_bonuses(self, obj: Species) -> dict[str, int]:
        """Get stat bonuses as dictionary."""
        return obj.get_stat_bonuses_dict()


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


class CGPointBudgetSerializer(serializers.ModelSerializer):
    """Serializer for CG point budget configuration."""

    class Meta:
        model = CGPointBudget
        fields = ["id", "name", "starting_points", "is_active"]
        read_only_fields = ["id"]


class PathSerializer(serializers.ModelSerializer):
    """Serializer for Path in CG context."""

    aspects = serializers.SerializerMethodField()

    class Meta:
        model = Path
        fields = [
            "id",
            "name",
            "description",
            "stage",
            "minimum_level",
            "icon_url",
            "aspects",
        ]

    def get_aspects(self, obj: Path) -> list[str]:
        """
        Get aspect names only (weights are staff-only, not exposed to players).

        Uses the model's aspect_names property which handles prefetched data
        via Prefetch(..., to_attr='_prefetched_path_aspects') to avoid
        SharedMemoryModel cache pollution.
        """
        return obj.aspect_names


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
    selected_beginnings = BeginningsSerializer(read_only=True)
    selected_beginnings_id = serializers.PrimaryKeyRelatedField(
        queryset=Beginnings.objects.all(),
        source="selected_beginnings",
        write_only=True,
        required=False,
        allow_null=True,
    )
    # Species selection
    selected_species = SpeciesSerializer(read_only=True)
    selected_species_id = serializers.PrimaryKeyRelatedField(
        queryset=Species.objects.all(),
        source="selected_species",
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
    # Appearance fields
    height_band = HeightBandSerializer(read_only=True)
    height_band_id = serializers.PrimaryKeyRelatedField(
        queryset=HeightBand.objects.filter(is_cg_selectable=True),
        source="height_band",
        write_only=True,
        required=False,
        allow_null=True,
    )
    height_inches = serializers.IntegerField(required=False, allow_null=True)
    build = BuildSerializer(read_only=True)
    build_id = serializers.PrimaryKeyRelatedField(
        queryset=Build.objects.filter(is_cg_selectable=True),
        source="build",
        write_only=True,
        required=False,
        allow_null=True,
    )
    # Path selection
    selected_path = PathSerializer(read_only=True)
    selected_path_id = serializers.PrimaryKeyRelatedField(
        queryset=Path.objects.filter(stage=PathStage.QUIESCENT, is_active=True),
        source="selected_path",
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
            "selected_beginnings",
            "selected_beginnings_id",
            "selected_species",
            "selected_species_id",
            "selected_gender",
            "selected_gender_id",
            "age",
            "family",
            "family_id",
            "height_band",
            "height_band_id",
            "height_inches",
            "build",
            "build_id",
            "selected_path",
            "selected_path_id",
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
        """Get stat bonuses from selected species."""
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

    def validate_selected_beginnings(self, value):
        """Ensure beginnings is valid for selected area."""
        if value is None:
            return value

        # Get the area from the request data or existing instance
        area = None
        if "selected_area_id" in self.initial_data:
            area_id = self.initial_data.get("selected_area_id")
            if area_id:
                area = StartingArea.objects.filter(id=area_id).first()
        elif self.instance:
            area = self.instance.selected_area

        if area and value.starting_area != area:
            msg = "This beginnings option is not available for the selected starting area."
            raise serializers.ValidationError(msg)

        # Also check accessibility by user
        request = self.context.get("request")
        if request and not value.is_accessible_by(request.user):
            msg = "You do not have access to this beginnings option."
            raise serializers.ValidationError(msg)

        return value

    def validate_selected_species(self, value):
        """Ensure species is valid for selected beginnings."""
        if value is None:
            return value

        # Get beginnings from request data or existing instance
        beginnings = None
        if "selected_beginnings_id" in self.initial_data:
            beginnings_id = self.initial_data.get("selected_beginnings_id")
            if beginnings_id:
                beginnings = Beginnings.objects.filter(id=beginnings_id).first()
        elif self.instance:
            beginnings = self.instance.selected_beginnings

        if beginnings:
            available_species = beginnings.get_available_species()
            if value not in available_species:
                msg = "This species is not available for the selected beginnings."
                raise serializers.ValidationError(msg)

        return value

    def validate_age(self, value):
        """Validate age is within allowed range for character creation."""
        if value is None:
            return value

        if value < AGE_MIN or value > AGE_MAX:
            msg = f"Age must be between {AGE_MIN} and {AGE_MAX} years."
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

    def validate(self, attrs):
        """Cross-field validation."""
        height_band = attrs.get("height_band") or (
            self.instance.height_band if self.instance else None
        )
        height_inches = attrs.get("height_inches")

        if height_inches is not None and height_band is not None:
            if not (height_band.min_inches <= height_inches <= height_band.max_inches):
                raise serializers.ValidationError(
                    {
                        "height_inches": (
                            f"Must be between {height_band.min_inches} and "
                            f"{height_band.max_inches} for {height_band.display_name}."
                        )
                    }
                )

        return attrs


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

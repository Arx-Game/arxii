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
    DraftAnimaRitual,
    DraftGift,
    DraftMotif,
    DraftMotifResonance,
    DraftMotifResonanceAssociation,
    DraftTechnique,
    StartingArea,
)
from world.character_sheets.models import Gender, Pronouns
from world.classes.models import Path, PathStage
from world.forms.models import Build, HeightBand
from world.forms.serializers import BuildSerializer, HeightBandSerializer
from world.magic.models import Restriction
from world.mechanics.models import ModifierType
from world.roster.models import Family
from world.roster.serializers import FamilySerializer
from world.species.models import Language, Species


class BeginningsSerializer(serializers.ModelSerializer):
    """Serializer for Beginnings options."""

    allowed_species_ids = serializers.SerializerMethodField()
    is_accessible = serializers.SerializerMethodField()

    def get_allowed_species_ids(self, obj: Beginnings) -> list[int]:
        """
        Get IDs of species available for this Beginnings, expanding parents to children.

        Uses get_available_species() which expands parent species (e.g., "Human") to
        their child subspecies. This ensures the frontend receives IDs that match
        the leaf species it fetches with has_parent=true.
        """
        return list(obj.get_available_species().values_list("id", flat=True))

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
            "icon_name",
            "aspects",
        ]

    def get_aspects(self, obj: Path) -> list[str]:
        """
        Get aspect names only (weights are staff-only, not exposed to players).

        Uses the model's cached_path_aspects property which is populated by
        Prefetch(..., to_attr='cached_path_aspects') in the ViewSet. This
        avoids SharedMemoryModel cache pollution and provides a single cache
        to invalidate when needed.
        """
        return [pa.aspect.name for pa in obj.cached_path_aspects]


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
        queryset=Path.objects.filter(stage=PathStage.PROSPECT, is_active=True),
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
        """Validate draft_data fields, including stat allocations and goals."""
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

        # Validate goals if present
        goals = value.get("goals")
        if goals is not None:
            value["goals"] = self._validate_goals(goals)

        return value

    def _validate_goals(self, goals: list) -> list:
        """
        Validate goals data.

        Since draft_data is a JSONField, we can only store serializable data (PKs).
        This method validates that domain IDs/names are valid, then stores PKs.
        The finalize_character service builds instances from these validated PKs.

        Args:
            goals: List of goal dicts with domain (name or id), points, text

        Returns:
            Validated goals list with domain_id (PK), points, notes - JSON-serializable

        Raises:
            serializers.ValidationError: If validation fails
        """
        from world.mechanics.models import ModifierType  # noqa: PLC0415

        if not isinstance(goals, list):
            msg = "goals must be a list"
            raise serializers.ValidationError(msg)

        # Cache valid domains for efficiency
        valid_domains = {
            mt.name.lower(): mt for mt in ModifierType.objects.filter(category__name="goal")
        }
        valid_domain_ids = {mt.id for mt in valid_domains.values()}

        validated_goals = []
        for goal in goals:
            if not isinstance(goal, dict):
                msg = "Each goal must be a dictionary"
                raise serializers.ValidationError(msg)

            points = goal.get("points", 0)
            notes = goal.get("text", "")

            # Resolve domain - accept either domain_id (PK) or domain (name)
            domain_id = goal.get("domain_id")
            domain_name = goal.get("domain")

            if domain_id is not None:
                # Validate PK exists
                if domain_id not in valid_domain_ids:
                    msg = f"Invalid goal domain ID: {domain_id}"
                    raise serializers.ValidationError(msg)
                resolved_id = domain_id
            elif domain_name:
                # Validate name and resolve to PK
                domain = valid_domains.get(domain_name.lower())
                if domain is None:
                    msg = f"Invalid goal domain: '{domain_name}'"
                    raise serializers.ValidationError(msg)
                resolved_id = domain.id
            else:
                msg = "Each goal must have either domain_id or domain"
                raise serializers.ValidationError(msg)

            # Validate points
            if not isinstance(points, int) or points < 0:
                msg = "Goal points must be a non-negative integer"
                raise serializers.ValidationError(msg)

            # Store JSON-serializable data (PKs, not instances)
            validated_goals.append(
                {
                    "domain_id": resolved_id,
                    "points": points,
                    "notes": notes,
                }
            )

        return validated_goals

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


class DraftTechniqueSerializer(serializers.ModelSerializer):
    """Serializer for DraftTechnique model."""

    restrictions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Restriction.objects.all(),
        required=False,
    )
    calculated_power = serializers.SerializerMethodField()

    class Meta:
        model = DraftTechnique
        fields = [
            "id",
            "gift",
            "name",
            "style",
            "effect_type",
            "restrictions",
            "level",
            "description",
            "calculated_power",
        ]
        read_only_fields = ["id", "calculated_power"]

    def get_calculated_power(self, obj) -> int | None:
        return obj.calculated_power


class DraftGiftSerializer(serializers.ModelSerializer):
    """Serializer for DraftGift model."""

    resonances = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ModifierType.objects.filter(category__name="resonance"),
        required=False,
    )
    techniques = DraftTechniqueSerializer(many=True, read_only=True)

    class Meta:
        model = DraftGift
        fields = [
            "id",
            "name",
            "affinity",
            "resonances",
            "description",
            "techniques",
        ]
        read_only_fields = ["id", "techniques"]


class DraftMotifResonanceAssociationSerializer(serializers.ModelSerializer):
    """Serializer for DraftMotifResonanceAssociation model."""

    class Meta:
        model = DraftMotifResonanceAssociation
        fields = ["id", "motif_resonance", "association"]
        read_only_fields = ["id"]


class DraftMotifResonanceSerializer(serializers.ModelSerializer):
    """Serializer for DraftMotifResonance model."""

    associations = DraftMotifResonanceAssociationSerializer(many=True, read_only=True)

    class Meta:
        model = DraftMotifResonance
        fields = ["id", "motif", "resonance", "is_from_gift", "associations"]
        read_only_fields = ["id", "associations"]


class DraftMotifSerializer(serializers.ModelSerializer):
    """Serializer for DraftMotif model."""

    resonances = DraftMotifResonanceSerializer(many=True, read_only=True)

    class Meta:
        model = DraftMotif
        fields = ["id", "description", "resonances"]
        read_only_fields = ["id", "resonances"]


class DraftAnimaRitualSerializer(serializers.ModelSerializer):
    """Serializer for DraftAnimaRitual model."""

    class Meta:
        model = DraftAnimaRitual
        fields = ["id", "stat", "skill", "specialization", "resonance", "description"]
        read_only_fields = ["id"]

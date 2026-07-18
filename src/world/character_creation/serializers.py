"""
Character Creation serializers.
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.character_creation.constants import (
    STAT_MAX_VALUE,
    STAT_MIN_VALUE,
)
from world.character_creation.models import (
    AGE_MAX,
    AGE_MIN,
    REQUIRED_STATS,
    Beginnings,
    CGExplanation,
    CGPointBudget,
    CharacterDraft,
    DraftApplication,
    DraftApplicationComment,
    OriginTemplate,
    OriginTemplateSlot,
    StartingArea,
)
from world.character_creation.types import StageValidationErrors
from world.character_sheets.models import Gender, Pronouns
from world.classes.models import Path, PathStage
from world.distinctions.models import Distinction
from world.forms.models import Build, HeightBand
from world.forms.serializers import BuildSerializer, HeightBandSerializer
from world.magic.models import Gift, GlimpseTag, Technique, Tradition
from world.mechanics.constants import GOAL_CATEGORY_NAME
from world.roster.models import Family, KinSlotPool, Kinsperson
from world.roster.serializers import FamilySerializer
from world.societies.houses.models import (
    HouseAspectDefinition,
    HouseAspectOption,
    HouseClaim,
    HouseFeature,
    HouseTemplate,
    Title,
)
from world.species.models import Language, Species
from world.worship.models import WorshippedBeing
from world.worship.serializers import WorshippedBeingRefSerializer


class BeginningsSerializer(serializers.ModelSerializer):
    """Serializer for Beginnings options."""

    allowed_species_ids = serializers.SerializerMethodField()
    is_accessible = serializers.SerializerMethodField()
    art_image = serializers.SerializerMethodField()
    codex_entry_ids = serializers.SerializerMethodField()

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
            "codex_entry_ids",
        ]
        # Note: social_rank intentionally NOT included (staff-only)

    def get_is_accessible(self, obj: Beginnings) -> bool:
        """Check if the requesting user can access this option."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.is_accessible_by(request.user)

    def get_art_image(self, obj: Beginnings) -> str | None:
        """Cloudinary URL sourced from art (#2408); key name kept for frontend compat."""
        return obj.art.cloudinary_url if obj.art_id else None

    def get_codex_entry_ids(self, obj: Beginnings) -> list[int]:
        """Get codex entry IDs granted by this beginnings choice."""
        return [grant.entry_id for grant in obj.cached_codex_grants]


class StartingAreaSerializer(serializers.ModelSerializer):
    """Serializer for starting areas with accessibility check."""

    is_accessible = serializers.SerializerMethodField()
    realm_theme = serializers.CharField(source="realm.theme", read_only=True, default="default")
    crest_image = serializers.SerializerMethodField()

    class Meta:
        model = StartingArea
        fields = [
            "id",
            "name",
            "description",
            "crest_image",
            "is_accessible",
            "realm_theme",
        ]

    def get_is_accessible(self, obj: StartingArea) -> bool:
        """Check if the requesting user can access this area."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.is_accessible_by(request.user)

    def get_crest_image(self, obj: StartingArea) -> str | None:
        """Cloudinary URL sourced from crest_art (#2408); key name kept for frontend compat."""
        return obj.crest_art.cloudinary_url if obj.crest_art_id else None


class SpeciesSerializer(serializers.ModelSerializer):
    """ModelSerializer for Species model."""

    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)
    stat_bonuses = serializers.SerializerMethodField()
    codex_entry_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Species
        fields = [
            "id",
            "name",
            "description",
            "parent",
            "parent_name",
            "stat_bonuses",
            "codex_entry_id",
        ]

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
        fields = ["id", "name", "starting_points", "xp_conversion_rate", "is_active"]
        read_only_fields = ["id"]


class PathSerializer(serializers.ModelSerializer):
    """Serializer for Path in CG context."""

    aspects = serializers.SerializerMethodField()
    codex_entry_ids = serializers.SerializerMethodField()

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
            "codex_entry_ids",
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

    def get_codex_entry_ids(self, obj: Path) -> list[int]:
        """Get codex entry IDs granted by this path.

        Read from ``cached_codex_grants`` populated by the ViewSet prefetch.
        """
        return [grant.entry_id for grant in obj.cached_codex_grants]


class TraditionSerializer(serializers.ModelSerializer):
    """Serializer for Tradition records available during CG."""

    codex_entry_ids = serializers.SerializerMethodField()
    required_distinction_id = serializers.SerializerMethodField()

    class Meta:
        model = Tradition
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "sort_order",
            "codex_entry_ids",
            "required_distinction_id",
        ]
        read_only_fields = fields

    def get_codex_entry_ids(self, obj) -> list[int]:
        """Get codex entry IDs granted by this tradition.

        Read from the ``cached_codex_grants`` attr populated by the
        ``Beginnings.cached_beginning_traditions`` prefetch. Same data for
        every caller (no per-request filter), so attaching to the shared
        Tradition instance is safe.
        """
        # cached_codex_grants is a cached_property (never None) — the shared
        # Prefetch/query interface, #2386.
        return [grant.entry_id for grant in obj.cached_codex_grants]

    def get_required_distinction_id(self, obj) -> int | None:
        """Get the required distinction ID from the BeginningTradition context.

        The view computes a ``{tradition_id: BeginningTradition}`` dict per
        request and passes it via context. We do NOT attach the BT row to
        ``obj`` (a SharedMemoryModel ``Tradition``) via ``Prefetch(to_attr=)``
        because that attribute would persist across requests with different
        ``beginning_id`` values and leak filtered data between users.
        """
        bt_map = self.context.get("beginning_traditions_by_tradition")
        if bt_map is not None:
            bt = bt_map.get(obj.id)
            return bt.required_distinction_id if bt and bt.required_distinction_id else None

        # Fallback for callers that didn't pre-compute the map (e.g. nested
        # use in CharacterDraftSerializer where context is set up differently).
        beginning_id = self.context.get("beginning_id")
        if not beginning_id:
            return None
        from world.character_creation.models import BeginningTradition  # noqa: PLC0415

        bt = (
            BeginningTradition.objects.filter(beginning_id=beginning_id, tradition=obj)
            .select_related("required_distinction")
            .first()
        )
        if bt and bt.required_distinction_id:
            return bt.required_distinction_id
        return None


class CGGiftOptionSerializer(serializers.ModelSerializer):
    """Gift row for the CG gift-options list (#2426).

    Backs ``GET /api/character-creation/gifts/?draft_id=<id>`` — a gift the
    draft's selected tradition + path make pickable (see
    ``world.magic.services.cg_catalog.get_gift_options``).
    """

    codex_entry_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Gift
        fields = ["id", "name", "description", "kind", "codex_entry_id"]
        read_only_fields = fields


class CGTechniqueOptionSerializer(serializers.ModelSerializer):
    """Technique row for the CG technique-options list (#2426).

    Backs ``GET /api/character-creation/technique-options/?draft_id=<id>&gift_id=<id>``
    — the pool ∪ signature availability set for one (path, gift, tradition) pick
    (see ``world.magic.services.cg_catalog.get_technique_options``). ``is_signature``
    is resolved from the ``signature_technique_ids`` set the ViewSet places in the
    serializer context — never attached to the (SharedMemoryModel) ``Technique``
    instance itself, to avoid leaking one request's filtered flag into another's
    cached row (see the ``required_distinction_id`` comment above).
    """

    category = serializers.CharField(source="effect_type.category", read_only=True)
    codex_entry_id = serializers.IntegerField(read_only=True, allow_null=True)
    is_signature = serializers.SerializerMethodField()

    class Meta:
        model = Technique
        fields = ["id", "name", "description", "category", "codex_entry_id", "is_signature"]
        read_only_fields = fields

    def get_is_signature(self, obj: Technique) -> bool:
        """True when this technique came from the tradition's signature set."""
        return obj.id in self.context.get("signature_technique_ids", set())


class CGGlimpseTagSuggestedDistinctionSerializer(serializers.ModelSerializer):
    """Distinction stub embedded in a glimpse tag's suggestion list (#2427)."""

    class Meta:
        model = Distinction
        fields = ["id", "name"]
        read_only_fields = fields


class CGGlimpseTagSerializer(serializers.ModelSerializer):
    """Glimpse tag row for the CG guided flow (#2427).

    Backs ``GET /api/character-creation/glimpse-tags/``. Curated distinction
    suggestions are embedded per tag (prefetched); the client dedupes across
    the chosen tag set.
    """

    suggested_distinctions = serializers.SerializerMethodField()

    class Meta:
        model = GlimpseTag
        fields = [
            "id",
            "axis",
            "name",
            "slug",
            "description",
            "example",
            "sort_order",
            "suggested_distinctions",
        ]
        read_only_fields = fields

    @extend_schema_field(CGGlimpseTagSuggestedDistinctionSerializer(many=True))
    def get_suggested_distinctions(self, obj: GlimpseTag) -> list[dict]:
        rows = obj.cached_distinction_suggestions  # Prefetch(to_attr=...), ordered
        return CGGlimpseTagSuggestedDistinctionSerializer(
            [row.distinction for row in rows], many=True
        ).data


class OriginTemplateSlotSerializer(serializers.ModelSerializer):
    """Slot prompt within an origin template (#2478)."""

    class Meta:
        model = OriginTemplateSlot
        fields = ["id", "name", "prompt", "example", "sort_order", "is_required"]
        read_only_fields = fields


class CGOriginTemplateSerializer(serializers.ModelSerializer):
    """Origin template for the CG guided flow (#2478).

    Backs ``GET /api/character-creation/origin-templates/``.
    """

    slots = serializers.SerializerMethodField()

    class Meta:
        model = OriginTemplate
        fields = ["id", "name", "frame_narrative", "is_active", "sort_order", "slots"]
        read_only_fields = fields

    @extend_schema_field(OriginTemplateSlotSerializer(many=True))
    def get_slots(self, obj: OriginTemplate) -> list[dict]:
        """Return nested slots, preferring the prefetched ``cached_slots`` attr."""
        slots = (
            obj.cached_slots if hasattr(obj, "cached_slots") else obj.slots.order_by("sort_order")
        )
        return OriginTemplateSlotSerializer(slots, many=True).data


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
    # Worship declarations (#2355) — the draft is owner-facing, so the secret pick
    # is visible here; it never leaves the draft/owner surfaces post-finalization.
    public_worship = WorshippedBeingRefSerializer(read_only=True)
    public_worship_id = serializers.PrimaryKeyRelatedField(
        queryset=WorshippedBeing.objects.filter(is_active=True),
        source="public_worship",
        write_only=True,
        required=False,
        allow_null=True,
    )
    secret_worship = WorshippedBeingRefSerializer(read_only=True)
    secret_worship_id = serializers.PrimaryKeyRelatedField(
        queryset=WorshippedBeing.objects.filter(is_active=True),
        source="secret_worship",
        write_only=True,
        required=False,
        allow_null=True,
    )
    # Kinship slot claim (#2062)
    claimed_kin_slot_id = serializers.PrimaryKeyRelatedField(
        queryset=Kinsperson.objects.filter(is_appable=True, sheet__isnull=True),
        source="claimed_kin_slot",
        write_only=True,
        required=False,
        allow_null=True,
    )
    claimed_kin_pool_id = serializers.PrimaryKeyRelatedField(
        queryset=KinSlotPool.objects.filter(count_remaining__gt=0),
        source="claimed_kin_pool",
        write_only=True,
        required=False,
        allow_null=True,
    )
    defer_parents = serializers.BooleanField(required=False)
    claimed_kin_slot = serializers.PrimaryKeyRelatedField(read_only=True)
    claimed_kin_pool = serializers.PrimaryKeyRelatedField(read_only=True)
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
    # Tradition selection — SerializerMethodField (not a nested declaration) so
    # we can inject ``beginning_id`` into the TraditionSerializer's context per
    # draft. The nested serializer's ``required_distinction_id`` resolves a
    # BeginningTradition row keyed on (beginning_id, tradition_id); without
    # the per-draft beginning_id it always returned None.
    selected_tradition = serializers.SerializerMethodField()
    selected_tradition_id = serializers.PrimaryKeyRelatedField(
        queryset=Tradition.objects.filter(is_active=True),
        source="selected_tradition",
        write_only=True,
        required=False,
        allow_null=True,
    )
    # Whether account has existing characters (for advanced CG options)
    has_existing_characters = serializers.SerializerMethodField()
    # CG points computed fields
    cg_points_spent = serializers.SerializerMethodField()
    cg_points_remaining = serializers.SerializerMethodField()
    stat_bonuses = serializers.SerializerMethodField()
    stage_completion = serializers.SerializerMethodField()
    stage_errors = serializers.SerializerMethodField()
    stats_points_remaining = serializers.SerializerMethodField()
    stats_budget = serializers.SerializerMethodField()
    # Gift-stage technique pick budget (#2426 Task 10) — CharacterDraft property,
    # base 1 + any distinction bonus; the GiftStage funnel's technique picker
    # needs it for the "n of m chosen" budget banner.
    starting_technique_picks = serializers.IntegerField(read_only=True)

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
            "claimed_kin_slot",
            "claimed_kin_slot_id",
            "claimed_kin_pool",
            "claimed_kin_pool_id",
            "defer_parents",
            "height_band",
            "height_band_id",
            "height_inches",
            "build",
            "build_id",
            "selected_path",
            "selected_path_id",
            "selected_tradition",
            "selected_tradition_id",
            "public_worship",
            "public_worship_id",
            "secret_worship",
            "secret_worship_id",
            "draft_data",
            "has_existing_characters",
            "cg_points_spent",
            "cg_points_remaining",
            "stat_bonuses",
            "stage_completion",
            "stage_errors",
            "stats_points_remaining",
            "stats_budget",
            "starting_technique_picks",
        ]
        read_only_fields = [
            "id",
            "has_existing_characters",
            "cg_points_spent",
            "cg_points_remaining",
            "stat_bonuses",
            "stage_completion",
            "stage_errors",
            "stats_points_remaining",
            "stats_budget",
            "starting_technique_picks",
        ]

    def get_has_existing_characters(self, obj: CharacterDraft) -> bool:
        """True if account has any active roster tenure (for advanced CG options)."""
        from world.roster.models import RosterEntry  # noqa: PLC0415

        return RosterEntry.objects.for_account(obj.account).exists()

    def get_selected_tradition(self, obj: CharacterDraft) -> dict | None:
        """Render the selected tradition with this draft's beginning_id in context.

        TraditionSerializer.required_distinction_id resolves a BeginningTradition
        row keyed on (beginning_id, tradition_id). Drafts carry both pieces of
        state directly, so we inject ``beginning_id`` into a per-draft context
        rather than relying on the list endpoint's pre-built map.
        """
        if obj.selected_tradition is None:
            return None
        nested_context = dict(self.context)
        nested_context["beginning_id"] = obj.selected_beginnings_id
        return TraditionSerializer(obj.selected_tradition, context=nested_context).data

    def get_stage_completion(self, obj: CharacterDraft) -> dict[int, bool]:
        """Get completion status for each stage."""
        return obj.get_stage_completion()

    def get_stage_errors(self, obj: CharacterDraft) -> StageValidationErrors:
        """Get validation errors for each stage."""
        return obj.get_stage_validation_errors()

    def get_cg_points_spent(self, obj: CharacterDraft) -> int:
        """Get total CG points spent."""
        return obj.calculate_cg_points_spent()

    def get_cg_points_remaining(self, obj: CharacterDraft) -> int:
        """Get remaining CG points."""
        return obj.calculate_cg_points_remaining()

    def get_stat_bonuses(self, obj: CharacterDraft) -> dict[str, int]:
        """Get stat bonuses from all sources (heritage + distinctions)."""
        return obj.get_all_stat_bonuses()

    def get_stats_points_remaining(self, obj: CharacterDraft) -> int:
        """Get remaining stat points to allocate (0 = fully allocated)."""
        return obj.calculate_points_remaining()

    def get_stats_budget(self, obj: CharacterDraft) -> int:
        """Get total stat point budget (base + bonuses)."""
        return obj.calculate_stat_budget()

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
        _area_id_key = "selected_area_id"
        if _area_id_key in self.initial_data:
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
        _beginnings_id_key = "selected_beginnings_id"
        if _beginnings_id_key in self.initial_data:
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

    def update(self, instance, validated_data):
        """Merge ``draft_data`` keys on partial update instead of replacing the blob.

        The wizard's stages save independently (debounced skills, slider commits,
        navigation-triggered saves) — whole-blob replacement made every PATCH a
        last-write-wins race over a snapshot of the client cache, silently
        reverting sibling stages' keys (2026-07 audit). A key set to ``null``
        still clears it; omitted keys are untouched.
        """
        incoming = validated_data.pop("draft_data", None)
        if incoming is not None:
            validated_data["draft_data"] = {**instance.draft_data, **incoming}
        return super().update(instance, validated_data)

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

                # Check value is in valid range (1-5)
                if not (STAT_MIN_VALUE <= stat_value <= STAT_MAX_VALUE):
                    msg = f"{stat_name} must be between {STAT_MIN_VALUE} and {STAT_MAX_VALUE}"
                    raise serializers.ValidationError(msg)

        # Validate tarot card selection
        self._validate_tarot_card_name(value)

        # Validate goals if present
        goals = value.get("goals")
        if goals is not None:
            value["goals"] = self._validate_goals(goals)

        return value

    def _validate_tarot_card_name(self, data: dict) -> None:
        """Validate that tarot_card_name refers to an existing TarotCard."""
        tarot_card_name = data.get("tarot_card_name")
        if tarot_card_name is not None:
            from world.tarot.models import TarotCard  # noqa: PLC0415

            if not TarotCard.objects.filter(name=tarot_card_name).exists():
                raise serializers.ValidationError(
                    {"tarot_card_name": f"Unknown tarot card: {tarot_card_name}"}
                )

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
        from world.mechanics.models import ModifierTarget  # noqa: PLC0415

        if not isinstance(goals, list):
            msg = "goals must be a list"
            raise serializers.ValidationError(msg)

        # Cache valid domains for efficiency
        valid_domains = {
            mt.name.lower(): mt
            for mt in ModifierTarget.objects.filter(category__name=GOAL_CATEGORY_NAME)
        }
        valid_domain_ids = {mt.id for mt in valid_domains.values()}

        validated_goals = []
        for goal in goals:
            if not isinstance(goal, dict):
                msg = "Each goal must be a dictionary"
                raise serializers.ValidationError(msg)

            points = goal.get("points", 0)
            notes = goal.get("notes", goal.get("text", ""))

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


class DraftApplicationCommentSerializer(serializers.ModelSerializer):
    """Serializer for comments on draft applications."""

    author_name = serializers.SerializerMethodField()

    class Meta:
        model = DraftApplicationComment
        fields = ["id", "author", "author_name", "text", "comment_type", "created_at"]
        read_only_fields = ["id", "author", "author_name", "comment_type", "created_at"]

    def get_author_name(self, obj: DraftApplicationComment) -> str | None:
        if obj.author:
            return obj.author.username
        return None


class DraftApplicationSerializer(serializers.ModelSerializer):
    """Serializer for draft applications (list view)."""

    draft_name = serializers.SerializerMethodField()
    player_name = serializers.SerializerMethodField()
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = DraftApplication
        fields = [
            "id",
            "draft",
            "draft_name",
            "player_name",
            "status",
            "submitted_at",
            "reviewer",
            "reviewer_name",
            "reviewed_at",
            "submission_notes",
            "expires_at",
        ]
        read_only_fields = fields

    def get_draft_name(self, obj: DraftApplication) -> str:
        if obj.draft:
            return obj.draft.draft_data.get("first_name", "Unnamed")
        return obj.character_name or "Unknown"

    def get_player_name(self, obj: DraftApplication) -> str:
        if obj.draft:
            return obj.draft.account.username
        return obj.player_account.username if obj.player_account else "Unknown"

    def get_reviewer_name(self, obj: DraftApplication) -> str | None:
        if obj.reviewer:
            return obj.reviewer.username
        return None


class DraftApplicationDetailSerializer(DraftApplicationSerializer):
    """Serializer for draft application detail view with comments and draft summary."""

    comments = DraftApplicationCommentSerializer(
        source="cached_comments", many=True, read_only=True
    )
    draft_summary = serializers.SerializerMethodField()

    class Meta(DraftApplicationSerializer.Meta):
        fields = [*DraftApplicationSerializer.Meta.fields, "comments", "draft_summary"]

    def get_draft_summary(self, obj: DraftApplication) -> dict:
        draft = obj.draft
        if draft is None:
            return {
                "id": None,
                "first_name": obj.character_name or "Unknown",
                "description": "",
                "personality": "",
                "background": "",
                "species": None,
                "area": None,
                "beginnings": None,
                "family": None,
                "gender": None,
                "age": None,
                "stage_completion": {},
            }
        return {
            "id": draft.id,
            "first_name": draft.draft_data.get("first_name", ""),
            "description": draft.draft_data.get("description", ""),
            "personality": draft.draft_data.get("personality", ""),
            "background": draft.draft_data.get("background", ""),
            "species": draft.selected_species.name if draft.selected_species else None,
            "area": draft.selected_area.name if draft.selected_area else None,
            "beginnings": draft.selected_beginnings.name if draft.selected_beginnings else None,
            "family": draft.family.name if draft.family else None,
            "gender": draft.selected_gender.display_name if draft.selected_gender else None,
            "age": draft.age,
            "stage_completion": draft.get_stage_completion(),
        }


class CGExplanationsSerializer:
    """Serializes all CG explanatory text as a flat dict: {key: text, ...}."""

    @staticmethod
    def to_dict() -> dict[str, str]:
        return {obj.key: obj.text for obj in CGExplanation.objects.all()}


# ---------------------------------------------------------------------------
# House creator (#1884 Phase D) — claimable titles + claim status for CG
# ---------------------------------------------------------------------------


class HouseAspectOptionSerializer(serializers.ModelSerializer):
    """One authored answer in an aspect catalog (#2079)."""

    class Meta:
        model = HouseAspectOption
        fields = ["id", "name", "description"]


class HouseAspectDefinitionSerializer(serializers.ModelSerializer):
    """A required catalog choice on a template, with its active options (#2079)."""

    options = serializers.SerializerMethodField()

    class Meta:
        model = HouseAspectDefinition
        fields = ["id", "name", "prompt", "min_picks", "max_picks", "options"]

    @extend_schema_field(HouseAspectOptionSerializer(many=True))
    def get_options(self, obj):
        active = [option for option in obj.options.all() if option.is_active]
        return HouseAspectOptionSerializer(active, many=True).data


class HouseFeatureSerializer(serializers.ModelSerializer):
    """A cultural fact houses of a template carry (#2079)."""

    class Meta:
        model = HouseFeature
        fields = ["id", "name", "slug", "description"]


class HouseTemplateOptionSerializer(serializers.ModelSerializer):
    """A realm template a CG house claim may build from."""

    aspect_definitions = HouseAspectDefinitionSerializer(many=True, read_only=True)
    features = HouseFeatureSerializer(many=True, read_only=True)

    class Meta:
        model = HouseTemplate
        fields = [
            "id",
            "name",
            "description",
            "family_type",
            "name_pattern",
            "mercy_min",
            "mercy_max",
            "method_min",
            "method_max",
            "status_min",
            "status_max",
            "change_min",
            "change_max",
            "allegiance_min",
            "allegiance_max",
            "power_min",
            "power_max",
            "aspect_definitions",
            "features",
        ]


class ClaimableTitleSerializer(serializers.ModelSerializer):
    """A vacant set-aside title open to CG house definition (#1884 Phase D)."""

    realm_name = serializers.CharField(source="realm.name", read_only=True)
    seat_domain_name = serializers.CharField(source="seat_domain.name", read_only=True, default="")
    templates = serializers.SerializerMethodField()

    class Meta:
        model = Title
        fields = ["id", "name", "tier", "realm_name", "seat_domain_name", "templates"]

    @extend_schema_field(HouseTemplateOptionSerializer(many=True))
    def get_templates(self, obj):
        from world.societies.houses.creator import templates_for_title  # noqa: PLC0415

        return HouseTemplateOptionSerializer(templates_for_title(obj), many=True).data


class HouseClaimStatusSerializer(serializers.ModelSerializer):
    """The draft's house claim, as CG shows it (#1884 Phase D, #2079)."""

    title_name = serializers.CharField(source="title.name", read_only=True)
    aspects = serializers.SerializerMethodField()

    class Meta:
        model = HouseClaim
        fields = [
            "id",
            "house_name",
            "title_name",
            "status",
            "review_note",
            "words",
            "colors",
            "sigil_description",
            "lands_writeup",
            "aspects",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_aspects(self, obj):
        return [
            {"definition": picked.definition.name, "option": picked.option.name}
            for picked in obj.aspects.select_related("definition", "option")
        ]

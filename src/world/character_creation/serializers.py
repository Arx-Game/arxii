"""
Character Creation serializers.
"""

from collections import defaultdict

from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.character_creation.constants import (
    AGE_MAX_ETERNAL_YOUTH,
    STAT_MAX_VALUE,
    STAT_MIN_VALUE,
    AnchorSource,
    QuestionKind,
)
from world.character_creation.models import (
    AGE_MAX,
    AGE_MIN,
    REQUIRED_STATS,
    Beginnings,
    CGExplanation,
    CGPointBudget,
    CharacterDraft,
    CharacterOriginSlot,
    DraftApplication,
    DraftApplicationComment,
    DraftMarking,
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
    StartingArea,
)
from world.character_creation.services import (
    age_bounds,
    clear_family_selection,
    select_origin_template,
    set_family_path,
)
from world.character_creation.types import StageValidationErrors
from world.character_sheets.models import DAYS_IN_MONTH, Gender, Heritage, Pronouns
from world.classes.models import Path, PathStage
from world.distinctions.models import Distinction
from world.forms.models import Build, HeightBand
from world.forms.serializers import BuildSerializer, HeightBandSerializer
from world.game_clock.services import get_ic_now
from world.magic.models import Gift, GlimpseTag, Technique, Tradition
from world.magic.serializers import TechniqueEffectSummarySerializer
from world.mechanics.constants import GOAL_CATEGORY_NAME
from world.roster.models import Family, KinSlotPool, Kinsperson
from world.roster.serializers import FamilySerializer, KinSlotPoolSerializer, KinSlotSerializer
from world.societies.houses.models import (
    HouseAspectDefinition,
    HouseAspectOption,
    HouseClaim,
    HouseFeature,
    HouseTemplate,
    Title,
)
from world.societies.models import Organization, Vacancy
from world.species.models import Language, Species
from world.worship.models import WorshippedBeing
from world.worship.serializers import WorshippedBeingRefSerializer

# Sentinel distinguishing "key not present in this PATCH" from an explicit
# ``None``/empty value, for CharacterDraftSerializer.update() (#3617).
_UNSET = object()


class PerspectiveEntrySerializer(serializers.Serializer):
    """Shop-window payload for a holder's perspective entries (#3281, ADR-0224).

    Serves CodexEntry rows ungated by codex knowledge: the CG wizard shows a
    culture's own voice while the player chooses. Read-only by construction.
    """

    entry_id = serializers.IntegerField(source="id")
    name = serializers.CharField()
    summary = serializers.CharField()
    lore_content = serializers.CharField()
    subject_name = serializers.CharField(source="subject.name")


class HeritageAnchorSerializer(serializers.ModelSerializer):
    """The world fact behind a heritage's CG age ceiling (#3663).

    Nested read-only under Beginnings so the appearance stage can say "The first
    Misbegotten were born in 980 AS." from data; the ceiling itself comes from
    the draft's ``age_max``.
    """

    first_appeared_ic_year = serializers.SerializerMethodField()

    class Meta:
        model = Heritage
        fields = ["name", "first_appeared_ic_year"]
        read_only_fields = ["name"]

    def get_first_appeared_ic_year(self, obj: Heritage) -> int | None:
        return obj.first_appeared_ic.year if obj.first_appeared_ic is not None else None


class EnemyOfferSerializer(serializers.Serializer):
    """One person or group a draft may name as its enemy (#3621). Read-only, schema only."""

    kind = serializers.CharField(read_only=True)
    organization_id = serializers.IntegerField(read_only=True, allow_null=True)
    name = serializers.CharField(read_only=True)
    reach = serializers.CharField(read_only=True)
    power_tier = serializers.CharField(read_only=True)
    why = serializers.CharField(read_only=True)
    source = serializers.CharField(read_only=True)


class IntroductionsOfferedSerializer(serializers.Serializer):
    """Which Introductions a draft is offered (#3621). Read-only, schema only."""

    first_journal = serializers.BooleanField(read_only=True)


class BeginningsSerializer(serializers.ModelSerializer):
    """Serializer for Beginnings options."""

    allowed_species_ids = serializers.SerializerMethodField()
    heritage = HeritageAnchorSerializer(read_only=True, allow_null=True)
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
            "allowed_species_ids",
            "grants_species_languages",
            "cg_point_cost",
            "is_accessible",
            "codex_entry_ids",
            "heritage",
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
            "eternal_youth",
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
    — the pool ∪ tradition availability set for one (path, gift, tradition) pick
    (see ``world.magic.services.cg_catalog.get_technique_options``). ``is_tradition_technique``
    is resolved from the ``tradition_technique_ids`` set the ViewSet places in the
    serializer context — never attached to the (SharedMemoryModel) ``Technique``
    instance itself, to avoid leaking one request's filtered flag into another's
    cached row (see the ``required_distinction_id`` comment above).
    """

    category = serializers.CharField(source="effect_type.category", read_only=True)
    codex_entry_id = serializers.IntegerField(read_only=True, allow_null=True)
    is_tradition_technique = serializers.SerializerMethodField()
    # #2898: CG was the thinnest surface of the four — no cost, no reach, no
    # targeting, no hostility — at the moment the pick is least reversible. The
    # shared effect block carries all of it, so this one field closes every gap.
    effect_summary = TechniqueEffectSummarySerializer(
        source="cached_effect_summary",
        read_only=True,
    )

    class Meta:
        model = Technique
        fields = [
            "id",
            "name",
            "description",
            "category",
            "codex_entry_id",
            "is_tradition_technique",
            "effect_summary",
        ]
        read_only_fields = fields

    def get_is_tradition_technique(self, obj: Technique) -> bool:
        """True when this technique came from the tradition's special technique set."""
        return obj.id in self.context.get("tradition_technique_ids", set())


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
            "affinity",
            "suggested_distinctions",
        ]
        read_only_fields = fields

    @extend_schema_field(CGGlimpseTagSuggestedDistinctionSerializer(many=True))
    def get_suggested_distinctions(self, obj: GlimpseTag) -> list[dict]:
        rows = obj.cached_distinction_suggestions  # Prefetch(to_attr=...), ordered
        return CGGlimpseTagSuggestedDistinctionSerializer(
            [row.distinction for row in rows], many=True
        ).data


_GLOSS_MAX_LEN = 160


def _gloss(description: str) -> str:
    """First line of ``description``, cut at a word boundary to <= 160 chars.

    No sentence-detection (a "St." abbreviation split on ". " was the bug this
    replaced, #3660 ruling C) and no trailing ellipsis - just the last whole
    word that still fits. An empty description gives "".
    """
    first_line = description.split("\n", 1)[0].strip()
    if len(first_line) <= _GLOSS_MAX_LEN:
        return first_line
    truncated = first_line[:_GLOSS_MAX_LEN]
    last_space = truncated.rfind(" ")
    return truncated[:last_space] if last_space > 0 else truncated


def _group_payload(org: Organization) -> dict:
    """Name, first-line gloss, and the family's influence (#3660)."""
    return {
        "id": org.id,
        "name": org.name,
        "gloss": _gloss(org.description),
        "influence": org.family.influence if org.family_id else None,
    }


def _batch_listed_groups(
    slots: list[OriginTemplateSlot],
) -> dict[int, list[Organization]]:
    """LISTED slots' offered groups: one query over the ``anchor_orgs`` M2M (#3660 ruling D).

    Every LISTED slot on the template shares this single query over the through
    table (joined to ``Organization``), grouped by slot id in Python - never a
    per-slot ``slot.anchor_orgs.all()`` call.
    """
    slot_ids = [
        slot.id
        for slot in slots
        if slot.kind == QuestionKind.GROUP and slot.anchor_source == AnchorSource.LISTED
    ]
    if not slot_ids:
        return {}
    through = OriginTemplateSlot.anchor_orgs.through
    pairs = list(
        through.objects.filter(origintemplateslot_id__in=slot_ids).values_list(
            "origintemplateslot_id", "organization_id"
        )
    )
    org_ids = {org_id for _, org_id in pairs}
    orgs_by_id = {
        org.id: org for org in Organization.objects.filter(pk__in=org_ids).select_related("family")
    }
    grouped: dict[int, list[Organization]] = defaultdict(list)
    for slot_id, org_id in pairs:
        org = orgs_by_id.get(org_id)
        if org is not None:
            grouped[slot_id].append(org)
    for orgs in grouped.values():
        orgs.sort(key=lambda org: org.name)
    return grouped


def _batch_pool_groups(
    slots: list[OriginTemplateSlot],
) -> dict[int, list[Organization]]:
    """POOL slots' offered groups: one shared query, partitioned per slot (#3660 ruling D).

    Every POOL slot's (org_type, society) filter is OR'd into a single
    ``Organization`` query; each slot's own filter (plus ``exclude_covert``) is
    then re-applied in Python to split the shared result set back out per slot,
    so the query count doesn't grow with the number of POOL questions.
    """
    pool_slots = [
        slot
        for slot in slots
        if slot.kind == QuestionKind.GROUP and slot.anchor_source == AnchorSource.POOL
    ]
    if not pool_slots:
        return {}
    combined = Q()
    for slot in pool_slots:
        slot_q = Q()
        if slot.anchor_org_type_id:
            slot_q &= Q(org_type_id=slot.anchor_org_type_id)
        if slot.anchor_society_id:
            slot_q &= Q(society_id=slot.anchor_society_id)
        combined |= slot_q
    rows = list(
        Organization.objects.filter(combined).select_related("org_type", "family").order_by("name")
    )
    grouped: dict[int, list[Organization]] = {}
    for slot in pool_slots:
        matches = []
        for org in rows:
            if slot.anchor_org_type_id and org.org_type_id != slot.anchor_org_type_id:
                continue
            if slot.anchor_society_id and org.society_id != slot.anchor_society_id:
                continue
            if slot.exclude_covert and org.org_type is not None and org.org_type.is_covert:
                continue
            matches.append(org)
        grouped[slot.id] = matches
    return grouped


class GrantedDistinctionSerializer(serializers.Serializer):
    """The Distinction a choice bundles at no extra cost (#3660 ruling E)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    cost_per_rank = serializers.IntegerField()
    secret_by_default = serializers.BooleanField()


class OriginGroupSerializer(serializers.Serializer):
    """One group a GROUP question offers, for the frontend picker (#3660 ruling E)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    gloss = serializers.CharField(allow_blank=True)
    influence = serializers.IntegerField(allow_null=True)


class DerivedAnchorSerializer(serializers.Serializer):
    """An OWN_FAMILY/SERVED_HOUSE GROUP question's resolved org (#3660 ruling L).

    No ``gloss`` (unlike ``OriginGroupSerializer``) - this backs the fact-card
    display on an already-answered question, not a picker.
    """

    id = serializers.IntegerField()
    name = serializers.CharField()
    influence = serializers.IntegerField(allow_null=True)


class OriginTemplateSlotChoiceSerializer(serializers.ModelSerializer):
    """One priced answer on an Upbringing prompt (#3617, #3660). The seed stays server-side."""

    grants_distinction = serializers.SerializerMethodField()

    class Meta:
        model = OriginTemplateSlotChoice
        fields = [
            "id",
            "name",
            "description",
            "cg_point_cost",
            "cost_per_influence",
            "trust_required",
            "grants_distinction",
            "sort_order",
        ]
        read_only_fields = fields

    @extend_schema_field(GrantedDistinctionSerializer(allow_null=True))
    def get_grants_distinction(self, obj: OriginTemplateSlotChoice) -> dict | None:
        dist = obj.grants_distinction
        return GrantedDistinctionSerializer(dist).data if dist is not None else None


class OriginTemplateSlotSerializer(serializers.ModelSerializer):
    """Slot prompt within an origin template (#2478, #3617, #3660)."""

    choices = serializers.SerializerMethodField()
    shown_for_choice_ids = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()

    class Meta:
        model = OriginTemplateSlot
        fields = [
            "id",
            "name",
            "prompt",
            "example",
            "sort_order",
            "is_required",
            "applies_to",
            "allows_text",
            "kind",
            "connection_kind",
            "life_stage",
            "anchor_source",
            "same_anchor_as",
            "follow_up_to",
            "shown_for_choice_ids",
            "groups",
            "choices",
        ]
        read_only_fields = fields

    @extend_schema_field(OriginTemplateSlotChoiceSerializer(many=True))
    def get_choices(self, obj: OriginTemplateSlot) -> list[dict]:
        """Return this slot's active choices from the parent's flat-queried grouping.

        ADR-0263: a ``to_attr`` prefetch keyed on a per-slot query would be a new
        stale-cache hit on this identity-mapped model, so the parent serializer
        (``CGOriginTemplateSerializer.get_slots``) runs one flat query for every
        slot's choices and passes the grouping down via context instead (mirrors
        the two-flat-queries approach in ``validators.py:_get_prompt_errors``).
        """
        rows = self.context.get("choices_by_slot", {}).get(obj.id, [])
        return OriginTemplateSlotChoiceSerializer(rows, many=True).data

    @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
    def get_shown_for_choice_ids(self, obj: OriginTemplateSlot) -> list[int]:
        """Choice ids on ``follow_up_to`` that reveal this slot; ``[]`` means any answer.

        Resolved by the parent serializer's flat query over the M2M through table
        (``CGOriginTemplateSerializer.get_slots``), never a per-slot ``.shown_for_choices
        .all()`` call here (ADR-0263).
        """
        return self.context.get("branch_ids_by_slot", {}).get(obj.id, [])

    @extend_schema_field(OriginGroupSerializer(many=True))
    def get_groups(self, obj: OriginTemplateSlot) -> list[dict]:
        """Groups a POOL/LISTED question offers; ``[]`` for every other source.

        SAME_AS / SERVED_HOUSE / OWN_FAMILY depend on draft state a template read
        doesn't have, so the frontend resolves those from the draft instead
        (``CGOriginTemplateSerializer.get_slots`` only populates this context key
        for POOL/LISTED).
        """
        payload = self.context.get("groups_by_slot", {}).get(obj.id, [])
        return OriginGroupSerializer(payload, many=True).data


class CGOriginTemplateSerializer(serializers.ModelSerializer):
    """Origin template for the CG guided flow (#2478, #3617).

    Backs ``GET /api/character-creation/origin-templates/``.
    """

    slots = serializers.SerializerMethodField()
    claimable_kind_ids = serializers.SerializerMethodField()
    family_templates = serializers.SerializerMethodField()

    class Meta:
        model = OriginTemplate
        fields = [
            "id",
            "name",
            "frame_narrative",
            "is_active",
            "sort_order",
            "cg_point_cost",
            "trust_required",
            "allows_claim_family",
            "allows_name_family",
            "allows_no_family",
            "claimable_kind_ids",
            "family_templates",
            "slots",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_family_templates(self, obj: OriginTemplate) -> list[dict]:
        """``FamilyTemplateSerializer`` is defined later in this module (near

        ``HouseTemplateOptionSerializer``, which it extends) - resolved by name
        at call time, not at class-definition time, so the forward reference
        never raises ``NameError`` on import.
        """
        return FamilyTemplateSerializer(obj.family_templates.all(), many=True).data

    @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
    def get_claimable_kind_ids(self, obj: OriginTemplate) -> list[int]:
        """Prefer the list view's batched grouping; fall back to a direct query.

        ``CGOriginTemplateViewSet.list()`` passes ``claimable_kind_ids_by_template``
        (one flat query for the whole response) into context. Nested usage
        (``CharacterDraftSerializer.selected_origin_template``) never provides that
        key, since it is one object, not a list - a direct query there is a single
        query, not a loop.
        """
        grouping = self.context.get("claimable_kind_ids_by_template")
        if grouping is not None:
            return list(grouping.get(obj.id, []))
        return list(obj.claimable_kinds.values_list("id", flat=True))

    @extend_schema_field(OriginTemplateSlotSerializer(many=True))
    def get_slots(self, obj: OriginTemplate) -> list[dict]:
        """Return nested slots from the view's grouping, or one fresh query.

        Never from a ``to_attr`` prefetch attribute: ``OriginTemplate`` is
        identity-mapped, so an attribute set by one request answered the next one
        too and a question deleted in between was still served, with a null id
        (ADR-0263, #3673).

        Choices and the branch-choice ids are each resolved with one flat query
        across every slot on this template, grouped by slot id in Python (see
        ``OriginTemplateSlotSerializer.get_choices``/``get_shown_for_choice_ids``).
        The groups a POOL or LISTED slot offers are batched the same way and
        never a per-slot query (#3660 ruling D): ``_batch_listed_groups`` runs
        one query over the ``anchor_orgs`` M2M's through table for every LISTED
        slot on the template, and ``_batch_pool_groups`` runs ONE ``Organization``
        query ORing every POOL slot's (org_type, society) filter together, then
        re-applies each slot's own filter (plus ``exclude_covert``) in Python to
        partition the shared result set back out per slot. Neither call's query
        count grows with the number of group questions. ``questionnaire.
        resolve_groups`` stays the draft-time resolver (SAME_AS / SERVED_HOUSE /
        OWN_FAMILY, and other single-slot callers) and is not used here.
        """
        slots = obj.questions.rows
        choices_by_slot: dict[int, list[OriginTemplateSlotChoice]] = defaultdict(list)
        slot_ids = [slot.id for slot in slots]
        if slot_ids:
            choice_rows = (
                OriginTemplateSlotChoice.objects.filter(slot_id__in=slot_ids, is_active=True)
                .select_related("grants_distinction")
                .order_by("sort_order")
            )
            for choice in choice_rows:
                choices_by_slot[choice.slot_id].append(choice)

        branch_ids_by_slot: dict[int, list[int]] = defaultdict(list)
        if slot_ids:
            through = OriginTemplateSlot.shown_for_choices.through
            for slot_id, choice_id in through.objects.filter(
                origintemplateslot_id__in=slot_ids
            ).values_list("origintemplateslot_id", "origintemplateslotchoice_id"):
                branch_ids_by_slot[slot_id].append(choice_id)

        orgs_by_slot = {**_batch_listed_groups(slots), **_batch_pool_groups(slots)}
        groups_by_slot: dict[int, list[dict]] = {
            slot_id: [_group_payload(org) for org in orgs] for slot_id, orgs in orgs_by_slot.items()
        }

        nested_context = {
            **self.context,
            "choices_by_slot": choices_by_slot,
            "branch_ids_by_slot": branch_ids_by_slot,
            "groups_by_slot": groups_by_slot,
        }
        return OriginTemplateSlotSerializer(slots, many=True, context=nested_context).data


class DraftMarkingSerializer(serializers.ModelSerializer):
    """CG-authored body markings (#2985) — materialized at finalization."""

    class Meta:
        model = DraftMarking
        fields = ["id", "body_region", "kind", "name", "description"]


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
    # The Upbringing and family path taken under it (#3617).
    selected_origin_template = CGOriginTemplateSerializer(read_only=True)
    selected_origin_template_id = serializers.PrimaryKeyRelatedField(
        queryset=OriginTemplate.objects.filter(is_active=True),
        source="selected_origin_template",
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
    # Vacancy claim / served-house pick (#3648)
    selected_vacancy_id = serializers.PrimaryKeyRelatedField(
        queryset=Vacancy.objects.filter(is_active=True),
        source="selected_vacancy",
        write_only=True,
        required=False,
        allow_null=True,
    )
    selected_vacancy = serializers.PrimaryKeyRelatedField(read_only=True)
    served_house_id = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(),
        source="served_house",
        write_only=True,
        required=False,
        allow_null=True,
    )
    served_house = serializers.PrimaryKeyRelatedField(read_only=True)
    defer_parents = serializers.BooleanField(required=False)
    claimed_kin_slot = serializers.PrimaryKeyRelatedField(read_only=True)
    claimed_kin_pool = serializers.PrimaryKeyRelatedField(read_only=True)
    # Invented cross-species parent (#2815)
    second_parent_species = serializers.PrimaryKeyRelatedField(read_only=True)
    second_parent_species_id = serializers.PrimaryKeyRelatedField(
        queryset=Species.objects.all(),
        source="second_parent_species",
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
    # The age range CG accepts for this draft: the general cap tightened by
    # eternal youth and by the heritage's first appearance (#3663). The
    # appearance stage clamps to these instead of knowing the rule.
    age_min = serializers.SerializerMethodField()
    age_max = serializers.SerializerMethodField()
    # Distinctions the Upbringing answers grant, shown locked in the Distinctions
    # stage so a player can't also hand-pick one already bundled in (#3660).
    bundled_distinctions = serializers.SerializerMethodField()
    # The Actor's Sheet (#3621): who the draft may name as its enemy, the two price
    # scales, and whether the First Journal is offered (an Arx start).
    enemy_offers = serializers.SerializerMethodField()
    enemy_price_tables = serializers.SerializerMethodField()
    enemy_degree_grants = serializers.SerializerMethodField()
    introductions_offered = serializers.SerializerMethodField()
    # OWN_FAMILY/SERVED_HOUSE GROUP questions' resolved org, since the frontend has
    # no way to derive these itself (#3660 ruling L; see questionnaire.derived_anchors).
    derived_anchors = serializers.SerializerMethodField()

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
            "birthday_month",
            "birthday_day",
            "family",
            "family_id",
            "selected_origin_template",
            "selected_origin_template_id",
            "family_path",
            "claimed_kin_slot",
            "claimed_kin_slot_id",
            "claimed_kin_pool",
            "claimed_kin_pool_id",
            "selected_vacancy",
            "selected_vacancy_id",
            "served_house",
            "served_house_id",
            "defer_parents",
            "second_parent_species",
            "second_parent_species_id",
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
            "age_min",
            "age_max",
            "bundled_distinctions",
            "derived_anchors",
            "enemy_offers",
            "enemy_price_tables",
            "enemy_degree_grants",
            "introductions_offered",
        ]
        read_only_fields = [
            "id",
            "age_min",
            "age_max",
            "enemy_offers",
            "enemy_price_tables",
            "enemy_degree_grants",
            "introductions_offered",
            "has_existing_characters",
            "cg_points_spent",
            "cg_points_remaining",
            "stat_bonuses",
            "stage_completion",
            "stage_errors",
            "stats_points_remaining",
            "stats_budget",
            "starting_technique_picks",
            "bundled_distinctions",
            "derived_anchors",
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

    def get_age_min(self, obj: CharacterDraft) -> int:
        return age_bounds(obj.selected_species, obj.selected_beginnings, get_ic_now()).minimum

    def get_age_max(self, obj: CharacterDraft) -> int:
        return age_bounds(obj.selected_species, obj.selected_beginnings, get_ic_now()).maximum

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_bundled_distinctions(self, obj: CharacterDraft) -> list[dict]:
        """Distinctions the Upbringing answers grant; shown locked in Distinctions (#3660)."""
        return list(obj.bundled_distinctions())

    @extend_schema_field(EnemyOfferSerializer(many=True))
    def get_enemy_offers(self, obj: CharacterDraft) -> list[dict]:
        """Persons and groups the draft may name as its enemy (#3621)."""
        from dataclasses import asdict  # noqa: PLC0415

        from world.character_creation.enemies import enemy_offers  # noqa: PLC0415

        return [asdict(offer) for offer in enemy_offers(obj)]

    @extend_schema_field(
        serializers.DictField(
            child=serializers.DictField(
                child=serializers.DictField(child=serializers.IntegerField())
            )
        )
    )
    def get_enemy_price_tables(self, obj: CharacterDraft) -> dict:  # noqa: ARG002
        """Both price scales, so the leaf can show the ledger line before it is chosen."""
        from world.character_creation.enemies import price_tables  # noqa: PLC0415

        return price_tables()

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_enemy_degree_grants(self, obj: CharacterDraft) -> dict[str, str]:  # noqa: ARG002
        """Degree value -> the Distinction it grants, so the row says "grants Hunted"."""
        from world.character_creation.enemies import degree_grants  # noqa: PLC0415

        return degree_grants()

    @extend_schema_field(IntroductionsOfferedSerializer())
    def get_introductions_offered(self, obj: CharacterDraft) -> dict[str, bool]:
        """Which Introductions this draft is offered (the First Journal needs an Arx start)."""
        from world.character_creation.services import first_journal_offered  # noqa: PLC0415

        return {"first_journal": first_journal_offered(obj)}

    @extend_schema_field(serializers.DictField(child=DerivedAnchorSerializer(allow_null=True)))
    def get_derived_anchors(self, obj: CharacterDraft) -> dict[str, dict | None]:
        """OWN_FAMILY/SERVED_HOUSE GROUP questions' resolved org, keyed by slot id (#3660).

        JSON object keys are always strings, so a slot id that ``derived_anchors``
        keys by ``int`` comes back here keyed by ``str`` - the frontend looks each
        slot up by ``String(slot.id)``.
        """
        return {str(slot_id): anchor for slot_id, anchor in obj.derived_anchors().items()}

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
        """Validate age against ``age_bounds`` for the draft's species and heritage (#3663).

        Species and Beginnings come from the same request when it changes them,
        else from the instance, so a PATCH that picks a Beginnings and an age
        together is judged against the Beginnings it picked.
        """
        if value is None:
            return value

        species = None
        species_id = self.initial_data.get("selected_species_id")
        if species_id:
            species = Species.objects.filter(id=species_id).first()
        elif self.instance:
            species = self.instance.selected_species
        beginnings = None
        beginnings_id = self.initial_data.get("selected_beginnings_id")
        if beginnings_id:
            beginnings = Beginnings.objects.filter(id=beginnings_id).first()
        elif self.instance:
            beginnings = self.instance.selected_beginnings
        bounds = age_bounds(species, beginnings, get_ic_now())

        if value < AGE_MIN or value > AGE_MAX:
            msg = f"Age must be between {AGE_MIN} and {AGE_MAX} years."
            raise serializers.ValidationError(msg)
        if value <= bounds.maximum:
            return value
        # Name the cap that bound: eternal youth when it set the ceiling, else
        # the heritage's first appearance (the only other thing that tightens it).
        if (
            species is not None
            and species.eternal_youth
            and bounds.maximum == AGE_MAX_ETERNAL_YOUTH
        ):
            msg = (
                f"{species.name} characters keep their eternal youth: age must be "
                f"at most {AGE_MAX_ETERNAL_YOUTH}."
            )
            raise serializers.ValidationError(msg)
        heritage = beginnings.heritage if beginnings is not None else None
        heritage_name = heritage.name if heritage is not None else "Characters of this heritage"
        msg = (
            f"{heritage_name} can be at most {bounds.maximum} years old: "
            f"the first were born in {bounds.heritage_first_year} AS."
        )
        raise serializers.ValidationError(msg)

    def update(self, instance, validated_data):
        """Handle the Upbringing/family-path picks, then merge ``draft_data``.

        The wizard's stages save independently (debounced skills, slider commits,
        navigation-triggered saves) - whole-blob replacement made every PATCH a
        last-write-wins race over a snapshot of the client cache, silently
        reverting sibling stages' keys (2026-07 audit). A key set to ``null``
        still clears it; omitted keys are untouched.

        ``selected_origin_template`` and ``family_path`` (#3617) are popped and
        handled explicitly before that merge and before ``super().update()``:
        a key absent from this PATCH (``_UNSET``) is left untouched; an explicit
        ``None`` clears the Upbringing and everything downstream of it; a change
        to a different Upbringing goes through ``select_origin_template`` (which
        raises a DRF ``ValidationError``, surfacing as a 400, on the wrong
        beginning or insufficient trust, and clears downstream state itself);
        the same pk is a no-op. ``family_path`` similarly goes through
        ``set_family_path`` (which raises when the Upbringing does not allow
        that path) unless it is being cleared to the empty string.
        """
        template = validated_data.pop("selected_origin_template", _UNSET)
        if template is _UNSET:
            pass
        elif template is None:
            instance.selected_origin_template = None
            clear_family_selection(instance)
        elif template.pk != instance.selected_origin_template_id:
            select_origin_template(instance, template)
        # else: same pk selected again, no-op.

        path = validated_data.pop("family_path", _UNSET)
        if path is _UNSET:
            pass
        elif path:
            set_family_path(instance, path)
        else:
            instance.family_path = ""

        vacancy = validated_data.get("selected_vacancy", _UNSET)
        if vacancy is not _UNSET and vacancy is not None:
            # A Vacancy supplies its own kin link; a manual claim would double it.
            validated_data["claimed_kin_slot"] = None
            validated_data["claimed_kin_pool"] = None
        family = validated_data.get("family", _UNSET)
        if family is not _UNSET and family != instance.family and instance.selected_vacancy_id:
            validated_data.setdefault("selected_vacancy", None)

        incoming = validated_data.pop("draft_data", None)
        if incoming is not None:
            validated_data["draft_data"] = {**instance.draft_data, **incoming}
        return super().update(instance, validated_data)

    def _validate_stats(self, stats) -> None:
        """Each named stat is a real stat, an integer, and inside the allowed band."""
        if not isinstance(stats, dict):
            msg = "stats must be a dictionary"
            raise serializers.ValidationError(msg)
        for stat_name, stat_value in stats.items():
            if stat_name not in REQUIRED_STATS:
                msg = f"'{stat_name}' is not a valid stat name"
                raise serializers.ValidationError(msg)
            if not isinstance(stat_value, int):
                msg = f"{stat_name} must be an integer, got {type(stat_value).__name__}"
                raise serializers.ValidationError(msg)
            if not (STAT_MIN_VALUE <= stat_value <= STAT_MAX_VALUE):
                msg = f"{stat_name} must be between {STAT_MIN_VALUE} and {STAT_MAX_VALUE}"
                raise serializers.ValidationError(msg)

    def validate_draft_data(self, value):
        """Validate draft_data fields, including stat allocations and goals."""
        if not isinstance(value, dict):
            msg = "draft_data must be a dictionary"
            raise serializers.ValidationError(msg)

        stats = value.get("stats")
        if stats is not None:
            self._validate_stats(stats)

        self._validate_tarot_card_name(value)
        self._validate_origin_choices(value)
        self._validate_origin_anchors(value)
        self._validate_origin_figures(value)
        self._validate_new_family_name(value)
        self._validate_family_aspect_picks(value)

        goals = value.get("goals")
        if goals is not None:
            value["goals"] = self._validate_goals(goals)

        self._validate_actor_sheet(value)
        return value

    def _validate_actor_sheet(self, data: dict) -> None:
        """The Actor's Sheet keys (#3621): three answers, the enemy pick, the Introductions."""
        from world.character_creation.constants import ACTOR_SHEET_QUESTIONS  # noqa: PLC0415

        for key, _copy_key in ACTOR_SHEET_QUESTIONS:
            if key in data and not isinstance(data[key], str):
                raise serializers.ValidationError({key: "Must be text."})
        if data.get("enemy") is not None:
            self._validate_enemy_pick(data["enemy"])
        if data.get("introductions") is not None:
            self._validate_introductions(data["introductions"])

    @staticmethod
    def _validate_enemy_pick(enemy: object) -> None:
        from world.character_sheets.types import (  # noqa: PLC0415
            EnemyDegree,
            EnemyKind,
            EnemyPowerTier,
        )

        if not isinstance(enemy, dict):
            raise serializers.ValidationError({"enemy": "Must be an object."})
        if enemy.get("kind") not in EnemyKind.values:
            raise serializers.ValidationError({"enemy": "kind must be person or group."})
        if enemy.get("degree") not in EnemyDegree.values:
            raise serializers.ValidationError({"enemy": "degree is not one of the four."})
        org_id = enemy.get("organization_id")
        if org_id is not None and not isinstance(org_id, int):
            raise serializers.ValidationError({"enemy": "organization_id must be an id."})
        tier = enemy.get("power_tier", "")
        if tier and tier not in EnemyPowerTier.values:
            raise serializers.ValidationError({"enemy": "power_tier is not on the ladder."})
        for key in ("name", "why", "public_line"):
            if not isinstance(enemy.get(key, ""), str):
                raise serializers.ValidationError({"enemy": f"{key} must be text."})

    @staticmethod
    def _validate_introductions(intros: object) -> None:
        from world.character_creation.constants import (  # noqa: PLC0415
            INTRODUCTION_APPLICATION,
            INTRODUCTION_FIRST_JOURNAL,
            INTRODUCTION_WHISPERS,
        )

        if not isinstance(intros, dict):
            raise serializers.ValidationError({"introductions": "Must be an object."})
        for key in (INTRODUCTION_FIRST_JOURNAL, INTRODUCTION_APPLICATION):
            answers = intros.get(key, [])
            if not isinstance(answers, list) or not all(isinstance(a, str) for a in answers):
                msg = f"{key} must be a list of text answers."
                raise serializers.ValidationError({"introductions": msg})
        if not isinstance(intros.get(INTRODUCTION_WHISPERS, ""), str):
            raise serializers.ValidationError({"introductions": "whispers must be text."})

    def _validate_origin_choices(self, data: dict) -> None:
        """``origin_choices`` maps a str slot id to a picked choice id, or null (#3617)."""
        origin_choices = data.get("origin_choices")
        if origin_choices is None:
            return
        if not isinstance(origin_choices, dict):
            msg = "origin_choices must be a dictionary"
            raise serializers.ValidationError({"origin_choices": msg})
        for slot_id, choice_id in origin_choices.items():
            if not isinstance(slot_id, str):
                msg = "origin_choices keys must be strings"
                raise serializers.ValidationError({"origin_choices": msg})
            if choice_id is not None and not isinstance(choice_id, int):
                msg = "origin_choices values must be an integer choice id or null"
                raise serializers.ValidationError({"origin_choices": msg})

    def _validate_origin_anchors(self, data: dict) -> None:
        """``origin_anchors`` maps a str slot id to an organization id, or null (#3660)."""
        anchors = data.get("origin_anchors")
        if anchors is None:
            return
        if not isinstance(anchors, dict):
            raise serializers.ValidationError(
                {"origin_anchors": "origin_anchors must be a dictionary"}
            )
        for slot_id, org_id in anchors.items():
            if not isinstance(slot_id, str):
                raise serializers.ValidationError(
                    {"origin_anchors": "origin_anchors keys must be strings"}
                )
            if org_id is not None and not isinstance(org_id, int):
                raise serializers.ValidationError(
                    {
                        "origin_anchors": (
                            "origin_anchors values must be an integer organization id or null"
                        )
                    }
                )

    def _validate_origin_figures(self, data: dict) -> None:
        """``origin_figures`` maps a str slot id to a person's name, at most 120 chars (#3660)."""
        figures = data.get("origin_figures")
        if figures is None:
            return
        if not isinstance(figures, dict):
            raise serializers.ValidationError(
                {"origin_figures": "origin_figures must be a dictionary"}
            )
        max_length = CharacterOriginSlot._meta.get_field("figure_name").max_length  # noqa: SLF001
        for slot_id, name in figures.items():
            if not isinstance(slot_id, str) or not isinstance(name, str):
                raise serializers.ValidationError(
                    {"origin_figures": "origin_figures must map strings to strings"}
                )
            if len(name) > max_length:
                raise serializers.ValidationError(
                    {"origin_figures": f"A person's name is at most {max_length} characters"}
                )

    def _validate_new_family_name(self, data: dict) -> None:
        """``new_family_name`` must fit ``Family.name``'s column width (#3617)."""
        new_family_name = data.get("new_family_name")
        if new_family_name is None:
            return
        if not isinstance(new_family_name, str):
            msg = "new_family_name must be a string"
            raise serializers.ValidationError({"new_family_name": msg})
        max_length = Family._meta.get_field("name").max_length  # noqa: SLF001
        if len(new_family_name) > max_length:
            msg = f"new_family_name must be at most {max_length} characters"
            raise serializers.ValidationError({"new_family_name": msg})

    def _validate_family_aspect_picks(self, data: dict) -> None:
        """``family_aspect_picks`` maps an int-castable definition id to a list of
        int-castable option ids (#3648 review): a shape ``validators.py``'s
        ``_get_aspect_pick_errors`` can read without raising on a malformed PATCH.
        """
        picks = data.get("family_aspect_picks")
        if picks is None:
            return
        msg = "family_aspect_picks must map a definition id to a list of option ids"
        if not isinstance(picks, dict):
            raise serializers.ValidationError({"family_aspect_picks": msg})
        for key, values in picks.items():
            if not isinstance(values, list):
                raise serializers.ValidationError({"family_aspect_picks": msg})
            try:
                int(key)
                for value in values:
                    int(value)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError({"family_aspect_picks": msg}) from exc

    def _validate_tarot_card_name(self, data: dict) -> None:
        """Validate that tarot_card_name refers to an existing TarotCard."""
        tarot_card_name = data.get("tarot_card_name")
        if tarot_card_name is not None:
            from world.tarot.models import TarotCard  # noqa: PLC0415

            if not TarotCard.objects.filter(name=tarot_card_name).exists():
                raise serializers.ValidationError(
                    {"tarot_card_name": f"Unknown tarot card: {tarot_card_name}"}
                )

    def _validate_goal(self, goal, valid_domains: dict, valid_domain_ids: set) -> dict:
        """One goal row, resolved to the PK-only shape finalize_character reads back."""
        if not isinstance(goal, dict):
            msg = "Each goal must be a dictionary"
            raise serializers.ValidationError(msg)

        # Resolve domain - accept either domain_id (PK) or domain (name)
        domain_id = goal.get("domain_id")
        domain_name = goal.get("domain")
        if domain_id is not None:
            if domain_id not in valid_domain_ids:
                msg = f"Invalid goal domain ID: {domain_id}"
                raise serializers.ValidationError(msg)
            resolved_id = domain_id
        elif domain_name:
            domain = valid_domains.get(domain_name.lower())
            if domain is None:
                msg = f"Invalid goal domain: '{domain_name}'"
                raise serializers.ValidationError(msg)
            resolved_id = domain.id
        else:
            msg = "Each goal must have either domain_id or domain"
            raise serializers.ValidationError(msg)

        points = goal.get("points", 0)
        if not isinstance(points, int) or points < 0:
            msg = "Goal points must be a non-negative integer"
            raise serializers.ValidationError(msg)

        from world.goals.constants import GoalHorizon  # noqa: PLC0415

        horizon = goal.get("horizon") or GoalHorizon.SHORT_TERM
        if horizon not in GoalHorizon.values:
            msg = f"Invalid goal horizon: '{horizon}'"
            raise serializers.ValidationError(msg)

        return {
            "horizon": horizon,
            "domain_id": resolved_id,
            "points": points,
            "notes": goal.get("notes", goal.get("text", "")),
        }

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
        return [self._validate_goal(g, valid_domains, valid_domain_ids) for g in goals]

    def validate(self, attrs):
        """Cross-field validation."""
        height_band = attrs.get("height_band") or (
            self.instance.height_band if self.instance else None
        )
        height_inches = attrs.get("height_inches")

        if (
            height_inches is not None
            and height_band is not None
            and not (height_band.min_inches <= height_inches <= height_band.max_inches)
        ):
            raise serializers.ValidationError(
                {
                    "height_inches": (
                        f"Must be between {height_band.min_inches} and "
                        f"{height_band.max_inches} for {height_band.display_name}."
                    )
                }
            )

        # Birthday pair must name a real Gregorian date (#2756).
        month = attrs.get("birthday_month", self.instance.birthday_month if self.instance else None)
        day = attrs.get("birthday_day", self.instance.birthday_day if self.instance else None)
        if month is not None and day is not None:
            max_day = DAYS_IN_MONTH[month - 1]
            if day > max_day:
                msg = f"Month {month} has at most {max_day} days."
                raise serializers.ValidationError({"birthday_day": msg})

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
                "never_do": "",
                "protect": "",
                "fear": "",
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
            "never_do": draft.draft_data.get("never_do", ""),
            "protect": draft.draft_data.get("protect", ""),
            "fear": draft.draft_data.get("fear", ""),
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
    """One authored answer in an aspect catalog (#2079).

    ``codex_entry_id`` (#2868) lets the CG option card link the option's lore
    write-up — Inferna's House Quiddities each have one.
    """

    codex_entry_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = HouseAspectOption
        fields = ["id", "name", "description", "codex_entry_id"]


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
            "kind",
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


class FamilyTemplateSerializer(HouseTemplateOptionSerializer):
    """A Family Template the name path offers (#3648)."""

    served_house_choices = serializers.SerializerMethodField()

    class Meta(HouseTemplateOptionSerializer.Meta):
        fields = [*HouseTemplateOptionSerializer.Meta.fields, "org_type", "served_house_choices"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_served_house_choices(self, obj) -> list[dict]:
        return [{"id": org.id, "name": org.name} for org in obj.served_house_choices.all()]


class CGVacancySerializer(serializers.ModelSerializer):
    """An opening reachable from the draft, priced for it (#3648)."""

    basis = serializers.CharField(read_only=True)
    cost = serializers.SerializerMethodField()
    rank_name = serializers.CharField(source="rank.name", read_only=True, default="")
    organization = serializers.SerializerMethodField()
    kin_pool = KinSlotPoolSerializer(read_only=True, allow_null=True)
    kin_node = KinSlotSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Vacancy
        fields = [
            "id",
            "name",
            "description",
            "basis",
            "importance",
            "presumed_importance",
            "cost",
            "rank_name",
            "count_remaining",
            "organization",
            "kin_pool",
            "kin_node",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_cost(self, obj: Vacancy) -> int:
        family = obj.organization.family
        return obj.cost_for(family.influence if family is not None else 0)

    @extend_schema_field(serializers.DictField())
    def get_organization(self, obj: Vacancy) -> dict:
        family = obj.organization.family
        return {
            "id": obj.organization_id,
            "name": obj.organization.name,
            "family": None
            if family is None
            else {"id": family.id, "name": family.name, "influence": family.influence},
        }


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

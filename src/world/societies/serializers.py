"""DRF serializers for the societies membership API (#1511)."""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.scenes.models import Persona
from world.societies.houses.models import Domain, Title
from world.societies.models import (
    LegendEntry,
    LegendEvent,
    LegendHonor,
    Organization,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationRank,
    OrganizationReputation,
    OrgAppeal,
    OrgAppealSignon,
    Proclamation,
    StandingDeclaration,
)

_ORGANIZATION_NAME_SOURCE = "organization.name"


class OrganizationRankSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationRank
        fields = [
            "id",
            "name",
            "tier",
            "can_invite",
            "can_kick",
            "can_manage_ranks",
            "can_lead_rituals",
            "can_declare_standing",
            "can_post_to_board",
            "can_moderate_board",
            "can_resolve_appeals",
        ]


class HouseTitleSerializer(serializers.ModelSerializer):
    holder_name = serializers.SerializerMethodField()

    class Meta:
        model = Title
        fields = ["id", "name", "tier", "holder_name", "is_claimable"]

    def get_holder_name(self, obj) -> str:
        from world.societies.houses.services import full_display_name  # noqa: PLC0415

        return full_display_name(obj.holder) if obj.holder is not None else ""


class HouseDomainSerializer(serializers.ModelSerializer):
    holding_names = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = ["name", "population", "prosperity", "unrest", "holding_names"]

    def get_holding_names(self, obj) -> list[str]:
        return [holding.name for holding in obj.holdings.all()]


class HouseAspectFacetSerializer(serializers.Serializer):
    """One picked identity facet on the house block (#2079)."""

    definition = serializers.CharField()
    option = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class HouseFeatureFacetSerializer(serializers.Serializer):
    """One cultural feature on the house block (#2079)."""

    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class HouseCrisisOptionSerializer(serializers.Serializer):
    """One judgment-call option on an open crisis (#2238)."""

    id = serializers.IntegerField()
    kind = serializers.CharField()
    cost_coppers = serializers.IntegerField()
    mission_template_id = serializers.IntegerField(allow_null=True)
    self_resolve_pct = serializers.IntegerField()
    worsen_pct = serializers.IntegerField()


class HouseCrisisSerializer(serializers.Serializer):
    """An open DomainCrisis on the house block (#2238)."""

    id = serializers.IntegerField()
    domain_name = serializers.CharField()
    severity = serializers.CharField()
    type_name = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    origin = serializers.CharField()
    opened_at = serializers.DateTimeField()
    chosen_kind = serializers.CharField(allow_blank=True)
    minted_mission_id = serializers.IntegerField(allow_null=True)
    options = HouseCrisisOptionSerializer(many=True)


class HouseStatureSerializer(serializers.Serializer):
    """The house's stature panel (#3091): qualitative headline, numbers below.

    Members-only by construction — the org queryset already gates non-staff
    viewers to their own orgs, so this is the house's own view of itself.
    All values are stored weekly (plus event shocks); zero extra queries.
    """

    headline = serializers.CharField(allow_blank=True)
    band_name = serializers.CharField(allow_blank=True)
    trend = serializers.CharField()
    perceived_total = serializers.IntegerField()
    true_total = serializers.IntegerField()
    renown_strength = serializers.IntegerField()
    military_strength = serializers.IntegerField()
    economic_strength = serializers.IntegerField()
    allied_strength = serializers.IntegerField()
    crisis_penalty = serializers.IntegerField()
    prestige_rank = serializers.IntegerField(allow_null=True)
    realm_rank = serializers.IntegerField(allow_null=True)
    realm_cohort_size = serializers.IntegerField(allow_null=True)


class HouseDetailSerializer(serializers.Serializer):
    """The house block of an org payload (#1884) — null for non-family orgs."""

    family_name = serializers.CharField()
    liege_name = serializers.CharField(allow_blank=True)
    vassal_names = serializers.ListField(child=serializers.CharField())
    titles = HouseTitleSerializer(many=True)
    domains = HouseDomainSerializer(many=True)
    aspects = HouseAspectFacetSerializer(many=True)
    features = HouseFeatureFacetSerializer(many=True)
    open_crises = HouseCrisisSerializer(many=True)
    stature = HouseStatureSerializer(allow_null=True)


class OrganizationSerializer(serializers.ModelSerializer):
    society_name = serializers.CharField(source="society.name", read_only=True)
    org_type_name = serializers.CharField(source="org_type.name", read_only=True)
    ranks = OrganizationRankSerializer(many=True, read_only=True)
    house = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "description",
            "words",
            "colors",
            "sigil_description",
            "society_name",
            "org_type_name",
            "ranks",
            "house",
        ]

    @extend_schema_field(HouseDetailSerializer(allow_null=True))
    def get_house(self, obj) -> dict | None:
        if obj.family is None:
            return None

        # Read the prefetched relations (OrganizationViewSet queryset, 2026-07
        # audit) — `.all()` uses the prefetch cache; titles are sorted in Python
        # to avoid a fresh ordered query per org. The liege edge (`fealty`,
        # OneToOne) and direct vassals (`vassal_edges`) are prefetched too, so
        # the whole house payload costs zero extra queries per org on a list.
        try:
            liege_edge = obj.fealty  # reverse OneToOne, prefetched
        except ObjectDoesNotExist:
            liege_edge = None
        titles = sorted(obj.titles.all(), key=lambda t: (t.tier, t.name))
        payload = {
            "family_name": obj.family.name,
            "liege_name": liege_edge.liege.name if liege_edge is not None else "",
            "vassal_names": [edge.vassal.name for edge in obj.vassal_edges.all()],
            "titles": titles,
            "domains": obj.domains.all(),
            "aspects": [
                {
                    "definition": facet.definition.name,
                    "option": facet.option.name,
                    "description": facet.option.description,
                }
                for facet in obj.aspects.all()
            ],
            "features": [
                {
                    "name": stamped.feature.name,
                    "slug": stamped.feature.slug,
                    "description": stamped.feature.description,
                }
                for stamped in obj.features.all()
            ],
            "open_crises": _house_open_crises(obj),
            "stature": _house_stature_payload(obj),
        }
        return HouseDetailSerializer(payload).data


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source=_ORGANIZATION_NAME_SOURCE, read_only=True)
    persona_name = serializers.CharField(source="persona.name", read_only=True)
    rank = OrganizationRankSerializer(read_only=True)
    title = serializers.CharField(source="get_title", read_only=True)
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationMembership
        fields = [
            "id",
            "organization",
            "organization_name",
            "persona",
            "persona_name",
            "rank",
            "title",
            "joined_date",
            "left_at",
            "exiled_at",
            "is_active",
        ]

    def get_is_active(self, obj: OrganizationMembership) -> bool:
        return obj.left_at is None and obj.exiled_at is None


class OrganizationReputationSerializer(serializers.ModelSerializer):
    """A persona's standing with an organization — named tier only, never the raw value."""

    organization_name = serializers.CharField(source=_ORGANIZATION_NAME_SOURCE, read_only=True)
    tier = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationReputation
        fields = [
            "id",
            "persona",
            "organization",
            "organization_name",
            "tier",
        ]

    def get_tier(self, obj: OrganizationReputation) -> str:
        return obj.get_tier().value


class StandingDeclarationSerializer(serializers.ModelSerializer):
    """A leader's public favor/disfavor declaration (#3290) — history/audit read.

    Public by design (spec decision 4): the declaration itself (who, target,
    direction, citation, when) is meant to be legible to bystanders, unlike
    the raw ``OrganizationReputation`` value it moves. ``delta_applied`` is
    deliberately NOT exposed here — the hidden-value convention
    (``OrganizationReputationSerializer``: "tier only, never the raw value")
    extends to the magnitude a declaration moved that value by; staff can read
    it in the admin for dispute resolution.
    """

    organization_name = serializers.CharField(source=_ORGANIZATION_NAME_SOURCE, read_only=True)
    target_persona_name = serializers.CharField(source="target_persona.name", read_only=True)
    declared_by_persona_name = serializers.CharField(
        source="declared_by_persona.name", read_only=True
    )

    class Meta:
        model = StandingDeclaration
        fields = [
            "id",
            "organization",
            "organization_name",
            "target_persona",
            "target_persona_name",
            "declared_by_persona",
            "declared_by_persona_name",
            "direction",
            "citation",
            "created_at",
        ]


class OrganizationMembershipOfferSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source=_ORGANIZATION_NAME_SOURCE, read_only=True)
    from_persona_name = serializers.CharField(source="from_persona.name", read_only=True)
    to_persona_name = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationMembershipOffer
        fields = [
            "id",
            "organization",
            "organization_name",
            "from_persona",
            "from_persona_name",
            "to_persona",
            "to_persona_name",
            "kind",
            "status",
            "created_at",
            "resolved_at",
        ]

    def get_to_persona_name(self, obj: OrganizationMembershipOffer) -> str:
        return obj.to_persona.name if obj.to_persona else ""


def _house_stature_payload(organization) -> dict | None:
    """The stature panel dict (#3091) — reads the prefetched ``stature`` row.

    Headline renders the band's authored template with the org name; trend
    compares band ranks (rank 1 is highest, so a lower rank is a rise).
    """
    try:
        stature = organization.stature  # reverse OneToOne, prefetched
    except ObjectDoesNotExist:
        return None
    band = stature.band
    previous = stature.previous_band
    if band is None or previous is None or band.rank == previous.rank:
        trend = "steady"
    else:
        trend = "rising" if band.rank < previous.rank else "falling"
    headline = ""
    if band is not None and band.headline_template:
        headline = band.headline_template.replace("{org}", organization.name)
    return {
        "headline": headline,
        "band_name": band.name if band is not None else "",
        "trend": trend,
        "perceived_total": stature.perceived_total,
        "true_total": stature.true_total,
        "renown_strength": stature.renown_strength,
        "military_strength": stature.military_strength,
        "economic_strength": stature.economic_strength,
        "allied_strength": stature.allied_strength,
        "crisis_penalty": stature.crisis_penalty,
        "prestige_rank": stature.prestige_rank,
        "realm_rank": stature.realm_rank,
        "realm_cohort_size": stature.realm_cohort_size,
    }


def _house_open_crises(organization) -> list[dict]:
    """Open crises across the org's domains (#2238), options included.

    Reads the viewset's prefetched ``domains`` relation; the per-crisis option
    menu comes from ``crisis_options`` (computed PAY costs).
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.societies.houses.crisis_services import crisis_options  # noqa: PLC0415
    from world.societies.houses.models import CrisisIntel  # noqa: PLC0415

    def _row(crisis, target_name: str) -> dict:
        return {
            "id": crisis.pk,
            "domain_name": target_name,
            "severity": crisis.severity,
            "valence": crisis.valence,
            "type_name": crisis.crisis_type.name if crisis.crisis_type else "",
            "description": crisis.description,
            "origin": crisis.origin,
            "opened_at": crisis.opened_at,
            "chosen_kind": (crisis.chosen_option.kind if crisis.chosen_option_id else ""),
            "minted_mission_id": crisis.minted_mission_id,
            "options": crisis_options(crisis),
        }

    now = timezone.now()
    candidates: list[tuple] = []
    for domain in organization.domains.all():
        candidates.extend(
            (crisis, domain.name) for crisis in domain.crises.all() if crisis.resolved_at is None
        )
    candidates.extend(
        (crisis, organization.name)
        for crisis in organization.org_crises.all()
        if crisis.resolved_at is None
    )
    # A still-covert generated crisis is hidden even from its target — a
    # spymaster's sweep (CrisisIntel) is how you see it early (#2837). One
    # batched intel query, only when something is actually hidden.
    hidden = [c for c, _ in candidates if c.surfaces_at is not None and c.surfaces_at > now]
    known_ids: set[int] = set()
    if hidden:
        known_ids = set(
            CrisisIntel.objects.filter(org=organization, crisis__in=hidden).values_list(
                "crisis_id", flat=True
            )
        )
    return [
        _row(crisis, name)
        for crisis, name in candidates
        if crisis.surfaces_at is None or crisis.surfaces_at <= now or crisis.pk in known_ids
    ]


class ProclamationSerializer(serializers.ModelSerializer):
    """Read surface for the public record (#2842). Prose is display-only."""

    issuer_name = serializers.CharField(source="issuer.name", read_only=True)
    stance_name = serializers.CharField(source="stance.name", read_only=True)
    org_name = serializers.CharField(source="org.name", read_only=True, default="")
    outcome_name = serializers.SerializerMethodField()

    class Meta:
        model = Proclamation
        fields = [
            "id",
            "issuer",
            "issuer_name",
            "org",
            "org_name",
            "stance",
            "stance_name",
            "prose",
            "outcome_name",
            "issued_at",
        ]

    def get_outcome_name(self, obj) -> str:
        return str(obj.check_outcome.name) if obj.check_outcome_id else ""


class ProclamationCreateSerializer(serializers.Serializer):
    """Create payload (#2842): stance + optional org voice, optional edict leg."""

    stance = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    prose = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    org = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    domain = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    edict_kind = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        has_edict = bool(attrs.get("domain")) and bool(attrs.get("edict_kind"))
        if bool(attrs.get("domain")) != bool(attrs.get("edict_kind")):
            msg = "Enacting an edict takes BOTH domain and edict_kind."
            raise serializers.ValidationError(msg)
        if not has_edict and not attrs.get("stance"):
            msg = "A plain proclamation requires a stance."
            raise serializers.ValidationError({"stance": msg})
        return attrs


class CrisisOptionInputSerializer(serializers.Serializer):
    """Input for the crisis judgment call (#2238): crisis + option, org-scoped."""

    crisis = serializers.IntegerField()
    option = serializers.IntegerField()

    def validate(self, attrs: dict) -> dict:
        from world.societies.houses.models import (  # noqa: PLC0415
            DomainCrisis,
            DomainCrisisTypeOption,
        )

        organization = self.context["organization"]
        crisis = (
            DomainCrisis.objects.select_related("domain", "crisis_type")
            .filter(pk=attrs["crisis"])
            .first()
        )
        if crisis is None or crisis.target_org.pk != organization.pk:
            msg = "That crisis is not this organization's to judge."
            raise serializers.ValidationError({"crisis": msg})
        option = DomainCrisisTypeOption.objects.filter(pk=attrs["option"]).first()
        if option is None:
            msg = "Unknown option."
            raise serializers.ValidationError({"option": msg})
        attrs["crisis"] = crisis
        attrs["option"] = option
        return attrs


# ---------------------------------------------------------------------------
# Match dossier (#2999) — full-information review of a candidate house
# ---------------------------------------------------------------------------


class DossierPactSerializer(serializers.Serializer):
    """One standing instrument on the dossier: paper pact or marriage."""

    kind = serializers.CharField()
    counterpart = serializers.CharField()
    since = serializers.DateTimeField(allow_null=True)
    commitments = serializers.ListField(child=serializers.CharField())


class DossierCrisisSerializer(serializers.Serializer):
    domain_name = serializers.CharField(allow_blank=True)
    severity = serializers.CharField()
    type_name = serializers.CharField(allow_blank=True)
    known_covertly = serializers.BooleanField()


class DossierShiftSerializer(serializers.Serializer):
    cause = serializers.CharField()
    delta_perceived = serializers.IntegerField()
    subject = serializers.CharField(allow_blank=True)
    occurred_at = serializers.DateTimeField()


class DossierConsortSerializer(serializers.Serializer):
    holder = serializers.CharField()
    consorts = serializers.IntegerField()
    cap = serializers.IntegerField(allow_null=True)


class OrgDossierSerializer(serializers.Serializer):
    """The match-review dossier (#2999): what a candidate house truly brings.

    Deliberately viewable by ANY authenticated player (the org page itself
    stays members-only): weighing a match requires seeing rival houses.
    Public facts only — band, perceived stature, ranks, standing instruments,
    surfaced crises — enriched with covert crises the VIEWER'S org has paid
    spycraft to know (CrisisIntel). True component detail stays members-only
    on the org page.
    """

    name = serializers.CharField()
    org_type_name = serializers.CharField(allow_blank=True)
    family_name = serializers.CharField(allow_blank=True)
    band_name = serializers.CharField(allow_blank=True)
    headline = serializers.CharField(allow_blank=True)
    trend = serializers.CharField()
    perceived_total = serializers.IntegerField(allow_null=True)
    prestige_rank = serializers.IntegerField(allow_null=True)
    realm_rank = serializers.IntegerField(allow_null=True)
    realm_cohort_size = serializers.IntegerField(allow_null=True)
    pacts = DossierPactSerializer(many=True)
    betrothals = serializers.ListField(child=serializers.CharField())
    open_crises = DossierCrisisSerializer(many=True)
    recent_shifts = DossierShiftSerializer(many=True)
    consorts = DossierConsortSerializer(many=True)


class OrgAppealSignonSerializer(serializers.ModelSerializer):
    """A member's signon on an appeal (#3293)."""

    member_persona_name = serializers.CharField(source="member_persona.name", read_only=True)

    class Meta:
        model = OrgAppealSignon
        fields = ["id", "member_persona", "member_persona_name", "note", "created_at"]


class OrgAppealSerializer(serializers.ModelSerializer):
    """Read serializer for an appeal to an organization (#3293).

    ``signons`` is a nested read; the queryset that feeds list/retrieve
    prefetches ``signons__member_persona`` for it. Mutating endpoints
    (signon/resolve/withdraw) re-fetch and drop the stale prefetch cache
    before re-serializing (see ``OrgAppealViewSet``).
    """

    organization_name = serializers.CharField(source=_ORGANIZATION_NAME_SOURCE, read_only=True)
    petitioner_persona_name = serializers.CharField(
        source="petitioner_persona.name", read_only=True
    )
    resolved_by_persona_name = serializers.SerializerMethodField()
    signons = OrgAppealSignonSerializer(many=True, read_only=True)

    class Meta:
        model = OrgAppeal
        fields = [
            "id",
            "organization",
            "organization_name",
            "petitioner_persona",
            "petitioner_persona_name",
            "title",
            "body",
            "state",
            "resolution_text",
            "resolved_by_persona",
            "resolved_by_persona_name",
            "created_at",
            "resolved_at",
            "signons",
        ]

    def get_resolved_by_persona_name(self, obj: OrgAppeal) -> str:
        return obj.resolved_by_persona.name if obj.resolved_by_persona_id else ""


class OrgAppealCreateSerializer(serializers.Serializer):
    """Lodge-an-appeal payload (#3293)."""

    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    title = serializers.CharField(max_length=120)
    body = serializers.CharField()


class OrgAppealSignonInputSerializer(serializers.Serializer):
    """Signon payload (#3293) — an optional short note."""

    note = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")


class OrgAppealResolveInputSerializer(serializers.Serializer):
    """Resolve payload (#3293) — grant or decline, with a written answer."""

    verdict = serializers.ChoiceField(choices=["grant", "decline"])
    answer = serializers.CharField(required=False, allow_blank=True, default="")


_NO_ACTIVE_PERSONA_REASON = "You need an active persona to honor a deed."


def _compute_can_honor(*, viewer_persona: Persona | None, deed: LegendEntry) -> dict:
    """Read-only eligibility preview for the Rite of Honors (#3466 Task 9).

    Mirrors ``honor_deed``'s (``world.societies.honors``) amplify-branch checks
    without any side effect — no row lock, no token resolution, no write. Every
    ``reason`` string is the same player-safe ``HonorRefused.user_message`` the
    service itself would raise, so a refusal shown here and a refusal returned by
    the POST ``honor`` action never drift apart. None of these name anything the
    viewer could not already see elsewhere on this same payload (the deed's own
    title/persona, or the Hare count this same response already discloses).
    """
    from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME  # noqa: PLC0415
    from world.currency.models import FavorTokenDetails  # noqa: PLC0415
    from world.societies.honors import (  # noqa: PLC0415
        AlreadyHonoredError,
        CannotHonorOwnDeedError,
        DeedAtCeilingError,
        EventMintedNothingRefusal,
        InsufficientHaresError,
        NoAnchorEventError,
        UnknownDeedError,
    )
    from world.societies.knowledge_services import knows_deed  # noqa: PLC0415
    from world.societies.models import LegendLevelCalibration  # noqa: PLC0415

    if viewer_persona is None:
        return {
            "allowed": False,
            "reason": _NO_ACTIVE_PERSONA_REASON,
            "hares_required": 0,
            "value_added": 0,
        }

    if deed.event_id is None:
        return {
            "allowed": False,
            "reason": NoAnchorEventError().user_message,
            "hares_required": 0,
            "value_added": 0,
        }

    anchor_event = deed.event
    sheet = viewer_persona.character_sheet
    # Authored content: unguarded on purpose (see LegendLevelCalibration's
    # docstring) — a missing row is a content gap the admin required-content
    # panel surfaces, never a silent fallback price.
    calibration = LegendLevelCalibration.objects.get(level=sheet.current_level)
    hares_required = calibration.honor_hares_required
    headroom = max(anchor_event.base_value - deed.base_value, 0)
    value_added = min(calibration.honor_value_added, headroom)

    reason: str | None = None
    if deed.persona.character_sheet_id == sheet.pk:
        reason = CannotHonorOwnDeedError().user_message
    elif not anchor_event.deeds.filter(is_active=True).exists():
        reason = EventMintedNothingRefusal().user_message
    elif not knows_deed(persona=viewer_persona, deed=deed):
        reason = UnknownDeedError().user_message
    elif LegendHonor.objects.filter(deed=deed, honorer=viewer_persona).exists():
        reason = AlreadyHonoredError().user_message
    elif headroom <= 0:
        reason = DeedAtCeilingError().user_message
    else:
        academy = Organization.objects.get(name=SHROUDWATCH_ACADEMY_NAME)
        available = FavorTokenDetails.objects.filter(
            issuing_organization=academy,
            redeemed_at__isnull=True,
            item_instance__holder_character_sheet=sheet,
            item_instance__destroyed_at__isnull=True,
        ).count()
        if available < hares_required:
            reason = InsufficientHaresError(hares_required).user_message

    return {
        "allowed": reason is None,
        "reason": reason,
        "hares_required": hares_required,
        "value_added": value_added,
    }


class _JournalSummarySerializer(serializers.Serializer):
    """The public journal an honor is mirrored onto — safe to inline in full."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    body = serializers.CharField(read_only=True)


class LegendHonorSerializer(serializers.ModelSerializer):
    """One paid, written testimony to a deed (#3466 Task 9).

    ``honorer`` is the persona id + display name ONLY — never the account. The
    honorer's journal is public by construction (``honor_deed`` always writes
    ``is_public=True``), so its body is safe to inline here rather than requiring
    a second request.
    """

    honorer = serializers.SerializerMethodField()
    journal = serializers.SerializerMethodField()

    class Meta:
        model = LegendHonor
        fields = [
            "id",
            "honorer",
            "value_added",
            "hares_spent",
            "established_deed",
            "created_at",
            "journal",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.DictField())
    def get_honorer(self, obj: LegendHonor) -> dict:
        return {"id": obj.honorer_id, "name": obj.honorer.name}

    @extend_schema_field(_JournalSummarySerializer())
    def get_journal(self, obj: LegendHonor) -> dict:
        journal = obj.journal_entry
        return {"id": journal.pk, "title": journal.title, "body": journal.body}


class CanHonorSerializer(serializers.Serializer):
    """Eligibility preview computed by ``_compute_can_honor`` — never persisted."""

    allowed = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(read_only=True, allow_null=True)
    hares_required = serializers.IntegerField(read_only=True)
    value_added = serializers.IntegerField(read_only=True)


class DeedDetailSerializer(serializers.ModelSerializer):
    """A deed's public detail page (#3466 Task 9): the React deed page's payload.

    ``persona`` exposes id + name only (the face, never the account). ``ceiling``
    is the anchoring event's ``base_value`` — null when the deed has no event, in
    which case ``can_honor.reason`` says so in plain words (an unanchored deed
    cannot be honored). ``can_honor`` needs ``context["viewer_persona"]``, set by
    the viewset from the requester's active persona (or ``None``).
    """

    persona = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()
    ceiling = serializers.SerializerMethodField()
    headroom = serializers.SerializerMethodField()
    honors = LegendHonorSerializer(many=True, read_only=True)
    can_honor = serializers.SerializerMethodField()

    class Meta:
        model = LegendEntry
        fields = [
            "id",
            "title",
            "description",
            "persona",
            "base_value",
            "ceiling",
            "headroom",
            "earned_at_level",
            "event",
            "honors",
            "can_honor",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.DictField())
    def get_persona(self, obj: LegendEntry) -> dict:
        return {"id": obj.persona_id, "name": obj.persona.name}

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_event(self, obj: LegendEntry) -> dict | None:
        if obj.event_id is None:
            return None
        return {"id": obj.event_id, "title": obj.event.title, "base_value": obj.event.base_value}

    def get_ceiling(self, obj: LegendEntry) -> int | None:
        return obj.event.base_value if obj.event_id is not None else None

    def get_headroom(self, obj: LegendEntry) -> int | None:
        if obj.event_id is None:
            return None
        return max(obj.event.base_value - obj.base_value, 0)

    @extend_schema_field(CanHonorSerializer())
    def get_can_honor(self, obj: LegendEntry) -> dict:
        return _compute_can_honor(viewer_persona=self.context.get("viewer_persona"), deed=obj)


class LegendEventSummarySerializer(serializers.ModelSerializer):
    """Minimal list/retrieve payload for the establish-a-deed anchor (#3466 Task 9)."""

    class Meta:
        model = LegendEvent
        fields = ["id", "title", "description", "base_value", "created_at"]
        read_only_fields = fields


class HonorDeedInputSerializer(serializers.Serializer):
    """``POST /api/societies/deeds/{id}/honor/`` body (#3466 Task 9): amplify."""

    journal_title = serializers.CharField(max_length=200)
    journal_body = serializers.CharField(allow_blank=False)


class EstablishDeedInputSerializer(serializers.Serializer):
    """``POST /api/societies/events/{id}/establish/`` body (#3466 Task 9)."""

    honoree_persona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    deed_title = serializers.CharField(max_length=200)
    journal_title = serializers.CharField(max_length=200)
    journal_body = serializers.CharField(allow_blank=False)

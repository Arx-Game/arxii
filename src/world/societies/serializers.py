"""DRF serializers for the societies membership API (#1511)."""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.societies.houses.models import Domain, Title
from world.societies.models import (
    Organization,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationRank,
    OrganizationReputation,
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


def _house_open_crises(organization) -> list[dict]:
    """Open crises across the org's domains (#2238), options included.

    Reads the viewset's prefetched ``domains`` relation; the per-crisis option
    menu comes from ``crisis_options`` (computed PAY costs).
    """
    from world.societies.houses.crisis_services import crisis_options  # noqa: PLC0415

    rows: list[dict] = []
    for domain in organization.domains.all():
        for crisis in domain.crises.all():
            if crisis.resolved_at is not None:
                continue
            rows.append(
                {
                    "id": crisis.pk,
                    "domain_name": domain.name,
                    "severity": crisis.severity,
                    "type_name": crisis.crisis_type.name if crisis.crisis_type else "",
                    "description": crisis.description,
                    "origin": crisis.origin,
                    "opened_at": crisis.opened_at,
                    "chosen_kind": (crisis.chosen_option.kind if crisis.chosen_option_id else ""),
                    "minted_mission_id": crisis.minted_mission_id,
                    "options": crisis_options(crisis),
                }
            )
    return rows

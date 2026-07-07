"""DRF serializers for the societies membership API (#1511)."""

from __future__ import annotations

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


class HouseDetailSerializer(serializers.Serializer):
    """The house block of an org payload (#1884) — null for non-family orgs."""

    family_name = serializers.CharField()
    liege_name = serializers.CharField(allow_blank=True)
    vassal_names = serializers.ListField(child=serializers.CharField())
    titles = HouseTitleSerializer(many=True)
    domains = HouseDomainSerializer(many=True)
    aspects = HouseAspectFacetSerializer(many=True)
    features = HouseFeatureFacetSerializer(many=True)


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
        from world.societies.houses.models import FealtyEdge  # noqa: PLC0415
        from world.societies.houses.services import vassals_of  # noqa: PLC0415

        edge = FealtyEdge.objects.filter(vassal=obj).select_related("liege").first()
        payload = {
            "family_name": obj.family.name,
            "liege_name": edge.liege.name if edge is not None else "",
            "vassal_names": [vassal.name for vassal in vassals_of(obj)],
            "titles": obj.titles.select_related("holder").order_by("tier", "name"),
            "domains": obj.domains.prefetch_related("holdings"),  # noqa: PREFETCH_STRING
            "aspects": [
                {
                    "definition": facet.definition.name,
                    "option": facet.option.name,
                    "description": facet.option.description,
                }
                for facet in obj.aspects.select_related("definition", "option")
            ],
            "features": [
                {
                    "name": stamped.feature.name,
                    "slug": stamped.feature.slug,
                    "description": stamped.feature.description,
                }
                for stamped in obj.features.select_related("feature")
            ],
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

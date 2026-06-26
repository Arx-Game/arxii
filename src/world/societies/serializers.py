"""DRF serializers for the societies membership API (#1511)."""

from __future__ import annotations

from rest_framework import serializers

from world.societies.models import (
    Organization,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationRank,
)


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
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    society_name = serializers.CharField(source="society.name", read_only=True)
    org_type_name = serializers.CharField(source="org_type.name", read_only=True)
    ranks = OrganizationRankSerializer(many=True, read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "description",
            "society_name",
            "org_type_name",
            "ranks",
        ]


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
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


class OrganizationMembershipOfferSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
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

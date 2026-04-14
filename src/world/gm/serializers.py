"""Serializers for the GM system."""

from __future__ import annotations

from rest_framework import serializers

from world.gm.constants import GMApplicationStatus
from world.gm.models import (
    GMApplication,
    GMProfile,
    GMTable,
    GMTableMembership,
)


class GMApplicationCreateSerializer(serializers.ModelSerializer):
    """For players submitting a GM application."""

    application_text = serializers.CharField(
        min_length=50,
        max_length=10000,
        allow_blank=False,
    )

    class Meta:
        model = GMApplication
        fields = ["application_text"]

    def validate(self, attrs: dict) -> dict:
        account = self.context["request"].user
        if GMProfile.objects.filter(account=account).exists():
            msg = "This account is already an approved GM."
            raise serializers.ValidationError(msg)
        if GMApplication.objects.filter(
            account=account,
            status=GMApplicationStatus.PENDING,
        ).exists():
            msg = "You already have a pending GM application."
            raise serializers.ValidationError(msg)
        return attrs

    def create(self, validated_data: dict) -> GMApplication:
        validated_data["account"] = self.context["request"].user
        return super().create(validated_data)


class GMApplicationDetailSerializer(serializers.ModelSerializer):
    """For staff reviewing GM applications."""

    account_username = serializers.CharField(source="account.username", read_only=True)
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = GMApplication
        fields = [
            "id",
            "account",
            "account_username",
            "application_text",
            "staff_response",
            "status",
            "created_at",
            "updated_at",
            "reviewed_by",
            "reviewed_by_username",
        ]
        read_only_fields = ["id", "account", "created_at", "updated_at", "reviewed_by"]


class GMProfileSerializer(serializers.ModelSerializer):
    """Read-only serializer for GM profiles."""

    account_username = serializers.CharField(source="account.username", read_only=True)

    class Meta:
        model = GMProfile
        fields = [
            "id",
            "account",
            "account_username",
            "level",
            "approved_at",
        ]
        read_only_fields = fields


class GMTableSerializer(serializers.ModelSerializer):
    """Serializer for GM tables."""

    gm_username = serializers.CharField(source="gm.account.username", read_only=True)

    class Meta:
        model = GMTable
        fields = [
            "id",
            "gm",
            "gm_username",
            "name",
            "description",
            "status",
            "created_at",
            "archived_at",
        ]
        read_only_fields = ["id", "gm_username", "created_at", "archived_at", "status"]


class GMTableMembershipSerializer(serializers.ModelSerializer):
    """Serializer for persona memberships at GM tables."""

    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = GMTableMembership
        fields = ["id", "table", "persona", "persona_name", "joined_at", "left_at"]
        read_only_fields = ["id", "persona_name", "joined_at", "left_at"]

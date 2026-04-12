"""Serializers for the GM system."""

from __future__ import annotations

from rest_framework import serializers

from world.gm.constants import GMApplicationStatus
from world.gm.models import GMApplication, GMProfile


class GMApplicationCreateSerializer(serializers.ModelSerializer):
    """For players submitting a GM application."""

    application_text = serializers.CharField(max_length=10000)

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

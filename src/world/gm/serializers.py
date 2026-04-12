"""Serializers for the GM system."""

from __future__ import annotations

from rest_framework import serializers

from world.gm.models import GMApplication, GMProfile


class GMApplicationCreateSerializer(serializers.ModelSerializer):
    """For players submitting a GM application."""

    class Meta:
        model = GMApplication
        fields = ["application_text"]

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
        read_only_fields = ["id", "account", "created_at", "updated_at"]


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

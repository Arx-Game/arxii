"""Serializers for the #2177 defense web surfaces."""

from __future__ import annotations

from rest_framework import serializers

from world.room_features.models import ExitBarsDetails, RoomAlarmDetails, RoomWardDetails


class DefenseInstallSerializer(serializers.Serializer):
    defense_kind = serializers.ChoiceField(choices=["EXIT_BARS", "ROOM_WARD", "ROOM_ALARM"])
    target_level = serializers.IntegerField(min_value=1)
    exit_id = serializers.IntegerField(required=False)
    resonance_id = serializers.IntegerField(required=False)


class DefenseInstallResultSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()


class FundWardSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)


class FundWardResultSerializer(serializers.Serializer):
    resonance_reserve = serializers.IntegerField()


class ExitBarsDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExitBarsDetails
        fields = ["exit_profile", "level", "installed_at", "last_upgraded_at", "dissolved_at"]


class RoomWardDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomWardDetails
        fields = [
            "room_profile",
            "level",
            "resonance",
            "resonance_reserve",
            "lapsed_at",
            "installed_at",
            "last_upgraded_at",
            "dissolved_at",
        ]


class RoomAlarmDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomAlarmDetails
        fields = ["room_profile", "level", "installed_at", "last_upgraded_at", "dissolved_at"]

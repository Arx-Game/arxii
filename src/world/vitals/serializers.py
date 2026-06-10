"""Serializers for the vitals API (response-shape only; no model writes)."""

from rest_framework import serializers


class FatiguePoolStatusSerializer(serializers.Serializer):
    """One fatigue pool's status (shape produced by fatigue.services.get_full_status)."""

    current = serializers.IntegerField()
    capacity = serializers.IntegerField()
    percentage = serializers.FloatField()
    zone = serializers.CharField()


class VitalsFatigueSerializer(serializers.Serializer):
    """All three fatigue pools plus global flags."""

    physical = FatiguePoolStatusSerializer()
    social = FatiguePoolStatusSerializer()
    mental = FatiguePoolStatusSerializer()
    well_rested = serializers.BooleanField()
    rested_today = serializers.BooleanField()


class CharacterVitalsSerializer(serializers.Serializer):
    """Read-only vitals payload for the character sheet panel (#521)."""

    health = serializers.IntegerField()
    max_health = serializers.IntegerField()
    health_percentage = serializers.FloatField()
    wound_description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    fatigue = VitalsFatigueSerializer()

"""Serializers for the technique picker (#4341)."""

from __future__ import annotations

from rest_framework import serializers


class ManifestOptionChoiceSerializer(serializers.Serializer):
    """One option a technique can bring: its label, whether its bond holds, why not."""

    option_id = serializers.IntegerField(source="option.pk")
    label = serializers.CharField()
    available = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)
    companion_id = serializers.IntegerField(source="companion.pk", allow_null=True, default=None)


class ManifestChoiceSerializer(serializers.Serializer):
    """One manifesting technique the character knows, its options and the current pick."""

    technique_id = serializers.IntegerField(source="technique.pk")
    technique_name = serializers.CharField()
    chosen_option_id = serializers.IntegerField(source="chosen.pk", allow_null=True, default=None)
    options = ManifestOptionChoiceSerializer(many=True)

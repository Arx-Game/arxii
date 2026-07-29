"""DRF serializers for proclamations (#2842)."""

from __future__ import annotations

from rest_framework import serializers

from world.proclamations.models import (
    DomainEdict,
    EdictKind,
    Proclamation,
    StanceArchetype,
)


class StanceArchetypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StanceArchetype
        fields = "__all__"


class ProclamationSerializer(serializers.ModelSerializer):
    issuer_name = serializers.CharField(source="issuer.name", read_only=True)
    stance_name = serializers.CharField(source="stance.name", read_only=True)

    class Meta:
        model = Proclamation
        fields = "__all__"


class EdictKindSerializer(serializers.ModelSerializer):
    class Meta:
        model = EdictKind
        fields = "__all__"


class DomainEdictSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source="domain.name", read_only=True)
    kind_name = serializers.CharField(source="kind.name", read_only=True)

    class Meta:
        model = DomainEdict
        fields = "__all__"

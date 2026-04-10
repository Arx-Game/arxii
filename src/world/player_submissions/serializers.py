"""Serializers for player submission models."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport


class _IdentitySummaryMixin:
    """Shared identity summary helper for submission serializers."""

    def _reporter_summary(self, obj: Any) -> str:
        request = self.context.get("request")  # type: ignore[attr-defined]
        include_account = bool(
            request and request.user.is_authenticated and request.user.is_staff,
        )
        return obj.reporter_persona.get_identity_summary(
            include_account=include_account,
        )


class PlayerFeedbackCreateSerializer(serializers.ModelSerializer):
    """Write serializer - player creates feedback."""

    class Meta:
        model = PlayerFeedback
        fields = ["description", "location"]


class PlayerFeedbackDetailSerializer(
    _IdentitySummaryMixin,
    serializers.ModelSerializer,
):
    """Read serializer for staff review."""

    reporter_summary = serializers.SerializerMethodField()

    class Meta:
        model = PlayerFeedback
        fields = [
            "id",
            "reporter_summary",
            "description",
            "location",
            "created_at",
            "status",
        ]
        read_only_fields = ["id", "reporter_summary", "created_at"]

    def get_reporter_summary(self, obj: PlayerFeedback) -> str:
        return self._reporter_summary(obj)


class BugReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BugReport
        fields = ["description", "location"]


class BugReportDetailSerializer(
    _IdentitySummaryMixin,
    serializers.ModelSerializer,
):
    reporter_summary = serializers.SerializerMethodField()

    class Meta:
        model = BugReport
        fields = [
            "id",
            "reporter_summary",
            "description",
            "location",
            "created_at",
            "status",
        ]
        read_only_fields = ["id", "reporter_summary", "created_at"]

    def get_reporter_summary(self, obj: BugReport) -> str:
        return self._reporter_summary(obj)


class PlayerReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerReport
        fields = [
            "reported_persona",
            "behavior_description",
            "asked_to_stop",
            "blocked_or_muted",
            "scene",
            "interaction",
            "location",
        ]


class PlayerReportDetailSerializer(
    _IdentitySummaryMixin,
    serializers.ModelSerializer,
):
    """Staff-only detail serializer with full identity context."""

    reporter_summary = serializers.SerializerMethodField()
    reported_summary = serializers.SerializerMethodField()

    class Meta:
        model = PlayerReport
        fields = [
            "id",
            "reporter_summary",
            "reported_summary",
            "behavior_description",
            "asked_to_stop",
            "blocked_or_muted",
            "scene",
            "interaction",
            "location",
            "created_at",
            "status",
        ]
        read_only_fields = [
            "id",
            "reporter_summary",
            "reported_summary",
            "created_at",
        ]

    def get_reporter_summary(self, obj: PlayerReport) -> str:
        return self._reporter_summary(obj)

    def get_reported_summary(self, obj: PlayerReport) -> str:
        request = self.context.get("request")
        include_account = bool(
            request and request.user.is_authenticated and request.user.is_staff,
        )
        return obj.reported_persona.get_identity_summary(
            include_account=include_account,
        )

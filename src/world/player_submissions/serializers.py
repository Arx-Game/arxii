"""Serializers for player submission models."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport


class _IdentitySummaryMixin:
    """Shared identity summary helper for submission serializers."""

    def _resolved_summary(
        self,
        persona_id: int,
        persona_obj: Any,
        *,
        include_account: bool,
    ) -> str:
        """Look up an identity summary for a persona.

        Prefers a batch-resolved lookup from the serializer context when
        available (set by the ViewSet's ``list``/``retrieve`` overrides)
        to avoid the N+1 ``persona.get_identity_summary()`` walk. Falls
        back to the per-row walk when no context lookup is present.
        """
        context = self.context  # type: ignore[attr-defined]
        identity_lookup = context.get("identity_lookup")
        format_summary = context.get("format_summary")
        if identity_lookup is not None and format_summary is not None:
            resolved = identity_lookup.get(persona_id)
            if resolved is not None:
                return format_summary(resolved, include_account=include_account)
        return persona_obj.get_identity_summary(include_account=include_account)

    def _reporter_summary(self, obj: Any) -> str:
        request = self.context.get("request")  # type: ignore[attr-defined]
        include_account = bool(
            request and request.user.is_authenticated and request.user.is_staff,
        )
        return self._resolved_summary(
            obj.reporter_persona_id,
            obj.reporter_persona,
            include_account=include_account,
        )


class PlayerFeedbackCreateSerializer(serializers.ModelSerializer):
    """Write serializer - player creates feedback.

    ``location`` is auto-populated from the submitter's current character
    location server-side and is not accepted as input (prevents forgery).
    """

    class Meta:
        model = PlayerFeedback
        fields = ["description"]


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
    """``location`` is auto-populated server-side; not accepted as input."""

    class Meta:
        model = BugReport
        fields = ["description"]


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
    """``location`` is auto-populated server-side; not accepted as input."""

    class Meta:
        model = PlayerReport
        fields = [
            "reported_persona",
            "behavior_description",
            "asked_to_stop",
            "blocked_or_muted",
            "scene",
            "interaction",
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
        return self._resolved_summary(
            obj.reported_persona_id,
            obj.reported_persona,
            include_account=include_account,
        )

"""Serializers for player submission models."""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport
from world.scenes.models import Persona

_NO_ROSTER_ENTRY = "This persona's character has no roster entry."
_NO_ACTIVE_TENURE = "This persona's character has no active tenure."
_NOT_OWNED = "You are not currently playing this persona."
_REPORTED_NO_ROSTER_ENTRY = "Reported persona's character has no roster entry."
_REPORTED_NO_TENURE = "Reported persona has no active player."
_CANNOT_REPORT_SELF = "You cannot report yourself."


def _validate_owned_persona(persona: Persona, account_pk: int) -> Persona:
    """Validate that ``account_pk`` is currently playing ``persona``.

    Walks persona -> character -> roster_entry -> current_tenure and
    confirms the active tenure belongs to the requesting account.
    """
    character = persona.character
    try:
        entry = character.roster_entry
    except ObjectDoesNotExist as exc:
        raise serializers.ValidationError(_NO_ROSTER_ENTRY) from exc
    tenure = entry.current_tenure
    if tenure is None:
        raise serializers.ValidationError(_NO_ACTIVE_TENURE)
    if tenure.player_data.account_id != account_pk:
        raise serializers.ValidationError(_NOT_OWNED)
    return persona


def _account_for_persona(persona: Persona) -> int:
    """Return the account id of the persona's current active tenure.

    Raises ``ValidationError`` if the persona has no current player —
    staff shouldn't be actioning reports against characters with no
    current player.
    """
    character = persona.character
    try:
        entry = character.roster_entry
    except ObjectDoesNotExist as exc:
        raise serializers.ValidationError(_REPORTED_NO_ROSTER_ENTRY) from exc
    tenure = entry.current_tenure
    if tenure is None:
        raise serializers.ValidationError(_REPORTED_NO_TENURE)
    return tenure.player_data.account_id


class PlayerFeedbackCreateSerializer(serializers.ModelSerializer):
    """Write serializer - player creates feedback.

    Frontend supplies ``reporter_persona``; the serializer validates
    that the requesting account currently plays that persona.
    ``location`` is auto-populated server-side and is not accepted as
    input.
    """

    class Meta:
        model = PlayerFeedback
        fields = ["reporter_persona", "description"]

    def validate_reporter_persona(self, value: Persona) -> Persona:
        account = self.context["account"]
        return _validate_owned_persona(value, account.pk)


class PlayerFeedbackDetailSerializer(serializers.ModelSerializer):
    """Read serializer for staff review."""

    reporter_account_username = serializers.CharField(
        source="reporter_account.username",
        read_only=True,
    )
    reporter_persona_name = serializers.CharField(
        source="reporter_persona.name",
        read_only=True,
    )

    class Meta:
        model = PlayerFeedback
        fields = [
            "id",
            "reporter_account",
            "reporter_account_username",
            "reporter_persona",
            "reporter_persona_name",
            "description",
            "location",
            "created_at",
            "status",
        ]
        read_only_fields = ["id", "reporter_account", "created_at"]


class BugReportCreateSerializer(serializers.ModelSerializer):
    """Frontend supplies ``reporter_persona``; ``location`` is server-derived."""

    class Meta:
        model = BugReport
        fields = ["reporter_persona", "description"]

    def validate_reporter_persona(self, value: Persona) -> Persona:
        account = self.context["account"]
        return _validate_owned_persona(value, account.pk)


class BugReportDetailSerializer(serializers.ModelSerializer):
    reporter_account_username = serializers.CharField(
        source="reporter_account.username",
        read_only=True,
    )
    reporter_persona_name = serializers.CharField(
        source="reporter_persona.name",
        read_only=True,
    )

    class Meta:
        model = BugReport
        fields = [
            "id",
            "reporter_account",
            "reporter_account_username",
            "reporter_persona",
            "reporter_persona_name",
            "description",
            "location",
            "created_at",
            "status",
        ]
        read_only_fields = ["id", "reporter_account", "created_at"]


class PlayerReportCreateSerializer(serializers.ModelSerializer):
    """Frontend supplies both reporter and reported personas.

    The reported_account is derived from the reported persona's current
    active tenure. If the reported persona has no current player, the
    submission is rejected.
    """

    class Meta:
        model = PlayerReport
        fields = [
            "reporter_persona",
            "reported_persona",
            "behavior_description",
            "asked_to_stop",
            "blocked_or_muted",
            "scene",
            "interaction",
        ]

    def validate_reporter_persona(self, value: Persona) -> Persona:
        account = self.context["account"]
        return _validate_owned_persona(value, account.pk)

    def validate(self, attrs: dict) -> dict:
        reported = attrs.get("reported_persona")
        reporter = attrs.get("reporter_persona")
        if reported is not None and reporter is not None and reported == reporter:
            raise serializers.ValidationError(
                {"reported_persona": _CANNOT_REPORT_SELF},
            )
        if reported is not None:
            attrs["reported_account_id"] = _account_for_persona(reported)
        return attrs


class PlayerReportDetailSerializer(serializers.ModelSerializer):
    """Staff-only detail serializer with full identity context."""

    reporter_account_username = serializers.CharField(
        source="reporter_account.username",
        read_only=True,
    )
    reporter_persona_name = serializers.CharField(
        source="reporter_persona.name",
        read_only=True,
    )
    reported_account_username = serializers.CharField(
        source="reported_account.username",
        read_only=True,
    )
    reported_persona_name = serializers.CharField(
        source="reported_persona.name",
        read_only=True,
    )

    class Meta:
        model = PlayerReport
        fields = [
            "id",
            "reporter_account",
            "reporter_account_username",
            "reporter_persona",
            "reporter_persona_name",
            "reported_account",
            "reported_account_username",
            "reported_persona",
            "reported_persona_name",
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
            "reporter_account",
            "reported_account",
            "created_at",
        ]

"""Serializers for the justice API (#1765)."""

from rest_framework import serializers

from world.justice.constants import tier_for_value
from world.justice.models import JusticeCase, PersonaHeat


class PersonaHeatSerializer(serializers.ModelSerializer):
    """One warrant row on the viewer's own crime tab — tiers only, never the raw number.

    Alleged deeds render as recorded: a false accusation reads the same as a
    true one (falsity is emergent, #1765).
    """

    area_name = serializers.CharField(source="area.name", read_only=True)
    society_name = serializers.CharField(source="society.name", read_only=True)
    tier = serializers.SerializerMethodField()
    tier_label = serializers.SerializerMethodField()
    alleged_deeds = serializers.SerializerMethodField()

    class Meta:
        model = PersonaHeat
        fields = (
            "id",
            "area",
            "area_name",
            "society",
            "society_name",
            "tier",
            "tier_label",
            "alleged_deeds",
        )

    def get_tier(self, obj: PersonaHeat) -> str:
        return tier_for_value(obj.value).value

    def get_tier_label(self, obj: PersonaHeat) -> str:
        return tier_for_value(obj.value).label

    def get_alleged_deeds(self, obj: PersonaHeat) -> list[str]:
        titles = {source.deed.title for source in obj.sources.all() if source.deed is not None}
        return sorted(titles)


class PublicMarkSerializer(serializers.Serializer):
    """One row of the wanted board's public record (#2378 Task 5).

    Serializes a :class:`world.justice.types.PublicMark` dataclass — area is
    already implied by the wanted endpoint's own ``?area=`` scope, so only
    ``kind``, ``persona_name``, and ``until`` are exposed here.
    """

    kind = serializers.CharField()
    persona_name = serializers.CharField()
    until = serializers.DateTimeField(allow_null=True)


class HumiliationMarkSerializer(serializers.Serializer):
    """The fading half of a #2378-follow-up humiliation, for examine/profile display.

    Serializes :func:`world.justice.sentences.active_humiliation_mark`'s
    :class:`~world.justice.types.PublicMark` (or None) — ``persona_name``/
    ``area_name`` are implied by whichever persona this is attached to, so only
    ``kind``, ``until``, and the neutral ``explanation`` copy
    (``constants.HUMILIATION_MARK_EXPLANATION``) are exposed. Consumed by
    ``PersonaSerializer.humiliation_mark`` (``world/scenes/serializers.py``).
    """

    kind = serializers.CharField()
    until = serializers.DateTimeField()
    explanation = serializers.CharField()


class MyCaseSerializer(serializers.ModelSerializer):
    """The captive's own case picture (#2378) — status, sentence + countdown fields.

    ``evidence_total``/``release_threshold`` are computed via the pipeline's
    own helpers (live ``ExculpatoryEvidence`` rows), not model fields.
    ``sentence_ends_at``/``terminal_due_at`` are the Task 8 frontend's
    countdown source once the case has been tried.
    """

    area_name = serializers.CharField(source="area.name", read_only=True)
    society_name = serializers.CharField(source="society.name", read_only=True)
    evidence_total = serializers.SerializerMethodField()
    release_threshold = serializers.SerializerMethodField()

    class Meta:
        model = JusticeCase
        fields = (
            "id",
            "area_name",
            "society_name",
            "opened_at",
            "evidence_total",
            "release_threshold",
            "failed_outs",
            "sentence_kind",
            "sentence_amount",
            "sentence_ends_at",
            "terminal_due_at",
        )

    def get_evidence_total(self, obj: JusticeCase) -> int:
        from world.justice.pipeline import exculpatory_total  # noqa: PLC0415

        return exculpatory_total(obj)

    def get_release_threshold(self, obj: JusticeCase) -> int:
        from world.justice.pipeline import release_threshold  # noqa: PLC0415

        return release_threshold(obj)

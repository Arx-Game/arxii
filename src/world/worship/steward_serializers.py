"""Serializers for the table page's Beings section (#4333 slice 4).

A stewarded being's table GM reads the being's card (what it favors, its
pledge types and how many outcome tiers each has answers for), writes pledge
types, answers and sacrifice lines, and answers the being's closed pledges.
Every write runs the model's own ``clean`` (an answer's tier limits, a pledge's
closing rite), and an answer's clues come only from the being's catalogue: the
clues its answers already link, since staff create clues.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.clues.models import Clue
from world.worship.constants import BeingResonanceTier, RiteTier
from world.worship.models import (
    Answer,
    AnswerSacrificeLine,
    Pledge,
    WorshippedBeing,
)
from world.worship.steward_services import (
    answer_options,
    answer_window_ends,
    author_credit,
    catalogue_clues,
    closing_tier,
    may_author,
    may_write_free_text,
)


def _request_account(serializer: serializers.BaseSerializer):
    request = serializer.context.get("request")
    return request.user if request is not None else None


def _run_model_clean(instance) -> None:
    """The model's own ``clean`` as a 400 with its field errors."""
    try:
        instance.clean()
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.message_dict) from exc


# ---------------------------------------------------------------------------
# The being card
# ---------------------------------------------------------------------------


class _NamedRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class _OutcomeTierSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    success_level = serializers.IntegerField()


class _CatalogueClueSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    target_kind = serializers.CharField()


class StewardPledgeSerializer(serializers.ModelSerializer):
    """A stewarded being's pledge type, written by its table GM."""

    covered_tiers = serializers.SerializerMethodField()

    class Meta:
        model = Pledge
        fields = [
            "id",
            "being",
            "name",
            "description",
            "favor_target",
            "span_weeks",
            "closing_rite",
            "is_active",
            "covered_tiers",
        ]
        read_only_fields = ["id", "covered_tiers"]

    def get_covered_tiers(self, obj: Pledge) -> list[int]:
        """Outcome tiers with at least one active answer for this pledge type.

        A being card passes every pledge's coverage in ``context["coverage"]``
        (one query for the card); a lone pledge reads its own.
        """
        coverage: dict[int, set[int]] | None = self.context.get("coverage")
        if coverage is not None:
            return sorted(coverage.get(obj.pk, set()))
        return sorted(
            set(obj.answers.filter(is_active=True).values_list("outcome_tier_id", flat=True))
        )

    def validate_being(self, being: WorshippedBeing) -> WorshippedBeing:
        if not may_author(_request_account(self), being):
            msg = "You do not steward that being."
            raise serializers.ValidationError(msg)
        return being

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        if self.instance is not None and attrs.get("being", self.instance.being) != (
            self.instance.being
        ):
            raise serializers.ValidationError({"being": "A pledge type keeps its being."})
        candidate = Pledge(**{**self._current(), **attrs})
        _run_model_clean(candidate)
        return attrs

    def _current(self) -> dict:
        if self.instance is None:
            return {}
        return {field: getattr(self.instance, field) for field in self.Meta.fields[1:-1]}

    def create(self, validated_data: dict) -> Pledge:
        validated_data["written_by"] = author_credit(_request_account(self))
        return super().create(validated_data)


class StewardedBeingSerializer(serializers.ModelSerializer):
    """One being card on the table page, with what its authoring forms need."""

    table = serializers.IntegerField(source="steward.table_id", read_only=True)
    favored_resonances = serializers.SerializerMethodField()
    associated_resonances = serializers.SerializerMethodField()
    favored_facets = serializers.SerializerMethodField()
    closing_rites = serializers.SerializerMethodField()
    pledges = serializers.SerializerMethodField()
    general_covered_tiers = serializers.SerializerMethodField()
    outcome_tiers = serializers.SerializerMethodField()
    catalogue_clues = serializers.SerializerMethodField()
    cost_pools = serializers.SerializerMethodField()

    class Meta:
        model = WorshippedBeing
        fields = [
            "id",
            "name",
            "description",
            "table",
            "favored_resonances",
            "associated_resonances",
            "favored_facets",
            "closing_rites",
            "pledges",
            "general_covered_tiers",
            "outcome_tiers",
            "catalogue_clues",
            "cost_pools",
        ]
        read_only_fields = fields

    def _resonance_names(self, obj: WorshippedBeing, tier: str) -> list[str]:
        return sorted(
            row.resonance.name
            for row in obj.resonances.select_related("resonance")
            if row.tier == tier
        )

    def get_favored_resonances(self, obj: WorshippedBeing) -> list[str]:
        return self._resonance_names(obj, BeingResonanceTier.FAVORED)

    def get_associated_resonances(self, obj: WorshippedBeing) -> list[str]:
        return self._resonance_names(obj, BeingResonanceTier.ASSOCIATED)

    @extend_schema_field(_NamedRowSerializer(many=True))
    def get_favored_facets(self, obj: WorshippedBeing) -> list[dict]:
        rows = obj.being_facets.select_related("facet").order_by("facet__name")
        return [{"id": row.facet_id, "name": row.facet.name} for row in rows]

    @extend_schema_field(_NamedRowSerializer(many=True))
    def get_closing_rites(self, obj: WorshippedBeing) -> list[dict]:
        rites = obj.rites.select_related("kind").exclude(kind__tier=RiteTier.PERILOUS)
        return [{"id": rite.pk, "name": rite.name} for rite in rites.order_by("name")]

    @extend_schema_field(StewardPledgeSerializer(many=True))
    def get_pledges(self, obj: WorshippedBeing) -> list[dict]:
        coverage: dict[int, set[int]] = {}
        for pledge_id, tier_id in obj.answers.filter(
            is_active=True, pledge__isnull=False
        ).values_list("pledge_id", "outcome_tier_id"):
            coverage.setdefault(pledge_id, set()).add(tier_id)
        return StewardPledgeSerializer(
            obj.pledges.order_by("name"), many=True, context={**self.context, "coverage": coverage}
        ).data

    def get_general_covered_tiers(self, obj: WorshippedBeing) -> list[int]:
        return sorted(
            set(
                obj.answers.filter(pledge__isnull=True, is_active=True).values_list(
                    "outcome_tier_id", flat=True
                )
            )
        )

    @extend_schema_field(_OutcomeTierSerializer(many=True))
    def get_outcome_tiers(self, _obj: WorshippedBeing) -> list[dict]:
        from world.traits.models import CheckOutcome  # noqa: PLC0415

        return [
            {"id": tier.pk, "name": tier.name, "success_level": tier.success_level}
            for tier in CheckOutcome.objects.order_by("-success_level", "name")
        ]

    @extend_schema_field(_CatalogueClueSerializer(many=True))
    def get_catalogue_clues(self, obj: WorshippedBeing) -> list[dict]:
        return [
            {"id": clue.pk, "name": clue.name, "target_kind": clue.target_kind}
            for clue in catalogue_clues(obj)
        ]

    @extend_schema_field(_NamedRowSerializer(many=True))
    def get_cost_pools(self, _obj: WorshippedBeing) -> list[dict]:
        from actions.models import ConsequencePool  # noqa: PLC0415

        return [
            {"id": pool.pk, "name": pool.name} for pool in ConsequencePool.objects.order_by("name")
        ]


# ---------------------------------------------------------------------------
# Answers and sacrifice lines
# ---------------------------------------------------------------------------


class StewardSacrificeLineSerializer(serializers.ModelSerializer):
    """One answer's line for one of its being's favored facets."""

    facet_name = serializers.CharField(source="facet.name", read_only=True)

    class Meta:
        model = AnswerSacrificeLine
        fields = ["id", "answer", "facet", "facet_name", "text"]
        read_only_fields = ["id", "facet_name"]

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        current = self.instance
        answer = attrs.get("answer", current.answer if current is not None else None)
        facet = attrs.get("facet", current.facet if current is not None else None)
        if answer is None or not may_author(_request_account(self), answer.being):
            raise serializers.ValidationError({"answer": "You do not steward that being."})
        favored = set(answer.being.being_facets.values_list("facet_id", flat=True))
        if facet is not None and facet.pk not in favored:
            raise serializers.ValidationError(
                {"facet": "A sacrifice line is for one of the being's favored facets."}
            )
        return attrs


class StewardAnswerSerializer(serializers.ModelSerializer):
    """An answer for a stewarded being, with the same tier limits as the staff
    Answer builder. Its clues must already be in the being's catalogue."""

    outcome_tier_name = serializers.CharField(source="outcome_tier.name", read_only=True)
    sacrifice_lines = StewardSacrificeLineSerializer(many=True, read_only=True)

    class Meta:
        model = Answer
        fields = [
            "id",
            "being",
            "pledge",
            "outcome_tier",
            "outcome_tier_name",
            "delay_text",
            "answer_text",
            "fact_text",
            "fact_clue",
            "cost_text",
            "cost_pool",
            "follow_up_text",
            "follow_up_clue",
            "onlooker_line",
            "conceals_source",
            "weight",
            "is_active",
            "sacrifice_lines",
        ]
        read_only_fields = ["id", "outcome_tier_name", "sacrifice_lines"]

    _EDITABLE = (
        "being",
        "pledge",
        "outcome_tier",
        "delay_text",
        "answer_text",
        "fact_text",
        "fact_clue",
        "cost_text",
        "cost_pool",
        "follow_up_text",
        "follow_up_clue",
        "onlooker_line",
        "conceals_source",
        "weight",
        "is_active",
    )

    def validate_being(self, being: WorshippedBeing) -> WorshippedBeing:
        if not may_author(_request_account(self), being):
            msg = "You do not steward that being."
            raise serializers.ValidationError(msg)
        return being

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        current = (
            {field: getattr(self.instance, field) for field in self._EDITABLE}
            if self.instance is not None
            else {}
        )
        merged = {**current, **attrs}
        if self.instance is not None and merged["being"] != self.instance.being:
            raise serializers.ValidationError({"being": "An answer keeps its being."})
        allowed = {clue.pk for clue in catalogue_clues(merged["being"])}
        errors: dict[str, str] = {}
        for field in ("fact_clue", "follow_up_clue"):
            clue: Clue | None = merged.get(field)
            if clue is not None and clue.pk not in allowed:
                errors[field] = "Pick a clue already linked from this being's answers."
        if errors:
            raise serializers.ValidationError(errors)
        _run_model_clean(Answer(**merged))
        return attrs

    def create(self, validated_data: dict) -> Answer:
        validated_data["written_by"] = author_credit(_request_account(self))
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# The steward's answer prompt
# ---------------------------------------------------------------------------


class _AnswerOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    outcome_tier_name = serializers.CharField()
    pledge_name = serializers.CharField()
    answer_text = serializers.CharField()
    delay_text = serializers.CharField()


class StewardPromptSerializer(serializers.Serializer):
    """A ``BEING_ANSWER`` prompt as the steward's answer panel reads it."""

    id = serializers.IntegerField()
    being = serializers.IntegerField()
    being_name = serializers.CharField()
    table = serializers.IntegerField()
    subject_name = serializers.CharField()
    pledge_name = serializers.CharField()
    outcome_tier_name = serializers.CharField()
    sacrificed = serializers.ListField(child=serializers.CharField())
    prayer_text = serializers.CharField()
    options = _AnswerOptionSerializer(many=True)
    may_write_free_text = serializers.BooleanField()
    catalogue_clues = _CatalogueClueSerializer(many=True)
    window_ends_at = serializers.DateTimeField()

    def to_representation(self, prompt) -> dict:
        from world.gm.prompt_services import prompt_subject_name  # noqa: PLC0415
        from world.worship.answer_services import pledge_sacrifices  # noqa: PLC0415

        details = prompt.pledge
        being = details.pledge.being
        tier = closing_tier(details)
        return {
            "id": prompt.pk,
            "being": being.pk,
            "being_name": being.name,
            "table": being.steward.table_id,
            "subject_name": prompt_subject_name(prompt),
            "pledge_name": details.pledge.name,
            "outcome_tier_name": tier.name if tier is not None else "",
            "sacrificed": [offering.item_name for offering in pledge_sacrifices(details)],
            "prayer_text": details.prayer.text if details.prayer is not None else "",
            "options": [
                {
                    "id": answer.pk,
                    "outcome_tier_name": answer.outcome_tier.name,
                    "pledge_name": answer.pledge.name if answer.pledge_id else "",
                    "answer_text": answer.answer_text,
                    "delay_text": answer.delay_text,
                }
                for answer in answer_options(details)
            ],
            "may_write_free_text": may_write_free_text(details),
            "catalogue_clues": [
                {"id": clue.pk, "name": clue.name, "target_kind": clue.target_kind}
                for clue in catalogue_clues(being)
            ],
            "window_ends_at": serializers.DateTimeField().to_representation(
                answer_window_ends(prompt)
            ),
        }


class StewardAnswerRequestSerializer(serializers.Serializer):
    """The panel's send: one authored answer, or the GM's own text and a clue."""

    answer = serializers.IntegerField(required=False, allow_null=True)
    text = serializers.CharField(required=False, allow_blank=True, default="")
    clue = serializers.IntegerField(required=False, allow_null=True)


class StewardActionResultSerializer(serializers.Serializer):
    """What the panel's send or dismiss reports back."""

    detail = serializers.CharField()

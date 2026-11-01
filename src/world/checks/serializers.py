"""Serializers for the checks API."""

from __future__ import annotations

from dataclasses import asdict

from django.db import models
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.checks.constants import ModifierSourceKind
from world.checks.models import CheckCallTarget, CheckType
from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier
from world.checks.outcome_utils import build_outcome_display
from world.scenes.action_constants import DifficultyChoice

# Provenance kinds scoped to staff reads.
_STAFF_ONLY_SOURCE_KINDS = frozenset({ModifierSourceKind.ROLLMOD})


class CheckTypeSerializer(serializers.ModelSerializer):
    """Read-only catalog listing for the web GM check-invocation picker (#3070).

    Mirrors the shared catalog rendering (``check_type_summary``/
    ``format_catalog_row`` in ``world.checks.catalog_invocation``, #3295) so the
    web picker shows the same stat+skill trait pairing a GM sees via telnet
    ``gm check find``.
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    trait_summary = serializers.SerializerMethodField()

    class Meta:
        model = CheckType
        fields = ["id", "name", "category", "category_name", "description", "trait_summary"]
        read_only_fields = fields

    def get_trait_summary(self, obj: CheckType) -> str:
        # Reads the ViewSet's ``to_attr="cached_traits"`` Prefetch when present
        # (list/retrieve via CheckTypeViewSet); falls back to a live query
        # otherwise (e.g. a serializer used directly in a test).
        traits = getattr(obj, "cached_traits", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if traits is None:
            traits = obj.traits.select_related("trait").order_by("-weight")
        names = [ctt.trait.name for ctt in traits]
        return " + ".join(names) if names else ""


class CheckCallTargetSerializer(serializers.Serializer):
    """Read-only payload for one of the requesting player's pending check calls (#3295).

    Mirrors ``GMSummonOfferSerializer``'s shape: answer/decline dispatch through
    the generic REGISTRY action-dispatch endpoint (``answer_check_call``/
    ``decline_check_call``) rather than a DRF action here.
    """

    id = serializers.IntegerField(read_only=True)
    call_id = serializers.IntegerField(source="call.pk", read_only=True)
    check_type_name = serializers.CharField(source="call.check_type.name", read_only=True)
    band = serializers.CharField(source="call.band", read_only=True)
    band_label = serializers.SerializerMethodField()
    caller_display_name = serializers.CharField(source="call.caller_persona.name", read_only=True)
    scene_id = serializers.IntegerField(source="call.scene_id", read_only=True)
    created_at = serializers.DateTimeField(source="call.created_at", read_only=True)

    def get_band_label(self, obj: CheckCallTarget) -> str:
        return DifficultyChoice(obj.call.band).label


class ConsequenceOutcomeModifierSerializer(serializers.ModelSerializer):
    """Serializes a single snapshotted modifier contribution."""

    class Meta:
        model = ConsequenceOutcomeModifier
        fields = ["source_kind", "source_label", "value"]


class OutcomeDisplayRowSerializer(serializers.Serializer):
    """Schema-only shape of get_outcome_display rows (world.checks.types.OutcomeDisplay).

    Never instantiated for serialization — exists so drf-spectacular emits a
    concrete component instead of {[key: string]: unknown} (#2423).
    """

    label = serializers.CharField()
    tier_name = serializers.CharField()
    weight = serializers.IntegerField()
    is_selected = serializers.BooleanField()


class RollLineSerializer(serializers.Serializer):
    """One source row in a roll breakdown (#4858); read-only, schema shape."""

    label = serializers.CharField()
    value = serializers.CharField(allow_blank=True)
    detail = serializers.CharField(allow_blank=True)


class RollBreakdownSerializer(serializers.Serializer):
    """A roll laid out as a heading, source rows and a result line (#4858); read-only."""

    heading = serializers.CharField()
    lines = RollLineSerializer(many=True)
    result = serializers.CharField(allow_blank=True)


class ConsequenceOutcomeListSerializer(serializers.ListSerializer):
    """Builds every Strike roll breakdown on the page at once (#4858).

    The breakdowns go to the child serializer through ``context["roll_breakdowns"]``, an
    explicit argument built once for the page, so each row's field reads it with no query.
    """

    def to_representation(self, data: object) -> list:
        from world.combat.services.declarations.strike import (  # noqa: PLC0415
            strike_roll_breakdowns,
        )

        rows = list(data.all()) if isinstance(data, models.Manager) else list(data)
        self.child.context["roll_breakdowns"] = strike_roll_breakdowns(rows)
        return super().to_representation(rows)


class ConsequenceOutcomeSerializer(serializers.ModelSerializer):
    """Read serializer for ConsequenceOutcome.

    Recomputes the roulette display on every read from the persisted pool +
    selected_consequence so the frontend always receives the full weighted
    roulette (outcome_display) rather than storing it.

    When pool is None (challenge-based resolution), the roulette is
    reconstructed from the authored consequence links on the approach and
    challenge template — no pool is stored; no denormalization occurs.

    Interaction sources are exposed as plain integer ids to avoid touching the
    range-partitioned arxii_interaction table at serialization time.
    """

    modifiers = serializers.SerializerMethodField()
    modifier_total = serializers.SerializerMethodField()
    outcome_display = serializers.SerializerMethodField()
    combat_interaction_id = serializers.IntegerField(read_only=True)
    challenge_record_id = serializers.IntegerField(read_only=True)
    action_interaction_id = serializers.IntegerField(read_only=True, allow_null=True)
    roll_breakdown = serializers.SerializerMethodField()

    def _visible_kinds_filter(self, rows: list) -> list:
        """Modifier rows visible to the requesting user (staff see all kinds)."""
        request = self.context.get("request")
        if request is not None and request.user is not None and request.user.is_staff:
            return rows
        return [m for m in rows if m.source_kind not in _STAFF_ONLY_SOURCE_KINDS]

    @extend_schema_field(ConsequenceOutcomeModifierSerializer(many=True))
    def get_modifiers(self, obj: ConsequenceOutcome) -> list[dict]:
        rows = self._visible_kinds_filter(list(obj.modifiers.all()))
        return ConsequenceOutcomeModifierSerializer(rows, many=True).data

    @extend_schema_field(serializers.IntegerField())
    def get_modifier_total(self, obj: ConsequenceOutcome) -> int:
        rows = list(obj.modifiers.all())
        visible = self._visible_kinds_filter(rows)
        if len(visible) == len(rows):
            return obj.modifier_total
        hidden = sum(m.value for m in rows if m not in visible)
        return obj.modifier_total - hidden

    class Meta:
        model = ConsequenceOutcome
        fields = [
            "id",
            "character",
            "check_type",
            "pool",
            "selected_consequence",
            "modifier_total",
            "summary",
            "outcome_display",
            "modifiers",
            "combat_interaction_id",
            "challenge_record_id",
            "action_interaction_id",
            "roll_breakdown",
            "created_at",
        ]
        read_only_fields = fields
        list_serializer_class = ConsequenceOutcomeListSerializer

    @extend_schema_field(RollBreakdownSerializer(allow_null=True))
    def get_roll_breakdown(self, obj: ConsequenceOutcome) -> dict[str, object] | None:
        """The roll as rows when its system lays it out (a Strike, #4858), else None.

        The roll's modifiers a viewer may see follow the system's own rows, before the
        result line.
        """
        breakdowns = self.context.get("roll_breakdowns")
        if breakdowns is None:
            from world.combat.services.declarations.strike import (  # noqa: PLC0415
                strike_roll_breakdowns,
            )

            breakdowns = strike_roll_breakdowns([obj])
        breakdown = breakdowns.get(obj.pk)
        if breakdown is None:
            return None
        from world.combat.constants import INTENSITY_MODIFIER_LABEL  # noqa: PLC0415

        lines = [asdict(line) for line in breakdown.lines]
        for modifier in self._visible_kinds_filter(list(obj.modifiers.all())):
            signed = f"+{modifier.value}" if modifier.value >= 0 else str(modifier.value)
            detail = (
                "misses add to hit"
                if modifier.source_label == INTENSITY_MODIFIER_LABEL
                else modifier.get_source_kind_display()
            )
            lines.append({"label": modifier.source_label, "value": signed, "detail": detail})
        return {"heading": breakdown.heading, "lines": lines, "result": breakdown.result}

    @extend_schema_field(OutcomeDisplayRowSerializer(many=True))
    def get_outcome_display(self, obj: ConsequenceOutcome) -> list[dict]:
        """Recompute the roulette from pool + selected_consequence on read.

        When pool is not None, reads pool entries and parent entries from the
        prefetch cache (populated by the ViewSet's _POOL_ENTRIES_PREFETCH /
        _PARENT_ENTRIES_PREFETCH Prefetch objects) so no additional queries are
        issued per row.  Mirrors the pool-walk logic of
        resolve_pool_consequences() but operates on already-fetched data.

        When pool is None (challenge-based resolution), reconstructs the
        consequence list from the authored ApproachConsequence and
        ChallengeTemplateConsequence links via the challenge_record.  Uses
        prefetch caches populated by the ViewSet's challenge-link Prefetch
        objects.

        Returns a list of plain dicts matching OutcomeDisplay's fields.
        """
        pool = obj.pool
        if pool is None and obj.challenge_record_id is None:
            # A roll with no roulette at all (a Strike's hit or damage roll, #4858): there
            # is no pool to show, and the "Unknown" placeholder is not a result.
            return []
        if pool is None:
            all_consequences = self._reconstruct_consequences_from_links(obj)
            display_items = build_outcome_display(all_consequences, obj.selected_consequence)
            return [asdict(item) for item in display_items]

        # Read from prefetch cache — pool.entries.all() hits the cache when
        # the ViewSet has declared a Prefetch for "pool__entries".
        own_entries = list(pool.entries.all())

        if pool.parent_id is None:
            all_consequences = [e.consequence for e in own_entries if not e.is_excluded]
        else:
            excluded_ids = {e.consequence_id for e in own_entries if e.is_excluded}
            # pool.parent.entries.all() hits the _PARENT_ENTRIES_PREFETCH cache.
            parent_consequences = [
                e.consequence
                for e in pool.parent.entries.all()
                if e.consequence_id not in excluded_ids
            ]
            own_included = [e.consequence for e in own_entries if not e.is_excluded]
            all_consequences = parent_consequences + own_included

        display_items = build_outcome_display(all_consequences, obj.selected_consequence)
        return [asdict(item) for item in display_items]

    def _reconstruct_consequences_from_links(self, obj: ConsequenceOutcome) -> list:
        """Reconstruct the consequence list from authored links when pool is None.

        Gathers consequences from:
        1. The approach's ApproachConsequence rows (approach.consequences prefetch)
        2. The challenge template's ChallengeTemplateConsequence rows
           (challenge_instance.template.challenge_consequences prefetch)

        Deduplication is by consequence PK; approach-level consequences come
        first (matching resolution-time ordering), followed by template-level
        consequences not already included.

        Returns an empty list if challenge_record is absent (defensive only —
        pool=None outcomes are always expected to have a challenge_record).
        """
        record = obj.challenge_record
        if record is None:
            return []

        seen_pks: set[int] = set()
        consequences = []

        # Approach-level consequences first (ApproachConsequence.related_name="consequences")
        for link in record.approach.consequences.all():
            c = link.consequence
            if c.pk not in seen_pks:
                seen_pks.add(c.pk)
                consequences.append(c)

        # Template-level consequences
        # (ChallengeTemplateConsequence.related_name="challenge_consequences")
        template = record.challenge_instance.template
        for link in template.challenge_consequences.all():
            c = link.consequence
            if c.pk not in seen_pks:
                seen_pks.add(c.pk)
                consequences.append(c)

        return consequences

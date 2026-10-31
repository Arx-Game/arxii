"""Serializers for combat API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema_field
from evennia.accounts.models import AccountDB
from rest_framework import serializers

from world.areas.positioning.serializers import (
    HeldPositionSerializer,
    PositionAdjacencyItemSerializer,
    PositionEdgeSerializer,
    PositionNodeSerializer,
    PositionSummarySerializer,
    SquareSerializer,
)
from world.checks.serializers import ConsequenceOutcomeSerializer
from world.combat.constants import (
    ENTITY_TYPE_PC,
    SIGNIFICANT_NPC_TIERS,
    ActionCategory,
    ClashActionSlot,
    ClashStatus,
    EncounterOutcome,
    OpponentStatus,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
    SurgeTriggerKind,
)
from world.combat.models import (
    Clash,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    ConsiderReading,
    CreatureTemplate,
    DramaticSurgeRecord,
    DuelChallenge,
    EscalationCurve,
    PendingSelection,
    SurgeTuning,
    SustainedAction,
    ThreatPool,
)
from world.conditions.serializers import ConditionInstanceSerializer
from world.conditions.services import get_active_conditions
from world.fatigue.services import get_fatigue_capacity
from world.magic.constants import AudereCeremony
from world.magic.models import CharacterTechnique, Technique
from world.scenes.constants import PersonaType, RoundStatus
from world.standoffs.serializers import (
    GMStandoffViewSerializer,
    StandoffSummarySerializer,
    StandoffViewSerializer,
)
from world.standoffs.services.gm_view import build_gm_standoff_view, build_standoff_summary
from world.standoffs.services.view import build_standoff_view

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evennia.objects.models import ObjectDB

    from world.combat.types import ComboSlotFill
    from world.mechanics.engagement import CharacterEngagement
    from world.scenes.models import Persona

# ---------------------------------------------------------------------------
# Condition helpers
# ---------------------------------------------------------------------------


# Serializer-context key holding the active ConditionInstances for every target
# in the payload, ``{object id: [ConditionInstance, ...]}``. The viewset loads it
# once per request (ADR-0260); a bare ``Prefetch(to_attr=...)`` on the
# idmapper-shared ObjectDB would outlive the request and go stale (ADR-0263).
ACTIVE_CONDITIONS_CONTEXT_KEY = "active_conditions_by_object_id"


def _context_active_conditions(target: ObjectDB, context: dict[str, Any]) -> list | None:
    """The request's preloaded active ConditionInstances on ``target``, or None.

    None means the caller built the serializer outside the viewset (websocket
    push, telnet, unit tests) and the caller falls back to a query.
    """
    by_object_id = context.get(ACTIVE_CONDITIONS_CONTEXT_KEY)
    if by_object_id is None:
        return None
    return by_object_id.get(target.pk, [])


def _serialize_active_conditions(
    target: ObjectDB,
    *,
    can_view_hidden: bool,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Serialize a target's active conditions, filtered by visibility.

    Public conditions (``is_visible_to_others=True``) are always included;
    hidden ones only when ``can_view_hidden`` is True (owner/GM/staff).
    Results are ordered by the template's ``display_priority`` (highest
    first). Reuses ``ConditionInstanceSerializer``.

    Prefers the viewset's per-request ``ACTIVE_CONDITIONS_CONTEXT_KEY`` dict
    (built with the same select_related + suppression filter as
    ``get_active_conditions``) — visibility filter + priority ordering run
    in Python over that list, so no per-row query fires.
    Falls back to ``get_active_conditions`` for callers that build the
    serializer directly (e.g. unit tests).
    """
    cached = _context_active_conditions(target, context)
    if cached is not None:
        instances = [
            inst for inst in cached if can_view_hidden or inst.condition.is_visible_to_others
        ]
        instances.sort(key=lambda inst: inst.condition.display_priority, reverse=True)
    else:
        qs = get_active_conditions(target)
        if not can_view_hidden:
            qs = qs.filter(condition__is_visible_to_others=True)
        instances = list(qs.order_by("-condition__display_priority"))
    return ConditionInstanceSerializer(instances, many=True, context=context).data


def _audere_state(
    target: ObjectDB,
    *,
    can_view_hidden: bool,
    context: dict[str, Any],
) -> str | None:
    """``"audere_majora"`` / ``"audere"`` / ``None`` for a participant's character (#4739).

    Found by the AudereThreshold's designated templates, never by name, so the web
    client's Audere strip does not care what staff call the conditions. Majora wins
    when both hold. Reads the same per-request active-condition list (and visibility
    rule) as ``_serialize_active_conditions``; falls back to a query without one.
    """
    from world.magic.audere import AudereThreshold  # noqa: PLC0415

    cached = _context_active_conditions(target, context)
    if cached is None:
        cached = list(get_active_conditions(target).select_related("condition"))
    held = {
        inst.condition_id
        for inst in cached
        if can_view_hidden or inst.condition.is_visible_to_others
    }
    if not held:
        return None
    threshold = AudereThreshold.objects.cached_singleton()
    if threshold is None:
        return None
    majora_id = threshold.audere_majora_condition_id
    audere_id = threshold.audere_condition_id
    if majora_id is not None and majora_id in held:
        return AudereCeremony.AUDERE_MAJORA.value
    if audere_id is not None and audere_id in held:
        return AudereCeremony.AUDERE.value
    return None


# ---------------------------------------------------------------------------
# Nested read serializers
# ---------------------------------------------------------------------------


def _square_payload(
    objectdb: ObjectDB | None,  # noqa: OBJECTDB_PARAM - a PC or an NPC's game object
) -> dict[str, int] | None:
    """The ``{x, y}`` of the battle-map square an object stands on, or None (#4651)."""
    from world.areas.positioning.services import square_of  # noqa: PLC0415

    square = square_of(objectdb) if objectdb is not None else None
    return {"x": square[0], "y": square[1]} if square is not None else None


class OpponentSerializer(serializers.ModelSerializer):
    """Read serializer for combat opponents.

    Soak value and probing threshold are GM-only — players discover
    these through gameplay (probing attacks, combo availability).

    ``level`` (#2707) is the opposite: a plain model field, deliberately
    PUBLIC and ungated. Threat assessment is the point -- players are meant
    to be able to look at an opponent and gauge whether they're punching up
    or down, so unlike soak_value/probing_threshold this is not wrapped in a
    SerializerMethodField behind ``_is_gm_or_staff``.

    Boss/morale readouts (phase count, damage multiplier, break bar, morale)
    are GM-only on the same gate (#3552); ``is_enraged`` and ``is_wall_broken``
    are public derived booleans, since the room narration has already told
    everyone the boss enraged or its wall broke.
    """

    soak_value = serializers.SerializerMethodField()
    probing_threshold = serializers.SerializerMethodField()
    # GM-only boss/morale readouts (#3552) - None for everyone else, the same
    # gate as soak_value / probing_threshold. Public badges derive from state
    # the room has already been narrated (phase line, enrage line, break
    # celebration), never from surge records (curve-gated, ADR-0098).
    phase_count = serializers.SerializerMethodField()
    damage_multiplier = serializers.SerializerMethodField()
    break_bar_current = serializers.SerializerMethodField()
    break_bar_threshold = serializers.SerializerMethodField()
    vulnerability_rounds_remaining = serializers.SerializerMethodField()
    morale = serializers.SerializerMethodField()
    max_morale = serializers.SerializerMethodField()
    morale_state = serializers.SerializerMethodField()
    is_enraged = serializers.SerializerMethodField()
    is_wall_broken = serializers.SerializerMethodField()
    active_conditions = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    thumbnail_media_url = serializers.SerializerMethodField()
    current_position = PositionSummarySerializer(read_only=True, allow_null=True)
    current_square = serializers.SerializerMethodField()
    # The in-world ObjectDB pk, distinct from this opponent's own pk (``id``).
    # ``id`` is the CombatOpponent PK the focused-target dispatch sends as
    # ``focused_opponent_target_id``; ``objectdb_id`` is the ObjectDB pk the
    # applicable-pulls API consumes as ``target_object_id``. Plain FK column —
    # no query. Null for opponents with no backing ObjectDB.
    objectdb_id = serializers.IntegerField(read_only=True, allow_null=True)
    # Public combat-side classification lets target pickers omit friendly summons.
    # Optional here keeps cached clients compatible while exposing the public side.
    allegiance = serializers.CharField(required=False, allow_null=True, default=None)
    # Duel mirror: FK PK column — no query. Non-null iff this opponent is a
    # passive surface mirroring a PC participant (is_duel_mirror == True).
    # The UI uses this to render the opponent as the opposing duelist rather
    # than a generic NPC.
    mirrors_participant_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = CombatOpponent
        fields = [
            "id",
            "objectdb_id",
            "name",
            "description",
            "tier",
            "level",
            "health",
            "max_health",
            "soak_value",
            "probing_current",
            "probing_threshold",
            "current_phase",
            "phase_count",
            "damage_multiplier",
            "break_bar_current",
            "break_bar_threshold",
            "vulnerability_rounds_remaining",
            "morale",
            "max_morale",
            "morale_state",
            "is_enraged",
            "is_wall_broken",
            "status",
            "allegiance",
            "active_conditions",
            "thumbnail_url",
            "thumbnail_media_url",
            "current_position",
            "current_square",
            "mirrors_participant_id",
        ]

    @extend_schema_field(SquareSerializer(allow_null=True))
    def get_current_square(self, obj: CombatOpponent) -> dict[str, int] | None:
        return _square_payload(obj.objectdb)

    def _is_gm_or_staff(self) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return self.context.get("is_gm", False)

    def get_soak_value(self, obj: CombatOpponent) -> int | None:
        """Soak value — GM/staff only."""
        return obj.soak_value if self._is_gm_or_staff() else None

    def get_probing_threshold(self, obj: CombatOpponent) -> int | None:
        """Probing threshold — GM/staff only."""
        return obj.probing_threshold if self._is_gm_or_staff() else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_phase_count(self, obj: CombatOpponent) -> int | None:
        """How many authored phases this boss has - GM/staff, BOSS tier only."""
        if not self._is_gm_or_staff() or obj.tier != OpponentTier.BOSS:
            return None
        return obj.phases.count()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_damage_multiplier(self, obj: CombatOpponent) -> str | None:
        return str(obj.damage_multiplier) if self._is_gm_or_staff() else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_break_bar_current(self, obj: CombatOpponent) -> int | None:
        return obj.break_bar_current if self._is_gm_or_staff() else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_break_bar_threshold(self, obj: CombatOpponent) -> int | None:
        return obj.break_bar_threshold if self._is_gm_or_staff() else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_vulnerability_rounds_remaining(self, obj: CombatOpponent) -> int | None:
        return obj.vulnerability_rounds_remaining if self._is_gm_or_staff() else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_morale(self, obj: CombatOpponent) -> int | None:
        return obj.morale if self._is_gm_or_staff() else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_max_morale(self, obj: CombatOpponent) -> int | None:
        return obj.max_morale if self._is_gm_or_staff() else None

    def get_morale_state(self, obj: CombatOpponent) -> str:
        """Derived STEADY/FALTER/BREAK - pure arithmetic, no query.

        Public: the derived state is observable behaviour; the number stays
        GM-only (#4147).
        """
        from world.combat.morale import morale_state_for  # noqa: PLC0415

        return morale_state_for(obj).value

    def get_is_enraged(self, obj: CombatOpponent) -> bool:
        """Public: the enrage line has fired (a transition raised the multiplier)."""
        return obj.current_phase > 1 and obj.damage_multiplier > 1

    def get_is_wall_broken(self, obj: CombatOpponent) -> bool:
        """Public: the break celebration named this boss and the window is open."""
        return obj.vulnerability_rounds_remaining > 0

    def get_active_conditions(self, obj: CombatOpponent) -> list[dict[str, Any]]:
        """Active conditions on this opponent's in-world ObjectDB.

        Public conditions (``is_visible_to_others=True``) are shown to
        everyone; hidden conditions only to GM/staff. Ordered by
        ``display_priority`` (highest first). Opponents with no backing
        ObjectDB (or none applied) serialize to ``[]``.
        """
        target = obj.objectdb
        if target is None:
            return []
        return _serialize_active_conditions(
            target,
            can_view_hidden=self._is_gm_or_staff(),
            context=self.context,
        )

    def get_thumbnail_url(self, obj: CombatOpponent) -> str | None:
        """Direct portrait URL, resolved through the opponent's persona.

        Mirrors ``PersonaSerializer.thumbnail_url`` (the persona's
        ``thumbnail_url`` URLField — ``""`` when unset). Persona-less
        opponents (``persona=None``) return ``None``.
        """
        if obj.persona_id is None:
            return None
        return obj.persona.thumbnail_url

    def get_thumbnail_media_url(self, obj: CombatOpponent) -> str | None:
        """Media portrait URL, dynamically resolved (#2196).

        Uses ``resolve_thumbnail()`` when the opponent has a persona (character).
        For persona-less (generic/ephemeral) NPCs, falls back to the opponent's
        own ``portrait`` FK via ``fallback_media``.
        """
        from world.conditions.thumbnail_services import resolve_thumbnail  # noqa: PLC0415

        if obj.persona_id is not None:
            try:
                character = obj.persona.character_sheet.character
            except AttributeError:
                character = None
            target = character or obj.objectdb
            # #2196: use prefetched conditions from the view (on objectdb)
            # Suppression justified: live/time-derived set on identity-mapped parent; (#2401) — a
            # context-over-cache never cached_property.
            cached_conditions = getattr(obj.objectdb, "active_condition_instances", None)  # noqa: GETATTR_LITERAL
            return resolve_thumbnail(
                target,
                persona=obj.persona,
                fallback_media=obj.portrait,
                cached_conditions=cached_conditions,
            )
        # Persona-less NPC — use portrait FK directly
        if obj.portrait_id is not None:
            return obj.portrait.cloudinary_url
        return None


class AftermathRecognitionSerializer(serializers.Serializer):
    """Safe causal label shape; source ids and check quality are never exposed."""

    key = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()


class AftermathLegendSerializer(serializers.Serializer):
    """Schema-only shape of one legend line in an aftermath digest (#3551)."""

    title = serializers.CharField()
    description = serializers.CharField()
    base_value = serializers.IntegerField()
    recognition = AftermathRecognitionSerializer(many=True)


class AftermathBeatSerializer(serializers.Serializer):
    """Schema-only shape of the beat line in an aftermath digest (#3551)."""

    outcome = serializers.CharField()
    tier_name = serializers.CharField(allow_null=True)
    resolution_text = serializers.CharField()


class ObjectiveBranchSerializer(serializers.Serializer):
    """Safe read shape for an authored objective branch (#3916)."""

    key = serializers.CharField()
    column = serializers.CharField(allow_null=True)
    outcome = serializers.CharField(required=False)
    label = serializers.CharField()


class ObjectiveSnapshotSerializer(serializers.Serializer):
    """Safe read shape for the existing objective routing primitives (#3916)."""

    key = serializers.CharField()
    source = serializers.ChoiceField(choices=["scenario", "stakes"])
    label = serializers.CharField(allow_blank=True)
    clock = serializers.DictField(allow_null=True)
    branches = ObjectiveBranchSerializer(many=True)


class WonOverRowSerializer(serializers.Serializer):
    """Schema-only shape of one AftermathDigest.won_over row (#4091).

    Never instantiated for output.
    """

    opponent_id = serializers.IntegerField()
    name = serializers.CharField()
    verb = serializers.CharField()
    source_label = serializers.CharField()
    nameless = serializers.BooleanField()
    persona_id = serializers.IntegerField(allow_null=True)
    present = serializers.BooleanField()
    condition = ConditionInstanceSerializer(allow_null=True)
    holds_until_settled = serializers.BooleanField()
    strength = serializers.IntegerField()
    can_bind = serializers.BooleanField()
    can_take_into_service = serializers.BooleanField()
    can_send_away = serializers.BooleanField()
    can_settle = serializers.BooleanField()
    bind_window_open = serializers.BooleanField()


class AftermathDigestSerializer(serializers.Serializer):
    """Schema-only shape of ParticipantSerializer.aftermath (#3551).

    Never instantiated for output.
    """

    outcome = serializers.CharField()
    consequence = ConsequenceOutcomeSerializer(allow_null=True)
    conditions = ConditionInstanceSerializer(many=True)
    legend = AftermathLegendSerializer(many=True)
    beat = AftermathBeatSerializer(allow_null=True)
    objective = ObjectiveSnapshotSerializer(allow_null=True)
    peril_round_active = serializers.BooleanField()
    won_over = WonOverRowSerializer(many=True)


class DodgeLandingSerializer(serializers.Serializer):
    """One place a dodge can land in (#4676)."""

    id = serializers.IntegerField()
    name = serializers.CharField()


class DodgePlanSerializer(serializers.Serializer):
    """Schema-only shape of the viewer's own dodge plan (#4676). Private to its owner."""

    enabled = serializers.BooleanField()
    landing_id = serializers.IntegerField(allow_null=True)
    options = DodgeLandingSerializer(many=True)
    cost_line = serializers.CharField()


class CompulsionActionCostSerializer(serializers.Serializer):
    """One action's cost under a compulsion (#4802). Schema-only."""

    action_key = serializers.CharField(help_text="A maneuver value, or technique_no_target.")
    difficulty = serializers.IntegerField()
    forbidden = serializers.BooleanField()


class CompulsionSerializer(serializers.Serializer):
    """The viewer's own compulsion and what going against it costs (#4802). Schema-only."""

    condition_name = serializers.CharField()
    wants_label = serializers.CharField()
    check_name = serializers.CharField()
    against = CompulsionActionCostSerializer(many=True)


class SteadyPlanSerializer(serializers.Serializer):
    """The viewer's own steady plan (#4802). Schema-only."""

    enabled = serializers.BooleanField()
    cost_line = serializers.CharField()
    bonus_hint = serializers.CharField()


class DigDeepOfferSerializer(serializers.Serializer):
    """What digging deep costs the viewer's own character right now (#4738); read-only."""

    free_dig_deeps = serializers.IntegerField(help_text="Free dig deeps she holds.")
    fatigue_category = serializers.CharField(help_text="Fatigue pool a dig deep is paid from.")
    fatigue_cost = serializers.IntegerField(
        help_text="Fatigue a dig deep costs without a free one."
    )
    dug_deep_this_round = serializers.BooleanField(
        help_text="Whether she has already dug deep this round."
    )
    given_by = serializers.CharField(
        allow_null=True,
        help_text="Name of the ally whose encouragement gave her free dig deeps, if any.",
    )


class ParticipantSerializer(serializers.ModelSerializer):
    """Read serializer for combat participants.

    Vitals (health, max_health, character_status) are private by default.
    Only visible to staff, the scene GM, or the player who owns the
    character — same visibility rules as character sheets.
    """

    character_name = serializers.CharField(
        source="character_sheet.character.db_key",
        read_only=True,
    )
    health = serializers.SerializerMethodField()
    max_health = serializers.SerializerMethodField()
    character_status = serializers.SerializerMethodField()
    available_strain = serializers.SerializerMethodField()
    fatigue = serializers.SerializerMethodField()
    active_conditions = serializers.SerializerMethodField()
    audere_state = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    thumbnail_media_url = serializers.SerializerMethodField()
    escalation_level = serializers.SerializerMethodField()
    intensity_modifier = serializers.SerializerMethodField()
    control_modifier = serializers.SerializerMethodField()
    fury_control_surrendered = serializers.SerializerMethodField()
    current_position = PositionSummarySerializer(read_only=True, allow_null=True)
    current_square = serializers.SerializerMethodField()
    aftermath = serializers.SerializerMethodField()
    reactions_used = serializers.SerializerMethodField(required=False)
    dodge_plan = serializers.SerializerMethodField()
    compulsion = serializers.SerializerMethodField()
    steady_plan = serializers.SerializerMethodField()
    dig_deep = serializers.SerializerMethodField()

    class Meta:
        model = CombatParticipant
        fields = [
            "id",
            "character_sheet_id",
            "character_name",
            "status",
            "health",
            "max_health",
            "character_status",
            "available_strain",
            "fatigue",
            "active_conditions",
            "audere_state",
            "thumbnail_url",
            "thumbnail_media_url",
            "escalation_level",
            "intensity_modifier",
            "control_modifier",
            "fury_control_surrendered",
            "current_position",
            "current_square",
            "aftermath",
            "reactions_used",
            "dodge_plan",
            "compulsion",
            "steady_plan",
            "dig_deep",
        ]

    @extend_schema_field(DigDeepOfferSerializer(allow_null=True))
    def get_dig_deep(self, obj: CombatParticipant) -> dict[str, Any] | None:
        """What digging deep costs the viewer's own character (#4738); None for anyone else."""
        if not self._is_viewers_own(obj):
            return None
        from world.combat.services.encounter.config import get_strain_config  # noqa: PLC0415

        engagement = self._combat_engagement(obj)
        config = get_strain_config()
        return {
            "free_dig_deeps": engagement.free_dig_deeps if engagement is not None else 0,
            "fatigue_category": config.dig_deep_fatigue_category,
            "fatigue_cost": config.dig_deep_fatigue_cost,
            "dug_deep_this_round": engagement is not None
            and engagement.last_dug_deep_round == obj.encounter.round_number,
            "given_by": self._dig_deep_giver_name(engagement),
        }

    @staticmethod
    def _dig_deep_giver_name(engagement: CharacterEngagement | None) -> str | None:
        """The name others know the free dig deeps' giver by, or None."""
        if engagement is None or engagement.free_dig_deeps <= 0:
            return None
        giver_id = engagement.free_dig_deeps_given_by_id
        if giver_id is None:
            return None
        from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

        return persona_names_for_sheets([giver_id]).get(giver_id)

    @extend_schema_field(SquareSerializer(allow_null=True))
    def get_current_square(self, obj: CombatParticipant) -> dict[str, int] | None:
        return _square_payload(obj.character_sheet.character)

    @extend_schema_field(DodgePlanSerializer(allow_null=True))
    def get_dodge_plan(self, obj: CombatParticipant) -> dict[str, Any] | None:
        """The viewer's own dodge plan and choices (#4676); None for anyone else.

        Never shown to other players or to a GM: where she means to land shows only
        when it happens. None also when nothing she has lets her dodge.
        """
        if not self._is_viewers_own(obj):
            return None
        from world.combat.services.reactions import (  # noqa: PLC0415
            dodge_cost_line,
            dodge_landing_options,
            dodge_sources,
        )

        sources = dodge_sources(obj)
        if not sources:
            return None
        return {
            "enabled": obj.dodge_enabled,
            "landing_id": obj.dodge_landing_id,
            "options": [{"id": p.pk, "name": p.name} for p in dodge_landing_options(obj)],
            "cost_line": dodge_cost_line(sources[0]),
        }

    @extend_schema_field(CompulsionSerializer(allow_null=True))
    def get_compulsion(self, obj: CombatParticipant) -> dict[str, Any] | None:
        """What the viewer's compulsion wants and costs (#4802); None for anyone else."""
        if not self._is_viewers_own(obj):
            return None
        from world.combat.compulsion import compulsion_summary  # noqa: PLC0415

        summary = compulsion_summary(obj)
        if summary is None:
            return None
        return {
            "condition_name": summary.condition_name,
            "wants_label": summary.wants_label,
            "check_name": summary.check_name,
            "against": [
                {"action_key": c.action_key, "difficulty": c.difficulty, "forbidden": c.forbidden}
                for c in summary.against
            ],
        }

    @extend_schema_field(SteadyPlanSerializer(allow_null=True))
    def get_steady_plan(self, obj: CombatParticipant) -> dict[str, Any] | None:
        """The viewer's own steady plan; None for anyone else or when nothing lets her steady."""
        if not self._is_viewers_own(obj):
            return None
        from world.combat.models import MovementConfig  # noqa: PLC0415
        from world.combat.services.reactions import steady_capability_value  # noqa: PLC0415

        capability = steady_capability_value(obj)
        config = MovementConfig.objects.cached_singleton()
        if capability <= 0 or config is None:
            return None
        return {
            "enabled": obj.steady_enabled,
            "cost_line": f"{config.steady_anima_cost} anima each",
            "bonus_hint": f"+{capability}",
        }

    def _is_viewers_own(self, obj: CombatParticipant) -> bool:
        """True when the requesting account plays this participant's character."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        viewer_character_ids = self.context.get("viewer_character_ids")
        if viewer_character_ids is None:
            try:
                viewer_character_ids = request.user.played_character_sheet_ids
            except AttributeError:
                viewer_character_ids = frozenset()
            self.context["viewer_character_ids"] = viewer_character_ids
        return obj.character_sheet.character_id in viewer_character_ids

    def _can_view_vitals(self, obj: CombatParticipant) -> bool:
        """Check if the requesting user can see this participant's vitals.

        Allowed for: staff, scene GMs, or the player who owns the character.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        # Check if viewer owns this character. Reads the context entry
        # populated by EncounterDetailSerializer._build_serializer_context,
        # falling back to the Account-level cached property.
        viewer_character_ids = self.context.get("viewer_character_ids")
        if viewer_character_ids is None:
            try:
                viewer_character_ids = request.user.played_character_sheet_ids
            except AttributeError:
                viewer_character_ids = frozenset()
            self.context["viewer_character_ids"] = viewer_character_ids
        if obj.character_sheet.character_id in viewer_character_ids:
            return True
        # Check GM status — prefer cached value, fall back to model method
        is_gm = self.context.get("is_gm")
        if is_gm is None:
            encounter = obj.encounter
            is_gm = encounter.scene.is_gm(request.user) if encounter.scene else False
        return is_gm

    def get_reactions_used(self, obj: CombatParticipant) -> int | None:
        """Return spent reactions only to the owner, GM, or staff."""
        return obj.reactions_used if self._can_view_vitals(obj) else None

    def get_health(self, obj: CombatParticipant) -> int | None:
        """Return current health — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.health
        except AttributeError:
            return None

    def get_max_health(self, obj: CombatParticipant) -> int | None:
        """Return max health — only if viewer has permission."""
        if not self._can_view_vitals(obj):
            return None
        try:
            return obj.character_sheet.vitals.max_health
        except AttributeError:
            return None

    def get_character_status(self, obj: CombatParticipant) -> str | None:
        """Return a coarse, read-only life status — only if viewer has permission.

        Derived at read time from life_state + active conditions + agency (there
        is no persisted status field anymore). The richer frontend status surface
        is tracked by #521/#522.
        """
        if not self._can_view_vitals(obj):
            return None
        from world.vitals.services import (  # noqa: PLC0415
            derive_character_status,
        )

        try:
            character_sheet = obj.character_sheet
        except AttributeError:
            return None
        if character_sheet is None:
            return None
        return derive_character_status(character_sheet)

    def get_available_strain(self, obj: CombatParticipant) -> int | None:
        """Return strain budget (anima pool) — only if viewer owns the PC.

        Uses the same vitals-visibility rules as health/status fields.
        The frontend's YourTurn strain slider reads this as its max value.
        """
        if not self._can_view_vitals(obj):
            return None
        return obj.available_strain

    def get_fatigue(self, obj: CombatParticipant) -> dict[str, dict[str, int]] | None:
        """Return the three fatigue pools (physical/social/mental).

        Each pool is ``{"current": N, "capacity": M}``. ``current`` reads the
        persisted ``FatiguePool`` row (0 when no row exists yet); ``capacity``
        is derived from the character's endurance stats via
        ``get_fatigue_capacity``. Gated by the same vitals-visibility rules as
        health/strain — outsiders get ``None``.

        The frontend's VitalPools component reads this to render fatigue bars
        (replacing the ``0/10`` placeholder). See #552.
        """
        if not self._can_view_vitals(obj):
            return None
        try:
            character_sheet = obj.character_sheet
        except AttributeError:
            return None
        if character_sheet is None:
            return None

        # Read the prefetched OneToOne (select_related on the viewset queryset)
        # exactly once — no per-category re-query. None when no row exists yet.
        fatigue_pool = character_sheet.fatigue_or_none
        well_rested = fatigue_pool.well_rested if fatigue_pool else False
        pools: dict[str, dict[str, int]] = {}
        for category in ActionCategory:
            current = fatigue_pool.get_current(category.value) if fatigue_pool else 0
            pools[category.value] = {
                "current": current,
                "capacity": get_fatigue_capacity(
                    character_sheet,
                    category.value,
                    well_rested=well_rested,
                ),
            }
        return pools

    def get_active_conditions(self, obj: CombatParticipant) -> list[dict[str, Any]]:
        """Active conditions on this participant's character ObjectDB.

        Public conditions (``is_visible_to_others=True``) are shown to
        everyone; hidden conditions only to the character's owner, GMs, or
        staff — reusing the same ownership gate as vitals
        (``_can_view_vitals``). Ordered by ``display_priority`` (highest
        first). No conditions → ``[]``.
        """
        try:
            character_sheet = obj.character_sheet
        except AttributeError:
            return []
        if character_sheet is None:
            return []
        return _serialize_active_conditions(
            character_sheet.character,
            can_view_hidden=self._can_view_vitals(obj),
            context=self.context,
        )

    @extend_schema_field(serializers.ChoiceField(choices=AudereCeremony.choices, allow_null=True))
    def get_audere_state(self, obj: CombatParticipant) -> str | None:
        """Which Audere ceremony the participant's character is in, if any (#4739)."""
        character_sheet = obj.character_sheet
        if character_sheet is None:
            return None
        return _audere_state(
            character_sheet.character,
            can_view_hidden=self._can_view_vitals(obj),
            context=self.context,
        )

    def _combat_engagement(self, obj: CombatParticipant) -> CharacterEngagement | None:
        """Resolve the participant's COMBAT CharacterEngagement, if any.

        Delegates to ``world.combat.services.active_combat_engagement_for``
        (#3573), which reads the reverse OneToOne accessor
        (``character.engagement``) rather than a fresh ``.filter()`` - the
        descriptor caches the result (even the no-row case) on the
        identity-mapped ObjectDB instance, so the three escalation fields
        share at most one query per character and the warm API path pays
        zero (no prefetch machinery; the idmapper is the cache layer).

        A participant whose ``character_sheet`` descriptor raises (bare or
        partially-constructed row) resolves to None here, before delegating.
        """
        from world.combat.services import active_combat_engagement_for  # noqa: PLC0415

        try:
            character = obj.character_sheet.character
        except AttributeError:
            return None
        return active_combat_engagement_for(character)

    def get_escalation_level(self, obj: CombatParticipant) -> int | None:
        """Escalation pressure on this combatant — public dramatic state."""
        engagement = self._combat_engagement(obj)
        return engagement.escalation_level if engagement else None

    @staticmethod
    def _any_engagement(obj: CombatParticipant) -> CharacterEngagement | None:
        """The participant's engagement whatever its type (#4738).

        The Pressure figures read this: a fight that starts while she holds a challenge
        or mission engagement runs on that row, and Fury's trade lands there.
        """
        from world.combat.services import engagement_of_any_type_for  # noqa: PLC0415

        try:
            character = obj.character_sheet.character
        except AttributeError:
            return None
        return engagement_of_any_type_for(character)

    def get_intensity_modifier(self, obj: CombatParticipant) -> int | None:
        """Process-derived intensity bonus from her engagement, whatever its type."""
        engagement = self._any_engagement(obj)
        return engagement.intensity_modifier if engagement else None

    def get_control_modifier(self, obj: CombatParticipant) -> int | None:
        """Process-derived control bonus from her engagement, whatever its type."""
        engagement = self._any_engagement(obj)
        return engagement.control_modifier if engagement else None

    def get_fury_control_surrendered(self, obj: CombatParticipant) -> int | None:
        """Control surrendered to Fury in her engagement so far, whatever its type (#4738)."""
        engagement = self._any_engagement(obj)
        return engagement.fury_control_surrendered if engagement else None

    def _primary_persona(self, obj: CombatParticipant) -> Persona | None:
        """Resolve the participant's PRIMARY persona through the cached accessor.

        Reads ``CharacterSheet.cached_payload_personas`` — a ``@cached_property``
        the encounter queryset pre-fills (with ``select_related("thumbnail")``)
        so serialization issues no per-row query; PRIMARY is found explicitly
        rather than positionally. Portrait is public identity, so this is not
        gated by ``_can_view_vitals`` (mirrors the opponent portrait, #554).
        """
        try:
            character_sheet = obj.character_sheet
        except ObjectDoesNotExist:
            return None
        if character_sheet is None:
            return None
        for persona in character_sheet.cached_payload_personas:
            if persona.persona_type == PersonaType.PRIMARY:
                return persona
        return None

    def get_thumbnail_url(self, obj: CombatParticipant) -> str | None:
        """Direct portrait URL via the primary persona (mirrors OpponentSerializer).

        The persona's ``thumbnail_url`` URLField (``""`` when unset); ``None``
        when the character has no primary persona.
        """
        persona = self._primary_persona(obj)
        return None if persona is None else persona.thumbnail_url

    def get_thumbnail_media_url(self, obj: CombatParticipant) -> str | None:
        """Media portrait URL, dynamically resolved (#2196).

        Uses ``resolve_thumbnail()`` via the primary persona's character.
        ``None`` when there is no primary persona.
        """
        from world.conditions.thumbnail_services import resolve_thumbnail  # noqa: PLC0415

        persona = self._primary_persona(obj)
        if persona is None:
            return None
        try:
            character = persona.character_sheet.character
        except AttributeError:
            return None
        # #2196: use the view's per-request conditions dict to avoid N+1 when
        # serializing multiple participants; None outside the viewset.
        cached_conditions = _context_active_conditions(character, self.context)
        return resolve_thumbnail(character, persona=persona, cached_conditions=cached_conditions)

    @extend_schema_field(AftermathDigestSerializer(allow_null=True))
    def get_aftermath(self, obj: CombatParticipant) -> dict[str, Any] | None:
        """What the fight changed for this participant (#3551).

        Only on a COMPLETED encounter, only for the owner, scene GM, or staff;
        None otherwise.
        """
        encounter = obj.encounter
        if encounter.status != RoundStatus.COMPLETED or encounter.completed_at is None:
            return None
        if not self._can_view_vitals(obj):
            return None

        from world.combat.aftermath import build_aftermath_digest  # noqa: PLC0415

        digest = build_aftermath_digest(encounter, obj)

        request = self.context.get("request")
        is_gm = self.context.get("is_gm")
        if is_gm is None:
            is_gm = encounter.scene.is_gm(request.user) if encounter.scene else False
        is_gm_or_staff = is_gm or (request is not None and request.user.is_staff)
        beat = None
        if digest.beat_completion is not None and (digest.beat_visible_to_player or is_gm_or_staff):
            completion = digest.beat_completion
            beat = {
                "outcome": completion.outcome,
                "tier_name": completion.outcome_tier.name if completion.outcome_tier_id else None,
                "resolution_text": completion.beat.player_resolution_text,
            }

        consequence = None
        if digest.consequence is not None:
            consequence = ConsequenceOutcomeSerializer(
                digest.consequence, context=self.context
            ).data

        return {
            "outcome": digest.outcome,
            "consequence": consequence,
            "conditions": ConditionInstanceSerializer(
                digest.conditions, many=True, context=self.context
            ).data,
            "legend": [
                {
                    "title": entry.title,
                    "description": entry.description,
                    "base_value": entry.base_value,
                    "recognition": digest.legend_recognitions.get(entry.pk, []),
                }
                for entry in digest.legend_entries
            ],
            "beat": beat,
            "objective": digest.objective,
            "peril_round_active": digest.peril_round_active,
            "won_over": WonOverRowSerializer(digest.won_over, many=True, context=self.context).data,
        }


class RoundActionSerializer(serializers.ModelSerializer):
    """Read serializer for declared actions."""

    participant_name = serializers.CharField(
        source="participant.character_sheet.character.db_key",
        read_only=True,
    )

    class Meta:
        model = CombatRoundAction
        fields = [
            "id",
            "participant",
            "participant_name",
            "round_number",
            "focused_category",
            "effort_level",
            "focused_action",
            "focused_opponent_target",
            "focused_ally_target",
            "physical_passive",
            "social_passive",
            "mental_passive",
            "combo_upgrade",
            "is_ready",
            "maneuver",
            "cast_destination",
            "cast_position_a",
            "cast_position_b",
        ]


# ---------------------------------------------------------------------------
# Clash state serializer (for EncounterDetailSerializer.clashes)
# ---------------------------------------------------------------------------


class ClashContributorSerializer(serializers.Serializer):
    """Schema-only shape of get_contributors rows on ClashStateSerializer.

    Never instantiated for serialization — exists so drf-spectacular emits a
    concrete component instead of {[key: string]: unknown} (#2423). Mirrors
    the frontend ``ClashContributor`` interface (combat/types.ts).
    """

    character_id = serializers.IntegerField(allow_null=True)
    character_name = serializers.CharField()
    action_slot = serializers.CharField()
    progress_delta = serializers.IntegerField()
    anima = serializers.IntegerField()


class ClashStateSerializer(serializers.ModelSerializer):
    """Compact read serializer for an active Clash, surfaced on EncounterDetail.

    Exposes the fields needed by the frontend ActiveState rail section:
    - id, flavor, status, progress, pc_win_threshold, npc_win_threshold
    - npc_opponent_id (for labelling the clash target)
    - contributors: per-PC contribution rollup (latest round)
    - side_favored: "PC" / "NPC" / "EVEN" computed from progress vs thresholds.
    """

    contributors = serializers.SerializerMethodField()
    side_favored = serializers.SerializerMethodField()

    class Meta:
        model = Clash
        fields = [
            "id",
            "flavor",
            "status",
            "progress",
            "pc_win_threshold",
            "npc_win_threshold",
            "npc_opponent",
            "contributors",
            "side_favored",
        ]
        # This serializer is read-only (constructed directly for output, never bound
        # to request data — see get_clashes below), but ModelSerializer infers
        # `required=False` from the model's `default=`/`null=True` on `status`,
        # `progress`, and `npc_win_threshold`. Every response always includes them
        # (drf-spectacular otherwise marks them optional, which surfaces as `?` on
        # the generated frontend type even though the field is never actually
        # missing — #2423 follow-up, caught by dropping the `as unknown as` casts).
        extra_kwargs = {
            "status": {"required": True},
            "progress": {"required": True},
            "npc_win_threshold": {"required": True},
        }

    @extend_schema_field(ClashContributorSerializer(many=True))
    def get_contributors(self, obj: Clash) -> list[dict[str, object]]:
        """Per-PC contribution rollup across all rounds of the clash.

        Sums each contributor's progress_delta + anima_committed. Returns
        a list of dicts shaped for the frontend ActiveState card:
            {character_id, character_name, action_slot, progress_delta, anima}

        Reads through ``clash.rounds.cached_contributions`` when the
        EncounterCombatHandler prefetch is in play; falls back to a query
        otherwise.
        """
        from collections import defaultdict  # noqa: PLC0415

        totals: dict[int, dict[str, object]] = defaultdict(
            lambda: {
                "character_id": None,
                "character_name": "",
                "action_slot": "",
                "progress_delta": 0,
                "anima": 0,
            }
        )

        # Walk rounds + contributions. Use cached_rounds/cached_contributions
        # if the handler-prefetch is in scope; fall back to live query otherwise.
        if hasattr(obj, "cached_rounds"):
            rounds = obj.cached_rounds
        else:
            from world.combat.models import ClashContribution  # noqa: PLC0415

            rounds = list(
                obj.rounds.all().prefetch_related(
                    Prefetch(
                        "contributions",
                        queryset=ClashContribution.objects.select_related("character"),
                        to_attr="cached_contributions",
                    ),
                )
            )
        for clash_round in rounds:
            if hasattr(clash_round, "cached_contributions"):
                contribs = clash_round.cached_contributions
            else:
                contribs = list(clash_round.contributions.select_related("character"))
            for c in contribs:
                bucket = totals[c.character_id]
                bucket["character_id"] = c.character_id
                bucket["character_name"] = c.character.character.db_key if c.character_id else ""
                # Most-recent action_slot wins (each round may use a different slot).
                bucket["action_slot"] = c.action_slot
                bucket["progress_delta"] = int(bucket["progress_delta"]) + c.progress_delta
                bucket["anima"] = int(bucket["anima"]) + c.anima_committed
        return list(totals.values())

    # Side-favored values surfaced to the frontend.
    SIDE_FAVORED_PC = "PC"
    SIDE_FAVORED_NPC = "NPC"
    SIDE_FAVORED_EVEN = "EVEN"

    def get_side_favored(self, obj: Clash) -> str:
        """PC / NPC / EVEN — computed from current progress vs thresholds.

        Heuristic: a side is "favored" when progress is past 75% of that side's
        win threshold. Else "EVEN."
        """
        pc_threshold = obj.pc_win_threshold or 0
        npc_threshold = obj.npc_win_threshold

        if pc_threshold > 0 and obj.progress >= pc_threshold * 0.75:
            return self.SIDE_FAVORED_PC
        if npc_threshold is not None and obj.progress <= npc_threshold * 0.75:
            return self.SIDE_FAVORED_NPC
        return self.SIDE_FAVORED_EVEN


# ---------------------------------------------------------------------------
# Duel-identity nested serializer
# ---------------------------------------------------------------------------


class DuelWinnerSerializer(serializers.Serializer):
    """Lightweight identity for a duel winner (CharacterSheet id + character name).

    Exposes only what the UI needs to label the victor — the CharacterSheet PK
    and the character's display name (ObjectDB.db_key). Read-only; no FK queries
    beyond the select_related on the encounter queryset.

    Note: CharacterSheet's primary key is the ``character`` OneToOneField to
    ObjectDB, so there is no ``.id`` attribute — we read ``.pk`` explicitly via
    ``source="pk"``.
    """

    id = serializers.IntegerField(source="pk", read_only=True)
    name = serializers.SerializerMethodField()

    def get_name(self, obj: object) -> str:
        """Return the character's display name (db_key).

        ``obj`` is a CharacterSheet instance. ``character`` is a OneToOneField
        to ObjectDB (select_related by the encounter queryset); db_key is a
        plain column — no query.
        """
        # Import at runtime so spectacular can resolve the annotation
        # without a NameError (see reference-typechecking-annotation-breaks-spectacular).
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        if isinstance(obj, CharacterSheet):
            return obj.character.db_key
        return ""


# ---------------------------------------------------------------------------
# DuelChallenge serializer
# ---------------------------------------------------------------------------


class _DuelParticipantIdentitySerializer(serializers.Serializer):
    """Compact identity for one side of a DuelChallenge (CharacterSheet id + name).

    Note: CharacterSheet's primary key is the ``character`` OneToOneField, so
    there is no ``.id`` attribute — ``source="pk"`` reads ``.pk`` explicitly.
    """

    id = serializers.IntegerField(source="pk", read_only=True)
    name = serializers.SerializerMethodField()

    def get_name(self, obj: object) -> str:
        """Return the character's display name from CharacterSheet.character.db_key."""
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        if isinstance(obj, CharacterSheet):
            return obj.character.db_key
        return ""


class DuelChallengeSerializer(serializers.ModelSerializer):
    """Read serializer for the DuelChallenge pending-challenge inbox.

    Exposes challenger/challenged identities (id + name), status, timestamps,
    and the resulting_encounter FK PK. Intended for a player's incoming or
    outgoing challenge list.

    N+1-safe when the queryset uses ``select_related("challenger_sheet__character",
    "challenged_sheet__character")``.

    ``is_lethal``/``opponent_name``/``opponent_tier`` (#3068): a GM-initiated
    lethal challenge has no PC challenger — ``challenger`` renders ``null`` for
    those rows (DRF's default None-attribute handling), so the frontend reads
    ``opponent_name`` instead whenever ``is_lethal`` is true.
    """

    # allow_null=True (#3068): challenger_sheet is null for a GM-initiated lethal
    # challenge — declared so the OpenAPI schema (and generated TS type) is honest
    # about the `| null` a lethal row actually renders, not just documented in prose.
    challenger = _DuelParticipantIdentitySerializer(
        source="challenger_sheet", read_only=True, allow_null=True
    )
    challenged = _DuelParticipantIdentitySerializer(source="challenged_sheet", read_only=True)

    class Meta:
        model = DuelChallenge
        fields = [
            "id",
            "challenger",
            "challenged",
            "status",
            "is_lethal",
            "opponent_name",
            "opponent_tier",
            "created_at",
            "resolved_at",
            "resulting_encounter",
        ]
        read_only_fields = fields


class ThreatPoolSerializer(serializers.ModelSerializer):
    """Read serializer for the ThreatPool catalog (#3067).

    ThreatPool is authored content (a named NPC move-set — e.g. "Goblin
    Raiders"), never a per-encounter/per-scene row, so this is a flat
    id/name/description listing for the GM's add-opponent picker — no
    encounter-scoped fields to compute.
    """

    class Meta:
        model = ThreatPool
        fields = ["id", "name", "description"]
        read_only_fields = fields


class CreatureTemplateSerializer(serializers.ModelSerializer):
    """Read-only bestiary catalog listing for the GM spawn-from-template picker (#3424).

    Deliberately thin — no phase/break-bar internals (leak table in the #3424
    spec: a player reading this payload would learn boss-phase mechanics and
    weakness windows ahead of Consider/weakness-research discovery). ``has_phases``
    only signals presence, never the phase count or triggers.
    """

    has_phases = serializers.SerializerMethodField()
    threat_pool_name = serializers.SerializerMethodField()

    class Meta:
        model = CreatureTemplate
        fields = ["id", "name", "tier", "description", "has_phases", "threat_pool_name"]
        read_only_fields = fields

    def get_has_phases(self, obj: CreatureTemplate) -> bool:
        # The ViewSet's Prefetch(to_attr="cached_phase_templates") fills this for
        # a whole page of rows, so there is no .exists() per row.
        return len(obj.cached_phase_templates) > 0

    def get_threat_pool_name(self, obj: CreatureTemplate) -> str | None:
        return obj.threat_pool.name if obj.threat_pool_id else None


class EscalationCurveSerializer(serializers.ModelSerializer):
    """Read-only escalation curve catalog row for the GM settings picker (#3552).

    GM-gated at the viewset (curve names and descriptions are authored
    encounter design, the same reasoning as the bestiary catalog, #3424).
    """

    class Meta:
        model = EscalationCurve
        fields = ["id", "name", "description", "start_round"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# List and detail serializers
# ---------------------------------------------------------------------------


class EncounterListSerializer(serializers.ModelSerializer):
    """Lightweight listing serializer for combat encounters."""

    participant_count = serializers.SerializerMethodField()
    opponent_count = serializers.SerializerMethodField()
    # Declared explicitly so the generated OpenAPI type admits the pre-completion
    # blank value the API serves until the encounter completes (#959).
    outcome = serializers.ChoiceField(
        choices=EncounterOutcome.choices, allow_blank=True, read_only=True
    )

    class Meta:
        model = CombatEncounter
        fields = [
            "id",
            "scene",
            "encounter_type",
            "status",
            "outcome",
            "completed_at",
            "round_number",
            "pace_mode",
            "pace_timer_minutes",
            "is_paused",
            "participant_count",
            "opponent_count",
        ]
        extra_kwargs = {
            "completed_at": {"read_only": True},
        }

    def get_participant_count(self, obj: CombatEncounter) -> int:
        """Return participant count, from the cached payload list."""
        return len(obj.participants_cached)

    def get_opponent_count(self, obj: CombatEncounter) -> int:
        """Return opponent count, from the cached payload list."""
        return len(obj.opponents_cached)


class VolatileObjectSerializer(serializers.Serializer):
    """A detonatable object in the encounter room, for the redirect destination picker (#2210)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    position_id = serializers.IntegerField(read_only=True, allow_null=True)
    position_name = serializers.CharField(read_only=True, allow_null=True)


class CombatMarkSerializer(serializers.Serializer):
    """Schema-only shape of get_marks rows on EncounterDetailSerializer (#4603).

    Never instantiated for serialization - exists so drf-spectacular emits a
    concrete component instead of {[key: string]: unknown}, mirroring
    EngagementLockSerializer below. Field shape matches the dict ``get_marks``
    builds verbatim.
    """

    id = serializers.IntegerField()
    participant_id = serializers.IntegerField()
    opponent_id = serializers.IntegerField()
    round_number = serializers.IntegerField()


class EngagementLockSerializer(serializers.Serializer):
    """Schema-only shape of get_engagement_locks rows on EncounterDetailSerializer (#3386).

    Never instantiated for serialization — exists so drf-spectacular emits a
    concrete component instead of {[key: string]: unknown}, mirroring
    ClashContributorSerializer above. Field shape matches the dict
    ``get_engagement_locks`` builds verbatim.
    """

    id = serializers.IntegerField()
    opponent_id = serializers.IntegerField()
    participant_id = serializers.IntegerField()
    status = serializers.CharField()
    initiated_by = serializers.CharField()
    started_round = serializers.IntegerField()


class PendingAttackSerializer(serializers.Serializer):
    """Schema-only shape of get_pending_attacks rows on EncounterDetailSerializer (#3572).

    Never instantiated for serialization (same idiom as EngagementLockSerializer):
    exists so drf-spectacular emits a concrete component. Threat-entry internals
    (damage, defense check, cooldown) are deliberately absent; the row carries only
    what the telegraph already announced plus the downgrade state.
    """

    id = serializers.IntegerField()
    opponent_id = serializers.IntegerField()
    opponent_name = serializers.CharField()
    target_participant_id = serializers.IntegerField(allow_null=True)
    target_name = serializers.CharField(allow_null=True)
    declared_round = serializers.IntegerField()
    resolves_round = serializers.IntegerField()
    rounds_until_landing = serializers.IntegerField()
    downgrades = serializers.IntegerField()
    called_out = serializers.BooleanField()
    damage_scale = serializers.FloatField()
    cancelled = serializers.BooleanField()
    attack_name = serializers.CharField()
    covered_position_id = serializers.IntegerField(allow_null=True)
    covered_position_name = serializers.CharField(allow_null=True)


class PendingSelectionOptionSerializer(serializers.Serializer):
    """A safe, authored choice shown only to its owning participant."""

    id = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class PendingSelectionSerializer(serializers.Serializer):
    """Read shape for a deferred specialist choice (#3915)."""

    id = serializers.IntegerField()
    participant_id = serializers.IntegerField()
    selection_type = serializers.CharField()
    options = PendingSelectionOptionSerializer(many=True, source="options_json")
    selected_option_id = serializers.CharField(allow_null=True)
    target_opponent_id = serializers.IntegerField(allow_null=True)
    target_opponent_name = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    resolved = serializers.BooleanField(source="is_resolved")


class SustainedActionSerializer(serializers.Serializer):
    """Observable countdown and erosion for a multi-round commitment."""

    id = serializers.IntegerField()
    participant_id = serializers.IntegerField()
    participant_name = serializers.CharField()
    kind = serializers.CharField(source="sustained_kind")
    subject = serializers.CharField(source="subject_name")
    declared_round = serializers.IntegerField()
    resolves_round = serializers.IntegerField()
    rounds_until_resolution = serializers.IntegerField()
    downgrades = serializers.IntegerField()
    broken = serializers.BooleanField()


class ProtectionCommitmentSerializer(serializers.Serializer):
    """Public ally-protection declaration, without private action details."""

    participant_id = serializers.IntegerField()
    participant_name = serializers.CharField()
    maneuver = serializers.CharField()
    protected_participant_id = serializers.IntegerField(allow_null=True)
    protected_participant_name = serializers.CharField(allow_null=True)


class CompanionOrderSummarySerializer(serializers.Serializer):
    """Current-round companion directive exposed on an encounter read."""

    companion_id = serializers.IntegerField()
    companion_name = serializers.CharField()
    order_kind = serializers.CharField()
    target_opponent_id = serializers.IntegerField(allow_null=True)
    defending_participant_id = serializers.IntegerField(allow_null=True)


class SurgeBeatSerializer(serializers.Serializer):
    """Shape of one dramatic-surge beat in a round payload (#2013, #4737); read-only.

    Everyone gets ``id`` and ``narration``. The rest appear only for the surged
    participant's owner, GMs and staff, and the roll fields only for a rolled surge.
    """

    id = serializers.IntegerField()
    narration = serializers.CharField()
    trigger_kind = serializers.CharField(required=False)
    amount = serializers.IntegerField(required=False)
    participant = serializers.IntegerField(required=False)
    outcome = serializers.CharField(required=False, help_text="Name of the roll's outcome.")
    potency = serializers.IntegerField(
        required=False, allow_null=True, help_text="What the roll was made against, if anything."
    )
    control_change = serializers.IntegerField(required=False)
    condition = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Name of the condition the surge actually applied.",
    )
    roll = serializers.CharField(
        required=False,
        help_text="The roll caption the surged player was shown, e.g. "
        "'Composure check vs taunt potency 14 · Partial · Intensity +5'.",
    )
    cause = serializers.CharField(
        required=False,
        help_text="What caused the surge, e.g. 'Mira taunts Tomas.'. Only the surged player, "
        "GMs and staff get it; everyone else reads the generic narration.",
    )


def _surge_roll_fields(records: Sequence[DramaticSurgeRecord]) -> dict[int, dict[str, Any]]:
    """The roll fields of each rolled surge record, keyed by record pk (#4737).

    A record with no ``outcome`` (a kind that is not rolled) has no entry. The outcome,
    potency, control change, amount and the condition the surge applied all come from the
    record, so a later retune of the band changes none of them. The ``roll`` line is the
    shared ``roll_line`` over those and the check type name of the surge tuning authored for
    the record's kind; with that tuning gone there is no ``roll``. One query however many
    records, none when no record is rolled.
    """
    from world.combat.surge_rolls import roll_line  # noqa: PLC0415

    rolled = [record for record in records if record.outcome is not None]
    if not rolled:
        return {}
    tunings = {
        tuning.trigger_kind: tuning
        for tuning in SurgeTuning.objects.select_related("check_type").filter(
            trigger_kind__in={record.trigger_kind for record in rolled}
        )
    }
    fields: dict[int, dict[str, Any]] = {}
    for record in rolled:
        outcome = record.outcome
        condition_name = record.condition.name if record.condition is not None else None
        entry: dict[str, Any] = {
            "outcome": outcome.name,
            "potency": record.potency,
            "control_change": record.control_change,
            "condition": condition_name,
        }
        tuning = tunings.get(record.trigger_kind)
        if tuning is not None:
            entry["roll"] = roll_line(
                check_type=tuning.check_type,
                trigger_kind=record.trigger_kind,
                potency=record.potency,
                outcome=outcome,
                amount=record.amount,
                control_change=record.control_change,
                condition_name=condition_name or "",
                vow_scaling=record.vow_scaling,
            )
        fields[record.pk] = entry
    return fields


class EncounterDetailSerializer(serializers.ModelSerializer):
    """Full encounter state with covenant-filtered action visibility."""

    participants = ParticipantSerializer(
        many=True,
        read_only=True,
        source="participants_cached",
    )
    opponents = OpponentSerializer(
        many=True,
        read_only=True,
        source="opponents_cached",
    )
    current_round_actions = serializers.SerializerMethodField()
    surge_beats = serializers.SerializerMethodField()
    is_participant = serializers.SerializerMethodField()
    is_gm = serializers.SerializerMethodField()
    clashes = serializers.SerializerMethodField()
    engagement_locks = serializers.SerializerMethodField()
    marks = serializers.SerializerMethodField()
    pending_attacks = serializers.SerializerMethodField()
    companion_orders = serializers.SerializerMethodField()
    resolution_order = serializers.SerializerMethodField()
    position_adjacency = serializers.SerializerMethodField()
    position_nodes = serializers.SerializerMethodField()
    position_edges = serializers.SerializerMethodField()
    held_positions = serializers.SerializerMethodField()
    volatile_objects = serializers.SerializerMethodField()
    objective = serializers.SerializerMethodField(required=False)
    pending_selections = serializers.SerializerMethodField(required=False)
    sustained_actions = serializers.SerializerMethodField(required=False)
    protection_commitments = serializers.SerializerMethodField(required=False)
    standoff = serializers.SerializerMethodField()
    gm_standoff = serializers.SerializerMethodField()
    standoff_summary = serializers.SerializerMethodField()
    escalation_curve = serializers.PrimaryKeyRelatedField(
        queryset=EscalationCurve.objects.all(),
        required=False,
        allow_null=True,
    )
    # null = encounter has no curve; tick_narration "" = curve set, no narration authored.
    escalation_curve_name = serializers.CharField(
        source="escalation_curve.name", read_only=True, default=None, allow_null=True
    )
    escalation_start_round = serializers.IntegerField(
        source="escalation_curve.start_round", read_only=True, default=None, allow_null=True
    )
    escalation_tick_narration = serializers.CharField(
        source="escalation_curve.tick_narration", read_only=True, default=None, allow_null=True
    )
    forced_escape = serializers.BooleanField(read_only=True)
    # Declared explicitly so the generated OpenAPI type admits the pre-completion
    # blank value the API serves until the encounter completes (#959).
    outcome = serializers.ChoiceField(
        choices=EncounterOutcome.choices, allow_blank=True, read_only=True
    )
    # Duel fields — derived / FK; no additional queries when the viewset queryset
    # uses select_related("duel_winner__character").
    is_lethal = serializers.BooleanField(read_only=True)
    duel_winner = DuelWinnerSerializer(read_only=True, allow_null=True)

    class Meta:
        model = CombatEncounter
        fields = [
            "id",
            "scene",
            "room",
            "encounter_type",
            "status",
            "outcome",
            "completed_at",
            "round_number",
            "risk_level",
            "stakes_level",
            "pace_mode",
            "pace_timer_minutes",
            "is_paused",
            "round_started_at",
            "created_at",
            "participants",
            "opponents",
            "current_round_actions",
            "surge_beats",
            "is_participant",
            "is_gm",
            "clashes",
            "engagement_locks",
            "marks",
            "pending_attacks",
            "companion_orders",
            "resolution_order",
            "escalation_curve",
            "escalation_curve_name",
            "escalation_start_round",
            "escalation_tick_narration",
            "forced_escape",
            "position_adjacency",
            "position_nodes",
            "position_edges",
            "held_positions",
            "volatile_objects",
            "objective",
            "pending_selections",
            "sustained_actions",
            "protection_commitments",
            "standoff",
            "gm_standoff",
            "standoff_summary",
            "is_lethal",
            "duel_winner",
        ]
        extra_kwargs = {
            "completed_at": {"read_only": True},
        }

    def to_representation(self, instance: CombatEncounter) -> dict[str, Any]:
        """Inject is_gm into context before nested serializers run.

        NOTE: This serializer must NOT be used with many=True — the is_gm
        value would leak across encounters. Use EncounterListSerializer
        for list views.
        """
        self.context["is_gm"] = self._compute_is_gm(instance)
        return super().to_representation(instance)

    def get_is_participant(self, obj: CombatEncounter) -> bool:
        """Check whether the requesting user has a character in this encounter."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        character_ids = self._get_viewer_character_ids(request)
        return any(p.character_sheet.character_id in character_ids for p in obj.participants_cached)

    @extend_schema_field(StandoffViewSerializer(allow_null=True))
    def get_standoff(self, obj: CombatEncounter) -> dict[str, Any] | None:
        """The standoff as the viewer's own participant sees it; None for anyone else.

        Built per viewer (angles, faction rule detail and unread things are private), so a
        viewer who is not a participant, or an encounter past its standoff, gets None.
        A user playing two characters in the encounter gets the first one's view.
        """
        # Round 0 is the only standoff window; a fight in progress costs no query.
        # build_standoff_view does the authoritative is_in_standoff check.
        if obj.round_number != 0:
            return None
        viewer_ids = self.context.get("viewer_character_ids", set())
        for participant in obj.participants_cached:
            if participant.character_sheet.character_id in viewer_ids:
                view = build_standoff_view(obj, participant.character_sheet)
                return None if view is None else StandoffViewSerializer(view).data
        return None

    @extend_schema_field(GMStandoffViewSerializer(allow_null=True))
    def get_gm_standoff(self, obj: CombatEncounter) -> dict[str, Any] | None:
        """The whole standoff for the scene's GMs and staff; None for anyone else (#4354).

        Carries every group's cause, drives, faction rules and matches, so it must never
        reach a player or an onlooker.
        """
        if obj.round_number != 0:
            return None
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        if not (self.context.get("is_gm", False) or request.user.is_staff):
            return None
        view = build_gm_standoff_view(obj)
        return None if view is None else GMStandoffViewSerializer(view).data

    @extend_schema_field(StandoffSummarySerializer(allow_null=True))
    def get_standoff_summary(self, obj: CombatEncounter) -> dict[str, Any] | None:
        """Public facts about the standoff for an onlooker (#4354).

        A participant gets their own ``standoff`` view and a GM gets ``gm_standoff``, so
        this is built only for a viewer who has neither.
        """
        if obj.round_number != 0 or self.context.get("is_gm", False):
            return None
        viewer_ids = self.context.get("viewer_character_ids", set())
        if any(
            participant.character_sheet.character_id in viewer_ids
            for participant in obj.participants_cached
        ):
            return None
        summary = build_standoff_summary(obj)
        return None if summary is None else StandoffSummarySerializer(summary).data

    @extend_schema_field(PendingSelectionSerializer(many=True))
    def get_pending_selections(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Expose specialist choices only to their owner or a GM."""
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return []
        viewer_ids = self.context.get("viewer_character_ids", set())
        is_gm = bool(self.context.get("is_gm", False) or request.user.is_staff)
        rows = (
            PendingSelection.objects.filter(encounter=obj)
            .select_related("participant__character_sheet__character", "target_opponent")
            .order_by("created_at", "pk")
        )
        if not is_gm:
            rows = rows.filter(participant__character_sheet__character_id__in=viewer_ids)
        return PendingSelectionSerializer(rows, many=True).data  # type: ignore[return-value]

    @extend_schema_field(SustainedActionSerializer(many=True))
    def get_sustained_actions(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return public countdown/erosion state, never the private budget."""
        rows = SustainedAction.objects.filter(encounter=obj).select_related(
            "participant__character_sheet__character"
        )
        return [
            {
                "id": row.pk,
                "participant_id": row.participant_id,
                "participant_name": str(row.participant.character_sheet.character),
                "kind": row.sustained_kind,
                "subject": row.subject_name,
                "declared_round": row.declared_round,
                "resolves_round": row.resolves_round,
                "rounds_until_resolution": max(row.resolves_round - obj.round_number, 0),
                "downgrades": row.downgrades,
                "broken": row.downgrades >= row.absorption_budget,
            }
            for row in rows
        ]

    @extend_schema_field(ProtectionCommitmentSerializer(many=True))
    def get_protection_commitments(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Expose current-round cover/interpose intent for ally coordination."""
        rows = CombatRoundAction.objects.filter(
            participant__encounter=obj,
            round_number=obj.round_number,
            maneuver__in=["cover", "interpose"],
        ).select_related(
            "participant__character_sheet__character",
            "focused_ally_target__character_sheet__character",
        )
        return [
            {
                "participant_id": row.participant_id,
                "participant_name": str(row.participant.character_sheet.character),
                "maneuver": row.maneuver,
                "protected_participant_id": row.focused_ally_target_id,
                "protected_participant_name": (
                    str(row.focused_ally_target.character_sheet.character)
                    if row.focused_ally_target_id
                    else None
                ),
            }
            for row in rows
        ]

    @extend_schema_field(ObjectiveSnapshotSerializer(allow_null=True))
    def get_objective(self, obj: CombatEncounter) -> dict[str, Any] | None:
        """Expose the active authored objective and selected branch (#3916)."""
        from world.combat.objective_branches import objective_snapshot  # noqa: PLC0415

        return objective_snapshot(obj)

    def get_resolution_order(self, obj: CombatEncounter) -> list[int]:
        """ACTIVE PC participant PKs in initiative (speed-rank) order.

        Computed from ``participants_cached`` (which already select_relateds
        ``covenant_role`` and the character) through the same ``effective_speed_ranks``
        that ``services.get_resolution_order`` sorts on, so the chips and the real
        order agree for ACTIVE PCs (effective rank asc, then pk). Costs one query for
        the turn order conditions. The frontend RoundFlow orders its initiative chips
        by this and marks the first not-yet-acted participant as the on-deck actor.

        The resolution path additionally applies a ``can_act`` filter (excluding a
        downed-but-not-removed PC); that is omitted here to keep the query count down,
        so such a PC may still appear in the display order. Acceptable for a display field.
        """
        from world.combat.services.combos.resolution_order import (  # noqa: PLC0415
            effective_speed_ranks,
        )

        active = [p for p in obj.participants_cached if p.status == ParticipantStatus.ACTIVE]
        ranks = effective_speed_ranks(active)
        active.sort(key=lambda p: (ranks[(ENTITY_TYPE_PC, p.pk)], p.pk))
        return [p.pk for p in active]

    def _get_viewer_character_ids(self, request: object) -> set[int] | frozenset[int]:
        """Get character_sheet IDs for the requesting user.

        Resolution order:
        1. Serializer context (populated by ``_build_serializer_context``)
        2. ``request.user.played_character_sheet_ids`` (cached on the
           Account typeclass; invalidated by RosterTenure mutations)
        Caches into context after fetching so subsequent fields in the
        same serializer pass don't re-read.
        """
        cached = self.context.get("viewer_character_ids")
        if cached is not None:
            return cached
        try:
            character_ids = request.user.played_character_sheet_ids  # type: ignore[union-attr]
        except AttributeError:
            character_ids = frozenset()
        self.context["viewer_character_ids"] = character_ids
        return character_ids

    def get_is_gm(self, obj: CombatEncounter) -> bool:
        """Check whether the requesting user is GM of the linked scene."""
        cached = self.context.get("is_gm")
        if cached is not None:
            return cached
        return self._compute_is_gm(obj)

    def _compute_is_gm(self, obj: CombatEncounter) -> bool:
        """Compute GM status for the requesting user.

        Uses the select_related scene and Scene.is_gm() which reads
        from participations_cached — no extra queries.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.scene.is_gm(request.user)

    def get_current_round_actions(
        self,
        obj: CombatEncounter,
    ) -> list[dict[str, Any]]:
        """Return actions visible to the requesting user.

        Covenant-scoped: participants see own covenant's actions.
        GMs and staff see all.
        """
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return []

        actions = CombatRoundAction.objects.filter(
            participant__encounter=obj,
            round_number=obj.round_number,
        ).select_related(
            "participant__character_sheet__character",
        )

        # Staff and GMs see all actions
        if request.user.is_staff or self.context.get("is_gm", False):
            return RoundActionSerializer(actions, many=True).data  # type: ignore[return-value]

        # Participants see their covenant's actions.
        # For now (covenants not fully built), show own actions only.
        character_ids = self.context.get("viewer_character_ids", set())
        own_actions = actions.filter(
            participant__character_sheet__character_id__in=character_ids,
        )
        return RoundActionSerializer(own_actions, many=True).data  # type: ignore[return-value]

    @extend_schema_field(SurgeBeatSerializer(many=True))
    def get_surge_beats(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return this round's dramatic-surge beats (#2013).

        Every viewer sees the generic ``narration`` line (never names the
        bond/track/subject — the leak rule). ``trigger_kind``/``amount`` and, when the
        surge stored one, the ``cause`` line (who taunted or rallied, or the wound) are
        added only for the surging participant's own owner, GMs, and staff —
        mirrors ``get_current_round_actions``'s covenant-scoped pattern. A rolled surge
        (#4737) adds the same way ``outcome``, ``potency``, ``control_change``,
        ``condition`` and the ready-made ``roll`` line; a beat of a kind that is not rolled
        carries none of them. A surge that was never announced to the room (it added no
        intensity) has an empty ``narration`` and is left out for everyone but those same
        viewers, and so is an emotional condition's feed (``CONDITION_FED``, #4739), which
        is never announced to the room.
        """
        request = self.context.get("request")
        records = list(
            DramaticSurgeRecord.objects.filter(
                encounter=obj,
                round_number=obj.round_number,
            ).select_related(
                "participant__character_sheet__character",
                "encounter__escalation_curve",
                "outcome",
                "condition",
            )
        )

        is_gm_or_staff = self.context.get("is_gm", False) or (
            request is not None and request.user.is_staff
        )
        viewer_character_ids = self.context.get("viewer_character_ids", set())

        rolls = _surge_roll_fields(records)
        beats: list[dict[str, Any]] = []
        for record in records:
            beat: dict[str, Any] = {
                "id": record.pk,
                "narration": self._render_surge_beat_narration(record),
            }
            character_id = record.participant.character_sheet.character_id
            sees_detail = is_gm_or_staff or character_id in viewer_character_ids
            if not sees_detail and (
                not beat["narration"] or record.trigger_kind == SurgeTriggerKind.CONDITION_FED
            ):
                # Nothing was announced to the room (a control-only or condition-only
                # surge, or an emotional condition's feed, #4739, which is never
                # announced), so a bystander has no beat to show.
                continue
            if sees_detail:
                beat["trigger_kind"] = record.trigger_kind
                beat["amount"] = record.amount
                beat["participant"] = record.participant_id
                beat.update(rolls.get(record.pk, {}))
                if record.cause:
                    beat["cause"] = record.cause
            beats.append(beat)
        return beats

    @staticmethod
    def _render_surge_beat_narration(record: DramaticSurgeRecord) -> str:
        """Re-render the generic narration line from the curve template.

        The record itself stores only trigger_kind/amount/subject (audit
        data) — narration is derived at read time from the encounter's
        current curve, same as the live broadcast at write time. A record that
        added no intensity (a control-only or condition-only surge) was never
        announced, so it renders nothing.
        """
        from world.combat.escalation import _render_surge_narration  # noqa: PLC0415

        curve = record.encounter.escalation_curve
        character_name = record.participant.character_sheet.character.db_key
        if curve is None or record.amount == 0:
            return ""
        return _render_surge_narration(curve, character_name)

    @extend_schema_field(ClashStateSerializer(many=True))
    def get_clashes(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return active Clash records for this encounter.

        Phase 8, Task 8.4 — exposes clash state to the frontend ActiveState
        rail section. Returns only ACTIVE clashes so resolved ones don't litter
        the UI after the clash is done.

        Reads ``CombatEncounter.clashes_cached``, which the viewset's
        ``_base_queryset`` pre-fills so no extra query fires here.
        """
        return ClashStateSerializer(obj.clashes_cached, many=True).data  # type: ignore[return-value]

    @extend_schema_field(EngagementLockSerializer(many=True))
    def get_engagement_locks(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return active EngagementLock records for this encounter (#2020).

        Exposes foil pairings (who is dueling whom) to the frontend combat UI.
        Returns only ACTIVE locks so resolved ones don't appear after breaking.

        Reads ``CombatEncounter.engagement_locks_cached``, which the viewset's
        ``_base_queryset`` pre-fills so no extra query fires here.
        """
        return [
            {
                "id": lock.pk,
                "opponent_id": lock.opponent_id,
                "participant_id": lock.participant_id,
                "status": lock.status,
                "initiated_by": lock.initiated_by,
                "started_round": lock.started_round,
            }
            for lock in obj.engagement_locks_cached
        ]

    @extend_schema_field(CombatMarkSerializer(many=True))
    def get_marks(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return this round's marks (#4603): who marked which foe.

        Marks are public to every reader of the encounter (participants, the GM,
        staff). One flat query, scoped to the current round so an earlier round's
        mark never shows.
        """
        from world.combat.models import CombatMark  # noqa: PLC0415

        marks = CombatMark.objects.filter(encounter=obj, round_number=obj.round_number).order_by(
            "pk"
        )
        return [
            {
                "id": mark.pk,
                "participant_id": mark.participant_id,
                "opponent_id": mark.opponent_id,
                "round_number": mark.round_number,
            }
            for mark in marks
        ]

    @extend_schema_field(PendingAttackSerializer(many=True))
    def get_pending_attacks(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Pending wind-ups on this encounter, soonest-landing first (#3572).

        Rows are deleted on maturation, so presence means pending. One query.
        """
        from world.combat.constants import WINDUP_FIZZLE_DOWNGRADES  # noqa: PLC0415
        from world.combat.models import PendingOpponentAttack  # noqa: PLC0415
        from world.combat.services import windup_damage_scale  # noqa: PLC0415

        rows = (
            PendingOpponentAttack.objects.filter(encounter=obj)
            .select_related(
                "opponent",
                "threat_entry",
                "covered_position",
                "target__character_sheet__character",
            )
            .order_by("resolves_round", "id")
        )
        return [
            {
                "id": row.pk,
                "opponent_id": row.opponent_id,
                "opponent_name": row.opponent.name,
                "target_participant_id": row.target_id,
                "target_name": (
                    str(row.target.character_sheet.character) if row.target_id else None
                ),
                "declared_round": row.declared_round,
                "resolves_round": row.resolves_round,
                "rounds_until_landing": max(row.resolves_round - obj.round_number, 0),
                "downgrades": row.downgrades,
                "called_out": row.called_out,
                "damage_scale": windup_damage_scale(row.downgrades),
                "cancelled": row.downgrades >= WINDUP_FIZZLE_DOWNGRADES,
                # A place-covering wind-up (#4676): the place it lands on.
                "attack_name": row.threat_entry.name,
                "covered_position_id": row.covered_position_id,
                "covered_position_name": (
                    row.covered_position.name if row.covered_position_id else None
                ),
            }
            for row in rows
        ]

    @extend_schema_field(CompanionOrderSummarySerializer(many=True))
    def get_companion_orders(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return current-round companion directives for the encounter."""
        return [
            {
                "companion_id": order.companion_id,
                "companion_name": order.companion.name,
                "order_kind": order.order_kind,
                "target_opponent_id": order.target_opponent_id,
                "defending_participant_id": order.defending_participant_id,
            }
            for order in obj.companion_orders_cached
        ]

    @extend_schema_field(PositionAdjacencyItemSerializer(many=True))
    def get_position_adjacency(self, obj: CombatEncounter) -> list[dict[str, object]]:
        """Return ADJACENT-reach position adjacency for the encounter's room.

        Each entry is ``{position_id: int, adjacent_position_ids: [int]}``.
        Returns an empty list when the encounter has no room.

        Uses ``room_position_adjacency`` from the positioning services, which
        reads from ``room.positions_cached`` / per-position
        ``passable_edges_as_a`` / ``passable_edges_as_b`` attrs when they
        were prefetched by the viewset's ``_base_queryset`` — zero extra
        queries on the warm path.
        """
        if obj.room_id is None:
            return []
        from world.areas.positioning.services import room_position_adjacency  # noqa: PLC0415

        entries = room_position_adjacency(obj.room)
        return PositionAdjacencyItemSerializer(entries, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PositionNodeSerializer(many=True))
    def get_position_nodes(self, obj: CombatEncounter) -> list[dict[str, object]]:
        """Return the full position-node list for the encounter's room (#2006).

        Unlike ``positions`` (id+name only), carries kind/elevation/layout for
        spatial rendering. Empty list when the encounter has no room.
        """
        if obj.room_id is None:
            return []
        from world.areas.positioning.services import position_graph  # noqa: PLC0415

        graph = position_graph(obj.room)
        return PositionNodeSerializer(graph.nodes, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PositionEdgeSerializer(many=True))
    def get_position_edges(self, obj: CombatEncounter) -> list[dict[str, object]]:
        """Return every edge (obstacle/gate visibility) for the encounter's room (#2006).

        Unlike ``position_adjacency`` (the reach graph — passable edges only,
        gating ignored), carries is_passable/blocks_flight/gating_challenge_name
        for every edge. Empty list when the encounter has no room.
        """
        if obj.room_id is None:
            return []
        from world.areas.positioning.services import position_graph  # noqa: PLC0415

        graph = position_graph(obj.room)
        return PositionEdgeSerializer(graph.edges, many=True).data  # type: ignore[return-value]

    @extend_schema_field(HeldPositionSerializer(many=True))
    def get_held_positions(self, obj: CombatEncounter) -> list[dict[str, object]]:
        """Places a ready enemy holds and who holds them (#4670); the same for every viewer."""
        from world.combat.services.held_ground import enemy_held_places  # noqa: PLC0415

        held = enemy_held_places(obj)
        return [
            {"position_id": position_id, "holder_names": names}
            for position_id, names in sorted(held.items())
        ]

    @extend_schema_field(VolatileObjectSerializer(many=True))
    def get_volatile_objects(self, obj: CombatEncounter) -> list[dict[str, object]]:
        """Return every volatile (detonatable) object in the encounter room (#2210).

        Objects carrying an ``ObjectProperty`` whose ``Property`` has a
        ``PropertyDetonation`` row — the redirect destination picker's data
        source. One query with ``select_related`` across the OneToOne position
        link; empty list when the encounter has no room.
        """
        if obj.room_id is None:
            return []
        from world.mechanics.models import ObjectProperty  # noqa: PLC0415

        rows = ObjectProperty.objects.filter(
            object__db_location_id=obj.room_id,
            property__detonation__isnull=False,
        ).select_related("object", "object__object_position__position")
        entries = []
        for row in rows:
            try:
                position = row.object.object_position.position
            except ObjectDoesNotExist:
                position = None
            entries.append(
                {
                    "id": row.object_id,
                    "name": row.object.db_key,
                    "position_id": position.pk if position is not None else None,
                    "position_name": position.name if position is not None else None,
                }
            )
        return VolatileObjectSerializer(entries, many=True).data  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Write serializers
# ---------------------------------------------------------------------------


class RemoveParticipantSerializer(serializers.Serializer):
    """Write serializer for removing a participant from an encounter."""

    participant_id = serializers.IntegerField()


class RemoveOpponentSerializer(serializers.Serializer):
    """Write serializer for removing an NPC opponent from an encounter (#3382)."""

    opponent_id = serializers.IntegerField()


class ComboSlotFillSerializer(serializers.Serializer):
    """One slot of a combo taking shape this round (#3553): the ask, and who fills it.

    Reads a ``ComboSlotFill``. The filler fields are null while the slot is open.
    """

    slot_number = serializers.IntegerField(source="slot.slot_number")
    effect_type = serializers.CharField(source="slot.required_action_type.name")
    resonance = serializers.SerializerMethodField()
    archetype = serializers.CharField(source="slot.required_archetype")
    participant_id = serializers.IntegerField(allow_null=True)
    character_name = serializers.CharField(allow_null=True)
    technique_name = serializers.CharField(allow_null=True)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_resonance(self, fill: ComboSlotFill) -> str | None:
        if fill.slot.resonance_requirement_id is None:
            return None
        return fill.slot.resonance_requirement.name


class RoundComboSerializer(serializers.Serializer):
    """A combo taking shape this round, with its slot composition and rider (#3553).

    Reads a ``RoundCombo``. ``complete`` is the upgrade condition; a partial
    fill is listed so the party can see what would complete it.
    """

    combo_id = serializers.IntegerField(source="combo.pk")
    combo_name = serializers.CharField(source="combo.name")
    known_by_participant = serializers.BooleanField()
    slot_count = serializers.IntegerField()
    filled_count = serializers.IntegerField()
    complete = serializers.BooleanField()
    bonus_damage = serializers.IntegerField(source="combo.bonus_damage")
    bypass_soak = serializers.BooleanField(source="combo.bypass_soak")
    slots = ComboSlotFillSerializer(source="slot_fills", many=True)


class UpgradeComboSerializer(serializers.Serializer):
    """Write serializer for upgrading an action to a combo."""

    combo_id = serializers.IntegerField()


class AddParticipantSerializer(serializers.Serializer):
    """Write serializer for adding a participant to an encounter."""

    character_sheet_id = serializers.IntegerField()
    covenant_role_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )


class ProposeLethalDuelSerializer(serializers.Serializer):
    """Write serializer for a GM proposing a lethal duel (#3068).

    ``scene`` is read by ``IsEncounterGMOrStaff.has_permission`` (the same
    field name the ``CombatEncounter`` create gate reads) to authorize the
    GM; the view resolves the room from the scene's location. ``tier`` is
    restricted to the significant-NPC tiers ``create_lethal_duel_challenge``
    accepts — validated here so a bad tier 400s with a clean message instead
    of surfacing a raw exception.
    """

    scene = serializers.IntegerField(min_value=1)
    challenged_sheet_id = serializers.IntegerField(min_value=1)
    opponent_name = serializers.CharField(max_length=200)
    tier = serializers.ChoiceField(choices=[(t, t) for t in SIGNIFICANT_NPC_TIERS])
    threat_pool_id = serializers.IntegerField(min_value=1)


class JoinEncounterSerializer(serializers.Serializer):
    """Write serializer for a player self-joining an encounter.

    Requires explicit ``character_sheet_id`` — never auto-selects which
    of the user's characters joins. The view validates that the chosen
    sheet belongs to one of the user's active tenures.
    """

    character_sheet_id = serializers.IntegerField(min_value=1)


class CoverSerializer(serializers.Serializer):
    """Write serializer for declaring a covering maneuver.

    Requires ``ally_participant_id`` — the PK of the ``CombatParticipant``
    this character intends to cover. Ownership and encounter-membership
    validation happens in the view (``get_object_or_404``) and service
    (``declare_cover``).
    """

    ally_participant_id = serializers.IntegerField(min_value=1)


class InterposeSerializer(serializers.Serializer):
    """Write serializer for declaring an interposing maneuver.

    ``ally_participant_id`` is optional: omitting it (or passing ``null``)
    means the participant will guard any ally hit this round. When provided,
    ownership and encounter-membership validation happens in the service
    (``declare_interpose``).
    """

    ally_participant_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class UseItemSerializer(serializers.Serializer):
    """Write serializer for declaring a USE_ITEM maneuver (#2023, #2120).

    ``item_instance_id`` is the PK of the held ``ItemInstance`` to use — a
    primary maneuver, unlike the passives-only cover/interpose declarations
    above. At most one of ``target_participant_id`` (an ally) /
    ``target_opponent_id`` (an NPC opponent) may be supplied; possession and
    encounter-membership validation happens in the view (``get_object_or_404``)
    and service (``declare_use_item``).
    """

    item_instance_id = serializers.IntegerField(min_value=1)
    target_participant_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    target_opponent_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        if attrs.get("target_participant_id") and attrs.get("target_opponent_id"):
            msg = "Supply at most one of target_participant_id / target_opponent_id."
            raise serializers.ValidationError(msg)
        return attrs


class OpponentTargetSerializer(serializers.Serializer):
    """Write serializer for social-combat verbs that target an NPC opponent (#2015).

    Requires ``opponent_id`` — the PK of the ``CombatOpponent`` this character
    intends to demoralize/taunt/parley. Encounter-membership validation happens
    in the view (``get_object_or_404``) and service (``declare_<verb>``).
    """

    opponent_id = serializers.IntegerField(min_value=1)


class TauntTargetSerializer(serializers.Serializer):
    """Write serializer for declaring a taunt (#2015, #4737).

    Name exactly one target: ``opponent_id`` (a ``CombatOpponent``, draws its aggro) or
    ``participant_id`` (a ``CombatParticipant``, goads that player character into a rolled
    surge). Encounter membership is checked in the view (``get_object_or_404``) and in
    ``declare_taunt``.
    """

    opponent_id = serializers.IntegerField(min_value=1, required=False)
    participant_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        has_opponent = attrs.get("opponent_id") is not None
        has_participant = attrs.get("participant_id") is not None
        if has_opponent == has_participant:
            msg = "Name exactly one target to taunt: an opponent or a participant."
            raise serializers.ValidationError(msg)
        return attrs


class PhaseSpecSerializer(serializers.Serializer):
    """Read-only serializer for a single PhaseSpec dataclass (boss phase budget)."""

    phase_number = serializers.IntegerField()
    health_trigger_percentage = serializers.FloatField(allow_null=True)
    soak_value = serializers.IntegerField()
    probing_threshold = serializers.IntegerField(allow_null=True)


class OpponentStatBlockSerializer(serializers.Serializer):
    """Read-only serializer for the OpponentStatBlock dataclass.

    All fields are derived from the scaling formula — never writable.
    The ``phases`` list is non-empty only for BOSS tier.
    """

    max_health = serializers.IntegerField()
    soak_value = serializers.IntegerField()
    probing_threshold = serializers.IntegerField(allow_null=True)
    swarm_count = serializers.IntegerField(allow_null=True)
    body_toughness = serializers.IntegerField(allow_null=True)
    bodies_per_attack = serializers.IntegerField(allow_null=True)
    barrier_strength = serializers.IntegerField(allow_null=True)
    phases = PhaseSpecSerializer(many=True)


class OpponentDefaultsResponseSerializer(serializers.Serializer):
    """Read-only response serializer for the opponent-defaults preview endpoint.

    Contains all ``OpponentStatBlock`` scalar fields + ``phases`` + the two
    stakes-gate advisory fields.  Used only for ``@extend_schema`` so that
    drf-spectacular emits the correct component instead of inferring the
    viewset's default ``EncounterDetail`` schema.
    """

    max_health = serializers.IntegerField()
    soak_value = serializers.IntegerField()
    probing_threshold = serializers.IntegerField(allow_null=True)
    swarm_count = serializers.IntegerField(allow_null=True)
    body_toughness = serializers.IntegerField(allow_null=True)
    bodies_per_attack = serializers.IntegerField(allow_null=True)
    barrier_strength = serializers.IntegerField(allow_null=True)
    phases = PhaseSpecSerializer(many=True)
    stakes_ok = serializers.BooleanField()
    stakes_message = serializers.CharField(allow_blank=True)


class AddOpponentSerializer(serializers.Serializer):
    """Write serializer for adding an opponent to an encounter.

    ``tier`` is required.  ``max_health`` is optional — when omitted the scaling
    formula fills every stat field automatically (Task 5 auto-fill mode).
    All other stat fields are optional overrides.

    ``position_id`` (#2005) is optional; when supplied it must name a Position
    in the encounter's own room — validated against the encounter's room here
    so a mismatched position never reaches the service layer.

    Expects ``encounter`` and ``request`` in serializer context (provided by the
    view) so that ``validate()`` can run the stakes gate.
    """

    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    tier = serializers.ChoiceField(choices=OpponentTier.choices)
    persona_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="A named NPC the story uses, to stand as this opponent (#4373).",
    )
    max_health = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    level = serializers.IntegerField(min_value=1, max_value=30, required=False, allow_null=True)
    threat_pool_id = serializers.IntegerField()
    # The Add Opponent dialog always sends a description, blank when none was typed.
    description = serializers.CharField(required=False, default="", allow_blank=True)
    soak_value = serializers.IntegerField(required=False)
    probing_threshold = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    position_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        """Run stakes requirement gate + validate position_id against the encounter's room."""
        from world.areas.positioning.models import Position  # noqa: PLC0415
        from world.combat.scaling import (  # noqa: PLC0415
            StakesRequirementError,
            validate_stakes_requirement,
        )

        encounter = self.context.get("encounter")
        request = self.context.get("request")
        if encounter is not None and request is not None:
            try:
                validate_stakes_requirement(encounter, cast(AccountDB, request.user))
            except StakesRequirementError as exc:
                raise serializers.ValidationError({"non_field_errors": exc.user_message}) from exc

        position_id = attrs.get("position_id")
        if (
            position_id is not None
            and encounter is not None
            and not Position.objects.filter(pk=position_id, room=encounter.room).exists()
        ):
            raise serializers.ValidationError(
                {"position_id": "That position is not in this encounter's room."}
            )
        attrs["persona"] = self._named_npc(attrs.get("persona_id"), encounter, request)
        if not attrs.get("name"):
            if attrs["persona"] is None:
                raise serializers.ValidationError({"name": "A name is required."})
            attrs["name"] = attrs["persona"].name
        return attrs

    @staticmethod
    def _named_npc(persona_id: int | None, encounter: object, request: object) -> object:
        """The named NPC to stand, checked against the encounter's story (#4373)."""
        if persona_id is None:
            return None
        from world.combat.services.boss.opponent import (  # noqa: PLC0415
            _acting_story_for_encounter,
        )
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.stories.services.cast import may_stand_persona  # noqa: PLC0415

        persona = Persona.objects.filter(pk=persona_id).first()
        if persona is None:
            raise serializers.ValidationError({"persona_id": "No such named NPC."})
        is_staff = bool(request is not None and request.user.is_staff)
        story = _acting_story_for_encounter(encounter) if encounter is not None else None
        if not may_stand_persona(story, persona, is_staff=is_staff):
            raise serializers.ValidationError(
                {"persona_id": f"{persona.name} is not a named NPC this story uses."}
            )
        if (
            encounter is not None
            and encounter.opponents.filter(persona=persona, status=OpponentStatus.ACTIVE).exists()
        ):
            raise serializers.ValidationError(
                {"persona_id": f"{persona.name} is already in this fight."}
            )
        return persona


class EncounterSettingsSerializer(serializers.Serializer):
    """Write serializer for the GM-driven settings update (#3383).

    Every field is optional so a PATCH may change any subset of
    ``stakes_level``/``risk_level``/``pace_mode``/``pace_timer_minutes``/
    ``escalation_curve`` - mirrors ``update_encounter_settings``'s
    all-optional-kwargs shape. ``escalation_curve`` is tri-state: omitted
    leaves it unchanged, ``null`` clears it, a pk sets it (#3552).
    """

    stakes_level = serializers.ChoiceField(choices=StakesLevel.choices, required=False)
    risk_level = serializers.ChoiceField(choices=RiskLevel.choices, required=False)
    pace_mode = serializers.ChoiceField(choices=PaceMode.choices, required=False)
    pace_timer_minutes = serializers.IntegerField(min_value=1, required=False)
    escalation_curve = serializers.PrimaryKeyRelatedField(
        queryset=EscalationCurve.objects.all(),
        required=False,
        allow_null=True,
        help_text="Set the escalation curve; null clears it (#3552).",
    )


class DeclareClashContributionSerializer(serializers.Serializer):
    """Write serializer for declaring a PC's clash contribution for the current round.

    Expects ``participant`` (a ``CombatParticipant`` instance) in serializer context.
    Validates clash state, ownership, and the passive anima cap.  Resolves FK PKs to
    model instances so the service function receives clean, typed inputs.
    """

    clash = serializers.IntegerField()
    action_slot = serializers.ChoiceField(choices=ClashActionSlot.choices)
    technique = serializers.IntegerField()
    strain_commitment = serializers.IntegerField(min_value=0)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Resolve FKs and enforce clash-state, ownership, and passive-cap rules."""
        from world.combat.services import get_clash_config  # noqa: PLC0415

        participant: CombatParticipant = self.context["participant"]

        # --- Resolve Clash ---
        try:
            clash = Clash.objects.get(pk=attrs["clash"])
        except Clash.DoesNotExist as exc:
            raise serializers.ValidationError({"clash": "Clash not found."}) from exc

        # Clash must be ACTIVE.
        if clash.status != ClashStatus.ACTIVE:
            raise serializers.ValidationError(
                {"clash": "Clash is not active and cannot accept contributions."}
            )

        # Clash must belong to the participant's encounter.
        if clash.encounter_id != participant.encounter_id:
            raise serializers.ValidationError(
                {"clash": "Clash does not belong to the participant's encounter."}
            )

        # --- Resolve Technique ---
        try:
            technique = Technique.objects.get(pk=attrs["technique"])
        except Technique.DoesNotExist as exc:
            raise serializers.ValidationError({"technique": "Technique not found."}) from exc

        # Participant must own the technique.
        owns = CharacterTechnique.objects.filter(
            character=participant.character_sheet,
            technique=technique,
        ).exists()
        if not owns:
            raise serializers.ValidationError({"technique": "You do not know this technique."})

        # --- Passive anima cap ---
        action_slot = attrs["action_slot"]
        strain_commitment = attrs["strain_commitment"]
        if action_slot == ClashActionSlot.PASSIVE:
            config = get_clash_config()
            if strain_commitment > config.passive_anima_cap:
                raise serializers.ValidationError(
                    {
                        "strain_commitment": (
                            f"Passive contributions may not commit more than "
                            f"{config.passive_anima_cap} anima (got {strain_commitment})."
                        )
                    }
                )

        return {
            "clash": clash,
            "action_slot": action_slot,
            "technique": technique,
            "strain_commitment": strain_commitment,
        }


class ConsiderReadingSerializer(serializers.Serializer):
    """Read serializer for a cached consider reading (#2716).

    Exposes only ``prose``, ``assessed_at``, and ``is_cached`` — never the
    check mechanics (success_level, true_band_index, reported_band_index).
    """

    prose = serializers.CharField(read_only=True)
    assessed_at = serializers.DateTimeField(read_only=True, source="created_at")
    is_cached = serializers.SerializerMethodField()

    def get_is_cached(self, obj: ConsiderReading) -> bool:  # noqa: ARG002
        """True when this is a re-fetch of an existing reading."""
        return self.context.get("is_cached", False)

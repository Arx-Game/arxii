"""Serializers for combat API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema_field
from evennia.accounts.models import AccountDB
from rest_framework import serializers

from world.areas.positioning.serializers import (
    PositionAdjacencyItemSerializer,
    PositionEdgeSerializer,
    PositionNodeSerializer,
    PositionSummarySerializer,
)
from world.combat.constants import (
    NO_ROLE_SPEED_RANK,
    ActionCategory,
    ClashActionSlot,
    ClashStatus,
    EncounterOutcome,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import (
    Clash,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    DramaticSurgeRecord,
    DuelChallenge,
    EscalationCurve,
)
from world.conditions.serializers import ConditionInstanceSerializer
from world.conditions.services import get_active_conditions
from world.fatigue.services import get_fatigue_capacity
from world.magic.models import CharacterTechnique, Technique
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import PersonaType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona

# ---------------------------------------------------------------------------
# Condition helpers
# ---------------------------------------------------------------------------


# Attribute name the viewset's Prefetch(to_attr=...) lands the active
# ConditionInstances on (on the participant's character / opponent's
# objectdb ObjectDB). Read here so the serializer avoids an N+1.
ACTIVE_CONDITIONS_CACHE_ATTR = "active_condition_instances"


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

    Prefers the viewset's ``Prefetch(to_attr=ACTIVE_CONDITIONS_CACHE_ATTR)``
    cache (built with the same select_related + suppression filter as
    ``get_active_conditions``) — visibility filter + priority ordering run
    in Python over the identity-mapped list, so no per-row query fires.
    Falls back to ``get_active_conditions`` for callers that build the
    serializer directly (e.g. unit tests).
    """
    # Suppression justified: live/time-derived set on identity-mapped parent; context-over-cache —
    # (#2401) never a cached_property.
    cached = getattr(target, ACTIVE_CONDITIONS_CACHE_ATTR, None)  # noqa: GETATTR_LITERAL
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


# ---------------------------------------------------------------------------
# Nested read serializers
# ---------------------------------------------------------------------------


class OpponentSerializer(serializers.ModelSerializer):
    """Read serializer for combat opponents.

    Soak value and probing threshold are GM-only — players discover
    these through gameplay (probing attacks, combo availability).
    """

    soak_value = serializers.SerializerMethodField()
    probing_threshold = serializers.SerializerMethodField()
    active_conditions = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    thumbnail_media_url = serializers.SerializerMethodField()
    current_position = PositionSummarySerializer(read_only=True, allow_null=True)
    # The in-world ObjectDB pk, distinct from this opponent's own pk (``id``).
    # ``id`` is the CombatOpponent PK the focused-target dispatch sends as
    # ``focused_opponent_target_id``; ``objectdb_id`` is the ObjectDB pk the
    # applicable-pulls API consumes as ``target_object_id``. Plain FK column —
    # no query. Null for opponents with no backing ObjectDB.
    objectdb_id = serializers.IntegerField(read_only=True, allow_null=True)
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
            "health",
            "max_health",
            "soak_value",
            "probing_current",
            "probing_threshold",
            "current_phase",
            "status",
            "active_conditions",
            "thumbnail_url",
            "thumbnail_media_url",
            "current_position",
            "mirrors_participant_id",
        ]

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
        """PlayerMedia portrait URL, dynamically resolved (#2196).

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
    thumbnail_url = serializers.SerializerMethodField()
    thumbnail_media_url = serializers.SerializerMethodField()
    escalation_level = serializers.SerializerMethodField()
    intensity_modifier = serializers.SerializerMethodField()
    control_modifier = serializers.SerializerMethodField()
    current_position = PositionSummarySerializer(read_only=True, allow_null=True)

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
            "thumbnail_url",
            "thumbnail_media_url",
            "escalation_level",
            "intensity_modifier",
            "control_modifier",
            "current_position",
        ]

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

    def _combat_engagement(self, obj: CombatParticipant) -> CharacterEngagement | None:
        """Resolve the participant's COMBAT CharacterEngagement, if any.

        Reads the reverse OneToOne accessor (``character.engagement``) rather
        than a fresh ``.filter()`` — the descriptor caches the result (even
        the no-row case) on the identity-mapped ObjectDB instance, so the
        three escalation fields share at most one query per character and the
        warm API path pays zero (no prefetch machinery; the idmapper is the
        cache layer). ``None`` when the character has no engagement, or its
        engagement is non-COMBAT (challenge/mission stakes are not combat
        escalation).
        """
        try:
            engagement = obj.character_sheet.character.engagement
        except (AttributeError, CharacterEngagement.DoesNotExist):
            return None
        # Queryset deletes null the pk on the cached instance without clearing
        # the reverse accessor; treat a pk-less engagement as gone.
        if engagement.pk is None:
            return None
        if engagement.engagement_type != EngagementType.COMBAT:
            return None
        return engagement

    def get_escalation_level(self, obj: CombatParticipant) -> int | None:
        """Escalation pressure on this combatant — public dramatic state."""
        engagement = self._combat_engagement(obj)
        return engagement.escalation_level if engagement else None

    def get_intensity_modifier(self, obj: CombatParticipant) -> int | None:
        """Process-derived intensity bonus from the COMBAT engagement."""
        engagement = self._combat_engagement(obj)
        return engagement.intensity_modifier if engagement else None

    def get_control_modifier(self, obj: CombatParticipant) -> int | None:
        """Process-derived control bonus from the COMBAT engagement."""
        engagement = self._combat_engagement(obj)
        return engagement.control_modifier if engagement else None

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
        """PlayerMedia portrait URL, dynamically resolved (#2196).

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
        # #2196: use the view's prefetched conditions (ACTIVE_CONDITIONS_CACHE_ATTR)
        # to avoid N+1 when serializing multiple participants.
        # Suppression justified: live/time-derived set on identity-mapped parent; (#2401) — never
        # context-over-cache a cached_property.
        cached_conditions = getattr(character, "active_condition_instances", None)  # noqa: GETATTR_LITERAL
        return resolve_thumbnail(character, persona=persona, cached_conditions=cached_conditions)


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
    """

    challenger = _DuelParticipantIdentitySerializer(source="challenger_sheet", read_only=True)
    challenged = _DuelParticipantIdentitySerializer(source="challenged_sheet", read_only=True)

    class Meta:
        model = DuelChallenge
        fields = [
            "id",
            "challenger",
            "challenged",
            "status",
            "created_at",
            "resolved_at",
            "resulting_encounter",
        ]
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
        """Return participant count, preferring cached list."""
        try:
            return len(obj.participants_cached)  # type: ignore[attr-defined]
        except AttributeError:
            return obj.participants.count()

    def get_opponent_count(self, obj: CombatEncounter) -> int:
        """Return opponent count, preferring cached list."""
        try:
            return len(obj.opponents_cached)  # type: ignore[attr-defined]
        except AttributeError:
            return obj.opponents.count()


class VolatileObjectSerializer(serializers.Serializer):
    """A detonatable object in the encounter room, for the redirect destination picker (#2210)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    position_id = serializers.IntegerField(read_only=True, allow_null=True)
    position_name = serializers.CharField(read_only=True, allow_null=True)


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
    resolution_order = serializers.SerializerMethodField()
    position_adjacency = serializers.SerializerMethodField()
    position_nodes = serializers.SerializerMethodField()
    position_edges = serializers.SerializerMethodField()
    volatile_objects = serializers.SerializerMethodField()
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
            "resolution_order",
            "escalation_curve",
            "escalation_curve_name",
            "escalation_start_round",
            "escalation_tick_narration",
            "forced_escape",
            "position_adjacency",
            "position_nodes",
            "position_edges",
            "volatile_objects",
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
        return any(
            p.character_sheet.character_id in character_ids
            for p in obj.participants_cached  # type: ignore[attr-defined]
        )

    def get_resolution_order(self, obj: CombatEncounter) -> list[int]:
        """ACTIVE PC participant PKs in initiative (speed-rank) order.

        Computed in-memory from ``participants_cached`` (which already
        ``select_related("covenant_role")``) so serialization issues **no extra
        query** — mirrors the speed-rank ordering of ``services.get_resolution_order``
        for ACTIVE PCs (speed_rank asc, then pk). The frontend RoundFlow orders its
        initiative chips by this and marks the first not-yet-acted participant as the
        on-deck actor.

        The resolution path additionally applies a ``can_act`` filter (excluding a
        downed-but-not-removed PC); that is omitted here to stay query-free, so such
        a PC may still appear in the display order. Acceptable for a display field.
        """
        active = [p for p in obj.participants_cached if p.status == ParticipantStatus.ACTIVE]
        active.sort(
            key=lambda p: (
                p.covenant_role.speed_rank if p.covenant_role_id else NO_ROLE_SPEED_RANK,
                p.pk,
            )
        )
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

    def get_surge_beats(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return this round's dramatic-surge beats (#2013).

        Every viewer sees the generic ``narration`` line (never names the
        bond/track/subject — the leak rule). ``trigger_kind``/``amount`` are
        added only for the surging participant's own owner, GMs, and staff —
        mirrors ``get_current_round_actions``'s covenant-scoped pattern.
        """
        request = self.context.get("request")
        records = DramaticSurgeRecord.objects.filter(
            encounter=obj,
            round_number=obj.round_number,
        ).select_related("participant__character_sheet__character", "encounter__escalation_curve")

        is_gm_or_staff = self.context.get("is_gm", False) or (
            request is not None and request.user.is_staff
        )
        viewer_character_ids = self.context.get("viewer_character_ids", set())

        beats: list[dict[str, Any]] = []
        for record in records:
            beat: dict[str, Any] = {"narration": self._render_surge_beat_narration(record)}
            character_id = record.participant.character_sheet.character_id
            if is_gm_or_staff or character_id in viewer_character_ids:
                beat["trigger_kind"] = record.trigger_kind
                beat["amount"] = record.amount
                beat["participant"] = record.participant_id
            beats.append(beat)
        return beats

    @staticmethod
    def _render_surge_beat_narration(record: DramaticSurgeRecord) -> str:
        """Re-render the generic narration line from the curve template.

        The record itself stores only trigger_kind/amount/subject (audit
        data) — narration is derived at read time from the encounter's
        current curve, same as the live broadcast at write time.
        """
        from world.combat.escalation import _render_surge_narration  # noqa: PLC0415

        curve = record.encounter.escalation_curve
        character_name = record.participant.character_sheet.character.db_key
        if curve is None:
            return ""
        return _render_surge_narration(curve, character_name)

    def get_clashes(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return active Clash records for this encounter.

        Phase 8, Task 8.4 — exposes clash state to the frontend ActiveState
        rail section. Returns only ACTIVE clashes so resolved ones don't litter
        the UI after the clash is done.

        Uses the ``clashes_cached`` prefetch-to-attr set on the viewset's
        ``_base_queryset`` so no extra query fires during detail serialization.
        Falls back to a direct filter for callers that don't use the viewset
        (e.g. unit tests that call the serializer directly).
        """
        # Suppression justified: live/time-derived set on identity-mapped parent; (#2401) — never
        # context-over-cache a cached_property.
        clashes = getattr(obj, "clashes_cached", None)  # noqa: GETATTR_LITERAL
        if clashes is None:
            clashes = (
                Clash.objects.filter(
                    encounter=obj,
                    status=ClashStatus.ACTIVE,
                )
                .select_related("npc_opponent")
                .all()
            )
        return ClashStateSerializer(clashes, many=True).data  # type: ignore[return-value]

    def get_engagement_locks(self, obj: CombatEncounter) -> list[dict[str, Any]]:
        """Return active EngagementLock records for this encounter (#2020).

        Exposes foil pairings (who is dueling whom) to the frontend combat UI.
        Returns only ACTIVE locks so resolved ones don't appear after breaking.

        Uses the ``engagement_locks_cached`` prefetch-to-attr set on the
        viewset's ``_base_queryset`` so no extra query fires during detail
        serialization. Falls back to a direct filter for callers that don't
        use the viewset (e.g. unit tests that call the serializer directly).
        """
        # Suppression justified: live/time-derived set on identity-mapped parent; (#2401) — never
        # context-over-cache a cached_property.
        locks = getattr(obj, "engagement_locks_cached", None)  # noqa: GETATTR_LITERAL
        if locks is None:
            from world.combat.constants import EngagementLockStatus  # noqa: PLC0415
            from world.combat.models import EngagementLock  # noqa: PLC0415

            locks = EngagementLock.objects.filter(
                encounter=obj,
                status=EngagementLockStatus.ACTIVE,
            )

        return [
            {
                "id": lock.pk,
                "opponent_id": lock.opponent_id,
                "participant_id": lock.participant_id,
                "status": lock.status,
                "initiated_by": lock.initiated_by,
                "started_round": lock.started_round,
            }
            for lock in locks
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

    name = serializers.CharField(max_length=200)
    tier = serializers.ChoiceField(choices=OpponentTier.choices)
    max_health = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    threat_pool_id = serializers.IntegerField()
    description = serializers.CharField(required=False, default="")
    soak_value = serializers.IntegerField(required=False, default=0)
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
        if position_id is not None and encounter is not None:
            if not Position.objects.filter(pk=position_id, room=encounter.room).exists():
                raise serializers.ValidationError(
                    {"position_id": "That position is not in this encounter's room."}
                )
        return attrs


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

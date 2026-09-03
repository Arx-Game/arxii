from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from evennia.objects.models import ObjectDB
from rest_framework import serializers

from world.areas.positioning.serializers import (
    PersonaPositionSerializer,
    PositionAdjacencyItemSerializer,
    PositionEdgeSerializer,
    PositionNodeSerializer,
    PositionSummarySerializer,
)
from world.justice.constants import HUMILIATION_MARK_EXPLANATION
from world.justice.serializers import HumiliationMarkSerializer
from world.missions.serializers import GroupBallotStateSerializer, GroupBeatResultSerializer
from world.scenes.constants import (
    ScenePrivacyMode,
    SceneRoundMode,
    SceneRoundStartReason,
)
from world.scenes.models import (
    Persona,
    PersonaType,
    Scene,
    SceneParticipation,
    SceneRound,
    SceneSummaryRevision,
)
from world.societies.constants import RenownRisk
from world.societies.houses.constants import NameDegree, TitleSuffixMode


class PersonaSerializer(serializers.ModelSerializer):
    roster_entry = serializers.SerializerMethodField()
    thumbnail_media_url = serializers.SerializerMethodField()
    allow_social_actions = serializers.SerializerMethodField()
    # #3261 — the particled composed name at this persona's preferred degree.
    display_name = serializers.SerializerMethodField()
    # #1682 — the guise's fabricated bio (null profile → empty strings), so the
    # web authoring dialog can prefill and blank-clears stay safe.
    guise_concept = serializers.SerializerMethodField()
    guise_quote = serializers.SerializerMethodField()
    guise_personality = serializers.SerializerMethodField()
    guise_background = serializers.SerializerMethodField()
    # #2378 follow-up (ruling 5) — the fading reputational layer atop a
    # permanent, provenance-free brand; None once HUMILIATION_TERM_DAYS passes.
    humiliation_mark = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = [
            "id",
            "character_sheet",
            "name",
            "display_name",
            "name_degree",
            "title_suffix",
            "is_fake_name",
            "persona_type",
            "thumbnail_url",
            "thumbnail_media_url",
            "roster_entry",
            "allow_social_actions",
            "guise_concept",
            "guise_quote",
            "guise_personality",
            "guise_background",
            "humiliation_mark",
        ]
        read_only_fields = ["roster_entry", "allow_social_actions", "display_name"]

    def get_display_name(self, obj: Persona) -> str:
        """The particled name at the persona's preferred degree (#3261).

        Only the PRIMARY persona derives from the kinship graph; disguises and
        alternate faces present their claimed name bare, so the née segment
        can never leak the true birth family through a mask.
        """
        from world.societies.houses.services import full_display_name  # noqa: PLC0415

        if obj.persona_type != PersonaType.PRIMARY:
            return obj.name
        try:
            person = obj.character_sheet.kinsperson
        except (AttributeError, ObjectDoesNotExist):
            return obj.name
        if person is None:
            return obj.name
        return full_display_name(person, degree=obj.name_degree, title_suffix=obj.title_suffix)

    def get_guise_concept(self, obj: Persona) -> str:
        return obj.profile.concept if obj.profile_id else ""

    def get_guise_quote(self, obj: Persona) -> str:
        return obj.profile.quote if obj.profile_id else ""

    def get_guise_personality(self, obj: Persona) -> str:
        return obj.profile.personality if obj.profile_id else ""

    def get_guise_background(self, obj: Persona) -> str:
        return obj.profile.background if obj.profile_id else ""

    def get_thumbnail_media_url(self, obj: Persona) -> str | None:
        from world.conditions.thumbnail_services import resolve_thumbnail  # noqa: PLC0415

        try:
            character = obj.character_sheet.character
        except AttributeError:
            return None
        return resolve_thumbnail(character, persona=obj)

    def get_allow_social_actions(self, obj: Persona) -> bool:
        """Whether this persona's character may be targeted by social actions.

        Mirrors the challenge consent gate (``_tenure_blocks_actor`` with
        ``category=None``): blocked only when the active tenure's
        ``SocialConsentPreference`` has ``allow_social_actions=False``. Lets the
        scene UI hide/disable the duel-challenge affordance for opted-out
        characters (#1181); the backend still enforces the full gate at dispatch.
        Defaults to True when there is no tenure or preference row.
        """
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        sheet = obj.character_sheet
        if sheet is None:
            return True
        try:
            entry = sheet.roster_entry
            tenure = entry.current_tenure if entry else None
            if tenure is None:
                return True
            return tenure.social_consent_preference.allow_social_actions
        except ObjectDoesNotExist:
            return True

    def get_roster_entry(self, obj: Persona) -> dict[str, int | str] | None:
        try:
            entry = obj.character_sheet.roster_entry
        except AttributeError:
            entry = None
        if entry:
            return {"id": entry.id, "name": entry.character_sheet.character.db_key}
        return None

    @extend_schema_field(HumiliationMarkSerializer(allow_null=True))
    def get_humiliation_mark(self, obj: Persona) -> dict[str, str] | None:
        """The fading half of a #2378-follow-up humiliation, or None (ruling 5).

        Neutral PLACEHOLDER copy only — never what the humiliation was, mirroring
        ``apply_humiliation``'s own rule. Disappears at ``HUMILIATION_TERM_DAYS``
        (prestige restored the same tick); the persona's permanent brand is
        unaffected either way — this field is examine/profile-only, not the brand.
        """
        from world.justice.sentences import active_humiliation_mark  # noqa: PLC0415

        mark = active_humiliation_mark(obj)
        if mark is None:
            return None
        return HumiliationMarkSerializer(
            {"kind": mark.kind, "until": mark.until, "explanation": HUMILIATION_MARK_EXPLANATION}
        ).data


class SceneParticipantSerializer(serializers.ModelSerializer):
    """Simplified participant representation for scene lists"""

    roster_entry = serializers.SerializerMethodField()
    dramatic_moment_count = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = ["id", "name", "roster_entry", "dramatic_moment_count"]

    def get_roster_entry(self, obj):
        try:
            entry = obj.character_sheet.roster_entry
        except AttributeError:
            entry = None
        if entry:
            return {"id": entry.id, "name": entry.character_sheet.character.db_key}
        return None

    def get_dramatic_moment_count(self, obj) -> int:
        sheet = obj.character_sheet
        if sheet is None:
            return 0
        count_map: dict[int, int] = self.context.get("dramatic_moment_counts", {})
        return count_map.get(sheet.pk, 0)


class SceneListSerializer(serializers.ModelSerializer):
    """Simplified scene representation for lists"""

    participants = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=ObjectDB.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        source="location",
    )
    is_owner = serializers.SerializerMethodField()
    viewer_can_gm = serializers.SerializerMethodField()
    running_beat = serializers.SerializerMethodField()

    class Meta:
        model = Scene
        fields = [
            "id",
            "name",
            "description",
            "date_started",
            "location",
            "location_id",
            "participants",
            "is_owner",
            "viewer_can_gm",
            "running_beat",
        ]

    def get_location(self, obj):
        if obj.location:
            return {"id": obj.location.id, "name": obj.location.db_key}
        return None

    def get_participants(self, obj: Scene) -> list[dict]:
        personas = self._collect_personas(obj, only_real_names=True)
        # Build a {character_sheet_id: count} map from the prefetched tags
        # (cached_scene_drama_tags set by SceneViewSet.get_queryset) to avoid N+1.
        # Falls back to an empty map if the attr is absent (e.g. direct
        # serializer instantiation in tests that don't use the viewset).
        cached_tags = getattr(obj, "cached_scene_drama_tags", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if cached_tags is not None:
            count_map: dict[int, int] = {}
            for tag in cached_tags:
                count_map[tag.character_sheet_id] = count_map.get(tag.character_sheet_id, 0) + 1
        else:
            count_map = {}
        return SceneParticipantSerializer(
            personas,
            many=True,
            context={"scene": obj, "dramatic_moment_counts": count_map},
        ).data

    @staticmethod
    def _collect_personas(obj: Scene, *, only_real_names: bool) -> list[Persona]:
        """Dedup personas reachable via the scene's interactions.

        Reads from the ``cached_interactions`` attribute populated by
        SceneViewSet's prefetch. Falls back to a fresh query if the serializer
        is used outside the viewset (e.g., direct instantiation in tests).
        """
        cached = getattr(obj, "cached_interactions", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if cached is None:
            cached = list(
                obj.interactions.select_related(
                    "persona__character_sheet__character",
                    "persona__character_sheet__roster_entry",
                    "persona__thumbnail",
                )
            )
        seen: dict[int, Persona] = {}
        for interaction in cached:
            persona = interaction.persona
            if persona is None or persona.pk in seen:
                continue
            if only_real_names and persona.is_fake_name:
                continue
            seen[persona.pk] = persona
        return list(seen.values())

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        privacy_mode = attrs.get("privacy_mode") or (
            self.instance.privacy_mode if self.instance is not None else None
        )
        location = attrs.get("location") or (
            self.instance.location if self.instance is not None else None
        )
        if (
            location is not None
            and privacy_mode is not None
            and privacy_mode != ScenePrivacyMode.PUBLIC
        ):
            from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415

            if room_is_publicly_listed(location):
                raise serializers.ValidationError(
                    {
                        "privacy_mode": (
                            "A non-public scene cannot be created in a publicly-listed room."
                        )
                    }
                )
        return attrs

    def get_is_owner(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.is_owner(request.user)
        return False

    def get_viewer_can_gm(self, obj: Scene) -> bool:
        request = self.context.get("request")
        if not (request and request.user and request.user.is_authenticated):
            return False
        user = request.user
        return bool(user.is_staff or obj.is_gm(user) or obj.is_owner(user))

    def get_running_beat(self, obj: Scene) -> dict[str, object] | None:
        """The Beat this scene is currently running (#3425), GM/staff viewers only.

        Only id + risk tier -- beat internals (internal_description, player
        hints, etc.) never ride this payload (see the #3425 spec's leak
        table); #3433 decides the separate player-visible slice.
        """
        if obj.running_beat_id is None:
            return None
        if not self.get_viewer_can_gm(obj):
            return None
        return {"id": obj.running_beat_id, "risk": obj.running_beat.risk}


class SceneRoundSerializer(serializers.ModelSerializer):
    """Read-only view of a scene's active round, for the round-settings control (#1467)."""

    is_danger = serializers.SerializerMethodField()

    class Meta:
        model = SceneRound
        fields = [
            "mode",
            "advance_quorum_pct",
            "max_actions_per_round",
            "per_target_repeat_lock",
            "status",
            "round_number",
            "is_danger",
        ]

    def get_is_danger(self, obj: SceneRound) -> bool:
        return obj.start_reason == SceneRoundStartReason.DANGER


class SceneDetailSerializer(SceneListSerializer):
    """Full scene representation with personas"""

    personas = serializers.SerializerMethodField()
    positions = serializers.SerializerMethodField()
    position_adjacency = serializers.SerializerMethodField()
    position_nodes = serializers.SerializerMethodField()
    position_edges = serializers.SerializerMethodField()
    persona_positions = serializers.SerializerMethodField()
    active_round = serializers.SerializerMethodField()
    declared_risk = serializers.SerializerMethodField()

    class Meta(SceneListSerializer.Meta):
        model = Scene
        fields = [
            *SceneListSerializer.Meta.fields,
            "date_finished",
            "is_active",
            "privacy_mode",
            "personas",
            "positions",
            "position_adjacency",
            "position_nodes",
            "position_edges",
            "persona_positions",
            "active_round",
            "declared_risk",
        ]
        extra_kwargs = {"name": {"required": False}}

    def get_personas(self, obj: Scene) -> list[dict]:
        personas = self._collect_personas(obj, only_real_names=False)
        return PersonaSerializer(personas, many=True).data

    def get_participants(self, obj):
        return super().get_participants(obj)

    @extend_schema_field(PositionSummarySerializer(many=True))
    def get_positions(self, obj: Scene) -> list[dict]:
        """Return all positions in the scene's room as [{id, name}].

        Returns an empty list when the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.models import Position  # noqa: PLC0415

        positions = Position.objects.filter(room=obj.location)
        return PositionSummarySerializer(positions, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PositionAdjacencyItemSerializer(many=True))
    def get_position_adjacency(self, obj: Scene) -> list[dict]:
        """Return ADJACENT-reach position adjacency for the scene's room.

        Each entry is ``{position_id: int, adjacent_position_ids: [int]}``.
        Returns an empty list when the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.services import room_position_adjacency  # noqa: PLC0415

        entries = room_position_adjacency(obj.location)
        return PositionAdjacencyItemSerializer(entries, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PositionNodeSerializer(many=True))
    def get_position_nodes(self, obj: Scene) -> list[dict]:
        """Return the full position-node list for the scene's room (#2006).

        Unlike ``positions`` (id+name only), carries kind/elevation/layout for
        spatial rendering. Empty list when the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.services import position_graph  # noqa: PLC0415

        graph = position_graph(obj.location)
        return PositionNodeSerializer(graph.nodes, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PositionEdgeSerializer(many=True))
    def get_position_edges(self, obj: Scene) -> list[dict]:
        """Return every edge (obstacle/gate visibility) for the scene's room (#2006).

        Unlike ``position_adjacency`` (the reach graph), carries every edge
        with is_passable/blocks_flight/gating_challenge_name. Empty list when
        the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.services import position_graph  # noqa: PLC0415

        graph = position_graph(obj.location)
        return PositionEdgeSerializer(graph.edges, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PersonaPositionSerializer(many=True))
    def get_persona_positions(self, obj: Scene) -> list[dict]:
        """Return [{persona_id, position: {id, name} | null}] for each persona in the scene.

        Resolves position via persona.character_sheet.character → position_of(character).
        Returns an empty list when the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.services import position_of  # noqa: PLC0415

        personas = self._collect_personas(obj, only_real_names=False)
        result = []
        for persona in personas:
            position = None
            if persona.character_sheet is not None:
                character = persona.character_sheet.character
                if character is not None:
                    pos = position_of(character)
                    if pos is not None:
                        position = PositionSummarySerializer(pos).data
            result.append({"persona_id": persona.pk, "position": position})
        return result

    @extend_schema_field(SceneRoundSerializer(allow_null=True))
    def get_active_round(self, obj: Scene) -> dict | None:
        if obj.location is None:
            return None
        from world.scenes.round_services import active_round_for_room  # noqa: PLC0415

        rnd = active_round_for_room(obj.location)
        return SceneRoundSerializer(rnd).data if rnd is not None else None

    def get_declared_risk(self, obj: Scene) -> str | None:
        """Player-visible declared risk tier for the scene header badge (#3433).

        Precedence: ``scene.running_beat.risk`` (#3425) -> the active (not-yet-
        completed) combat encounter's ``story_beat.risk`` -> the scene's PENDING
        ``DecisiveCheckMarker``'s beat risk -> ``None``. Reads
        ``story_beat.risk`` (``RenownRisk``, the narrative stakes tier) --
        NEVER ``CombatEncounter.risk_level`` (the combat ``RiskLevel`` enum
        that drives the acknowledgement gate; a different field one hop away).
        Returns the tier string only -- never the beat's id/name/internals,
        which stay on the GM/staff-gated ``running_beat`` field above.
        ``RenownRisk.NONE`` renders nothing: undeclared risk is not "safe".
        """
        risk = self._resolve_declared_risk(obj)
        if risk is None or risk == RenownRisk.NONE:
            return None
        return risk

    @staticmethod
    def _resolve_declared_risk(obj: Scene) -> str | None:
        """Delegates the precedence chain to ``world.scenes.beat_selectors``.

        Extracted in #3463 because Legend settlement must resolve the SAME beat
        this badge reports. Two copies would drift, and the drift would mean the
        badge telling a player what they are risking while settlement paid them
        for something else.
        """
        from world.scenes.beat_selectors import running_beat_for_scene  # noqa: PLC0415

        beat = running_beat_for_scene(obj)
        return beat.risk if beat is not None else None


class ScenesSpotlightSerializer(serializers.Serializer):
    """
    Serializer for the spotlight endpoint that matches frontend expectations
    """

    in_progress = SceneListSerializer(many=True, source="active_scenes")
    recent = SceneListSerializer(many=True, source="recent_scenes")


class HighlightReelFeaturedSerializer(serializers.Serializer):
    """The single featured moment of a scene's highlight reel (#1241, #2161).

    The collapsed featured card is *fully sealed* — it shows no pose content, type, or
    participants until the viewer expands it, at which point the frontend fetches the
    pose through the existing interaction-detail endpoint (which re-checks visibility).
    Sending pose content here would defeat the seal, but ``vote_count``/``reaction_count``
    (#2161) are exposed so the frontend can badge the sealed card.
    """

    interaction_id = serializers.IntegerField()
    vote_count = serializers.IntegerField()
    reaction_count = serializers.IntegerField()


class HighlightReelEntrySerializer(serializers.Serializer):
    """One sealed entry in the ranked index below the featured moment (#1241, #2161)."""

    interaction_id = serializers.IntegerField()
    rank = serializers.IntegerField()
    vote_count = serializers.IntegerField()
    reaction_count = serializers.IntegerField()


class HighlightReelSerializer(serializers.Serializer):
    """A scene's highlight reel: a sealed featured moment + a ranked index (#1241, #2161).

    ``featured`` is null when the scene has no GM-tagged moments AND no voted-or-reacted
    poses (an empty reel — the frontend hides the collapsible section).
    """

    featured = HighlightReelFeaturedSerializer(allow_null=True)
    index = HighlightReelEntrySerializer(many=True)


class SceneSummaryRevisionSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = SceneSummaryRevision
        fields = ["id", "scene", "persona", "persona_name", "content", "action", "timestamp"]
        read_only_fields = ["timestamp"]

    def _validate_persona_is_the_requester(self, persona: Persona) -> None:
        """The revision must be signed with a face the requesting account actually wears."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return
        roster_entry = persona.character_sheet.roster_entry_or_none
        if roster_entry is None:
            raise serializers.ValidationError(
                {"persona": "Persona's character has no roster entry."}
            )
        from world.roster.models import RosterTenure  # noqa: PLC0415

        owns_character = RosterTenure.objects.filter(
            roster_entry=roster_entry,
            player_data__account=request.user,
            end_date__isnull=True,
        ).exists()
        if not owns_character:
            raise serializers.ValidationError(
                {"persona": "You can only submit revisions as your own persona."}
            )

    def _validate_persona_was_there(self, scene: Scene, persona: Persona) -> None:
        """The signing persona's account must be a participant of the scene being summarized.

        A persona with no roster entry, or whose character has no active tenure,
        has no account to check against and is left to the ownership check above.
        """
        from world.roster.models import RosterTenure  # noqa: PLC0415

        # Audit fix (was getattr(...character, "roster_entry", None)): the reverse
        # OneToOne lives on the SHEET — the old receiver was the ObjectDB character,
        # so this always resolved None and the participant check silently never ran.
        roster_entry = persona.character_sheet.roster_entry_or_none
        if not roster_entry:
            return
        active_tenure = (
            RosterTenure.objects.filter(
                roster_entry=roster_entry,
                end_date__isnull=True,
            )
            .select_related("player_data")
            .first()
        )
        if not active_tenure:
            return
        is_participant = SceneParticipation.objects.filter(
            scene=scene,
            account=active_tenure.player_data.account,
        ).exists()
        if not is_participant:
            raise serializers.ValidationError(
                {"persona": "Persona must belong to a participant of this scene."}
            )

    def validate(self, attrs: dict) -> dict:
        scene = attrs.get("scene")
        persona = attrs.get("persona")

        if scene and scene.privacy_mode != ScenePrivacyMode.EPHEMERAL:
            raise serializers.ValidationError(
                {"scene": "Summary revisions can only be submitted for ephemeral scenes."}
            )
        if persona:
            self._validate_persona_is_the_requester(persona)
        if scene and persona:
            self._validate_persona_was_there(scene, persona)
        return attrs


class SetActivePersonaRequestSerializer(serializers.Serializer):
    """POST body for the #981 set-active-persona endpoint."""

    persona_id = serializers.IntegerField(min_value=1)


class SetNameDisplayRequestSerializer(serializers.Serializer):
    """POST body for the #3261 set-name-display endpoint (degree + titles)."""

    name_degree = serializers.ChoiceField(choices=NameDegree.choices)
    title_suffix = serializers.ChoiceField(choices=TitleSuffixMode.choices)


class ActivePersonaResultSerializer(serializers.Serializer):
    """Result of the #981 set-active-persona endpoint — the now-worn face id."""

    active_persona_id = serializers.IntegerField(read_only=True)


class CreateEstablishedPersonaRequestSerializer(serializers.Serializer):
    """POST body for the #1127 create-established-persona endpoint."""

    name = serializers.CharField(max_length=255)


class CreateMaskRequestSerializer(serializers.Serializer):
    """POST body for the #1127 create-mask endpoint — a temporary anonymous face."""

    name = serializers.CharField(max_length=255)


class SetPersonaProfileRequestSerializer(serializers.Serializer):
    """POST body for the #1682 set-profile endpoint — author a guise's bio.

    Every bio field is optional and None-preserving: an ABSENT field leaves the
    stored value untouched (the ``set_persona_profile`` contract, so partial
    edits are safe), while a PRESENT-but-blank field explicitly clears it.
    """

    persona_id = serializers.IntegerField(min_value=1)
    concept = serializers.CharField(required=False, allow_blank=True, max_length=255)
    quote = serializers.CharField(required=False, allow_blank=True)
    personality = serializers.CharField(required=False, allow_blank=True)
    background = serializers.CharField(required=False, allow_blank=True)


class SetRoundModeRequestSerializer(serializers.Serializer):
    """POST body for the #1445 set-round-mode endpoint.

    All fields are optional — callers may change the mode, one or more knobs, or any
    combination. At least one field should be provided (the action will succeed with
    a generic message if none are, because the service is a no-op update).
    """

    mode = serializers.ChoiceField(choices=SceneRoundMode.choices, required=False)
    advance_quorum_pct = serializers.IntegerField(min_value=0, max_value=100, required=False)
    max_actions_per_round = serializers.IntegerField(min_value=0, required=False)
    per_target_repeat_lock = serializers.BooleanField(required=False)


class TruncatePrecaptureRequestSerializer(serializers.Serializer):
    """POST body for the #3069 truncate-precapture endpoint.

    ``interaction_id`` is the row the starter clicked "start from here" on — every
    pre-scene-captured pose before it (oldest-first) gets detached.
    """

    interaction_id = serializers.IntegerField()


class SceneScenarioLastDeedSerializer(serializers.Serializer):
    """The GM scenario view's most recent deed - ``{option_key, outcome_name}`` (#3565)."""

    option_key = serializers.CharField()
    outcome_name = serializers.CharField(allow_null=True)


class SceneScenarioGMSerializer(serializers.Serializer):
    """The GM-only scenario view: current node, every ballot, the last deed (#3565).

    Mirror of ``world.scenes.scenario_services._gm_payload``'s dict shape - staff or
    viewers with standing on the running story only (see
    ``world.scenes.scenario_services.build_scene_scenario_payload``).
    """

    node_key = serializers.CharField(allow_blank=True)
    flavor_text = serializers.CharField(allow_blank=True)
    conflict_mode = serializers.CharField(allow_blank=True)
    phase = serializers.CharField()
    is_paused = serializers.BooleanField()
    ballots = GroupBallotStateSerializer(many=True)
    last_deed = serializers.SerializerMethodField()
    beat_outcome = serializers.CharField()
    beat_outcome_key = serializers.CharField(allow_blank=True)

    @extend_schema_field(SceneScenarioLastDeedSerializer(allow_null=True))
    def get_last_deed(self, obj: dict) -> dict | None:
        return obj["last_deed"] if isinstance(obj, dict) else obj.last_deed


class SceneScenarioSerializer(serializers.Serializer):
    """Mirror of ``world.scenes.scenario_services.build_scene_scenario_payload`` (#3565).

    ``group_beat``/``gm`` use ``SerializerMethodField`` because DRF nested
    ``to_representation`` rejects None (see ``GroupBeatResultSerializer``).
    """

    instance_id = serializers.IntegerField(allow_null=True)
    is_paused = serializers.BooleanField()
    viewer_is_participant = serializers.BooleanField()
    group_beat = serializers.SerializerMethodField()
    gm = serializers.SerializerMethodField()

    @extend_schema_field(GroupBeatResultSerializer(allow_null=True))
    def get_group_beat(self, obj: dict) -> dict | None:
        result = obj["group_beat"] if isinstance(obj, dict) else obj.group_beat
        return GroupBeatResultSerializer(result).data if result is not None else None

    @extend_schema_field(SceneScenarioGMSerializer(allow_null=True))
    def get_gm(self, obj: dict) -> dict | None:
        gm = obj["gm"] if isinstance(obj, dict) else obj.gm
        return SceneScenarioGMSerializer(gm).data if gm is not None else None

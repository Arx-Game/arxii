import re as _re

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from world.scenes.constants import InteractionMode, PoseKind
from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import (
    Interaction,
    InteractionAction,
    InteractionFavorite,
    InteractionReaction,
    Persona,
    ReactionEmoji,
    Scene,
)
from world.scenes.place_models import InteractionReceiver
from world.scenes.types import PersonaPayload, ReactionAggregation

_MAX_POSE_LENGTH = 10_000

_DANGEROUS_LINK_RE = _re.compile(
    r"\[[^\]]*\]\((?!https?://)",
    _re.IGNORECASE,
)


class InlineActionInteractionSerializer(serializers.ModelSerializer):
    """Minimal serializer for an ACTION-mode Interaction embedded in an action-link chip."""

    class Meta:
        model = Interaction
        fields = ["id", "content", "mode", "timestamp"]


class InteractionActionLinkSerializer(serializers.ModelSerializer):
    """Serializes the InteractionAction bridge for the action_links field on a POSE."""

    action_interaction = InlineActionInteractionSerializer(read_only=True)
    has_critical_effect = serializers.SerializerMethodField()

    class Meta:
        model = InteractionAction
        fields = ["id", "ordering", "action_interaction", "has_critical_effect"]

    def get_has_critical_effect(self, obj: InteractionAction) -> bool:
        """Cheap critical signal for first-paint auto-expand (#996).

        ``True`` when this action's linked ``CombatRoundAction`` targeted an
        opponent that is now ``DEFEATED`` — the dominant load-bearing outcome the
        detail panel highlights. Reads ONLY prefetched data (the linked action's
        ``cached_round_actions`` + ``focused_opponent_target``); no condition or
        vitals queries, so it stays N+1-safe. The prefetch is set up in
        ``interaction_views`` as
        ``action_links__action_interaction__combat_round_actions`` with
        ``to_attr="cached_round_actions"`` and ``focused_opponent_target``
        select_related, so reading ``cached_round_actions`` never queries.
        """
        from world.combat.constants import OpponentStatus  # noqa: PLC0415

        action_interaction = obj.action_interaction
        if action_interaction is None:
            return False
        # cached_round_actions is a Prefetch(to_attr=...) attribute set by the
        # interaction_views queryset; getattr with a default keeps serialization
        # safe if this serializer is ever used without that prefetch.
        round_actions = getattr(action_interaction, "cached_round_actions", [])  # noqa: GETATTR_LITERAL
        for round_action in round_actions:
            opponent = round_action.focused_opponent_target
            if opponent is not None and opponent.status == OpponentStatus.DEFEATED:
                return True
        return False


class InteractionReceiverSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)
    persona_id = serializers.IntegerField(source="persona.id", read_only=True)

    class Meta:
        model = InteractionReceiver
        fields = ["id", "persona_name", "persona_id"]


class InteractionListSerializer(serializers.ModelSerializer):
    persona = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()
    reaction_windows = serializers.SerializerMethodField()
    receiver_persona_ids = serializers.SerializerMethodField()
    place_name = serializers.SerializerMethodField()
    target_persona_ids = serializers.SerializerMethodField()
    action_links = InteractionActionLinkSerializer(
        many=True,
        read_only=True,
        source="cached_action_links",
    )
    dramatic_moment_tags = serializers.SerializerMethodField()
    endorsee_sheet_id = serializers.IntegerField(
        source="persona.character_sheet_id", read_only=True
    )
    endorsable_resonances = serializers.SerializerMethodField()
    pose_endorsers = serializers.SerializerMethodField()
    my_pose_endorsement = serializers.SerializerMethodField()
    entry_endorsers = serializers.SerializerMethodField()
    entry_endorsed_by_me = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = [
            "id",
            "persona",
            "scene",
            "place",
            "content",
            "mode",
            "visibility",
            "timestamp",
            "pose_kind",
            "is_muted",
            "endorsee_sheet_id",
            "is_favorited",
            "reactions",
            "reaction_windows",
            "receiver_persona_ids",
            "place_name",
            "target_persona_ids",
            "action_links",
            "dramatic_moment_tags",
            "endorsable_resonances",
            "pose_endorsers",
            "my_pose_endorsement",
            "entry_endorsers",
            "entry_endorsed_by_me",
        ]

    def get_persona(self, obj: Interaction) -> PersonaPayload:
        # Per-viewer name resolution (#1109): own faces and named-public faces render real;
        # discovered anonymous faces reveal "<mask> (<real>)"; undiscovered anonymous faces
        # render a composed sdesc. Resolved once for the whole page (see _persona_display_map).
        name, _is_discovered = self._persona_display_map().get(
            obj.persona_id, (obj.persona.name, False)
        )
        return PersonaPayload(
            id=obj.persona_id,
            name=name,
            thumbnail_url=obj.persona.thumbnail_url or "",
        )

    def _persona_display_map(self) -> dict[int, tuple[str, bool]]:
        """Cache the page's persona-display resolution on the shared context (O(1) queries)."""
        cached = self.context.get("_persona_display_map")
        if cached is not None:
            return cached
        from world.scenes.persona_display import build_persona_display_map  # noqa: PLC0415

        if self.parent is not None:
            rows = list(self.parent.instance or [])
        elif self.instance is not None:
            rows = [self.instance]
        else:
            rows = []
        display_map = build_persona_display_map(
            [row.persona for row in rows],
            viewer_persona_ids=set(self.context.get("persona_ids", set())),
            viewer_sheet_ids=set(self.context.get("viewer_sheet_ids", set())),
            is_staff=bool(self.context.get("is_staff", False)),
        )
        self.context["_persona_display_map"] = display_map
        return display_map

    def get_receiver_persona_ids(self, obj: Interaction) -> list[int]:
        return [r.persona_id for r in obj.cached_receivers]

    def get_place_name(self, obj: Interaction) -> str | None:
        return obj.place.name if obj.place_id else None

    def get_target_persona_ids(self, obj: Interaction) -> list[int]:
        return [p.pk for p in obj.cached_target_personas]

    def _muted_persona_ids(self) -> set[int]:
        """Lazily compute muted persona IDs, cached on the serializer context (#2087)."""
        cache_key = "_muted_persona_ids_cache"
        if cache_key not in self.context:
            from world.scenes.mute_services import muted_persona_ids_for_viewer  # noqa: PLC0415

            request = self.context.get("request")
            user = request.user if request is not None else None
            if user and getattr(user, "is_authenticated", False):  # noqa: GETATTR_LITERAL
                self.context[cache_key] = muted_persona_ids_for_viewer(viewer_account=user)
            else:
                self.context[cache_key] = set()
        return self.context[cache_key]

    def get_is_muted(self, obj: Interaction) -> bool:
        """True when this interaction's persona is muted by the viewer (#2087).

        Muted interactions stay in the feed with content blanked — the action
        still shows, just without the text. The frontend renders a "N hidden"
        divider for consecutive muted rows.
        """
        return obj.persona_id in self._muted_persona_ids()

    def get_content(self, obj: Interaction) -> str:
        """The interaction's content, blanked when the persona is muted (#2087).

        Muted personas' interactions stay visible (so the scene stays coherent)
        but their text is redacted. The viewer can click-to-expand to fetch the
        full content via the detail endpoint.
        """
        if obj.persona_id in self._muted_persona_ids():
            return ""
        return obj.content

    def get_is_favorited(self, obj: Interaction) -> bool:
        roster_entry_ids: set[int] = self.context.get("roster_entry_ids", set())
        if not roster_entry_ids:
            return False
        return any(f.roster_entry_id in roster_entry_ids for f in obj.cached_favorites)

    def get_reaction_windows(self, obj: Interaction) -> list[dict]:
        """Reaction windows on this event (#904): choices, reactions, my_reaction.

        ``my_reaction`` is per-viewer and flows through serializer context
        (``persona_ids``) — never a Prefetch(to_attr) on the shared instance.
        """
        from world.scenes.reaction_services import get_reaction_kind  # noqa: PLC0415

        windows = getattr(obj, "cached_reaction_windows", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if windows is None:
            windows = list(obj.reaction_windows.all())
        if not windows:
            return []

        viewer_persona_ids: set[int] = self.context.get("persona_ids", set())
        payloads: list[dict] = []
        for window in windows:
            rows = getattr(window, "cached_reaction_rows", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
            if rows is None:
                rows = list(window.reactions.select_related("reactor_persona"))
            try:
                config = get_reaction_kind(window.kind)
            except DjangoValidationError:
                continue  # consumer app gone; render nothing rather than 500
            my_reaction = next(
                (r.choice for r in rows if r.reactor_persona_id in viewer_persona_ids),
                None,
            )
            if config.public:
                reactions = [
                    {
                        "persona_id": r.reactor_persona_id,
                        "persona_name": r.reactor_persona.name,
                        "choice": r.choice,
                    }
                    for r in rows
                ]
            else:
                reactions = []
            counts: dict[str, int] = {}
            for r in rows:
                counts[r.choice] = counts.get(r.choice, 0) + 1
            payloads.append(
                {
                    "id": window.pk,
                    "kind": window.kind,
                    "is_open": window.is_open,
                    "public": config.public,
                    "choices": [
                        {"slug": c.slug, "label": c.label} for c in config.choices_for(window)
                    ],
                    "reactions": reactions,
                    "counts": counts,
                    "my_reaction": my_reaction,
                }
            )
        return payloads

    def get_reactions(self, obj: Interaction) -> list[ReactionAggregation]:
        """Aggregate emoji counts with reacted-by-current-user flag."""
        reaction_list = obj.cached_reactions

        counts: dict[str, int] = {}
        user_reacted: set[str] = set()
        request = self.context.get("request")
        user_id = request.user.pk if request and request.user.is_authenticated else None

        for reaction in reaction_list:
            emoji = reaction.emoji
            counts[emoji] = counts.get(emoji, 0) + 1
            if reaction.account_id == user_id:
                user_reacted.add(emoji)

        return [
            ReactionAggregation(emoji=emoji, count=count, reacted=emoji in user_reacted)
            for emoji, count in counts.items()
        ]

    def get_dramatic_moment_tags(self, obj: Interaction) -> list[dict]:
        tags = getattr(obj, "cached_dramatic_moment_tags", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if tags is None:
            return []
        return [
            {"moment_type_label": t.moment_type.label, "character_sheet_id": t.character_sheet_id}
            for t in tags
        ]

    def get_endorsable_resonances(self, obj: Interaction) -> list[dict]:
        """List of resonances claimed by the endorsee (pose author).

        Reads from the prefetched ``persona__character_sheet__resonances``
        path (set up in ``interaction_views.get_queryset``) via the
        ``cached_resonances`` to_attr. Falls back to a live query if the attr
        is absent (e.g. serializer used outside the view's queryset pipeline).
        """
        sheet = obj.persona.character_sheet
        if sheet is None:
            return []
        resonances = getattr(sheet, "cached_resonances", None)  # noqa: GETATTR_LITERAL
        if resonances is None:
            resonances = list(sheet.resonances.select_related("resonance"))
        return [{"id": cr.resonance_id, "name": cr.resonance.name} for cr in resonances]

    def get_pose_endorsers(self, obj: Interaction) -> list[dict]:
        """List of peers who endorsed this pose, with persona info.

        Reads ``obj.cached_endorsements`` (Prefetch(to_attr=...) set by the
        view queryset). Each endorser's primary persona is pre-loaded via
        ``cached_primary_persona`` (another nested Prefetch).
        """
        out = []
        for e in getattr(obj, "cached_endorsements", []):  # noqa: GETATTR_LITERAL
            persona = next(iter(e.endorser_sheet.cached_primary_persona), None)
            if persona is None:
                continue
            out.append(
                {
                    "persona_id": persona.pk,
                    "persona_name": persona.name,
                    "thumbnail_url": persona.thumbnail_url or "",
                    "resonance_id": e.resonance_id,
                }
            )
        return out

    def get_my_pose_endorsement(self, obj: Interaction) -> dict | None:
        """Return the viewer's own endorsement for this pose, or None.

        Checks ``character_sheet_ids`` from context (viewer's sheet PKs) against
        each cached endorsement's ``endorser_sheet_id``.
        """
        sheet_ids: set[int] = self.context.get("character_sheet_ids", set())
        for e in getattr(obj, "cached_endorsements", []):  # noqa: GETATTR_LITERAL
            if e.endorser_sheet_id in sheet_ids:
                return {
                    "id": e.pk,
                    "resonance_id": e.resonance_id,
                    "settled": e.settled_at is not None,
                }
        return None

    def _entry_rows(self, obj: Interaction) -> list:
        """Return scene-entry endorsement rows for ENTRY poses only."""
        if obj.pose_kind != PoseKind.ENTRY:
            return []
        sheet_id = obj.persona.character_sheet_id
        return self.context.get("scene_entry_endorsements", {}).get(sheet_id, [])

    def get_entry_endorsers(self, obj: Interaction) -> list[dict]:
        """List of peers who gave this character a scene-entry endorsement.

        Only non-empty for ENTRY poses. Reads ``scene_entry_endorsements`` from
        context (populated by the view's ``get_serializer_context``).
        """
        out = []
        for r in self._entry_rows(obj):
            persona = next(iter(r.endorser_sheet.cached_primary_persona), None)
            if persona is None:
                continue
            out.append(
                {
                    "persona_id": persona.pk,
                    "persona_name": persona.name,
                    "thumbnail_url": persona.thumbnail_url or "",
                    "resonance_id": r.resonance_id,
                }
            )
        return out

    def get_entry_endorsed_by_me(self, obj: Interaction) -> bool:
        """True when the viewer has given this character a scene-entry endorsement."""
        sheet_ids: set[int] = self.context.get("character_sheet_ids", set())
        return any(r.endorser_sheet_id in sheet_ids for r in self._entry_rows(obj))


class InteractionDetailSerializer(InteractionListSerializer):
    receivers = InteractionReceiverSerializer(
        many=True,
        read_only=True,
        source="cached_receivers",
    )

    class Meta(InteractionListSerializer.Meta):
        fields = [
            *InteractionListSerializer.Meta.fields,
            "receivers",
        ]

    def get_content(self, obj: Interaction) -> str:
        """Detail endpoint always returns full content (#2087 — opt-in backfill).

        The list endpoint blanks content for muted personas; the detail endpoint
        is the reveal path — a viewer who clicks 'expand' fetches the full content here.
        """
        return obj.content


class InteractionFavoriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionFavorite
        fields = ["id", "interaction", "created_at"]
        read_only_fields = ["created_at"]


class InteractionReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionReaction
        fields = ["id", "interaction", "emoji", "created_at"]
        read_only_fields = ["created_at"]


class ReactionEmojiSerializer(serializers.ModelSerializer):
    """Read serializer for the active reaction-emoji catalog (#1699)."""

    class Meta:
        model = ReactionEmoji
        fields = ["emoji", "valence", "sort_order"]


class PoseSubmitSerializer(serializers.Serializer):
    """Write serializer for submitting a POSE-mode Interaction from the web frontend.

    Validates persona ownership and action_link_ids integrity before the view
    creates the Interaction and wires the auto-link service.
    """

    persona_id = serializers.IntegerField(
        help_text="PK of the Persona the requesting user is posing as.",
    )
    scene_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="PK of the Scene this pose belongs to. Null for scene-less poses.",
    )
    content = serializers.CharField(
        help_text="The written text of the pose.",
    )
    action_link_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text=(
            "Optional explicit action-link override. When provided, auto-link "
            "is skipped and InteractionAction bridges are created for exactly "
            "these ACTION Interaction ids in order. An empty list explicitly "
            "requests no links (caller opted out of auto-link this pose)."
        ),
    )

    pose_kind = serializers.ChoiceField(
        choices=PoseKind.choices,
        required=False,
        default=PoseKind.STANDARD,
        help_text=(
            "Classifies the pose (Spec C). ENTRY opens a Make-an-Entrance "
            "reaction window (#904) when the pose belongs to a scene."
        ),
    )

    def validate_persona_id(self, value: int) -> int:
        """Confirm the persona exists and belongs to the requesting user."""
        request = self.context.get("request")
        if request is None:
            msg = "Request context unavailable."
            raise serializers.ValidationError(msg)
        try:
            persona = Persona.objects.get(pk=value)
        except Persona.DoesNotExist:
            msg = "Persona not found."
            raise serializers.ValidationError(msg) from None

        owned_persona_ids = get_account_personas(request)
        if persona.pk not in owned_persona_ids:
            msg = "You do not own this persona."
            raise serializers.ValidationError(msg)

        return value

    def validate_scene_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        if not Scene.objects.filter(pk=value).exists():
            msg = "Scene not found."
            raise serializers.ValidationError(msg)
        return value

    def validate_content(self, value: str) -> str:
        if not value.strip():
            msg = "Pose content cannot be blank."
            raise serializers.ValidationError(msg)
        if len(value) > _MAX_POSE_LENGTH:
            msg = f"Pose content exceeds the maximum length of {_MAX_POSE_LENGTH} characters."
            raise serializers.ValidationError(msg)
        if "\x00" in value:
            msg = "Pose content contains invalid characters."
            raise serializers.ValidationError(msg)
        if _DANGEROUS_LINK_RE.search(value):
            msg = "Links must use http:// or https:// URLs."
            raise serializers.ValidationError(msg)
        return value

    def validate_action_link_ids(self, value: list[int]) -> list[int]:
        """Confirm all supplied IDs reference ACTION-mode Interactions."""
        if not value:
            return value
        valid_pks = set(
            Interaction.objects.filter(
                pk__in=value,
                mode=InteractionMode.ACTION,
            ).values_list("pk", flat=True)
        )
        invalid = set(value) - valid_pks
        if invalid:
            msg = f"These IDs are not valid ACTION-mode Interactions: {sorted(invalid)}"
            raise serializers.ValidationError(msg)
        return value

    def validate(self, attrs: dict) -> dict:
        """Cross-field: persona must own the action_link_ids (same character)."""
        action_link_ids = attrs.get("action_link_ids")
        if not action_link_ids:
            return attrs

        persona_id = attrs.get("persona_id")
        if persona_id is None:
            return attrs  # persona_id error will be surfaced by its own validator

        try:
            persona = Persona.objects.get(pk=persona_id)
        except Persona.DoesNotExist:
            return attrs  # surfaced by validate_persona_id

        # All action interactions must belong to the same persona as this pose.
        wrong_persona = Interaction.objects.filter(
            pk__in=action_link_ids,
        ).exclude(persona=persona)
        if wrong_persona.exists():
            raise serializers.ValidationError(
                {
                    "action_link_ids": (
                        "All action_link_ids must belong to the same persona as the pose."
                    )
                }
            )
        return attrs

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
    Scene,
)
from world.scenes.place_models import InteractionReceiver
from world.scenes.types import PersonaPayload, ReactionAggregation


class InlineActionInteractionSerializer(serializers.ModelSerializer):
    """Minimal serializer for an ACTION-mode Interaction embedded in an action-link chip."""

    class Meta:
        model = Interaction
        fields = ["id", "content", "mode", "timestamp"]


class InteractionActionLinkSerializer(serializers.ModelSerializer):
    """Serializes the InteractionAction bridge for the action_links field on a POSE."""

    action_interaction = InlineActionInteractionSerializer(read_only=True)

    class Meta:
        model = InteractionAction
        fields = ["id", "ordering", "action_interaction"]


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
            "is_favorited",
            "reactions",
            "reaction_windows",
            "receiver_persona_ids",
            "place_name",
            "target_persona_ids",
            "action_links",
        ]

    def get_persona(self, obj: Interaction) -> PersonaPayload:
        p = obj.persona
        return PersonaPayload(
            id=p.pk,
            name=p.name,
            thumbnail_url=p.thumbnail_url or "",
        )

    def get_receiver_persona_ids(self, obj: Interaction) -> list[int]:
        return [r.persona_id for r in obj.cached_receivers]

    def get_place_name(self, obj: Interaction) -> str | None:
        return obj.place.name if obj.place_id else None

    def get_target_persona_ids(self, obj: Interaction) -> list[int]:
        return [p.pk for p in obj.cached_target_personas]

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

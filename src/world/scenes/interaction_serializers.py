from rest_framework import serializers
from rest_framework.request import Request

from world.scenes.interaction_permissions import get_account_roster_entries
from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    InteractionReaction,
)
from world.scenes.place_models import InteractionReceiver


class InteractionReceiverSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)
    persona_id = serializers.IntegerField(source="persona.id", read_only=True)

    class Meta:
        model = InteractionReceiver
        fields = ["id", "persona_name", "persona_id"]


class InteractionListSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)
    target_persona_names = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = [
            "id",
            "persona_name",
            "scene",
            "place",
            "content",
            "mode",
            "visibility",
            "timestamp",
            "target_persona_names",
            "is_favorited",
            "reactions",
        ]

    def get_target_persona_names(self, obj: Interaction) -> list[str]:
        return [p.name for p in obj.cached_target_personas]

    def get_is_favorited(self, obj: Interaction) -> bool:
        request: Request | None = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        roster_entries = get_account_roster_entries(request)
        if not roster_entries:
            return False
        roster_entry_ids = {re.pk for re in roster_entries}
        return any(f.roster_entry_id in roster_entry_ids for f in obj.cached_favorites)

    def get_reactions(self, obj: Interaction) -> list[dict[str, object]]:
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
            {"emoji": emoji, "count": count, "reacted": emoji in user_reacted}
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

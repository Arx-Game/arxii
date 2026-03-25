from rest_framework import serializers

from world.scenes.models import (
    Interaction,
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
    persona = serializers.SerializerMethodField()
    target_persona_names = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()

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
            "target_persona_names",
            "is_favorited",
            "reactions",
        ]

    def get_persona(self, obj: Interaction) -> dict[str, object]:
        p = obj.persona
        return {
            "id": p.pk,
            "name": p.name,
            "thumbnail_url": p.thumbnail_url or "",
        }

    def get_target_persona_names(self, obj: Interaction) -> list[str]:
        return [p.name for p in obj.cached_target_personas]

    def get_is_favorited(self, obj: Interaction) -> bool:
        roster_entry_ids: set[int] = self.context.get("roster_entry_ids", set())
        if not roster_entry_ids:
            return False
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

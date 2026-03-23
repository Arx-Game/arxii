from rest_framework import serializers
from rest_framework.request import Request

from world.scenes.interaction_permissions import get_account_roster_entries
from world.scenes.models import Interaction, InteractionFavorite
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

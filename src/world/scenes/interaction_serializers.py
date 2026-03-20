from rest_framework import serializers
from rest_framework.request import Request

from world.scenes.interaction_permissions import get_account_roster_entries
from world.scenes.models import Interaction, InteractionAudience, InteractionFavorite


class InteractionAudienceSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True, default=None)
    persona_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = InteractionAudience
        fields = ["id", "persona_name", "persona_id"]


class InteractionListSerializer(serializers.ModelSerializer):
    character_name = serializers.CharField(source="roster_entry.character.db_key", read_only=True)
    persona_name = serializers.CharField(source="persona.name", read_only=True, default=None)
    target_persona_names = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = [
            "id",
            "character_name",
            "persona_name",
            "location",
            "scene",
            "content",
            "mode",
            "visibility",
            "timestamp",
            "sequence_number",
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
    audience = InteractionAudienceSerializer(
        many=True,
        read_only=True,
        source="cached_audience",
    )

    class Meta(InteractionListSerializer.Meta):
        fields = [
            *InteractionListSerializer.Meta.fields,
            "audience",
        ]


class InteractionFavoriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionFavorite
        fields = ["id", "interaction", "created_at"]
        read_only_fields = ["created_at"]

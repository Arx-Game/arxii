from django.db.models import Q, QuerySet
import django_filters

from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction, InteractionFavorite, InteractionReaction

WHISPER_MODE = InteractionMode.WHISPER
OOC_MODES = ("ooc", "system")
TABLETALK_MODE = "tt"
KIND_WHISPER = "whisper"
KIND_PLACE = "place"
KIND_SCENE_OOC = "scene_ooc"
KIND_CHANNEL = "channel"
KIND_ROOM = "room"


class InteractionFilter(django_filters.FilterSet):
    persona = django_filters.NumberFilter(field_name="persona_id")
    scene = django_filters.NumberFilter(field_name="scene_id")
    mode = django_filters.CharFilter(field_name="mode")
    visibility = django_filters.CharFilter(field_name="visibility")
    since = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")
    target_persona = django_filters.NumberFilter(
        field_name="target_personas",
        lookup_expr="exact",
    )
    kind = django_filters.CharFilter(method="filter_kind")
    participant = django_filters.NumberFilter(method="filter_participant")
    without_pose_link = django_filters.BooleanFilter(
        method="filter_without_pose_link",
        label="Exclude interactions that are already linked to a POSE via InteractionAction.",
    )

    def filter_kind(
        self,
        queryset: QuerySet[Interaction],
        name: str,  # noqa: ARG002
        value: str,
    ) -> QuerySet[Interaction]:
        """Mirror `play_views._conversation()`'s kind derivation as a queryset filter.

        Kept in lockstep with that function deliberately -- `kind` is not a
        stored column (#3759 ledger).
        """
        if value == KIND_WHISPER:
            return queryset.filter(mode=WHISPER_MODE)
        if value == KIND_PLACE:
            return queryset.filter(place__isnull=False)
        if value == KIND_SCENE_OOC:
            return queryset.filter(mode__in=OOC_MODES)
        if value == KIND_CHANNEL:
            return queryset.filter(mode=TABLETALK_MODE)
        if value == KIND_ROOM:
            excluded_modes = {WHISPER_MODE, TABLETALK_MODE} | set(OOC_MODES)
            return queryset.filter(
                place__isnull=True,
                mode__in=[m for m in InteractionMode.values if m not in excluded_modes],
            )
        return queryset

    def filter_participant(
        self,
        queryset: QuerySet[Interaction],
        name: str,  # noqa: ARG002
        value: int,
    ) -> QuerySet[Interaction]:
        """Rows where `value` wrote OR received the interaction."""
        return queryset.filter(Q(persona_id=value) | Q(receivers__persona_id=value)).distinct()

    def filter_without_pose_link(
        self,
        queryset: QuerySet[Interaction],
        name: str,  # noqa: ARG002
        value: bool,
    ) -> QuerySet[Interaction]:
        """When true, exclude ACTION interactions already linked to a POSE."""
        if value:
            return queryset.filter(pose_links__isnull=True)
        return queryset

    class Meta:
        model = Interaction
        fields = ["persona", "scene", "mode", "visibility"]


class InteractionFavoriteFilter(django_filters.FilterSet):
    interaction = django_filters.NumberFilter(field_name="interaction_id")

    class Meta:
        model = InteractionFavorite
        fields = ["interaction"]


class InteractionReactionFilter(django_filters.FilterSet):
    interaction = django_filters.NumberFilter(field_name="interaction_id")

    class Meta:
        model = InteractionReaction
        fields = ["interaction"]

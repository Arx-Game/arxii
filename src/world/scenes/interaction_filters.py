from django.db.models import Exists, OuterRef, Q, QuerySet
import django_filters

from world.scenes.constants import (
    KIND_CHANNEL,
    KIND_PLACE,
    KIND_ROOM,
    KIND_SCENE_OOC,
    KIND_WHISPER,
    OOC_MODES,
    TABLETALK_MODE,
    WHISPER_MODE,
)
from world.scenes.models import (
    Interaction,
    InteractionFavorite,
    InteractionReaction,
    InteractionReceiver,
)


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
        stored column (#3759 ledger). `_conversation()`'s precedence is an
        if/elif chain checked in exactly this order: whisper (mode==WHISPER_MODE
        AND has receivers) > place (place is set) > scene_ooc (mode in OOC_MODES)
        > channel (mode==TABLETALK_MODE) > room (everything else). Each branch
        below is therefore the FULL exclusion of every higher-precedence branch,
        not just a same-tier positive match -- e.g. a whisper-mode row that also
        has `place` set is classified "whisper" by `_conversation()` (whisper is
        checked first), so the `place` branch here must exclude it too, or the two
        functions would disagree on that row's kind.

        `scene_ooc` and `channel` are currently unreachable in practice --
        `InteractionMode` has no "ooc"/"system"/"tt" value yet (#3299 is not
        delivered) -- but the exclusions are still written out for when it does.
        """
        annotated = queryset.annotate(
            has_receivers=Exists(InteractionReceiver.objects.filter(interaction=OuterRef("pk")))
        )
        is_whisper = Q(mode=WHISPER_MODE, has_receivers=True)
        if value == KIND_WHISPER:
            return annotated.filter(is_whisper)
        if value == KIND_PLACE:
            return annotated.filter(place__isnull=False).exclude(is_whisper)
        if value == KIND_SCENE_OOC:
            return annotated.filter(mode__in=OOC_MODES, place__isnull=True).exclude(is_whisper)
        if value == KIND_CHANNEL:
            return annotated.filter(mode=TABLETALK_MODE, place__isnull=True).exclude(is_whisper)
        if value == KIND_ROOM:
            excluded_modes = {TABLETALK_MODE} | set(OOC_MODES)
            return (
                annotated.filter(place__isnull=True)
                .exclude(mode__in=excluded_modes)
                .exclude(is_whisper)
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

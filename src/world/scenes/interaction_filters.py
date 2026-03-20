import django_filters

from world.scenes.models import Interaction, InteractionFavorite


class InteractionFilter(django_filters.FilterSet):
    roster_entry = django_filters.NumberFilter(field_name="roster_entry_id")
    character = django_filters.NumberFilter(
        field_name="roster_entry__character_id",
        help_text="Filter by character ID (resolved through roster_entry).",
    )
    location = django_filters.NumberFilter(field_name="location_id")
    scene = django_filters.NumberFilter(field_name="scene_id")
    mode = django_filters.CharFilter(field_name="mode")
    visibility = django_filters.CharFilter(field_name="visibility")
    since = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")
    target_persona = django_filters.NumberFilter(field_name="target_personas")

    class Meta:
        model = Interaction
        fields = [
            "roster_entry",
            "character",
            "location",
            "scene",
            "mode",
            "visibility",
            "since",
            "until",
            "target_persona",
        ]


class InteractionFavoriteFilter(django_filters.FilterSet):
    interaction = django_filters.NumberFilter(field_name="interaction_id")

    class Meta:
        model = InteractionFavorite
        fields = ["interaction"]

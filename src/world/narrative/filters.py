import django_filters

from world.narrative.constants import NarrativeCategory
from world.narrative.models import Gemit, NarrativeMessageDelivery, UserStoryMute


class NarrativeMessageDeliveryFilter(django_filters.FilterSet):
    """Filter deliveries by message category, related story, or acknowledgement state."""

    category = django_filters.ChoiceFilter(
        choices=NarrativeCategory.choices, field_name="message__category"
    )
    related_story = django_filters.NumberFilter(field_name="message__related_story_id")
    acknowledged = django_filters.BooleanFilter(
        field_name="acknowledged_at",
        lookup_expr="isnull",
        exclude=True,
    )

    class Meta:
        model = NarrativeMessageDelivery
        fields = ["category", "related_story", "acknowledged"]


class GemitFilter(django_filters.FilterSet):
    """Filter Gemits by related era or story."""

    related_era = django_filters.NumberFilter(field_name="related_era_id")
    related_story = django_filters.NumberFilter(field_name="related_story_id")
    sender_account = django_filters.NumberFilter(field_name="sender_account_id")

    class Meta:
        model = Gemit
        fields = ["related_era", "related_story", "sender_account"]


class UserStoryMuteFilter(django_filters.FilterSet):
    """Filter UserStoryMutes by story (account is always scoped to request.user in view)."""

    story = django_filters.NumberFilter(field_name="story_id")

    class Meta:
        model = UserStoryMute
        fields = ["story"]

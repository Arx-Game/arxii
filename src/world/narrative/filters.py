import django_filters

from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery


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

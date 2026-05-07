"""FilterSet classes for the relationships API."""

from django.db.models import Q, QuerySet
import django_filters

from world.relationships.models import RelationshipCapstone


class RelationshipCapstoneFilter(django_filters.FilterSet):
    """Filter capstones by optional other-character involvement.

    Accepts ``?other_character_sheet_id=<pk>`` and restricts the queryset to
    capstones whose parent ``CharacterRelationship`` involves that character
    sheet on either the source or target side.
    """

    other_character_sheet_id = django_filters.NumberFilter(method="filter_by_other_character")

    class Meta:
        model = RelationshipCapstone
        fields = ["other_character_sheet_id"]

    def filter_by_other_character(
        self,
        queryset: QuerySet[RelationshipCapstone],
        name: str,
        value: int,
    ) -> QuerySet[RelationshipCapstone]:
        """Return capstones whose relationship involves the given character sheet."""
        return queryset.filter(Q(relationship__source_id=value) | Q(relationship__target_id=value))

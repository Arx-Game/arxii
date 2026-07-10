"""FilterSet classes for the relationships API."""

from django.db.models import Q, QuerySet
import django_filters

from world.relationships.models import RelationshipCapstone, RelationshipUpdate


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


class RelationshipUpdateFilter(django_filters.FilterSet):
    """Filter the writeup-commend list by relationship/track, or narrow to one subject.

    ``?subject_character=<CharacterSheet pk>`` narrows
    ``RelationshipUpdateViewSet``'s already tenure-scoped queryset (see its
    ``get_queryset``) down to writeups whose parent relationship's subject
    (``target``) is that specific sheet. This exists so an account with
    several owned characters can request "just this one sheet's writeups"
    instead of every owned character's — it can only *narrow* the result,
    never widen it, since the base queryset is already restricted to the
    requester's own tenure-owned subject characters.
    """

    subject_character = django_filters.NumberFilter(method="filter_by_subject_character")

    class Meta:
        model = RelationshipUpdate
        fields = ["relationship", "track", "subject_character"]

    def filter_by_subject_character(
        self,
        queryset: QuerySet[RelationshipUpdate],
        name: str,
        value: int,
    ) -> QuerySet[RelationshipUpdate]:
        """Return writeups whose relationship's subject (target) is the given sheet."""
        return queryset.filter(relationship__target_id=value)

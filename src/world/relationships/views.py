"""API views for the relationships system (#3957)."""

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.mechanics.models import ModifierTarget
from world.relationships.filters import RelationshipCapstoneFilter
from world.relationships.models import RelationshipCapstone, RelationshipCondition
from world.relationships.serializers import (
    RelationshipCapstoneSerializer,
    RelationshipConditionSerializer,
)


class RelationshipConditionViewSet(ReadOnlyModelViewSet):
    """List and retrieve relationship conditions."""

    queryset = RelationshipCondition.objects.prefetch_related(
        Prefetch(
            "gates_modifiers",
            queryset=ModifierTarget.objects.all(),
            to_attr="cached_gates_modifiers",
        ),
    )
    serializer_class = RelationshipConditionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class RelationshipCapstoneViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet exposing the caller's RelationshipCapstone rows (#3957).

    Used by the frontend to populate the Soul Tether ritual perform form's
    capstone picker. The ``?other_character_sheet_id=`` filter narrows to
    capstones whose parent relationship involves a specific target character.
    """

    serializer_class = RelationshipCapstoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RelationshipCapstoneFilter

    def get_queryset(self):  # type: ignore[override]
        """Return capstones authored on relationships the caller's sheets source.

        Newest first via the model's own ``Meta.ordering`` — no explicit ``order_by``
        needed here.
        """
        return RelationshipCapstone.objects.filter(
            relationship__source__character__db_account=self.request.user
        ).select_related("journal_entry", "relationship")

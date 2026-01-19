"""
API views for traits system.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from world.traits.models import Trait
from world.traits.serializers import TraitSerializer


class StatDefinitionsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for primary stat definitions.

    Provides read-only access to the 9 primary stat Trait records.
    Used by the frontend character creation to display stat options.
    """

    queryset = Trait.objects.filter(trait_type="stat").order_by("name")
    serializer_class = TraitSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Only 9 stats, no pagination needed

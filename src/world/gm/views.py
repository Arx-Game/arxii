"""ViewSets for the GM system."""

from __future__ import annotations

import builtins

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from world.gm.filters import GMApplicationFilter
from world.gm.models import GMApplication
from world.gm.serializers import (
    GMApplicationCreateSerializer,
    GMApplicationDetailSerializer,
)
from world.stories.pagination import StandardResultsSetPagination


class GMApplicationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """GM application management.

    Create: any authenticated player.
    List/Retrieve/Update: staff only.
    """

    queryset = GMApplication.objects.select_related("account", "reviewed_by")
    filterset_class = GMApplicationFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return GMApplicationCreateSerializer
        return GMApplicationDetailSerializer

    def get_permissions(self) -> builtins.list:
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAdminUser()]

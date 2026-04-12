"""ViewSets for the GM system."""

from __future__ import annotations

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from world.gm.constants import GMApplicationStatus
from world.gm.filters import GMApplicationFilter
from world.gm.models import GMApplication, GMProfile
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

    queryset = GMApplication.objects.select_related("account", "reviewed_by").order_by(
        "-created_at"
    )
    filterset_class = GMApplicationFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return GMApplicationCreateSerializer
        return GMApplicationDetailSerializer

    def get_permissions(self) -> list:
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAdminUser()]

    def perform_update(self, serializer: serializers.Serializer) -> None:
        # Fetch the pre-update status from the DB to avoid relying on
        # DRF's internal timing of when instance mutation happens.
        previous_status = GMApplication.objects.values_list("status", flat=True).get(
            pk=serializer.instance.pk
        )
        instance = serializer.save(reviewed_by=self.request.user)
        if (
            instance.status == GMApplicationStatus.APPROVED
            and previous_status != GMApplicationStatus.APPROVED
        ):
            GMProfile.objects.get_or_create(
                account=instance.account,
                defaults={
                    "approved_at": timezone.now(),
                    "approved_by": self.request.user,
                },
            )

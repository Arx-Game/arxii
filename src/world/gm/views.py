"""ViewSets for the GM system."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.gm.constants import GMApplicationStatus
from world.gm.filters import (
    GMApplicationFilter,
    GMTableFilter,
    GMTableMembershipFilter,
)
from world.gm.models import (
    GMApplication,
    GMProfile,
    GMTable,
    GMTableMembership,
)
from world.gm.serializers import (
    GMApplicationCreateSerializer,
    GMApplicationDetailSerializer,
    GMTableMembershipSerializer,
    GMTableSerializer,
)
from world.gm.services import (
    archive_table,
    join_table,
    leave_table,
    transfer_ownership as transfer_ownership_service,
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


class GMTableViewSet(viewsets.ModelViewSet):
    """GM table management.

    Staff sees all tables. GMs see only their own. Archive and transfer
    ownership are staff-only lifecycle actions.
    """

    queryset = GMTable.objects.select_related("gm__account").order_by("-created_at")
    serializer_class = GMTableSerializer
    filterset_class = GMTableFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[GMTable]:
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(gm__account=user)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def archive(self, request: Request, pk: str | None = None) -> Response:
        table = self.get_object()
        archive_table(table)
        return Response(GMTableSerializer(table).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def transfer_ownership(self, request: Request, pk: str | None = None) -> Response:
        new_gm_id = request.data.get("new_gm")
        if not new_gm_id:
            return Response(
                {"new_gm": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        table = self.get_object()
        new_gm = get_object_or_404(GMProfile, pk=new_gm_id)
        transfer_ownership_service(table, new_gm)
        return Response(GMTableSerializer(table).data)


class GMTableMembershipViewSet(viewsets.ModelViewSet):
    """GM table membership management.

    Staff sees all memberships. GMs see only memberships for tables they own.
    Creation uses the join_table service to apply temporary-persona validation.
    Destroy is a soft-leave — the record remains with left_at set.
    """

    queryset = GMTableMembership.objects.select_related("table", "persona")
    serializer_class = GMTableMembershipSerializer
    filterset_class = GMTableMembershipFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[GMTableMembership]:
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(table__gm__account=user)

    def perform_create(self, serializer: serializers.Serializer) -> None:
        """Create membership via service to enforce TEMPORARY rejection.

        Idempotent: if an active membership already exists, ``join_table``
        returns it rather than creating a duplicate. The HTTP response
        will still be 201 in either case — DRF's CreateModelMixin does
        not distinguish create-vs-already-exists, and semantic correctness
        here is minor compared to keeping a single code path.
        """
        table = serializer.validated_data["table"]
        persona = serializer.validated_data["persona"]
        try:
            membership = join_table(table, persona)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        serializer.instance = membership

    def perform_destroy(self, instance: GMTableMembership) -> None:
        leave_table(instance)

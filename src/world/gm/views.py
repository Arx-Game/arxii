"""ViewSets for the GM system."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.gm.constants import GMApplicationStatus, GMTableStatus
from world.gm.filters import (
    GMApplicationFilter,
    GMTableFilter,
    GMTableMembershipFilter,
)
from world.gm.models import (
    GMApplication,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
)
from world.gm.serializers import (
    GMApplicationCreateSerializer,
    GMApplicationDetailSerializer,
    GMApplicationQueueSerializer,
    GMRosterInviteSerializer,
    GMTableMembershipSerializer,
    GMTableSerializer,
)
from world.gm.services import (
    approve_application_as_gm as approve_as_gm_service,
    archive_table,
    claim_invite as claim_invite_service,
    create_invite as create_invite_service,
    deny_application_as_gm as deny_as_gm_service,
    gm_application_queue,
    join_table,
    leave_table,
    revoke_invite as revoke_invite_service,
    transfer_ownership as transfer_ownership_service,
)
from world.roster.models.applications import RosterApplication
from world.stories.pagination import StandardResultsSetPagination


def _get_gm_or_403(user) -> GMProfile:
    """Return ``user.gm_profile`` or raise PermissionDenied.

    Centralizes the try/except that several GM views would otherwise
    duplicate. Callers should have already ensured authentication via
    ``IsAuthenticated`` permission.
    """
    try:
        return user.gm_profile
    except GMProfile.DoesNotExist as exc:
        msg = "You must be a GM to use this endpoint."
        raise PermissionDenied(msg) from exc


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


class GMRosterInviteViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """GM invites for specific roster characters.

    - create: GM only, must oversee the character
    - list/retrieve: scoped to GM's invites (staff sees all)
    - destroy: revokes (unclaimed invites only)
    """

    serializer_class = GMRosterInviteSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[GMRosterInvite]:
        qs = GMRosterInvite.objects.select_related(
            "roster_entry", "created_by__account", "claimed_by"
        ).order_by("-created_at")
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(created_by__account=user)

    def perform_create(self, serializer: serializers.Serializer) -> None:
        gm = _get_gm_or_403(self.request.user)
        try:
            invite = create_invite_service(
                gm=gm,
                roster_entry=serializer.validated_data["roster_entry"],
                is_public=serializer.validated_data.get("is_public", False),
                invited_email=serializer.validated_data.get("invited_email", ""),
                expires_at=serializer.validated_data.get("expires_at"),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc
        serializer.instance = invite

    def perform_destroy(self, instance: GMRosterInvite) -> None:
        if self.request.user.is_staff:
            if instance.is_claimed:
                from rest_framework.exceptions import (  # noqa: PLC0415
                    ValidationError as DRFValidationError,
                )

                raise DRFValidationError({"detail": "Claimed invites cannot be revoked."})
            instance.expires_at = timezone.now()
            instance.save(update_fields=["expires_at"])
            return
        gm = _get_gm_or_403(self.request.user)
        try:
            revoke_invite_service(gm=gm, invite=instance)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc


class GMApplicationQueueView(generics.ListAPIView):
    """Read-only list of pending applications for this GM's characters."""

    serializer_class = GMApplicationQueueSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[RosterApplication]:
        if self.request.user.is_staff:
            # Staff see all pending apps across all GM tables.
            from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

            return (
                RosterApplication.objects.filter(
                    status=ApplicationStatus.PENDING,
                    character__story_participations__is_active=True,
                    character__story_participations__story__primary_table__isnull=False,
                    character__story_participations__story__primary_table__status=(
                        GMTableStatus.ACTIVE
                    ),
                )
                .select_related("character", "player_data__account")
                .distinct()
            )
        gm = _get_gm_or_403(self.request.user)
        return gm_application_queue(gm)


APPROVE_ACTION = "approve"
DENY_ACTION = "deny"


class GMApplicationActionView(APIView):
    """GM approves or denies a pending application in their queue.

    URL path: /api/gm/queue/<id>/<action>/ where action is 'approve' or 'deny'.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int, action: str) -> Response:
        gm = _get_gm_or_403(request.user)
        application = get_object_or_404(RosterApplication, pk=pk)
        try:
            if action == APPROVE_ACTION:
                approve_as_gm_service(gm, application)
            elif action == DENY_ACTION:
                deny_as_gm_service(
                    gm,
                    application,
                    review_notes=request.data.get("review_notes", ""),
                )
            else:
                return Response(
                    {"detail": f"Unknown action: {action}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"status": "ok"})


class GMInviteClaimView(APIView):
    """Logged-in user claims an invite by code."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        code = request.data.get("code")
        if not code:
            return Response(
                {"code": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            application = claim_invite_service(code=code, account=request.user)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"application_id": application.pk},
            status=status.HTTP_201_CREATED,
        )

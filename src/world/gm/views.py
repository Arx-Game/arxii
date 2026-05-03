"""ViewSets for the GM system."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.gm.constants import GMApplicationStatus, GMTableStatus
from world.gm.filters import (
    GMApplicationFilter,
    GMProfileFilter,
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
from world.gm.permissions import IsGM, IsGMOrStaff
from world.gm.serializers import (
    GMApplicationActionSerializer,
    GMApplicationCreateSerializer,
    GMApplicationDetailSerializer,
    GMApplicationQueueSerializer,
    GMInviteClaimSerializer,
    GMInviteRevokeSerializer,
    GMProfileSerializer,
    GMRosterInviteSerializer,
    GMTableMembershipSerializer,
    GMTableSerializer,
)
from world.gm.services import (
    archive_table,
    gm_application_queue,
    join_table,
    leave_table,
    transfer_ownership as transfer_ownership_service,
)
from world.roster.models.applications import RosterApplication
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


class GMProfileViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only list of approved GM profiles.

    Accessible by any authenticated user so players can pick a GM when
    offering their story. Supports ``?search=<username>`` for autocomplete.
    """

    queryset = GMProfile.objects.select_related("account").order_by("account__username")
    serializer_class = GMProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = GMProfileFilter
    pagination_class = StandardResultsSetPagination


class GMTableViewSet(viewsets.ModelViewSet):
    """GM table management.

    Staff sees all tables. GMs see their own tables. Players see tables where any
    of their personas has an active GMTableMembership (left_at__isnull=True).

    Persona-to-account chain: GMTableMembership.persona → Persona.character_sheet
    → CharacterSheet.character (ObjectDB) → ObjectDB.db_account.

    Archive and transfer ownership are staff-only lifecycle actions.
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
        # GM owner of the table OR has an active membership via any persona.
        return qs.filter(
            Q(gm__account=user)
            | Q(
                memberships__persona__character_sheet__character__db_account=user,
                memberships__left_at__isnull=True,
            )
        ).distinct()

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

    Staff sees all memberships. GMs (table owners) see all memberships at their
    tables. Authenticated players see all memberships at tables where any of
    their personas has an active membership — this gives them the member roster
    for tables they belong to.

    Persona-to-account chain: GMTableMembership.persona → Persona.character_sheet
    → CharacterSheet.character (ObjectDB) → ObjectDB.db_account.

    Creation uses the join_table service to apply temporary-persona validation.
    Destroy is a soft-leave — the record remains with left_at set.
    """

    queryset = GMTableMembership.objects.select_related("table", "persona").order_by("-pk")
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
        # GM owns the table OR the user has an active membership at the table.
        # The second branch gives members access to the full membership roster
        # for any table they actively belong to (needed for Wave 4 Members tab).
        return qs.filter(
            Q(table__gm__account=user)
            | Q(
                table__memberships__persona__character_sheet__character__db_account=user,
                table__memberships__left_at__isnull=True,
            )
        ).distinct()

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

    - create: GM only, must oversee the character (validated in serializer)
    - list/retrieve: scoped to GM's invites (staff sees all)
    - destroy: revokes unclaimed invites (validated in serializer)
    """

    serializer_class = GMRosterInviteSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsGMOrStaff]

    def get_queryset(self) -> QuerySet[GMRosterInvite]:
        qs = GMRosterInvite.objects.select_related(
            "roster_entry", "created_by__account", "claimed_by"
        ).order_by("-created_at")
        user = self.request.user
        if user.is_staff:
            return qs
        return qs.filter(created_by__account=user)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        instance = self.get_object()
        serializer = GMInviteRevokeSerializer(
            instance,
            data={},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GMApplicationQueueView(generics.ListAPIView):
    """Read-only list of pending applications for this GM's characters."""

    serializer_class = GMApplicationQueueSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsGMOrStaff]

    def get_queryset(self) -> QuerySet[RosterApplication]:
        from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

        user = self.request.user
        if user.is_staff:
            # Staff see all pending apps across all GM tables.
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
        return gm_application_queue(user.gm_profile)


class GMApplicationActionView(APIView):
    """GM approves or denies a pending application in their queue.

    URL path: /api/gm/queue/<id>/<action>/ where action is 'approve' or 'deny'.
    """

    permission_classes = [IsGM]

    @transaction.atomic
    def post(self, request: Request, pk: int, action: str) -> Response:
        application = get_object_or_404(RosterApplication, pk=pk)
        serializer = GMApplicationActionSerializer(
            data={
                "action": action,
                "review_notes": request.data.get("review_notes", ""),
            },
            context={"request": request, "application": application},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "ok"})


class GMInviteClaimView(APIView):
    """Logged-in user claims an invite by code."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request: Request) -> Response:
        serializer = GMInviteClaimSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        return Response(
            {"application_id": application.pk},
            status=status.HTTP_201_CREATED,
        )

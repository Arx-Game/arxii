"""API ViewSets for covenants."""

from __future__ import annotations

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.covenants.exceptions import (
    CovenantEngagementPrerequisiteNotMetError,
    CovenantExitError,
    NotACovenantLeaderError,
    NotAStandingBattleCovenantError,
    SubrolePromotionError,
)
from world.covenants.filters import (
    CharacterCovenantRoleFilter,
    CovenantFilter,
    CovenantRiteFilter,
    CovenantRoleFilter,
    GearArchetypeCompatibilityFilter,
)
from world.covenants.handlers import can_engage_membership
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantLevelThreshold,
    CovenantRite,
    CovenantRole,
    GearArchetypeCompatibility,
)
from world.covenants.permissions import CanKickFromCovenant, IsOwnMembership
from world.covenants.serializers import (
    CharacterCovenantRoleSerializer,
    CovenantLevelThresholdSerializer,
    CovenantRiteSerializer,
    CovenantRolePassivePowerSerializer,
    CovenantRoleSerializer,
    CovenantSerializer,
    GearArchetypeCompatibilitySerializer,
    PromoteSubroleSerializer,
)
from world.covenants.services import (
    clear_engaged_membership,
    kick_member,
    leave_covenant,
    promote_to_subrole,
    set_engaged_membership,
    stand_down_battle_covenant,
)


class CovenantsPagination(PageNumberPagination):
    """Standard pagination for covenants list endpoints."""

    page_size = 50


class CharacterCovenantRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for character covenant role assignments.

    Non-staff users only see assignments on character sheets they currently
    play (via the active RosterTenure chain). Staff see all assignments;
    they may filter explicitly by character_sheet PK to scope results.
    """

    serializer_class = CharacterCovenantRoleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CovenantsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterCovenantRoleFilter

    def get_queryset(self) -> QuerySet[CharacterCovenantRole]:
        qs = CharacterCovenantRole.objects.select_related(
            "character_sheet",
            "covenant_role",
            "covenant",
        ).order_by("-joined_at")
        if self.request.user.is_staff:
            return qs
        # Non-staff: scope to character sheets the user currently plays.
        return qs.filter(
            character_sheet__roster_entry__tenures__end_date__isnull=True,
            character_sheet__roster_entry__tenures__player_data__account=self.request.user,
        ).distinct()

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, IsOwnMembership],
    )
    def engage(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/engage/

        Engage the membership for scene presence.  Returns 400 when the
        IC prerequisite is not met (no covenant members present in scene).
        """
        membership = self.get_object()
        if not can_engage_membership(membership):
            return Response(
                {"detail": CovenantEngagementPrerequisiteNotMetError.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        set_engaged_membership(membership=membership)
        return Response(self.get_serializer(membership).data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, IsOwnMembership],
    )
    def disengage(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/disengage/

        Un-engage the membership.  Idempotent — succeeds even if not currently
        engaged.
        """
        membership = self.get_object()
        clear_engaged_membership(membership=membership)
        return Response(self.get_serializer(membership).data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, IsOwnMembership],
        serializer_class=PromoteSubroleSerializer,
    )
    def promote(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/promote/

        Promote the membership from its current parent role to a sub-role.
        Body: { "target_subrole": <pk> }

        Returns the new CharacterCovenantRole row on success.
        Returns 400 with a user_message body on promotion failures.
        """
        membership = self.get_object()
        ser = PromoteSubroleSerializer(
            data=request.data,
            context={"membership": membership},
        )
        ser.is_valid(raise_exception=True)
        try:
            new_membership = promote_to_subrole(
                membership=membership,
                target_subrole=ser.validated_data["target_subrole"],
            )
        except SubrolePromotionError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            CharacterCovenantRoleSerializer(new_membership, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, IsOwnMembership],
    )
    def leave(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/leave/ — voluntary self-leave."""
        membership = self.get_object()
        leave_covenant(membership=membership)
        return Response(self.get_serializer(membership).data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, CanKickFromCovenant],
    )
    def kick(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/kick/ — a leader removes a non-leader.

        The target may be outside the requester's own-scoped get_queryset, so fetch it
        via the full manager and run object permissions explicitly rather than get_object().
        """
        target = get_object_or_404(
            CharacterCovenantRole.objects.select_related("covenant", "covenant_role"), pk=pk
        )
        self.check_object_permissions(request, target)
        actor = (
            CharacterCovenantRole.objects.filter(
                covenant_id=target.covenant_id,
                left_at__isnull=True,
                covenant_role__is_leadership=True,
                character_sheet__roster_entry__tenures__end_date__isnull=True,
                character_sheet__roster_entry__tenures__player_data__account=request.user,
            )
            .exclude(pk=target.pk)
            .select_related("covenant_role")
            .first()
        )
        if actor is None:
            return Response(
                {"detail": NotACovenantLeaderError.user_message},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            kick_member(target=target, actor=actor)
        except CovenantExitError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(target).data)


class CovenantRoleViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for CovenantRole lookup data.

    Staff-authored lookup table listing available roles per covenant type.
    Supports ?covenant_type= filtering so ritual form pickers can populate
    only the roles relevant to the chosen covenant type.
    """

    serializer_class = CovenantRoleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table — no pagination needed.
    filter_backends = [DjangoFilterBackend]
    filterset_class = CovenantRoleFilter
    queryset = CovenantRole.objects.all().order_by("covenant_type", "name")


class GearArchetypeCompatibilityViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for authored covenant×archetype compatibility rows."""

    queryset = GearArchetypeCompatibility.objects.select_related("covenant_role").order_by(
        "covenant_role__name",
        "gear_archetype",
    )
    serializer_class = GearArchetypeCompatibilitySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Authored lookup table — small, no pagination needed.
    filter_backends = [DjangoFilterBackend]
    filterset_class = GearArchetypeCompatibilityFilter


def _build_role_power_row(
    membership: CharacterCovenantRole,
    threads_by_key: dict,
    effects_by_resonance: dict,
) -> dict:
    """Join one active membership to its current passive role power (no queries).

    ``threads_by_key`` is keyed (owner_id, covenant_role_id);
    ``effects_by_resonance`` maps resonance_id → tier-0 CAPABILITY_GRANT effect.
    A member with no woven role-thread (or a thread below the effect's
    ``min_thread_level``) has null capability fields.
    """
    thread = threads_by_key.get((membership.character_sheet_id, membership.covenant_role_id))
    resonance_name = None
    capability_name = None
    narrative_snippet = None
    if thread is not None and thread.resonance_id is not None:
        resonance_name = thread.resonance.name
        effect = effects_by_resonance.get(thread.resonance_id)
        if effect is not None and thread.level >= effect.min_thread_level:
            if effect.capability_grant is not None:
                capability_name = effect.capability_grant.name
            narrative_snippet = effect.narrative_snippet or None
    return {
        "membership_id": membership.pk,
        "character_sheet": membership.character_sheet_id,
        "covenant_role_id": membership.covenant_role_id,
        "covenant_role_name": membership.covenant_role.name,
        "resonance_name": resonance_name,
        "capability_name": capability_name,
        "narrative_snippet": narrative_snippet,
        "engaged": membership.engaged,
    }


class CovenantViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for Covenant.

    Non-staff users only see covenants where they have an active membership
    on a character sheet they currently play (via the active RosterTenure
    chain). Staff see all covenants.
    """

    serializer_class = CovenantSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CovenantsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CovenantFilter

    def get_queryset(self) -> QuerySet[Covenant]:
        qs = Covenant.objects.all().order_by("-formed_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(
            memberships__left_at__isnull=True,
            memberships__character_sheet__roster_entry__tenures__end_date__isnull=True,
            memberships__character_sheet__roster_entry__tenures__player_data__account=self.request.user,
        ).distinct()

    @action(detail=True, methods=["GET"])
    def powers(self, request: Request, pk: int | None = None) -> Response:
        """GET /api/covenants/covenants/{id}/powers/

        Return the covenant's available rites (with per-covenant gate flags) and
        per-member passive role powers in one payload, for the React detail page.

        Visibility is enforced by ``get_object()`` (the membership-scoped
        ``get_queryset``): a non-staff user with no active membership gets 404.
        Deliberately does NOT serialize the Covenant via ``CovenantSerializer``
        (that touches the Postgres-only legend materialized view).
        """
        from world.magic.constants import EffectKind, TargetKind  # noqa: PLC0415
        from world.magic.models import Thread, ThreadPullEffect  # noqa: PLC0415

        covenant = self.get_object()

        # --- Active memberships (one query, role pre-joined) -----------------
        memberships = list(
            covenant.memberships.filter(left_at__isnull=True).select_related("covenant_role")
        )
        active_member_count = len(memberships)

        sheet_ids = {m.character_sheet_id for m in memberships}
        role_ids = {m.covenant_role_id for m in memberships}

        # --- Threads: one query keyed (owner, role) -------------------------
        threads_by_key: dict[tuple[int, int], Thread] = {}
        resonance_ids: set[int] = set()
        if sheet_ids and role_ids:
            for thread in Thread.objects.filter(
                owner_id__in=sheet_ids,
                target_kind=TargetKind.COVENANT_ROLE,
                target_covenant_role_id__in=role_ids,
                retired_at__isnull=True,
            ).select_related("resonance"):
                threads_by_key[(thread.owner_id, thread.target_covenant_role_id)] = thread
                if thread.resonance_id is not None:
                    resonance_ids.add(thread.resonance_id)

        # --- Tier-0 CAPABILITY_GRANT effects: one query keyed by resonance ---
        effects_by_resonance: dict[int, ThreadPullEffect] = {}
        if resonance_ids:
            for effect in ThreadPullEffect.objects.filter(
                target_kind=TargetKind.COVENANT_ROLE,
                tier=0,
                effect_kind=EffectKind.CAPABILITY_GRANT,
                resonance_id__in=resonance_ids,
            ).select_related("capability_grant"):
                effects_by_resonance[effect.resonance_id] = effect

        # --- Join in Python --------------------------------------------------
        role_power_rows = [
            _build_role_power_row(membership, threads_by_key, effects_by_resonance)
            for membership in memberships
        ]
        role_power_data = CovenantRolePassivePowerSerializer(role_power_rows, many=True).data

        # --- Rites: authored per covenant_type, with gate flags --------------
        rite_data = []
        for rite in CovenantRite.objects.filter(
            covenant_type=covenant.covenant_type
        ).select_related("ritual", "granted_condition"):
            entry = dict(CovenantRiteSerializer(rite).data)
            entry["level_met"] = covenant.level >= rite.min_covenant_level
            entry["members_present_met"] = active_member_count >= rite.min_members_present
            rite_data.append(entry)

        return Response({"rites": rite_data, "role_powers": role_power_data})

    @action(detail=True, methods=["POST"])
    def stand_down(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/covenants/{id}/stand_down/

        Stand a risen STANDING battle covenant back down to dormant, clearing
        engagement on its members. The "rise" path is ritual-fired; this is the
        plain inverse the covenant detail UI POSTs to.

        Visibility/membership is enforced by ``get_object()`` (the
        membership-scoped ``get_queryset``): a non-staff user with no active
        membership gets 404. Returns 400 with a ``detail`` message when the
        target is not a standing battle covenant.

        Returns a minimal confirmation dict rather than ``CovenantSerializer``
        (which touches the Postgres-only legend materialized view); the
        frontend re-fetches the covenant detail separately.
        """
        covenant = self.get_object()
        try:
            stand_down_battle_covenant(covenant=covenant)
        except NotAStandingBattleCovenantError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "id": covenant.id,
                "is_dormant": covenant.is_dormant,
                "battle_binding": covenant.battle_binding,
            }
        )


class CovenantRiteViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for CovenantRite authored definitions.

    Rites are authored/public content — any authenticated user may read.
    No per-user scoping needed.
    """

    serializer_class = CovenantRiteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CovenantsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CovenantRiteFilter
    queryset = CovenantRite.objects.select_related("ritual", "granted_condition").all()

    def get_queryset(self) -> QuerySet[CovenantRite]:
        return CovenantRite.objects.select_related("ritual", "granted_condition").all()


class CovenantLevelThresholdViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ViewSet for CovenantLevelThreshold authored lookup table.

    Returns the legend totals required to reach each covenant level.
    No pagination — this is a small, stable lookup table.
    """

    queryset = CovenantLevelThreshold.objects.all().order_by("level")
    serializer_class = CovenantLevelThresholdSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table — no pagination needed.

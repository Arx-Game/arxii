"""API ViewSets for covenants."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.covenants.exceptions import (
    CannotTransferToDepartedMemberError,
    CovenantEngagementPrerequisiteNotMetError,
    CovenantExitError,
    CrossCovenantRankError,
    IncompleteRankReorderError,
    LastManagerRankError,
    NotAStandingBattleCovenantError,
    NotAuthorizedToKickError,
    NotAuthorizedToManageRanksError,
)
from world.covenants.filters import (
    CharacterCovenantRoleFilter,
    CovenantFilter,
    CovenantRankFilter,
    CovenantRiteFilter,
    CovenantRoleFilter,
    GearArchetypeCompatibilityFilter,
)
from world.covenants.handlers import can_engage_membership
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantLevelThreshold,
    CovenantRank,
    CovenantRite,
    CovenantRole,
    GearArchetypeCompatibility,
)
from world.covenants.permissions import (
    CanKickFromCovenant,
    IsOwnMembership,
)
from world.covenants.selectors import resolve_actor_membership
from world.covenants.serializers import (
    AssignMemberRequestSerializer,
    CharacterCovenantRoleSerializer,
    CovenantLevelThresholdSerializer,
    CovenantRankSerializer,
    CovenantRiteSerializer,
    CovenantRolePassivePowerSerializer,
    CovenantRoleSerializer,
    CovenantSerializer,
    GearArchetypeCompatibilitySerializer,
    ReorderRanksRequestSerializer,
    TransferTopRequestSerializer,
)
from world.covenants.services import (
    assign_rank,
    clear_engaged_membership,
    create_rank,
    delete_rank,
    kick_member,
    leave_covenant,
    rename_rank,
    reorder_ranks,
    set_engaged_membership,
    set_rank_capabilities,
    stand_down_battle_covenant,
    transfer_top,
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
        qs = (
            CharacterCovenantRole.objects.select_related(
                "character_sheet",
                "character_sheet__character",
                "covenant_role",
                "covenant",
            )
            # Serialized twice per row (anchor_role + the resolved covenant_role,
            # which for non-promoted rows IS the same covenant_role instance) —
            # prefetch so both reads hit the cache instead of issuing 2 queries (#2443).
            .prefetch_related(
                Prefetch(
                    "covenant_role__technique_specialties",
                    to_attr="cached_technique_specialties",
                )
            )
            .order_by("-joined_at")
        )
        if self.request.user.is_staff:
            return qs
        if self.action == "list":
            # Non-staff list: show all members of covenants the user is currently a member of.
            # The display_name field suppresses identity for blocked pairs (#2086).
            return qs.filter(
                covenant__memberships__left_at__isnull=True,
                covenant__memberships__character_sheet__roster_entry__tenures__end_date__isnull=True,
                covenant__memberships__character_sheet__roster_entry__tenures__player_data__account=self.request.user,
            ).distinct()
        # Non-staff retrieve/action: scope to character sheets the user currently plays.
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
    )
    def leave(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/leave/ — voluntary self-leave."""
        membership = self.get_object()
        try:
            leave_covenant(membership=membership)
        except CovenantExitError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(membership).data)

    @action(
        detail=True,
        methods=["POST"],
        permission_classes=[IsAuthenticated, CanKickFromCovenant],
    )
    def kick(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/character-roles/{id}/kick/ — remove a member with lower rank
        authority (rank tier precedence: actor.rank.tier < target.rank.tier).

        The target may be outside the requester's own-scoped get_queryset, so fetch it
        via the full manager and run object permissions explicitly rather than get_object().
        """
        target = get_object_or_404(
            CharacterCovenantRole.objects.select_related("covenant", "covenant_role", "rank"),
            pk=pk,
        )
        self.check_object_permissions(request, target)
        actor = (
            CharacterCovenantRole.objects.filter(
                covenant_id=target.covenant_id,
                left_at__isnull=True,
                rank__can_kick=True,
                character_sheet__roster_entry__tenures__end_date__isnull=True,
                character_sheet__roster_entry__tenures__player_data__account=request.user,
            )
            .exclude(pk=target.pk)
            .select_related("rank")
            .first()
        )
        if actor is None:
            return Response(
                {"detail": NotAuthorizedToKickError.user_message},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            kick_member(target=target, actor=actor)
        except CovenantExitError as exc:
            # CannotKickEqualOrHigherRankError (and CannotKickSelfError) arrive here → 400.
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

    # Page aggregates (member_count / legend_total keyed by covenant pk) that
    # ``list`` precomputes for ``get_serializer_context``; None on non-list
    # actions so the serializer falls back to its per-object path. DRF builds a
    # fresh viewset instance per request, so this never leaks across requests.
    _page_aggregates: dict[int, dict[str, int]] | None = None

    def get_queryset(self) -> QuerySet[Covenant]:
        # prefetch storylines (2026-07 audit): CovenantSerializer.storylines is a
        # many-relation that otherwise fires one query per covenant on the list.
        qs = Covenant.objects.prefetch_related(
            "storylines",  # noqa: PREFETCH_STRING
        ).order_by("-formed_at")
        if self.request.user.is_staff:
            return qs
        return qs.filter(
            memberships__left_at__isnull=True,
            memberships__character_sheet__roster_entry__tenures__end_date__isnull=True,
            memberships__character_sheet__roster_entry__tenures__player_data__account=self.request.user,
        ).distinct()

    @staticmethod
    def _covenant_aggregates(covenant_ids: list[int]) -> dict[int, dict[str, int]]:
        """Bulk member_count + legend_total for a page of covenants (2026-07 audit).

        CovenantSerializer computed both per row — a ``.count()`` and a matview
        ``values_list`` each — so a page cost ~2 queries per covenant. This runs
        two total queries for the whole page instead. Kept as a plain
        bulk-fetch (correlated matview Subqueries proved fragile on the covenant
        pk); the members-only list keeps the page small regardless.
        """
        from django.db.models import Count  # noqa: PLC0415

        from world.societies.services import get_covenant_legend_totals  # noqa: PLC0415

        if not covenant_ids:
            return {}
        counts = dict(
            CharacterCovenantRole.objects.filter(covenant_id__in=covenant_ids, left_at__isnull=True)
            .values("covenant_id")
            .annotate(c=Count("id"))
            .values_list("covenant_id", "c")
        )
        totals = get_covenant_legend_totals(covenant_ids)
        return {
            pk: {"member_count": counts.get(pk, 0), "legend_total": totals.get(pk, 0)}
            for pk in covenant_ids
        }

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        aggregates = self._page_aggregates
        if aggregates is not None:
            context["covenant_aggregates"] = aggregates
        return context

    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        # NOTE: intentionally no docstring — drf-spectacular would publish it as
        # the list endpoint's description, replacing the class docstring. Mirrors
        # DRF's default list() but stashes the page's aggregates first so
        # get_serializer_context can hand them to the serializer, avoiding the
        # per-row member_count/legend_total queries.
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        covenants = page if page is not None else list(queryset)
        self._page_aggregates = self._covenant_aggregates([c.pk for c in covenants])
        serializer = self.get_serializer(covenants, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

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
                target_gift__isnull=True,  # COVENANT_ROLE path; exclude gift-specific rows
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


class CovenantRankViewSet(viewsets.ModelViewSet):
    """ViewSet for CovenantRank (the per-covenant administrative authority ladder).

    Reads: any active covenant member.
    Writes (create/update/partial_update/destroy): requires CanManageCovenantRanks
    (requester's active membership must have rank.can_manage_ranks=True).

    All rank management operations route through the Task 5 service functions
    (create_rank, rename_rank, set_rank_capabilities, reorder_ranks, delete_rank).
    No business logic lives in the view.
    """

    serializer_class = CovenantRankSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CovenantsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = CovenantRankFilter

    def get_queryset(self) -> QuerySet[CovenantRank]:
        qs = CovenantRank.objects.select_related("covenant").order_by("covenant", "tier")
        if self.request.user.is_staff:
            return qs
        # Non-staff: scope to covenants where the user has an active membership.
        return qs.filter(
            covenant__memberships__left_at__isnull=True,
            covenant__memberships__character_sheet__roster_entry__tenures__end_date__isnull=True,
            covenant__memberships__character_sheet__roster_entry__tenures__player_data__account=(
                self.request.user
            ),
        ).distinct()

    def _get_actor(self, covenant: Covenant) -> CharacterCovenantRole | None:
        """Return the requesting user's active can_manage_ranks membership, or None."""
        user_sheets = CharacterSheet.objects.filter(
            roster_entry__tenures__end_date__isnull=True,
            roster_entry__tenures__player_data__account=self.request.user,
        )
        return resolve_actor_membership(
            covenant=covenant,
            character_sheets=user_sheets,
            capability="can_manage_ranks",
        )

    def _any_manager(self, covenant: Covenant) -> CharacterCovenantRole | None:
        """Return any active can_manage_ranks member (for staff bypass). Or None."""
        return resolve_actor_membership(
            covenant=covenant,
            character_sheets=CharacterSheet.objects.all(),
            capability="can_manage_ranks",
        )

    def _resolve_actor(
        self,
        covenant: Covenant,
        request: Request,
    ) -> tuple[CharacterCovenantRole | None, Response | None]:
        """Return (actor, None) when authorized, or (None, 403 Response) when not.

        For staff: any active manager in the covenant acts as proxy.
        For non-staff: the requesting user's own active manager membership.
        Returns (None, None) only in the staff path when NO manager exists in the
        covenant at all — callers may proceed with a direct-DB fallback.
        """
        if request.user.is_staff:
            return self._any_manager(covenant), None
        actor = self._get_actor(covenant)
        if actor is None:
            return None, Response(
                {"detail": NotAuthorizedToManageRanksError.user_message},
                status=status.HTTP_403_FORBIDDEN,
            )
        return actor, None

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """POST /api/covenants/ranks/ — create a new rank via the service."""
        ser = CovenantRankSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        covenant = ser.validated_data["covenant"]
        actor, err = self._resolve_actor(covenant, request)
        if err is not None:
            return err
        if actor is None:
            # Staff with no existing manager: direct create.
            rank = CovenantRank.objects.create(**ser.validated_data)
            return Response(CovenantRankSerializer(rank).data, status=status.HTTP_201_CREATED)
        try:
            rank = create_rank(
                covenant=covenant,
                actor=actor,
                name=ser.validated_data["name"],
                tier=ser.validated_data["tier"],
                can_invite=ser.validated_data.get("can_invite", False),
                can_kick=ser.validated_data.get("can_kick", False),
                can_manage_ranks=ser.validated_data.get("can_manage_ranks", False),
                can_lead_rituals=ser.validated_data.get("can_lead_rituals", False),
            )
        except NotAuthorizedToManageRanksError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)
        return Response(CovenantRankSerializer(rank).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: object, **kwargs: object) -> Response:
        """PUT/PATCH — rename and/or set capability flags via service functions."""
        partial = kwargs.pop("partial", False)
        rank = self.get_object()
        ser = CovenantRankSerializer(rank, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        actor, err = self._resolve_actor(rank.covenant, request)
        if err is not None:
            return err
        if actor is None:
            # Staff with no existing manager: direct update.
            for field, value in ser.validated_data.items():
                setattr(rank, field, value)
            rank.save()
            return Response(CovenantRankSerializer(rank).data)
        return self._apply_rank_update(rank, actor, ser.validated_data)

    def _apply_rank_update(
        self, rank: CovenantRank, actor: CharacterCovenantRole, validated: dict
    ) -> Response:
        """Apply rename + capability updates through service functions."""
        try:
            if "name" in validated:  # noqa: STRING_LITERAL
                rank = rename_rank(rank=rank, actor=actor, name=validated["name"])
            cap_kwargs: dict = {
                cap: validated[cap]
                for cap in ("can_invite", "can_kick", "can_manage_ranks", "can_lead_rituals")
                if cap in validated
            }
            if cap_kwargs:
                rank = set_rank_capabilities(rank=rank, actor=actor, **cap_kwargs)
        except NotAuthorizedToManageRanksError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)
        except LastManagerRankError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CovenantRankSerializer(rank).data)

    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """DELETE — requires reassign_to in body; routes through delete_rank service."""
        rank = self.get_object()
        reassign_to_id = request.data.get("reassign_to")
        if reassign_to_id is None:
            return Response(
                {"detail": "reassign_to is required when deleting a rank."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reassign_to = get_object_or_404(CovenantRank, pk=reassign_to_id)
        actor, err = self._resolve_actor(rank.covenant, request)
        if err is not None:
            return err
        if actor is None:
            rank.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        try:
            delete_rank(rank=rank, actor=actor, reassign_to=reassign_to)
        except NotAuthorizedToManageRanksError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)
        except (LastManagerRankError, CrossCovenantRankError) as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=ReorderRanksRequestSerializer,
        responses={200: CovenantRankSerializer(many=True)},
    )
    @action(detail=False, methods=["POST"], url_path="reorder", pagination_class=None)
    def reorder(self, request: Request) -> Response:
        """POST /api/covenants/ranks/reorder/

        Body: { "covenant": <pk>, "ordered_rank_ids": [<pk>, ...] }
        Reorders the covenant's ranks — requires can_manage_ranks.
        """
        covenant_id = request.data.get("covenant")
        ordered_rank_ids = request.data.get("ordered_rank_ids")
        if covenant_id is None or ordered_rank_ids is None:
            return Response(
                {"detail": "covenant and ordered_rank_ids are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        covenant = get_object_or_404(Covenant, pk=covenant_id)
        actor, err = self._resolve_actor(covenant, request)
        if err is not None:
            return err
        if actor is None:
            return Response(
                {"detail": NotAuthorizedToManageRanksError.user_message},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            ranks = reorder_ranks(covenant=covenant, actor=actor, ordered_rank_ids=ordered_rank_ids)
        except NotAuthorizedToManageRanksError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)
        except IncompleteRankReorderError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CovenantRankSerializer(ranks, many=True).data)

    @extend_schema(
        request=AssignMemberRequestSerializer,
        responses=CharacterCovenantRoleSerializer,
    )
    @action(detail=True, methods=["POST"], url_path="assign-member")
    def assign_member(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/ranks/{pk}/assign-member/

        Body: { "membership": <pk> }
        Assigns the given membership to this rank — requires can_manage_ranks.
        """
        rank = self.get_object()
        membership_id = request.data.get("membership")
        if membership_id is None:
            return Response(
                {"detail": "membership is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership = get_object_or_404(CharacterCovenantRole, pk=membership_id)
        actor, err = self._resolve_actor(rank.covenant, request)
        if err is not None:
            return err
        if actor is None:
            return Response(
                {"detail": NotAuthorizedToManageRanksError.user_message},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            membership = assign_rank(membership=membership, actor=actor, rank=rank)
        except NotAuthorizedToManageRanksError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)
        except (LastManagerRankError, CrossCovenantRankError) as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        ser = CharacterCovenantRoleSerializer(membership, context={"request": request})
        return Response(ser.data)

    @extend_schema(
        request=TransferTopRequestSerializer,
        responses=CovenantRankSerializer,
    )
    @action(detail=True, methods=["POST"], url_path="transfer-top")
    def transfer_top_rank(self, request: Request, pk: int | None = None) -> Response:
        """POST /api/covenants/ranks/{pk}/transfer-top/

        Body: { "new_top_membership": <pk> }
        Transfer the top rank (this rank) from the actor to the given membership.
        Requires can_manage_ranks.
        """
        rank = self.get_object()
        new_top_id = request.data.get("new_top_membership")
        if new_top_id is None:
            return Response(
                {"detail": "new_top_membership is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        new_top_membership = get_object_or_404(CharacterCovenantRole, pk=new_top_id)
        actor, err = self._resolve_actor(rank.covenant, request)
        if err is not None:
            return err
        if actor is None:
            return Response(
                {"detail": NotAuthorizedToManageRanksError.user_message},
                status=status.HTTP_403_FORBIDDEN,
            )
        return self._do_transfer_top(rank, actor, new_top_membership)

    def _do_transfer_top(
        self,
        rank: CovenantRank,
        actor: CharacterCovenantRole,
        new_top_membership: CharacterCovenantRole,
    ) -> Response:
        """Execute transfer_top and map typed exceptions to HTTP responses."""
        try:
            transfer_top(covenant=rank.covenant, actor=actor, new_top_membership=new_top_membership)
        except NotAuthorizedToManageRanksError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)
        except (CrossCovenantRankError, CannotTransferToDepartedMemberError) as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CovenantRankSerializer(rank).data)

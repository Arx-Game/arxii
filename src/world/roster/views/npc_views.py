"""The NPC roster and authoring API at ``/api/roster/npcs/`` (#4418).

GMs and Guides browse the NPCs holders have listed and ask to borrow them; a holder
edits the lending settings and notes, authors the NPC's regard and preferences, and
copies sections between their NPCs. Owner-only routes answer 404 to anyone else so a
non-owner learns nothing about an NPC they cannot manage.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPMethod
from typing import Any, cast

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.shortcuts import get_object_or_404
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from web.api.character_type import TYPECLASS_TO_CHARACTER_TYPE
from world.gm.models import GuideProfile
from world.npc_services.personality import set_npc_preferences
from world.npc_services.regard import author_npc_regard
from world.roster.constants import NPCBorrowAudience, NPCLendPolicy, NPCLoanStatus
from world.roster.models import NPCLoan, RosterEntry, RosterTenure, StoryNPCSettings
from world.roster.permissions import IsGMOrGuide
from world.roster.serializers.npc_roster import (
    AnswerSerializer,
    CopyAsNewSerializer,
    CopySectionResultSerializer,
    CopySectionSerializer,
    CreatedNPCSerializer,
    NPCDetailSerializer,
    NPCLoanSerializer,
    NPCOfferSerializer,
    NPCRosterRowSerializer,
    PreferencesSerializer,
    RegardResultSerializer,
    RegardSerializer,
    source_entries_for,
)
from world.roster.services.npc_copy import copy_npc_as_new, copy_npc_section
from world.roster.services.npc_lending import (
    NPCLendingError,
    answer_loan,
    request_borrow,
)
from world.roster.services.staff_characters import StaffMintError
from world.scenes.cast_list_services import player_names

_ROW_RELATIONS = (
    "character_sheet__character__display_data",
    "story_npc_settings",
    "created_by_account",
    "profile_picture__media",
    "profile_picture__tenure",
    "character_sheet__character",
)
_OWNER_ACTIONS = ("partial_update", "update", "regard", "preferences", "copy_section")


def npc_entries() -> QuerySet[RosterEntry]:
    """Every NPC with lending settings, with what a row reads already selected.

    ``has_holder`` is whether someone currently holds the NPC (an open tenure).
    """
    held = RosterTenure.objects.filter(roster_entry=OuterRef("pk"), end_date__isnull=True)
    return (
        RosterEntry.objects.filter(story_npc_settings__isnull=False)
        .select_related(*_ROW_RELATIONS)
        .annotate(has_holder=Exists(held))
    )


def owner_names_for(entries: list[RosterEntry]) -> dict[int, str]:
    """Owner account id to the GM or Staff character name shown for it, in one query."""
    account_ids = {e.created_by_account_id for e in entries if e.created_by_account_id}
    names: dict[int, str] = {}
    tenures = (
        RosterTenure.objects.filter(
            player_data__account_id__in=account_ids,
            end_date__isnull=True,
            roster_entry__character_sheet__character__db_typeclass_path__in=list(
                TYPECLASS_TO_CHARACTER_TYPE
            ),
        )
        .select_related("player_data", "roster_entry__character_sheet__character")
        .order_by("-pk")
    )
    for tenure in tenures:
        names[tenure.player_data.account_id] = tenure.roster_entry.character_sheet.character.db_key
    return names


class NPCRosterPagination(PageNumberPagination):
    page_size = 20


@dataclass
class NPCViewer:
    """What the requesting account may do with NPCs, read once per request."""

    account: AccountDB
    is_gm: bool
    is_guide: bool
    held_entry_ids: frozenset[int]
    borrowed_entry_ids: frozenset[int]
    open_request_entry_ids: frozenset[int]

    @classmethod
    def for_account(cls, account: AccountDB) -> NPCViewer:
        held = RosterTenure.objects.filter(player_data__account=account, end_date__isnull=True)
        loans = NPCLoan.objects.filter(borrower=account)
        return cls(
            account=account,
            is_gm=account.gm_profile_or_none is not None,
            is_guide=GuideProfile.objects.filter(account=account, is_active=True).exists(),
            held_entry_ids=frozenset(held.values_list("roster_entry_id", flat=True)),
            borrowed_entry_ids=frozenset(
                loans.filter(status=NPCLoanStatus.ACTIVE).values_list("roster_entry_id", flat=True)
            ),
            open_request_entry_ids=frozenset(
                loans.filter(
                    status__in=(NPCLoanStatus.REQUESTED, NPCLoanStatus.ACTIVE)
                ).values_list("roster_entry_id", flat=True)
            ),
        )

    def manages(self, entry: RosterEntry) -> bool:
        return self.account.is_staff or entry.created_by_account_id == self.account.pk

    def sees_notes(self, entry: RosterEntry) -> bool:
        return self.manages(entry) or entry.pk in self.borrowed_entry_ids

    def can_borrow(self, entry: RosterEntry, settings: StoryNPCSettings) -> bool:
        """Mirrors the refusals ``request_borrow`` makes, without raising."""
        if settings.lend_policy == NPCLendPolicy.NOT_LENT or settings.is_template:
            return False
        if not settings.listed_on_npc_roster or not entry.has_holder:
            return False
        guide_ok = settings.borrow_audience == NPCBorrowAudience.GMS_AND_GUIDES and self.is_guide
        if not (self.account.is_staff or self.is_gm or guide_ok):
            return False
        if entry.created_by_account_id == self.account.pk or entry.pk in self.held_entry_ids:
            return False
        return entry.pk not in self.open_request_entry_ids


class NPCRosterFilterSet(django_filters.FilterSet):
    lendable_to_me = django_filters.BooleanFilter(method="filter_lendable_to_me")

    class Meta:
        model = RosterEntry
        fields: list[str] = []

    def filter_lendable_to_me(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        if not value:
            return queryset
        account = self.request.user
        queryset = queryset.exclude(story_npc_settings__lend_policy=NPCLendPolicy.NOT_LENT)
        if not (account.is_staff or account.gm_profile_or_none is not None):
            queryset = queryset.filter(
                story_npc_settings__borrow_audience=NPCBorrowAudience.GMS_AND_GUIDES
            )
        held = RosterTenure.objects.filter(player_data__account=account, end_date__isnull=True)
        open_loans = NPCLoan.objects.filter(
            borrower=account, status__in=(NPCLoanStatus.REQUESTED, NPCLoanStatus.ACTIVE)
        )
        return (
            queryset.exclude(created_by_account=account)
            .exclude(pk__in=held.values("roster_entry_id"))
            .exclude(pk__in=open_loans.values("roster_entry_id"))
        )


class StoryNPCViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Browse listed NPCs; owners edit settings, authoring and copies."""

    serializer_class = NPCRosterRowSerializer
    permission_classes = [IsGMOrGuide]
    pagination_class = NPCRosterPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = NPCRosterFilterSet
    search_fields = ["character_sheet__character__db_key"]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    # -- scoping -------------------------------------------------------------

    def get_queryset(self) -> QuerySet[RosterEntry]:
        if not self.request.user.is_authenticated:  # schema generation: anonymous
            return RosterEntry.objects.none()
        account = self.request.user
        base = npc_entries()
        if self.action in _OWNER_ACTIONS:
            scope = Q() if account.is_staff else Q(created_by_account=account)
        elif self.action == "retrieve":
            scope = Q(created_by_account=account) | Q(
                npc_loans__borrower=account, npc_loans__status=NPCLoanStatus.ACTIVE
            )
            if account.is_staff:
                scope = Q()
        elif self.action == "copy_as_new":
            scope = source_entries_for(account)
        elif self.action == "templates":
            scope = Q(story_npc_settings__is_template=True) & source_entries_for(account)
        else:
            scope = Q(
                story_npc_settings__listed_on_npc_roster=True,
                story_npc_settings__is_template=False,
            )
        return base.filter(scope).distinct().order_by("character_sheet__character__db_key", "pk")

    def get_serializer_class(self) -> type[serializers.BaseSerializer]:
        if self.action in ("retrieve", "partial_update", "update"):
            return NPCDetailSerializer
        return super().get_serializer_class()

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        if self.request is not None and self.request.user.is_authenticated:
            context["viewer"] = NPCViewer.for_account(cast(AccountDB, self.request.user))
            context["owner_names"] = {}
        return context

    @staticmethod
    def _refused(exc: NPCLendingError | StaffMintError) -> Response:
        return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)

    # -- owner authoring -----------------------------------------------------

    @extend_schema(request=RegardSerializer, responses=RegardResultSerializer)
    @action(detail=True, methods=[HTTPMethod.PUT])
    def regard(self, request: Request, pk: int | None = None) -> Response:
        entry = self.get_object()
        serializer = RegardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        author_npc_regard(
            holder_persona=entry.character_sheet.primary_persona,
            target=data["target"],
            value=data["value"],
            reason=data["reason"],
        )
        return Response(
            {
                "target_type": data["target_type"],
                "target_id": data["target_id"],
                "value": data["value"],
            }
        )

    @extend_schema(request=PreferencesSerializer, responses=PreferencesSerializer)
    @action(detail=True, methods=[HTTPMethod.PUT])
    def preferences(self, request: Request, pk: int | None = None) -> Response:
        entry = self.get_object()
        serializer = PreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lines = serializer.validated_data["preferences"]
        set_npc_preferences(
            entry.character_sheet.primary_persona,
            [(line["trait"], line["valence"]) for line in lines],
        )
        return Response(
            {
                "preferences": [
                    {"trait": line["trait"].pk, "valence": line["valence"]} for line in lines
                ]
            }
        )

    @extend_schema(request=CopySectionSerializer, responses=CopySectionResultSerializer)
    @action(detail=True, methods=[HTTPMethod.POST], url_path="copy-section")
    def copy_section(self, request: Request, pk: int | None = None) -> Response:
        target = self.get_object()
        serializer = CopySectionSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        copy_npc_section(
            serializer.validated_data["source_entry"], target, serializer.validated_data["section"]
        )
        return Response({"section": serializer.validated_data["section"]})

    @extend_schema(request=CopyAsNewSerializer, responses={201: CreatedNPCSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="copy-as-new")
    def copy_as_new(self, request: Request, pk: int | None = None) -> Response:
        source = self.get_object()
        serializer = CopyAsNewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            new_entry = copy_npc_as_new(
                source,
                by=cast(AccountDB, request.user),
                name=serializer.validated_data["name"],
                as_template=serializer.validated_data["as_template"],
            )
        except StaffMintError as exc:
            return self._refused(exc)
        return Response({"id": new_entry.pk}, status=status.HTTP_201_CREATED)

    def _page_response(self, request: Request) -> Response:
        page = list(self.paginate_queryset(self.filter_queryset(self.get_queryset())) or [])
        context = self.get_serializer_context()
        context["owner_names"] = owner_names_for(page)
        serializer = NPCRosterRowSerializer(page, many=True, context=context)
        return self.get_paginated_response(serializer.data)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._page_response(request)

    @extend_schema(responses=NPCRosterRowSerializer(many=True))
    @action(detail=False, methods=[HTTPMethod.GET])
    def templates(self, request: Request) -> Response:
        return self._page_response(request)

    # -- borrowing -----------------------------------------------------------

    @extend_schema(request=None, responses={201: NPCLoanSerializer})
    @action(detail=True, methods=[HTTPMethod.POST])
    def borrow(self, request: Request, pk: int | None = None) -> Response:
        entry = self.get_object()
        try:
            loan = request_borrow(entry=entry, borrower=cast(AccountDB, request.user))
        except NPCLendingError as exc:
            return self._refused(exc)
        return Response(NPCLoanSerializer(loan).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=NPCOfferSerializer(many=True))
    @action(detail=False, methods=[HTTPMethod.GET])
    def offers(self, request: Request) -> Response:
        """The NPC offers waiting for the requesting Guide to answer."""
        loans = (
            NPCLoan.objects.filter(borrower=request.user, status=NPCLoanStatus.OFFERED)
            .select_related(
                "scene",
                "roster_entry__story_npc_settings",
                "roster_entry__profile_picture__media",
                "roster_entry__profile_picture__tenure",
                "roster_entry__character_sheet__character",
            )
            .order_by("-pk")
        )
        page = list(self.paginate_queryset(loans) or [])
        context = self.get_serializer_context()
        context["offered_names"] = player_names(loan.offered_by_id for loan in page)
        serializer = NPCOfferSerializer(page, many=True, context=context)
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=AnswerSerializer, responses=NPCLoanSerializer)
    @action(detail=False, methods=[HTTPMethod.POST])
    def answer(self, request: Request) -> Response:
        serializer = AnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = cast(AccountDB, request.user)
        # Only the NPC's owner, staff, or the borrower of the loan may even see it.
        scope = Q(borrower=account) | Q(roster_entry__created_by_account=account)
        loans = NPCLoan.objects.select_related("roster_entry", "scene")
        loan = get_object_or_404(
            loans if account.is_staff else loans.filter(scope),
            pk=serializer.validated_data["loan_id"],
        )
        try:
            loan = answer_loan(
                loan=loan,
                accept=serializer.validated_data["accept"],
                by=account,
            )
        except NPCLendingError as exc:
            return self._refused(exc)
        return Response(NPCLoanSerializer(loan).data)

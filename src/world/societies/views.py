"""DRF viewsets for the societies membership API (#1511)."""

from __future__ import annotations

from http import HTTPMethod

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.societies.filters import (
    OrganizationFilter,
    OrganizationMembershipFilter,
    OrganizationMembershipOfferFilter,
    OrganizationRankFilter,
    OrgAppealFilter,
    StandingDeclarationFilter,
)
from world.societies.models import (
    Organization,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationRank,
    OrganizationReputation,
    OrgAppeal,
    StandingDeclaration,
)
from world.societies.permissions import IsOwnMembership, active_persona_q
from world.societies.serializers import (
    OrganizationMembershipOfferSerializer,
    OrganizationMembershipSerializer,
    OrganizationRankSerializer,
    OrganizationReputationSerializer,
    OrganizationSerializer,
    OrgAppealCreateSerializer,
    OrgAppealResolveInputSerializer,
    OrgAppealSerializer,
    OrgAppealSignonInputSerializer,
    OrgDossierSerializer,
    StandingDeclarationSerializer,
)
from world.tidings.serializers import PublicFeedItemSerializer


def _active_persona_for_request(request):
    """Resolve the request user's ACTIVE persona, or None.

    Small local mirror of ``world.tasking.permissions.active_persona_for_request``
    (kept in-app rather than cross-imported from ``tasking`` — a private
    per-file helper is the established pattern here, see e.g. `_actor_persona`
    duplicated across `actions/definitions/*.py`).
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


class SocietiesPagination(PageNumberPagination):
    page_size = 50


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve organizations the requester is an active member of.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    Staff see all non-covenant organizations.
    """

    # Prefetch the house-payload relations (2026-07 audit): OrganizationSerializer
    # .get_house serializes titles/domains/aspects/features inline, which fired
    # ~6 queries per org with a family (~300 on a 50-org page). select_related
    # the family + prefetch the rest so the payload reads from cache.
    queryset = (
        Organization.objects.select_related(
            "family", "society", "org_type", "stature__band", "stature__previous_band"
        )
        .prefetch_related(
            "ranks",  # noqa: PREFETCH_STRING
            "titles__holder",  # noqa: PREFETCH_STRING
            "domains__holdings",  # noqa: PREFETCH_STRING
            "aspects__definition",  # noqa: PREFETCH_STRING
            "aspects__option",  # noqa: PREFETCH_STRING
            "features__feature",  # noqa: PREFETCH_STRING
            "domains__crises__crisis_type__options",  # noqa: PREFETCH_STRING — crisis cards (#2238)
            "domains__crises__chosen_option",  # noqa: PREFETCH_STRING
            "org_crises__crisis_type__options",  # noqa: PREFETCH_STRING — org-leg cards (#2837)
            "org_crises__chosen_option",  # noqa: PREFETCH_STRING
            "fealty__liege",  # noqa: PREFETCH_STRING  — this org's liege edge (get_house)
            "vassal_edges__vassal",  # noqa: PREFETCH_STRING  — its direct vassals
        )
        .order_by("id")
    )
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        return qs.filter(
            active_persona_q(self.request.user, path="memberships__persona"),
            memberships__left_at__isnull=True,
            memberships__exiled_at__isnull=True,
        ).distinct()

    @action(detail=True, methods=[HTTPMethod.POST], url_path="crisis-option")
    def crisis_option(self, request, pk=None):
        """POST /api/societies/organizations/{id}/crisis-option/ (#2238).

        The administrator's judgment call on an open DomainCrisis. Body:
        ``{"crisis": <id>, "option": <id>}``. Acts as whichever of the
        requester's personas holds domain authority (leader rank or the
        domain-steward office) — a 400 with a safe message otherwise.
        """
        from world.scenes.interaction_permissions import get_account_personas  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.houses.crisis_services import (  # noqa: PLC0415
            CrisisServiceError,
            can_judge_crisis,
            choose_crisis_option,
        )
        from world.societies.serializers import (  # noqa: PLC0415
            CrisisOptionInputSerializer,
            _house_open_crises,
        )

        organization = self.get_object()
        ser = CrisisOptionInputSerializer(data=request.data, context={"organization": organization})
        ser.is_valid(raise_exception=True)
        crisis = ser.validated_data["crisis"]
        option = ser.validated_data["option"]

        persona = None
        owned = Persona.objects.filter(pk__in=get_account_personas(request))
        for candidate in owned:
            if can_judge_crisis(candidate, crisis):
                persona = candidate
                break
        if persona is None:
            return Response(
                {"detail": "You do not have authority over this."},
                status=400,
            )
        try:
            choose_crisis_option(crisis, persona, option)
        except CrisisServiceError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response({"open_crises": _house_open_crises(organization)})

    @extend_schema(responses=OrgDossierSerializer)
    @action(detail=True, methods=[HTTPMethod.GET])
    def dossier(self, request, pk=None):
        """GET /api/societies/organizations/{id}/dossier/ (#2999).

        The match-review dossier — deliberately readable by ANY authenticated
        player (weighing a match means reviewing RIVAL houses, so this action
        looks the org up directly rather than through the members-only
        queryset). Public facts + covert crises the viewer's org has paid
        spycraft (CrisisIntel) to know.
        """
        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        from world.scenes.interaction_permissions import get_account_personas  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.dossier_services import build_dossier  # noqa: PLC0415
        from world.societies.serializers import OrgDossierSerializer  # noqa: PLC0415

        organization = get_object_or_404(
            Organization.objects.select_related(
                "family", "org_type", "stature__band", "stature__previous_band"
            ),
            pk=pk,
            covenant__isnull=True,
        )
        viewer = Persona.objects.filter(pk__in=get_account_personas(request)).first()
        payload = build_dossier(organization, viewer=viewer)
        return Response(OrgDossierSerializer(payload).data)

    @extend_schema(responses=PublicFeedItemSerializer(many=True))
    @action(detail=True, methods=[HTTPMethod.GET])
    def feed(self, request, pk=None):
        """The house feed (#1884): recent deeds + revealed scandals of the household."""
        from world.tidings.services import house_feed_for  # noqa: PLC0415

        organization = self.get_object()
        items = house_feed_for(organization)
        return Response(PublicFeedItemSerializer(items, many=True).data)


class ProclamationViewSet(viewsets.ReadOnlyModelViewSet):
    """Public record of proclamations (#2842) + the issue door.

    List/retrieve are public to authenticated players (proclamations are
    public speech by design). ``POST /proclaim/`` issues one as the
    requester's active persona — a plain stance, an org voice, or a domain
    edict enactment (domain + edict_kind).
    """

    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ("org", "stance", "issuer")

    def get_queryset(self):
        from world.societies.models import Proclamation  # noqa: PLC0415

        return Proclamation.objects.select_related(
            "issuer", "stance", "org", "check_outcome"
        ).order_by("-issued_at")

    def get_serializer_class(self):
        from world.societies.serializers import ProclamationSerializer  # noqa: PLC0415

        return ProclamationSerializer

    @action(detail=False, methods=[HTTPMethod.POST], url_path="proclaim")
    def proclaim(self, request):
        """Issue a proclamation (optionally enacting a domain edict)."""
        from world.scenes.interaction_permissions import get_account_personas  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.houses.models import Domain, EdictKind  # noqa: PLC0415
        from world.societies.models import Organization, StanceArchetype  # noqa: PLC0415
        from world.societies.proclamations import (  # noqa: PLC0415
            ProclamationError,
            enact_edict,
            issue_proclamation,
        )
        from world.societies.serializers import (  # noqa: PLC0415
            ProclamationCreateSerializer,
            ProclamationSerializer,
        )

        payload = ProclamationCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        persona = Persona.objects.filter(pk__in=get_account_personas(request)).first()
        if persona is None:
            return Response({"detail": "No active persona."}, status=400)
        try:
            if data.get("domain"):
                domain = Domain.objects.filter(pk=data["domain"]).first()
                kind = EdictKind.objects.filter(pk=data["edict_kind"]).first()
                if domain is None or kind is None:
                    return Response({"detail": "No such domain or edict."}, status=400)
                edict = enact_edict(domain, kind, persona, prose=data.get("prose", ""))
                row = edict.proclamation
            else:
                stance = StanceArchetype.objects.filter(pk=data["stance"]).first()
                if stance is None:
                    return Response({"detail": "No such stance."}, status=400)
                org = (
                    Organization.objects.filter(pk=data["org"]).first() if data.get("org") else None
                )
                row = issue_proclamation(persona, stance, prose=data.get("prose", ""), org=org)
        except ProclamationError as exc:
            return Response({"detail": exc.user_message}, status=400)
        return Response(ProclamationSerializer(row).data, status=201)


class OrganizationMembershipViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve memberships for personas the requester currently plays.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    """

    queryset = (
        OrganizationMembership.objects.select_related("organization", "persona", "rank")
        .filter(organization__covenant__isnull=True)
        .order_by("-joined_date")
    )
    serializer_class = OrganizationMembershipSerializer
    permission_classes = [IsAuthenticated, IsOwnMembership]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationMembershipFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(organization__covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        return qs.filter(active_persona_q(self.request.user, path="persona"))


class OrganizationReputationViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve org reputations (standing) for personas the requester currently plays.

    Self-only: rows are scoped to personas the requester currently plays.
    """

    queryset = OrganizationReputation.objects.select_related("organization").order_by(
        "organization__name"
    )
    serializer_class = OrganizationReputationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ("organization",)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(active_persona_q(self.request.user, path="persona"))


class OrganizationRankViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve rank ladders for organizations the requester belongs to.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    Staff see all non-covenant rank ladders.
    """

    queryset = OrganizationRank.objects.select_related("organization").order_by("tier")
    serializer_class = OrganizationRankSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationRankFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(organization__covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        return qs.filter(
            active_persona_q(self.request.user, path="organization__memberships__persona"),
            organization__memberships__left_at__isnull=True,
            organization__memberships__exiled_at__isnull=True,
        ).distinct()


class OrganizationMembershipOfferViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve membership offers visible to the requester.

    Covenants (organizations with a related ``covenant`` row) are excluded.
    """

    queryset = OrganizationMembershipOffer.objects.select_related(
        "organization", "from_persona", "to_persona"
    ).order_by("-created_at")
    serializer_class = OrganizationMembershipOfferSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrganizationMembershipOfferFilter

    def get_queryset(self):
        qs = super().get_queryset().filter(organization__covenant__isnull=True)
        if self.request.user.is_staff:
            return qs
        user = self.request.user
        owned = qs.filter(active_persona_q(user, path="from_persona"))
        received = qs.filter(active_persona_q(user, path="to_persona"))
        org_visible = qs.filter(
            active_persona_q(user, path="organization__memberships__persona"),
            organization__memberships__left_at__isnull=True,
            organization__memberships__exiled_at__isnull=True,
        )
        return (owned | received | org_visible).distinct()


class StandingDeclarationViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve leader favor/disfavor declarations (#3290).

    Public read to any authenticated player (spec decision 4) — org politics
    played through declarations are meant to be legible to bystanders, unlike
    the raw ``OrganizationReputation`` value they move (which stays self-only,
    see ``OrganizationReputationViewSet``). Writes never happen here — a
    declaration is minted by ``DeclareStandingAction`` (web + telnet), which
    calls ``world.societies.standing_services.declare_standing``.
    """

    queryset = StandingDeclaration.objects.select_related(
        "organization", "target_persona", "declared_by_persona"
    ).order_by("-created_at")
    serializer_class = StandingDeclarationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = StandingDeclarationFilter

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(organization__covenant__isnull=True)


class OrgAppealViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Appeals to organizations (#3293) — list/read + lodge/signon/resolve/withdraw.

    Read is member-gated (mirrors `tasking/views.py`'s `OrgTaskViewSet`):
    visible rows are the organization's active members' + the petitioner's
    own appeals — an org's inbound asks are its own business, not public.
    Lodging, signing on, resolving, and withdrawing all dispatch through the
    matching REGISTRY Action (ADR-0001) — the same seam telnet's `CmdAppeal`
    uses.
    """

    queryset = (
        OrgAppeal.objects.select_related(
            "organization", "petitioner_persona", "resolved_by_persona"
        )
        .prefetch_related("signons__member_persona")  # noqa: PREFETCH_STRING
        .order_by("-created_at")
    )
    serializer_class = OrgAppealSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SocietiesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrgAppealFilter

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        owned = qs.filter(active_persona_q(user, path="petitioner_persona"))
        org_visible = qs.filter(
            active_persona_q(user, path="organization__memberships__persona"),
            organization__memberships__left_at__isnull=True,
            organization__memberships__exiled_at__isnull=True,
        )
        return (owned | org_visible).distinct()

    def _refetch(self, appeal: OrgAppeal) -> OrgAppeal:
        """Re-fetch *appeal* dropping any stale ``signons`` prefetch cache.

        ``self.get_object()`` may have prefetched ``signons`` before a mutating
        action created/changed related rows; a plain ``refresh_from_db()``
        would leave that stale cache in place (SharedMemoryModel instances are
        shared — see the idmapper caching notes in `world/CLAUDE.md`), so drop
        it explicitly before re-serializing.
        """
        appeal.refresh_from_db()
        # `_prefetched_objects_cache` is a Django-internal instance attribute only
        # set when prefetch_related actually ran (e.g. never on the `create()`
        # return path, which fetches directly) — read it via __dict__ instead of
        # getattr() so a never-prefetched appeal doesn't need a literal-default
        # fallback (tools/lint_getattr_literal.py).
        cache = appeal.__dict__.get("_prefetched_objects_cache")
        if cache is not None:
            cache.pop("signons", None)
        return appeal

    def create(self, request, *args, **kwargs):
        """Lodge an appeal — dispatched through LodgeAppealAction (ADR-0001)."""
        from actions.registry import get_action  # noqa: PLC0415

        persona = _active_persona_for_request(request)
        if persona is None:
            return Response({"detail": "No active persona."}, status=400)

        payload = OrgAppealCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        result = get_action("org_appeal_lodge").run(
            persona.character_sheet.character,
            organization_id=data["organization"].pk,
            title=data["title"],
            body=data["body"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=400)
        appeal = OrgAppeal.objects.get(pk=result.data["appeal_id"])
        return Response(self.get_serializer(appeal).data, status=201)

    @action(detail=True, methods=[HTTPMethod.POST])
    def signon(self, request, pk=None):
        """A member signs onto this open appeal — SignonAppealAction."""
        from actions.registry import get_action  # noqa: PLC0415

        appeal = self.get_object()
        persona = _active_persona_for_request(request)
        if persona is None:
            return Response({"detail": "No active persona."}, status=400)

        payload = OrgAppealSignonInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        result = get_action("org_appeal_signon").run(
            persona.character_sheet.character,
            appeal_id=appeal.pk,
            note=payload.validated_data["note"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=400)
        return Response(self.get_serializer(self._refetch(appeal)).data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def resolve(self, request, pk=None):
        """Leadership (or staff) grants/declines this open appeal — ResolveAppealAction."""
        from actions.registry import get_action  # noqa: PLC0415

        appeal = self.get_object()
        persona = _active_persona_for_request(request)
        if persona is None:
            return Response({"detail": "No active persona."}, status=400)

        payload = OrgAppealResolveInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        result = get_action("org_appeal_resolve").run(
            persona.character_sheet.character,
            appeal_id=appeal.pk,
            verdict=data["verdict"],
            answer=data["answer"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=400)
        return Response(self.get_serializer(self._refetch(appeal)).data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def withdraw(self, request, pk=None):
        """The petitioner withdraws their own open appeal — WithdrawAppealAction."""
        from actions.registry import get_action  # noqa: PLC0415

        appeal = self.get_object()
        persona = _active_persona_for_request(request)
        if persona is None:
            return Response({"detail": "No active persona."}, status=400)

        result = get_action("org_appeal_withdraw").run(
            persona.character_sheet.character,
            appeal_id=appeal.pk,
        )
        if not result.success:
            return Response({"detail": result.message}, status=400)
        return Response(self.get_serializer(self._refetch(appeal)).data)

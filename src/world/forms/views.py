from http import HTTPMethod

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from world.forms.models import (
    AlternateSelf,
    Build,
    CharacterForm,
    CharacterFormValue,
    FormTrait,
    HeightBand,
)
from world.forms.serializers import (
    ActiveAlternateSelfResultSerializer,
    AlternateSelfSerializer,
    ApparentFormSerializer,
    BuildSerializer,
    CharacterFormSerializer,
    FormTraitSerializer,
    HeightBandSerializer,
    ShiftFormRequestSerializer,
)
from world.forms.services import get_apparent_form, get_cg_builds, get_cg_height_bands
from world.roster.selectors import puppeted_sheet_for


class FormTraitViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing form trait definitions."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    queryset = FormTrait.objects.all()
    serializer_class = FormTraitSerializer
    permission_classes = [IsAuthenticated]


class CharacterFormViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing a character's forms."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = CharacterFormSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to forms belonging to the user's characters."""
        if not self.request.user.is_authenticated:
            return CharacterForm.objects.none()
        # Get characters owned by this account
        return (
            CharacterForm.objects.filter(character__db_account=self.request.user)
            .select_related("character")
            .prefetch_related(
                Prefetch(
                    "values",
                    queryset=CharacterFormValue.objects.select_related("trait", "option"),
                    to_attr="cached_values",
                ),
            )
        )

    @action(detail=False, methods=["get"])
    def apparent(self, request):
        """Get the apparent form for the user's active character."""
        character = request.user.puppet if hasattr(request.user, "puppet") else None
        if not character:
            return Response({"detail": "No active character"}, status=400)

        apparent = get_apparent_form(character)
        serializer = ApparentFormSerializer(apparent)
        return Response(serializer.data)


class HeightBandViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing height bands in character creation."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = HeightBandSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return CG-selectable bands by default, all for staff."""
        if self.request.user.is_staff:
            return HeightBand.objects.all()
        return get_cg_height_bands()


class BuildViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing builds in character creation."""

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = BuildSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return CG-selectable builds by default, all for staff."""
        if self.request.user.is_staff:
            return Build.objects.all()
        return get_cg_builds()


class AlternateSelfPagination(PageNumberPagination):
    """Pagination for alternate-selves list."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AlternateSelfViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read + actions over a character's alternate selves (#1111 slice 4).

    Mirrors ``PersonaViewSet``: list the caller's own alt-self grants, then expose
    player-facing mutators that dispatch through ``dispatch_player_action`` so the web
    and telnet share one ``action.run()`` seam.
    """

    serializer_class = AlternateSelfSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {"character": ["exact"]}
    pagination_class = AlternateSelfPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to alternate selves belonging to the played character's sheet."""
        user = self.request.user
        sheet = puppeted_sheet_for(user)
        queryset = AlternateSelf.objects.select_related(
            "persona", "form", "combat_profile"
        ).prefetch_related("techniques")  # noqa: PREFETCH_STRING
        if sheet is not None:
            return queryset.filter(character=sheet).order_by("display_name")
        return queryset.none()

    @extend_schema(
        request=ShiftFormRequestSerializer,
        responses={200: ActiveAlternateSelfResultSerializer},
        tags=["alternate-selves"],
    )
    @action(
        detail=False,
        methods=[HTTPMethod.POST],
        url_path="shift",
        permission_classes=[permissions.IsAuthenticated],
    )
    def shift(self, request: Request) -> Response:
        """#1111 — assume an alternate self owned by the played character."""
        body = ShiftFormRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        puppet = request.user.puppet
        sheet = puppeted_sheet_for(request.user)
        if puppet is None or sheet is None:
            msg = "You must be playing a character to shift forms."
            raise serializers.ValidationError(msg)

        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="shift_form")
        result = dispatch_player_action(
            puppet, ref, {"alternate_self_id": body.validated_data["alternate_self_id"]}
        )
        detail = result.detail
        if not detail.success:
            raise serializers.ValidationError(detail.message)
        return Response(
            ActiveAlternateSelfResultSerializer(
                {"active_alternate_self_id": detail.data.get("active_alternate_self_id")}
            ).data
        )

    @extend_schema(
        responses={200: ActiveAlternateSelfResultSerializer},
        tags=["alternate-selves"],
    )
    @action(
        detail=False,
        methods=[HTTPMethod.POST],
        url_path="revert",
        permission_classes=[permissions.IsAuthenticated],
    )
    def revert(self, request: Request) -> Response:
        """#1111 — revert the active alternate self (blocked while not in control)."""
        puppet = request.user.puppet
        sheet = puppeted_sheet_for(request.user)
        if puppet is None or sheet is None:
            msg = "You must be playing a character to revert forms."
            raise serializers.ValidationError(msg)

        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="revert_form")
        result = dispatch_player_action(puppet, ref, {})
        detail = result.detail
        if not detail.success:
            raise serializers.ValidationError(detail.message)
        return Response(
            ActiveAlternateSelfResultSerializer(
                {"active_alternate_self_id": detail.data.get("active_alternate_self_id")}
            ).data
        )

"""Account-throttled, authenticated typed menu read boundary."""

from typing import Any

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_vary_headers
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from evennia.objects.models import ObjectDB
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from actions.target_menu import InvalidCandidateCursor, build_target_menu
from actions.target_menu_serializers import TargetMenuSerializer
from actions.target_menu_types import (
    INPUT_CONTAINER_ITEM,
    INPUT_OWNER_PERSONA,
    MenuTargetKind,
    MenuTargetRequest,
)
from web.api.permissions import IsCharacterOwner

UNAVAILABLE = "That isn't available."
INPUT_CANDIDATE_CURSOR = "candidate_cursor"


class MenuAccountThrottle(SimpleRateThrottle):
    """One account allowance for all menu reads; best-effort cache history."""

    scope = "target_menu"

    def get_rate(self) -> str:
        return settings.TARGET_MENU_ACCOUNT_RATE

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        if not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(request.user.pk)}


class MenuContextFilter(filters.FilterSet):
    owner_persona_id = filters.NumberFilter(min_value=1)
    container_item_id = filters.NumberFilter(min_value=1)
    candidate_cursor = filters.CharFilter(required=False)
    inputs_for = filters.ChoiceFilter(
        choices=(("give", "Give"), ("put_in", "Put in"), ("use_item", "Use"))
    )

    class Meta:
        model = ObjectDB
        fields = []


class TargetMenuView(APIView):
    permission_classes = [IsAuthenticated, IsCharacterOwner]
    throttle_classes = [MenuAccountThrottle]

    def handle_exception(self, exc: Any) -> Response:
        if isinstance(exc, Http404):
            exc = NotFound(UNAVAILABLE)
        return super().handle_exception(exc)

    def finalize_response(self, request: Any, response: Any, *args: Any, **kwargs: Any) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ("Cookie", "Authorization"))
        return response

    @extend_schema(responses={200: TargetMenuSerializer})
    def get(self, request: Any, character_id: int, target_kind: str, target_id: int) -> Response:
        try:
            kind = MenuTargetKind(target_kind)
        except ValueError as exc:
            raise NotFound(UNAVAILABLE) from exc
        context = MenuContextFilter(request.query_params, queryset=ObjectDB.objects.none())
        if not context.is_valid():
            raise ValidationError(context.errors)
        cleaned = context.form.cleaned_data
        if INPUT_CANDIDATE_CURSOR in request.query_params and not cleaned.get(
            INPUT_CANDIDATE_CURSOR
        ):
            raise ValidationError({INPUT_CANDIDATE_CURSOR: ["Enter a valid cursor."]})
        values = {}
        for name in (INPUT_OWNER_PERSONA, INPUT_CONTAINER_ITEM):
            value = cleaned.get(name)
            if value is not None:
                if value != value.to_integral_value():
                    raise ValidationError({name: ["Enter a whole number."]})
                values[name] = int(value)
        if INPUT_OWNER_PERSONA in values and INPUT_CONTAINER_ITEM in values:
            raise ValidationError({"detail": "Choose owner or container context, not both."})
        actor = get_object_or_404(ObjectDB, pk=character_id)
        try:
            menu = build_target_menu(
                actor,
                MenuTargetRequest(kind, target_id, **values),
                inputs_for=cleaned.get("inputs_for") or None,
                candidate_cursor=cleaned.get(INPUT_CANDIDATE_CURSOR) or None,
                account_id=request.user.pk,
            )
        except InvalidCandidateCursor:
            raise ValidationError({INPUT_CANDIDATE_CURSOR: ["Enter a valid cursor."]}) from None
        if menu is None:
            raise NotFound(UNAVAILABLE)
        return Response(TargetMenuSerializer(menu).data)

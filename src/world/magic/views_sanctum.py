"""Sanctum API views (Plan 4 §F).

Lean MVP surface: list "my Sanctums" (sanctums I own + sanctums I've
woven into) and POST actions for Homecoming / Purging / Weave / Sever.
The install-wizard endpoint (create the install Project + nested
SanctumInstallParams) is a deferred follow-up — opening a project is a
multi-app coordination (Project + RoomFeatureProgressionDetails +
SanctumInstallParams) that warrants its own design pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.magic.constants import TargetKind
from world.magic.exceptions import ResonanceInsufficient
from world.magic.models import Resonance, SanctumDetails, Thread
from world.magic.serializers_sanctum import (
    HomecomingActionSerializer,
    PurgingActionSerializer,
    SanctumDetailsSerializer,
    SanctumThreadSerializer,
    WeaveActionSerializer,
)
from world.magic.services.sanctum_install import (
    AbsorbError,
    absorb_sanctum_pool,
)
from world.magic.services.sanctum_rituals import (
    HomecomingValidationError,
    PurgingValidationError,
    perform_homecoming_ritual,
    perform_purging_ritual,
)
from world.magic.services.sanctum_weaving import (
    SanctumWeavingError,
    sever_sanctum_thread,
    weave_sanctum_thread,
)

if TYPE_CHECKING:
    from world.scenes.models import Persona


def _active_persona_for_request(request) -> Persona:
    """Resolve the request user's currently presented persona.

    Sanctum actions are persona-scoped per `feedback_account_fk_wrong_for_ic_items`
    — alt personas are separate IC identities, and ownership / membership
    checks must run against the persona the player is acting as right now.
    Lookup: account → active RosterEntry → CharacterSheet → primary_persona.
    Multi-persona alt-of-self awareness is a deferred follow-up; for now
    the primary persona is the safe default.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        msg = "You must have an active roster entry to act on Sanctums."
        raise DRFValidationError(msg)
    persona = entry.character_sheet.primary_persona
    if persona is None:
        msg = "Your character has no primary persona; cannot act on Sanctums."
        raise DRFValidationError(msg)
    return persona


class SanctumViewSet(viewsets.ReadOnlyModelViewSet):
    """Read + action endpoints for the player's Sanctum surface.

    `list` returns Sanctums the user has standing in (owns or has woven
    into). `retrieve` is gated by the same standing check. POST actions
    delegate to the service layer; service-level exceptions surface as
    HTTP 400 with the typed `user_message` per `feedback_codeql_exceptions`.
    """

    serializer_class = SanctumDetailsSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "feature_instance_id"
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        persona = _active_persona_for_request(self.request)
        woven_sanctum_ids = Thread.objects.filter(
            owner=persona.character_sheet,
            target_kind=TargetKind.SANCTUM,
            retired_at__isnull=True,
        ).values_list("target_sanctum_details_id", flat=True)
        # Owned Sanctums: traverse LocationOwnership for the room. Persona-scoped
        # so alt-persona separation holds (see feedback_account_fk_wrong_for_ic_items).
        from world.locations.models import LocationOwnership  # noqa: PLC0415

        owned_room_ids = LocationOwnership.objects.filter(
            holder_persona=persona,
            ended_at__isnull=True,
        ).values_list("room_profile_id", flat=True)
        return (
            SanctumDetails.objects.select_related(
                "feature_instance__room_profile",
                "resonance_type",
            )
            .filter(
                Q(feature_instance_id__in=woven_sanctum_ids)
                | Q(feature_instance__room_profile_id__in=owned_room_ids)
            )
            .distinct()
        )

    @action(detail=True, methods=["post"], url_path="homecoming")
    def homecoming(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        serializer = HomecomingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        persona = _active_persona_for_request(request)
        try:
            result = perform_homecoming_ritual(
                sanctum,
                persona,
                resonance_sacrificed=serializer.validated_data["resonance_sacrificed"],
                narrative_text=serializer.validated_data.get("narrative_text", ""),
            )
        except (HomecomingValidationError, ResonanceInsufficient) as exc:
            return _action_error_response(exc)
        return Response(
            {
                "base_resonance_added": result.base_resonance_added,
                "overflow_escrowed": result.overflow_escrowed,
                "new_homecoming_sum": result.new_homecoming_sum,
                "new_cap": result.new_cap,
            }
        )

    @action(detail=True, methods=["post"], url_path="purging")
    def purging(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        serializer = PurgingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        persona = _active_persona_for_request(request)
        new_resonance = get_object_or_404(
            Resonance, pk=serializer.validated_data["new_resonance_id"]
        )
        try:
            result = perform_purging_ritual(
                sanctum,
                persona,
                new_resonance=new_resonance,
                resonance_sacrificed=serializer.validated_data["resonance_sacrificed"],
            )
        except (PurgingValidationError, ResonanceInsufficient) as exc:
            return _action_error_response(exc)
        return Response(
            {
                "new_resonance_id": result.new_resonance_id,
                "sum_after_drain": result.sum_after_drain,
                "sacrifice_paid": result.sacrifice_paid,
            }
        )

    @action(detail=True, methods=["post"], url_path="weave")
    def weave(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        serializer = WeaveActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        persona = _active_persona_for_request(request)
        try:
            thread = weave_sanctum_thread(
                sanctum,
                persona.character_sheet,
                serializer.validated_data["slot_kind"],
            )
        except SanctumWeavingError as exc:
            return _action_error_response(exc)
        return Response(SanctumThreadSerializer(thread).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="absorb")
    def absorb(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        persona = _active_persona_for_request(request)
        try:
            result = absorb_sanctum_pool(sanctum, persona)
        except AbsorbError as exc:
            return _action_error_response(exc)
        return Response(
            {
                "sanctum_id": result.sanctum_id,
                "weaving_drained": result.weaving_drained,
                "owner_bonus_drained": result.owner_bonus_drained,
                "total_drained": result.total_drained,
            }
        )

    @action(detail=True, methods=["post"], url_path="sever/(?P<thread_id>[0-9]+)")
    def sever(self, request, feature_instance_id=None, thread_id=None):
        sanctum = self.get_object()
        persona = _active_persona_for_request(request)
        thread = get_object_or_404(
            Thread,
            pk=thread_id,
            target_sanctum_details=sanctum,
            owner=persona.character_sheet,
            target_kind=TargetKind.SANCTUM,
        )
        try:
            sever_sanctum_thread(thread)
        except SanctumWeavingError as exc:
            return _action_error_response(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _action_error_response(exc: Exception) -> Response:
    """Surface the typed exception's user_message — never str(exc)."""
    user_message = getattr(exc, "user_message", "Operation failed.")  # noqa: GETATTR_LITERAL
    return Response({"detail": user_message}, status=status.HTTP_400_BAD_REQUEST)

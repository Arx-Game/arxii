"""Sanctum API views (Plan 4 §F).

Lean MVP surface: list "my Sanctums" (sanctums I own + sanctums I've
woven into) and POST actions for Homecoming / Purging / Weave / Sever /
Install / Dissolve / Absorb.  All write endpoints converge on
``action.run()`` via the seven Actions in
``actions/definitions/sanctum.py`` (#1497).
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

from actions.definitions.sanctum import (
    SanctumAbsorbAction,
    SanctumDissolveAction,
    SanctumHomecomingAction,
    SanctumInstallAction,
    SanctumPurgingAction,
    SanctumSeverAction,
    SanctumWeaveAction,
)
from world.magic.constants import TargetKind
from world.magic.models import Resonance, SanctumDetails, Thread
from world.magic.serializers_sanctum import (
    HomecomingActionSerializer,
    PurgingActionSerializer,
    SanctifyActionSerializer,
    SanctumDetailsSerializer,
    SanctumThreadSerializer,
    WeaveActionSerializer,
)
from world.magic.views_actor import PuppetActorMixin

if TYPE_CHECKING:
    from world.scenes.models import Persona

#: Error detail returned when the request has no active character to act as.
NO_ACTIVE_CHARACTER_DETAIL = "No active character."


def _active_persona_for_request(request) -> Persona:
    """Resolve the request user's ACTIVE persona — the face they're on (#981).

    Sanctum actions are persona-scoped per `feedback_account_fk_wrong_for_ic_items`
    — alt personas are separate IC identities, and ownership / membership checks
    must run against the persona the player is acting as right now. Lookup:
    account → active RosterEntry → CharacterSheet → `active_persona_for_sheet`
    (the durable worn face, defaulting to PRIMARY). So a player acting as an
    ESTABLISHED alt operates on *that* identity's sanctums and their other faces
    never leak.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        msg = "You must have an active roster entry to act on Sanctums."
        raise DRFValidationError(msg)
    return active_persona_for_sheet(entry.character_sheet)


class SanctumViewSet(PuppetActorMixin, viewsets.ReadOnlyModelViewSet):
    """Read + action endpoints for the player's Sanctum surface.

    `list` returns Sanctums the user has standing in (owns or has woven
    into). `retrieve` is gated by the same standing check. POST actions
    delegate to the seven Actions in ``actions/definitions/sanctum.py``;
    ``ActionResult`` fields map 1:1 to the existing response bodies so the
    contract is preserved (#1497).
    """

    serializer_class = SanctumDetailsSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "feature_instance_id"
    lookup_value_regex = r"\d+"

    def get_serializer_context(self):
        """Resolve the viewer's CharacterSheet once per request.

        Without this, every serialized row re-fires
        ``RosterEntry.for_account(...)`` inside
        ``SanctumDetailsSerializer._viewer_character_sheet``. With this,
        the serializer reads it from context for free.
        """
        ctx = super().get_serializer_context()
        request = self.request
        if request is not None and request.user.is_authenticated:
            from world.roster.models import RosterEntry  # noqa: PLC0415

            entry = RosterEntry.objects.for_account(request.user).first()
            ctx["viewer_character_sheet"] = entry.character_sheet if entry else None
        return ctx

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
            .filter(feature_instance__dissolved_at__isnull=True)
            .distinct()
        )

    # ------------------------------------------------------------------
    # Write endpoints — converge on action.run()
    # ------------------------------------------------------------------
    # Actor resolution (``_resolve_actor``) is inherited from ``PuppetActorMixin``
    # (extracted to ``views_actor.py`` in #1728 so ``SignatureViewSet`` can share it).

    @action(detail=True, methods=["post"], url_path="homecoming")
    def homecoming(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        serializer = HomecomingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = SanctumHomecomingAction().run(
            actor=actor,
            sanctum=sanctum,
            resonance_sacrificed=serializer.validated_data["resonance_sacrificed"],
            narrative_text=serializer.validated_data.get("narrative_text", ""),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=True, methods=["post"], url_path="purging")
    def purging(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        serializer = PurgingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        new_resonance = get_object_or_404(
            Resonance, pk=serializer.validated_data["new_resonance_id"]
        )
        result = SanctumPurgingAction().run(
            actor=actor,
            sanctum=sanctum,
            new_resonance=new_resonance,
            resonance_sacrificed=serializer.validated_data["resonance_sacrificed"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=True, methods=["post"], url_path="weave")
    def weave(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        serializer = WeaveActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = SanctumWeaveAction().run(
            actor=actor,
            sanctum=sanctum,
            slot_kind=serializer.validated_data["slot_kind"],
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        thread = Thread.objects.get(pk=result.data["thread_id"])
        return Response(SanctumThreadSerializer(thread).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="install")
    def install(self, request):
        """Sanctification entry point — ``POST /api/magic/sanctums/install/``.

        Body: ``{ room_profile_id, resonance_type_id, owner_mode, components }``.
        ``components`` is an optional list of the caller's own ``ItemInstance``
        pks (the Sanctification Ritual's touchstone/reagent
        ``RitualComponentRequirement`` rows, #707) — explicit selection,
        validated to belong to the requesting sheet by
        ``SanctifyActionSerializer.validate_components``.
        Wraps :class:`actions.definitions.sanctum.SanctumInstallAction`
        — action does the heavy validation (room ownership, leader
        standing, physical presence, partial-unique race window). Returns
        the new SanctumDetails on success.
        """
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        serializer = SanctifyActionSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        room_profile = get_object_or_404(
            RoomProfile, pk=serializer.validated_data["room_profile_id"]
        )
        resonance = get_object_or_404(Resonance, pk=serializer.validated_data["resonance_type_id"])
        result = SanctumInstallAction().run(
            actor=actor,
            room_profile=room_profile,
            resonance=resonance,
            owner_mode=serializer.validated_data["owner_mode"],
            components_provided=serializer.validated_data.get("components", []),
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        if result.data["fizzled"]:
            return Response(result.data, status=status.HTTP_200_OK)
        sanctum = SanctumDetails.objects.get(pk=result.data["sanctum_id"])
        return Response(
            {
                **SanctumDetailsSerializer(sanctum, context={"request": request}).data,
                "fizzled": False,
                "success_level": result.data["success_level"],
                "tier": result.data["tier"],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="dissolve")
    def dissolve(self, request, feature_instance_id=None):
        """Ritual of Dissolution — ``POST /api/magic/sanctums/{id}/dissolve/``.

        Wraps :class:`actions.definitions.sanctum.SanctumDissolveAction`.
        Action enforces physical presence; tiered check determines
        recovery fraction. Returns the dissolution outcome.
        """
        sanctum = self.get_object()
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = SanctumDissolveAction().run(actor=actor, sanctum=sanctum)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=True, methods=["post"], url_path="absorb")
    def absorb(self, request, feature_instance_id=None):
        sanctum = self.get_object()
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        result = SanctumAbsorbAction().run(actor=actor, sanctum=sanctum)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result.data)

    @action(detail=True, methods=["post"], url_path="sever/(?P<thread_id>[0-9]+)")
    def sever(self, request, feature_instance_id=None, thread_id=None):
        sanctum = self.get_object()
        actor = self._resolve_actor(request)
        if actor is None:
            return Response(
                {"detail": NO_ACTIVE_CHARACTER_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        thread = get_object_or_404(
            Thread,
            pk=thread_id,
            target_sanctum_details=sanctum,
            owner=actor.sheet_data,
            target_kind=TargetKind.SANCTUM,
        )
        result = SanctumSeverAction().run(actor=actor, thread=thread)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

"""API viewsets for proclamations (#2842)."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.proclamations.models import (
    DomainEdict,
    EdictKind,
    Proclamation,
    StanceArchetype,
)
from world.proclamations.serializers import (
    DomainEdictSerializer,
    EdictKindSerializer,
    ProclamationSerializer,
    StanceArchetypeSerializer,
)
from world.proclamations.services import (
    enact_edict,
    issue_proclamation,
    revoke_edict,
)


class StanceArchetypeViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve stance archetypes."""

    queryset = StanceArchetype.objects.all()
    serializer_class = StanceArchetypeSerializer


class ProclamationViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve proclamations + custom issue action."""

    queryset = Proclamation.objects.select_related("issuer", "stance", "org")
    serializer_class = ProclamationSerializer

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def issue(self, request):
        """Issue a proclamation. Expects ``stance`` (name) and optional ``prose``."""
        from world.scenes.models import Persona  # noqa: PLC0415

        stance_name = request.data.get("stance")
        prose = request.data.get("prose", "")
        if not stance_name:
            return Response({"error": "stance is required"}, status=400)
        try:
            stance = StanceArchetype.objects.get(name=stance_name)
        except StanceArchetype.DoesNotExist:
            return Response({"error": "stance not found"}, status=404)

        persona = Persona.objects.filter(character_sheet__account=request.user).first()
        if persona is None:
            return Response({"error": "no active persona"}, status=403)

        result = issue_proclamation(persona, stance, prose=prose)
        return Response(ProclamationSerializer(result.proclamation).data, status=201)


class EdictKindViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve edict kinds."""

    queryset = EdictKind.objects.select_related("stance")
    serializer_class = EdictKindSerializer


class DomainEdictViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve domain edicts + enact/revoke actions."""

    queryset = DomainEdict.objects.select_related("domain", "kind", "proclamation")
    serializer_class = DomainEdictSerializer

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def enact(self, request):
        """Enact an edict. Expects ``domain`` (id), ``kind`` (name), ``proclamation`` (id)."""
        from world.societies.houses.models import Domain  # noqa: PLC0415

        domain_id = request.data.get("domain")
        kind_name = request.data.get("kind")
        proclamation_id = request.data.get("proclamation")
        if not domain_id or not kind_name or not proclamation_id:
            return Response({"error": "domain, kind, and proclamation are required"}, status=400)
        try:
            domain = Domain.objects.get(pk=domain_id)
            kind = EdictKind.objects.get(name=kind_name)
            proc = Proclamation.objects.get(pk=proclamation_id)
        except (Domain.DoesNotExist, EdictKind.DoesNotExist, Proclamation.DoesNotExist):
            return Response({"error": "not found"}, status=404)

        edict = enact_edict(domain, kind, proc)
        return Response(DomainEdictSerializer(edict).data, status=201)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def revoke(self, request):
        """Revoke the active edict on a domain. Expects ``domain`` (id)."""
        from world.societies.houses.models import Domain  # noqa: PLC0415

        domain_id = request.data.get("domain")
        if not domain_id:
            return Response({"error": "domain is required"}, status=400)
        try:
            domain = Domain.objects.get(pk=domain_id)
        except Domain.DoesNotExist:
            return Response({"error": "not found"}, status=404)

        edict = revoke_edict(domain)
        if edict is None:
            return Response({"error": "no active edict"}, status=404)
        return Response(DomainEdictSerializer(edict).data, status=200)

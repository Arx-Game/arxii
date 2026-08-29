"""Read-only NPC statline preset catalog ViewSet (#3427)."""

from __future__ import annotations

from django.db.models import Prefetch
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.gm.permissions import IsGMOrStaff
from world.roster.models import NPCPresetSkillLine, NPCPresetTraitLine, NPCStatlinePreset
from world.roster.serializers import NPCStatlinePresetSerializer


class NPCStatlinePresetPagination(PageNumberPagination):
    """Default pagination for the NPC statline preset catalog.

    A generous page size: the mint dialog's Select wants the whole catalog
    in one page (a starter catalog of a handful of archetypes, not hundreds),
    not a paginated picker.
    """

    page_size = 100


class NPCStatlinePresetViewSet(ReadOnlyModelViewSet):
    """Read-only catalog listing feeding the Story-NPC mint dialog's preset picker.

    Mirrors ``combat.views.ThreatPoolViewSet``'s shape (flat, unfiltered
    catalog browse via ``SearchFilter`` on ``name``) but gated ``IsGMOrStaff``
    rather than any-authenticated-user, since presets have exactly one
    consumer today: the GM mint dialog (#3426's ``GMDashboardPage``) and its
    telnet counterpart (``gm npc ... preset=<name>``).
    """

    # to_attr deliberately reuses each relation's own related_name: Django
    # replaces the reverse-FK manager on prefetched instances with a plain
    # list under that name, and DRF's nested-serializer field (see
    # NPCStatlinePresetSerializer) handles a plain list exactly like a
    # manager (it only calls .all() when the attribute IS a Manager) — so
    # the serializer needs no prefetch-aware branching, unlike
    # CreatureTemplateSerializer's getattr(..., "cached_phase_templates")
    # (a distinct name, since that field renders a derived bool, not a
    # nested list).
    queryset = NPCStatlinePreset.objects.all().prefetch_related(
        Prefetch(
            "trait_lines",
            queryset=NPCPresetTraitLine.objects.select_related("trait"),
            to_attr="trait_lines",
        ),
        Prefetch(
            "skill_lines",
            queryset=NPCPresetSkillLine.objects.select_related("skill", "skill__trait"),
            to_attr="skill_lines",
        ),
    )
    serializer_class = NPCStatlinePresetSerializer
    permission_classes = [IsGMOrStaff]
    pagination_class = NPCStatlinePresetPagination
    filter_backends = [SearchFilter]
    search_fields = ["name"]

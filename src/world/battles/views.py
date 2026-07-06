"""ViewSet for the read-only battle aggregate API (#2009)."""

from __future__ import annotations

from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import Serializer
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.battles.models import (
    Battle,
    BattleParticipant,
    BattlePlace,
    BattleSide,
    BattleUnit,
    Fortification,
)
from world.battles.serializers import BattleDetailSerializer, BattleListSerializer
from world.scenes.constants import PersonaType
from world.scenes.models import Persona, Scene
from world.stories.pagination import StandardResultsSetPagination


class BattleViewSet(ReadOnlyModelViewSet):
    """Read-only battle aggregate API — list (slim) and detail (full aggregate).

    Scene-gated exactly like ``CombatEncounterViewSet`` (world/combat/views.py):
    a Battle is a 1:1 extension of scenes.Scene (world/battles/models.py), so
    scene read-visibility alone decides who may see a battle. No participant
    union needed — enlisting in a battle has no bearing here independent of
    scene visibility.
    """

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["scene", "outcome"]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self) -> type[Serializer]:
        if self.action == "list":
            return BattleListSerializer
        return BattleDetailSerializer

    def _detail_prefetches(self) -> list[Prefetch]:
        """Explicit ``to_attr``-cached prefetches for the retrieve-only nested aggregate.

        Every relation the detail serializer nests (sides/places/units/
        participants, plus places' fortifications) is loaded via a ``Prefetch``
        with ``to_attr`` — never a bare string — so the serializer's cache reads
        cost zero extra queries (repo-wide PREFETCH_STRING rule).
        ``BattleSideSerializer``/``BattlePlaceSerializer``/etc. read the
        matching ``cached_*`` attrs via their ``source=`` kwarg.
        """
        return [
            Prefetch(
                "sides",
                queryset=BattleSide.objects.select_related("covenant"),
                to_attr="cached_sides",
            ),
            Prefetch(
                "places",
                queryset=BattlePlace.objects.select_related(
                    "battle", "combat_encounter"
                ).prefetch_related(
                    Prefetch(
                        "fortifications",
                        queryset=Fortification.objects.all(),
                        to_attr="cached_fortifications",
                    ),
                ),
                to_attr="cached_places",
            ),
            Prefetch("units", queryset=BattleUnit.objects.all(), to_attr="cached_units"),
            Prefetch(
                "participants",
                queryset=BattleParticipant.objects.select_related(
                    "character_sheet"
                ).prefetch_related(
                    # Pre-fill CharacterSheet.cached_payload_personas (a
                    # @cached_property doubling as this to_attr target) so
                    # BattleParticipantSerializer resolves the PRIMARY persona
                    # with zero per-row queries. Queryset shape mirrors
                    # world/combat/views.py's identical Prefetch (#630) and the
                    # property's own documented fallback (must match exactly, or
                    # prefetched vs. non-prefetched rows diverge).
                    Prefetch(
                        "character_sheet__personas",
                        queryset=Persona.objects.filter(
                            persona_type__in=[PersonaType.PRIMARY, PersonaType.ESTABLISHED]
                        )
                        .order_by("-persona_type", "created_at", "id")
                        .select_related("thumbnail"),
                        to_attr="cached_payload_personas",
                    ),
                ),
                to_attr="cached_participants",
            ),
        ]

    def _base_queryset(self) -> QuerySet[Battle]:
        qs = Battle.objects.order_by("-created_at")
        if self.action == "retrieve":
            qs = qs.prefetch_related(*self._detail_prefetches())
        return qs

    def get_queryset(self) -> QuerySet[Battle]:
        return self._filter_readable(self._base_queryset())

    def _filter_readable(self, qs: QuerySet[Battle]) -> QuerySet[Battle]:
        """Restrict list/retrieve to battles whose scene the caller may view.

        Exact shape of ``CombatEncounterViewSet._filter_readable``
        (world/combat/views.py:262-273) — staff see everything; everyone else
        is scoped to ``Scene.objects.viewable_by``, the single source of truth
        for scene read-visibility.
        """
        user = self.request.user
        if getattr(user, "is_staff", False):  # noqa: GETATTR_LITERAL
            return qs
        return qs.filter(scene__in=Scene.objects.viewable_by(user)).distinct()

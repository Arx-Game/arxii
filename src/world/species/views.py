"""API views for the species app's web surface (#2993 language mechanics)."""

from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.character_sheets.models import CharacterSheet
from world.species.language_constants import fluency_band
from world.species.models import Language
from world.species.serializers import MyLanguageSerializer
from world.species.types import MyLanguageRow
from world.traits.models import CharacterTraitValue


def _caller_character_sheet(request: Request) -> CharacterSheet | None:
    """The requesting account's active character sheet, or None (#2993).

    Mirrors ``world.covenants.views._caller_character_sheet`` (#2640) — the
    tenure-chain scoping that resolves "the" active character for a web
    request, not every character the account has ever played. No active
    tenure (account browsing with no character, or logged out) resolves to
    ``None``.
    """
    return (
        CharacterSheet.objects.filter(
            roster_entry__tenures__end_date__isnull=True,
            roster_entry__tenures__player_data__account=request.user,
        )
        .distinct()
        .first()
    )


@extend_schema(tags=["species"])
class MyLanguagesViewSet(viewsets.ViewSet):
    """Read-only list of the requester's own active character's languages (#2993).

    Self-scoped only — no ``character`` query parameter, unlike the item-first
    visible-worn endpoints. Rows join trained fluency with active-condition
    bonuses (#4090, ``condition_language_bonuses``) — a condition-only language
    appears while the condition lasts. Computed by joining ``Language`` against
    the character's ``CharacterTraitValue`` fluency (one batched query, not
    per-language lookups) and ``CharacterSheet.current_language``.

    No active character (logged out, or an account with no current tenure)
    returns an empty list — never 403/500, matching the visible-worn
    endpoints' out-of-scope-returns-``[]`` contract.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None  # Character-scoped list; small enough to return in full.
    filter_backends = []  # No filterable dimension — always "my active character".
    serializer_class = MyLanguageSerializer

    @extend_schema(responses=MyLanguageSerializer(many=True))
    def list(self, request: Request) -> Response:
        """Return the caller's active character's known languages."""
        sheet = _caller_character_sheet(request)
        if sheet is None:
            return Response([])

        from world.species.language_services import condition_language_bonuses  # noqa: PLC0415

        bonuses = condition_language_bonuses(sheet)
        languages = list(
            Language.objects.filter(
                Q(trait__character_values__character=sheet) | Q(pk__in=list(bonuses))
            )
            .distinct()
            .order_by("name")
        )
        if not languages:
            return Response([])

        trait_ids = [lang.trait_id for lang in languages if lang.trait_id is not None]
        fluency_by_trait = dict(
            CharacterTraitValue.objects.filter(character=sheet, trait_id__in=trait_ids).values_list(
                "trait_id", "value"
            )
        )

        rows: list[MyLanguageRow] = []
        for lang in languages:
            trained = fluency_by_trait.get(lang.trait_id, 0)
            bonus = bonuses.get(lang.pk)
            effective = max(0, trained + bonus.total) if bonus else trained
            # A trained row always shows; a condition-only row only while its bonus is positive.
            if lang.trait_id not in fluency_by_trait and effective <= 0:
                continue
            rows.append(
                MyLanguageRow(
                    language_id=lang.pk,
                    name=lang.name,
                    fluency=trained,
                    band=fluency_band(trained).value,
                    is_current=lang.pk == sheet.current_language_id,
                    effective_fluency=effective,
                    effective_band=fluency_band(effective).value,
                    temporary_sources=bonus.sources if bonus else (),
                )
            )
        serializer = MyLanguageSerializer(rows, many=True)
        return Response(serializer.data)

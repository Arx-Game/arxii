"""Vacancies: staff-marked openings a character enters a family through (#3648).

``reachable_vacancies`` is the CG offer; ``take_vacancy`` is the counted, locked
claim finalize makes. Kin/path rules live in ``character_creation.validators``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet

from world.societies.houses.services import HousesServiceError
from world.societies.models import Vacancy

if TYPE_CHECKING:
    from world.character_creation.models import CharacterDraft


class VacancyExhaustedError(HousesServiceError):
    """The vacancy closed between the pick and finalize (or was deactivated)."""


def _open_filter() -> Q:
    return Q(is_active=True) & (Q(count_remaining__isnull=True) | Q(count_remaining__gt=0))


def reachable_vacancies(draft: CharacterDraft, *, require_open: bool = True) -> QuerySet[Vacancy]:
    """Open vacancies this draft may take: realm, Upbringing gate, trust.

    ``require_open=False`` (``character_creation.validators``, #3648) drops the
    availability filter while keeping every other gate: a vacancy closing
    between pick and finalize is ``take_vacancy``'s ``VacancyExhaustedError``
    graceful-degradation case, not a Lineage-stage validation failure.
    """
    upbringing = draft.selected_origin_template
    if upbringing is None:
        return Vacancy.objects.none()
    queryset = Vacancy.objects.filter(
        Q(allowed_upbringings__isnull=True) | Q(allowed_upbringings=upbringing)
    )
    if require_open:
        queryset = queryset.filter(_open_filter())
    realm = draft.selected_area.realm if draft.selected_area else None
    if realm is not None:
        queryset = queryset.filter(
            Q(organization__family__origin_realm__isnull=True)
            | Q(organization__family__origin_realm=realm)
        )
    account = draft.account
    if not account.is_staff:
        try:
            trust = account.trust
        except AttributeError:
            trust = 0
        queryset = queryset.filter(trust_required__lte=trust)
    return (
        queryset.select_related("organization__family", "rank", "kin_pool", "kin_node")
        .distinct()
        .order_by("organization__name", "sort_order", "name")
    )


def take_vacancy(vacancy_id: int) -> Vacancy:
    """Lock and claim one opening; caller holds ``transaction.atomic()``."""
    locked = Vacancy.objects.select_for_update().get(pk=vacancy_id)
    if not locked.is_open:
        msg = f"vacancy {vacancy_id} is closed"
        raise VacancyExhaustedError(msg, user_message="That opening has been filled.")
    if locked.count_remaining is not None:
        locked.count_remaining -= 1
        locked.save(update_fields=["count_remaining"])
    return locked

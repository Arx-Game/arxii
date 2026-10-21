"""The items a being asks for (#4530, #4462 section 6.4).

A pledge or a rite can list ``RequestedItem`` rows: one item template, or any item carrying
one facet, with a quantity, the points each gives and a hint. They are scavenger-hunt
errands staff set up in advance; a player tracks the item down and gives it up. Giving a
matching item up while the pledge is open (as a sacrifice), or during the rite (as part of
its roll), adds the row's points to that roll as a ``REQUESTED`` meaning signal, until the
row's quantity is filled. There is no carry gate: finding the item is the errand.

Requests are cheap by rule. An item matches only when its template's value is within
``DevotionConfig.requested_item_max_value`` (the one place an item's value is read, and only
as a ceiling: it never adds a point), so money cannot buy a way to ease a roll. A roll eased
by a request cannot come out as a Critical Failure (``sacrifice_services.lift_botch``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.items.constants import MeaningSignalKind
from world.items.types import MeaningSignal

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from world.items.models import ItemInstance
    from world.worship.models import DevotionConfig, PledgeDetails, RequestedItem


@dataclass(frozen=True)
class RequestLine:
    """One request as the pledge card shows it: what is asked, the hint, how many have been
    given up and the points each gives. ``where`` is "pledge" for a sacrifice at the shrine
    and "closing rite" for an item given up while the pledge is closed."""

    request: RequestedItem
    asked_for: str
    hint: str
    quantity: int
    given: int
    points: int
    where: str


def request_matches_item(row: RequestedItem, item: ItemInstance, config: DevotionConfig) -> bool:
    """Whether ``item`` fills ``row``: the template (or an attached facet) matches and the
    template's value is within the ceiling, for both kinds of request."""
    template = item.template
    if template.value > config.requested_item_max_value:
        return False
    if row.item_template_id is not None:
        return template.pk == row.item_template_id
    return any(attached.facet_id == row.facet_id for attached in item.cached_item_facets)


def requested_signal(row: RequestedItem, config: DevotionConfig) -> MeaningSignal:
    """The signal an item filling ``row`` carries: the row's points within the cap."""
    return MeaningSignal(
        MeaningSignalKind.REQUESTED,
        min(row.points, config.requested_item_max_points),
        f"asked for: {row.asked_for}",
    )


def given_count(row: RequestedItem, details: PledgeDetails | None) -> int:
    """How many items have already filled ``row`` for the pledge (0 with no pledge: a
    rite's request outside a pledge is filled afresh by each performance)."""
    from world.ceremonies.models import OfferingSignal  # noqa: PLC0415

    if details is None:
        return 0
    return OfferingSignal.objects.filter(
        requested_item=row, offering__pledge_details=details
    ).count()


def assign_requests(
    rows: Sequence[RequestedItem],
    items: Iterable[ItemInstance],
    *,
    filled: dict[int, int],
    config: DevotionConfig,
) -> dict[int, RequestedItem]:
    """The request each item fills, by item pk, in the order the items are given.

    An item fills the matching row with the most points that still has quantity left
    (``filled`` is how many each row has already had); each item fills at most one row, and
    a row stops matching once its quantity is reached.
    """
    remaining = {row.pk: row.quantity - filled.get(row.pk, 0) for row in rows}
    assigned: dict[int, RequestedItem] = {}
    for item in items:
        fits = [
            row for row in rows if remaining[row.pk] > 0 and request_matches_item(row, item, config)
        ]
        if not fits:
            continue
        best = max(
            fits, key=lambda row: (min(row.points, config.requested_item_max_points), -row.pk)
        )
        remaining[best.pk] -= 1
        assigned[item.pk] = best
    return assigned


def pledge_requests(details: PledgeDetails) -> list[RequestedItem]:
    """The requests an item given up at a shrine while ``details`` is open can fill: the
    pledge's own."""
    return list(
        details.pledge.requested_items.select_related("item_template", "facet").order_by("pk")
    )


def closing_rite_requests(details: PledgeDetails) -> list[RequestedItem]:
    """The requests an item given up during the pledge's closing rite can fill: the pledge's
    own and the closing rite's."""
    from django.db.models import Q  # noqa: PLC0415

    from world.worship.models import RequestedItem  # noqa: PLC0415

    return list(
        RequestedItem.objects.filter(Q(pledge=details.pledge) | Q(rite=details.pledge.closing_rite))
        .select_related("item_template", "facet")
        .order_by("pk")
    )


def request_lines(details: PledgeDetails) -> list[RequestLine]:
    """Every request the pledge card lists, with how many are given: the pledge's own, then
    the closing rite's."""
    return [
        RequestLine(
            request=row,
            asked_for=row.asked_for,
            hint=row.hint,
            quantity=row.quantity,
            given=min(given_count(row, details), row.quantity),
            points=row.points,
            where="pledge" if row.pledge_id is not None else "closing rite",
        )
        for row in closing_rite_requests(details)
    ]

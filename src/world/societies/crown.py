"""The crime ladder's top: tiers, the weighted underworld vote, and the crown (#4061).

Maintainer rulings (2026-09-29):

- A crime organization's tier is what it holds: a crew holds an outdoor room, a
  gang a neighborhood, a family a ward. The Criminal Empire is a recognition
  won by vote, not ground taken.
- The head of an organization holding a majority of a city's *criminal* wards
  (own plus vassals; lawful wards excluded from the count) may call a vote,
  during a sitting term too: that is the ouster.
- Everyone sheeted in the underworld votes, at the weight of the highest seat
  they personally hold (an associate rank in a bigger organization is not a
  seat); NPCs only when a staffer puppets them. Alternate personas voting twice
  is IC cheating, recorded and punished in character, never prevented here.
- The vote runs a real month and is tallied only when it closes. A term is
  three IC years (a real year at 3:1).
- The crown puts the winning family on top: every liege-less crime family in the
  city becomes its vassal at the crown rate (``FealtyEdge`` + tithe) until the
  next crown, and the family holds the city's ``Turf``.

Magnitudes PLACEHOLDER (``CROWN_*``).
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.areas.constants import AreaLevel
from world.societies.constants import CrimeTier, CrownBidStatus

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona
    from world.societies.models import Crown, CrownBid, CrownVote, Organization

logger = logging.getLogger(__name__)


class CrownError(ValueError):
    """A refusal with a line the player reads; the log line is the first argument."""

    def __init__(self, message: str, *, user_message: str) -> None:
        super().__init__(message)
        self.user_message = user_message


CROWN_VOTE_DAYS = 30  # a real month, so every player can get a vote in
CROWN_TERM_DAYS = 365  # three IC years at the 3:1 clock
CROWN_TITHE_PCT = 10  # the crown's cut of every family in the city; PLACEHOLDER
CROWN_START_GRIP = 50  # the crown family's hold on the city turf at recognition; PLACEHOLDER

_TIER_BY_LEVEL = {
    AreaLevel.NEIGHBORHOOD: CrimeTier.GANG,
    AreaLevel.WARD: CrimeTier.FAMILY,
    AreaLevel.CITY: CrimeTier.EMPIRE,
}
_TIER_ORDER = [CrimeTier.CREW, CrimeTier.GANG, CrimeTier.FAMILY, CrimeTier.EMPIRE]


def current_crown(city: Area) -> Crown | None:
    from world.societies.models import Crown  # noqa: PLC0415

    return (
        Crown.objects.filter(city=city, deposed_at__isnull=True)
        .select_related("organization")
        .first()
    )


def crime_tier(org: Organization) -> str | None:
    """The highest rung ``org`` itself holds a Turf on; the crown's family is the Empire."""
    from world.societies.models import Crown, Turf  # noqa: PLC0415

    if Crown.objects.filter(organization=org, deposed_at__isnull=True).exists():
        return CrimeTier.EMPIRE
    best: str | None = None
    for turf in Turf.objects.filter(controlling_org=org).select_related("area"):
        tier = CrimeTier.CREW if turf.area_id is None else _TIER_BY_LEVEL.get(turf.area.level)
        if tier is None:
            continue
        if best is None or _TIER_ORDER.index(tier) > _TIER_ORDER.index(best):
            best = tier
    return best


def criminal_wards(city: Area) -> list[Area]:
    """The city's WARD areas somebody criminal holds; lawful wards do not count."""
    from world.areas.models import Area  # noqa: PLC0415

    return list(
        Area.objects.filter(
            parent=city, level=AreaLevel.WARD, turf__controlling_org__isnull=False
        ).select_related("turf__controlling_org")
    )


def _holds_through_vassals(org: Organization, holder: Organization) -> bool:
    from world.societies.houses.services import vassals_of  # noqa: PLC0415

    if holder.pk == org.pk:
        return True
    return any(v.pk == holder.pk for v in vassals_of(org, recursive=True))


def wards_held(org: Organization, city: Area) -> int:
    return sum(
        1 for ward in criminal_wards(city) if _holds_through_vassals(org, ward.turf.controlling_org)
    )


def may_call_vote(org: Organization, city: Area) -> bool:
    """A strict majority of the city's criminal wards, own plus vassals."""
    wards = criminal_wards(city)
    if not wards:
        return False
    return wards_held(org, city) * 2 > len(wards)


def call_crown_vote(org: Organization, city: Area, called_by: Persona | None) -> CrownBid:
    from world.societies.models import CrownBid  # noqa: PLC0415

    if city.level != AreaLevel.CITY:
        msg = f"area {city.pk} is not a city"
        raise CrownError(msg, user_message="A crown is a city's.")
    if CrownBid.objects.filter(city=city, status=CrownBidStatus.OPEN).exists():
        msg = f"open bid exists in city {city.pk}"
        raise CrownError(msg, user_message="A vote is already open in this city.")
    if not may_call_vote(org, city):
        msg = f"org {org.pk} holds no majority in city {city.pk}"
        raise CrownError(
            msg, user_message="Only a majority of the city's criminal wards may call the vote."
        )
    return CrownBid.objects.create(
        city=city,
        bidder=org,
        called_by=called_by,
        closes_at=timezone.now() + timedelta(days=CROWN_VOTE_DAYS),
    )


def vote_weight(sheet: CharacterSheet) -> int:
    """The highest seat the character personally holds, by tier and rung; 0 = no vote."""
    from world.societies.models import CrimeVoteWeight, OrganizationMembership  # noqa: PLC0415

    memberships = OrganizationMembership.objects.filter(
        persona__character_sheet=sheet, left_at__isnull=True, exiled_at__isnull=True
    ).select_related("organization", "rank")
    weights = {(w.tier, w.rank_tier): w.weight for w in CrimeVoteWeight.objects.all()}
    best = 0
    for membership in memberships:
        tier = crime_tier(membership.organization)
        if tier is None:
            continue
        best = max(best, weights.get((tier, membership.rank.tier), 0))
    return best


def cast_crown_vote(
    bid: CrownBid, sheet: CharacterSheet, persona: Persona | None, *, in_favor: bool
) -> CrownVote:
    """Cast (or re-cast) one character's vote at the weight of their highest seat."""
    from world.societies.models import CrownVote  # noqa: PLC0415

    if bid.status != CrownBidStatus.OPEN or bid.closes_at <= timezone.now():
        msg = f"bid {bid.pk} is closed"
        raise CrownError(msg, user_message="This vote is closed.")
    weight = vote_weight(sheet)
    if weight <= 0:
        msg = f"sheet {sheet.pk} has no seat"
        raise CrownError(msg, user_message="You hold no seat in this city's underworld.")
    vote, _created = CrownVote.objects.update_or_create(
        bid=bid,
        character_sheet=sheet,
        defaults={"persona": persona, "in_favor": in_favor, "weight": weight},
    )
    return vote


def close_crown_bids(*, now=None) -> int:
    """Daily: tally every bid past its close; a passed bid recognizes the crown."""
    from world.societies.models import CrownBid  # noqa: PLC0415

    now = now or timezone.now()
    closed = 0
    for bid in CrownBid.objects.filter(status=CrownBidStatus.OPEN, closes_at__lte=now):
        votes = list(bid.votes.all())
        bid.weight_for = sum(v.weight for v in votes if v.in_favor)
        bid.weight_against = sum(v.weight for v in votes if not v.in_favor)
        passed = bid.weight_for > bid.weight_against and bid.weight_for > 0
        bid.status = CrownBidStatus.PASSED if passed else CrownBidStatus.FAILED
        bid.save(update_fields=["weight_for", "weight_against", "status"])
        if passed:
            recognize_crown(bid, now=now)
        closed += 1
    return closed


def _depose(old_org: Organization, winner: Organization) -> set[int]:
    """Who re-swears when ``old_org`` loses the crown to ``winner``: the deposed family
    itself and every family the old crown held only as crown (a family swears to
    another family only through the crown; its gangs and crews keep their liege).
    The winner's own oath to the old crown is released first, or the deposed
    family's new oath would circle."""
    from world.societies.houses.models import FealtyEdge  # noqa: PLC0415

    own = FealtyEdge.objects.filter(vassal=winner, liege=old_org).first()
    if own is not None:
        if own.obligation_id is not None:
            own.obligation.delete()
        own.delete()
    to_swear = {old_org.pk}
    for edge in FealtyEdge.objects.filter(liege=old_org).select_related("vassal"):
        if crime_tier(edge.vassal) in (CrimeTier.FAMILY, CrimeTier.EMPIRE):
            to_swear.add(edge.vassal_id)
    return to_swear


def _families_in_city(city: Area) -> list[Organization]:
    """Every organization holding a ward's turf under the city."""
    return [ward.turf.controlling_org for ward in criminal_wards(city)]


@transaction.atomic
def recognize_crown(bid: CrownBid, *, now=None) -> Crown:
    """The winning family becomes the city's crown: the old one is deposed, the family
    holds the city's Turf, and every liege-less family in the city (the deposed one
    included, plus the families the old crown held only as crown) swears to it at
    ``CROWN_TITHE_PCT``. A gang or crew genuinely sworn to a family keeps its liege."""
    from world.societies.houses.models import FealtyEdge  # noqa: PLC0415
    from world.societies.houses.services import swear_fealty  # noqa: PLC0415
    from world.societies.models import Crown, Turf  # noqa: PLC0415
    from world.societies.territory import ensure_turf_stream  # noqa: PLC0415
    from world.societies.turf_services import (  # noqa: PLC0415
        _sync_crime_modifier,
        retarget_territory_streams,
    )

    now = now or timezone.now()
    city = bid.city
    winner = bid.bidder
    old = current_crown(city)
    to_swear: set[int] = set()
    if old is not None:
        old.deposed_at = now
        old.save(update_fields=["deposed_at"])
        if old.organization_id != winner.pk:
            to_swear |= _depose(old.organization, winner)
    crown = Crown.objects.create(
        city=city, organization=winner, bid=bid, term_ends_at=now + timedelta(days=CROWN_TERM_DAYS)
    )
    turf, _created = Turf.objects.get_or_create(area=city, room_profile=None)
    turf.controlling_org = winner
    turf.grip = max(turf.grip, CROWN_START_GRIP)
    turf.save(update_fields=["controlling_org", "grip", "updated_at"])
    _sync_crime_modifier(turf)
    ensure_turf_stream(turf)
    retarget_territory_streams(turf)
    for family in _families_in_city(city):
        if family.pk == winner.pk:
            continue
        if not FealtyEdge.objects.filter(vassal=family).exists():
            to_swear.add(family.pk)
    from world.societies.models import Organization  # noqa: PLC0415

    for org in Organization.objects.filter(pk__in=to_swear).exclude(pk=winner.pk):
        swear_fealty(vassal=org, liege=winner, tithe_pct=CROWN_TITHE_PCT)
    logger.info("crown: %s recognized in %s (bid %s)", winner.name, city.name, bid.pk)
    return crown

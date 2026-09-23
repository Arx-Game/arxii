"""The Almanach de Catenys (#3983): the feudal ladder as a service.

A rung is a Title, the Area it decorates and the Domain on that Area. A
count-or-higher rung comes with the seat chain down to the barony that is
its demesne (a duchy also with its county), so every rung's title always has
a seat and the chain never lacks a holder. Every Area on the chain gets its
own Domain row (Domain is 1:1 with Area), and ``owner_org`` is kept in sync
across the whole chain — that's what lets liege lookup walk plain
``Area.parent`` links instead of the (Postgres-only) area closure view. All
writes are explicit service calls; no signals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from world.areas.constants import AreaLevel, GridOrigin
from world.areas.models import Area
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.roster.models import Kinsperson
from world.societies.houses.constants import TIER_TO_AREA_LEVEL, TITLE_TIER_RANK, TitleTier
from world.societies.houses.models import Domain, FealtyEdge, LandShape, Title
from world.societies.houses.services import HousesServiceError, swear_fealty, sync_house_channel
from world.societies.models import Organization, OrganizationRank, Vacancy

if TYPE_CHECKING:
    from world.realms.models import Realm

UNDEFINED_AREA_NAME = "Undefined"
HOUSEHOLD_RANK_TITLE = "Household"

# Which lower rungs come bundled under a top rung, from the top down to the
# barony seat. MARCH is a county-tier holding (shares the county Atlas
# level) and carries the same one-barony seat as a County.
_CHAIN_BELOW: dict[str, tuple[str, ...]] = {
    TitleTier.EMPIRE: (TitleTier.KINGDOM, TitleTier.DUCHY, TitleTier.COUNTY, TitleTier.BARONY),
    TitleTier.KINGDOM: (TitleTier.DUCHY, TitleTier.COUNTY, TitleTier.BARONY),
    TitleTier.DUCHY: (TitleTier.COUNTY, TitleTier.BARONY),
    TitleTier.MARCH: (TitleTier.BARONY,),
    TitleTier.COUNTY: (TitleTier.BARONY,),
    TitleTier.BARONY: (),
}


def _area_name(name: str) -> str:
    return name or UNDEFINED_AREA_NAME


def _family_top(members: list[Title]) -> Title:
    """The highest-ranked title among titles sharing one seat: its own
    family's top rung, the one originally passed to ``plant_rung``."""
    return max(members, key=lambda t: TITLE_TIER_RANK[t.tier])


def _require_chain_top(title: Title) -> list[Title]:
    """Refuse a title that is only an internal member of its own chain — its
    own higher rungs share its own owner, so a liege walk starting from it
    would immediately find "itself" as its nearest held ancestor. Returns
    the full family (all titles sharing ``title``'s seat) for reuse."""
    family = list(Title.objects.filter(seat_domain_id=title.seat_domain_id))
    if _family_top(family).pk != title.pk:
        msg = f"title {title.pk} is not its chain's top title"
        raise HousesServiceError(
            msg, user_message="That title is part of a higher title's own chain."
        )
    return family


def _slug_for(parent: Area | None, tier: str, name: str, *, exclude_pk: int | None = None) -> str:
    """A stable slug: the plain name when one is given, else a
    parent-prefixed, always-numbered placeholder (an "Undefined" rung has no
    name to slugify, and several of them can share a parent).

    ``exclude_pk`` skips the row being renamed itself, so an idempotent
    rename (submitting the same name again) doesn't collide with its own
    still-persisted old slug and bump to ``<slug>-2``.
    """
    if name:
        candidate, n = slugify(name), 1
    else:
        prefix = (parent.slug if parent is not None else None) or "realm"
        base = f"{prefix}-{tier}"
        n = 1
        candidate = f"{base}-{n}"
    conflicts = Area.objects.all()
    if exclude_pk is not None:
        conflicts = conflicts.exclude(pk=exclude_pk)
    while conflicts.filter(slug=candidate).exists():
        n += 1
        candidate = f"{slugify(name)}-{n}" if name else f"{base}-{n}"
    return candidate


def _rung_area(title: Title) -> Area:
    """The Area a title's own rung decorates: its seat chain's Area at the
    title's tier level. A title mid-chain (e.g. the seat barony of a duchy)
    resolves to its own barony-level Area, not the duchy's — callers that
    want "this title's own rung, walked outward" (``liege_for_title``,
    ``assign_holder``) must be given the chain's top title, never an
    internal member, or the walk immediately finds the chain's own higher
    rungs (same owner) and treats the title as its own liege."""
    if title.seat_domain_id is None:
        msg = f"title {title.pk} has no seat domain"
        raise HousesServiceError(msg, user_message="That title has no land on the Atlas.")
    level = TIER_TO_AREA_LEVEL[title.tier]
    area: Area | None = title.seat_domain.area
    while area is not None and area.level != level:
        area = area.parent
    if area is None:
        msg = f"title {title.pk} has no ancestor area at its own rung's level"
        raise HousesServiceError(msg, user_message="That title has no land on the Atlas.")
    return area


def _make_area(*, name: str, tier: str, parent: Area | None, realm: Realm | None) -> Area:
    area = Area(
        name=_area_name(name),
        slug=_slug_for(parent, tier, name),
        level=TIER_TO_AREA_LEVEL[tier],
        parent=parent,
        realm=realm,
        origin=GridOrigin.AUTHORED,
    )
    area.save()
    return area


@transaction.atomic
def plant_rung(
    *,
    realm: Realm,
    tier: str,
    name: str,
    parent_title: Title | None = None,
    held_by: Organization | None = None,
) -> Title:
    """Plant a rung: its Area, a Domain per chain Area, and a Title per
    chain tier, all sharing one seat Domain (the barony at the chain's
    bottom). Unclaimed (``held_by=None``) rungs are left ``is_claimable``.
    """
    parent_area = _rung_area(parent_title) if parent_title is not None else None
    top_area = _make_area(name=name, tier=tier, parent=parent_area, realm=realm)
    chain_areas = [top_area]
    for lower_tier in _CHAIN_BELOW[tier]:
        lower_area = _make_area(name="", tier=lower_tier, parent=chain_areas[-1], realm=realm)
        chain_areas.append(lower_area)
    seat_area = chain_areas[-1]
    seat_domain = Domain.objects.create(
        area=seat_area,
        name=name if seat_area is top_area else "",
        owner_org=held_by,
    )
    for area in chain_areas[:-1]:
        Domain.objects.create(area=area, name=name if area is top_area else "", owner_org=held_by)
    tiers = (tier, *_CHAIN_BELOW[tier])
    titles = [
        Title.objects.create(
            name=name if area is top_area else "",
            tier=rung_tier,
            realm=realm,
            house=held_by,
            seat_domain=seat_domain,
            is_claimable=held_by is None,
        )
        for rung_tier, area in zip(tiers, chain_areas, strict=True)
    ]
    top = titles[0]
    if held_by is not None:
        liege = liege_for_title(top)
        if liege is not None and liege.pk != held_by.pk:
            swear_fealty(vassal=held_by, liege=liege)
    return top


@transaction.atomic
def batch_unclaimed(
    *, parent_title: Title, tier: str, count: int, baronies_per_county: int = 0
) -> list[Title]:
    """Plant ``count`` unclaimed rungs under ``parent_title``. For a
    COUNTY/MARCH batch, also plants ``baronies_per_county`` extra unclaimed
    baronies alongside each county's own seat barony."""
    made: list[Title] = []
    for _ in range(count):
        rung = plant_rung(realm=parent_title.realm, tier=tier, name="", parent_title=parent_title)
        made.append(rung)
        if tier in (TitleTier.COUNTY, TitleTier.MARCH):
            for _ in range(baronies_per_county):
                plant_rung(
                    realm=parent_title.realm, tier=TitleTier.BARONY, name="", parent_title=rung
                )
    return made


@transaction.atomic
def name_rung(title: Title, name: str) -> Title:
    """Name (or rename) a rung: its Title, its own Area, and that Area's
    Domain, regenerating the Area's slug."""
    area = _rung_area(title)
    title.name = name
    title.save(update_fields=["name"])
    area.name = _area_name(name)
    area.slug = _slug_for(area.parent, title.tier, name, exclude_pk=area.pk)
    area.save()
    domain = Domain.objects.filter(area=area).first()
    if domain is not None:
        domain.name = name
        domain.save(update_fields=["name"])
    return title


def liege_for_title(title: Title) -> Organization | None:
    """The holder of the nearest held ancestor rung, walking ``Area.parent``
    upward from ``title``'s own rung. Raises when ``title`` is only an
    internal member of its own chain (see ``_require_chain_top``)."""
    _require_chain_top(title)
    area = _rung_area(title).parent
    while area is not None:
        domain = (
            Domain.objects.filter(pk=area.pk, owner_org__isnull=False)
            .select_related("owner_org")
            .first()
        )
        if domain is not None:
            return domain.owner_org
        area = area.parent
    return None


def _descendant_areas(area: Area) -> list[Area]:
    found: list[Area] = []
    frontier = [area]
    while frontier:
        children = list(Area.objects.filter(parent__in=frontier))
        found.extend(children)
        frontier = children
    return found


@transaction.atomic
def assign_holder(title: Title, house: Organization) -> Title:
    """Seat ``house`` on ``title``'s whole chain, swear it to its own
    nearest liege, and re-home any vassal beneath it that now owes fealty to
    ``house`` instead of whoever it answered to before. Raises when ``title``
    is only an internal member of its own chain (see ``_require_chain_top``).
    """
    family = _require_chain_top(title)
    family_areas = [_rung_area(t) for t in family]
    for member in family:
        member.house = house
        member.is_claimable = False
        member.save(update_fields=["house", "is_claimable"])
    for area in family_areas:
        domain = Domain.objects.get(pk=area.pk)
        domain.owner_org = house
        domain.save(update_fields=["owner_org"])
    title.refresh_from_db()
    liege = liege_for_title(title)
    if liege is not None and liege.pk != house.pk:
        swear_fealty(vassal=house, liege=liege)
    rehome_vassals(title)
    return title


@transaction.atomic
def rehome_vassals(title: Title) -> int:
    """Re-swear every held chain beneath ``title`` whose nearest held
    ancestor is now ``title``'s holder onto it. Returns the number moved."""
    holder = title.house
    if holder is None:
        return 0
    own_area = _rung_area(title)
    own_family = Title.objects.filter(seat_domain_id=title.seat_domain_id)
    own_domain_ids = {_rung_area(t).pk for t in own_family}
    descendant_ids = [a.pk for a in _descendant_areas(own_area)]
    if not descendant_ids:
        return 0
    candidate_org_ids = (
        Domain.objects.filter(pk__in=descendant_ids, owner_org__isnull=False)
        .exclude(pk__in=own_domain_ids)
        .exclude(owner_org=holder)
        .values_list("owner_org_id", flat=True)
        .distinct()
    )
    moved = 0
    for org_id in candidate_org_ids:
        family = list(
            Title.objects.filter(house_id=org_id, seat_domain__area_id__in=descendant_ids)
        )
        if not family:
            continue
        family_top = _family_top(family)
        new_liege = liege_for_title(family_top)
        if new_liege is None or new_liege.pk != holder.pk:
            continue
        current_edge = FealtyEdge.objects.filter(vassal_id=org_id).first()
        if current_edge is not None and current_edge.liege_id == holder.pk:
            continue
        swear_fealty(vassal=family_top.house, liege=holder)
        moved += 1
    return moved


# ---------------------------------------------------------------------------
# House record — state, publication, demesne, estate, household, belief
# ---------------------------------------------------------------------------


def set_house_state(house: Organization, state: str) -> Organization:
    """Set a house's lifecycle standing (standing/in-exile/extinct/gentry)."""
    house.house_state = state
    house.save(update_fields=["house_state"])
    return house


def publish_house(house: Organization) -> Organization:
    """Publish a house to the Almanach and sync its house channel's audience."""
    house.published_at = timezone.now()
    house.save(update_fields=["published_at"])
    sync_house_channel(house)
    return house


def unpublish_house(house: Organization) -> Organization:
    """Pull a published house back to draft."""
    house.published_at = None
    house.save(update_fields=["published_at"])
    return house


@transaction.atomic
def describe_demesne(
    *, domain: Domain, description: str, hall_name: str, land_shape_names: list[str]
) -> Domain:
    """Write a demesne's public description, its hall, and its land shapes.

    The hall may never repeat the demesne's own name: a domain and its seat
    are two distinct nouns (the land, and the building that sits on it), so
    a matching name is refused as a naming mistake rather than accepted.
    """
    if hall_name and hall_name.strip().lower() == (domain.name or "").strip().lower():
        msg = f"hall of domain {domain.pk} repeats the demesne's name"
        raise HousesServiceError(msg, user_message="The hall needs a name of its own.")
    domain.description = description
    if hall_name:
        if domain.hall is None:
            hall = Area(
                name=hall_name,
                slug=_slug_for(domain.area, "hall", hall_name),
                level=AreaLevel.BUILDING,
                parent=domain.area,
                realm=domain.area.realm,
                origin=GridOrigin.AUTHORED,
            )
            hall.save()
            domain.hall = hall
        elif domain.hall.name != hall_name:
            domain.hall.name = hall_name
            domain.hall.save()
    domain.save(update_fields=["description", "hall"])
    domain.land_shapes.set(LandShape.objects.filter(name__in=land_shape_names))
    return domain


@transaction.atomic
def plan_estate(
    *,
    house: Organization,
    city_area: Area,
    name: str,
    description: str,
    district: Area | None = None,
) -> Area:
    """Plant an estate Area under a city (or a named district within it) and
    record the house's active ownership of it."""
    parent = district if district is not None else city_area
    estate = Area(
        name=name,
        slug=_slug_for(parent, "estate", name),
        level=AreaLevel.BUILDING,
        parent=parent,
        realm=city_area.realm,
        description=description,
        origin=GridOrigin.AUTHORED,
    )
    estate.save()
    LocationOwnership.objects.create(
        parent_type=LocationParentType.AREA,
        area=estate,
        holder_type=HolderType.ORGANIZATION,
        holder_organization=house,
    )
    return estate


def _household_rank(house: Organization) -> OrganizationRank:
    """The house's Household rank rung, minted one tier below its current
    lowest rank the first time a household member needs it."""
    rank = house.ranks.filter(name=HOUSEHOLD_RANK_TITLE).first()
    if rank is None:
        lowest = house.ranks.order_by("-tier").first()
        rank = OrganizationRank.objects.create(
            organization=house,
            tier=(lowest.tier + 1) if lowest is not None else 5,
            name=HOUSEHOLD_RANK_TITLE,
        )
    return rank


def add_household_member(
    *, house: Organization, kinsperson: Kinsperson, rank: OrganizationRank | None
) -> Vacancy:
    """Record a household member.

    ``OrganizationMembership.persona`` is non-nullable, so an unsheeted
    Kinsperson (no Persona yet) cannot hold one; the household relation is
    instead a filled Vacancy pointed at the kinsperson (#3983) — present on
    the house's household, off the succession line entirely.
    """
    effective_rank = rank if rank is not None else _household_rank(house)
    return Vacancy.objects.create(
        organization=house,
        name=f"{effective_rank.name}: {kinsperson.name}",
        kin_node=kinsperson,
        rank=effective_rank,
        count_remaining=0,
    )


def record_public_belief(kinsperson: Kinsperson, *, believed_deceased: bool) -> Kinsperson:
    """Set what the public record believes about a kinsperson's death,
    independent of ``is_deceased`` (the private truth)."""
    kinsperson.believed_deceased = believed_deceased
    kinsperson.save(update_fields=["believed_deceased"])
    return kinsperson

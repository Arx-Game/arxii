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
from world.roster.constants import DefinitionTier, MembershipBasis
from world.roster.models import (
    Family,
    FamilyMembership,
    Kinsperson,
    ParentageEdge,
    Union,
    UnionKind,
)
from world.roster.services.kinship import (
    KinshipServiceError,
    add_membership,
    claim_appable_node,
    create_person,
    record_parentage,
    record_union,
)
from world.scenes.constants import PersonaType
from world.societies.houses.constants import (
    TIER_TO_AREA_LEVEL,
    TITLE_TIER_RANK,
    ClaimKinRelation,
    HoldingChoice,
    KinLink,
    LifeStatus,
    TitleTier,
)
from world.societies.houses.models import Domain, DomainHolding, FealtyEdge, LandShape, Title
from world.societies.houses.services import (
    HousesServiceError,
    acknowledge_into_family,
    liege_chain_of,
    recognize_birth,
    release_fealty,
    swear_fealty,
    sync_house_channel,
)
from world.societies.houses.types import CreatedFamily
from world.societies.membership_services import active_membership_for_persona, join_organization
from world.societies.models import Organization, OrganizationRank, Vacancy

if TYPE_CHECKING:
    from collections.abc import Sequence

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


def claim_grants(title: Title) -> list[Title]:
    """Everything a claim on ``title`` seats the house on (#3983 Plan B): the
    title's own seat chain, top first, plus every houseless barony lying
    directly inside one of the chain's areas that is not itself a member of
    another chain (a county's own seat barony stays with its county, never
    listed twice).

    ``_require_chain_top`` returns the family in whatever order the DB
    handed it back (``Title.Meta.ordering`` sorts by tier NAME, so
    alphabetically — not by rank), so this sorts top-first by
    ``TITLE_TIER_RANK`` explicitly; callers rely on that order (a duchy
    claim's grants list duchy, county, then barony, then any loose extras).
    """
    chain = sorted(_require_chain_top(title), key=lambda t: -TITLE_TIER_RANK[t.tier])
    chain_pks = {t.pk for t in chain}
    chain_area_pks = {_rung_area(t).pk for t in chain}
    loose = (
        Title.objects.filter(
            tier=TitleTier.BARONY,
            realm=title.realm,
            house__isnull=True,
            seat_domain__area__parent_id__in=chain_area_pks,
        )
        .exclude(pk__in=chain_pks)
        .select_related("seat_domain__area")
    )
    extras = [
        b
        for b in loose
        if _family_top(list(Title.objects.filter(seat_domain=b.seat_domain))).pk == b.pk
    ]
    return [*chain, *extras]


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


def rung_area_for_title(title: Title) -> Area:
    """The Area a title's own rung decorates (``_rung_area``), for callers outside
    this module such as the world map's carve (#4242)."""
    return _rung_area(title)


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
    if parent_area is not None and TIER_TO_AREA_LEVEL[tier] >= parent_area.level:
        # ``Area.save()`` runs ``full_clean()`` and would raise a bare
        # ``ValidationError`` here (a county under a barony, a march under a
        # county — same Atlas level); refused as a house refusal instead, so
        # every caller gets a sentence it can show (#3983 review M7).
        msg = f"tier {tier} does not nest inside {parent_title.tier}"
        raise HousesServiceError(
            msg, user_message="That rung does not sit beneath the one you picked."
        )
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
        if (
            liege is not None
            and liege.pk != held_by.pk
            and _may_swear_to_containment_liege(held_by, liege)
        ):
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
def delete_rung(title: Title) -> None:
    """Delete a planted rung: its chain's Titles, Domains and Areas together.

    Only a rung that is the top of its own chain, unheld, with no rung or room
    beneath it and no holding on it. Anything else still points at the land and
    is refused with a sentence saying what to clear first.
    """
    from django.db.models import ProtectedError  # noqa: PLC0415

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    family = _require_chain_top(title)
    if any(member.house_id is not None for member in family):
        msg = f"title {title.pk} is held"
        raise HousesServiceError(msg, user_message="That rung is held; vacate it first.")
    areas = [_rung_area(member) for member in family]
    area_pks = {area.pk for area in areas}
    if Area.objects.filter(parent_id__in=area_pks).exclude(pk__in=area_pks).exists():
        msg = f"title {title.pk} has rungs beneath it"
        raise HousesServiceError(
            msg, user_message="Rungs sit beneath it; delete or move them first."
        )
    if DomainHolding.objects.filter(domain__area_id__in=area_pks).exists():
        msg = f"title {title.pk} has holdings"
        raise HousesServiceError(msg, user_message="It has holdings; remove them first.")
    if RoomProfile.objects.filter(area_id__in=area_pks).exists():
        msg = f"title {title.pk} has rooms"
        raise HousesServiceError(msg, user_message="Rooms are placed there; move them first.")
    try:
        with transaction.atomic():
            Title.objects.filter(pk__in=[member.pk for member in family]).delete()
            Domain.objects.filter(pk__in=area_pks).delete()
            for area in sorted(areas, key=lambda a: a.level):
                area.delete()
    except ProtectedError as exc:
        msg = f"title {title.pk} is still referenced"
        raise HousesServiceError(
            msg, user_message="Something else still points at that land."
        ) from exc


@transaction.atomic
def move_rung(title: Title, new_parent: Title) -> Title:
    """Move a rung (its chain, and every rung beneath it) under ``new_parent``.

    Refused for a rung that is not its chain's top, one in another realm, a parent
    that is the rung itself or lies beneath it, a parent of the wrong tier, and any
    rung whose subtree is held (moving it would change the liege of a held house).
    """
    from world.areas.services import area_subtree_pks  # noqa: PLC0415

    family = _require_chain_top(title)
    own_area = _rung_area(title)
    parent_area = _rung_area(new_parent)
    if new_parent.realm_id != title.realm_id:
        msg = f"title {new_parent.pk} is in another realm"
        raise HousesServiceError(msg, user_message="That rung belongs to another realm.")
    subtree = set(area_subtree_pks(own_area))
    if parent_area.pk in subtree:
        msg = f"title {new_parent.pk} lies beneath title {title.pk}"
        raise HousesServiceError(msg, user_message="A rung cannot move beneath itself.")
    if TIER_TO_AREA_LEVEL[title.tier] >= parent_area.level:
        msg = f"tier {title.tier} does not nest inside {new_parent.tier}"
        raise HousesServiceError(
            msg, user_message="That rung does not sit beneath the one you picked."
        )
    if own_area.parent_id == parent_area.pk:
        return title
    held = Title.objects.filter(house__isnull=False).filter(
        seat_domain__area_id__in=subtree
    ) | Title.objects.filter(pk__in=[member.pk for member in family], house__isnull=False)
    if held.exists():
        msg = f"title {title.pk} has held rungs in its subtree"
        raise HousesServiceError(msg, user_message="A rung beneath it is held; vacate those first.")
    own_area.parent = parent_area
    own_area.save()
    return title


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


def _may_swear_to_containment_liege(holder: Organization, liege: Organization) -> bool:
    """Whether ``holder`` should be sworn to a merely-containing ``liege``
    (#3983 Decision 3, the Seawatch-inside-Ardor case): a house's own barony
    sitting inside another house's county is HELD, not sworn, when the
    holder already has a real fealty of its own, or when ``liege`` is
    actually beneath ``holder`` in the tree (the crown's own barony inside
    one of its vassal's counties must never make the crown that vassal's
    vassal)."""
    if FealtyEdge.objects.filter(vassal=holder).exists():
        return False
    return holder not in liege_chain_of(liege)


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
    if liege is not None and liege.pk != house.pk and _may_swear_to_containment_liege(house, liege):
        swear_fealty(vassal=house, liege=liege)
    rehome_vassals(title)
    return title


@transaction.atomic
def vacate_holder(title: Title) -> Title:
    """Unseat ``title``'s holder from the whole chain, the inverse of ``assign_holder``.

    The chain's titles go back to unheld and claimable and its Domains lose their
    owner. A house that was sworn to the old holder because its land lies beneath
    this rung is re-sworn to the nearest remaining liege, or released when none is
    left. The old holder's own oath upward stays: it is still a house. Raises when
    ``title`` is already vacant or is only an internal member of its own chain.
    """
    family = _require_chain_top(title)
    former = title.house
    if former is None:
        msg = f"title {title.pk} is already vacant"
        raise HousesServiceError(msg, user_message="That title is already vacant.")
    own_area = _rung_area(title)
    family_areas = [_rung_area(t) for t in family]
    for member in family:
        member.house = None
        member.is_claimable = True
        member.save(update_fields=["house", "is_claimable"])
    for area in family_areas:
        domain = Domain.objects.get(pk=area.pk)
        domain.owner_org = None
        domain.save(update_fields=["owner_org"])
    title.refresh_from_db()
    _resettle_vassals_of(former, own_area)
    return title


def _resettle_vassals_of(former: Organization, own_area: Area) -> None:
    """Re-swear the houses beneath ``own_area`` that answered to ``former`` (see
    ``vacate_holder``): to their new nearest holder, or free when there is none."""
    descendant_ids = [a.pk for a in _descendant_areas(own_area)]
    if not descendant_ids:
        return
    candidate_org_ids = (
        Domain.objects.filter(pk__in=descendant_ids, owner_org__isnull=False)
        .exclude(owner_org=former)
        .values_list("owner_org_id", flat=True)
        .distinct()
    )
    for org_id in candidate_org_ids:
        edge = FealtyEdge.objects.filter(vassal_id=org_id, liege=former).first()
        if edge is None:
            continue
        beneath = list(
            Title.objects.filter(house_id=org_id, seat_domain__area_id__in=descendant_ids)
        )
        if not beneath:
            continue
        family_top = _family_top(beneath)
        new_liege = liege_for_title(family_top)
        if new_liege is None:
            release_fealty(edge)
        elif new_liege.pk != former.pk:
            swear_fealty(vassal=family_top.house, liege=new_liege)


def _may_rehome_to(
    *, vassal: Organization, holder: Organization, current_edge: FealtyEdge | None
) -> bool:
    """Whether a house holding land beneath a freshly seated rung should be
    re-sworn to its new holder (#3983 Decision 3).

    Interposition is the only case that moves an oath: a house sworn to the
    crown by containment, with a duke now seated between them, owes the
    duke. Everything else stays HELD, not sworn —

    - a house ``holder`` itself answers to (the crown's own loose barony
      lying inside one of its vassals' counties). Swearing that back would
      invert the tree, and ``swear_fealty``'s cycle guard would raise and
      roll the whole seating back;
    - a house whose real fealty is elsewhere entirely, which merely owns one
      barony down here. Its primary ``FealtyEdge`` (and its tithe) are not
      this rung's to delete.
    """
    if vassal.pk == holder.pk:
        return False
    holder_chain = liege_chain_of(holder)
    if any(org.pk == vassal.pk for org in holder_chain):
        return False
    if current_edge is None:
        return True
    return any(org.pk == current_edge.liege_id for org in holder_chain)


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
        if not _may_rehome_to(vassal=family_top.house, holder=holder, current_edge=current_edge):
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


_VACANCY_NAME_MAX = 120
WARD_POSITION_LABEL = "Ward"
_WARD_TITLE_PREFIX = f"{WARD_POSITION_LABEL}: "


def _ward_title(node: Kinsperson) -> str:
    """The Vacancy name a ward's own household row is KEYED by: "Ward: <name>",
    or plain "Ward" for a ward still to be named. ``Vacancy`` is unique on
    (organization, name), so the key has to carry the person — what the row is
    CALLED is ``household_position_label``'s answer, not this."""
    name = node.display_name
    title = f"{_WARD_TITLE_PREFIX}{name}" if name else WARD_POSITION_LABEL
    return title[:_VACANCY_NAME_MAX]


def household_position_label(vacancy_name: str) -> str:
    """What a household row is CALLED, given the name its Vacancy is keyed by.

    A ward's key carries the ward's own name only to keep the row unique
    (``_ward_title``); reading it back verbatim would make the household read
    "Marisol · Ward: Marisol", the holder's name twice. So a ward row is
    simply a "Ward", and every other row — an open post, or a titled place
    staff filled — is called exactly what it is titled.
    """
    if vacancy_name == WARD_POSITION_LABEL or vacancy_name.startswith(_WARD_TITLE_PREFIX):
        return WARD_POSITION_LABEL
    return vacancy_name


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


@transaction.atomic
def add_household_member(
    *,
    house: Organization,
    kinsperson: Kinsperson,
    rank: OrganizationRank | None = None,
    position: str = "",
) -> Vacancy:
    """Record a household member as a filled retainer Vacancy (#3983).

    Never ``kin_node``/``kin_pool``: those mark a KIN vacancy (Recipe 11,
    ``docs/systems/family-authoring-recipes.md``) that puts the holder on the
    family's claim path — a household member is staff/service-placed, not
    appable. A sheeted kinsperson with a primary persona additionally gets a
    real ``OrganizationMembership`` at the Household rank, so a sheeted
    household member is a genuine member, not just a filled slot.

    ``position`` titles a named place (a Steward, a Master-at-arms staff are
    filling); left blank it falls back to the member's own ward title, which
    is what keeps a second ward from taking the first's row — ``Vacancy`` is
    unique on (organization, name), so a shared default would collide for
    any caller, not just ``record_kin``.
    """
    if house.family_id is None:
        msg = f"house {house.pk} has no family on record"
        raise HousesServiceError(msg, user_message="That house has no family on record.")
    effective_rank = rank if rank is not None else _household_rank(house)
    vacancy, _created = Vacancy.objects.update_or_create(
        organization=house,
        name=position or _ward_title(kinsperson),
        defaults={
            "rank": effective_rank,
            "holder_kinsperson": kinsperson,
            "count_remaining": 0,
            "is_active": True,
        },
    )
    persona = None
    if kinsperson.sheet_id is not None:
        persona = kinsperson.sheet.personas.filter(persona_type=PersonaType.PRIMARY).first()
    if persona is not None and active_membership_for_persona(house, persona) is None:
        join_organization(house, persona, rank=effective_rank, vacancy=vacancy)
    return vacancy


@transaction.atomic
def open_household_position(*, house: Organization, position: str) -> Vacancy:
    """Post an OPEN household position — a title with nobody in it yet (#3983).

    The counterpart of ``add_household_member``: that one records a person
    the house already has, this one records a post the house has yet to fill
    ("Master-at-arms · position · open" on the plate). No ``Kinsperson`` is
    minted for it — a post is not a person, and inventing a phantom NPC to
    hold it is exactly the defect this replaces — so the row is a retainer
    Vacancy at the same Household rank with ``count_remaining=1`` and no
    holder. ``Vacancy`` is unique on (organization, name), so re-posting the
    same title re-opens the existing row rather than colliding; an existing
    holder on that row is left alone (filling a post is
    ``add_household_member``'s job, never this one's).
    """
    if house.family_id is None:
        msg = f"house {house.pk} has no family on record"
        raise HousesServiceError(msg, user_message="That house has no family on record.")
    title = position.strip()
    if not title:
        msg = f"house {house.pk} household position has no title"
        raise HousesServiceError(msg, user_message="Name the position.")
    vacancy, _created = Vacancy.objects.update_or_create(
        organization=house,
        name=title[:_VACANCY_NAME_MAX],
        defaults={"rank": _household_rank(house), "count_remaining": 1, "is_active": True},
    )
    return vacancy


def record_public_belief(kinsperson: Kinsperson, *, believed_deceased: bool) -> Kinsperson:
    """Set what the public record believes about a kinsperson's death,
    independent of ``is_deceased`` (the private truth)."""
    kinsperson.believed_deceased = believed_deceased
    kinsperson.save(update_fields=["believed_deceased"])
    return kinsperson


def _record_kin_edges(  # noqa: PLR0913 — mirrors record_kin edge inputs
    *, node, parent, parents, child, spouse, marriage_kind
) -> None:
    """Write the kinship edges requested for one house-tree node."""
    for parent_node in (parent, *parents):
        if parent_node is not None:
            record_parentage(child=node, parent=parent_node)
    if child is not None:
        record_parentage(child=child, parent=node)
    if spouse is not None:
        record_union(kind=marriage_kind, members=[node, spouse])


def _record_kin_memberships(*, house, node, relation, basis, born_into) -> None:
    """Apply relation-based memberships for one house-tree node."""
    if relation == ClaimKinRelation.HEAD:
        has_members = (
            FamilyMembership.objects.filter(family=house.family, ended_at__isnull=True)
            .exclude(kinsperson=node)
            .exists()
        )
        head_basis = MembershipBasis.BORN if has_members else MembershipBasis.FOUNDING
        add_membership(kinsperson=node, family=house.family, basis=head_basis)
    elif relation == ClaimKinRelation.SPOUSE:
        add_membership(kinsperson=node, family=house.family, basis=MembershipBasis.MARRIED_IN)
    elif relation == ClaimKinRelation.CHILD and not basis:
        if recognize_birth(node) is None:
            acknowledge_into_family(node, house.family)
    elif basis:
        add_membership(kinsperson=node, family=house.family, basis=basis)

    if born_into is not None:
        add_membership(
            kinsperson=node, family=born_into, basis=MembershipBasis.BORN, is_primary=False
        )


@transaction.atomic
def record_kin(  # noqa: PLR0913 — keyword-only public service API
    *,
    house: Organization,
    name: str,
    relation: str,
    gender: object | None = None,
    age: int | None = None,
    is_deceased: bool = False,
    believed_deceased: bool = False,
    parent: Kinsperson | None = None,
    parents: Sequence[Kinsperson] = (),
    child: Kinsperson | None = None,
    spouse: Kinsperson | None = None,
    marriage_kind: UnionKind | None = None,
    born_into: Family | None = None,
    basis: str = "",
    is_household: bool = False,
    tier: str = DefinitionTier.NAME_ONLY,
    node: Kinsperson | None = None,
) -> tuple[Kinsperson, Vacancy | None]:
    """Author one node of a house's family tree (#3983 Plan B).

    The shared kin-writing engine: moved verbatim off the staff
    ``almanach_edit_kin`` action's own create branch and generalized so
    founder finalize (``materialize_house_claim``) can place a founder-
    written kin tree through the same seam, including placing the founder's
    OWN already-existing node (pass it as ``node`` instead of a bare name).

    A blank ``name`` on a freshly created node marks a future app-in slot —
    shaped exactly like the nodes ``open_slots_for`` surfaces
    (``is_appable=True``, no sheet): a nameless kin row isn't a dead end,
    it's an invitation.

    Edges (``parent``/``parents``/``child``/``spouse``) are wired
    unconditionally whenever given, independent of ``relation``. Membership
    is relation-driven: HEAD gets FOUNDING (or BORN when the family already
    has a member other than this node) and SPOUSE gets MARRIED_IN, always;
    CHILD with no explicit ``basis`` runs the same realm-recognition walk
    the action always used (``recognize_birth`` falling back to
    ``acknowledge_into_family``); any relation WITH an explicit ``basis``
    (the materialize path, for MOTHER/FATHER/GRANDPARENT/SIBLING/CHILD rows
    the founder wrote in directly) joins the house's family on that basis.
    WARD rows never get a family membership — household retainers are
    staff/service-placed, not family (#3983 Decision 1) — so callers placing
    one must leave ``basis`` empty. A POSITION is refused outright: an open
    household post has no person in it, so it is a bare Vacancy
    (``open_household_position``), never a Kinsperson.
    """
    if house.family_id is None:
        msg = f"house {house.pk} has no family on record"
        raise HousesServiceError(msg, user_message="That house has no family on record.")
    if relation == ClaimKinRelation.POSITION:
        msg = f"house {house.pk}: a household POSITION is not a person"
        raise HousesServiceError(msg, user_message="A position is a post, not a person.")
    if node is None:
        node = Kinsperson.objects.create(
            definition_tier=tier,
            name=name,
            gender=gender,
            age=age,
            is_deceased=is_deceased,
            is_appable=not name,
        )

    _record_kin_edges(
        node=node,
        parent=parent,
        parents=parents,
        child=child,
        spouse=spouse,
        marriage_kind=marriage_kind,
    )
    _record_kin_memberships(
        house=house, node=node, relation=relation, basis=basis, born_into=born_into
    )

    vacancy = None
    if is_household:
        # One household row per person, keyed by the person: ``Vacancy``
        # is unique on (organization, name), so naming every ward "Ward"
        # made the second ward overwrite the first's holder (the key is
        # ``add_household_member``'s own default now). A POSITION is not a
        # person at all and never comes through here (the guard at the top
        # of this function) — it is ``open_household_position``'s row.
        vacancy = add_household_member(house=house, kinsperson=node)

    if believed_deceased:
        record_public_belief(node, believed_deceased=True)

    return node, vacancy


# ---------------------------------------------------------------------------
# #4239: every family, every person. Entry points that compose the services
# above and the kinship writers, so staff never open the admin for the next
# linked part. Each refusal carries a ``user_message``; each runs atomically.
# ---------------------------------------------------------------------------

_TIER_ORDER = [
    DefinitionTier.NAME_ONLY,
    DefinitionTier.FUNCTIONARY,
    DefinitionTier.STANDING,
    DefinitionTier.SHEETED,
    DefinitionTier.PC,
]
_PC_LOCKED = "A player character's name, tier and death are recorded from play, not here."


def _as_houses_error(exc: KinshipServiceError) -> HousesServiceError:
    return HousesServiceError(str(exc), user_message=exc.user_message)


def _family_org(family: Family) -> Organization | None:
    """The organization standing behind ``family``, if it has taken any (#4239).

    Lowest pk, the same choice the player family page makes
    (``roster/views/family_views.py``), so the two surfaces agree on which
    organization is the house.
    """
    return Organization.objects.filter(family=family).order_by("pk").first()


@transaction.atomic
def create_family(  # noqa: PLR0913 — keyword-only; one arg per form field
    *,
    kind,
    name: str,
    realm: Realm | None,
    created_by=None,
    template=None,
    holding: str = HoldingChoice.NONE,
    title_tier: str | None = None,
    title_name: str | None = None,
    parent_title: Title | None = None,
    holder: Kinsperson | None = None,
    home_domain: Domain | None = None,
) -> CreatedFamily:
    """Create Family (#4239): a Family row, and standing only when asked for.

    With no template and no holding the family stands alone: an orphan's
    dozen NPC relatives need no organization. A family type that styles as
    a house, a template, or any holding choice builds the organization through
    ``build_family_org`` (ADR-0268). ``holding``: CREATE plants a domain and
    title under ``parent_title`` held by the new house; VACANT assigns the
    unclaimed ``parent_title`` to it; NONE adds no land. ``holder`` becomes the
    title's personal holder and, if not yet of the family, its head.
    """
    from world.societies.houses.creator import build_family_org  # noqa: PLC0415

    name = (name or "").strip()
    if not name:
        msg = "blank family name"
        raise HousesServiceError(msg, user_message="A family needs a name.")
    if Family.objects.filter(name=name).exists():
        msg = f"family {name!r} exists"
        raise HousesServiceError(msg, user_message="A family of that name already exists.")
    needs_org = template is not None or holding != HoldingChoice.NONE or bool(kind.styles_as_house)
    if not needs_org:
        family = Family.objects.create(
            name=name, kind=kind, origin_realm=realm, created_by=created_by
        )
        return CreatedFamily(family=family, organization=None, title=None)
    if template is None:
        msg = "template required"
        raise HousesServiceError(msg, user_message="Pick a family type for this realm.")
    family, org = build_family_org(
        template, name, origin_realm=realm, created_by=created_by, home_domain=home_domain
    )
    title = _take_holding(
        org,
        realm=realm,
        holding=holding,
        title_tier=title_tier,
        title_name=title_name,
        parent_title=parent_title,
    )
    if title is not None and holder is not None:
        if not FamilyMembership.objects.filter(
            kinsperson=holder, family=family, ended_at__isnull=True
        ).exists():
            record_kin(house=org, name=holder.name, relation=ClaimKinRelation.HEAD, node=holder)
        set_personal_holder(title=title, node=holder)
    return CreatedFamily(family=family, organization=org, title=title)


def _take_holding(  # noqa: PLR0913 — keyword-only; the holding block's fields
    org: Organization,
    *,
    realm: Realm | None,
    holding: str,
    title_tier: str | None,
    title_name: str | None,
    parent_title: Title | None,
) -> Title | None:
    """The holding block of Create Family (#4239): plant, assign, or nothing."""
    if holding == HoldingChoice.CREATE:
        if realm is None or not title_tier or not title_name:
            msg = "holding incomplete"
            raise HousesServiceError(
                msg, user_message="A new domain needs a realm, a tier and a name."
            )
        return plant_rung(
            realm=realm, tier=title_tier, name=title_name, parent_title=parent_title, held_by=org
        )
    if holding == HoldingChoice.VACANT:
        if (
            parent_title is None
            or parent_title.house_id is not None
            or (realm is not None and parent_title.realm_id != realm.pk)
        ):
            msg = "bad vacant title"
            raise HousesServiceError(msg, user_message="That title is not open in this realm.")
        return assign_holder(parent_title, org)
    return None


@transaction.atomic
def found_organization(*, family: Family, template, created_by=None) -> Organization:
    """Give a family that already has people its organization (#4239)."""
    from world.societies.houses.creator import build_family_org  # noqa: PLC0415

    existing = _family_org(family)
    if existing is not None:
        msg = f"family {family.pk} already has organization {existing.pk}"
        raise HousesServiceError(msg, user_message="That family already has an organization.")
    _family, org = build_family_org(
        template,
        family.name,
        origin_realm=family.origin_realm,
        created_by=created_by,
        existing_family=family,
    )
    return org


@transaction.atomic
def create_kin(  # noqa: PLR0913 — keyword-only; one arg per form field
    *,
    family: Family,
    name: str,
    tier: str = DefinitionTier.NAME_ONLY,
    gender=None,
    age: int | None = None,
    created_by=None,
) -> Kinsperson:
    """Create Kin (#4239): a person with nothing but a family.

    Writes the node and a BORN membership through ``create_person``; needs
    no organization and no relation. Links come afterwards (``link_kin``).
    """
    if tier not in (DefinitionTier.NAME_ONLY, DefinitionTier.FUNCTIONARY, DefinitionTier.STANDING):
        msg = "bad tier"
        raise HousesServiceError(
            msg, user_message="A new person is tier 0, 1 or 2; a sheet comes later."
        )
    return create_person(
        name=(name or "").strip(),
        tier=tier,
        family=family,
        gender=gender,
        age=age,
        created_by=created_by,
    )


@transaction.atomic
def link_kin(
    *,
    node: Kinsperson,
    other: Kinsperson,
    link: str,
    union_kind: UnionKind | None = None,
    is_public_record: bool = True,
) -> ParentageEdge | Union:
    """Relate ``node`` to anyone in any family (#4239).

    PARENT: ``other`` is ``node``'s parent. CHILD: ``node`` is ``other``'s
    parent. SPOUSE: one Union both families' trees read; when the kind
    confers wedlock and ``node``'s family has an organization, ``other`` joins
    that family MARRIED_IN unless already of it.
    """
    if node.pk == other.pk:
        msg = "self link"
        raise HousesServiceError(msg, user_message="A person cannot be linked to themself.")
    try:
        if link == KinLink.PARENT:
            return record_parentage(child=node, parent=other, is_public_record=is_public_record)
        if link == KinLink.CHILD:
            return record_parentage(child=other, parent=node, is_public_record=is_public_record)
        if link == KinLink.SPOUSE:
            if union_kind is None:
                msg = "union kind required"
                raise HousesServiceError(msg, user_message="Pick the kind of union.")
            union = record_union(
                kind=union_kind, members=[node, other], is_public_record=is_public_record
            )
            if (
                union_kind.confers_wedlock
                and node.family_id is not None
                and other.family_id != node.family_id
                and not FamilyMembership.objects.filter(
                    kinsperson=other, family_id=node.family_id, ended_at__isnull=True
                ).exists()
            ):
                add_membership(
                    kinsperson=other,
                    family=node.family,
                    basis=MembershipBasis.MARRIED_IN,
                    is_primary=False,
                )
            return union
    except KinshipServiceError as exc:
        raise _as_houses_error(exc) from exc
    msg = "bad link"
    raise HousesServiceError(msg, user_message="A link is parent, child or spouse.")


@transaction.atomic
def correct_parentage(*, edge: ParentageEdge, new_parent: Kinsperson) -> ParentageEdge:
    """Replace a wrong parentage edge with the right parent (#4239).

    The child, the kind, the record and truth flags and any secret carry
    over; nobody is deleted.
    """
    if new_parent.pk == edge.child_id:
        msg = "self parent"
        raise HousesServiceError(msg, user_message="A person cannot be their own parent.")
    kept = {
        "kind": edge.kind,
        "is_public_record": edge.is_public_record,
        "is_true": edge.is_true,
        "born_within_union": edge.born_within_union,
        "secret": edge.secret,
    }
    child = edge.child
    edge.delete()
    try:
        return record_parentage(child=child, parent=new_parent, **kept)
    except KinshipServiceError as exc:
        raise _as_houses_error(exc) from exc


@transaction.atomic
def set_life_status(
    *,
    node: Kinsperson,
    status: str,
    record_accurate: bool = True,
    obituary: str = "",
) -> Kinsperson:
    """Status Alive / RIP / Missing, what the record says, and in what words (#4239).

    The truth is ``is_deceased`` / ``is_missing``; the record is
    ``believed_deceased`` (equal to the truth when accurate, its inverse
    otherwise) and ``obituary``. A PC's death is recorded from play.
    """
    if status not in LifeStatus.values:
        msg = "bad status"
        raise HousesServiceError(msg, user_message="Status is Alive, RIP or Missing.")
    is_rip = status == LifeStatus.RIP
    if node.definition_tier == DefinitionTier.PC and is_rip != node.is_deceased:
        msg = "pc death from almanach"
        raise HousesServiceError(msg, user_message=_PC_LOCKED)
    node.is_deceased = is_rip
    node.is_missing = status == LifeStatus.MISSING
    node.believed_deceased = is_rip if record_accurate else not is_rip
    node.obituary = (obituary or "").strip()
    node.save(update_fields=["is_deceased", "is_missing", "believed_deceased", "obituary"])
    return node


def _tier_index(tier: str) -> int:
    try:
        return _TIER_ORDER.index(tier)
    except ValueError as exc:
        msg = "bad tier"
        raise HousesServiceError(msg, user_message="No such tier.") from exc


@transaction.atomic
def attach_sheet(*, node: Kinsperson, sheet) -> Kinsperson:
    """Tie a sheet to a node from the node's side (#4239).

    A sheet on a player shelf makes the node a PC: through
    ``claim_appable_node`` when the node is appable (its constraints hold),
    else by staff fiat. Any other sheet (a Story NPC's) makes it SHEETED.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    if node.sheet_id is not None:
        msg = "node has sheet"
        raise HousesServiceError(msg, user_message="That person already has a sheet.")
    if Kinsperson.objects.filter(sheet=sheet).exists():
        msg = "sheet has node"
        raise HousesServiceError(msg, user_message="That sheet is already someone in the tree.")
    is_player_sheet = (
        RosterEntry.objects.filter(character_sheet=sheet)
        .exclude(roster__roster_type=RosterType.NPC)
        .exists()
    )
    if is_player_sheet and node.is_appable:
        try:
            return claim_appable_node(node=node, sheet=sheet)
        except KinshipServiceError as exc:
            raise _as_houses_error(exc) from exc
    node.sheet = sheet
    node.definition_tier = DefinitionTier.PC if is_player_sheet else DefinitionTier.SHEETED
    node.is_appable = False
    node.save(update_fields=["sheet", "definition_tier", "is_appable"])
    return node


@transaction.atomic
def promote_kin(*, node: Kinsperson, tier: str, gm_account) -> Kinsperson:
    """Raise a node's tier (#4239). Tier only rises; PC is never set here.

    At SHEETED with no sheet, a Story NPC is minted for ``gm_account`` and
    bound to the node (``mint_story_npc`` then ``attach_sheet``); the staffer's
    own OOC character (``mint_gm_character``) is never the tool.
    """
    from world.roster.services.staff_characters import (  # noqa: PLC0415
        StaffMintError,
        mint_story_npc,
    )

    if node.definition_tier == DefinitionTier.PC:
        msg = "pc tier"
        raise HousesServiceError(msg, user_message=_PC_LOCKED)
    if tier == DefinitionTier.PC:
        msg = "pc by fiat"
        raise HousesServiceError(
            msg, user_message="A player character is made by an application, not here."
        )
    if _tier_index(tier) <= _tier_index(node.definition_tier):
        msg = "tier only rises"
        raise HousesServiceError(msg, user_message="Tier only rises.")
    if tier == DefinitionTier.SHEETED:
        if node.sheet_id is None:
            if not node.name:
                msg = "nameless sheet"
                raise HousesServiceError(
                    msg, user_message="Name the person before giving them a sheet."
                )
            try:
                character = mint_story_npc(gm_account=gm_account, name=node.name)
            except StaffMintError as exc:
                # StaffMintError carries a player-safe message and nothing else.
                raise HousesServiceError(str(exc), user_message=str(exc)) from exc
            return attach_sheet(node=node, sheet=character.sheet_data)
        node.definition_tier = DefinitionTier.SHEETED
    else:
        node.definition_tier = tier
    node.save(update_fields=["definition_tier"])
    return node


@transaction.atomic
def set_appable(  # noqa: PLR0913 — keyword-only; one arg per slot constraint
    *,
    node: Kinsperson,
    appable: bool,
    age_min: int | None = None,
    age_max: int | None = None,
    allowed_genders=(),
    name_locked: bool = False,
) -> Kinsperson:
    """Open or close a node to applicants, with its constraints (#4239).

    Read by the roster (``open_slots_for``) and CG (``claim_appable_node``)
    exactly as today; a node with a sheet is never appable.
    """
    if node.sheet_id is not None and appable:
        msg = "sheeted appable"
        raise HousesServiceError(
            msg, user_message="A person with a sheet is not open for claiming."
        )
    if age_min is not None and age_max is not None and age_min > age_max:
        msg = "age range"
        raise HousesServiceError(msg, user_message="The age range is upside down.")
    node.is_appable = appable
    node.age_min = age_min
    node.age_max = age_max
    node.name_locked = name_locked
    node.save(update_fields=["is_appable", "age_min", "age_max", "name_locked"])
    node.allowed_genders.set(list(allowed_genders))
    return node


@transaction.atomic
def set_personal_holder(*, title: Title, node: Kinsperson) -> Title:
    """Name who holds ``title`` in person (#4239): one of the holding house's family."""
    if title.house_id is None or title.house.family_id is None:
        msg = "unheld title"
        raise HousesServiceError(
            msg, user_message="Give the title to a house before naming its holder."
        )
    if not FamilyMembership.objects.filter(
        kinsperson=node, family_id=title.house.family_id, ended_at__isnull=True
    ).exists():
        msg = "holder outside family"
        raise HousesServiceError(msg, user_message="The holder must be of the holding family.")
    title.holder = node
    title.save(update_fields=["holder"])
    return title

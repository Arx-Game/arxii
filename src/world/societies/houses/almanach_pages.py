"""Almanach reads for every family, every person (#4239): the front page's
three rolls and its search, a person's document, a rung's document, a family's
document, and the Books, Forces, Openings and Turf chapters the house
document grows.

Everything here is a read over rows that exist. The ladder and realm graph
come from ``almanach_reads`` (one Title query, one Area query, walked in
memory); the kinship reads come from ``world.roster.services.kinship`` with
the omniscient viewer, since every caller is staff. Payloads are plain dicts
and lists so the serializers stay flat, the same convention as the house
document. Money is in coppers, per cycle (the weekly tick); the full
organizational ledger is #4243 and these numbers are what exists until it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db.models import Count, Q

from world.areas.constants import AreaLevel
from world.areas.models import Area
from world.currency.models import OrganizationTreasury, OrgIncomeStream
from world.military.models import MilitaryUnit
from world.realms.models import Realm
from world.roster.constants import DefinitionTier
from world.roster.models import Family, FamilyMembership, Kinsperson, ParentageEdge, Union
from world.roster.services.kinship import (
    OMNISCIENT,
    children_of,
    family_tree_for,
    parents_of,
    siblings_of,
    spouses_of,
)
from world.scenes.constants import PersonaType
from world.societies.constants import CrimeTier
from world.societies.houses.almanach import _family_org, liege_for_title
from world.societies.houses.almanach_reads import (
    _build_rows,
    _realm_graph,
    _row_for,
    _row_summary,
)
from world.societies.houses.constants import NPC_TIER_LABEL, NPC_TIER_NUMBER, KinLink, LifeStatus
from world.societies.houses.models import Domain, DomainGarrisonPost, DomainHolding, Title
from world.societies.models import (
    CrewSlot,
    Organization,
    OrganizationMembership,
    Turf,
    Vacancy,
)

if TYPE_CHECKING:
    from world.societies.houses.almanach_reads import LadderRow

SEARCH_MIN_CHARS = 2
SEARCH_LIMIT = 20
ROLL_LIMIT = 50


@dataclass
class FrontRolls:
    """The front page: Noble, Crime, Commoner. Without a query each roll is
    its grouping (realms, cities, families); with one, the matching rows."""

    noble: list[dict]
    crime: list[dict]
    commoner: list[dict]


@dataclass
class SearchHit:
    kind: str
    id: int
    name: str
    sub: str


@dataclass
class Books:
    """Income per cycle, what is pooled uncollected, and the treasury balance."""

    income_week: int
    uncollected: int
    treasury: int
    streams: int


@dataclass
class PersonDocument:
    person: dict
    family: dict | None
    kin: list[dict]
    house: dict | None
    titles: list[dict]
    sheet: dict
    memberships: list[dict]
    record: dict


@dataclass
class RungDocument:
    title: dict
    demesne: dict | None
    holdings: list[dict]
    books: dict
    forces: list[dict]
    vassals: list[dict]


@dataclass
class FamilyDocument:
    family: dict
    organization_id: int | None
    tree: dict
    openings: dict


@dataclass
class Openings:
    appable: list[dict] = field(default_factory=list)
    posts: list[dict] = field(default_factory=list)
    vacant_seats: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# shared bits
# ---------------------------------------------------------------------------


def tier_display(tier: str) -> dict:
    """``{"number": 2, "label": "Standing NPC"}``; a PC has no number."""
    return {"number": NPC_TIER_NUMBER.get(tier), "label": NPC_TIER_LABEL.get(tier, tier)}


def life_status(person: Kinsperson) -> str:
    if person.is_deceased:
        return LifeStatus.RIP
    if person.is_missing:
        return LifeStatus.MISSING
    return LifeStatus.ALIVE


_WOMAN_WORDS = ("woman", "female", "girl")
_MAN_WORDS = ("man", "male", "boy")
_SIBLING = "sibling"
_SPOUSE = "spouse"


def _gendered(person: Kinsperson, *, she: str, he: str, other: str) -> str:
    """A kin word by the person's gender: mother/father/parent, daughter/son/child."""
    name = (person.gender.display_name if person.gender_id else "").strip().lower()
    if name and any(name == w or name.startswith(w) for w in _WOMAN_WORDS):
        return she
    if name and any(name == w or name.startswith(w) for w in _MAN_WORDS):
        return he
    return other


def kin_word(person: Kinsperson, link: str, label: str = "") -> str:
    """The word a kin row prints for its relation to the page's person (#4239)."""
    if link == KinLink.PARENT:
        return _gendered(person, she="mother", he="father", other="parent")
    if link == KinLink.CHILD:
        return _gendered(person, she="daughter", he="son", other="child")
    if link == KinLink.SPOUSE:
        return _SPOUSE
    if not label or label == _SIBLING:
        return _gendered(person, she="sister", he="brother", other=_SIBLING)
    return label


def _person_row(person: Kinsperson, *, relation: str = "", link: str = "") -> dict:
    return {
        "id": person.pk,
        "name": person.display_name,
        "relation": relation,
        "link": link,
        "tier": person.definition_tier,
        "tier_display": tier_display(person.definition_tier),
        "status": life_status(person),
        "is_pc": person.definition_tier == DefinitionTier.PC,
        "sheet_id": person.sheet_id,
        "is_appable": person.is_appable and person.sheet_id is None,
        "family_id": person.family_id,
    }


def _primary_persona(person: Kinsperson):
    if person.sheet_id is None:
        return None
    return person.sheet.personas.filter(persona_type=PersonaType.PRIMARY).first()


def books_for(org: Organization | None) -> Books:
    """What exists today of an organization's books; zeros for no organization."""
    if org is None:
        return Books(income_week=0, uncollected=0, treasury=0, streams=0)
    income = 0
    pooled = 0
    count = 0
    for gross, pool in OrgIncomeStream.objects.filter(organization=org, active=True).values_list(
        "gross_amount", "uncollected_pool"
    ):
        income += gross
        pooled += pool
        count += 1
    treasury = OrganizationTreasury.objects.filter(organization=org).first()
    return Books(
        income_week=income,
        uncollected=pooled,
        treasury=treasury.balance if treasury is not None else 0,
        streams=count,
    )


def forces_for(org: Organization | None, *, domain: Domain | None = None) -> list[dict]:
    """The units an organization fields, plus any posted to ``domain``."""
    posted_ids: set[int] = set()
    units: dict[int, MilitaryUnit] = {}
    if domain is not None:
        for post in DomainGarrisonPost.objects.filter(domain=domain).select_related("unit"):
            posted_ids.add(post.unit_id)
            units[post.unit_id] = post.unit
    if org is not None:
        for unit in MilitaryUnit.objects.filter(owner_org=org).select_related("owner_org"):
            units[unit.pk] = unit
    return [
        {
            "unit_id": unit.pk,
            "name": unit.name,
            "owner": unit.owner_org.name if unit.owner_org_id else "",
            "quality": unit.quality,
            "men": unit.individual_count or 0,
            "strength": unit.strength,
            "morale": unit.morale,
            "posted_here": unit.pk in posted_ids,
        }
        for unit in sorted(units.values(), key=lambda u: (u.pk not in posted_ids, u.name))
    ]


def _books_dict(books: Books) -> dict:
    return {
        "income_week": books.income_week,
        "uncollected": books.uncollected,
        "treasury": books.treasury,
        "streams": books.streams,
    }


# ---------------------------------------------------------------------------
# openings and turf: the house document's new chapters
# ---------------------------------------------------------------------------


def openings_for(house: Organization) -> Openings:
    """Everything a player could take up in this house, in one list each:
    appable kin, open household posts, vacant seats sworn beneath it."""
    out = Openings()
    if house.family_id is not None:
        for node in Kinsperson.objects.filter(
            family_id=house.family_id, is_appable=True, sheet__isnull=True
        ).order_by("name"):
            out.appable.append(_person_row(node))
    for vacancy in Vacancy.objects.filter(
        organization=house,
        is_active=True,
        kin_node__isnull=True,
        kin_pool__isnull=True,
        holder_kinsperson__isnull=True,
    ).order_by("name"):
        out.posts.append({"vacancy_id": vacancy.pk, "position": vacancy.name})
    held = list(Title.objects.filter(house=house).values_list("pk", "realm_id"))
    if held:
        held_ids = {pk for pk, _realm in held}
        realm_ids = {realm for _pk, realm in held}
        for realm_id in realm_ids:
            rows, _unclaimed = _build_rows(realm_id)
            for row in rows:
                if row.house_id is None and row.parent_title_id in held_ids:
                    out.vacant_seats.append(_row_summary(row))
    return out


def _openings_dict(openings: Openings) -> dict:
    return {
        "appable": openings.appable,
        "posts": openings.posts,
        "vacant_seats": openings.vacant_seats,
    }


def _boss_name(org: Organization) -> str:
    membership = (
        OrganizationMembership.objects.filter(
            organization=org, left_at__isnull=True, exiled_at__isnull=True, rank__tier=1
        )
        .select_related("persona")
        .first()
    )
    return membership.persona.name if membership is not None else ""


def turf_for(house: Organization) -> dict | None:
    """The crime family's chapters: its wards, the gangs beneath it with their
    neighborhoods, the crews on rooms. ``None`` when the organization holds no
    turf, so a noble house's document carries no turf key."""
    wards = list(
        Turf.objects.filter(controlling_org=house, area__isnull=False).select_related(
            "area", "income_stream"
        )
    )
    gangs = list(
        Organization.objects.filter(
            Q(parent_org=house) | Q(fealty__liege=house), held_turf__area__isnull=False
        )
        .distinct()
        .order_by("name")
    )
    if not wards and not gangs:
        return None
    gang_ids = [g.pk for g in gangs]
    turf_by_org: dict[int, list[Turf]] = defaultdict(list)
    for turf in Turf.objects.filter(controlling_org_id__in=gang_ids).select_related("area"):
        turf_by_org[turf.controlling_org_id].append(turf)
    slots_by_gang: dict[int, list[CrewSlot]] = defaultdict(list)
    for slot in (
        CrewSlot.objects.filter(gang_id__in=gang_ids, is_active=True)
        .select_related("claimed_by")
        .annotate(room_count=Count("rooms"))
    ):
        slots_by_gang[slot.gang_id].append(slot)
    gang_rows = []
    for gang in gangs:
        neighborhoods = [t.area.name for t in turf_by_org.get(gang.pk, []) if t.area_id]
        crews = [
            {
                "crew_slot_id": slot.pk,
                "name": slot.name,
                "rooms": slot.room_count,
                "claimed_by": slot.claimed_by.name if slot.claimed_by_id else "",
                "is_open": slot.is_open,
            }
            for slot in slots_by_gang.get(gang.pk, [])
        ]
        gang_rows.append(
            {
                "org_id": gang.pk,
                "name": gang.name,
                "boss": _boss_name(gang),
                "neighborhood": ", ".join(neighborhoods),
                "crews": crews,
            }
        )
    return {
        "tier": _crime_tier_label(house),
        "wards": [
            {
                "turf_id": t.pk,
                "area_id": t.area_id,
                "name": t.area.name,
                "grip": t.grip,
                "base_value": t.income_stream.gross_amount if t.income_stream_id else 0,
            }
            for t in wards
        ],
        "gangs": gang_rows,
    }


def _crime_tier_label(org: Organization) -> str:
    from world.societies.crown import crime_tier  # noqa: PLC0415

    tier = crime_tier(org)
    return CrimeTier(tier).label if tier else ""


# ---------------------------------------------------------------------------
# the front page
# ---------------------------------------------------------------------------


def _city_of(area: Area, parent_by_area: dict[int, int | None], areas: dict[int, Area]):
    node: Area | None = area
    seen = 0
    while node is not None and seen < 12:  # noqa: PLR2004 - defensive walk cap
        if node.level == AreaLevel.BARONY:
            return node
        parent_id = parent_by_area.get(node.pk)
        node = areas.get(parent_id) if parent_id is not None else None
        seen += 1
    return None


def _standing_family_ids() -> set[int]:
    """Families whose organization holds a title or turf: noble or crime."""
    titled = Title.objects.filter(house__family__isnull=False).values_list(
        "house__family_id", flat=True
    )
    turfed = Turf.objects.filter(controlling_org__family__isnull=False).values_list(
        "controlling_org__family_id", flat=True
    )
    return set(titled) | set(turfed)


def _noble_roll(q: str) -> list[dict]:
    if q:
        houses = (
            Organization.objects.filter(
                name__icontains=q, titles__isnull=False, family__isnull=False
            )
            .distinct()
            .select_related("family__origin_realm")
            .order_by("name")[:ROLL_LIMIT]
        )
        return [
            {
                "kind": "house",
                "id": h.pk,
                "name": h.name,
                "sub": h.family.origin_realm.name if h.family.origin_realm_id else "",
            }
            for h in houses
        ]
    out = []
    for realm in Realm.objects.order_by("name"):
        rows, unclaimed = _build_rows(realm.pk)
        held = sum(1 for r in rows if r.house_id is not None)
        out.append(
            {
                "kind": "realm",
                "id": realm.pk,
                "name": realm.name,
                "titles": len(rows),
                "held": held,
                "unclaimed": sum(unclaimed.values()),
            }
        )
    return out


def _crime_roll(q: str) -> list[dict]:
    turfs = list(
        Turf.objects.filter(area__isnull=False, controlling_org__isnull=False).select_related(
            "area", "controlling_org"
        )
    )
    if q:
        seen: dict[int, Organization] = {}
        for t in turfs:
            if t.area.level in (AreaLevel.WARD, AreaLevel.BARONY) and q.lower() in (
                t.controlling_org.name.lower()
            ):
                seen[t.controlling_org_id] = t.controlling_org
        return [
            {"kind": "family", "id": org.pk, "name": org.name, "sub": "crime family"}
            for org in sorted(seen.values(), key=lambda o: o.name)[:ROLL_LIMIT]
        ]
    if not turfs:
        return []
    areas = {a.pk: a for a in Area.objects.all()}
    parent_by_area = {pk: a.parent_id for pk, a in areas.items()}
    per_city: dict[int, dict] = {}
    gangs_by_city: dict[int, set[int]] = defaultdict(set)
    for t in turfs:
        city = _city_of(t.area, parent_by_area, areas)
        if city is None:
            continue
        entry = per_city.setdefault(
            city.pk, {"kind": "city", "id": city.pk, "name": city.name, "families": set()}
        )
        if t.area.level in (AreaLevel.WARD, AreaLevel.BARONY):
            entry["families"].add(t.controlling_org_id)
        elif t.area.level == AreaLevel.NEIGHBORHOOD:
            gangs_by_city[city.pk].add(t.controlling_org_id)
    slot_counts = dict(
        CrewSlot.objects.filter(is_active=True, claimed_by__isnull=True)
        .values("gang_id")
        .annotate(n=Count("id"))
        .values_list("gang_id", "n")
    )
    out = []
    for city_id, entry in sorted(per_city.items(), key=lambda kv: kv[1]["name"]):
        gangs = gangs_by_city.get(city_id, set())
        out.append(
            {
                "kind": "city",
                "id": city_id,
                "name": entry["name"],
                "families": len(entry["families"]),
                "gangs": len(gangs),
                "crew_slots": sum(slot_counts.get(g, 0) for g in gangs),
            }
        )
    return out


def _commoner_roll(q: str) -> list[dict]:
    families = Family.objects.exclude(pk__in=_standing_family_ids()).select_related("kind")
    if q:
        families = families.filter(name__icontains=q).order_by("name")
    else:
        families = families.order_by("-pk")
    families = list(families[:ROLL_LIMIT])
    ids = [f.pk for f in families]
    on_record = dict(
        FamilyMembership.objects.filter(family_id__in=ids, ended_at__isnull=True)
        .values("family_id")
        .annotate(n=Count("id"))
        .values_list("family_id", "n")
    )
    appable = dict(
        Kinsperson.objects.filter(family_id__in=ids, is_appable=True, sheet__isnull=True)
        .values("family_id")
        .annotate(n=Count("id"))
        .values_list("family_id", "n")
    )
    return [
        {
            "kind": "family",
            "id": f.pk,
            "name": f.name,
            "sub": f.kind.name.lower() if f.kind_id else "",
            "on_record": on_record.get(f.pk, 0),
            "appable": appable.get(f.pk, 0),
        }
        for f in families
    ]


def front_rolls(*, q: str = "") -> FrontRolls:
    """The front page's three rolls; ``q`` narrows each to matching names."""
    q = (q or "").strip()
    return FrontRolls(noble=_noble_roll(q), crime=_crime_roll(q), commoner=_commoner_roll(q))


def search(q: str, *, limit: int = SEARCH_LIMIT) -> list[SearchHit]:
    """Find people, families, organizations and titles by name. Staff only,
    capped, and nothing at all under two characters so it never scans."""
    q = (q or "").strip()
    if len(q) < SEARCH_MIN_CHARS:
        return []
    people = Kinsperson.objects.filter(name__icontains=q).select_related("family")[:limit]
    families = Family.objects.filter(name__icontains=q).select_related("kind")[:limit]
    orgs = Organization.objects.filter(name__icontains=q).select_related("org_type")[:limit]
    titles = Title.objects.filter(name__icontains=q).select_related("realm", "house")[:limit]
    hits: list[SearchHit] = [
        *(
            SearchHit(
                "person",
                p.pk,
                p.display_name,
                p.family.name if p.family_id else NPC_TIER_LABEL[p.definition_tier],
            )
            for p in people
        ),
        *(SearchHit("family", f.pk, f.name, f.kind.name.lower()) for f in families),
        *(SearchHit("organization", o.pk, o.name, o.org_type.name) for o in orgs),
        *(
            SearchHit("title", t.pk, t.name, t.house.name if t.house_id else "vacant")
            for t in titles
        ),
    ]
    return hits[:limit]


# ---------------------------------------------------------------------------
# a person
# ---------------------------------------------------------------------------


def _kin_rows(node: Kinsperson) -> list[dict]:
    sibling_labels = siblings_of(node, OMNISCIENT)
    siblings = Kinsperson.objects.filter(pk__in=sibling_labels.keys()).order_by("name")
    return [
        *(
            _person_row(e.parent, relation=kin_word(e.parent, KinLink.PARENT), link=KinLink.PARENT)
            for e in parents_of(node, OMNISCIENT)
        ),
        *(
            _person_row(e.child, relation=kin_word(e.child, KinLink.CHILD), link=KinLink.CHILD)
            for e in children_of(node, OMNISCIENT)
        ),
        *(
            _person_row(s, relation=kin_word(s, KinLink.SPOUSE), link=KinLink.SPOUSE)
            for s in spouses_of(node, OMNISCIENT)
        ),
        *(
            _person_row(s, relation=kin_word(s, _SIBLING, sibling_labels[s.pk]), link=_SIBLING)
            for s in siblings
        ),
    ]


def _titles_held(node: Kinsperson) -> list[dict]:
    rows = []
    graphs: dict[int, object] = {}
    for title in Title.objects.filter(holder=node).select_related("realm", "house", "seat_domain"):
        graph = graphs.get(title.realm_id)
        if graph is None:
            graph = _realm_graph(title.realm_id)
            graphs[title.realm_id] = graph
        row: LadderRow | None = _row_for(title, graph) if graph is not None else None
        rows.append(
            {
                "title_id": title.pk,
                "name": title.name,
                "tier": title.tier,
                "realm": title.realm.name,
                "held_by": title.house.name if title.house_id else "",
                "seat": title.seat_domain.name if title.seat_domain_id else "",
                "vassals": row.vassals if row is not None else 0,
            }
        )
    return rows


def _house_block(node: Kinsperson, org: Organization | None) -> dict | None:
    if org is None:
        return None
    persona = _primary_persona(node)
    role = ""
    rank = None
    if persona is not None:
        membership = (
            OrganizationMembership.objects.filter(
                organization=org, persona=persona, left_at__isnull=True
            )
            .select_related("rank")
            .first()
        )
        if membership is not None and membership.rank_id:
            role = membership.rank.name
            rank = membership.rank.tier
    post = Vacancy.objects.filter(organization=org, holder_kinsperson=node).first()
    return {
        "org_id": org.pk,
        "name": org.name,
        "role": role,
        "rank": rank,
        "household_post": post.name if post is not None else "",
    }


def _memberships(node: Kinsperson) -> list[dict]:
    persona = _primary_persona(node)
    if persona is None:
        return []
    return [
        {
            "org_id": m.organization_id,
            "name": m.organization.name,
            "rank": m.rank.name if m.rank_id else "",
        }
        for m in OrganizationMembership.objects.filter(
            persona=persona, left_at__isnull=True, exiled_at__isnull=True
        ).select_related("organization", "rank")
    ]


def person_document(node: Kinsperson) -> PersonDocument:
    """A person's page: identity, status, family, kin, house, titles, sheet,
    memberships, and the record rail's counts. Staff read; omniscient."""
    family = node.family
    org = _family_org(family) if family is not None else None
    membership = (
        FamilyMembership.objects.filter(kinsperson=node, is_primary=True, ended_at__isnull=True)
        .select_related("family")
        .first()
    )
    kin = _kin_rows(node)
    hidden = (
        ParentageEdge.objects.filter(Q(child=node) | Q(parent=node), is_public_record=False).count()
        + Union.objects.filter(members=node, is_public_record=False).count()
    )
    unions = Union.objects.filter(members=node, ended_at__isnull=True).count()
    return PersonDocument(
        person={
            "id": node.pk,
            "name": node.name,
            "display_name": node.display_name,
            "gender_id": node.gender_id,
            "gender": node.gender.display_name if node.gender_id else "",
            "age": node.age,
            "tier": node.definition_tier,
            "tier_display": tier_display(node.definition_tier),
            "status": life_status(node),
            "record_accurate": node.believed_deceased == node.is_deceased,
            "obituary": node.obituary,
            "is_pc": node.definition_tier == DefinitionTier.PC,
            "description": node.description,
        },
        family=(
            {
                "id": family.pk,
                "name": family.name,
                "kind": family.kind.name if family.kind_id else "",
                "basis": membership.basis if membership is not None else "",
                "organization_id": org.pk if org is not None else None,
            }
            if family is not None
            else None
        ),
        kin=kin,
        house=_house_block(node, org),
        titles=_titles_held(node),
        sheet={
            "sheet_id": node.sheet_id,
            "is_appable": node.is_appable and node.sheet_id is None,
            "name_locked": node.name_locked,
            "age_min": node.age_min,
            "age_max": node.age_max,
            "allowed_gender_ids": list(node.allowed_genders.values_list("pk", flat=True)),
        },
        memberships=_memberships(node),
        record={
            "parents": sum(1 for k in kin if k["link"] == KinLink.PARENT),
            "children": sum(1 for k in kin if k["link"] == KinLink.CHILD),
            "siblings": sum(1 for k in kin if k["link"] not in KinLink.values),
            "unions": unions,
            "hidden_truths": hidden,
        },
    )


# ---------------------------------------------------------------------------
# a rung
# ---------------------------------------------------------------------------


def _holding_site(holding: DomainHolding) -> str:
    if holding.room_profile_id:
        return holding.room_profile.name
    if holding.building_id:
        return holding.building.name
    if holding.field_id:
        return holding.field.name
    return ""


def rung_document(title: Title) -> RungDocument:
    """A domain's page: the title and who holds it, its land, holdings, books,
    forces, and the vassal rungs beneath it."""
    graph = _realm_graph(title.realm_id)
    row = _row_for(title, graph) if graph is not None else None
    liege = liege_for_title(title)
    law = title.succession_law or (title.house.default_succession_law if title.house_id else None)
    own_area_id = graph.own_area_by_title.get(title.pk) if graph is not None else None
    domain = Domain.objects.filter(pk=own_area_id).select_related("area", "hall").first()
    holdings: list[dict] = []
    if domain is not None:
        holdings = [
            {
                "holding_id": holding.pk,
                "name": holding.name,
                "kind": holding.kind.name,
                "site": _holding_site(holding),
                "standing": holding.standing,
                "unsited": not (holding.room_profile_id or holding.building_id or holding.field_id),
            }
            for holding in DomainHolding.objects.filter(domain=domain).select_related(
                "kind", "room_profile", "building", "field"
            )
        ]
    vassals = []
    if graph is not None:
        for child in graph.children_by_parent_title.get(title.pk, []):
            if child.seat_domain_id == title.seat_domain_id:
                continue
            vassals.append(_row_summary(_row_for(child, graph)))
    return RungDocument(
        title={
            "title_id": title.pk,
            "name": title.name,
            "tier": title.tier,
            "realm_id": title.realm_id,
            "realm": title.realm.name,
            "house_id": title.house_id,
            "held_by": title.house.name if title.house_id else "",
            "holder_id": title.holder_id,
            "holder": title.holder.display_name if title.holder_id else "",
            "sworn_to": liege.name if liege is not None else (row.sworn_to if row else ""),
            "succession": law.name if law is not None else "",
            "seat": title.seat_domain.name if title.seat_domain_id else "",
            "is_claimable": title.is_claimable,
            "chain_top_id": row.chain_top_id if row is not None else title.pk,
        },
        demesne=(
            {
                "domain_id": domain.pk,
                "name": domain.area.name,
                "description": domain.description,
                "hall": domain.hall.name if domain.hall_id else "",
                "population": domain.population,
                "prosperity": domain.prosperity,
                "unrest": domain.unrest,
                "defenses": domain.defenses,
            }
            if domain is not None
            else None
        ),
        holdings=holdings,
        books=_books_dict(books_for(title.house if title.house_id else None)),
        forces=forces_for(title.house if title.house_id else None, domain=domain),
        vassals=vassals,
    )


# ---------------------------------------------------------------------------
# a family
# ---------------------------------------------------------------------------


def family_document(family: Family, *, viewer: object, staff: bool) -> FamilyDocument:
    """A family's page when it has no organization (or for the family half of
    one that does): identity, the tree, and its appable kin."""
    org = _family_org(family)
    payload = family_tree_for(family, OMNISCIENT if staff else viewer)
    believed = dict(
        Kinsperson.objects.filter(pk__in=[n["id"] for n in payload.nodes]).values_list(
            "pk", "believed_deceased"
        )
    )
    nodes = [{**n, "believed_deceased": believed.get(n["id"], False)} for n in payload.nodes]
    openings = Openings(
        appable=[
            _person_row(node)
            for node in Kinsperson.objects.filter(
                family=family, is_appable=True, sheet__isnull=True
            ).order_by("name")
        ]
    )
    return FamilyDocument(
        family={
            "id": family.pk,
            "name": family.name,
            "kind": family.kind.name if family.kind_id else "",
            "realm_id": family.origin_realm_id,
            "realm": family.origin_realm.name if family.origin_realm_id else "",
            "is_playable": family.is_playable,
            "description": family.description,
        },
        organization_id=org.pk if org is not None else None,
        tree={"nodes": nodes, "parentage": payload.parentage, "unions": payload.unions},
        openings=_openings_dict(openings),
    )


def house_chapters(house: Organization) -> dict:
    """The chapters the house document grows for #4239, as plain dicts."""
    return {
        "books": _books_dict(books_for(house)),
        "forces": forces_for(house),
        "openings": _openings_dict(openings_for(house)),
        "turf": turf_for(house),
    }

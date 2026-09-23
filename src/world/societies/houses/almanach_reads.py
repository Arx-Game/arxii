"""Almanach de Catenys (#3983) read payloads: the ladder and the house document.

Both reads are built from one in-memory pass over a realm's ``Title`` rows plus
its ``Area`` graph, never a per-row query — the (Postgres-only) area closure
matview isn't available on the SQLite test tier, so ancestry is walked over a
realm-wide ``Area.parent`` map built once. ``Domain.pk`` is always the same
value as its ``Area.pk`` (``Domain.area`` is a primary-key OneToOne), so a
title's ``seat_domain_id`` doubles as "the id of the barony-level Area at the
bottom of its chain" with no extra lookup.

**Ladder rows** (``ladder_for_realm``): one ``LadderRow`` per ``Title`` in the
realm, ordered by the Area's ancestry depth then name.

- ``state``/``claimable`` read straight off ``house_id``/``is_claimable``.
  ``is_defined`` is ``bool(name)``; an undefined name still renders
  ``state == "Unclaimed"`` (definedness and holding are independent axes).
- ``parent_title_id`` is the title whose own rung Area is the nearest
  ancestor Area that is itself a rung (i.e. is some other title's own-tier
  Area) — this is the graph ``sworn_to``/``vassals``/``unclaimed_by_tier``
  all walk.
- A row is a *chain top* when it is the highest-tier title sharing its
  ``seat_domain_id`` (``almanach._family_top``). A non-top row (an internal
  chain member — a duchy's own unnamed county/barony) always reports its
  chain top's name via both ``comes_with`` and ``sworn_to``: it isn't an
  independent rung, so it has nothing of its own to report.
- ``sworn_to`` for a chain-top row walks ``parent_title_id`` up to the
  nearest *held* ancestor (the containment liege) and reports that house's
  name — with a `` (crown)`` suffix only when the row itself is *held* and
  that liege holds the realm's highest present tier. An unclaimed chain top
  reports the same liege name with no suffix (nothing is sworn yet); with no
  held ancestor at all it falls back to the immediate parent rung's own name
  (or "Undefined" for an unnamed parent), and with no parent at all it is "".
- ``is_seat_of`` fires only for a BARONY-tier, held, non-top row: it names
  the house holding the higher rung whose seat this barony is.
- ``demesne``: a held row counts BARONY-tier titles in its own Area subtree
  sharing its house; an unclaimed row is 1 exactly when its own chain's
  barony is itself still unclaimed (always true today — a chain's house is
  set uniformly across the whole family), else 0.
- ``vassals``: direct child rungs (``parent_title_id == this``) that don't
  share this row's own ``seat_domain_id`` (i.e. aren't on its own chain). An
  unclaimed row counts child rows; a held row counts the *distinct houses*
  among held children only (an unclaimed child isn't a vassal yet, and one
  house holding two direct child chains counts once).
- ``unclaimed_by_tier``: every unclaimed chain top counts at its own tier.
  Additionally, a BARONY-tier chain member whose immediate
  ``parent_title_id`` is itself a chain top counts at BARONY — this is what
  makes a county/march's own one-barony seat count as an available barony
  even though it isn't independently claimable, while a duchy/kingdom's own
  seat chain (buried two-plus hops down) does not, since that barony is
  already represented by the duchy/kingdom row's own ``demesne``.
- ``for_founder=True`` drops any row whose own house, or any held house
  above it up the ``parent_title_id`` chain, has no ``published_at`` — an
  unclaimed rung stays visible as long as nothing unpublished sits above it.

**The house document** (``document_for_house``) folds ``house``/``family``/
``household``/``realm``/``lands``/``estate`` into plain dicts (``household``
and ``estate`` are lists of dicts — naturally repeating, not aggregates) so
Task 5 can serialize the payload with plain DRF fields, no nested
dataclasses. ``realm``'s ``demesne``/``vassals`` lists and ``lands`` reuse
the same title/Area maps ``ladder_for_realm`` builds, so the two reads never
diverge. ``realm["demesne"]`` is every barony-tier title the house holds
directly, wherever it sits (a barony seated inside a vassal's own county is
still the house's own land); ``realm["vassals"]`` is every direct child rung
of ANY title the house holds — not only its own top chain — excluding
children that are themselves on one of the house's own chains.
``household`` is filtered to retainer Vacancy rows (no ``kin_node``/
``kin_pool`` link — those mark an appable kin slot, never a household
position) at the Household rank. ``staff=True`` reads the family tree with
the omniscient viewer (mechanical truth); otherwise the caller's own
``viewer`` gates what's visible, exactly like every other kinship read.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.areas.constants import AreaLevel
from world.areas.models import Area
from world.locations.models import LocationOwnership
from world.roster.constants import NOBLE_KIND_NAME
from world.roster.models import Kinsperson
from world.roster.services.kinship import OMNISCIENT, family_tree_for
from world.societies.houses.almanach import HOUSEHOLD_RANK_TITLE, UNDEFINED_AREA_NAME, _family_top
from world.societies.houses.constants import TIER_TO_AREA_LEVEL, TITLE_TIER_RANK, TitleTier
from world.societies.houses.models import (
    Domain,
    DomainHolding,
    HouseTemplate,
    NobiliaryParticle,
    Title,
)
from world.societies.houses.services import resolve_particle
from world.societies.models import Organization, Vacancy

if TYPE_CHECKING:
    from world.realms.models import Realm


@dataclass
class LadderRow:
    """One rung of the realm ladder, ready to serialize (Task 5)."""

    title_id: int
    name: str
    is_defined: bool
    tier: str
    level: int
    parent_title_id: int | None
    house_id: int | None
    house_name: str
    state: str
    is_seat_of: str
    sworn_to: str
    demesne: int
    vassals: int
    claimable: bool
    seat_domain_id: int | None
    comes_with: str


@dataclass
class LadderPayload:
    """A realm's whole ladder: every rung plus per-tier unclaimed counts."""

    rows: list[LadderRow]
    unclaimed_by_tier: dict[str, int]


@dataclass
class HouseDocument:
    """The Almanach's house document: plain dicts/lists per section."""

    house: dict
    family: dict
    household: list[dict]
    realm: dict
    lands: dict
    estate: list[dict]


@dataclass
class RealmCharter:
    """The realm-level defaults the founder ladder shows before any claim
    exists (Task 3, #3983 Plan B): mirrors ``_house_payload``'s
    ``default_succession_law`` shape for the law, and ``resolve_particle``'s
    band rule (blank-floor row) for the particle."""

    succession_law: dict | None
    particle: dict
    quiddity_prompt: str
    capital_name: str


def _subtree_area_ids(root: int, children_by_area: dict[int | None, list[int]]) -> set[int]:
    """Every Area id in ``root``'s subtree (inclusive), walked in memory."""
    found = {root}
    frontier = [root]
    while frontier:
        nxt: list[int] = []
        for area_id in frontier:
            for child_id in children_by_area.get(area_id, []):
                if child_id not in found:
                    found.add(child_id)
                    nxt.append(child_id)
        frontier = nxt
    return found


def _area_maps(
    realm_id: int,
) -> tuple[dict[int, int | None], dict[int, int], dict[int | None, list[int]], dict[int, int]]:
    """One Area query for the whole realm: parent/level lookups, a
    parent->children index, and each Area's ancestry depth (BFS from the
    roots — no parent, or a parent outside this realm's own Area set).

    ``.values_list`` rather than ``.only()``: Area is identity-mapped
    (SharedMemoryModel), and a narrowed ``.only()`` load leaves the resident
    instance permanently missing columns for the rest of the process
    (ADR-0261) — a scalar-only projection never touches the cache.
    """
    rows = Area.objects.filter(realm_id=realm_id).values_list("pk", "parent_id", "level")
    parent_by_area: dict[int, int | None] = {}
    level_by_area: dict[int, int] = {}
    children_by_area: dict[int | None, list[int]] = defaultdict(list)
    for pk, parent_id, level in rows:
        parent_by_area[pk] = parent_id
        level_by_area[pk] = level
        children_by_area[parent_id].append(pk)

    depth_by_area: dict[int, int] = {}
    frontier = [pk for pk, parent_id in parent_by_area.items() if parent_id not in parent_by_area]
    depth = 0
    while frontier:
        for area_id in frontier:
            depth_by_area[area_id] = depth
        frontier = [c for pk in frontier for c in children_by_area.get(pk, [])]
        depth += 1
    return parent_by_area, level_by_area, children_by_area, depth_by_area


def _own_rung_areas(
    titles: list[Title], parent_by_area: dict[int, int | None], level_by_area: dict[int, int]
) -> dict[int, int | None]:
    """Each title's own rung Area id: walk up from its (shared) seat Area
    until the level matches the title's own tier (mirrors
    ``almanach._rung_area``, in memory — a per-row DB walk here would be an
    N+1 across the realm)."""
    own_area_by_title: dict[int, int | None] = {}
    for t in titles:
        target_level = TIER_TO_AREA_LEVEL[t.tier]
        area_id = t.seat_domain_id
        while area_id is not None and level_by_area.get(area_id) != target_level:
            area_id = parent_by_area.get(area_id)
        own_area_by_title[t.pk] = area_id
    return own_area_by_title


def _parent_title_ids(
    titles: list[Title],
    own_area_by_title: dict[int, int | None],
    parent_by_area: dict[int, int | None],
) -> dict[int, int | None]:
    """Each title's ``parent_title_id``: the nearest ancestor Area that is
    itself some title's own rung Area."""
    title_by_area = {
        area_id: title_pk for title_pk, area_id in own_area_by_title.items() if area_id is not None
    }
    parent_title_by_title: dict[int, int | None] = {}
    for t in titles:
        area_id = own_area_by_title.get(t.pk)
        walker = parent_by_area.get(area_id) if area_id is not None else None
        found = None
        while walker is not None:
            if walker in title_by_area:
                found = title_by_area[walker]
                break
            walker = parent_by_area.get(walker)
        parent_title_by_title[t.pk] = found
    return parent_title_by_title


@dataclass
class _RealmGraph:
    """The in-memory Title/Area graph one realm's ladder is read off — built
    once by ``_realm_graph`` and shared by every row."""

    titles_by_pk: dict[int, Title]
    parent_title_by_title: dict[int, int | None]
    children_by_parent_title: dict[int, list[Title]]
    family_top_by_seat: dict[int, int]
    barony_by_seat: dict[int, Title]
    own_area_by_title: dict[int, int | None]
    depth_by_area: dict[int, int]
    children_by_area: dict[int | None, list[int]]
    top_tier_house_ids: set[int]

    def is_top(self, t: Title) -> bool:
        """Whether ``t`` is the highest-tier title sharing its seat (its
        own chain's top), not an internal chain member."""
        top_id = self.family_top_by_seat.get(t.seat_domain_id)
        return t.seat_domain_id is not None and top_id == t.pk

    def liege_title(self, title_pk: int) -> Title | None:
        """Nearest ancestor rung (via ``parent_title_id``) with a house set."""
        current = self.parent_title_by_title.get(title_pk)
        while current is not None:
            candidate = self.titles_by_pk[current]
            if candidate.house_id is not None:
                return candidate
            current = self.parent_title_by_title.get(current)
        return None

    def founder_hidden(self, title_pk: int) -> bool:
        """This row, or any held rung above it, belongs to an unpublished house."""
        current: int | None = title_pk
        while current is not None:
            t = self.titles_by_pk[current]
            if t.house_id is not None and t.house.published_at is None:
                return True
            current = self.parent_title_by_title.get(current)
        return False


def _realm_graph(realm_id: int) -> _RealmGraph | None:
    """One Title query, one Area query, everything else walked in memory.
    ``None`` when the realm has no titles at all."""
    titles = list(Title.objects.filter(realm_id=realm_id).select_related("house", "seat_domain"))
    if not titles:
        return None

    parent_by_area, level_by_area, children_by_area, depth_by_area = _area_maps(realm_id)
    own_area_by_title = _own_rung_areas(titles, parent_by_area, level_by_area)
    parent_title_by_title = _parent_title_ids(titles, own_area_by_title, parent_by_area)

    children_by_parent_title: dict[int, list[Title]] = defaultdict(list)
    for t in titles:
        parent_id = parent_title_by_title.get(t.pk)
        if parent_id is not None:
            children_by_parent_title[parent_id].append(t)

    by_seat: dict[int, list[Title]] = defaultdict(list)
    for t in titles:
        if t.seat_domain_id is not None:
            by_seat[t.seat_domain_id].append(t)
    family_top_by_seat = {seat_id: _family_top(group).pk for seat_id, group in by_seat.items()}

    barony_by_seat: dict[int, Title] = {
        t.seat_domain_id: t for t in titles if t.tier == TitleTier.BARONY and t.seat_domain_id
    }
    top_tier_rank = max(TITLE_TIER_RANK[t.tier] for t in titles)
    top_tier_house_ids = {
        t.house_id for t in titles if TITLE_TIER_RANK[t.tier] == top_tier_rank and t.house_id
    }

    return _RealmGraph(
        titles_by_pk={t.pk: t for t in titles},
        parent_title_by_title=parent_title_by_title,
        children_by_parent_title=dict(children_by_parent_title),
        family_top_by_seat=family_top_by_seat,
        barony_by_seat=barony_by_seat,
        own_area_by_title=own_area_by_title,
        depth_by_area=depth_by_area,
        children_by_area=children_by_area,
        top_tier_house_ids=top_tier_house_ids,
    )


def _sworn_to_and_comes_with(
    t: Title, graph: _RealmGraph, *, top: bool, parent_id: int | None
) -> tuple[str, str]:
    """See the module docstring's ``sworn_to``/``comes_with`` rules."""
    if not top:
        top_title = graph.titles_by_pk[graph.family_top_by_seat[t.seat_domain_id]]
        return top_title.name, top_title.name
    liege = graph.liege_title(t.pk)
    if t.house_id is not None:
        if liege is None:
            return "", ""
        suffix = " (crown)" if liege.house_id in graph.top_tier_house_ids else ""
        return f"{liege.house.name}{suffix}", ""
    if liege is not None:
        return liege.house.name, ""
    if parent_id is not None:
        return graph.titles_by_pk[parent_id].name or UNDEFINED_AREA_NAME, ""
    return "", ""


def _demesne_for(t: Title, graph: _RealmGraph, own_area_id: int | None) -> int:
    """See the module docstring's ``demesne`` rule."""
    if t.house_id is not None:
        subtree = _subtree_area_ids(own_area_id, graph.children_by_area) if own_area_id else set()
        return sum(
            1
            for seat_id, barony in graph.barony_by_seat.items()
            if barony.house_id == t.house_id and seat_id in subtree
        )
    own_barony = graph.barony_by_seat.get(t.seat_domain_id)
    return 1 if own_barony is not None and own_barony.house_id is None else 0


def _vassals_for(t: Title, graph: _RealmGraph) -> int:
    """See the module docstring's ``vassals`` rule."""
    direct_children = graph.children_by_parent_title.get(t.pk, [])
    not_on_chain = [c for c in direct_children if c.seat_domain_id != t.seat_domain_id]
    if t.house_id is not None:
        return len({c.house_id for c in not_on_chain if c.house_id is not None})
    return len(not_on_chain)


def _unclaimed_tier_hit(t: Title, graph: _RealmGraph, *, top: bool) -> str | None:
    """The tier this (unclaimed) title counts toward in ``unclaimed_by_tier``,
    or ``None`` if it doesn't count at all. See the module docstring."""
    if t.house_id is not None:
        return None
    if top:
        return t.tier
    if t.tier == TitleTier.BARONY:
        parent_id = graph.parent_title_by_title.get(t.pk)
        if parent_id is not None and graph.is_top(graph.titles_by_pk[parent_id]):
            return TitleTier.BARONY
    return None


def _row_for(t: Title, graph: _RealmGraph) -> LadderRow:
    """One ``LadderRow`` for ``t``, per the module docstring's field rules."""
    top = graph.is_top(t)
    parent_id = graph.parent_title_by_title.get(t.pk)
    own_area_id = graph.own_area_by_title.get(t.pk)
    sworn_to, comes_with = _sworn_to_and_comes_with(t, graph, top=top, parent_id=parent_id)
    is_seat_of = ""
    if t.tier == TitleTier.BARONY and t.house_id is not None and not top:
        is_seat_of = t.house.name
    return LadderRow(
        title_id=t.pk,
        name=t.name,
        is_defined=bool(t.name),
        tier=t.tier,
        level=graph.depth_by_area.get(own_area_id, 0) if own_area_id is not None else 0,
        parent_title_id=parent_id,
        house_id=t.house_id,
        house_name=t.house.name if t.house_id is not None else "",
        state="Held" if t.house_id is not None else "Unclaimed",
        is_seat_of=is_seat_of,
        sworn_to=sworn_to,
        demesne=_demesne_for(t, graph, own_area_id),
        vassals=_vassals_for(t, graph),
        claimable=t.is_claimable,
        seat_domain_id=t.seat_domain_id,
        comes_with=comes_with,
    )


def _build_rows(realm_id: int, *, for_founder: bool = False) -> tuple[list[LadderRow], dict]:
    """The shared graph pass behind both ``ladder_for_realm`` and
    ``document_for_house``: one Title query, one Area query, everything else
    walked in memory. See the module docstring for the field rules."""
    graph = _realm_graph(realm_id)
    if graph is None:
        return [], {}

    rows: list[LadderRow] = []
    unclaimed_by_tier: dict[str, int] = defaultdict(int)
    for t in graph.titles_by_pk.values():
        if for_founder and graph.founder_hidden(t.pk):
            continue
        rows.append(_row_for(t, graph))
        hit = _unclaimed_tier_hit(t, graph, top=graph.is_top(t))
        if hit is not None:
            unclaimed_by_tier[hit] += 1

    rows.sort(key=lambda r: (r.level, r.name))
    return rows, dict(unclaimed_by_tier)


def ladder_for_realm(realm: Realm, *, for_founder: bool = False) -> LadderPayload:
    """The realm's whole feudal ladder (#3983): every rung, plus per-tier
    unclaimed counts. ``for_founder=True`` hides any rung whose own house,
    or any held house above it, isn't published yet."""
    rows, unclaimed_by_tier = _build_rows(realm.pk, for_founder=for_founder)
    return LadderPayload(rows=rows, unclaimed_by_tier=unclaimed_by_tier)


def _row_summary(row: LadderRow) -> dict:
    return {
        "title_id": row.title_id,
        "name": row.name,
        "held_by": row.house_name,
        "demesne": row.demesne,
        "vassals": row.vassals,
    }


def _house_titles(house: Organization) -> list[Title]:
    return list(house.titles.select_related("house", "seat_domain").all())


_PARTICLE_EXAMPLE_KIN_COUNT = 2


def _particle_example(house: Organization) -> str:
    """'<name> <particle> <house>' pairs (born-form, taken-in-form) joined
    with ' · ', using the family's first two kin (or 'Sample'/'Sample' when
    it has fewer than two)."""
    names = []
    if house.family_id is not None:
        kin = Kinsperson.objects.filter(family_id=house.family_id).order_by("pk")
        names = [k.display_name for k in kin[:_PARTICLE_EXAMPLE_KIN_COUNT]]
    if len(names) < _PARTICLE_EXAMPLE_KIN_COUNT:
        names = ["Sample", "Sample"]
    born = resolve_particle(house.family)
    taken_in = resolve_particle(house.family, taken_in=True)
    pair_born = " ".join(piece for piece in (names[0], born, house.name) if piece)
    pair_taken_in = " ".join(piece for piece in (names[1], taken_in, house.name) if piece)
    return f"{pair_born} · {pair_taken_in}"


def _house_payload(house: Organization) -> dict:
    law = house.default_succession_law
    law_payload = (
        {"name": law.name, "codex_entry_id": law.codex_entry_id} if law is not None else None
    )
    return {
        "id": house.pk,
        "name": house.name,
        "description": house.description,
        "words": house.words,
        "colors": house.colors,
        "sigil_description": house.sigil_description,
        "house_state": house.house_state,
        "published_at": house.published_at,
        "particle_example": _particle_example(house),
        "default_succession_law": law_payload,
        "aspects": [
            {
                "definition": facet.definition.name,
                "option": facet.option.name,
                "description": facet.option.description,
            }
            for facet in house.aspects.select_related("definition", "option").all()
        ],
        "features": [
            {
                "name": stamped.feature.name,
                "slug": stamped.feature.slug,
                "description": stamped.feature.description,
            }
            for stamped in house.features.select_related("feature").all()
        ],
        "offices": [
            {
                "slug": office.slug,
                "title": office.title,
                "holder_name": office.holder.name if office.holder_id else "",
            }
            for office in house.offices.select_related("holder").all()
        ],
    }


def _family_payload(house: Organization, viewer: object, *, staff: bool) -> dict:
    if house.family_id is None:
        return {"nodes": [], "parentage": [], "unions": []}
    payload = family_tree_for(house.family, OMNISCIENT if staff else viewer)
    node_ids = [node["id"] for node in payload.nodes]
    believed = dict(
        Kinsperson.objects.filter(pk__in=node_ids).values_list("pk", "believed_deceased")
    )
    nodes = [
        {**node, "believed_deceased": believed.get(node["id"], False)} for node in payload.nodes
    ]
    return {"nodes": nodes, "parentage": payload.parentage, "unions": payload.unions}


def _household_payload(house: Organization) -> list[dict]:
    # A household member is a RETAINER Vacancy (Vacancy's own docstring: no
    # kin_node/kin_pool link) at the Household rank — the kin-link test is
    # the defining one (a kin Vacancy is an appable claim slot, never a
    # household position), and the rank filter narrows to the Household rung
    # specifically rather than every retainer vacancy on the org.
    vacancies = Vacancy.objects.filter(
        organization=house,
        rank__name=HOUSEHOLD_RANK_TITLE,
        kin_node__isnull=True,
        kin_pool__isnull=True,
    ).select_related("holder_kinsperson")
    out = []
    for v in vacancies:
        holder = v.holder_kinsperson
        out.append(
            {
                "vacancy_id": v.pk,
                "position": v.name,
                "holder_id": holder.pk if holder is not None else None,
                "holder_name": holder.display_name if holder is not None else "",
                "is_open": v.is_open,
                "count_remaining": v.count_remaining,
                "is_deceased": holder.is_deceased if holder is not None else False,
                "believed_deceased": holder.believed_deceased if holder is not None else False,
            }
        )
    return out


def _realm_payload(house: Organization, titles: list[Title], all_rows: list[LadderRow]) -> dict:
    if not titles:
        return {"sworn_to": "", "obligation_pct": None, "holds": "", "demesne": [], "vassals": []}
    top = _family_top(titles)
    try:
        fealty = house.fealty
    except ObjectDoesNotExist:
        fealty = None
    sworn_to = fealty.liege.name if fealty is not None else ""
    obligation_pct = None
    if fealty is not None and fealty.obligation_id is not None:
        obligation_pct = fealty.obligation.percent
    # Demesne is every barony the house holds personally, wherever it lies —
    # a barony seated deep in a vassal's own county is still the house's own
    # land (spec Decision 3), not only the ones on its own top chain.
    held_rows = [r for r in all_rows if r.house_id == house.pk]
    held_title_ids = {r.title_id for r in held_rows}
    own_chain_seat_ids = {r.seat_domain_id for r in held_rows}
    demesne = [_row_summary(r) for r in held_rows if r.tier == TitleTier.BARONY]
    # Vassals are the houses/unclaimed rungs sworn beneath ANY rung the house
    # holds, not only its own top chain — a direct child of a barony it holds
    # inside someone else's territory is still its vassal. Excludes children
    # that are themselves on one of the house's own chains (an internal
    # chain member's "child" is just the next rung down the same chain).
    vassals = [
        _row_summary(r)
        for r in all_rows
        if r.parent_title_id in held_title_ids and r.seat_domain_id not in own_chain_seat_ids
    ]
    return {
        "sworn_to": sworn_to,
        "obligation_pct": obligation_pct,
        "holds": top.name,
        "demesne": demesne,
        "vassals": vassals,
    }


def _lands_payload(house: Organization, titles: list[Title]) -> dict:
    if not titles:
        return {"count": 0, "population": 0, "produces": [], "seat": "", "baronies": []}
    top = _family_top(titles)
    domains = list(
        Domain.objects.filter(owner_org=house, area__level=AreaLevel.BARONY).select_related(
            "area", "area__parent", "hall"
        )
    )
    produces = sorted(
        set(
            DomainHolding.objects.filter(domain__owner_org=house).values_list(
                "kind__name", flat=True
            )
        )
    )
    # A through-table query, not prefetch_related: Domain is identity-mapped
    # (SharedMemoryModel), and a bare prefetch_related string caches on the
    # shared instance's _prefetched_objects_cache, stale for whoever else
    # reads that same Domain next (see houses.services.particles_for_families
    # for the same call).
    land_shapes_by_domain: dict[int, list[str]] = defaultdict(list)
    shape_rows = Domain.land_shapes.through.objects.filter(
        domain_id__in=[d.pk for d in domains]
    ).values_list("domain_id", "landshape__name")
    for domain_id, shape_name in shape_rows:
        land_shapes_by_domain[domain_id].append(shape_name)
    baronies = [
        {
            "id": domain.pk,
            "name": domain.area.name,
            "in": domain.area.parent.name if domain.area.parent_id else "",
            "hall": domain.hall.name if domain.hall_id else "",
            "is_seat": domain.pk == top.seat_domain_id,
            "description": domain.description,
            "land_shapes": land_shapes_by_domain.get(domain.pk, []),
            "population": domain.population,
        }
        for domain in domains
    ]
    return {
        "count": len(domains),
        "population": sum(b["population"] for b in baronies),
        "produces": produces,
        "seat": next((b["name"] for b in baronies if b["is_seat"]), ""),
        "baronies": baronies,
    }


def _estate_payload(house: Organization) -> list[dict]:
    ownerships = LocationOwnership.objects.filter(
        holder_organization=house, ended_at__isnull=True, area__level=AreaLevel.BUILDING
    ).select_related("area", "area__parent", "area__parent__parent", "area__parent__parent__parent")
    estates = []
    for ownership in ownerships:
        area = ownership.area
        walker = area.parent
        under_city = False
        while walker is not None:
            if walker.level == AreaLevel.CITY:
                under_city = True
                break
            walker = walker.parent
        if not under_city:
            continue
        district = None
        if area.parent is not None and area.parent.level != AreaLevel.CITY:
            district = area.parent
        estates.append(
            {
                "id": area.pk,
                "name": area.name,
                "district": district.name if district is not None else "",
                "description": area.description,
            }
        )
    return estates


def document_for_house(house: Organization, *, viewer: object, staff: bool) -> HouseDocument:
    """The Almanach's house document (#3983): the house's own charter block
    folded together with its family tree, household, realm standing, lands,
    and estate — one read for the whole house page."""
    titles = _house_titles(house)
    all_rows: list[LadderRow] = []
    if titles:
        all_rows, _unclaimed = _build_rows(titles[0].realm_id)
    return HouseDocument(
        house=_house_payload(house),
        family=_family_payload(house, viewer, staff=staff),
        household=_household_payload(house),
        realm=_realm_payload(house, titles, all_rows),
        lands=_lands_payload(house, titles),
        estate=_estate_payload(house),
    )


def _realm_default_template(realm_id: int) -> HouseTemplate | None:
    """The realm's tier-less fallback template (``templates_for_title``'s own
    fallback rung), else its first by name; ``None`` for an unauthored realm."""
    templates = list(HouseTemplate.objects.filter(realm_id=realm_id))
    tierless = next((t for t in templates if not t.tier), None)
    return tierless or (templates[0] if templates else None)


def charter_for_realm(realm: Realm) -> RealmCharter:
    """The realm's charter defaults for the founder ladder (#3983 Plan B,
    Task 3), read before any claim exists so nothing here touches
    ``HouseClaim``: the default template's succession law, the blank-floor
    Noble particle (``resolve_particle``'s own band rule), the default
    template's first aspect prompt, and the realm's capital name."""
    template = _realm_default_template(realm.pk)
    law = template.default_succession_law if template is not None else None
    law_payload = (
        {"name": law.name, "codex_entry_id": law.codex_entry_id} if law is not None else None
    )
    particle_row = NobiliaryParticle.objects.filter(
        realm=realm, kind__name=NOBLE_KIND_NAME, tier_floor=""
    ).first()
    particle = {
        "born": particle_row.particle if particle_row is not None else "",
        "taken_in": (
            (particle_row.taken_in_particle or particle_row.particle)
            if particle_row is not None
            else ""
        ),
    }
    definition = template.aspect_definitions.all().first() if template is not None else None
    capital = Area.objects.filter(realm=realm, is_capital=True).first()
    return RealmCharter(
        succession_law=law_payload,
        particle=particle,
        quiddity_prompt=definition.prompt if definition is not None else "",
        capital_name=capital.name if capital is not None else "",
    )

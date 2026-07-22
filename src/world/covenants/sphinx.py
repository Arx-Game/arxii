"""The Sphinx of Black Quartz — the read-only vow-suitability oracle (#2640).

Diegetic Shroudwatch Academy fixture, invoked as *"Sphinx of Black Quartz, judge
my vow: [vow]."* Runs the SAME kit∩role-demand join ``covenant_role_specialty_
power_term`` (``world.magic.services.power_terms``) uses for the always-on
specialty power boost — but as a REPORT instead of a resolution-time bonus:
"could this character's known techniques ever satisfy this vow's authored
demands." No writes anywhere in this module; nothing here gates anything (the
soft-gate ruling — a player may swear a vow the Sphinx warned about).

Two entry points:

- ``judge_vow`` — one character × one role → a three-tier ``SphinxVerdict``
  (``SphinxTier.TAKES``/``DORMANT``/``NOT_YET``), the player-facing verdict
  (REST endpoint + ``sphinx`` telnet command).
- ``audit_vow_coverage`` — every active anchor role × every active Tradition →
  "which vows are swearable today, per tradition" (the staff coverage-audit
  instrument; validation-plan instrument 2). Deliberately narrower than
  ``judge_vow``: it compares against the role's SPECIALTY-function demand set
  only (situation demands are per-character DB state — a fired situational
  perk depends on a live target/ally/scene, not on what a tradition's
  technique pool could ever satisfy in the abstract — so they are excluded
  from this catalog-level pass; see the docstring on ``audit_vow_coverage``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from django.db.models import Prefetch

from world.covenants.constants import SphinxTier
from world.covenants.models import (
    CovenantRole,
    CovenantRoleTechniqueSpecialty,
    VowSituationalPerk,
    VowSituationalPerkRung,
    VowSituationalPerkSituation,
)
from world.covenants.perks.constants import SITUATION_CREATOR_FUNCTIONS, PerkBeneficiary
from world.magic.models import (
    CharacterTechnique,
    CharacterTradition,
    Technique,
    TechniqueFunctionTag,
    Tradition,
    TraditionGiftGrant,
)
from world.magic.services.gift_acquisition import can_learn_technique

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

#: Shopping-list cap per uncovered function (spec: "up to 3 Technique rows").
_SHOPPING_LIST_PER_FUNCTION = 3
#: Candidate pool cap per function before the learnability check — bounds the
#: per-candidate ``can_learn_technique`` calls to a small, predictable number.
_SHOPPING_CANDIDATE_POOL = 20

#: The label used for demand rows sourced from a role's technique-specialty
#: table, distinguishing them from perk-sourced (situation) demand rows whose
#: ``source`` is the perk's own authored name.
_SPECIALTY_SOURCE = "specialty"


@dataclass(frozen=True)
class SphinxDemand:
    """One authored demand a vow makes of its holder's kit (#2640).

    ``function`` doubles as the demand's display label: for a ``specialty``
    demand it is the literal ``TechniqueFunction`` value the role rewards; for
    a perk-sourced demand it is the ``Situation`` value the perk requires
    (whose CREATOR set — ``SITUATION_CREATOR_FUNCTIONS[function]`` — is the
    thing actually checked against the kit, since a situation can be created
    by any function in its creator set, not one specific function).
    """

    function: str
    source: str
    covered: bool
    qualifying_technique_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SphinxShoppingItem:
    """One learnable technique that would flip an uncovered demand (#2640)."""

    technique_name: str
    gift_name: str
    function: str


@dataclass(frozen=True)
class SphinxVerdict:
    """The Sphinx's full verdict for one character × one role (#2640)."""

    tier: str
    role_name: str
    demands: list[SphinxDemand] = field(default_factory=list)
    shopping_list: list[SphinxShoppingItem] = field(default_factory=list)


@dataclass(frozen=True)
class SphinxCoverageRow:
    """One (anchor role × tradition) cell of the staff coverage audit (#2640)."""

    role_name: str
    tradition_name: str
    coverage: Literal["full", "partial", "none"]
    missing_functions: list[str] = field(default_factory=list)


def _role_ids_for_judgment(role: CovenantRole) -> list[int]:
    """Anchor role id, plus the parent's id when ``role`` is a sub-role.

    Mirrors ``covenant_role_specialty_power_term``'s row-collection rule
    (#2443 spec §3): sub-role demand rows ADD to the anchor's, never replace
    them — the same ADD semantics apply to ``VowSituationalPerk`` rows.
    """
    role_ids = [role.pk]
    if role.parent_role_id is not None:
        role_ids.append(role.parent_role_id)
    return role_ids


def _kit_supply(sheet: CharacterSheet) -> dict[str, list[str]]:
    """Map TechniqueFunction -> known technique names carrying it (#2640).

    One query for the character's known techniques + a prefetch of each
    technique's function tags (the ``Prefetch(to_attr=)`` idiom shared with
    ``cg_catalog.get_technique_options`` / ``covenant_role_specialty_power_
    term`` — no query-per-technique).
    """
    character_techniques = (
        CharacterTechnique.objects.filter(character=sheet)
        .select_related("technique")
        .prefetch_related(
            Prefetch(
                "technique__function_tags",
                queryset=TechniqueFunctionTag.objects.all(),
                to_attr="cached_function_tags",
            )
        )
    )
    supply: dict[str, list[str]] = {}
    for character_technique in character_techniques:
        technique = character_technique.technique
        for tag in technique.cached_function_tags:
            supply.setdefault(tag.function, []).append(technique.name)
    return supply


def _specialty_demands(role_ids: list[int], supply: dict[str, list[str]]) -> list[SphinxDemand]:
    """One ``SphinxDemand`` per unique specialty function across ``role_ids``."""
    functions = sorted(
        {
            row.function
            for row in CovenantRoleTechniqueSpecialty.objects.filter(covenant_role_id__in=role_ids)
        }
    )
    return [
        SphinxDemand(
            function=function,
            source=_SPECIALTY_SOURCE,
            covered=bool(supply.get(function)),
            qualifying_technique_names=list(supply.get(function, [])),
        )
        for function in functions
    ]


def _situation_demands(role_ids: list[int], supply: dict[str, list[str]]) -> list[SphinxDemand]:
    """One ``SphinxDemand`` per (SELF-beneficiary perk, in-mapping situation).

    Walks the role's (+ parent, for a sub-role) SELF-beneficiary perks' base
    situations AND rung ``extra_situation`` values; only situations present in
    ``SITUATION_CREATOR_FUNCTIONS`` demand anything (positional/encounter
    states demand nothing from a kit — see that mapping's docstring). A
    creator-set demand is covered when the kit carries ANY function in the
    set.
    """
    self_perks = VowSituationalPerk.objects.filter(
        covenant_role_id__in=role_ids,
        beneficiary=PerkBeneficiary.SELF,
    ).prefetch_related(
        Prefetch(
            "situations",
            queryset=VowSituationalPerkSituation.objects.all(),
            to_attr="cached_situations",
        ),
        Prefetch(
            "rungs",
            queryset=VowSituationalPerkRung.objects.all(),
            to_attr="cached_rungs",
        ),
    )

    demands: list[SphinxDemand] = []
    for perk in self_perks:
        situations = {row.situation for row in perk.cached_situations}
        situations.update(rung.extra_situation for rung in perk.cached_rungs)
        for situation in sorted(situations):
            creator_functions = SITUATION_CREATOR_FUNCTIONS.get(situation)
            if creator_functions is None:
                continue
            qualifying = sorted(
                {
                    name
                    for creator_function in creator_functions
                    for name in supply.get(creator_function, [])
                }
            )
            demands.append(
                SphinxDemand(
                    function=situation,
                    source=perk.name,
                    covered=bool(qualifying),
                    qualifying_technique_names=qualifying,
                )
            )
    return demands


def _tier_for(demands: list[SphinxDemand]) -> str:
    if not demands:
        # An unauthored vow makes no demands — it cannot reject (#2640 v1 rule).
        return SphinxTier.TAKES
    covered_count = sum(1 for demand in demands if demand.covered)
    if covered_count == len(demands):
        return SphinxTier.TAKES
    if covered_count >= 1:
        return SphinxTier.DORMANT
    return SphinxTier.NOT_YET


def _uncovered_target_functions(demands: list[SphinxDemand]) -> set[str]:
    """Which TechniqueFunction values would flip an uncovered demand.

    Specialty demands target their own function directly; situation demands
    target the situation's whole creator set (any one function would cover
    it).
    """
    targets: set[str] = set()
    for demand in demands:
        if demand.covered:
            continue
        if demand.source == _SPECIALTY_SOURCE:
            targets.add(demand.function)
        else:
            targets.update(SITUATION_CREATOR_FUNCTIONS.get(demand.function, frozenset()))
    return targets


def _signature_technique_ids(sheet: CharacterSheet) -> set[int]:
    """PKs of Techniques in the sheet's active tradition's signature pool.

    One row lookup (the active ``CharacterTradition``) + one bulk
    ``values_list`` — no per-candidate query later.
    """
    active_row = (
        CharacterTradition.objects.filter(character=sheet, left_at__isnull=True)
        .select_related("tradition")
        .first()
    )
    if active_row is None:
        return set()
    ids = set(
        TraditionGiftGrant.objects.filter(tradition=active_row.tradition).values_list(
            "signature_techniques", flat=True
        )
    )
    ids.discard(None)
    return ids


def _shopping_list(
    sheet: CharacterSheet,
    demands: list[SphinxDemand],
    known_technique_ids: set[int],
) -> list[SphinxShoppingItem]:
    """Up to ``_SHOPPING_LIST_PER_FUNCTION`` learnable techniques per uncovered function.

    "Learnable" = ``can_learn_technique`` passes OR the technique is in the
    sheet's tradition's signature pool. Bounded: one query per uncovered
    function (typically a handful), each capped to a small candidate pool
    before the per-candidate learnability check.
    """
    target_functions = _uncovered_target_functions(demands)
    if not target_functions:
        return []
    signature_ids = _signature_technique_ids(sheet)

    shopping_list: list[SphinxShoppingItem] = []
    for function in sorted(target_functions):
        candidates = (
            Technique.objects.filter(function_tags__function=function)
            .exclude(pk__in=known_technique_ids)
            .select_related("gift", "style")
            .distinct()
            .order_by("name")[:_SHOPPING_CANDIDATE_POOL]
        )
        found = 0
        for technique in candidates:
            if found >= _SHOPPING_LIST_PER_FUNCTION:
                break
            if technique.pk in signature_ids or can_learn_technique(sheet, technique):
                shopping_list.append(
                    SphinxShoppingItem(
                        technique_name=technique.name,
                        gift_name=technique.gift.name,
                        function=function,
                    )
                )
                found += 1
    return shopping_list


def judge_vow(sheet: CharacterSheet, role: CovenantRole) -> SphinxVerdict:
    """The Sphinx's verdict on ``sheet`` taking up ``role``'s vow (#2640).

    Demand = the role's (+ parent's, for a sub-role) specialty functions
    UNION the creator-functions its SELF-beneficiary situational perks (+
    rungs) require. Supply = the sheet's known-technique function tags.
    Tier: all demands covered -> TAKES; >=1 covered -> DORMANT; 0 covered (or
    demands is empty) -> TAKES when empty / NOT_YET otherwise — see
    ``_tier_for``. Shopping list only populated for NOT_YET/DORMANT verdicts
    (empty when every demand is covered).
    """
    role_ids = _role_ids_for_judgment(role)
    supply = _kit_supply(sheet)

    demands = _specialty_demands(role_ids, supply) + _situation_demands(role_ids, supply)
    tier = _tier_for(demands)

    known_technique_ids = set(
        CharacterTechnique.objects.filter(character=sheet).values_list("technique_id", flat=True)
    )
    shopping_list = _shopping_list(sheet, demands, known_technique_ids)

    return SphinxVerdict(
        tier=tier,
        role_name=role.name,
        demands=demands,
        shopping_list=shopping_list,
    )


def _tradition_function_pools(tradition_ids: list[int]) -> dict[int, set[str]]:
    """Bulk: tradition id -> union of function tags over its grants' signature pool.

    One query total via the ``TraditionGiftGrant.signature_techniques``
    reverse relation (``Technique.granted_by_tradition_gifts``) — no
    per-tradition query loop.
    """
    rows = TechniqueFunctionTag.objects.filter(
        technique__granted_by_tradition_gifts__tradition_id__in=tradition_ids
    ).values_list("technique__granted_by_tradition_gifts__tradition_id", "function")
    pools: dict[int, set[str]] = {}
    for tradition_id, function in rows:
        pools.setdefault(tradition_id, set()).add(function)
    return pools


def _anchor_role_specialty_functions(role_ids: list[int]) -> dict[int, set[str]]:
    """Bulk: anchor role id -> its own specialty-function demand set.

    One query total. Unlike ``judge_vow``, the audit is anchor-role-only (no
    sub-role parent-union) — it is asking "which PRIMARY vows are swearable,"
    the entry point every new covenant member picks from first.
    """
    rows = CovenantRoleTechniqueSpecialty.objects.filter(covenant_role_id__in=role_ids).values_list(
        "covenant_role_id", "function"
    )
    demand: dict[int, set[str]] = {}
    for role_id, function in rows:
        demand.setdefault(role_id, set()).add(function)
    return demand


def audit_vow_coverage() -> list[SphinxCoverageRow]:
    """Staff coverage audit: every active anchor role x every active Tradition (#2640).

    "Which vows are swearable today, per tradition" — validation-plan
    instrument 2, built FIRST per the spec's build order (it runs the same
    kit∩demand join across the whole catalog instead of one character).

    Deliberately narrower than ``judge_vow``: compares only against each
    role's SPECIALTY-function demand set. Situation demands are excluded here
    because a situational perk's creator-function demand is about a live
    character's DB state (an applied condition, a disposition value) at
    judgment time — a tradition's technique POOL has no such state to check
    against in the abstract, so folding situation demands into this
    catalog-level pass would silently misreport "swearable" for a vow whose
    non-specialty half can only ever be judged per-character.
    """
    anchor_roles = list(
        CovenantRole.objects.filter(parent_role__isnull=True).order_by("covenant_type", "name")
    )
    traditions = list(Tradition.objects.filter(is_active=True).order_by("sort_order", "name"))
    if not anchor_roles or not traditions:
        return []

    demand_by_role = _anchor_role_specialty_functions([role.pk for role in anchor_roles])
    pool_by_tradition = _tradition_function_pools([tradition.pk for tradition in traditions])

    rows: list[SphinxCoverageRow] = []
    for role in anchor_roles:
        demand = demand_by_role.get(role.pk, set())
        for tradition in traditions:
            pool = pool_by_tradition.get(tradition.pk, set())
            if not demand:
                rows.append(
                    SphinxCoverageRow(
                        role_name=role.name,
                        tradition_name=tradition.name,
                        coverage="full",
                        missing_functions=[],
                    )
                )
                continue
            missing = demand - pool
            if not missing:
                coverage: Literal["full", "partial", "none"] = "full"
            elif missing == demand:
                coverage = "none"
            else:
                coverage = "partial"
            rows.append(
                SphinxCoverageRow(
                    role_name=role.name,
                    tradition_name=tradition.name,
                    coverage=coverage,
                    missing_functions=sorted(missing),
                )
            )
    return rows

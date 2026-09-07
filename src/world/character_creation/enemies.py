"""Who wants the character to fail, and what the world pays for it (#3621).

The one place the enemy rule lives. ``enemy_price`` reads the two scales; ``enemy_offers``
assembles what a draft may pick (its answered Lineage groups and persons, plus what its
Beginning puts in the way); ``resolve_enemy`` turns the draft's pick into the priced,
placed-or-pending row finalize writes. Serializers, the purse and finalize all read
through here rather than re-deriving any of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.character_creation.constants import (
    ENEMY_PRICE_GROUP,
    ENEMY_PRICE_PENDING,
    ENEMY_PRICE_PERSON,
    QuestionKind,
)
from world.character_creation.questionnaire import DraftAnswers, anchor_for
from world.character_sheets.types import EnemyDegree, EnemyKind, EnemyPowerTier, EnemyStatus
from world.societies.models import Organization

if TYPE_CHECKING:
    from world.character_creation.models import CharacterDraft

SOURCE_LINEAGE = "lineage"
SOURCE_BEGINNING = "beginning"


@dataclass(frozen=True)
class EnemyOffer:
    """One person or group the draft may name as its enemy."""

    kind: str
    organization_id: int | None
    name: str
    reach: str  # a group's reach; "" for a person
    power_tier: str  # a person's power when the offer fixes it; "" when the player rates them
    why: str  # the Beginning's gloss; "" for a Lineage offer
    source: str  # SOURCE_LINEAGE or SOURCE_BEGINNING


@dataclass(frozen=True)
class ResolvedEnemy:
    """The draft's enemy pick, priced and placed (or pending staff placement)."""

    kind: str
    organization_id: int | None
    name: str
    figure_name: str
    power_tier: str
    reach: str
    degree: str
    price: int
    status: str
    why: str
    public_line: str


def enemy_price(kind: str, scale: str, degree: str) -> int:
    """CG points awarded: a group by its reach, a person by their power, both by degree.

    An empty ``scale`` is an unplaced enemy (no real group, no rated person) and prices at
    ``ENEMY_PRICE_PENDING`` until staff place it.
    """
    table = ENEMY_PRICE_PERSON if kind == EnemyKind.PERSON else ENEMY_PRICE_GROUP
    row = table.get(scale)
    if row is None:
        return ENEMY_PRICE_PENDING
    return row.get(degree, ENEMY_PRICE_PENDING)


def price_tables() -> dict[str, dict[str, dict[str, int]]]:
    """Both scales, for the leaf to show so the ledger line is never a surprise."""
    return {"group": ENEMY_PRICE_GROUP, "person": ENEMY_PRICE_PERSON}


def _reach_of(org: Organization, override: str = "") -> str:
    return override or org.org_type.reach


def _lineage_offers(draft: CharacterDraft) -> list[EnemyOffer]:
    template = draft.selected_origin_template
    if template is None:
        return []
    answers = DraftAnswers.from_draft(draft)
    visible = draft.visible_origin_slot_ids()
    slots = [s for s in template.slots.select_related("same_anchor_as") if s.id in visible]
    org_ids = {anchor for anchor in (anchor_for(slot, draft, answers) for slot in slots) if anchor}
    orgs = {o.pk: o for o in Organization.objects.filter(pk__in=org_ids).select_related("org_type")}
    offers: list[EnemyOffer] = []
    seen: set[tuple[str, str]] = set()
    for slot in slots:
        org = orgs.get(anchor_for(slot, draft, answers))
        if slot.kind == QuestionKind.GROUP and org is not None:
            key = (EnemyKind.GROUP, org.name)
            if key in seen:
                continue
            seen.add(key)
            offers.append(
                EnemyOffer(
                    kind=EnemyKind.GROUP,
                    organization_id=org.pk,
                    name=org.name,
                    reach=_reach_of(org),
                    power_tier="",
                    why="",
                    source=SOURCE_LINEAGE,
                )
            )
        elif slot.kind == QuestionKind.PERSON:
            name = answers.figures.get(slot.id, "")
            if not name or (EnemyKind.PERSON, name) in seen:
                continue
            seen.add((EnemyKind.PERSON, name))
            offers.append(
                EnemyOffer(
                    kind=EnemyKind.PERSON,
                    organization_id=org.pk if org is not None else None,
                    name=name,
                    reach="",
                    power_tier="",
                    why="",
                    source=SOURCE_LINEAGE,
                )
            )
    return offers


def _beginning_offers(draft: CharacterDraft) -> list[EnemyOffer]:
    beginning = draft.selected_beginnings
    if beginning is None:
        return []
    offers: list[EnemyOffer] = []
    for row in beginning.enemy_offers.select_related("organization__org_type"):
        if row.is_person:
            offers.append(
                EnemyOffer(
                    kind=EnemyKind.PERSON,
                    organization_id=row.organization_id,
                    name=row.figure_name,
                    reach="",
                    power_tier=row.power_tier,
                    why=row.why,
                    source=SOURCE_BEGINNING,
                )
            )
        elif row.organization_id is not None:
            offers.append(
                EnemyOffer(
                    kind=EnemyKind.GROUP,
                    organization_id=row.organization_id,
                    name=row.organization.name,
                    reach=_reach_of(row.organization, row.reach_override),
                    power_tier="",
                    why=row.why,
                    source=SOURCE_BEGINNING,
                )
            )
    return offers


def enemy_offers(draft: CharacterDraft) -> list[EnemyOffer]:
    """What the draft may pick: its Lineage's groups and persons, then its Beginning's."""
    return _lineage_offers(draft) + _beginning_offers(draft)


def resolve_enemy(draft: CharacterDraft) -> ResolvedEnemy | None:
    """Price and place the draft's enemy pick, or None when the draft named nobody.

    A group with a real Organization takes its reach from the matching offer (so a
    Beginning's override holds) or from its type; a person with a power tier is placed.
    Anything else is pending: priced at ``ENEMY_PRICE_PENDING`` until staff link it.
    """
    data = draft.draft_data.get("enemy") or {}
    degree = data.get("degree", "")
    if degree not in EnemyDegree.values:
        return None
    kind = EnemyKind.PERSON if data.get("kind") == EnemyKind.PERSON else EnemyKind.GROUP
    org_id = data.get("organization_id")
    org = (
        Organization.objects.filter(pk=org_id).select_related("org_type").first()
        if org_id
        else None
    )
    name = (data.get("name") or "").strip()
    offers_by_target = {(o.kind, o.organization_id, o.name): o for o in enemy_offers(draft)}
    if kind == EnemyKind.GROUP:
        reach = ""
        if org is not None:
            offer = offers_by_target.get((EnemyKind.GROUP, org.pk, org.name))
            reach = offer.reach if offer is not None else _reach_of(org)
            name = org.name
        scale, tier = reach, ""
    else:
        tier = data.get("power_tier", "")
        if tier not in EnemyPowerTier.values:
            tier = ""
        scale, reach = tier, ""
    placed = bool(scale)
    return ResolvedEnemy(
        kind=kind,
        organization_id=org.pk if org is not None else None,
        name=name,
        figure_name=name if kind == EnemyKind.PERSON or org is None else "",
        power_tier=tier,
        reach=reach,
        degree=degree,
        price=enemy_price(kind, scale, degree) if placed else ENEMY_PRICE_PENDING,
        status=EnemyStatus.PLACED if placed else EnemyStatus.PENDING,
        why=(data.get("why") or "").strip(),
        public_line=(data.get("public_line") or "").strip(),
    )

"""A deity's companion: what its Codex entry shows beside the prose (#4198).

Registered from ``world/worship/apps.py`` ``ready()`` through the Codex's companion
registry; the Codex never imports this package (ADR-0010, ADR-4198). Every fact here is
one the deity editor writes (``editor_services.save_being``); this is the first reader
of those rows.
"""

from __future__ import annotations

from world.codex.models import CodexEntry
from world.codex.types import (
    Companion,
    CompanionGroup,
    CompanionItem,
    CompanionReader,
    CompanionSection,
)
from world.game_clock.services import format_ic_month_day
from world.worship.constants import BeingRelationshipValence, BeingResonanceTier
from world.worship.models import (
    BeingFacet,
    BeingRelationship,
    BeingTarotCard,
    WorshippedBeing,
)

_DOMAINS = "Domains"
_ALSO_CALLED = "Also called"
_FEAST_DAYS = "Feast days"
_FEAST_DAY_ONE = "Feast day"
_CARDS = "Cards"
_FACETS = "Facets"
_FEAST_DAY = "Feast day"
_REVERSED = " reversed"
# The rail's relationship groups, in the order they are drawn.
_VALENCE_ORDER = (
    BeingRelationshipValence.ALLY,
    BeingRelationshipValence.RIVAL,
    BeingRelationshipValence.FEUD,
    BeingRelationshipValence.UNKNOWN,
)


def feast_day_anchor(ic_month: int, ic_day: int) -> str:
    return f"feast-{ic_month}-{ic_day}"


def relationship_anchor(other_being_id: int) -> str:
    return f"relationship-{other_being_id}"


def being_companion(entry: CodexEntry, reader: CompanionReader) -> Companion | None:
    """The companion for a deity's entry; ``None`` when no being owns ``entry``.

    Groups in the rail's order, each left out when empty; a feast day's story and this
    god's side of a relationship become sections under the Lore.
    """
    being = WorshippedBeing.objects.filter(codex_entry=entry).order_by("pk").first()
    if being is None:
        return None
    rail: list[CompanionGroup] = []
    sections: list[CompanionSection] = []
    _group(rail, _DOMAINS, [CompanionItem(being.domains.strip())] if being.domains.strip() else [])
    _group(
        rail,
        _ALSO_CALLED,
        [
            CompanionItem(name)
            for name in being.nicknames.order_by("pk").values_list("name", flat=True)
        ],
    )
    _feast_days(being, rail, sections)
    _cards(being, rail)
    _resonances(being, rail)
    _group(
        rail,
        _FACETS,
        [
            CompanionItem(row.facet.name)
            for row in BeingFacet.objects.filter(being=being)
            .select_related("facet")
            .order_by("facet__name")
        ],
    )
    _relationships(being, reader, rail, sections)
    return Companion(rail=rail, sections=sections)


def _group(rail: list[CompanionGroup], label: str, items: list[CompanionItem]) -> None:
    if items:
        rail.append(CompanionGroup(label, items))


def _feast_days(
    being: WorshippedBeing, rail: list[CompanionGroup], sections: list[CompanionSection]
) -> None:
    """Calendar order; a day with a story gets a section and its rail line anchors to it."""
    items: list[CompanionItem] = []
    for day in being.feast_days.order_by("ic_month", "ic_day"):
        anchor = feast_day_anchor(day.ic_month, day.ic_day)
        when = format_ic_month_day(day.ic_month, day.ic_day)
        story = day.lore.strip()
        items.append(CompanionItem(f"{day.name} · {when}", anchor=anchor if story else None))
        if story:
            sections.append(
                CompanionSection(
                    anchor=anchor, label=_FEAST_DAY, name=day.name, when=when, body=story
                )
            )
    _group(rail, _FEAST_DAY_ONE if len(items) == 1 else _FEAST_DAYS, items)


def _cards(being: WorshippedBeing, rail: list[CompanionGroup]) -> None:
    """A card has no entry of its own today, so a card line never links anywhere."""
    links = BeingTarotCard.objects.filter(being=being).select_related("card")
    _group(
        rail,
        _CARDS,
        [
            CompanionItem(f"{link.card.name}{_REVERSED if link.is_reversed else ''}")
            for link in links.order_by("card__name", "is_reversed")
        ],
    )


def _resonances(being: WorshippedBeing, rail: list[CompanionGroup]) -> None:
    by_tier: dict[str, list[CompanionItem]] = {}
    for row in being.resonances.select_related("resonance").order_by("resonance__name"):
        by_tier.setdefault(row.tier, []).append(CompanionItem(row.resonance.name))
    for tier in (BeingResonanceTier.FAVORED, BeingResonanceTier.ASSOCIATED):
        _group(rail, tier.label, by_tier.get(tier, []))


def _relationships(
    being: WorshippedBeing,
    reader: CompanionReader,
    rail: list[CompanionGroup],
    sections: list[CompanionSection],
) -> None:
    """One rail group per valence and one section per told story, naming only the
    gods whose entry the reader may open: a relationship to a god the reader cannot
    see would reveal that god exists."""
    by_valence: dict[str, list[CompanionItem]] = {}
    told: dict[str, list[CompanionSection]] = {}
    rows = (
        BeingRelationship.objects.filter(being_a=being)
        | BeingRelationship.objects.filter(being_b=being)
    ).select_related("being_a", "being_b")
    for row in rows.order_by("pk"):
        other = row.being_b if row.being_a_id == being.pk else row.being_a
        if not reader.may_see(other.codex_entry_id):
            continue
        story = row.story_from(being.pk).strip()
        anchor = relationship_anchor(other.pk) if story else None
        by_valence.setdefault(row.valence, []).append(
            CompanionItem(other.name, entry_id=other.codex_entry_id, anchor=anchor)
        )
        if story:
            told.setdefault(row.valence, []).append(
                CompanionSection(
                    anchor=relationship_anchor(other.pk),
                    label=BeingRelationshipValence(row.valence).label,
                    name=other.name,
                    entry_id=other.codex_entry_id,
                    body=story,
                )
            )
    for valence in _VALENCE_ORDER:
        _group(rail, valence.label, by_valence.get(valence, []))
    for valence in _VALENCE_ORDER:
        sections.extend(told.get(valence, []))

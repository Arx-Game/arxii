"""What the vow page reads about one vow, never writing (#4880, slice 2 of #4843).

Every function here is a read: the picks grouped by level, the budget per level,
who holds each pick, which techniques the vow's added effects ride, a one-line
summary of every payload row, and, for an edit not yet saved, which holders'
totals it moves. The budget is read from the ``VowFocusPickConfig`` singleton
without creating it, the same rule the Combat roles panel keeps on a GET.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
import re
from urllib.parse import urlencode

from django.urls import reverse

from world.covenants.added_effect_summary import summarize_vow_added_effect
from world.covenants.added_effects import (
    effect_rides_technique,
    payload_prefetches,
    techniques_by_function,
)
from world.covenants.constants import (
    FOCUS_PICK_FREQUENCY_LIMIT_KINDS,
    FOCUS_PICK_LIMIT_FREQUENCY_FULL,
    VOW_FOCUS_PICK_MAX_LEVEL,
)
from world.covenants.focus_picks import pick_price
from world.covenants.models import (
    CharacterVowFocusPick,
    CovenantRole,
    CovenantRoleTechniqueSpecialty,
    VowAddedEffect,
    VowFocusPick,
    VowFocusPickConfig,
    VowFocusPickLimit,
    VowSituationalPerk,
    VowSituationalPerkRung,
    VowSituationalPerkSituation,
    VowStatScaling,
)

#: How many technique names the rail lists under a group before "N more".
RIDES_SAMPLE = 3


@dataclass(frozen=True)
class PickRow:
    """One focus pick as the page's table shows it on a GET."""

    pick: VowFocusPick
    price: int
    held_by: int
    limits: str


@dataclass(frozen=True)
class LevelGroup:
    """The picks offered at one pick level, ordered by name."""

    level: int
    picks: list[PickRow] = field(default_factory=list)


@dataclass(frozen=True)
class BudgetRow:
    """One pick level's offered prices against the budget a holder may spend there."""

    level: int
    offered: int
    budget: int


@dataclass(frozen=True)
class TechniqueLink:
    """A catalog technique's name and its admin change page."""

    name: str
    url: str


@dataclass(frozen=True)
class RidesRow:
    """A specialty, or a group of the vow's added effects, and the techniques it rides."""

    label: str
    count: int
    techniques: list[TechniqueLink]

    @property
    def more(self) -> int:
        return max(0, self.count - len(self.techniques))


@dataclass(frozen=True)
class RidesSummary:
    """The rail's rows, and how many techniques each specialty function rides."""

    rows: list[RidesRow]
    specialty_counts: dict[str, int]


@dataclass(frozen=True)
class PayloadLine:
    """One payload row in plain words, with its stock admin pages."""

    kind: str
    summary: str
    change_url: str

    @property
    def popup_url(self) -> str:
        return f"{self.change_url}?_popup=1"


@dataclass(frozen=True)
class HolderImpact:
    """What an unsaved edit does to one holder's spend at one pick level."""

    holder_name: str
    picks_url: str
    level: int
    old_total: int
    new_total: int
    budget: int
    #: Every pick the holder chose at this level, as (pk, stored name).
    chosen: tuple[tuple[int, str], ...] = ()

    @property
    def over(self) -> bool:
        return self.new_total > self.budget


@dataclass(frozen=True)
class HolderLine:
    """One holder under one changed pick: the other picks they hold there, and the result."""

    impact: HolderImpact
    others: list[str]

    @property
    def text(self) -> str:
        """What follows the holder's name, e.g. "also holds Static Halo and goes over ..."."""
        impact = self.impact
        verb = "goes over" if impact.over else "stays within"
        result = f"{verb} level {impact.level}'s budget ({impact.new_total} of {impact.budget})."
        if self.others:
            return f"also holds {_and_list(self.others)} and {result}"
        return result


#: Spelled-out counts for the warning's opening sentence.
_COUNT_WORDS = ("No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine")


@dataclass(frozen=True)
class PickChange:
    """One held pick an unsaved edit reprices or deletes, with each holder it moves."""

    name: str
    old_price: int
    new_price: int | None
    holders: list[HolderLine]

    @property
    def headline(self) -> str:
        count = len(self.holders)
        if self.new_price is None:
            noun = "holder" if count == 1 else "holders"
            return f"Deleting {self.name} returns its price to {count} {noun}."
        word = _COUNT_WORDS[count] if count < len(_COUNT_WORDS) else str(count)
        holds = "character holds it" if count == 1 else "characters hold it"
        return (
            f"{self.name}'s price goes from {self.old_price} to {self.new_price}. {word} {holds}."
        )


def _and_list(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


#: How long the header chip's description clause may run before it is cut.
CLAUSE_LENGTH = 40


def description_clause(text: str) -> str:
    """The description's first clause, lower-cased, for the header chip: "ranged damage"."""
    first = re.split(r"[.;:,!?\n]", text.strip(), maxsplit=1)[0].strip()
    if len(first) > CLAUSE_LENGTH:
        first = first[:CLAUSE_LENGTH].rsplit(" ", 1)[0] + "..."
    if len(first) > 1 and first[1:2].islower():
        first = first[0].lower() + first[1:]
    return first


def focus_pick_budget() -> int:
    """The budget per pick level, read without creating the config row on a GET."""
    config = VowFocusPickConfig.objects.cached_singleton()
    if config is None:
        return VowFocusPickConfig().budget_per_level
    return config.budget_per_level


def role_picks(role: CovenantRole) -> list[VowFocusPick]:
    """The vow's picks by level then name.

    Each pick's limits come from its own ``cached_limits``, which the identity map keeps
    between requests and a limit's save or delete clears.
    """
    return list(VowFocusPick.objects.filter(covenant_role=role).order_by("pick_level", "name"))


def holders_by_pick(role: CovenantRole) -> dict[int, int]:
    """How many live memberships chose each of the vow's picks, in one query."""
    pick_ids = CharacterVowFocusPick.objects.filter(
        pick__covenant_role=role, character_role__left_at__isnull=True
    ).values_list("pick_id", flat=True)
    return dict(Counter(pick_ids))


def limits_text(limits: list[VowFocusPickLimit]) -> str:
    """The pick's limits in one short line: "Target ×0.5, Cost -1", or "none"."""
    parts: list[str] = []
    for limit in limits:
        label = limit.get_kind_display()
        if limit.kind in FOCUS_PICK_FREQUENCY_LIMIT_KINDS:
            parts.append(f"{label} ×{limit.frequency_tenths / FOCUS_PICK_LIMIT_FREQUENCY_FULL}")
        else:
            parts.append(f"{label} -{limit.reduction}")
    return ", ".join(parts) or "none"


def picks_by_level(role: CovenantRole) -> list[LevelGroup]:
    """Every pick level from 1 to the maximum, each with its picks (an empty level too)."""
    held = holders_by_pick(role)
    groups = {level: LevelGroup(level=level) for level in range(1, VOW_FOCUS_PICK_MAX_LEVEL + 1)}
    for pick in role_picks(role):
        group = groups.setdefault(pick.pick_level, LevelGroup(level=pick.pick_level))
        group.picks.append(
            PickRow(
                pick=pick,
                price=pick_price(pick),
                held_by=held.get(pick.pk, 0),
                limits=limits_text(pick.cached_limits),
            )
        )
    return [groups[level] for level in sorted(groups)]


def budget_rows(role: CovenantRole) -> list[BudgetRow]:
    """Each pick level's total offered price against the budget per level."""
    budget = focus_pick_budget()
    offered: dict[int, int] = dict.fromkeys(range(1, VOW_FOCUS_PICK_MAX_LEVEL + 1), 0)
    for pick in role_picks(role):
        offered[pick.pick_level] = offered.get(pick.pick_level, 0) + pick_price(pick)
    return [BudgetRow(level=level, offered=offered[level], budget=budget) for level in offered]


def _rides_label(effect: VowAddedEffect) -> str:
    function = effect.get_function_display()
    if effect.technique_id is not None:
        return f"{function}, only {effect.technique.name}"
    if effect.gift_id is not None:
        return f"{function}, {effect.gift.name}"
    return f"{function}, any gift"


def _rides_row(label: str, techniques: list) -> RidesRow:
    return RidesRow(
        label=label,
        count=len(techniques),
        techniques=[
            TechniqueLink(name=t.name, url=_change_url("technique", t.pk))
            for t in techniques[:RIDES_SAMPLE]
        ],
    )


def rides_summary(role: CovenantRole) -> RidesSummary:
    """What the vow rides: each specialty, then the added effects by function and narrowing.

    A specialty rides every catalog technique carrying its function; an added effect group
    narrows that list through the cast path's own ``effect_rides_technique``. One query for
    the specialties, one for the effects, one for every technique they name.
    """
    specialties = list(CovenantRoleTechniqueSpecialty.objects.filter(covenant_role=role))
    effects = VowAddedEffect.objects.filter(covenant_role=role).select_related("gift", "technique")
    groups: dict[tuple[str, int | None, int | None], VowAddedEffect] = {}
    for effect in effects:
        groups.setdefault((effect.function, effect.gift_id, effect.technique_id), effect)
    by_function = techniques_by_function(
        {s.function for s in specialties} | {e.function for e in groups.values()}
    )
    rows = [
        _rides_row(f"{s.get_function_display()} specialty", by_function[s.function])
        for s in sorted(specialties, key=lambda s: s.get_function_display())
    ]
    effect_rows = [
        _rides_row(
            _rides_label(effect),
            [
                technique
                for technique in by_function[effect.function]
                if effect_rides_technique(effect, technique, {effect.function})
            ],
        )
        for effect in groups.values()
    ]
    rows.extend(sorted(effect_rows, key=lambda row: row.label))
    counts = {s.function: len(by_function[s.function]) for s in specialties}
    return RidesSummary(rows=rows, specialty_counts=counts)


def _change_url(model_name: str, pk: int) -> str:
    return reverse(f"admin:arxii_{model_name}_change", args=[pk])


def add_url(model_name: str, role: CovenantRole, pick: VowFocusPick | None = None) -> str:
    """The stock admin add form for a payload row, prefilled with the vow and the pick."""
    params: dict[str, int] = {"covenant_role": role.pk}
    if pick is not None:
        params["focus_pick"] = pick.pk
    query = urlencode({**params, "_popup": 1})
    return f"{reverse(f'admin:arxii_{model_name}_add')}?{query}"


def _perk_summary(
    perk: VowSituationalPerk, situations: list[str], rungs: list[VowSituationalPerkRung]
) -> str:
    parts = [perk.get_beneficiary_display(), perk.get_effect_kind_display()]
    if situations:
        parts.append(f"when {' and '.join(situations)}")
    parts.append(f"{perk.magnitude_tenths} tenths")
    summary = f"{perk.name}: {', '.join(parts)}"
    for rung in rungs:
        summary += (
            f" · rung {rung.rung_number}: {rung.get_extra_situation_display()}, "
            f"{rung.magnitude_tenths} tenths"
        )
    return summary


def _scaling_summary(scaling: VowStatScaling) -> str:
    return f"{scaling.modifier_target.name} {scaling.bonus_per_level:+d} per thread level"


def payload_summaries(role: CovenantRole) -> dict[int | None, list[PayloadLine]]:
    """Every payload row of the vow keyed by its focus pick's pk (``None`` is the base vow)."""
    lines: dict[int | None, list[PayloadLine]] = {}
    effects = (
        VowAddedEffect.objects.filter(covenant_role=role)
        .select_related("gift", "technique")
        .prefetch_related(*payload_prefetches())
    )
    for effect in effects:
        lines.setdefault(effect.focus_pick_id, []).append(
            PayloadLine(
                kind="Added effect",
                summary=summarize_vow_added_effect(effect),
                change_url=_change_url("vowaddedeffect", effect.pk),
            )
        )
    situations: dict[int, list[str]] = {}
    for row in VowSituationalPerkSituation.objects.filter(perk__covenant_role=role):
        situations.setdefault(row.perk_id, []).append(row.get_situation_display())
    rungs: dict[int, list[VowSituationalPerkRung]] = {}
    for rung in VowSituationalPerkRung.objects.filter(perk__covenant_role=role).order_by(
        "perk_id", "rung_number"
    ):
        rungs.setdefault(rung.perk_id, []).append(rung)
    for perk in VowSituationalPerk.objects.filter(covenant_role=role):
        lines.setdefault(perk.focus_pick_id, []).append(
            PayloadLine(
                kind="Situational perk",
                summary=_perk_summary(perk, situations.get(perk.pk, []), rungs.get(perk.pk, [])),
                change_url=_change_url("vowsituationalperk", perk.pk),
            )
        )
    scalings = VowStatScaling.objects.filter(covenant_role=role).select_related("modifier_target")
    for scaling in scalings:
        lines.setdefault(scaling.focus_pick_id, []).append(
            PayloadLine(
                kind="Stat scaling",
                summary=_scaling_summary(scaling),
                change_url=_change_url("vowstatscaling", scaling.pk),
            )
        )
    return lines


@dataclass(frozen=True)
class StoredPick:
    """A pick's name, level and price as the database holds them, read before any form binds."""

    name: str
    level: int
    price: int


def stored_picks(role: CovenantRole) -> dict[int, StoredPick]:
    """Each of the vow's picks as stored, keyed by pk.

    Validating a pick or limit form writes the posted values onto the identity-mapped
    row, so a POST reads this before binding and hands it to ``holder_impact``.
    """
    return {
        pick.pk: StoredPick(name=pick.name, level=pick.pick_level, price=pick_price(pick))
        for pick in role_picks(role)
    }


def holder_impact(
    role: CovenantRole,
    new_prices: Mapping[int, int | None],
    stored: Mapping[int, StoredPick] | None = None,
) -> list[HolderImpact]:
    """Each live holder whose spend at a level an edit moves, with old and new totals.

    ``new_prices`` maps a pick of ``role`` to the price the edit leaves it at, or
    ``None`` for a pick the edit deletes. A pick whose price does not change moves
    nothing. A holder's total at a level counts every pick they chose there, a sub-role
    holder's picks from the anchor's catalog too; a deleted pick drops out of it.
    ``stored`` is ``stored_picks(role)`` read before any form bound; without it the
    picks are read now.
    """
    stored = dict(stored) if stored is not None else stored_picks(role)
    changed = {
        pick_id
        for pick_id, price in new_prices.items()
        if pick_id in stored and price != stored[pick_id].price
    }
    if not changed:
        return []
    choices = list(
        CharacterVowFocusPick.objects.filter(
            character_role__left_at__isnull=True,
            character_role__focus_picks__pick_id__in=changed,
        )
        .distinct()
        .select_related("character_role__character_sheet__character", "pick")
        .order_by("character_role__character_sheet__character__db_key", "pick__pick_level")
    )

    def old_price(choice: CharacterVowFocusPick) -> int:
        if choice.pick_id in stored:
            return stored[choice.pick_id].price
        return pick_price(choice.pick)

    def new_price(choice: CharacterVowFocusPick) -> int:
        if choice.pick_id in new_prices:
            return new_prices[choice.pick_id] or 0
        return old_price(choice)

    by_membership_level: dict[tuple[int, int], list[CharacterVowFocusPick]] = {}
    for choice in choices:
        level = stored[choice.pick_id].level if choice.pick_id in stored else choice.pick.pick_level
        by_membership_level.setdefault((choice.character_role_id, level), []).append(choice)
    budget = focus_pick_budget()
    impacts: list[HolderImpact] = []
    for (membership_id, level), level_choices in by_membership_level.items():
        if not any(choice.pick_id in changed for choice in level_choices):
            continue
        sheet = level_choices[0].character_role.character_sheet
        impacts.append(
            HolderImpact(
                holder_name=sheet.character.db_key,
                picks_url=(
                    f"{reverse('admin:arxii_charactervowfocuspick_changelist')}"
                    f"?character_role__id__exact={membership_id}"
                ),
                level=level,
                old_total=sum(old_price(choice) for choice in level_choices),
                new_total=sum(new_price(choice) for choice in level_choices),
                budget=budget,
                chosen=tuple(
                    (
                        choice.pick_id,
                        stored[choice.pick_id].name
                        if choice.pick_id in stored
                        else choice.pick.name,
                    )
                    for choice in level_choices
                ),
            )
        )
    return impacts


def pick_changes(
    role: CovenantRole,
    new_prices: Mapping[int, int | None],
    stored: Mapping[int, StoredPick] | None = None,
) -> list[PickChange]:
    """Each held pick an edit reprices or deletes, with every holder it moves (#4880).

    Built on ``holder_impact``: a pick with no live holder is left out, since its
    price change moves nobody. Ordered by level, then name, as the page lists picks.
    """
    stored = dict(stored) if stored is not None else stored_picks(role)
    impacts = holder_impact(role, new_prices, stored)
    changes: list[PickChange] = []
    ordered = sorted(stored.items(), key=lambda item: (item[1].level, item[1].name))
    for pick_id, pick in ordered:
        if pick_id not in new_prices or new_prices[pick_id] == pick.price:
            continue
        holders = [
            HolderLine(
                impact=impact,
                others=[name for chosen_id, name in impact.chosen if chosen_id != pick_id],
            )
            for impact in impacts
            if any(chosen_id == pick_id for chosen_id, _ in impact.chosen)
        ]
        if holders:
            changes.append(
                PickChange(
                    name=pick.name,
                    old_price=pick.price,
                    new_price=new_prices[pick_id],
                    holders=holders,
                )
            )
    return changes

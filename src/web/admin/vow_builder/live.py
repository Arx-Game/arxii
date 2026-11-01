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
from urllib.parse import urlencode

from django.urls import reverse

from world.covenants.added_effect_summary import summarize_vow_added_effect
from world.covenants.added_effects import payload_prefetches, techniques_ridden_by
from world.covenants.constants import (
    FOCUS_PICK_FREQUENCY_LIMIT_KINDS,
    FOCUS_PICK_LIMIT_FREQUENCY_FULL,
    VOW_FOCUS_PICK_MAX_LEVEL,
)
from world.covenants.focus_picks import pick_price
from world.covenants.models import (
    CharacterVowFocusPick,
    CovenantRole,
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
class RidesRow:
    """A group of the vow's added effects and the catalog techniques they ride."""

    label: str
    count: int
    names: list[str]

    @property
    def more(self) -> int:
        return max(0, self.count - len(self.names))


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

    @property
    def over(self) -> bool:
        return self.new_total > self.budget


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


def rides_summary(role: CovenantRole) -> list[RidesRow]:
    """The vow's added effects grouped by function and narrowing, with the techniques ridden.

    One technique query per group, through the same catalog match the cast path uses.
    """
    effects = VowAddedEffect.objects.filter(covenant_role=role).select_related("gift", "technique")
    groups: dict[tuple[str, int | None, int | None], VowAddedEffect] = {}
    for effect in effects:
        groups.setdefault((effect.function, effect.gift_id, effect.technique_id), effect)
    rows: list[RidesRow] = []
    for effect in groups.values():
        names = list(techniques_ridden_by(effect).values_list("name", flat=True))
        rows.append(
            RidesRow(label=_rides_label(effect), count=len(names), names=names[:RIDES_SAMPLE])
        )
    return sorted(rows, key=lambda row: row.label)


def _change_url(model_name: str, pk: int) -> str:
    return reverse(f"admin:arxii_{model_name}_change", args=[pk])


def add_url(model_name: str, role: CovenantRole, pick: VowFocusPick | None = None) -> str:
    """The stock admin add form for a payload row, prefilled with the vow and the pick."""
    params: dict[str, int] = {"covenant_role": role.pk}
    if pick is not None:
        params["focus_pick"] = pick.pk
    query = urlencode({**params, "_popup": 1})
    return f"{reverse(f'admin:arxii_{model_name}_add')}?{query}"


def _perk_summary(perk: VowSituationalPerk, situations: list[str], rungs: int) -> str:
    parts = [perk.get_beneficiary_display(), perk.get_effect_kind_display()]
    if situations:
        parts.append(f"when {' and '.join(situations)}")
    parts.append(f"{perk.magnitude_tenths} tenths")
    if rungs:
        parts.append(f"{rungs} rung{'s' if rungs != 1 else ''}")
    return f"{perk.name}: {', '.join(parts)}"


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
    rungs = Counter(
        VowSituationalPerkRung.objects.filter(perk__covenant_role=role).values_list(
            "perk_id", flat=True
        )
    )
    for perk in VowSituationalPerk.objects.filter(covenant_role=role):
        lines.setdefault(perk.focus_pick_id, []).append(
            PayloadLine(
                kind="Situational perk",
                summary=_perk_summary(perk, situations.get(perk.pk, []), rungs[perk.pk]),
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


def holder_impact(role: CovenantRole, new_prices: Mapping[int, int | None]) -> list[HolderImpact]:
    """Each live holder whose spend at a level an edit moves, with old and new totals.

    ``new_prices`` maps a pick of ``role`` to the price the edit leaves it at, or
    ``None`` for a pick the edit deletes. A pick whose price does not change moves
    nothing. A holder's total at a level counts every pick they chose there, a sub-role
    holder's picks from the anchor's catalog too; a deleted pick drops out of it.
    """
    old_prices = {pick.pk: pick_price(pick) for pick in role_picks(role)}
    changed = {
        pick_id
        for pick_id, price in new_prices.items()
        if pick_id in old_prices and price != old_prices[pick_id]
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
    by_membership_level: dict[tuple[int, int], list[CharacterVowFocusPick]] = {}
    for choice in choices:
        key = (choice.character_role_id, choice.pick.pick_level)
        by_membership_level.setdefault(key, []).append(choice)
    budget = focus_pick_budget()
    impacts: list[HolderImpact] = []
    for (membership_id, level), level_choices in by_membership_level.items():
        if not any(choice.pick_id in changed for choice in level_choices):
            continue
        old_total = sum(pick_price(choice.pick) for choice in level_choices)
        new_total = sum(
            (new_prices[choice.pick_id] or 0)
            if choice.pick_id in new_prices
            else pick_price(choice.pick)
            for choice in level_choices
        )
        sheet = level_choices[0].character_role.character_sheet
        impacts.append(
            HolderImpact(
                holder_name=sheet.character.db_key,
                picks_url=(
                    f"{reverse('admin:arxii_charactervowfocuspick_changelist')}"
                    f"?character_role__id__exact={membership_id}"
                ),
                level=level,
                old_total=old_total,
                new_total=new_total,
                budget=budget,
            )
        )
    return impacts

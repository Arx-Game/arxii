"""The plain-words lines read for a vow's payload rows (#4581).

Built only from the row's own fields: enum labels, the names of the rows it points
at, and the payload clauses a technique sentence uses. It never reads free prose, so
what staff read back in admin is exactly what the row does.

    From thread 3. On covenant allies' Weaken casts, in a fight, when Target Is a
    Boss, once a fight: Deals Fire damage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.covenants.constants import VowEffectContext, VowEffectFrequency
from world.covenants.perks.constants import PerkBeneficiary
from world.magic.services.technique_effects import (
    condition_payload,
    damage_payload,
    render_payload_clauses,
    treatment_payload,
)

if TYPE_CHECKING:
    from world.covenants.models import (
        VowAddedEffect,
        VowSituationalPerk,
        VowSituationalPerkRung,
        VowStatScaling,
    )

NOTHING_YET = "Adds nothing yet."

_WHOSE: dict[str, str] = {
    PerkBeneficiary.SELF: "On your own",
    PerkBeneficiary.COVENANT_ALLIES: "On covenant allies'",
    PerkBeneficiary.WHOLE_GROUP: "On your and covenant allies'",
}
_CONTEXT_QUALIFIER: dict[str, str] = {
    VowEffectContext.IN_COMBAT: "in a fight",
    VowEffectContext.OUT_OF_COMBAT: "outside a fight",
}
_FREQUENCY_QUALIFIER: dict[str, str] = {
    VowEffectFrequency.ONCE_PER_ROUND: "once a round",
    VowEffectFrequency.ONCE_PER_FIGHT: "once a fight",
}


def _qualifiers(effect: VowAddedEffect) -> list[str]:
    """Where, when and how often the effect fires, in the order a reader scans them."""
    found = [_CONTEXT_QUALIFIER.get(effect.cast_context, "")]
    if effect.situation:
        found.append(f"when {effect.get_situation_display()}")
    found.append(_FREQUENCY_QUALIFIER.get(effect.frequency, ""))
    return [qualifier for qualifier in found if qualifier]


def summarize_vow_added_effect(effect: VowAddedEffect) -> str:
    """One plain-words line for *effect*: whose casts, how narrowed, and what it adds."""
    opening = f"From thread {effect.unlock_thread_level}. " if effect.unlock_thread_level else ""
    subject = effect.technique.name if effect.technique_id else effect.get_function_display()
    head = f"{opening}{_WHOSE.get(effect.beneficiary, '')} {subject} casts"
    if effect.gift_id:
        head += f" of {effect.gift.name}"
    for qualifier in _qualifiers(effect):
        head += f", {qualifier}"
    clauses = render_payload_clauses(
        applies=[condition_payload(row) for row in effect.cached_applied_conditions],
        removes=[condition_payload(row) for row in effect.cached_removed_conditions],
        damage=[damage_payload(row) for row in effect.cached_damage_profiles],
        treatments=[treatment_payload(row) for row in effect.cached_treatments],
    )
    return f"{head}: {' '.join(clauses) or NOTHING_YET}"


def summarize_situational_perk(
    perk: VowSituationalPerk, situations: list[str], rungs: list[VowSituationalPerkRung]
) -> str:
    """One line for a situational perk: who gains it, what, when, and its rungs.

    Shared by the vow page (#4880) and the holder's pick catalog (#4929).
    """
    effect = perk.get_effect_kind_display()
    if perk.roll_kind:
        # "Applies to" (#5092): e.g. "Check Bonus on attack rolls".
        effect = f"{effect} on {perk.get_roll_kind_display().lower()}"
    parts = [perk.get_beneficiary_display(), effect]
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


def summarize_stat_scaling(scaling: VowStatScaling) -> str:
    """One line for a stat scaling: the target and its bonus per thread level."""
    return f"{scaling.modifier_target.name} {scaling.bonus_per_level:+d} per thread level"

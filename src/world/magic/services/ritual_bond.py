"""What an Anima ritual with a partner earns and costs (#5181).

The ritual always has a partner. With a resonance the ritual names, it also earns that
resonance (``AnimaRitualResonanceAward`` at the roll's tier, plus the kindled share when the
resonance is kindled at that moment) and does something to the partner's fatigue: the
affinity of that resonance sets whether it takes fatigue, eases it or does neither
(``Affinity.ritual_partner_fatigue``).

``apply_ritual_bond`` does the earning and the fatigue, and takes the partner as an argument so
a later ritual that takes in a whole scene can call it once per member. The lines each side
reads, and the sentence the partner's consent prompt carries, are built here too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.constants import ActionCategory
from world.fatigue.constants import EffortLevel
from world.fatigue.services import apply_fatigue, recover_fatigue
from world.magic.constants import GainSource
from world.magic.models import AnimaRitualResonanceAward
from world.magic.services.kindling import kindled_for, kindling_context_for
from world.magic.services.resonance import grant_resonance
from world.magic.types.ritual import RitualBond

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance, Ritual

TAKES_FATIGUE_SENTENCE = "It will add to your fatigue."
EASES_FATIGUE_SENTENCE = "It will ease your fatigue."


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def ritual_partner_effect_sentence(resonance: Resonance | None) -> str:
    """The sentence a partner reads before agreeing: what the ritual will do to their fatigue.

    Blank when the ritual names no resonance, or the affinity's ``ritual_partner_fatigue`` is 0.
    """
    if resonance is None:
        return ""
    setting = _sign(resonance.affinity.ritual_partner_fatigue)
    if setting > 0:
        return TAKES_FATIGUE_SENTENCE
    if setting < 0:
        return EASES_FATIGUE_SENTENCE
    return ""


def _resonance_to_earn(
    performer_sheet: CharacterSheet, resonance: Resonance, outcome: object
) -> int:
    """The ritual's earning at ``outcome`` for ``resonance``: the authored amount, plus the
    kindled share of it when the resonance is kindled now. 0 when the tier has no row."""
    award = AnimaRitualResonanceAward.objects.filter(outcome_tier=outcome).first()
    if award is None or award.amount <= 0:
        return 0
    amount = award.amount
    context = kindling_context_for(performer_sheet)
    fed = kindled_for(
        performer_sheet, resonance, resolution=context.resolution, mission=context.mission
    ).fed_tier
    if fed is not None:
        amount += amount * fed.earn_percent // 100
    return amount


def apply_ritual_bond(
    performer_sheet: CharacterSheet,
    partner_sheet: CharacterSheet,
    ritual: Ritual,
    outcome: object,
    resonance: Resonance | None,
) -> RitualBond:
    """Earn the ritual's resonance for the performer and touch the partner's fatigue.

    ``resonance`` is the one the ritual names; None means it earns nothing and does nothing to
    the partner. The pick was checked against the performer's aura when it was set, and it keeps
    working until changed, so no holding check is made here. The earning is paid in full at once
    through ``grant_resonance(source=ANIMA_RITUAL)`` and skipped when it is 0. The partner's
    fatigue, in the social category, rises by the affinity's positive ``ritual_partner_fatigue``
    (scaled by their own fatigue rules, as any fatigue is) or falls by its negative one.
    Corruption is never added. A partner who is an NPC is treated as a player character is.
    """
    if resonance is None:
        return RitualBond()
    amount = _resonance_to_earn(performer_sheet, resonance, outcome)
    granted = 0
    if amount > 0:
        ledger: list = []
        grant_resonance(
            performer_sheet,
            resonance,
            amount,
            source=GainSource.ANIMA_RITUAL,
            deed_label=ritual.name,
            ledger_out=ledger,
        )
        granted = ledger[-1].amount
    setting_value = resonance.affinity.ritual_partner_fatigue
    change = 0
    if setting_value > 0:
        change = apply_fatigue(
            partner_sheet, ActionCategory.SOCIAL, setting_value, EffortLevel.MEDIUM
        )
    elif setting_value < 0:
        change = -recover_fatigue(partner_sheet, ActionCategory.SOCIAL, -setting_value)
    return RitualBond(
        resonance=resonance,
        resonance_granted=granted,
        partner_fatigue_setting=_sign(setting_value),
        fatigue_change=change,
    )


def performer_ritual_line(bond: RitualBond, partner_name: str) -> str:
    """The private line the performer reads, e.g. "Your ritual feeds on Tobin. Your Ruin grows
    by 13."; blank when the ritual named no resonance."""
    if bond.resonance is None:
        return ""
    if bond.partner_fatigue_setting > 0:
        opening = f"Your ritual feeds on {partner_name}."
    elif bond.partner_fatigue_setting < 0:
        opening = f"Your ritual lifts {partner_name}."
    else:
        opening = f"Your ritual with {partner_name} is done."
    if bond.resonance_granted <= 0:
        return opening
    return f"{opening} Your {bond.resonance.name} grows by {bond.resonance_granted}."


def partner_ritual_line(bond: RitualBond, performer_name: str) -> str:
    """The private line the partner reads when their fatigue changed, else blank."""
    if bond.fatigue_change > 0:
        return f"{performer_name}'s ritual leaves you wearier."
    if bond.fatigue_change < 0:
        return f"{performer_name}'s ritual leaves you lighter."
    return ""

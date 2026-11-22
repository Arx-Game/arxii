"""What an Anima ritual with a partner earns and costs (#5181, #5280).

The ritual always has a partner and grows up to two resonances in the performer's aura: a
Primal one for how it feels to her, and a Celestial or Abyssal one for how it reaches the
partner. The award at the roll's tier (``AnimaRitualResonanceAward``) is split between the two
picks in proportion to how the performer's aura is settled (``ritual_earning_parts``), each part
gets the kindled share of its own resonance, and each is granted only for a resonance she holds.

A roll that fails (Failure or Critical Failure) gives no Primal growth. The outward part reaches
the partner: a story NPC's takes hold at once on a success, and a player character partner is
asked, so the part waits on the performance until they answer. The affinity of the outward pick
also sets whether the ritual takes the partner's fatigue, eases it or does neither
(``Affinity.ritual_partner_fatigue``), on any roll.

``apply_ritual_bond`` does the earning and the fatigue, and takes the partner as an argument so
a later ritual that takes in a whole scene can call it once per member. The lines each side
reads, and the sentence the partner's consent prompt carries, are built here too.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from actions.constants import ActionCategory
from world.fatigue.constants import EffortLevel
from world.fatigue.services import apply_fatigue, recover_fatigue
from world.magic.constants import AnimaRitualEndorsement, GainSource
from world.magic.models import AnimaConfig, AnimaRitualResonanceAward, CharacterResonance
from world.magic.services.anima import ritual_succeeded
from world.magic.services.kindling import kindled_for, kindling_context_for
from world.magic.services.resonance import grant_resonance
from world.magic.types.ritual import RitualBond, RitualEarningParts
from world.traits.constants import CANONICAL_OUTCOME_LEVELS

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import AnimaRitualPerformance, Resonance, Ritual
    from world.traits.models import CheckOutcome

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


def _award_total(outcome: CheckOutcome | None) -> int:
    """The authored resonance award at ``outcome``'s tier; 0 when the tier has no row."""
    award = AnimaRitualResonanceAward.objects.filter(outcome_tier=outcome).first()
    return award.amount if award is not None and award.amount > 0 else 0


def _settled_hundredths(sheet: CharacterSheet, resonance: Resonance) -> int:
    """The settled share of ``resonance``'s affinity in ``sheet``'s aura, in hundredths of a
    percent (so it is a whole number); 0 when there is no aura or no share row."""
    aura = sheet.aura_or_none
    if aura is None:
        return 0
    for share in aura.cached_shares:
        if share.affinity_id == resonance.affinity_id:
            return int(share.settled_percent * Decimal(100))
    return 0


def ritual_earning_parts(
    sheet: CharacterSheet, total: int, primal: Resonance | None, outward: Resonance | None
) -> RitualEarningParts:
    """Split ``total`` between the ritual's two picks by how ``sheet``'s aura is settled.

    A lone pick gets the whole total. With both, each pick's weight is the settled share of its
    own affinity, the outward part is the total times its share of the two, rounded down, and
    the Primal part is what is left, so the parts always add up to ``total``. A pick whose
    affinity has no settled share gets nothing from the split, and two empty shares split
    the total in half (the outward part rounds down).
    """
    if outward is None:
        return RitualEarningParts(primal=total if primal is not None else 0, outward=0)
    if primal is None:
        return RitualEarningParts(primal=0, outward=total)
    primal_share = _settled_hundredths(sheet, primal)
    outward_share = _settled_hundredths(sheet, outward)
    if primal_share + outward_share == 0:
        outward_part = total // 2
    else:
        outward_part = total * outward_share // (primal_share + outward_share)
    return RitualEarningParts(primal=total - outward_part, outward=outward_part)


def _with_kindled_share(sheet: CharacterSheet, resonance: Resonance, amount: int) -> int:
    """``amount`` plus the kindled share of it when ``resonance`` is kindled for ``sheet`` now.
    0 stays 0."""
    if amount <= 0:
        return 0
    context = kindling_context_for(sheet)
    fed = kindled_for(
        sheet, resonance, resolution=context.resolution, mission=context.mission
    ).fed_tier
    if fed is not None:
        amount += amount * fed.earn_percent // 100
    return amount


def _holds(sheet: CharacterSheet, resonance: Resonance) -> bool:
    """True when ``sheet`` holds ``resonance`` (a ``CharacterResonance`` row).

    The anima ritual belongs to the account, so another character on it may perform it with a
    pick she does not hold. The ritual feeds the resonances a character already has.
    """
    return CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).exists()


def _grant(sheet: CharacterSheet, resonance: Resonance, amount: int, ritual: Ritual) -> int:
    """Grant ``amount`` of ``resonance`` through the ledger and return what it recorded (0 when
    there was nothing to grant)."""
    if amount <= 0:
        return 0
    ledger: list = []
    grant_resonance(
        sheet,
        resonance,
        amount,
        source=GainSource.ANIMA_RITUAL,
        deed_label=ritual.name,
        ledger_out=ledger,
    )
    return ledger[-1].amount


def _failed_endorsement_pending(
    performer_sheet: CharacterSheet, primal: Resonance | None, outward: Resonance
) -> int:
    """The outward growth held after a failed roll: ``failed_endorsement_percent`` of the
    outward part of the Success tier's award (a failed tier's own award is usually 0 or absent),
    0 when there is no Success award. The tier is found by its success level, not its name, so
    a staff rename cannot zero the endorsement."""
    award = AnimaRitualResonanceAward.objects.filter(
        outcome_tier__success_level=CANONICAL_OUTCOME_LEVELS["Success"]
    ).first()
    if award is None or award.amount <= 0:
        return 0
    parts = ritual_earning_parts(performer_sheet, award.amount, primal, outward)
    outward_part = _with_kindled_share(performer_sheet, outward, parts.outward)
    return outward_part * AnimaConfig.get_singleton().failed_endorsement_percent // 100


def apply_ritual_bond(  # noqa: PLR0913
    performer_sheet: CharacterSheet,
    partner_sheet: CharacterSheet,
    ritual: Ritual,
    outcome: CheckOutcome,
    performance: AnimaRitualPerformance,
    *,
    primal: Resonance | None,
    outward: Resonance | None,
) -> RitualBond:
    """Earn the ritual's resonances for the performer and touch the partner's fatigue.

    ``primal`` and ``outward`` are the picks the ritual names (None for a pick it has none of);
    they were checked against the performer's aura when set, and keep working until changed.
    The award at the roll's tier is split by ``ritual_earning_parts``, each part gets the
    kindled share of its own resonance, and a part is earned only for a resonance the performer
    holds now.

    On a success the Primal part is granted through ``grant_resonance(source=ANIMA_RITUAL)``,
    and a failure gives none. The outward part reaches the partner: a story NPC's is granted at
    once on a success and never after a failure. A player character partner's is stored on
    ``performance`` as pending, to be granted when they endorse: all of it after a success,
    after a failure ``failed_endorsement_percent`` of the outward part of the Success tier's
    award. Nothing is stored (and the partner is not asked) when that amount is 0.

    The partner's fatigue, in the social category, follows the outward pick's affinity on any
    roll: it rises by a positive ``ritual_partner_fatigue`` (scaled by their own fatigue rules,
    as any fatigue is) or falls by a negative one. Corruption is never added.
    """
    from world.roster.services.activity import is_player_character  # noqa: PLC0415

    succeeded = ritual_succeeded(outcome)
    parts = ritual_earning_parts(performer_sheet, _award_total(outcome), primal, outward)

    primal_granted = 0
    if succeeded and primal is not None and _holds(performer_sheet, primal):
        primal_amount = _with_kindled_share(performer_sheet, primal, parts.primal)
        primal_granted = _grant(performer_sheet, primal, primal_amount, ritual)

    outward_granted = 0
    outward_pending = 0
    endorsement = AnimaRitualEndorsement.NOT_ASKED
    if outward is not None and _holds(performer_sheet, outward):
        if is_player_character(partner_sheet):
            if succeeded:
                outward_pending = _with_kindled_share(performer_sheet, outward, parts.outward)
            else:
                outward_pending = _failed_endorsement_pending(performer_sheet, primal, outward)
            if outward_pending > 0:
                endorsement = AnimaRitualEndorsement.PENDING
                performance.endorsement = endorsement
                performance.outward_resonance = outward
                performance.outward_amount_pending = outward_pending
                performance.save(
                    update_fields=["endorsement", "outward_resonance", "outward_amount_pending"]
                )
        elif succeeded:
            outward_amount = _with_kindled_share(performer_sheet, outward, parts.outward)
            outward_granted = _grant(performer_sheet, outward, outward_amount, ritual)

    setting_value = outward.affinity.ritual_partner_fatigue if outward is not None else 0
    change = 0
    if setting_value > 0:
        change = apply_fatigue(
            partner_sheet, ActionCategory.SOCIAL, setting_value, EffortLevel.MEDIUM
        )
    elif setting_value < 0:
        change = -recover_fatigue(partner_sheet, ActionCategory.SOCIAL, -setting_value)
    return RitualBond(
        primal_resonance=primal,
        primal_granted=primal_granted,
        outward_resonance=outward,
        outward_granted=outward_granted,
        outward_pending=outward_pending,
        endorsement=endorsement,
        partner_fatigue_setting=_sign(setting_value),
        fatigue_change=change,
    )


def performer_ritual_line(bond: RitualBond, partner_name: str, anima_recovered: int) -> str:
    """The private line the performer reads after the roll, e.g. "Your ritual feeds on Tobin.
    You recover 6 anima. Your Ruin grows by 13."; each sentence after the opening is left out
    when its number is 0. The outward growth appears only when it was granted at once (a story
    NPC partner after a success)."""
    if bond.partner_fatigue_setting > 0:
        line = f"Your ritual feeds on {partner_name}."
    elif bond.partner_fatigue_setting < 0:
        line = f"Your ritual lifts {partner_name}."
    else:
        line = f"Your ritual with {partner_name} is done."
    if anima_recovered > 0:
        line += f" You recover {anima_recovered} anima."
    if bond.primal_granted > 0 and bond.primal_resonance is not None:
        line += f" Your {bond.primal_resonance.name} grows by {bond.primal_granted}."
    if bond.outward_granted > 0 and bond.outward_resonance is not None:
        line += f" Your {bond.outward_resonance.name} grows by {bond.outward_granted}."
    return line


def partner_endorsement_prompt(performer_name: str, outward: Resonance) -> str:
    """The question a player character partner is asked about the ritual's outward part."""
    return (
        f"{performer_name}'s ritual reached for your {outward.name.lower()}. "
        "Did it take hold of you?"
    )


def partner_ritual_line(bond: RitualBond, performer_name: str) -> str:
    """The private line the partner reads when their fatigue changed, else blank."""
    if bond.fatigue_change > 0:
        return f"{performer_name}'s ritual leaves you wearier."
    if bond.fatigue_change < 0:
        return f"{performer_name}'s ritual leaves you lighter."
    return ""

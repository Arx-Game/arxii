"""The fatigue a resonance gain costs whoever pays for it (#5327).

Each affinity carries one staff-set number, ``Affinity.gain_fatigue``: what one gain in a
resonance of that affinity costs its payer, before any fatigue reduction the payer has. Who pays
follows the affinity: Primal and Celestial tire the character who gains, Abyssal tires the
character the gain was taken from (the act's target), and nobody when that target is a game-run
opponent with no sheet.

A payer who is running low pays what they can: the gain shrinks in proportion to the room they
have left and stops at nothing. Nobody is pushed into the Exhausted zone by someone else's gain,
and no collapse check runs. A payer whose capacity is not set up pays nothing and the gain is
not reduced.

``charge_gain_fatigue`` takes the payer and the pool from its caller, so a gain that points at no
act (an endorsed reach, an accepted proposal, a GM's tag) calls it too. ``gain_fatigue_payer``
is the one rule for who the payer is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from django.db import transaction

from world.fatigue.constants import EffortLevel
from world.fatigue.services import add_fatigue_points, fatigue_cost_for, fatigue_room
from world.magic.constants import AFFINITY_ABYSSAL
from world.magic.types.marking import GainFatigueCharge

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance

_SOMEONE = "Someone"
_YOU = "you"


def gain_fatigue_payer(
    gainer: CharacterSheet, resonance: Resonance, target: CharacterSheet | None
) -> CharacterSheet | None:
    """Who pays the fatigue of ``gainer`` gaining ``resonance``.

    An Abyssal resonance tires ``target``, the character the gain was taken from, and nobody
    when there is none (a game-run opponent has no sheet). Any other affinity tires the
    gainer. For a Celestial gain from an act the gainer is the character who acted.
    """
    if resonance.affinity.name == AFFINITY_ABYSSAL:
        return target
    return gainer


def charge_gain_fatigue(
    gainer: CharacterSheet,
    payer: CharacterSheet | None,
    resonance: Resonance,
    category: str,
    amount: int,
) -> GainFatigueCharge:
    """Charge ``payer`` the fatigue of a gain of ``amount`` in ``resonance``, from ``category``.

    ``payer`` is who ``gain_fatigue_payer`` named (or whoever a caller with no act chose);
    None charges nobody and leaves ``amount`` as it is, as does an affinity whose
    ``gain_fatigue`` is 0 and a payer whose capacity is not set up. Otherwise the cost is
    ``Affinity.gain_fatigue`` through ``fatigue_cost_for`` at medium effort, so any fatigue
    reduction the payer has applies once. When the payer's room (``fatigue_room``) is below
    that cost, the amount becomes ``amount * room // cost`` and the payer is charged the room;
    at no room, or when the shrunk amount is 0, nothing is charged and the returned amount is
    0, so the caller refuses the gain and consumes nothing.

    When someone other than ``gainer`` is charged, they are told in one private line once the
    surrounding transaction commits.
    """
    unchanged = GainFatigueCharge(amount=amount, charged=0, payer=payer)
    base_cost = resonance.affinity.gain_fatigue
    if payer is None or amount <= 0 or base_cost <= 0:
        return unchanged
    room = fatigue_room(payer, category)
    if room is None:
        return unchanged
    cost = fatigue_cost_for(payer, base_cost, EffortLevel.MEDIUM)
    if room >= cost:
        charged, paid, shrunk = cost, amount, False
    else:
        charged, paid, shrunk = room, amount * room // cost, True
        if paid <= 0:
            return GainFatigueCharge(amount=0, charged=0, payer=payer, shrunk=True)
    add_fatigue_points(payer, category, charged)
    if payer.pk != gainer.pk:
        transaction.on_commit(_told_payer(payer, gainer, resonance, shrunk=shrunk))
    return GainFatigueCharge(amount=paid, charged=charged, payer=payer, shrunk=shrunk)


def _payer_is_gainer(charge: GainFatigueCharge, gainer: CharacterSheet) -> bool:
    return charge.payer is None or charge.payer.pk == gainer.pk


def payer_name(charge: GainFatigueCharge, gainer: CharacterSheet) -> str:
    """How ``gainer`` names whoever pays: "you" for herself, else the name she knows them by."""
    if _payer_is_gainer(charge, gainer):
        return _YOU
    return _name_for(gainer, charge.payer)  # ty: ignore[invalid-argument-type]


def refusal_line(charge: GainFatigueCharge, gainer: CharacterSheet, resonance: Resonance) -> str:
    """What ``gainer`` reads when a gain was refused because its payer is worn, and what to do
    next: "Hale is too worn to pay for this, so your Cruelty does not grow. The act stays on
    your list. Mark it again once Hale has recovered, or mark another act." Herself as the
    payer it reads "You were too worn ...", "... once you have recovered ..."."""
    who = payer_name(charge, gainer)
    if _payer_is_gainer(charge, gainer):
        lead, again = "You were too worn to pay for this", "you have"
    else:
        lead, again = f"{who} is too worn to pay for this", f"{who} has"
    return (
        f"{lead}, so your {resonance.name} does not grow. The act stays on your list. "
        f"Mark it again once {again} recovered, or mark another act."
    )


def shrink_reason(charge: GainFatigueCharge, gainer: CharacterSheet) -> str:
    """The "because ..." clause of a gain that shrank: "because Hale had little left to give",
    or "because you had little left to give" when the gainer is the payer."""
    return f"because {payer_name(charge, gainer)} had little left to give"


def stay_small_sentence(charge: GainFatigueCharge, gainer: CharacterSheet) -> str:
    """What to expect next after a gain shrank: "Marks against Hale stay small until they have
    recovered." (or "Marks stay small until you have recovered." for her own fatigue)."""
    if _payer_is_gainer(charge, gainer):
        return "Marks stay small until you have recovered."
    return f"Marks against {payer_name(charge, gainer)} stay small until they have recovered."


def _name_for(viewer: CharacterSheet, sheet: CharacterSheet) -> str:
    """The name ``viewer`` knows ``sheet``'s character by, else a plain "Someone"."""
    from world.magic.services.kindling import shown_names  # noqa: PLC0415

    return shown_names(viewer, [sheet.pk]).get(sheet.pk) or _SOMEONE


def _told_payer(
    payer: CharacterSheet, gainer: CharacterSheet, resonance: Resonance, *, shrunk: bool
) -> Callable[[], None]:
    """The after-commit send of the one private line a payer other than the gainer reads;
    when the charge took only part of the cost it says so."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    def _send() -> None:
        name = _name_for(payer, gainer)
        body = f"{name} marked {resonance.name} on what they did to you. You are wearier."
        if shrunk:
            body += " You had little left to give, so it took only part."
        send_narrative_message(
            recipients=[payer],
            body=body,
            category=NarrativeCategory.SYSTEM,
            ooc_note="Resonance gain fatigue",
        )

    return _send


__all__ = [
    "charge_gain_fatigue",
    "gain_fatigue_payer",
    "payer_name",
    "refusal_line",
    "shrink_reason",
    "stay_small_sentence",
]

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
        transaction.on_commit(_told_payer(payer, gainer, resonance))
    return GainFatigueCharge(amount=paid, charged=charged, payer=payer, shrunk=shrunk)


def worn_clause(charge: GainFatigueCharge, gainer: CharacterSheet) -> str:
    """The sentence telling ``gainer`` a gain shrank or was refused because its payer was worn,
    and what to do next; "" when the gain was not reduced.

    ``charge`` is what ``charge_gain_fatigue`` returned. A gain's payer is the gainer
    ("You are") or another character, named as the gainer knows them.
    """
    if not charge.shrunk:
        return ""
    payer = charge.payer
    if payer is None or payer.pk == gainer.pk:
        who, are, has = "You", "were", "you have"
    else:
        name = _name_for(gainer, payer)
        who, are, has = name, "was", f"{name} has"
    if charge.refused:
        return (
            f"{who} {are} too worn for this to pay anything. "
            f"Mark another act, or wait until {has} recovered."
        )
    return (
        f"{who} {are} too worn to bear all of this, so it paid less. "
        f"Mark another act, or wait until {has} recovered."
    )


def _name_for(viewer: CharacterSheet, sheet: CharacterSheet) -> str:
    """The name ``viewer`` knows ``sheet``'s character by, else a plain "Someone"."""
    from world.magic.services.kindling import shown_names  # noqa: PLC0415

    return shown_names(viewer, [sheet.pk]).get(sheet.pk) or _SOMEONE


def _told_payer(
    payer: CharacterSheet, gainer: CharacterSheet, resonance: Resonance
) -> Callable[[], None]:
    """The after-commit send of the one private line a payer other than the gainer reads."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    def _send() -> None:
        name = _name_for(payer, gainer)
        send_narrative_message(
            recipients=[payer],
            body=f"{name} marked {resonance.name} on what they did to you. You are wearier.",
            category=NarrativeCategory.SYSTEM,
            ooc_note="Resonance gain fatigue",
        )

    return _send


__all__ = ["charge_gain_fatigue", "gain_fatigue_payer", "worn_clause"]

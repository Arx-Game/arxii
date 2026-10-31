"""Lycan moon-control window (#2845, #4802): the pull and its sweep.

A moon-bound character (one carrying a condition with a MOON_PULL control-loss trigger,
Lycan blood innately) under a felt moon pull has the trigger fired each reconcile window.
Everything that decides the roll lives on the trigger and its bands
(``world.conditions.control_loss``): difficulty, relief, tier exemption, and what a
failure does (the forced battle-form shift and the shared Berserk condition).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.conditions.constants import ControlLossFiresOn
from world.species.moon_pull import felt_moon_pull

CANI_UNEASE_MESSAGE = (
    "|wThe moonlight prickles along your spine — something old in your blood "
    "stirs and will not settle while the moon watches.|n"
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

logger = logging.getLogger(__name__)


def is_moon_bound(sheet: CharacterSheet) -> bool:
    """Whether *sheet* carries a condition with a MOON_PULL control-loss trigger."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target_id=sheet.pk,
        condition__control_loss_triggers__fires_on=ControlLossFiresOn.MOON_PULL,
    ).exists()


def reconcile_moon_pull(character) -> None:
    """One moon-bound character's control-loss window (#2845).

    A character already compelled gets a rampage window instead; anyone else has the
    MOON_PULL triggers fired at the pull they feel.
    """
    from world.conditions.control_loss import (  # noqa: PLC0415
        fire_control_loss_triggers,
        has_compulsion,
    )

    sheet = character.character_sheet
    if sheet is None or not is_moon_bound(sheet):
        return
    if has_compulsion(character):
        _rampage_window(character)
        return
    exposure = felt_moon_pull(character, character.location)
    if exposure.pull <= 0:
        return
    outcomes = fire_control_loss_triggers(
        character, ControlLossFiresOn.MOON_PULL, moon_pull=exposure.pull
    )
    if any(outcome.applied is not None for outcome in outcomes):
        _announce_loss(character)


def reconcile_moon_pull_safely(character) -> None:
    """Best-effort moon reconcile for cron call sites (#2845)."""
    from world.species.services import run_reconcile_safely  # noqa: PLC0415

    run_reconcile_safely(character, reconcile_moon_pull, "moon-pull")


def _announce_loss(character) -> None:
    """Tell the character and the room the moon took them."""
    character.msg(
        "|rThe moon's pull crests and something older than you answers it — "
        "the beast takes the reins.|n"
    )
    location = character.location
    if location is not None:
        location.msg_contents(
            f"|r{character.key} convulses under the moonlight — and what rises is "
            "not entirely them anymore.|n",
            exclude=[character],
        )


def _rampage_window(character) -> None:
    """One out-of-combat rampage window while the moon-swept character rages."""
    from world.combat.berserk_compulsion import berserk_rampage_window  # noqa: PLC0415

    berserk_rampage_window(character)


def reconcile_cani_unease(character) -> None:
    """Apply/remove the Cani Moonlit Unease with the open night moon (#2845).

    Ruled 2026-07-31: the Cani umbrella (wolves, hounds, all canine-touched)
    carries the unease — khati subspecies stay umbrella families, so no
    wolf-specific subspecies exists or should. Mechanically inert flavor state
    in v1 (PLACEHOLDER); the message fires once, on application.
    """
    from world.conditions.services import (  # noqa: PLC0415
        apply_condition,
        get_active_conditions,
        remove_condition,
    )
    from world.species.factories import ensure_moonlit_unease_condition  # noqa: PLC0415
    from world.species.moon_constants import MOONLIT_UNEASE_NAME  # noqa: PLC0415

    sheet = character.character_sheet
    if sheet is None or not _is_cani(sheet):
        return
    exposure = felt_moon_pull(character, character.location)
    active = None
    for instance in get_active_conditions(character):
        if instance.condition.name == MOONLIT_UNEASE_NAME:
            active = instance
            break
    if exposure.pull > 0 and active is None:
        template = ensure_moonlit_unease_condition()
        apply_condition(character, template, severity=1, source_character=character)
        character.msg(CANI_UNEASE_MESSAGE)
    elif exposure.pull <= 0 and active is not None:
        remove_condition(character, active.condition)


def _is_cani(sheet: CharacterSheet) -> bool:
    """Whether the sheet's species is (or descends from) the Cani umbrella."""
    from world.species.moon_constants import CANI_SPECIES_NAME  # noqa: PLC0415

    species = sheet.species
    while species is not None:
        if species.name == CANI_SPECIES_NAME:
            return True
        species = species.parent
    return False


def reconcile_cani_unease_safely(character) -> None:
    """Best-effort unease reconcile for the cron sweep (#2845)."""
    from world.species.services import run_reconcile_safely  # noqa: PLC0415

    run_reconcile_safely(character, reconcile_cani_unease, "cani-unease")

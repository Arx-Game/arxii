"""The two resonances an anima ritual grows, picked from the aura (#5280).

A character picks a Primal resonance (how the ritual feels to her) and a Celestial or Abyssal
one (what it reaches for in her partner) from the resonances she holds. The first setup is free
and writes both picks at once; after that the picks are locked, and changing them takes an
attunement. A pick stays on the ritual until it is changed, even when the resonance later leaves
her aura: the ritual keeps feeding it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.constants import AFFINITY_PRIMAL
from world.magic.exceptions import AnimaRitualPickError
from world.magic.models import CharacterResonance, RitualCheckConfig
from world.magic.services.anima import get_character_anima_ritual
from world.magic.types.ritual import AnimaRitualChoices

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance

NO_RITUAL_TO_SET_UP = "You have no anima ritual to set up."
RESONANCES_ARE_SET = "Your ritual's resonances are set. Attune it to change them."
PICK_AT_LEAST_ONE = "Pick at least one resonance."


def _is_primal(resonance: Resonance) -> bool:
    return resonance.affinity.name == AFFINITY_PRIMAL


def ritual_config_of(sheet: CharacterSheet) -> RitualCheckConfig | None:
    """The check config of the character's anima ritual, or None when she has no ritual or it
    has no config."""
    ritual = get_character_anima_ritual(sheet.character)
    return ritual.check_config_or_none if ritual is not None else None


def anima_ritual_choices(sheet: CharacterSheet) -> AnimaRitualChoices:
    """The resonances she holds that each pick may take, and the picks her ritual carries now.

    "Held" is a ``CharacterResonance`` row, whether or not her aura has settled any share in
    that affinity. The two pick fields read as None for a character with no anima ritual.
    """
    held = [
        row.resonance
        for row in CharacterResonance.objects.filter(character_sheet=sheet)
        .select_related("resonance__affinity")
        .order_by("resonance__name")
    ]
    config = ritual_config_of(sheet)
    primal_pick = config.primal_resonance if config is not None else None
    outward_pick = config.outward_resonance if config is not None else None
    return AnimaRitualChoices(
        primal=tuple(r for r in held if _is_primal(r)),
        outward=tuple(r for r in held if not _is_primal(r)),
        primal_pick=primal_pick,
        outward_pick=outward_pick,
        locked=primal_pick is not None or outward_pick is not None,
    )


def _check_pick_is_held(sheet: CharacterSheet, resonance: Resonance) -> None:
    if not CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).exists():
        msg = f"{resonance.name} is not a resonance you hold."
        raise AnimaRitualPickError(msg)


def check_anima_ritual_picks(
    sheet: CharacterSheet, primal: Resonance | None, outward: Resonance | None
) -> None:
    """Refuse picks the ritual cannot take, before anything is written or spent.

    Raises:
        AnimaRitualPickError: no pick at all, a pick she does not hold, a Primal slot given a
            resonance that is not Primal, or the outward slot given a Primal one.
    """
    if primal is None and outward is None:
        raise AnimaRitualPickError(PICK_AT_LEAST_ONE)
    if primal is not None:
        _check_pick_is_held(sheet, primal)
        if not _is_primal(primal):
            msg = f"{primal.name} is not a Primal resonance."
            raise AnimaRitualPickError(msg)
    if outward is not None:
        _check_pick_is_held(sheet, outward)
        if _is_primal(outward):
            msg = f"{outward.name} is a Primal resonance. Pick a Celestial or Abyssal one."
            raise AnimaRitualPickError(msg)


def set_up_anima_ritual_resonances(
    sheet: CharacterSheet, primal: Resonance | None, outward: Resonance | None
) -> RitualCheckConfig:
    """Write the ritual's two picks for free, once. Returns the config that carries them.

    Raises:
        AnimaRitualPickError: she has no ritual, either pick is already set (attuning changes
            them), or the picks fail ``check_anima_ritual_picks``.
        ValidationError: the config fails its own validation (nothing is kept).
    """
    config = ritual_config_of(sheet)
    if config is None:
        raise AnimaRitualPickError(NO_RITUAL_TO_SET_UP)
    with transaction.atomic():
        # Read the stored picks under a row lock, so two setups racing cannot both be free.
        stored = (
            RitualCheckConfig.objects.select_for_update()
            .values("primal_resonance_id", "outward_resonance_id")
            .get(pk=config.pk)
        )
        if stored["primal_resonance_id"] or stored["outward_resonance_id"]:
            raise AnimaRitualPickError(RESONANCES_ARE_SET)
        check_anima_ritual_picks(sheet, primal, outward)
        config.primal_resonance = primal
        config.outward_resonance = outward
        try:
            config.full_clean()
        except ValidationError:
            # The config is a shared cached row: put it back so nobody reads the refused picks.
            config.primal_resonance = None
            config.outward_resonance = None
            raise
        config.save(update_fields=["primal_resonance", "outward_resonance"])
    return config

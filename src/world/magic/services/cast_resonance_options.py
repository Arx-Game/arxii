"""The resonances a cast may be worked in, for the scene cast panel and the combat
declaration (#5231).

One entry per resonance on the caster's thread on the Gift, leading first. The default is
read from ``cast_resonance_for`` and the kindled strength from ``kindled_for_each`` read in
the caster's live fight and mission, so the picker can never disagree with the cast that
follows it. The strength an entry is ranked by is ``kindled_cast_strength``, the number the
kindled cast power term would add for it; a pull is not chosen yet when this list is shown,
so it reports the strength a cast with no pull gets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.services.kindling import kindled_for_each, kindling_context_for
from world.magic.services.power_terms import kindled_cast_strength
from world.magic.specialization.services import cast_resonance_for, gift_resonances_for
from world.magic.types.techniques import CastResonanceOption

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import Technique


def cast_resonance_options(
    # the thread handler and sheet lookups take the character
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
) -> list[CastResonanceOption]:
    """Every resonance a cast of ``technique`` may be worked in, leading first (#5231).

    Empty for a technique with no Gift and for a caster with no character sheet. An entry is
    kindled only when she holds the resonance, the test the cast itself applies. ``stronger``
    is true for the single entry with the highest kindled cast power, when that is above the
    default entry's; a tie for the highest marks none.
    """
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

    if technique.gift_id is None:
        return []
    sheet = _get_character_sheet(character)
    if sheet is None:
        return []
    resonances = gift_resonances_for(character, technique.gift)
    if not resonances:
        return []
    default = cast_resonance_for(character, technique)
    context = kindling_context_for(sheet)
    answers = kindled_for_each(
        sheet, resonances, resolution=context.resolution, mission=context.mission
    )
    held = {entry.resonance_id for entry in sheet.cached_resonances}
    tiers = [
        answer.tier if resonance.pk in held else None
        for resonance, answer in zip(resonances, answers, strict=True)
    ]
    strengths = [
        kindled_cast_strength(resonance, tier)
        for resonance, tier in zip(resonances, tiers, strict=True)
    ]
    default_strength = next(
        (s for r, s in zip(resonances, strengths, strict=True) if default and r.pk == default.pk),
        0,
    )
    top = max(strengths)
    leaders = [i for i, strength in enumerate(strengths) if strength == top]
    stronger = leaders[0] if len(leaders) == 1 and top > default_strength else None
    return [
        CastResonanceOption(
            resonance=resonance,
            is_default=default is not None and resonance.pk == default.pk,
            kindled_strength=tiers[i],
            reasons=answers[i].reasons if tiers[i] is not None else (),
            stronger=i == stronger,
            adds_corruption=resonance.affinity.corruption_coefficient > 0,
        )
        for i, resonance in enumerate(resonances)
    ]

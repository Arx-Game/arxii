"""The resonances a cast may be worked in, for the scene cast panel and the combat
declaration (#5231).

One entry per resonance on the caster's thread on the Gift, leading first, and the cast's own
default as the first entry when it is not on that thread (a worn alternate self's resonance).
The default is read from ``cast_resonance_for`` and the kindled strength from the one kindling
read the caller hands in, so the picker can never disagree with the cast that follows it. The
strength an entry is ranked by is ``kindled_cast_strength``, the number the kindled cast power
term would add for it; a pull is not chosen yet when this list is shown, so it reports the
strength a cast with no pull gets.

A caller listing several techniques reads the kindling once with ``kindling_by_resonance`` and
passes it to each call, so the list costs no kindling queries per technique.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from world.magic.services.kindling import (
    active_mission_for,
    kindled_resonances,
    kindling_context_for,
)
from world.magic.services.power_terms import kindled_cast_strength
from world.magic.specialization.services import (
    cast_resonance_for,
    gift_resonances_for,
    gift_threads_for,
)
from world.magic.types.techniques import CastResonanceOption

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance, Technique
    from world.magic.types.kindling import KindledResonance


def kindling_by_resonance(
    sheet: CharacterSheet, *, resolution: object | None = None
) -> dict[int, KindledResonance]:
    """Resonance id -> the kindling answer for each resonance she holds, read once.

    The reading ``kindled_strength_now`` gives a cast: her live fight and mission with no act,
    or the round the caller already holds as ``resolution`` (her mission is still her newest
    active one). A resonance she does not hold has no entry, so it counts as not kindled.
    """
    if resolution is None:
        context = kindling_context_for(sheet)
        resolution, mission = context.resolution, context.mission
    else:
        mission = active_mission_for(sheet)
    return {
        answer.resonance.pk: answer
        for answer in kindled_resonances(sheet, resolution=resolution, mission=mission)
    }


def stronger_marks(strengths: Sequence[int], default_index: int | None) -> list[bool]:
    """Which entry, if any, is marked stronger: a list of flags, at most one of them true.

    The entry is marked when its strength is the single highest of the list and strictly above
    the default entry's (0 when there is no default entry). A tie for the highest marks none.
    """
    default_strength = strengths[default_index] if default_index is not None else 0
    top = max(strengths, default=0)
    leaders = [i for i, strength in enumerate(strengths) if strength == top]
    stronger = leaders[0] if len(leaders) == 1 and top > default_strength else None
    return [i == stronger for i in range(len(strengths))]


def cast_resonance_options(
    # the thread handler and sheet lookups take the character
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    technique: Technique,
    *,
    sheet: CharacterSheet | None = None,
    kindling: Mapping[int, KindledResonance] | None = None,
) -> list[CastResonanceOption]:
    """Every resonance a cast of ``technique`` may be worked in, the default first if off-thread.

    Empty for a technique with no Gift and for a caster with no character sheet. A caster with
    no thread on the Gift gets only her default entry. The thread's resonances follow in order,
    leading first. An entry is kindled only when she holds the
    resonance, the test the cast itself applies. ``stronger`` is true for the single entry
    with the highest kindled cast power, when that is above the default entry's; a tie for the
    highest marks none.

    A caller that lists several techniques passes the ``sheet`` it holds and the ``kindling``
    it read once (``kindling_by_resonance``); left out, they are read for this call alone.
    """
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

    if technique.gift_id is None:
        return []
    if sheet is None:
        sheet = _get_character_sheet(character)
    if sheet is None:
        return []
    default = cast_resonance_for(character, technique)
    # A caster with no thread on the Gift has no choice to make (#5231): her only entry is the
    # default, so no picker shows and nothing offered would be refused.
    has_thread = bool(gift_threads_for(character, technique.gift))
    resonances = list(gift_resonances_for(character, technique.gift)) if has_thread else []
    # A worn alternate self's resonance is the default without being on the Gift's thread: it is
    # its own entry, first, because choosing it is the same as naming nothing.
    if default is not None and all(resonance.pk != default.pk for resonance in resonances):
        resonances.insert(0, default)
    if not resonances:
        return []
    if kindling is None:
        kindling = kindling_by_resonance(sheet)
    return _options_for(resonances, default, kindling)


def _options_for(
    resonances: list[Resonance],
    default: Resonance | None,
    kindling: Mapping[int, KindledResonance],
) -> list[CastResonanceOption]:
    answers = [kindling.get(resonance.pk) for resonance in resonances]
    tiers = [answer.tier if answer is not None else None for answer in answers]
    strengths = [
        kindled_cast_strength(resonance, tier)
        for resonance, tier in zip(resonances, tiers, strict=True)
    ]
    default_index = next(
        (i for i, resonance in enumerate(resonances) if default and resonance.pk == default.pk),
        None,
    )
    stronger = stronger_marks(strengths, default_index)
    return [
        CastResonanceOption(
            resonance=resonance,
            is_default=i == default_index,
            kindled_strength=tiers[i],
            reasons=answers[i].reasons if answers[i] is not None and tiers[i] is not None else (),
            stronger=stronger[i],
            adds_corruption=resonance.affinity.corruption_coefficient > 0,
        )
        for i, resonance in enumerate(resonances)
    ]

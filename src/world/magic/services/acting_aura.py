"""The aura a character acts with: an active alternate self's affinity, else the true aura.

Power-side readers (the aura-alignment power term, resonance of place, covenant
affinity situations) read this. Identity-side readers (Fall threshold, Soul Tether,
atonement, the sheet display, gates) keep reading the true ``CharacterAura``.
Derive-on-read (ADR-0014): nothing is written when an alternate self is assumed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.magic.specialization.services import active_alt_self_resonance
from world.magic.types.aura import ActingAura

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Affinity, Resonance


def acting_aura(sheet: CharacterSheet) -> ActingAura | None:
    """The aura ``sheet``'s character acts with right now.

    ``None`` when the sheet has no ``CharacterAura`` and no active alternate self
    carrying a resonance.
    """
    resonance = active_alt_self_resonance(sheet)
    alternate_affinity = resonance.affinity if resonance is not None else None
    try:
        true_aura = sheet.aura
    except ObjectDoesNotExist:
        true_aura = None
    if true_aura is None and alternate_affinity is None:
        return None
    return ActingAura(true_aura=true_aura, alternate_affinity=alternate_affinity)


def working_affinities(
    sheet: CharacterSheet | None, resonances: Iterable[Resonance]
) -> list[Affinity]:
    """The distinct affinities a cast works in, in the order the resonances give them.

    ``resonances`` are the gift's resonances for this character
    (``gift_resonances_for``). While an alternate self with a resonance is worn, that
    resonance replaces them, as it does in variant resolution
    (``_effective_variant_resonance``), so her own techniques work in the affinity she
    acts with (#4731). Read by the aura-alignment power term and the cast-time
    resonance of place. Empty when the gift has no resonance for her.
    """
    resonances = list(resonances)
    if not resonances:
        return []
    if sheet is not None:
        alternate = active_alt_self_resonance(sheet)
        if alternate is not None:
            return [alternate.affinity]
    seen: set[int] = set()
    result: list[Affinity] = []
    for resonance in resonances:
        if resonance.affinity_id not in seen:
            seen.add(resonance.affinity_id)
            result.append(resonance.affinity)
    return result

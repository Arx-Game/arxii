"""Defilement: a CASTER_DOMINANT caster overpowering an opposed place (issue #525).

When a strong-enough caster overpowers a place it opposes on a
``caster_dominance_defiles`` interaction (today: an Abyssal caster vs a Primal
place #6 or a Celestial place #4), the caster DEFILES the place:

1. **Degrade** the place's dominant opposed resonance(s) toward zero.
2. **Spread** the casting technique's Abyssal resonance(s) onto the room — repeated
   defilement eventually flips the room to Abyssal "corrupted ground".
3. **Caster->world corruption** routed through the existing ``CORRUPTION_ACCRUING``
   event (an additional increment atop baseline abyssal-cast accrual), so a Sinner's
   Hollow / Soul Tether absorbs it with zero new wiring.

This is a core magic-physics service (a peer of ``resonance_environment_for_cast``),
called from the technique-use orchestrator's Step 10. It emits no events of its own
and runs no flows; the only event is the one ``accrue_corruption`` already emits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.locations.services import effective_value, upsert_room_resonance_modifier
from world.magic.constants import ResonanceDirection
from world.magic.services.corruption import accrue_corruption
from world.magic.services.resonance_environment import (
    _get_room_resonances,
    evaluate_resonance_environment,
    get_resonance_environment_config,
    magical_profile,
)
from world.magic.types.corruption import CorruptionSource

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.techniques import Technique
    from world.magic.services.resonance_environment import ResonanceEnvironmentEffect
    from world.magic.types.techniques import TechniqueUseResult

#: ``LocationValueModifier.source`` tag for cascade rows mutated by defilement.
DEFILE_SOURCE = "defilement"

#: Affinity whose resonances corrupt the world (case-insensitive name match).
_ABYSSAL = "abyssal"


@transaction.atomic
def defile_place_for_cast(  # noqa: C901 — +1 branch for the cached-effect bypass (#722); not worth extracting
    *,
    caster_sheet: CharacterSheet,
    room_profile: RoomProfile,
    technique: Technique,
    technique_result: TechniqueUseResult,
    effect: ResonanceEnvironmentEffect | None = None,
) -> None:
    """Apply defilement for a cast, if the caster overpowers an opposed place.

    No-op unless the resonance-environment primitive resolves to
    ``CASTER_DOMINANT`` on a ``caster_dominance_defiles`` interaction. Gated by
    ``magical_profile`` (Quiescent casters / NPCs without an aura do nothing).

    When ``effect`` is passed in, the call skips its own
    ``evaluate_resonance_environment`` — the orchestrator computes it once at
    Step 10 and feeds the same value here AND into
    ``resonance_environment_for_cast`` (saves ~4-5 queries per cast).
    """
    aura = magical_profile(caster_sheet)
    if aura is None:
        return

    # Down-convert at the primitive boundary (mirrors resonance_environment_for_cast).
    caster = caster_sheet.character
    room = room_profile.objectdb

    if effect is None:
        effect = evaluate_resonance_environment(caster=caster, room=room, technique=technique)
    interaction = effect.interaction
    if (
        effect.direction != ResonanceDirection.CASTER_DOMINANT
        or interaction is None
        or not interaction.caster_dominance_defiles
    ):
        return

    cfg = get_resonance_environment_config()

    # 1. Degrade the place's dominant opposed resonance(s), flooring effective value at 0.
    place_affinity = effect.environment_affinity
    if place_affinity is not None and cfg.defile_degrade_per_cast > 0:
        for resonance in _get_room_resonances(room):
            if resonance.affinity_id != place_affinity.pk:
                continue
            current = effective_value(room, resonance=resonance)
            if current <= 0:
                continue
            delta = -min(cfg.defile_degrade_per_cast, current)
            upsert_room_resonance_modifier(
                room_profile, resonance, source=DEFILE_SOURCE, delta=delta
            )

    # The technique's Abyssal resonances drive spread + extra corruption.
    abyssal_resonances = [
        inv.resonance
        for inv in technique_result.resonance_involvements
        if inv.resonance.affinity.name.lower() == _ABYSSAL
    ]
    for resonance in abyssal_resonances:
        # 2. Spread Abyssal taint onto the room.
        if cfg.defile_spread_per_cast > 0:
            upsert_room_resonance_modifier(
                room_profile, resonance, source=DEFILE_SOURCE, delta=cfg.defile_spread_per_cast
            )
        # 3. Caster->world corruption via the interceptable CORRUPTION_ACCRUING event.
        if cfg.defile_corruption_per_cast > 0:
            accrue_corruption(
                character_sheet=caster_sheet,
                resonance=resonance,
                amount=cfg.defile_corruption_per_cast,
                source=CorruptionSource.DEFILEMENT,
            )

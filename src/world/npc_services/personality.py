"""The thin NPC personality layer (#2827 phase 4).

Instantiated NPCs get a few likes/dislikes drawn from the authored
`PersonalityTrait` vocabulary at materialization. Consumers read one
function: `preference_modifier(npc_persona, check_type)` — approach an NPC
through what they love and the roll against them eases; through what they
despise and it hardens. Aligned with ADR-0058's durable disposition tier
(preferences hang on personas, never on placements).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from world.npc_services.models import NpcPreference, PersonalityTrait, PreferenceValence

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.scenes.models import Persona

# PLACEHOLDER calibration: how many traits a fresh instantiation rolls.
PERSONALITY_LIKES_PER_NPC = 2
PERSONALITY_DISLIKES_PER_NPC = 1


def assign_random_personality(persona: Persona) -> int:
    """Give a freshly-materialized NPC their quirks. Idempotent-ish: no-op
    when the persona already has any preference rows. Returns rows created."""
    if NpcPreference.objects.filter(persona=persona).exists():
        return 0
    traits = list(PersonalityTrait.objects.filter(is_active=True))
    if not traits:
        return 0
    count = min(len(traits), PERSONALITY_LIKES_PER_NPC + PERSONALITY_DISLIKES_PER_NPC)
    # S311/NOSONAR: game RNG for NPC flavor, not crypto.
    picks = random.sample(traits, k=count)  # NOSONAR
    created = 0
    for index, trait in enumerate(picks):
        valence = (
            PreferenceValence.LIKES
            if index < PERSONALITY_LIKES_PER_NPC
            else PreferenceValence.DISLIKES
        )
        NpcPreference.objects.create(persona=persona, trait=trait, valence=valence)
        created += 1
    return created


def preference_modifier(npc_persona: Persona | None, check_type: CheckType | None) -> int:
    """Points of ease (+) or resistance (−) this NPC gives ``check_type`` rolls
    made against them. 0 for faceless NPCs or checks nobody has feelings about."""
    if npc_persona is None or check_type is None:
        return 0
    rows = NpcPreference.objects.filter(
        persona=npc_persona,
        trait__is_active=True,
        trait__eased_check=check_type,
    ).select_related("trait")
    total = 0
    for row in rows:
        magnitude = row.trait.ease_magnitude
        total += magnitude if row.valence == PreferenceValence.LIKES else -magnitude
    return total

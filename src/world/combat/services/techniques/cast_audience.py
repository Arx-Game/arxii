"""The audience a combat cast reaches."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatParticipant

if TYPE_CHECKING:
    from world.magic.models import Technique
    from world.magic.services.cast_observation import CastAudience


def _resolve_combat_cast_audience(
    participant: CombatParticipant,
    technique: Technique,
) -> CastAudience:
    """Who perceived this action, and how much of it they could attribute (#2734).

    Delegates to the shipped #2710 service, which early-returns an unconcealed
    audience — no queries, no checks — whenever attribution cannot be hidden: a
    SAME-reach technique (you are standing on your target), or a caster whose style
    imposes no concealment. That is the overwhelmingly common case, and the reason an
    ordinary encounter costs nothing extra.
    """
    from world.magic.services.cast_observation import resolve_cast_audience  # noqa: PLC0415

    # No cast_openly equivalent in combat: CombatRoundAction has no such field, so a
    # combat cast always resolves at the caster's style concealment. A deliberate
    # in-combat reveal is its own UX surface (out of scope, #2734).
    return resolve_cast_audience(caster=participant.character_sheet.character, technique=technique)

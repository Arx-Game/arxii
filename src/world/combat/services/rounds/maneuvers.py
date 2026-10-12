"""Standalone maneuver resolver table."""

from __future__ import annotations

from collections.abc import Callable

from world.combat.constants import CombatManeuver
from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.services.declarations.demoralize import _resolve_demoralize
from world.combat.services.declarations.flee import _resolve_flee
from world.combat.services.declarations.joust import _resolve_joust
from world.combat.services.declarations.parley import _resolve_parley
from world.combat.services.declarations.rally import _resolve_rally
from world.combat.services.declarations.taunt import _resolve_taunt
from world.combat.services.declarations.use_item import _resolve_use_item
from world.combat.types import ActionOutcome

#: Maneuvers that resolve wholly on their own, short-circuiting the technique
#: pipeline in :func:`_resolve_pc_action`. COVER is deliberately absent — it
#: falls through to the passives-only return, since its effect is the
#: ``cover_bonus`` it contributes to the sheltered ally's flee check.
_STANDALONE_MANEUVER_RESOLVERS: dict[
    str, Callable[[CombatParticipant, CombatRoundAction], ActionOutcome]
] = {
    CombatManeuver.FLEE: _resolve_flee,
    # Social/mental combat verbs (#2015): resolve as checks at round-tick.
    CombatManeuver.RALLY: _resolve_rally,
    CombatManeuver.DEMORALIZE: _resolve_demoralize,
    CombatManeuver.TAUNT: _resolve_taunt,
    CombatManeuver.PARLEY: _resolve_parley,
    # On-use items as a combat maneuver (#2023): dispatches the existing
    # UseItemAction as a primary maneuver (mutually exclusive with the focused
    # technique, like FLEE/COVER). Using an item costs the round's focused action.
    CombatManeuver.USE_ITEM: _resolve_use_item,
    # JOUST (#1843): a bilateral opposed pass between two mounted, lance-armed
    # duelists — resolved directly against the loser's mirror CombatOpponent,
    # not through the normal per-target technique pipeline (there is no single
    # "attacker vs one opponent" shape here).
    CombatManeuver.JOUST: _resolve_joust,
}

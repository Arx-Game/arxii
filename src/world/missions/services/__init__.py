"""Missions service layer (Phase 1).

Public surface: :func:`bindings_for_character`, which turns the authored-once
affordance bindings into the concrete options an acting character can take
against a challenge.
"""

from world.missions.services.affordances import bindings_for_character

__all__ = ["bindings_for_character"]

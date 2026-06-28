"""Placeholder-position effects no-op instead of crashing on cast (#1584).

Teleport / obstacle / telekinesis are seeded with placeholder destination/position
ids (0) until runtime destination selection ships. Because Task 14d made every
effect technique castable (action_template), an unguarded ``Position.objects.get(pk=0)``
would raise ``Position.DoesNotExist`` on cast and propagate through the flow engine.
The CONDITION_APPLIED adapters guard the placeholder so the cast is a no-op instead.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from world.areas.positioning.models import PositionEdge
from world.magic.services.effect_handlers import (
    create_obstacle_on_condition,
    move_position_on_condition,
)


class PlaceholderPositionGuardTests(TestCase):
    """The position adapters no-op (do not raise) when the seeded id is the placeholder."""

    def test_move_position_on_condition_placeholder_is_noop(self) -> None:
        # payload.target is never touched on the placeholder path — a bare stub suffices.
        move_position_on_condition(payload=SimpleNamespace(target=None), destination_position_id=0)
        # No exception == pass; nothing to assert beyond not crashing.

    def test_create_obstacle_on_condition_placeholder_is_noop(self) -> None:
        before = PositionEdge.objects.count()
        create_obstacle_on_condition(
            payload=SimpleNamespace(target=None), position_a_id=0, position_b_id=0
        )
        # No edge sealed when the positions are unresolved placeholders.
        self.assertEqual(PositionEdge.objects.count(), before)

"""Direct model-level tests for the sequence auto-assign 0/sentinel fix (#2470).

A whole-branch re-review of commit ``74cf779c2`` found that the
``test_mission_graph_round_trips`` extension in
``core_management/tests/test_content_export.py`` cannot detect this bug class in
either the old or new formula: the reward/award rows there are created via the
factories/``.objects.create()`` BEFORE ``export_to_content_repo`` runs and are
never deleted before the reimport, so ``load_entries``'s
``update_or_create(**lookup, defaults=fields)`` always finds an existing row
(the exported fixture's ``sequence`` matches what's already in the DB) and
takes the UPDATE branch — ``save()``'s ``if self.pk is None:`` guard (the only
code the fix touches) is a no-op on updates and is never exercised.

These tests instead call ``save()`` directly (via the factory / ``.create()``)
in the exact adversarial order the bug was about: a sibling row with an
EXPLICIT nonzero ``sequence`` is created first, then a second row is left at
the field's ``0`` sentinel default to trigger auto-assignment — proving the
result neither collides with the sibling nor is itself the literal ``0``
sentinel. The reverse order (auto-assign on an empty parent, then an explicit
sibling) is also covered to prove the base case yields ``1`` (not ``0``) and
that ordering doesn't matter for correctness.
"""

from __future__ import annotations

from django.test import TestCase

from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionOptionRoute, MissionOptionRouteReward, MissionRenownAward
from world.societies.constants import RenownMagnitude, RenownRisk


def _make_route(label: str) -> MissionOptionRoute:
    """A fresh terminal BRANCH route under its own template/node/option.

    Each call builds an entirely new template/node/option chain so tests
    never share a parent route (and thus never share ``sequence`` state).
    """
    template = MissionTemplateFactory(name=f"Sequence Auto-Assign {label}")
    node = MissionNodeFactory(template=template, key="entry", is_entry=True)
    option = MissionOptionFactory(node=node, key="entry-option")
    return MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)


class MissionOptionRouteRewardSequenceAutoAssignTests(TestCase):
    """Adversarial-order coverage for MissionOptionRouteReward.save()."""

    def test_explicit_then_auto_assigns_next_sequence_not_zero(self) -> None:
        """A sentinel-default row created AFTER an explicit sibling must not collide with it."""
        route = _make_route("Explicit-Then-Auto Reward")
        first = MissionOptionRouteRewardFactory(route=route, sequence=5)
        second = MissionOptionRouteRewardFactory(route=route)  # left at the 0 default

        first.refresh_from_db()
        second.refresh_from_db()

        assert first.sequence == 5
        assert second.sequence == 6
        assert second.sequence != 0

    def test_auto_then_explicit_first_row_gets_one_not_zero(self) -> None:
        """Auto-assign on an empty parent must yield 1 (the pre-fix formula stored 0)."""
        route = _make_route("Auto-Then-Explicit Reward")
        first = MissionOptionRouteRewardFactory(route=route)  # empty parent, left at 0
        first.refresh_from_db()
        assert first.sequence == 1

        second = MissionOptionRouteRewardFactory(route=route, sequence=5)
        second.refresh_from_db()

        assert second.sequence == 5
        assert first.sequence != second.sequence
        assert MissionOptionRouteReward.objects.filter(route=route).count() == 2


class MissionRenownAwardSequenceAutoAssignTests(TestCase):
    """Adversarial-order coverage for MissionRenownAward.save() (parallels the reward tests)."""

    def test_explicit_then_auto_assigns_next_sequence_not_zero(self) -> None:
        route = _make_route("Explicit-Then-Auto Renown")
        first = MissionRenownAward.objects.create(
            route=route, sequence=5, magnitude=RenownMagnitude.MODERATE, risk=RenownRisk.NONE
        )
        second = MissionRenownAward.objects.create(
            route=route, magnitude=RenownMagnitude.HIGH, risk=RenownRisk.LOW
        )  # left at the 0 default

        first.refresh_from_db()
        second.refresh_from_db()

        assert first.sequence == 5
        assert second.sequence == 6
        assert second.sequence != 0

    def test_auto_then_explicit_first_row_gets_one_not_zero(self) -> None:
        route = _make_route("Auto-Then-Explicit Renown")
        first = MissionRenownAward.objects.create(
            route=route, magnitude=RenownMagnitude.MODERATE, risk=RenownRisk.NONE
        )  # empty parent, left at 0
        first.refresh_from_db()
        assert first.sequence == 1

        second = MissionRenownAward.objects.create(
            route=route, sequence=5, magnitude=RenownMagnitude.HIGH, risk=RenownRisk.LOW
        )
        second.refresh_from_db()

        assert second.sequence == 5
        assert first.sequence != second.sequence
        assert MissionRenownAward.objects.filter(route=route).count() == 2

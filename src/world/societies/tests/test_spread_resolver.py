"""spread_a_tale resolver (#745 — Spread a Tale Phase 1a, Task 6).

Uses a mocked check result so the resolver logic is tested independently of
perform_check's roll randomness.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import PersonaFactory, SceneFactory
from world.societies.factories import LegendEntryFactory
from world.societies.models import LegendSpread
from world.societies.spread_services import _resolve_spread_tale


def _request_with(deed, spreader):
    return SceneActionRequest.objects.create(
        scene=SceneFactory(),
        initiator_persona=spreader,
        target_persona=None,
        action_key="spread_a_tale",
        spread_deed_target=deed,
        pose_text="She sang of the deed.",
    )


def _result_with(success_level):
    result = MagicMock()
    result.action_resolution.main_result.check_result.success_level = success_level
    return result


class SpreadTaleResolverTest(TestCase):
    def test_success_adds_legend_value(self) -> None:
        subject = PersonaFactory()
        deed = LegendEntryFactory(persona=subject, base_value=100)
        req = _request_with(deed, PersonaFactory())
        _resolve_spread_tale(req, _result_with(1))
        spread = LegendSpread.objects.filter(legend_entry=deed).first()
        self.assertIsNotNone(spread)
        # base 100 × tier_payoff(1)=0.10 × Busy(1.0) = 10
        self.assertEqual(spread.value_added, 10)

    def test_failure_adds_nothing(self) -> None:
        subject = PersonaFactory()
        deed = LegendEntryFactory(persona=subject, base_value=100)
        req = _request_with(deed, PersonaFactory())
        _resolve_spread_tale(req, _result_with(-1))
        self.assertFalse(LegendSpread.objects.filter(legend_entry=deed).exists())

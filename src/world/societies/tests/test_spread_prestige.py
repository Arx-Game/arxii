"""Prestige spreads like fame (#2168): the slow, permanent counterpart.

`apply_spread_prestige_bump` mirrors `apply_spread_fame_bump` but writes
permanent `prestige_from_deeds` at a smaller magnitude. `_resolve_spread_tale`
awards it alongside fame on a successful retelling, traffic-scaled — so a social
hub (#1694) amplifies prestige automatically via its traffic boost.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import PersonaFactory, SceneFactory
from world.societies.factories import LegendEntryFactory
from world.societies.renown import apply_spread_prestige_bump
from world.societies.spread_services import _resolve_spread_tale


class ApplySpreadPrestigeBumpTest(TestCase):
    def test_awards_permanent_prestige_to_the_subject(self) -> None:
        subject = PersonaFactory()
        before = subject.prestige_from_deeds
        deed = LegendEntryFactory(persona=subject, base_value=100)
        awarded = apply_spread_prestige_bump(deed, npc_audience=3, success_level=2)
        self.assertTrue(awarded)
        subject.refresh_from_db()
        self.assertEqual(subject.prestige_from_deeds, before + 3 * 2)

    def test_zero_audience_is_a_noop(self) -> None:
        subject = PersonaFactory()
        before = subject.prestige_from_deeds
        deed = LegendEntryFactory(persona=subject, base_value=100)
        self.assertFalse(apply_spread_prestige_bump(deed, npc_audience=0, success_level=3))
        subject.refresh_from_db()
        self.assertEqual(subject.prestige_from_deeds, before)


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


class SpreadTalePrestigeTest(TestCase):
    def test_success_grows_permanent_prestige(self) -> None:
        subject = PersonaFactory()
        before = subject.prestige_from_deeds
        deed = LegendEntryFactory(persona=subject, base_value=100)
        _resolve_spread_tale(_request_with(deed, PersonaFactory()), _result_with(1))
        subject.refresh_from_db()
        # npc_audience = int(Busy 1.0 × _PRESTIGE_AUDIENCE_PER_MULTIPLIER=3) × sl 1 = 3
        self.assertEqual(subject.prestige_from_deeds, before + 3)

    def test_failure_grows_nothing(self) -> None:
        subject = PersonaFactory()
        before = subject.prestige_from_deeds
        deed = LegendEntryFactory(persona=subject, base_value=100)
        _resolve_spread_tale(_request_with(deed, PersonaFactory()), _result_with(-1))
        subject.refresh_from_db()
        self.assertEqual(subject.prestige_from_deeds, before)

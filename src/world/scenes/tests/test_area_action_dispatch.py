"""Area-action dispatch + cost (#745 — Spread a Tale Phase 1a, Task 7).

Asserts the check-independent behaviour of the immediate-resolve area path:
AP charged, social fatigue applied, request resolved with no target, pose echoed.
The check-outcome -> legend math is covered deterministically in
world.societies.tests.test_spread_resolver.
"""

from django.test import TestCase

from actions.constants import ActionTargetType
from actions.factories import ActionTemplateFactory
from world.action_points.models import ActionPointPool
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_services import create_and_resolve_area_action
from world.scenes.factories import PersonaFactory, SceneFactory
from world.societies.factories import LegendEntryFactory
from world.societies.spread_services import SPREAD_TALE_TEMPLATE_NAME


class AreaActionDispatchTest(TestCase):
    def test_area_action_resolves_and_charges_cost(self) -> None:
        spreader = PersonaFactory()
        scene = SceneFactory()
        template = ActionTemplateFactory(
            name=SPREAD_TALE_TEMPLATE_NAME,
            target_type=ActionTargetType.AREA,
            category="social",
            ap_cost=20,
            social_fatigue_cost=3,
            accepts_pose_text=True,
        )
        deed = LegendEntryFactory(persona=PersonaFactory())
        character = spreader.character_sheet.character
        ActionPointPool.get_or_create_for_character(character)

        create_and_resolve_area_action(
            scene=scene,
            initiator_persona=spreader,
            action_template=template,
            action_key="spread_a_tale",
            pose_text="She sang of the deed.",
            effort_level="medium",
            spread_deed_target=deed,
        )

        pool = ActionPointPool.get_or_create_for_character(character)
        self.assertEqual(pool.current, pool.maximum - 20)
        self.assertGreater(spreader.character_sheet.fatigue.social_current, 0)

        req = SceneActionRequest.objects.get(action_key="spread_a_tale")
        self.assertEqual(req.status, ActionRequestStatus.RESOLVED)
        self.assertIsNone(req.target_persona)
        self.assertIsNotNone(req.result_interaction)
        self.assertIn("She sang of the deed.", req.result_interaction.content)

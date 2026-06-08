"""SceneActionRequest area fields (#745 — Spread a Tale Phase 1a, Task 2)."""

from django.test import TestCase

from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import PersonaFactory, SceneFactory
from world.societies.factories import LegendEntryFactory


class AreaActionModelTest(TestCase):
    def test_area_request_allows_null_target(self) -> None:
        scene = SceneFactory()
        initiator = PersonaFactory()
        deed = LegendEntryFactory(persona=initiator)
        req = SceneActionRequest.objects.create(
            scene=scene,
            initiator_persona=initiator,
            target_persona=None,
            action_key="spread_a_tale",
            pose_text="She sang of the duel.",
            effort_level="medium",
            spread_deed_target=deed,
        )
        self.assertIsNone(req.target_persona)
        self.assertEqual(req.spread_deed_target_id, deed.pk)
        self.assertEqual(req.pose_text, "She sang of the duel.")
        self.assertIn("room", str(req))

"""Tests for scene-scoped condition expiry on scene finish (#2514)."""

from evennia.utils.test_resources import EvenniaTestCase


class ExpireSceneScopedConditionsTests(EvenniaTestCase):
    def test_removes_scene_duration_conditions(self):
        """A SCENE-duration condition on a target is removed by the sweep."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.conditions.services import expire_scene_scoped_conditions
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        scene_tmpl = ConditionTemplateFactory(
            name="Irritated", default_duration_type=DurationType.SCENE
        )
        scene_inst = ConditionInstanceFactory(
            target=target, condition=scene_tmpl, rounds_remaining=None
        )

        removed = expire_scene_scoped_conditions([target])

        self.assertEqual(removed, [scene_tmpl])
        self.assertFalse(ConditionInstance.objects.filter(pk=scene_inst.pk).exists())

    def test_leaves_other_duration_types(self):
        """ROUNDS and UNTIL_CURED conditions survive the scene sweep."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.conditions.services import expire_scene_scoped_conditions
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        target = persona.character_sheet.character
        rounds_tmpl = ConditionTemplateFactory(
            name="Bleeding", default_duration_type=DurationType.ROUNDS
        )
        cured_tmpl = ConditionTemplateFactory(
            name="Poisoned", default_duration_type=DurationType.UNTIL_CURED
        )
        rounds_inst = ConditionInstanceFactory(
            target=target, condition=rounds_tmpl, rounds_remaining=3
        )
        cured_inst = ConditionInstanceFactory(
            target=target, condition=cured_tmpl, rounds_remaining=None
        )

        removed = expire_scene_scoped_conditions([target])

        self.assertEqual(removed, [])
        self.assertTrue(ConditionInstance.objects.filter(pk=rounds_inst.pk).exists())
        self.assertTrue(ConditionInstance.objects.filter(pk=cured_inst.pk).exists())

    def test_idempotent_noop_on_empty_or_none(self):
        """Empty list, None entries, and targets without SCENE conditions are no-ops."""
        from world.conditions.services import expire_scene_scoped_conditions

        self.assertEqual(expire_scene_scoped_conditions([]), [])
        self.assertEqual(expire_scene_scoped_conditions([None]), [])

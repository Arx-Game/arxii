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


def _create_pc_with_sheet(db_key: str):
    """Create a PC character with a live roster tenure.

    Mirrors ``test_scene_admin_services._create_pc_with_sheet``. Returns
    (character, account, character_sheet).
    """
    from evennia_extensions.factories import CharacterFactory
    from world.character_sheets.factories import CharacterSheetFactory
    from world.roster.factories import RosterEntryFactory, RosterTenureFactory

    char = CharacterFactory(db_key=db_key)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    return char, account, sheet


class FinishSceneExpiresSceneConditionsTests(EvenniaTestCase):
    def test_finish_scene_full_clears_scene_conditions(self):
        """E2E: a SCENE-duration condition on a participant is cleared when
        finish_scene_full runs, while a ROUNDS condition on another
        participant survives."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.scenes.factories import SceneFactory
        from world.scenes.models import SceneParticipation
        from world.scenes.scene_admin_services import finish_scene_full

        scene = SceneFactory()
        char_a, account_a, _sheet_a = _create_pc_with_sheet("Alice")
        char_b, account_b, _sheet_b = _create_pc_with_sheet("Bob")
        SceneParticipation.objects.create(scene=scene, account=account_a)
        SceneParticipation.objects.create(scene=scene, account=account_b)

        scene_tmpl = ConditionTemplateFactory(
            name="Flustered", default_duration_type=DurationType.SCENE
        )
        rounds_tmpl = ConditionTemplateFactory(
            name="Bleeding", default_duration_type=DurationType.ROUNDS
        )
        scene_inst = ConditionInstanceFactory(
            target=char_a, condition=scene_tmpl, rounds_remaining=None
        )
        rounds_inst = ConditionInstanceFactory(
            target=char_b, condition=rounds_tmpl, rounds_remaining=3
        )

        finish_scene_full(scene)

        self.assertFalse(ConditionInstance.objects.filter(pk=scene_inst.pk).exists())
        self.assertTrue(ConditionInstance.objects.filter(pk=rounds_inst.pk).exists())

    def test_finish_scene_full_idempotent_no_double_sweep(self):
        """Calling finish_scene_full twice does not error; the second call is
        a no-op (guarded by the is_finished check at the top)."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.scenes.factories import SceneFactory
        from world.scenes.models import SceneParticipation
        from world.scenes.scene_admin_services import finish_scene_full

        scene = SceneFactory()
        char, account, _sheet = _create_pc_with_sheet("Carol")
        SceneParticipation.objects.create(scene=scene, account=account)
        tmpl = ConditionTemplateFactory(name="Irritated", default_duration_type=DurationType.SCENE)
        ConditionInstanceFactory(target=char, condition=tmpl, rounds_remaining=None)

        finish_scene_full(scene)
        finish_scene_full(scene)  # should not raise

        self.assertFalse(ConditionInstance.objects.filter(condition=tmpl).exists())

    def test_finish_scene_full_no_participants_is_safe(self):
        """A scene with no participants does not crash; the sweep is a no-op."""
        from world.conditions.constants import DurationType
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import ConditionInstance
        from world.scenes.factories import SceneFactory
        from world.scenes.scene_admin_services import finish_scene_full

        scene = SceneFactory()
        # No SceneParticipation rows created — active_participant_personas() returns []
        tmpl = ConditionTemplateFactory(
            name="Lonely Mood", default_duration_type=DurationType.SCENE
        )
        # A condition on a character who is NOT a participant should survive
        char, _account, _sheet = _create_pc_with_sheet("Dan")
        inst = ConditionInstanceFactory(target=char, condition=tmpl, rounds_remaining=None)

        finish_scene_full(scene)

        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())

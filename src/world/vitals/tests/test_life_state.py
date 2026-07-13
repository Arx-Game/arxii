"""Tests for CharacterVitals life_state field and is_dead/is_alive services."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.types import LifecycleState
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import _mark_dead, is_alive, is_dead


class LifeStateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.alive_vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)

    def test_defaults_alive(self) -> None:
        v = self.alive_vitals
        self.assertEqual(v.life_state, CharacterLifeState.ALIVE)
        self.assertTrue(is_alive(v.character_sheet.character.sheet_data))
        self.assertFalse(is_dead(v.character_sheet.character.sheet_data))

    def test_dead(self) -> None:
        v = CharacterVitalsFactory(life_state=CharacterLifeState.DEAD)
        self.assertTrue(is_dead(v.character_sheet.character.sheet_data))
        self.assertFalse(is_alive(v.character_sheet.character.sheet_data))

    def test_no_vitals_is_alive(self) -> None:
        """Character with no CharacterSheet at all is considered alive by default.

        The post-OBJECTDB_PARAM refactor takes CharacterSheet | None; passing
        None covers the "ObjectDB has no sheet" path (NPCs without vitals
        tracking, fresh test fixtures, etc.).
        """
        CharacterFactory(db_key="no_vitals_life_state")
        self.assertTrue(is_alive(None))
        self.assertFalse(is_dead(None))

    def test_mark_dead_propagates_to_roster_lifecycle(self) -> None:
        """#1770 PR2: the single death writer also stamps CharacterSheet.lifecycle_state.

        Combat death (debited health -> process_damage_consequences -> terminal
        peril -> _mark_dead) must reach the roster lifecycle, so downstream
        systems (dormancy, stake grading) see the death without reading vitals.
        """
        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)
        sheet = vitals.character_sheet
        self.assertEqual(sheet.lifecycle_state, LifecycleState.ALIVE)

        _mark_dead(sheet)

        self.assertEqual(vitals.life_state, CharacterLifeState.DEAD)
        self.assertIsNotNone(vitals.died_at)
        sheet.refresh_from_db()
        self.assertEqual(sheet.lifecycle_state, LifecycleState.DEAD)
        self.assertIsNotNone(sheet.lifecycle_state_at)

    def test_mark_dead_without_vitals_is_noop(self) -> None:
        """No vitals row: _mark_dead returns early and never touches lifecycle."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        _mark_dead(sheet)
        sheet.refresh_from_db()
        self.assertEqual(sheet.lifecycle_state, LifecycleState.ALIVE)


class DeathMomentTests(TestCase):
    """#2287: _mark_dead stamps the death scene and delivers the condolence."""

    def test_mark_dead_stamps_active_scene_at_body(self) -> None:
        from evennia.utils import create as evennia_create

        from world.scenes.factories import SceneFactory
        from world.scenes.interaction_services import invalidate_active_scene_cache

        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)
        sheet = vitals.character_sheet
        room = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Death Room", nohome=True
        )
        sheet.character.location = room
        scene = SceneFactory(location=room)
        invalidate_active_scene_cache(room)

        _mark_dead(sheet)

        vitals.refresh_from_db()
        self.assertEqual(vitals.died_in_scene_id, scene.pk)

    def test_mark_dead_offscreen_leaves_scene_null(self) -> None:
        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)
        _mark_dead(vitals.character_sheet)
        vitals.refresh_from_db()
        self.assertIsNone(vitals.died_in_scene)

    def test_condolence_text_delivered_to_character(self) -> None:
        from unittest.mock import patch

        from world.vitals.models import VitalsConsequenceConfig

        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
        config.death_condolence_body = "PLACEHOLDER condolence."
        config.save(update_fields=["death_condolence_body"])

        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)
        sheet = vitals.character_sheet
        with patch.object(type(sheet.character), "msg") as mock_msg:
            _mark_dead(sheet)
        delivered = [call.args[0] for call in mock_msg.call_args_list if call.args]
        self.assertIn("PLACEHOLDER condolence.", delivered)

    def test_empty_condolence_sends_nothing(self) -> None:
        from unittest.mock import patch

        from world.vitals.models import VitalsConsequenceConfig

        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
        config.death_condolence_body = ""
        config.save(update_fields=["death_condolence_body"])

        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.ALIVE)
        sheet = vitals.character_sheet
        with patch.object(type(sheet.character), "msg") as mock_msg:
            _mark_dead(sheet)
        self.assertEqual(mock_msg.call_count, 0)

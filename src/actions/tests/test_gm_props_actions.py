"""Tests for the GM stage-prop improv actions (#2503).

Mirrors ``test_gm_combat_actions.py``'s fixture shape: a GM (staff) actor, a
non-GM player actor, and a ``Scene`` in the shared room with the GM enrolled as
``is_gm``. Covers the ``action.run()`` seam directly per the task brief.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.gm_props import StagePropAction, StagePropertyAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemTemplateFactory, ItemTemplatePropertyFactory
from world.items.models import ItemInstance
from world.mechanics.factories import PropertyFactory
from world.mechanics.models import ObjectProperty
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    RosterTenureFactory(roster_entry=entry, player_data__account=account, end_date=None)
    return char, entry.character_sheet


class GMStagePropTestBase(TestCase):
    """Shared fixture: room, staff-GM actor, non-GM player actor, active scene."""

    def setUp(self) -> None:
        self.room = _make_room("StagePropRoom")

        self.gm_account = AccountFactory(username="stageroom_gm", is_staff=True)
        self.gm_actor, self.gm_sheet = _make_actor_with_account(
            "stage_gm_actor", self.room, self.gm_account
        )

        self.player_account = AccountFactory(username="stageroom_player")
        self.player_actor, self.player_sheet = _make_actor_with_account(
            "stage_player_actor", self.room, self.player_account
        )

        self.scene = SceneFactory(location=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        self.template = ItemTemplateFactory(name="Improv Torch")
        self.prop_flammable = PropertyFactory(name="flammable")
        ItemTemplatePropertyFactory(
            item_template=self.template, property=self.prop_flammable, value=1
        )


class StagePropActionTests(GMStagePropTestBase):
    def test_gm_stages_prop_with_default_properties(self) -> None:
        result = StagePropAction().run(actor=self.gm_actor, item_template="Improv Torch")
        self.assertTrue(result.success, result.message)

        object_id = result.data["object_id"]
        from evennia.objects.models import ObjectDB

        game_object = ObjectDB.objects.get(pk=object_id)
        self.assertEqual(game_object.location, self.room)

        instance = ItemInstance.objects.get(game_object=game_object)
        self.assertEqual(instance.template, self.template)
        self.assertEqual(instance.holder_character_sheet, None)

        obj_prop = ObjectProperty.objects.get(object=game_object, property=self.prop_flammable)
        self.assertEqual(obj_prop.value, 1)

    def test_non_gm_rejected(self) -> None:
        result = StagePropAction().run(actor=self.player_actor, item_template="Improv Torch")
        self.assertFalse(result.success)
        self.assertFalse(ItemInstance.objects.filter(template=self.template).exists())

    def test_invalid_template_name_clean_error(self) -> None:
        result = StagePropAction().run(actor=self.gm_actor, item_template="Nonexistent Widget")
        self.assertFalse(result.success)
        self.assertIn("Nonexistent Widget", result.message)
        self.assertFalse(ItemInstance.objects.filter(template__name="Nonexistent Widget").exists())

    def test_missing_template_kwarg_clean_error(self) -> None:
        result = StagePropAction().run(actor=self.gm_actor)
        self.assertFalse(result.success)
        self.assertIn("template", result.message.lower())

    def test_staff_without_gm_participation_still_allowed(self) -> None:
        """Staff bypasses the scene-GM check entirely (mirrors _actor_may_gm_encounter)."""
        other_room = _make_room("OtherStageRoom")
        self.gm_actor.location = other_room
        self.gm_actor.save()
        result = StagePropAction().run(actor=self.gm_actor, item_template="Improv Torch")
        self.assertTrue(result.success, result.message)

    def test_non_staff_scene_gm_allowed(self) -> None:
        """A non-staff scene GM (SceneParticipation.is_gm) may also stage a prop."""
        table_gm_account = AccountFactory(username="stageroom_table_gm")
        table_gm_actor, _ = _make_actor_with_account(
            "stage_table_gm_actor", self.room, table_gm_account
        )
        SceneParticipationFactory(scene=self.scene, account=table_gm_account, is_gm=True)

        result = StagePropAction().run(actor=table_gm_actor, item_template="Improv Torch")
        self.assertTrue(result.success, result.message)


class StagePropertyActionTests(GMStagePropTestBase):
    def test_gm_stages_property_on_room(self) -> None:
        prop_dark = PropertyFactory(name="dark")
        result = StagePropertyAction().run(actor=self.gm_actor, property="dark")
        self.assertTrue(result.success, result.message)
        obj_prop = ObjectProperty.objects.get(object=self.room, property=prop_dark)
        self.assertEqual(obj_prop.value, 1)

    def test_gm_stages_property_on_target(self) -> None:
        target = ObjectDBFactory(db_key="A Table", location=self.room)
        prop_sturdy = PropertyFactory(name="sturdy")
        result = StagePropertyAction().run(actor=self.gm_actor, property="sturdy", target=target)
        self.assertTrue(result.success, result.message)
        ObjectProperty.objects.get(object=target, property=prop_sturdy)

    def test_non_gm_rejected(self) -> None:
        PropertyFactory(name="dark")
        result = StagePropertyAction().run(actor=self.player_actor, property="dark")
        self.assertFalse(result.success)

    def test_invalid_property_name_clean_error(self) -> None:
        result = StagePropertyAction().run(actor=self.gm_actor, property="not_a_real_property")
        self.assertFalse(result.success)
        self.assertIn("not_a_real_property", result.message)

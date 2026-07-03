from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import ConditionCategoryFactory, ConditionTemplateFactory
from world.conditions.services import (
    apply_condition,
    bulk_apply_conditions,
    remove_condition,
    suppress_condition,
)
from world.conditions.types import BulkConditionApplication
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import SceneFactory
from world.scenes.services import has_unseen_observers


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class ConcealmentOOCWiringTests(TestCase):
    def setUp(self) -> None:
        roster = RosterEntryFactory()
        self.sheet = roster.character_sheet
        self.character = self.sheet.character
        # CharacterFactory creates with nohome=True (location=None); a real room is
        # required for get_active_scene to resolve anything (mirrors test_can_perceive.py).
        self.character.location = _create_room()
        self.scene = SceneFactory(location=self.character.location, is_active=True)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        self.template = ConditionTemplateFactory(category=cat)

    def test_apply_registers_unseen_observer(self) -> None:
        apply_condition(target=self.character, condition=self.template)
        self.assertTrue(has_unseen_observers(self.scene))

    def test_remove_clears_unseen_observer(self) -> None:
        apply_condition(target=self.character, condition=self.template)
        remove_condition(self.character, self.template)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_suppress_clears_unseen_observer(self) -> None:
        apply_condition(target=self.character, condition=self.template)
        suppress_condition(self.character, self.template)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_non_concealing_condition_does_not_register(self) -> None:
        plain_template = ConditionTemplateFactory()
        apply_condition(target=self.character, condition=plain_template)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_remove_one_of_two_concealments_keeps_banner_up(self) -> None:
        """Two independently-applied concealing conditions on the same target;
        removing one must not drop the OOC banner while the other remains active
        (#1225 review fix)."""
        other_cat = ConditionCategoryFactory(conceals_from_perception=True)
        other_template = ConditionTemplateFactory(category=other_cat)

        apply_condition(target=self.character, condition=self.template)
        apply_condition(target=self.character, condition=other_template)
        self.assertTrue(has_unseen_observers(self.scene))

        remove_condition(self.character, self.template)

        self.assertTrue(has_unseen_observers(self.scene))

    def test_bulk_apply_registers_unseen_observer(self) -> None:
        """bulk_apply_conditions (the magic/combat/covenant apply path, #1225 review
        gap) must trigger the same OOC hook as the single-condition apply_condition
        path."""
        bulk_apply_conditions(
            [BulkConditionApplication(target=self.character, template=self.template)]
        )
        self.assertTrue(has_unseen_observers(self.scene))

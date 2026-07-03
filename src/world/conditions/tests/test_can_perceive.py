from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import can_perceive, is_concealed, register_detection
from world.roster.factories import RosterEntryFactory


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class IsConcealedTests(TestCase):
    def test_false_without_concealment(self):
        inst = ConditionInstanceFactory()
        self.assertFalse(is_concealed(inst.target))

    def test_true_with_active_concealment(self):
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        inst = ConditionInstanceFactory(condition=tmpl)
        self.assertTrue(is_concealed(inst.target))

    def test_false_when_suppressed(self):
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        inst = ConditionInstanceFactory(condition=tmpl, is_suppressed=True)
        self.assertFalse(is_concealed(inst.target))


class CanPerceiveTests(TestCase):
    def setUp(self) -> None:
        self.actor_sheet = RosterEntryFactory().character_sheet
        self.actor = self.actor_sheet.character
        self.actor.location = _create_room()
        self.target_roster = RosterEntryFactory()
        self.target = self.target_roster.character_sheet.character

    def test_true_when_colocated_and_unconcealed(self):
        self.target.move_to(self.actor.location, quiet=True)
        self.assertTrue(can_perceive(self.actor, self.target))

    def test_false_when_not_colocated(self):
        self.assertFalse(can_perceive(self.actor, self.target))

    def test_false_when_concealed_and_undetected(self):
        self.target.move_to(self.actor.location, quiet=True)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=self.target, condition=tmpl)
        self.assertFalse(can_perceive(self.actor, self.target))

    def test_true_when_concealed_but_detected_by_this_actor(self):
        self.target.move_to(self.actor.location, quiet=True)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=self.target, condition=tmpl)
        register_detection(self.actor_sheet, self.target)
        self.assertTrue(can_perceive(self.actor, self.target))

    def test_false_for_a_different_undetecting_actor(self):
        self.target.move_to(self.actor.location, quiet=True)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=self.target, condition=tmpl)
        other_sheet = RosterEntryFactory().character_sheet
        register_detection(other_sheet, self.target)
        self.assertFalse(can_perceive(self.actor, self.target))

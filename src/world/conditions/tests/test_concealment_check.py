"""Concealment predicates do not grant spatial scope or record detection."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import can_perceive, passes_concealment_check
from world.roster.factories import RosterEntryFactory


class ConcealmentCheckTests(TestCase):
    def setUp(self):
        self.room = RoomProfileFactory().objectdb
        self.remote = RoomProfileFactory().objectdb
        self.sheet = RosterEntryFactory().character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.other_sheet = RosterEntryFactory().character_sheet
        self.wearer = self.other_sheet.character
        self.wearer.location = self.room
        self.target = ObjectDBFactory(location=self.wearer)

    def _condition(self, **changes):
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        return ConditionInstanceFactory(target=self.target, condition=template, **changes)

    def test_predicate_does_not_grant_direct_spatial_scope(self):
        assert passes_concealment_check(self.actor, self.target)
        assert not can_perceive(self.actor, self.target)
        for location in (self.actor, self.room):
            self.target.location = location
            assert can_perceive(self.actor, self.target)
        self.target.location = self.remote
        assert passes_concealment_check(self.actor, self.target)
        assert not can_perceive(self.actor, self.target)

    def test_every_active_instance_requires_this_observers_detection(self):
        first = self._condition()
        second = self._condition()
        first.detected_by.add(self.sheet)
        second.detected_by.add(self.other_sheet)
        assert not passes_concealment_check(self.actor, self.target)
        second.detected_by.add(self.sheet)
        assert passes_concealment_check(self.actor, self.target)
        first.detected_by.remove(self.sheet)
        assert not passes_concealment_check(self.actor, self.target)
        first.detected_by.add(self.sheet)
        assert passes_concealment_check(self.actor, self.target)
        self._condition()
        assert not passes_concealment_check(self.actor, self.target)

    def test_suppressed_resolved_and_nonconcealing_instances_do_not_block(self):
        self._condition(is_suppressed=True)
        self._condition(resolved_at=timezone.now())
        category = ConditionCategoryFactory(conceals_from_perception=False)
        template = ConditionTemplateFactory(category=category)
        ConditionInstanceFactory(target=self.target, condition=template)
        assert passes_concealment_check(self.actor, self.target)
        active = self._condition()
        assert not passes_concealment_check(self.actor, self.target)
        active.is_suppressed = True
        active.save(update_fields=["is_suppressed"])
        assert passes_concealment_check(self.actor, self.target)
        active.is_suppressed = False
        active.resolved_at = timezone.now()
        active.save(update_fields=["is_suppressed", "resolved_at"])
        assert passes_concealment_check(self.actor, self.target)

    def test_sheetless_observer_is_allowed_only_without_active_concealment(self):
        observer = ObjectDBFactory(location=self.room)
        assert observer.character_sheet is None
        assert passes_concealment_check(observer, self.target)
        self._condition()
        assert not passes_concealment_check(observer, self.target)

    def test_reads_do_not_register_detection_or_change_conditions(self):
        instance = self._condition()
        detected_before = list(instance.detected_by.all())
        state_before = (instance.is_suppressed, instance.resolved_at)
        for _ in range(2):
            assert not passes_concealment_check(self.actor, self.target)
        assert list(instance.detected_by.all()) == detected_before
        assert (instance.is_suppressed, instance.resolved_at) == state_before

    def test_direct_perception_delegates_only_after_original_location_gate(self):
        with patch("world.conditions.services.passes_concealment_check") as check:
            assert not can_perceive(self.actor, self.target)
            check.assert_not_called()
            self.target.location = self.room
            check.return_value = False
            assert not can_perceive(self.actor, self.target)
            check.assert_called_once_with(self.actor, self.target)
            check.reset_mock()
            check.return_value = True
            assert can_perceive(self.actor, self.target)
            check.assert_called_once_with(self.actor, self.target)

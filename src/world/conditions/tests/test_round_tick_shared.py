"""Tests for the shared tick_round_for_targets orchestrator (Task 4 / #520)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.vitals.services import tick_round_for_targets


class TickRoundForTargetsTests(TestCase):
    def test_end_timing_decrements_condition_rounds(self):
        target = ObjectDBFactory(db_key="T1")
        CharacterSheetFactory(character=target)
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(target=target, condition=template, rounds_remaining=3)

        tick_round_for_targets([target], timing="end")

        inst.refresh_from_db()
        assert inst.rounds_remaining == 2

    def test_empty_targets_is_noop(self):
        tick_round_for_targets([], timing="end")

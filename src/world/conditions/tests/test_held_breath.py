"""Held-breath conditions (#4741).

A held-breath condition (a smoke form, being underwater) lasts as many rounds as the
bearer's breath check outcome buys, ends when she takes a breath, ends when a coughing
fit lands, and applies its runs-out condition only when the breath runs out by itself.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.definitions.conditions import take_breath as take_breath_action
from evennia_extensions.factories import RoomProfileFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.events.payloads import TechniqueCastPayload
from flows.models.flows import FlowDefinition, FlowStepDefinition
from flows.models.triggers import TriggerDefinition
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import BreathHoldDurationAward
from world.conditions.services import (
    apply_condition,
    get_active_conditions,
    get_breath_hold_config,
    process_round_end,
    take_breath,
)
from world.magic.types.power_ledger import PowerLedger
from world.traits.factories import CheckOutcomeFactory


def _held_breath_template(**kwargs):
    return ConditionTemplateFactory(
        holds_breath=True,
        default_duration_type=DurationType.ROUNDS,
        default_duration_value=2,
        **kwargs,
    )


def _active_names(character) -> set[str]:
    return {i.condition.name for i in get_active_conditions(character)}


class BreathCheckSetsTheRoundsTests(TestCase):
    def setUp(self):
        self.character = CharacterSheetFactory().character
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        BreathHoldDurationAward.objects.create(outcome_tier=self.success, rounds=5)
        BreathHoldDurationAward.objects.create(outcome_tier=self.failure, rounds=1)
        config = get_breath_hold_config()
        config.check_type = CheckTypeFactory()
        config.target_difficulty = 30
        config.save()
        self.smoke = _held_breath_template(name="Smoke Form")

    def test_the_outcome_tier_picks_the_rounds(self):
        for outcome, expected in ((self.success, 5), (self.failure, 1)):
            with self.subTest(outcome=outcome.name):
                with force_check_outcome(outcome) as capture:
                    result = apply_condition(self.character, self.smoke)
                self.assertEqual(result.instance.rounds_remaining, expected)
                self.assertEqual(capture.target_difficulty, 30)
                take_breath(self.character)

    def test_the_breath_roll_overrides_a_techniques_duration(self):
        with force_check_outcome(self.success):
            result = apply_condition(self.character, self.smoke, duration_rounds=9)
        self.assertEqual(result.instance.rounds_remaining, 5)

    def test_an_ordinary_condition_keeps_its_own_rounds(self):
        ordinary = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=4
        )
        result = apply_condition(self.character, ordinary)
        self.assertEqual(result.instance.rounds_remaining, 4)


class NoBreathCheckConfiguredTests(TestCase):
    def test_the_conditions_own_default_rounds_apply(self):
        character = CharacterSheetFactory().character
        result = apply_condition(character, _held_breath_template())
        self.assertEqual(result.instance.rounds_remaining, 2)


class TakingABreathTests(TestCase):
    def setUp(self):
        self.character = CharacterSheetFactory().character
        self.drowning = ConditionTemplateFactory(name="Drowning")
        self.underwater = _held_breath_template(
            name="Underwater", breath_runs_out_condition=self.drowning
        )
        self.smoke = _held_breath_template(name="Smoke Form")

    def test_breathing_ends_every_held_breath_and_drowns_no_one(self):
        apply_condition(self.character, self.underwater)
        apply_condition(self.character, self.smoke)

        result = take_breath_action.run(self.character)

        self.assertTrue(result.success)
        self.assertIn("Smoke Form", result.message)
        self.assertIn("Underwater", result.message)
        self.assertEqual(_active_names(self.character), set())

    def test_nothing_held_is_refused(self):
        result = take_breath_action.run(self.character)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You aren't holding your breath.")

    def test_running_out_applies_the_runs_out_condition(self):
        apply_condition(self.character, self.underwater)
        process_round_end(self.character)
        self.assertEqual(_active_names(self.character), {"Underwater"})

        process_round_end(self.character)

        self.assertEqual(_active_names(self.character), {"Drowning"})

    def test_a_held_breath_needs_a_rounds_duration(self):
        template = ConditionTemplateFactory(
            holds_breath=True, default_duration_type=DurationType.PERMANENT
        )
        with self.assertRaises(ValidationError):
            template.full_clean()


class CoughingBreaksTheHeldBreathTests(TestCase):
    """A coughing fit, applied by her own lungs after each cast, unless she resists."""

    def setUp(self):
        room = RoomProfileFactory().objectdb
        self.character = CharacterSheetFactory().character
        self.character.db_location = room
        self.character.save(update_fields=["db_location"])
        self.room = room
        self.resisted = CheckOutcomeFactory(name="Success", success_level=1)
        self.not_resisted = CheckOutcomeFactory(name="Failure", success_level=-1)
        self.smoke = _held_breath_template(name="Smoke Form")
        self.coughing = ConditionTemplateFactory(
            name="Coughing",
            breaks_held_breath=True,
            resist_check_type=CheckTypeFactory(),
            resist_difficulty=40,
        )
        flow = FlowDefinition.objects.create(name="cough after casting")
        FlowStepDefinition.objects.create(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="flow_apply_condition",
            parameters={"target": "@payload.caster", "condition_name": "Coughing"},
        )
        trigger = TriggerDefinition.objects.create(
            name="smoke-scarred lungs",
            event_name=EventName.TECHNIQUE_CAST,
            flow_definition=flow,
            base_filter_condition={"path": "caster", "op": "==", "value": "self"},
        )
        lungs = ConditionTemplateFactory(
            name="Smoke-Scarred Lungs", default_duration_type=DurationType.PERMANENT
        )
        lungs.reactive_triggers.add(trigger)
        apply_condition(self.character, lungs)
        apply_condition(self.character, self.smoke)

    def _cast(self):
        emit_event(
            EventName.TECHNIQUE_CAST,
            TechniqueCastPayload(
                caster=self.character,
                technique=None,
                targets=[],
                intensity=0,
                power=0,
                ledger=PowerLedger(entries=(), total=0),
                result=None,
            ),
            location=self.room,
        )

    def test_a_cough_she_fails_to_resist_ends_the_smoke_form(self):
        with force_check_outcome(self.not_resisted):
            self._cast()

        names = _active_names(self.character)
        self.assertIn("Coughing", names)
        self.assertNotIn("Smoke Form", names)

    def test_a_cough_she_resists_leaves_the_smoke_form(self):
        with force_check_outcome(self.resisted) as capture:
            self._cast()

        self.assertEqual(capture.target_difficulty, 40)
        names = _active_names(self.character)
        self.assertNotIn("Coughing", names)
        self.assertIn("Smoke Form", names)

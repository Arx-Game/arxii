"""E2E tests for the involuntary trigger transformation cause-path.

Exercises ``CONDITION_APPLIED`` → ``TriggerDefinition`` → ``FlowDefinition`` →
``CALL_SERVICE_FUNCTION`` → ``flow_trigger_transformation`` wiring, plus the
decoupled revert-blocking invariant while an alters-behavior condition is active.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition, remove_condition
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    FormCombatProfileEffectFactory,
    FormCombatProfileFactory,
)
from world.forms.models import (
    ActiveAlternateSelf,
    CharacterFormState,
    FormType,
)
from world.forms.services import RevertBlockedError, revert_alternate_self
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory

SELF_FILTER = {"path": "target", "op": "==", "value": "self"}


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_check_result(check_type, outcome_name: str) -> CheckResult:
    """Build a deterministic CheckResult with the named outcome."""
    from world.traits.factories import CheckOutcomeFactory

    outcome = CheckOutcomeFactory(name=outcome_name)
    return CheckResult(
        check_type=check_type,
        outcome=outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


class TriggerTransformationFlowTests(TestCase):
    """Trigger→flow→transformation E2E, including resist-check branching."""

    @classmethod
    def setUpTestData(cls):
        cls.room = _create_room()
        cls.rage_category = ConditionCategoryFactory(
            name="Test Behavior Control", alters_behavior=True
        )
        cls.rage_template = ConditionTemplateFactory(
            name="Test Rage",
            category=cls.rage_category,
            has_progression=False,
        )
        cls.resist_check_type = CheckTypeFactory(name="Resist Lycanthropy")

    def _make_subject(self):
        """Create a character with a true form, an alt form/persona/grant, and modifiers."""
        char = CharacterFactory(location=self.room)
        sheet = CharacterSheetFactory(character=char)

        true_form = CharacterFormFactory(character=char, name="True", form_type=FormType.TRUE)
        CharacterFormState.objects.create(character=char, active_form=true_form)

        form_name = f"Beast-{char.db_key}"
        alt_form = CharacterFormFactory(
            character=char, name=form_name, form_type=FormType.ALTERNATE
        )

        target = ModifierTargetFactory(
            name=f"strength-{char.db_key}",
            category=ModifierCategoryFactory(name=f"stats-{char.db_key}"),
        )
        profile = FormCombatProfileFactory(form=alt_form)
        FormCombatProfileEffectFactory(profile=profile, target=target, value=10)

        alt_persona = PersonaFactory(
            character_sheet=sheet,
            persona_type=PersonaType.ALTERNATE,
            name=f"Beast-{char.db_key}",
        )
        alt_self = AlternateSelfFactory(
            character=sheet,
            form=alt_form,
            persona=alt_persona,
            combat_profile=profile,
        )
        return char, sheet, alt_form, alt_self, target

    def _install_transformation_trigger(self, char, form_name: str, instance_value: float = 1.0):
        """Attach a CONDITION_APPLIED trigger that calls trigger_transformation."""
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent=None,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="trigger_transformation",
            parameters={
                "character": "@payload.target",
                "form_name": form_name,
                "instance_value": instance_value,
            },
        )
        trigger_def = TriggerDefinitionFactory(
            event_name=EventName.CONDITION_APPLIED,
            flow_definition=flow,
        )
        TriggerFactory(
            trigger_definition=trigger_def,
            obj=char,
            source_condition=None,
            additional_filter_condition=SELF_FILTER,
        )

    def test_trigger_fires_assumes_alt_self(self):
        """CONDITION_APPLIED triggers the flow and assumes the alt-self with variance."""
        char, sheet, alt_form, alt_self, _target = self._make_subject()
        self._install_transformation_trigger(char, alt_form.name, instance_value=1.5)

        template = ConditionTemplateFactory()
        result = apply_condition(char, template)
        self.assertTrue(result.success)

        active = ActiveAlternateSelf.objects.get(character=sheet)
        self.assertEqual(active.alternate_self, alt_self)

        modifier = CharacterModifier.objects.get(character=sheet)
        # effect.value=10, baseline=1, instance_value=1.5, SCALE=10 => round(1.5)=2
        self.assertEqual(modifier.value, 2)

    def test_revert_blocked_while_rage_active(self):
        """After the trigger forces the shift, revert is blocked while raging."""
        char, sheet, alt_form, alt_self, _target = self._make_subject()
        self._install_transformation_trigger(char, alt_form.name)

        apply_condition(char, ConditionTemplateFactory())
        active = ActiveAlternateSelf.objects.get(character=sheet)
        self.assertEqual(active.alternate_self, alt_self)

        apply_condition(char, self.rage_template)
        self.assertFalse(sheet.in_control)

        with self.assertRaises(RevertBlockedError):
            revert_alternate_self(sheet)

        active = ActiveAlternateSelf.objects.get(character=sheet)
        self.assertEqual(active.alternate_self, alt_self)

    def test_revert_unblocks_after_rage_clears(self):
        """Removing the alters-behavior condition unblocks revert."""
        char, sheet, alt_form, _alt_self, _target = self._make_subject()
        self._install_transformation_trigger(char, alt_form.name)

        apply_condition(char, ConditionTemplateFactory())
        apply_condition(char, self.rage_template)
        self.assertFalse(sheet.in_control)

        self.assertTrue(remove_condition(char, self.rage_template))
        self.assertTrue(sheet.in_control)

        revert_alternate_self(sheet)

        active = ActiveAlternateSelf.objects.get(character=sheet)
        self.assertIsNone(active.alternate_self)

        state = CharacterFormState.objects.get(character=char)
        self.assertEqual(state.active_form.name, "True")

    def test_resist_check_failure_forces_shift(self):
        """Resist Success blocks the shift; resist Failure lets it through.

        The brief assumed ``EVALUATE_EQUALS(variable_name="resist",
        parameters={"value": "Failure"})``. The real engine in
        ``FlowStepDefinition._handle_conditional`` treats the evaluated value as
        the flow variable and compares it to ``parameters["value"]`` with
        ``operator.eq``, so the same parameter shape works unchanged.
        """
        for outcome_name, should_shift in (("Success", False), ("Failure", True)):
            with self.subTest(outcome_name=outcome_name, should_shift=should_shift):
                char, sheet, alt_form, alt_self, _target = self._make_subject()

                flow = FlowDefinitionFactory()
                check_step = FlowStepDefinitionFactory(
                    flow=flow,
                    parent=None,
                    action=FlowActionChoices.CALL_SERVICE_FUNCTION,
                    variable_name=("flows.service_functions.conditions.flow_perform_check"),
                    parameters={
                        "character": "@payload.target",
                        "check_type_name": self.resist_check_type.name,
                        "result_variable": "resist",
                    },
                )
                branch_step = FlowStepDefinitionFactory(
                    flow=flow,
                    parent_id=check_step.pk,
                    action=FlowActionChoices.EVALUATE_EQUALS,
                    variable_name="resist",
                    parameters={"value": "Failure"},
                )
                FlowStepDefinitionFactory(
                    flow=flow,
                    parent_id=branch_step.pk,
                    action=FlowActionChoices.CALL_SERVICE_FUNCTION,
                    variable_name="trigger_transformation",
                    parameters={
                        "character": "@payload.target",
                        "form_name": alt_form.name,
                    },
                )

                trigger_def = TriggerDefinitionFactory(
                    event_name=EventName.CONDITION_APPLIED,
                    flow_definition=flow,
                )
                TriggerFactory(
                    trigger_definition=trigger_def,
                    obj=char,
                    source_condition=None,
                    additional_filter_condition=SELF_FILTER,
                )

                with patch("world.checks.services.perform_check") as mock_check:
                    mock_check.return_value = _make_check_result(
                        self.resist_check_type, outcome_name
                    )
                    apply_condition(char, ConditionTemplateFactory())

                if should_shift:
                    active = ActiveAlternateSelf.objects.get(character=sheet)
                    self.assertEqual(
                        active.alternate_self,
                        alt_self,
                        "Resist Failure should have forced the transformation.",
                    )
                else:
                    active = ActiveAlternateSelf.objects.filter(character=sheet).first()
                    self.assertIsNone(
                        active,
                        "Resist Success should have left the transformation blocked.",
                    )

"""Soulfray is the template ``SoulfrayConfig.condition`` names, not one matched by name (#4122)."""

from __future__ import annotations

from django.test import TestCase, tag

from evennia_extensions.factories import CharacterFactory
from web.admin.tuning import required_content as rc
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    SoulfrayTemplateFactory,
)
from world.conditions.models import ConditionTemplate
from world.magic.factories import SoulfrayConfigFactory
from world.magic.models import SoulfrayConfig
from world.magic.services.soulfray import (
    _handle_soulfray_accumulation,
    get_soulfray_template,
    get_soulfray_warning,
    is_soulfray_stage,
    soulfray_condition_id,
    soulfray_stages,
)


class RenamedSoulfrayTemplateTests(TestCase):
    """Staff renamed the template; every Soulfray read still finds it."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = SoulfrayConfigFactory(resilience_check_type=CheckTypeFactory())
        cls.template = SoulfrayTemplateFactory(name="Veil Strain")
        cls.decoy = ConditionTemplateFactory(name="Soulfray")
        cls.first = ConditionStageFactory(condition=cls.template, stage_order=1, name="Fraying")
        cls.second = ConditionStageFactory(condition=cls.template, stage_order=2, name="Tearing")
        cls.decoy_stage = ConditionStageFactory(condition=cls.decoy, stage_order=1, name="Decoy")

    def test_the_config_names_the_template_whatever_it_is_called(self) -> None:
        self.assertEqual(soulfray_condition_id(), self.template.pk)
        self.assertEqual(get_soulfray_template(), self.template)

    def test_stages_are_the_named_templates_not_a_template_called_soulfray(self) -> None:
        self.assertEqual(list(soulfray_stages()), [self.first, self.second])
        self.assertTrue(is_soulfray_stage(self.second))
        self.assertFalse(is_soulfray_stage(self.decoy_stage))

    def test_the_checkpoint_warning_reads_the_renamed_condition(self) -> None:
        character = CharacterFactory()
        ConditionInstanceFactory(
            target=character, condition=self.template, current_stage=self.second
        )
        warning = get_soulfray_warning(character)
        self.assertIsNotNone(warning)
        self.assertEqual(warning.stage_name, "Tearing")

    @tag("postgres")  # apply_condition uses DISTINCT ON
    def test_accrual_applies_the_renamed_condition(self) -> None:
        character = CharacterFactory()
        result = _handle_soulfray_accumulation(
            character=character,
            soulfray_severity=7,
            soulfray_config=self.config,
            technique_check_result=None,
        )
        self.assertTrue(result.stage_advanced)
        instance = character.condition_instances.get()
        self.assertEqual(instance.condition, self.template)


class UnsetSoulfrayConditionTests(TestCase):
    """With the config's condition unset, nothing is Soulfray and accrual fails loudly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = SoulfrayConfigFactory(resilience_check_type=CheckTypeFactory())
        cls.template = ConditionTemplateFactory(name="Soulfray")
        cls.stage = ConditionStageFactory(condition=cls.template, stage_order=1, name="Fraying")

    def test_a_template_called_soulfray_is_not_soulfray_until_the_config_names_it(self) -> None:
        self.assertIsNone(self.config.condition_id)
        self.assertIsNone(soulfray_condition_id())
        self.assertEqual(list(soulfray_stages()), [])
        self.assertFalse(is_soulfray_stage(self.stage))

    def test_accrual_raises_instead_of_guessing_a_template(self) -> None:
        with self.assertRaises(ConditionTemplate.DoesNotExist):
            _handle_soulfray_accumulation(
                character=CharacterFactory(),
                soulfray_severity=3,
                soulfray_config=self.config,
                technique_check_result=None,
            )

    def test_required_content_flags_the_unset_condition(self) -> None:
        result = rc._probe_soulfray_condition_set()
        self.assertFalse(result.present)
        self.assertIn("Condition field is empty", result.detail)

    def test_required_content_passes_once_the_condition_is_set(self) -> None:
        self.config.condition = self.template
        self.config.save(update_fields=["condition"])
        self.assertTrue(rc._probe_soulfray_condition_set().present)


class NoSoulfrayConfigTests(TestCase):
    def test_required_content_flags_a_missing_config_row(self) -> None:
        self.assertFalse(SoulfrayConfig.objects.exists())
        result = rc._probe_soulfray_condition_set()
        self.assertFalse(result.present)
        self.assertIn("No Soulfray configuration row", result.detail)

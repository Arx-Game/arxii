"""EXTERNAL_ACT MissionOption validation (#1035)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.missions.constants import ExternalAct, OptionKind, OptionSource
from world.missions.factories import MissionNodeFactory, MissionOptionFactory


class ExternalActOptionValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.node = MissionNodeFactory(key="entry", is_entry=True)

    def test_external_act_requires_required_act(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            MissionOptionFactory(
                node=self.node,
                option_kind=OptionKind.EXTERNAL_ACT,
                source_kind=OptionSource.AUTHORED,
            )
        self.assertIn("required_act", ctx.exception.error_dict)

    def test_external_act_with_act_is_valid(self) -> None:
        option = MissionOptionFactory(
            node=self.node,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.TECHNIQUE_CAST,
        )
        self.assertEqual(option.required_act, ExternalAct.TECHNIQUE_CAST)

    def test_external_act_forbids_check_fields(self) -> None:
        from world.checks.factories import CheckTypeFactory

        with self.assertRaises(ValidationError) as ctx:
            MissionOptionFactory(
                node=self.node,
                option_kind=OptionKind.EXTERNAL_ACT,
                source_kind=OptionSource.AUTHORED,
                required_act=ExternalAct.THREAD_WOVEN,
                authored_check_type=CheckTypeFactory(),
            )
        self.assertIn("authored_check_type", ctx.exception.error_dict)

    def test_non_external_act_forbids_required_act(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            MissionOptionFactory(
                node=self.node,
                option_kind=OptionKind.BRANCH,
                source_kind=OptionSource.AUTHORED,
                required_act=ExternalAct.COVENANT_SWORN,
            )
        self.assertIn("required_act", ctx.exception.error_dict)

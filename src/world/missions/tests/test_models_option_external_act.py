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

    def test_durable_act_on_non_entry_node_is_rejected(self) -> None:
        """THREAD_WOVEN/COVENANT_SWORN may only be authored on entry nodes (#1035).

        fast_forward_external_acts only runs from enter_node on the run's
        true entry — a mid-run node advance never re-checks durable state,
        so an option authored on a non-entry node could never fast-forward.
        """
        non_entry = MissionNodeFactory(template=self.node.template, key="mid", is_entry=False)
        with self.assertRaises(ValidationError) as ctx:
            MissionOptionFactory(
                node=non_entry,
                option_kind=OptionKind.EXTERNAL_ACT,
                source_kind=OptionSource.AUTHORED,
                required_act=ExternalAct.THREAD_WOVEN,
            )
        self.assertIn("required_act", ctx.exception.error_dict)

    def test_durable_act_on_entry_node_is_valid(self) -> None:
        option = MissionOptionFactory(
            node=self.node,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.COVENANT_SWORN,
        )
        self.assertEqual(option.required_act, ExternalAct.COVENANT_SWORN)

    def test_technique_cast_on_non_entry_node_is_valid(self) -> None:
        """TECHNIQUE_CAST is transient — free placement, unlike the durable acts."""
        non_entry = MissionNodeFactory(template=self.node.template, key="mid2", is_entry=False)
        option = MissionOptionFactory(
            node=non_entry,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.TECHNIQUE_CAST,
        )
        self.assertEqual(option.required_act, ExternalAct.TECHNIQUE_CAST)

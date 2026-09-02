"""ENCOUNTER option + route beat_outcome clean rules (#3565)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.combat.constants import RiskLevel
from world.missions.constants import ConflictMode, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionOpponentLineFactory,
)
from world.missions.models import MissionOption, MissionOptionRoute
from world.stories.constants import BeatOutcome


class EncounterOptionCleanTests(TestCase):
    def test_encounter_requires_risk_level(self) -> None:
        node = MissionNodeFactory(conflict_mode=ConflictMode.GROUP_VOTE)
        option = MissionOption(
            node=node,
            order=1,
            key="fight",
            option_kind=OptionKind.ENCOUNTER,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Draw steel",
        )
        with self.assertRaises(ValidationError) as ctx:
            option.full_clean()
        self.assertIn("encounter_risk_level", ctx.exception.message_dict)

    def test_encounter_forbids_check_and_branch_fields(self) -> None:
        node = MissionNodeFactory(conflict_mode=ConflictMode.GROUP_VOTE)
        base = MissionOptionFactory(
            node=node, option_kind=OptionKind.CHECK, authored_check_type=CheckTypeFactory()
        )
        option = MissionOption(
            node=node,
            order=2,
            key="fight",
            option_kind=OptionKind.ENCOUNTER,
            source_kind=OptionSource.AUTHORED,
            encounter_risk_level=RiskLevel.MODERATE,
            authored_check_type=base.authored_check_type,
            branch_target=node,
        )
        with self.assertRaises(ValidationError) as ctx:
            option.full_clean()
        self.assertIn("authored_check_type", ctx.exception.message_dict)
        self.assertIn("branch_target", ctx.exception.message_dict)

    def test_encounter_forbidden_on_joint_node(self) -> None:
        node = MissionNodeFactory(conflict_mode=ConflictMode.JOINT, joint_combine="any")
        option = MissionOption(
            node=node,
            order=1,
            key="fight",
            option_kind=OptionKind.ENCOUNTER,
            source_kind=OptionSource.AUTHORED,
            encounter_risk_level=RiskLevel.LOW,
        )
        with self.assertRaises(ValidationError) as ctx:
            option.full_clean()
        self.assertIn("option_kind", ctx.exception.message_dict)

    def test_non_encounter_option_may_not_set_risk_level(self) -> None:
        node = MissionNodeFactory(conflict_mode=ConflictMode.GROUP_VOTE)
        option = MissionOption(
            node=node,
            order=1,
            key="talk",
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            encounter_risk_level=RiskLevel.LOW,
        )
        with self.assertRaises(ValidationError) as ctx:
            option.full_clean()
        self.assertIn("encounter_risk_level", ctx.exception.message_dict)

    def test_encounter_must_be_authored_source(self) -> None:
        node = MissionNodeFactory(conflict_mode=ConflictMode.GROUP_VOTE)
        option = MissionOption(
            node=node,
            order=1,
            key="fight",
            option_kind=OptionKind.ENCOUNTER,
            source_kind=OptionSource.CHALLENGE,
            encounter_risk_level=RiskLevel.LOW,
        )
        with self.assertRaises(ValidationError) as ctx:
            option.full_clean()
        self.assertIn("source_kind", ctx.exception.message_dict)

    def test_valid_encounter_option_with_opponent_line(self) -> None:
        node = MissionNodeFactory(conflict_mode=ConflictMode.GROUP_VOTE)
        option = MissionOptionFactory(
            node=node,
            option_kind=OptionKind.ENCOUNTER,
            authored_check_type=None,
            encounter_risk_level=RiskLevel.HIGH,
        )
        option.full_clean()
        line = MissionOptionOpponentLineFactory(option=option, count=2)
        self.assertEqual(list(option.opponent_lines.all()), [line])


class RouteBeatOutcomeCleanTests(TestCase):
    def test_beat_outcome_only_on_terminal_route(self) -> None:
        node = MissionNodeFactory()
        option = MissionOptionFactory(
            node=node, option_kind=OptionKind.BRANCH, authored_check_type=None
        )
        route = MissionOptionRoute(
            option=option,
            outcome_tier=None,
            target_node=node,
            beat_outcome=BeatOutcome.FAILURE,
        )
        with self.assertRaises(ValidationError) as ctx:
            route.full_clean()
        self.assertIn("beat_outcome", ctx.exception.message_dict)

    def test_beat_outcome_allowed_on_terminal_route(self) -> None:
        option = MissionOptionFactory(option_kind=OptionKind.BRANCH, authored_check_type=None)
        route = MissionOptionRoute(
            option=option,
            outcome_tier=None,
            target_node=None,
            beat_outcome=BeatOutcome.FAILURE,
        )
        route.full_clean()
        self.assertEqual(route.beat_outcome, "failure")

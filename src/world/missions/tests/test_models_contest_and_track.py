"""CONTEST option and track node row validation (#3568)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.missions.constants import ConflictMode, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
    MissionTrackProgressFactory,
)
from world.missions.models import MissionOption, MissionTrackProgress
from world.stories.constants import BeatOutcome


class ContestOptionCleanTests(TestCase):
    def setUp(self) -> None:
        self.node = MissionNodeFactory()
        self.check_type = CheckTypeFactory()
        self.sheet = CharacterSheetFactory()

    def _contest(self, **overrides: object) -> MissionOption:
        fields = {
            "node": self.node,
            "order": 1,
            "option_kind": OptionKind.CONTEST,
            "source_kind": OptionSource.AUTHORED,
            "authored_check_type": self.check_type,
            "opposition_sheet": self.sheet,
            "opposition_check_type": self.check_type,
        }
        fields.update(overrides)
        return MissionOptionFactory.build(**fields)

    def test_valid_contest_saves(self) -> None:
        option = self._contest()
        option.save()
        self.assertEqual(option.option_kind, OptionKind.CONTEST)

    def test_contest_requires_opposition_sheet(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self._contest(opposition_sheet=None).save()
        self.assertIn("opposition_sheet", ctx.exception.message_dict)

    def test_contest_requires_opposition_check_type(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self._contest(opposition_check_type=None).save()
        self.assertIn("opposition_check_type", ctx.exception.message_dict)

    def test_contest_requires_authored_check_type(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            self._contest(authored_check_type=None).save()
        self.assertIn("authored_check_type", ctx.exception.message_dict)

    def test_check_forbids_opposition_fields(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            MissionOptionFactory(
                node=self.node,
                option_kind=OptionKind.CHECK,
                authored_check_type=self.check_type,
                opposition_sheet=self.sheet,
            )
        self.assertIn("opposition_sheet", ctx.exception.message_dict)

    def test_opposition_sheet_delete_is_protected(self) -> None:
        option = self._contest()
        option.save()
        with self.assertRaises(ProtectedError):
            self.sheet.delete()


class TrackNodeCleanTests(TestCase):
    def setUp(self) -> None:
        self.template = MissionTemplateFactory()

    def test_track_thresholds_must_both_be_set(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            MissionNodeFactory(template=self.template, track_successes=3, track_failures=0)
        self.assertIn("track_failures", ctx.exception.message_dict)

    def test_track_node_may_not_be_joint(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            MissionNodeFactory(
                template=self.template,
                conflict_mode=ConflictMode.JOINT,
                joint_combine="any",
                track_successes=3,
                track_failures=2,
            )
        self.assertIn("conflict_mode", ctx.exception.message_dict)

    def test_non_track_node_forbids_track_targets(self) -> None:
        other = MissionNodeFactory(template=self.template)
        with self.assertRaises(ValidationError) as ctx:
            MissionNodeFactory(template=self.template, track_success_target=other)
        self.assertIn("track_success_target", ctx.exception.message_dict)

    def test_non_track_node_forbids_track_beat_outcomes(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            MissionNodeFactory(
                template=self.template, track_failure_beat_outcome=BeatOutcome.FAILURE
            )
        self.assertIn("track_failure_beat_outcome", ctx.exception.message_dict)

    def test_is_track(self) -> None:
        node = MissionNodeFactory(template=self.template, track_successes=3, track_failures=2)
        self.assertTrue(node.is_track)
        self.assertFalse(MissionNodeFactory(template=self.template).is_track)

    def test_track_node_refuses_encounter_option(self) -> None:
        node = MissionNodeFactory(template=self.template, track_successes=3, track_failures=2)
        with self.assertRaises(ValidationError) as ctx:
            MissionOptionFactory(
                node=node, option_kind=OptionKind.ENCOUNTER, encounter_risk_level="low"
            )
        self.assertIn("option_kind", ctx.exception.message_dict)

    def test_check_route_on_track_node_forbids_target_node(self) -> None:
        node = MissionNodeFactory(template=self.template, track_successes=3, track_failures=2)
        other = MissionNodeFactory(template=self.template)
        option = MissionOptionFactory(
            node=node, option_kind=OptionKind.CHECK, authored_check_type=CheckTypeFactory()
        )
        route = MissionOptionRouteFactory.build(option=option, target_node=other)
        with self.assertRaises(ValidationError) as ctx:
            route.full_clean()
        self.assertIn("target_node", ctx.exception.message_dict)

    def test_branch_route_on_track_node_may_leave(self) -> None:
        node = MissionNodeFactory(template=self.template, track_successes=3, track_failures=2)
        other = MissionNodeFactory(template=self.template)
        option = MissionOptionFactory(node=node, option_kind=OptionKind.BRANCH)
        route = MissionOptionRouteFactory(option=option, target_node=other)
        self.assertEqual(route.target_node, other)


class TrackProgressTests(TestCase):
    def test_unique_per_instance_and_node(self) -> None:
        progress = MissionTrackProgressFactory()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MissionTrackProgress.objects.create(instance=progress.instance, node=progress.node)

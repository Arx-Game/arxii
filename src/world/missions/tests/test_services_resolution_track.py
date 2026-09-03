"""Track nodes (#3568): CHECK/CONTEST deeds count toward thresholds and route.

Same fixture style as ``test_services_resolution_resolve.py``: a track node
(``track_successes=2, track_failures=2``) with ``track_success_target=win_node``,
``track_failure_target=None``, ``track_failure_beat_outcome=FAILURE``, and one
CHECK option whose per-tier routes have ``target_node=None`` (a track's CHECK
routes never route themselves - the track decides).
"""

from __future__ import annotations

from unittest import mock
from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.missions.constants import MissionStatus, OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGroupBallot, MissionNodeSnapshot, MissionTrackProgress
from world.missions.services import resolve_group_node
from world.missions.services.resolution import enter_node, resolve_option
from world.stories.constants import BeatOutcome
from world.traits.factories import CheckOutcomeFactory

_APPLY = "world.missions.services.resolution.apply_all_effects"
_ON_COMPLETE = "world.missions.services.resolution.on_mission_complete_for_beat"


class TrackNodeResolutionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

        self.template = MissionTemplateFactory(name="track-tmpl", risk_tier=2)
        self.instance = MissionInstanceFactory(template=self.template)
        self.win_node = MissionNodeFactory(template=self.template, key="win")
        self.track_node = MissionNodeFactory(
            template=self.template,
            key="track",
            track_successes=2,
            track_failures=2,
            track_success_target=self.win_node,
            track_failure_target=None,
            track_failure_beat_outcome=BeatOutcome.FAILURE,
        )
        self.actor = MissionParticipantFactory(
            instance=self.instance,
            character=self.character.sheet_data,
            is_contract_holder=True,
        )
        self.instance.current_node = self.track_node
        self.instance.save()

        self.success = CheckOutcomeFactory(name="TrackSuccess", success_level=3)
        self.failure = CheckOutcomeFactory(name="TrackFailure", success_level=-3)
        self.check_type = CheckTypeFactory(name="TrackCheck")

        self.check_option = MissionOptionFactory(
            node=self.track_node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        self.success_conseq = ConsequenceFactory(outcome_tier=self.success)
        self.success_route = MissionOptionRouteFactory(
            option=self.check_option,
            outcome_tier=self.success,
            target_node=None,
            consequence=self.success_conseq,
        )
        self.failure_route = MissionOptionRouteFactory(
            option=self.check_option,
            outcome_tier=self.failure,
            target_node=None,
        )

    def test_first_success_stays_on_node_and_counts(self) -> None:
        with force_check_outcome(self.success), patch(_APPLY) as mocked:
            resolve_option(self.instance, self.track_node, self.check_option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.track_node)
        progress = MissionTrackProgress.objects.get(instance=self.instance, node=self.track_node)
        self.assertEqual(progress.successes, 1)
        self.assertEqual(progress.failures, 0)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(mocked.call_args_list[0].args[0], self.success_conseq)
        self.assertEqual(self.instance.status, MissionStatus.ACTIVE)

    def test_nth_success_routes_to_success_target(self) -> None:
        for _ in range(2):
            with force_check_outcome(self.success), patch(_APPLY):
                resolve_option(self.instance, self.track_node, self.check_option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.win_node)
        self.assertTrue(
            MissionNodeSnapshot.objects.filter(instance=self.instance, node=self.win_node).exists()
        )

    def test_mth_failure_with_null_target_terminates_with_authored_failure(self) -> None:
        with mock.patch(_ON_COMPLETE) as mocked:
            for _ in range(2):
                with force_check_outcome(self.failure), patch(_APPLY):
                    resolve_option(self.instance, self.track_node, self.check_option, self.actor)
        self.instance.refresh_from_db()
        self.assertIn(self.instance.status, (MissionStatus.COMPLETE, MissionStatus.RESOLVED))
        self.assertIsNone(self.instance.current_node)
        mocked.assert_called_once_with(
            self.instance, route=None, option=None, beat_outcome=BeatOutcome.FAILURE
        )

    def test_reentry_resets_progress(self) -> None:
        with force_check_outcome(self.success), patch(_APPLY):
            resolve_option(self.instance, self.track_node, self.check_option, self.actor)
        progress = MissionTrackProgress.objects.get(instance=self.instance, node=self.track_node)
        self.assertEqual((progress.successes, progress.failures), (1, 0))

        enter_node(self.instance, self.track_node)

        progress.refresh_from_db()
        self.assertEqual((progress.successes, progress.failures), (0, 0))

    def test_group_vote_counts_once(self) -> None:
        p2 = MissionParticipantFactory(instance=self.instance, character=CharacterSheetFactory())
        MissionGroupBallot.objects.create(
            instance=self.instance,
            node=self.track_node,
            participant=self.actor,
            picked_option=self.check_option,
            voted_option=None,
        )
        MissionGroupBallot.objects.create(
            instance=self.instance,
            node=self.track_node,
            participant=p2,
            picked_option=self.check_option,
            voted_option=None,
        )
        with force_check_outcome(self.success), patch(_APPLY):
            resolve_group_node(self.instance, self.track_node)
        progress = MissionTrackProgress.objects.get(instance=self.instance, node=self.track_node)
        self.assertEqual((progress.successes, progress.failures), (1, 0))

    def test_branch_option_on_track_node_routes_normally(self) -> None:
        other = MissionNodeFactory(template=self.template, key="other")
        branch = MissionOptionFactory(
            node=self.track_node,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            branch_target=other,
        )
        resolve_option(self.instance, self.track_node, branch, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, other)
        self.assertFalse(
            MissionTrackProgress.objects.filter(
                instance=self.instance, node=self.track_node
            ).exists()
        )

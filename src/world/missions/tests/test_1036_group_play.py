"""Tests for the #1036 group decision play surface + API + timeout sweep.

The engine (``resolve_group_node`` / ``_tally_group_winner`` / JOINT) is covered
in ``test_services_multiplayer``; this file drives the player-facing two-stage
flow (``submit_group_pick`` → ``cast_group_vote`` → resolve), the lazy/cron
timeout, and the ``MissionJournalViewSet`` group endpoints. GROUP_VOTE nodes use
BRANCH options so routing is deterministic (no dice); the JOINT trigger reuses a
forced CHECK outcome.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import (
    GROUP_VOTE_TIMEOUT_SECONDS,
    ConflictMode,
    JointCombine,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGroupBallot
from world.missions.services.cron import resolve_expired_group_votes
from world.missions.services.play import (
    BeatActionError,
    cast_group_vote,
    group_beat,
    submit_group_pick,
)
from world.missions.services.run import share_mission, staff_assign_mission


def _pc():
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


def _group_graph(name, *, conflict_mode=ConflictMode.GROUP_VOTE):
    """A group entry node with two BRANCH options, each routing to a dest."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(
        template=template,
        key="entry",
        is_entry=True,
        conflict_mode=conflict_mode,
        joint_combine=JointCombine.ANY if conflict_mode == ConflictMode.JOINT else None,
    )
    dest_a = MissionNodeFactory(template=template, key="dest-a")
    dest_b = MissionNodeFactory(template=template, key="dest-b")
    opt_a = MissionOptionFactory(
        node=entry,
        order=0,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="Path A",
        branch_target=dest_a,
    )
    opt_b = MissionOptionFactory(
        node=entry,
        order=1,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="Path B",
        branch_target=dest_b,
    )
    return template, entry, opt_a, opt_b, dest_a, dest_b


def _group(name="grp"):
    """A 2-participant ACTIVE run; returns (instance, holder_char, p2_char, opts...)."""
    holder = _pc()
    p2 = _pc()
    template, _entry, opt_a, opt_b, dest_a, dest_b = _group_graph(name)
    instance = staff_assign_mission(template, holder)
    share_mission(instance, p2)
    return instance, holder, p2, opt_a, opt_b, dest_a, dest_b


class GroupVoteFlowTests(TestCase):
    def test_full_pick_then_vote_resolves_to_plurality(self):
        instance, holder, p2, opt_a, opt_b, dest_a, _ = _group("flow")
        # Stage 1: both pick (different options).
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        res = submit_group_pick(instance, p2, option_id=opt_b.pk)
        self.assertIsNotNone(res.group_beat)
        self.assertEqual(res.group_beat.phase, "vote")  # all picked → vote opens
        # Stage 2: both vote A → A wins → resolves, routes to dest_a.
        cast_group_vote(instance, holder, option_id=opt_a.pk)
        res = cast_group_vote(instance, p2, option_id=opt_a.pk)
        self.assertIsNotNone(res.resolved)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node_id, dest_a.pk)
        # Ballots cleared after resolution.
        self.assertFalse(MissionGroupBallot.objects.filter(instance=instance).exists())

    def test_vote_before_all_picked_is_rejected(self):
        instance, holder, _p2, opt_a, _opt_b, _da, _db = _group("early")
        submit_group_pick(instance, holder, option_id=opt_a.pk)  # only one of two picked
        with self.assertRaises(BeatActionError):
            cast_group_vote(instance, holder, option_id=opt_a.pk)

    def test_cannot_vote_for_unsurfaced_option(self):
        instance, holder, p2, opt_a, opt_b, _da, _db = _group("surfaced")
        # Both pick opt_a; opt_b was never put forward.
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        submit_group_pick(instance, p2, option_id=opt_a.pk)
        with self.assertRaises(BeatActionError):
            cast_group_vote(instance, holder, option_id=opt_b.pk)

    def test_cannot_pick_another_participants_option_id_unowned(self):
        instance, holder, _p2, _opt_a, _opt_b, _da, _db = _group("ownership")
        # 999 is not a live option for this character.
        with self.assertRaises(BeatActionError):
            submit_group_pick(instance, holder, option_id=999999)

    def test_votes_override_picks(self):
        instance, holder, p2, opt_a, opt_b, *_ = _group("override")
        # picks: A and B (tie); votes: both B → B wins deterministically.
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        submit_group_pick(instance, p2, option_id=opt_b.pk)
        cast_group_vote(instance, holder, option_id=opt_b.pk)
        res = cast_group_vote(instance, p2, option_id=opt_b.pk)
        self.assertIsNotNone(res.resolved)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node_id, opt_b.branch_target_id)


class GroupVoteTimeoutTests(TestCase):
    def _expire(self, instance, node):
        past = timezone.now() - timedelta(seconds=GROUP_VOTE_TIMEOUT_SECONDS + 5)
        MissionGroupBallot.objects.filter(instance=instance, node=node).update(created_at=past)

    def test_lazy_resolve_on_access_after_window_expires(self):
        instance, holder, p2, opt_a, opt_b, _da, _db = _group("lazy")
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        submit_group_pick(instance, p2, option_id=opt_b.pk)  # picked, never voted
        self._expire(instance, instance.current_node)
        # A plain view past the deadline resolves from the picks (no votes).
        res = group_beat(instance, holder)
        self.assertIsNotNone(res.resolved)
        instance.refresh_from_db()
        self.assertIn(instance.current_node_id, {opt_a.branch_target_id, opt_b.branch_target_id})

    def test_cron_sweep_resolves_abandoned_group(self):
        instance, holder, p2, opt_a, opt_b, _da, _db = _group("sweep")
        node = instance.current_node
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        submit_group_pick(instance, p2, option_id=opt_b.pk)
        self._expire(instance, node)
        self.assertEqual(resolve_expired_group_votes(), 1)
        instance.refresh_from_db()
        self.assertNotEqual(instance.current_node_id, node.pk)
        # Idempotent: a second sweep finds nothing.
        self.assertEqual(resolve_expired_group_votes(), 0)


class GroupVoteApiTests(TestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.instance, self.holder, self.p2, self.opt_a, self.opt_b, *_ = _group("api")
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def _as(self, character):
        return mock.patch("world.missions.views._puppet_character", return_value=character)

    def _url(self, action):
        return f"/api/missions/journal/{self.instance.pk}/{action}/"

    def test_group_pick_and_vote_through_api_resolves(self):
        with self._as(self.holder):
            r = self.client.post(
                self._url("group-pick"), {"option_id": self.opt_a.pk}, format="json"
            )
        self.assertEqual(r.status_code, 200)
        with self._as(self.p2):
            r = self.client.post(
                self._url("group-pick"), {"option_id": self.opt_a.pk}, format="json"
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["group_beat"]["phase"], "vote")
        with self._as(self.holder):
            self.client.post(self._url("group-vote"), {"option_id": self.opt_a.pk}, format="json")
        with self._as(self.p2):
            r = self.client.post(
                self._url("group-vote"), {"option_id": self.opt_a.pk}, format="json"
            )
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.data["resolved"])

    def test_group_beat_ballot_has_character_name(self):
        """GroupBallotState exposes character_name alongside character_id (#2049)."""
        # Submit picks first — ballots are created on pick, not on beat access.
        with self._as(self.holder):
            self.client.post(self._url("group-pick"), {"option_id": self.opt_a.pk}, format="json")
        with self._as(self.p2):
            self.client.post(self._url("group-pick"), {"option_id": self.opt_a.pk}, format="json")
        with self._as(self.holder):
            r = self.client.get(self._url("group-beat"))
        self.assertEqual(r.status_code, 200)
        ballots = r.data["group_beat"]["ballots"]
        self.assertEqual(len(ballots), 2)
        names = {self.holder.key, self.p2.key}
        for ballot in ballots:
            self.assertIn(ballot["character_name"], names)
            self.assertTrue(ballot["character_name"])

    def test_group_beat_non_participant_404(self):
        with self._as(_pc()):
            r = self.client.get(self._url("group-beat"))
        self.assertEqual(r.status_code, 404)

    def test_group_vote_before_pick_400(self):
        with self._as(self.holder):
            r = self.client.post(
                self._url("group-vote"), {"option_id": self.opt_a.pk}, format="json"
            )
        self.assertEqual(r.status_code, 400)


class GroupJointTriggerTests(TestCase):
    """JOINT resolves on all-picked (no vote stage); routing covered in the engine tests."""

    def test_joint_resolves_when_all_picked(self):
        from unittest.mock import patch

        from world.checks.factories import CheckTypeFactory, ConsequenceFactory
        from world.checks.types import CheckResult
        from world.missions.factories import MissionOptionRouteFactory
        from world.traits.factories import CheckOutcomeFactory

        holder = _pc()
        p2 = _pc()
        template = MissionTemplateFactory(name="joint-play")
        entry = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        dest = MissionNodeFactory(template=template, key="dest")
        success = CheckOutcomeFactory(name="JointWin", success_level=3)
        check = CheckTypeFactory(name="JointCheck")
        opt = MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=check,
        )
        MissionOptionRouteFactory(
            option=opt,
            outcome_tier=success,
            target_node=dest,
            consequence=ConsequenceFactory(outcome_tier=success),
        )
        instance = staff_assign_mission(template, holder)
        share_mission(instance, p2)

        # Both participants roll a CHECK, so pin BOTH (force_check_outcome is
        # single-shot); ANY + both success → combined success → dest.
        def _always_success(character, check_type, **_kw):
            return CheckResult(
                check_type=check_type,
                outcome=success,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )

        with patch("world.missions.services.resolution.perform_check", side_effect=_always_success):
            submit_group_pick(instance, holder, option_id=opt.pk)
            res = submit_group_pick(instance, p2, option_id=opt.pk)  # last pick resolves JOINT
        self.assertIsNotNone(res.resolved)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node_id, dest.pk)


class GroupVoteRegressionTests(TestCase):
    """Adversarial-review regressions (#1036)."""

    def test_repick_after_others_voted_does_not_crash(self):
        # B1: a stale vote for a now-unpicked option must be filtered at tally
        # (not crash with a winner that has no picker). The still-surfaced
        # option wins.
        instance, holder, p2, opt_a, opt_b, *_ = _group("repick")
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        submit_group_pick(instance, p2, option_id=opt_b.pk)
        cast_group_vote(instance, p2, option_id=opt_a.pk)  # p2 votes A (surfaced)
        submit_group_pick(instance, holder, option_id=opt_b.pk)  # A now unpicked
        res = cast_group_vote(instance, holder, option_id=opt_b.pk)  # all voted → resolve
        self.assertIsNotNone(res.resolved)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node_id, opt_b.branch_target_id)

    def test_joint_timeout_without_holder_pick_resolves(self):
        # B2: timeout fires JOINT resolution even when the holder never picked —
        # the routing anchor falls back to a picker rather than raising.
        from unittest.mock import patch

        from world.checks.factories import CheckTypeFactory, ConsequenceFactory
        from world.checks.types import CheckResult
        from world.missions.factories import MissionOptionRouteFactory
        from world.traits.factories import CheckOutcomeFactory

        holder = _pc()
        p2 = _pc()
        template = MissionTemplateFactory(name="joint-timeout")
        entry = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        dest = MissionNodeFactory(template=template, key="dest")
        success = CheckOutcomeFactory(name="JTWin", success_level=3)
        check = CheckTypeFactory(name="JTCheck")
        opt = MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=check,
        )
        MissionOptionRouteFactory(
            option=opt,
            outcome_tier=success,
            target_node=dest,
            consequence=ConsequenceFactory(outcome_tier=success),
        )
        instance = staff_assign_mission(template, holder)
        share_mission(instance, p2)

        def _always_success(character, check_type, **_kw):
            return CheckResult(
                check_type=check_type,
                outcome=success,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )

        with patch("world.missions.services.resolution.perform_check", side_effect=_always_success):
            submit_group_pick(instance, p2, option_id=opt.pk)  # holder never picks
        # Expire the window, then a lazy access resolves anchoring on p2.
        past = timezone.now() - timedelta(seconds=GROUP_VOTE_TIMEOUT_SECONDS + 5)
        MissionGroupBallot.objects.filter(instance=instance).update(created_at=past)
        with patch("world.missions.services.resolution.perform_check", side_effect=_always_success):
            res = group_beat(instance, p2)
        self.assertIsNotNone(res.resolved)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node_id, dest.pk)


class GroupVotePauseGateTests(TestCase):
    """Regression (#1899 whole-branch review): the play-surface ``is not None``
    ⇔ "really resolved" contract must hold under pause.

    ``resolve_group_node`` returns ``[]`` (not ``None``) when the instance is
    paused — a sentinel needed by the cron sweep, which calls it directly.
    Before the fix, ``_resolve_group_if_ready``/``_resolve_if_expired`` passed
    that ``[]`` straight through to their callers, and every play-surface
    caller (``group_beat``/``submit_group_pick``/``cast_group_vote``) treats
    any non-None return as "the beat resolved" — so a paused instance whose
    ballots satisfied the ready condition would falsely tell the still-connected
    co-participant the beat resolved, even though the mission is frozen.
    """

    def test_paused_instance_cast_group_vote_reports_not_resolved(self):
        instance, holder, p2, opt_a, _opt_b, _dest_a, _dest_b = _group("pause-vote")
        entry_node_id = instance.current_node_id
        # Both pick, opening the vote phase — resolution WOULD fire once both
        # vote, absent the pause.
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        submit_group_pick(instance, p2, option_id=opt_a.pk)
        instance.is_paused = True
        instance.save(update_fields=["is_paused"])

        cast_group_vote(instance, holder, option_id=opt_a.pk)
        res = cast_group_vote(instance, p2, option_id=opt_a.pk)  # all voted → would resolve

        # The correct branch is "not ready yet" (group_beat set), NOT "resolved".
        self.assertIsNone(res.resolved)
        self.assertIsNotNone(res.group_beat)
        # The mission never actually advanced, and the ballots survive
        # untouched (resolve_group_node's atomic resolve+delete never ran).
        instance.refresh_from_db()
        self.assertEqual(instance.current_node_id, entry_node_id)
        self.assertTrue(MissionGroupBallot.objects.filter(instance=instance).exists())

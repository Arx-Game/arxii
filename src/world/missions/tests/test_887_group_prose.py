"""Tests for per-actor STORY + ambient stir on group resolution (#887)."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.types import CheckResult
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
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGroupBallot
from world.missions.services.cron import resolve_expired_group_votes
from world.missions.services.play import cast_group_vote, submit_group_pick
from world.missions.services.run import share_mission, staff_assign_mission
from world.missions.tests.test_1036_group_play import _group_graph, _pc
from world.traits.factories import CheckOutcomeFactory


def _make_room():
    """A room with an ensured RoomProfile so anchor_room resolves in tests."""
    from evennia_extensions.models import RoomProfile

    room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.get_or_create(objectdb=room)
    return room


def _pc_in_room():
    """A character sheet whose character stands in a profiled room."""
    room = _make_room()
    return _pc(), room


def _group_vote_in_room(name="vote"):
    """A 2-participant ACTIVE GROUP_VOTE run; holder + p2 co-located in a room."""
    template, _entry, opt_a, opt_b, dest_a, dest_b = _group_graph(name)
    holder, room = _pc_in_room()
    holder.location = room
    holder.save()
    p2 = _pc()
    p2.location = room
    p2.save()
    instance = staff_assign_mission(template, holder)
    share_mission(instance, p2)
    return instance, holder, p2, opt_a, opt_b, dest_a, dest_b


def _group_joint_in_room(name="joint"):
    """A 2-participant ACTIVE JOINT run with a CHECK graph; both co-located."""
    holder, room = _pc_in_room()
    holder.location = room
    holder.save()
    p2 = _pc()
    p2.location = room
    p2.save()
    template = MissionTemplateFactory(name=name)
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
        authored_ic_framing="The joint attempt",
    )
    MissionOptionRouteFactory(
        option=opt,
        outcome_tier=success,
        target_node=dest,
        consequence=ConsequenceFactory(outcome_tier=success),
    )
    instance = staff_assign_mission(template, holder)
    share_mission(instance, p2)
    return instance, holder, p2, opt, success


def _always_success_factory(success):
    """A perform_check side effect that always rolls ``success``."""

    def _always_success(_character, _check_type, **_kw):
        return CheckResult(
            check_type=_check_type,
            outcome=success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    return _always_success


class GroupResolutionProseTest(TestCase):
    def test_joint_each_actor_gets_their_own_story(self) -> None:
        instance, holder, p2, opt, success = _group_joint_in_room("joint-prose")
        with (
            patch("world.missions.services.multiplayer.send_narrative_message") as send,
            patch("world.missions.services.multiplayer.emit_ambient_room_stir") as stir,
            patch(
                "world.missions.services.resolution.perform_check",
                side_effect=_always_success_factory(success),
            ),
        ):
            submit_group_pick(instance, holder, option_id=opt.pk)
            submit_group_pick(instance, p2, option_id=opt.pk)  # last pick resolves JOINT
            self.assertEqual(send.call_count, 2)
            stir.assert_called_once()

    def test_group_vote_only_winner_gets_story(self) -> None:
        instance, holder, p2, opt_a, opt_b, *_ = _group_vote_in_room("vote-prose")
        with (
            patch("world.missions.services.multiplayer.send_narrative_message") as send,
            patch("world.missions.services.multiplayer.emit_ambient_room_stir") as stir,
        ):
            submit_group_pick(instance, holder, option_id=opt_a.pk)
            submit_group_pick(instance, p2, option_id=opt_b.pk)
            cast_group_vote(instance, holder, option_id=opt_a.pk)
            cast_group_vote(instance, p2, option_id=opt_a.pk)  # all voted -> resolve
            self.assertEqual(send.call_count, 1)
            stir.assert_called_once()

    def test_cron_sweep_emits_prose(self) -> None:
        instance, holder, p2, opt_a, opt_b, *_ = _group_vote_in_room("cron-prose")
        submit_group_pick(instance, holder, option_id=opt_a.pk)
        submit_group_pick(instance, p2, option_id=opt_b.pk)
        MissionGroupBallot.objects.filter(instance=instance).update(
            created_at=timezone.now() - timedelta(seconds=GROUP_VOTE_TIMEOUT_SECONDS + 1)
        )
        with (
            patch("world.missions.services.multiplayer.send_narrative_message") as send,
            patch("world.missions.services.multiplayer.emit_ambient_room_stir") as stir,
        ):
            n = resolve_expired_group_votes()
            self.assertEqual(n, 1)
            self.assertTrue(send.call_count >= 1)
            stir.assert_called_once()

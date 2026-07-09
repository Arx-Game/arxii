"""Tests for CmdScene — the thin telnet face of scene lifecycle actions.

Pattern mirrors test_entrance_flourish_e2e.py: construct the command,
set caller/args, call func(), inspect caller.msg call_args_list.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.scene import CmdScene
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundStartReason
from world.scenes.factories import (
    SceneFactory,
    SceneOwnerParticipationFactory,
    SceneRoundParticipantFactory,
)
from world.scenes.models import Scene, SceneParticipation, SceneRound

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room(label: str = "CmdSceneRoom"):
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _create_pc_with_account(db_key: str, location=None):
    """Create a PC with a live roster tenure (active_account is non-None).

    Returns (character, account).
    """
    kwargs = {"db_key": db_key}
    if location is not None:
        kwargs["location"] = location
    char = CharacterFactory(**kwargs)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    return char, account


def _run_cmd(caller, args: str) -> list[str]:
    """Construct and run CmdScene; return all positional string messages."""
    cmd = CmdScene()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"scene {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


# ---------------------------------------------------------------------------
# scene start
# ---------------------------------------------------------------------------


class CmdSceneStartTests(TestCase):
    """``scene start`` dispatches StartSceneAction and creates a scene."""

    def setUp(self):
        self.room = _make_room("StartRoom")
        self.caller, _account = _create_pc_with_account("SceneStarter", location=self.room)
        self.caller.msg = MagicMock()

    def test_start_creates_active_scene(self):
        """``scene start`` creates an active Scene in the room."""
        _run_cmd(self.caller, "start")
        self.assertTrue(Scene.objects.filter(location=self.room, is_active=True).exists())

    def test_start_messages_caller(self):
        """Caller receives the action's result message after start."""
        messages = _run_cmd(self.caller, "start")
        self.assertTrue(messages, "Expected at least one message after scene start")

    def test_start_with_name_passes_name(self):
        """``scene start My Scene Name`` still creates the scene (name kwarg forwarded)."""
        _run_cmd(self.caller, "start My Scene Name")
        self.assertTrue(Scene.objects.filter(location=self.room, is_active=True).exists())


# ---------------------------------------------------------------------------
# scene finish
# ---------------------------------------------------------------------------


_BROADCAST_PATCH = "world.scenes.scene_admin_services.broadcast_scene_message"


class CmdSceneFinishTests(TestCase):
    """``scene finish`` dispatches FinishSceneAction."""

    def setUp(self):
        self.room = _make_room("FinishRoom")
        self.caller, self.account = _create_pc_with_account("SceneFinisher", location=self.room)
        self.caller.msg = MagicMock()
        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account)

    def test_finish_closes_scene(self):
        """``scene finish`` marks the scene as finished."""
        with patch(_BROADCAST_PATCH):
            _run_cmd(self.caller, "finish")
        self.scene.refresh_from_db()
        self.assertFalse(self.scene.is_active)

    def test_finish_messages_caller(self):
        """Caller receives a confirmation message after scene finish."""
        with patch(_BROADCAST_PATCH):
            messages = _run_cmd(self.caller, "finish")
        self.assertTrue(messages, "Expected at least one message after scene finish")

    def test_finish_denied_for_non_owner(self):
        """A non-owner receives a failure message and scene stays active."""
        non_owner, _acc = _create_pc_with_account("NonOwner", location=self.room)
        non_owner.msg = MagicMock()
        # broadcast is never reached when the permission gate refuses.
        _run_cmd(non_owner, "finish")
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.is_active)


# ---------------------------------------------------------------------------
# scene gm
# ---------------------------------------------------------------------------


class CmdSceneGmTests(TestCase):
    """``scene gm <name>`` dispatches GrantSceneGMAction (#2113)."""

    def setUp(self):
        self.room = _make_room("GmRoom")
        self.owner, self.owner_account = _create_pc_with_account("GmOwner", location=self.room)
        self.owner.msg = MagicMock()
        self.target, self.target_account = _create_pc_with_account("GmTarget", location=self.room)
        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneOwnerParticipationFactory(scene=self.scene, account=self.owner_account)

    def test_gm_grants_to_present_approved_gm(self):
        """A scene owner grants GM status to a present GMProfile holder."""
        GMProfileFactory(account=self.target_account)

        messages = _run_cmd(self.owner, f"gm {self.target.db_key}")

        self.assertTrue(
            SceneParticipation.objects.filter(
                scene=self.scene, account=self.target_account, is_gm=True
            ).exists()
        )
        self.assertTrue(messages, "Expected at least one message after scene gm grant")

    def test_gm_missing_name_shows_usage(self):
        """``scene gm`` with no name shows the usage message."""
        messages = _run_cmd(self.owner, "gm")
        self.assertTrue(
            any("usage: scene gm" in m.lower() for m in messages),
            f"Expected usage message; got: {messages}",
        )

    def test_gm_denied_for_non_admin_actor(self):
        """A present PC who doesn't administer the scene cannot grant GM status."""
        GMProfileFactory(account=self.target_account)
        non_admin, _acc = _create_pc_with_account("GmNonAdmin", location=self.room)
        non_admin.msg = MagicMock()

        _run_cmd(non_admin, f"gm {self.target.db_key}")

        self.assertFalse(
            SceneParticipation.objects.filter(
                scene=self.scene, account=self.target_account, is_gm=True
            ).exists()
        )

    def test_gm_denied_for_target_without_gm_profile(self):
        """A present target with no GMProfile is refused."""
        messages = _run_cmd(self.owner, f"gm {self.target.db_key}")

        self.assertFalse(
            SceneParticipation.objects.filter(
                scene=self.scene, account=self.target_account, is_gm=True
            ).exists()
        )
        self.assertTrue(
            any("not an approved gm" in m.lower() for m in messages),
            f"Expected a not-approved-GM message; got: {messages}",
        )


# ---------------------------------------------------------------------------
# scene round
# ---------------------------------------------------------------------------


class CmdSceneRoundTests(TestCase):
    """``scene round <mode> [knobs]`` dispatches SetRoundModeAction."""

    def setUp(self):
        self.room = _make_room("RoundRoom")
        self.caller, self.account = _create_pc_with_account("RoundOwner", location=self.room)
        self.caller.msg = MagicMock()
        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account)
        self.rnd = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
            mode=SceneRoundMode.POSE_ORDER,
            scene=self.scene,
        )

    def test_round_strict_sets_mode(self):
        """``scene round strict`` sets the round mode to STRICT."""
        _run_cmd(self.caller, "round strict")
        self.rnd.refresh_from_db()
        self.assertEqual(self.rnd.mode, SceneRoundMode.STRICT)

    def test_round_strict_quorum_cap_lock_parsed(self):
        """All optional knobs are parsed and forwarded to the action."""
        _run_cmd(self.caller, "round strict quorum=70 cap=2 lock=on")
        self.rnd.refresh_from_db()
        self.assertEqual(self.rnd.mode, SceneRoundMode.STRICT)
        self.assertEqual(self.rnd.advance_quorum_pct, 70)
        self.assertEqual(self.rnd.max_actions_per_round, 2)
        self.assertTrue(self.rnd.per_target_repeat_lock)

    def test_round_messages_caller(self):
        """Caller receives the action result message after mode change."""
        messages = _run_cmd(self.caller, "round open")
        self.assertTrue(messages, "Expected at least one message after round mode change")

    def test_round_bad_quorum_shows_error(self):
        """Non-numeric quorum value emits a friendly error; round is unchanged."""
        _run_cmd(self.caller, "round strict quorum=abc")
        self.rnd.refresh_from_db()
        self.assertEqual(self.rnd.mode, SceneRoundMode.POSE_ORDER)
        messages = [str(c.args[0]) for c in self.caller.msg.call_args_list if c.args]
        self.assertTrue(
            any("number" in m.lower() for m in messages),
            f"Expected error message about numbers; got: {messages}",
        )

    def test_round_bad_cap_shows_error(self):
        """Non-numeric cap value emits a friendly error."""
        _run_cmd(self.caller, "round strict cap=xyz")
        messages = [str(c.args[0]) for c in self.caller.msg.call_args_list if c.args]
        self.assertTrue(
            any("number" in m.lower() for m in messages),
            f"Expected error message about numbers; got: {messages}",
        )

    def test_round_lock_off_sets_false(self):
        """``lock=off`` parses to False."""
        self.rnd.per_target_repeat_lock = True
        self.rnd.save(update_fields=["per_target_repeat_lock"])
        _run_cmd(self.caller, "round strict lock=off")
        self.rnd.refresh_from_db()
        self.assertFalse(self.rnd.per_target_repeat_lock)


# ---------------------------------------------------------------------------
# scene interpose
# ---------------------------------------------------------------------------


class CmdSceneInterposeTests(TestCase):
    """``scene interpose <ally>`` dispatches InterposeSceneAction (#1316)."""

    def setUp(self):
        self.room = _make_room("InterposeRoom")
        self.caller, self.account = _create_pc_with_account("Interposer", location=self.room)
        self.caller.msg = MagicMock()
        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account)
        self.rnd = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
            mode=SceneRoundMode.STRICT,
            scene=self.scene,
        )
        SceneRoundParticipantFactory(scene_round=self.rnd, character_sheet=self.caller.sheet_data)
        self.ally, _ally_account = _create_pc_with_account("ProtectedAlly", location=self.room)
        SceneRoundParticipantFactory(scene_round=self.rnd, character_sheet=self.ally.sheet_data)

    def test_interpose_dispatches_and_messages_caller(self):
        """A named ally present in the round is accepted; caller gets a result message."""
        messages = _run_cmd(self.caller, f"interpose {self.ally.db_key}")
        self.assertTrue(messages, "Expected at least one message after scene interpose")
        self.assertTrue(
            any("shelter" in m.lower() or "guard" in m.lower() for m in messages),
            f"Expected a success message; got: {messages}",
        )

    def test_interpose_missing_ally_shows_usage(self):
        """``scene interpose`` with no ally name shows the usage message."""
        messages = _run_cmd(self.caller, "interpose")
        self.assertTrue(
            any("usage: scene interpose" in m.lower() for m in messages),
            f"Expected usage message; got: {messages}",
        )


# ---------------------------------------------------------------------------
# scene status / no args
# ---------------------------------------------------------------------------


class CmdSceneStatusTests(TestCase):
    """``scene`` and ``scene status`` show scene + round status."""

    def setUp(self):
        self.room = _make_room("StatusRoom")
        self.caller, _account = _create_pc_with_account("StatusPc", location=self.room)
        self.caller.msg = MagicMock()

    def test_status_no_scene_message(self):
        """With no active scene, caller is told there's none."""
        messages = _run_cmd(self.caller, "")
        self.assertTrue(
            any("no active scene" in m.lower() for m in messages),
            f"Expected 'no active scene' message; got: {messages}",
        )

    def test_status_bare_status_subcommand(self):
        """``scene status`` behaves the same as bare ``scene``."""
        messages = _run_cmd(self.caller, "status")
        self.assertTrue(
            any("no active scene" in m.lower() for m in messages),
            f"Expected 'no active scene' message; got: {messages}",
        )

    def test_status_shows_scene_name(self):
        """With an active scene, status line contains the scene name."""
        SceneFactory(location=self.room, is_active=True, name="The Great Hall")
        messages = _run_cmd(self.caller, "")
        self.assertTrue(
            any("Great Hall" in m for m in messages),
            f"Expected scene name in messages; got: {messages}",
        )

    def test_status_shows_round_info_when_active(self):
        """With an active round, status line includes round number and mode."""
        scene = SceneFactory(location=self.room, is_active=True, name="Round Test")
        SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=2,
            start_reason=SceneRoundStartReason.OPT_IN,
            mode=SceneRoundMode.STRICT,
            scene=scene,
        )
        messages = _run_cmd(self.caller, "")
        self.assertTrue(
            any("2" in m for m in messages),
            f"Expected round number '2' in messages; got: {messages}",
        )


# ---------------------------------------------------------------------------
# unknown subcommand
# ---------------------------------------------------------------------------


class CmdSceneUnknownTests(TestCase):
    """Unknown subcommand shows a usage/help message."""

    def setUp(self):
        self.room = _make_room("UnknownRoom")
        self.caller, _account = _create_pc_with_account("UnknownPc", location=self.room)
        self.caller.msg = MagicMock()

    def test_unknown_subcommand_shows_usage(self):
        """An unrecognized subcommand emits a usage hint."""
        messages = _run_cmd(self.caller, "frobinate")
        self.assertTrue(
            any("usage" in m.lower() or "scene" in m.lower() for m in messages),
            f"Expected usage message; got: {messages}",
        )

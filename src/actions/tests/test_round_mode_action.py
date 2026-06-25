"""Tests for SetRoundModeAction + StartRoundAction mode override (#1445)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.rounds import SetRoundModeAction, StartRoundAction
from evennia_extensions.factories import CharacterFactory, GMCharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundStartReason
from world.scenes.factories import SceneFactory, SceneOwnerParticipationFactory
from world.scenes.models import SceneRound


def _create_pc_with_account(db_key: str, location=None):
    """Create a PC character with a live roster tenure (non-None active_account).

    Returns (character, sheet, account).
    """
    kwargs = {"db_key": db_key}
    if location is not None:
        kwargs["location"] = location
    char = CharacterFactory(**kwargs)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    return char, sheet, account


def _make_room():
    return ObjectDBFactory(
        db_key="TestRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_active_round(room, mode=SceneRoundMode.POSE_ORDER, scene=None):
    rnd = SceneRound.objects.create(
        room=room,
        status=RoundStatus.DECLARING,
        round_number=1,
        start_reason=SceneRoundStartReason.OPT_IN,
        mode=mode,
    )
    if scene is not None:
        rnd.scene = scene
        rnd.save(update_fields=["scene"])
    return rnd


class SetRoundModeActionGateTests(TestCase):
    """Permission gate tests for SetRoundModeAction."""

    def setUp(self):
        self.room = _make_room()
        self.scene = SceneFactory(location=self.room, is_active=True)

    def test_non_owner_pc_denied(self):
        """A PC who is not a scene owner gets success=False."""
        char, _sheet, _account = _create_pc_with_account("Alice", location=self.room)
        # Not an owner — no SceneOwnerParticipation
        _make_active_round(self.room)
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertFalse(result.success)
        self.assertIn("GM or an owner", result.message)

    def test_non_owner_mode_unchanged(self):
        """When denied, the round's mode is NOT modified."""
        char, _sheet, _account = _create_pc_with_account("Bob", location=self.room)
        rnd = _make_active_round(self.room, mode=SceneRoundMode.POSE_ORDER)
        action = SetRoundModeAction()
        action.run(char, mode=SceneRoundMode.OPEN)
        rnd.refresh_from_db()
        self.assertEqual(rnd.mode, SceneRoundMode.POSE_ORDER)

    def test_owner_can_set_mode(self):
        """A scene co-owner can change the round mode."""
        char, _sheet, account = _create_pc_with_account("Carol", location=self.room)
        SceneOwnerParticipationFactory(scene=self.scene, account=account)
        rnd = _make_active_round(self.room, mode=SceneRoundMode.POSE_ORDER)
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertTrue(result.success)
        rnd.refresh_from_db()
        self.assertEqual(rnd.mode, SceneRoundMode.OPEN)

    def test_owner_set_mode_links_round_scene(self):
        """A successful set_round_mode call links rnd.scene when it was None."""
        char, _sheet, account = _create_pc_with_account("Dana", location=self.room)
        SceneOwnerParticipationFactory(scene=self.scene, account=account)
        rnd = _make_active_round(self.room, mode=SceneRoundMode.POSE_ORDER, scene=None)
        self.assertIsNone(rnd.scene_id)
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertTrue(result.success)
        rnd.refresh_from_db()
        self.assertEqual(rnd.scene_id, self.scene.pk)

    def test_gm_character_can_set_mode(self):
        """A GM (is_story_runner) character can set the round mode without account."""
        gm = GMCharacterFactory(db_key="GMChar", location=self.room)
        rnd = _make_active_round(self.room, mode=SceneRoundMode.POSE_ORDER)
        action = SetRoundModeAction()
        result = action.run(gm, mode=SceneRoundMode.OPEN)
        self.assertTrue(result.success)
        rnd.refresh_from_db()
        self.assertEqual(rnd.mode, SceneRoundMode.OPEN)


class SetRoundModeActionRefusalTests(TestCase):
    """Refusal cases for SetRoundModeAction (no room, no scene, no round)."""

    def test_no_room_returns_failure(self):
        """Actor with no location gets NOT_IN_A_ROOM response."""
        char, _sheet, _account = _create_pc_with_account("Eve")
        char.location = None
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertFalse(result.success)
        self.assertIn("not in a room", result.message.lower())

    def test_no_active_scene_returns_failure(self):
        """Room has no active scene → action refuses before permission check."""
        room = _make_room()
        char, _sheet, _account = _create_pc_with_account("Frank", location=room)
        # No scene created for this room
        _make_active_round(room)
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertFalse(result.success)
        self.assertIn("scene", result.message.lower())

    def test_no_active_round_returns_failure(self):
        """Room has a scene but no active round → action refuses."""
        room = _make_room()
        char, _sheet, account = _create_pc_with_account("Grace", location=room)
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=account)
        # No round created
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertFalse(result.success)
        self.assertIn("round", result.message.lower())

    def test_danger_round_mode_change_refused(self):
        """DANGER rounds cannot have their mode changed (service raises RoundModeError)."""
        room = _make_room()
        char, _sheet, account = _create_pc_with_account("Hank", location=room)
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=account)
        # DANGER round — mode is forced to OPEN at creation; service guards against changes.
        SceneRound.objects.create(
            room=room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.DANGER,
        )
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.POSE_ORDER)
        self.assertFalse(result.success)
        # The service's RoundModeError message surfaces as success=False
        self.assertIn("danger", result.message.lower())

    def test_success_message_names_new_mode(self):
        """Success result mentions the new mode when mode was set."""
        room = _make_room()
        char, _sheet, account = _create_pc_with_account("Iris", location=room)
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=account)
        _make_active_round(room)
        action = SetRoundModeAction()
        result = action.run(char, mode=SceneRoundMode.STRICT)
        self.assertTrue(result.success)
        self.assertIn("strict", result.message.lower())

    def test_knob_only_update_without_mode(self):
        """Updating only a knob (no mode change) → success with generic message."""
        room = _make_room()
        char, _sheet, account = _create_pc_with_account("Jake", location=room)
        scene = SceneFactory(location=room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=account)
        rnd = _make_active_round(room)
        action = SetRoundModeAction()
        result = action.run(char, advance_quorum_pct=75)
        self.assertTrue(result.success)
        rnd.refresh_from_db()
        self.assertEqual(rnd.advance_quorum_pct, 75)


class StartRoundActionModeOverrideTests(TestCase):
    """StartRoundAction with mode/knob override — gated by scene + admin."""

    def setUp(self):
        self.room = _make_room()

    def test_no_override_starts_without_scene(self):
        """No override → start_round works as before (no scene required)."""
        char, _sheet, _account = _create_pc_with_account("Kim", location=self.room)
        action = StartRoundAction()
        result = action.run(char)
        self.assertTrue(result.success)
        rnd = SceneRound.objects.get(room=self.room)
        self.assertEqual(rnd.status, RoundStatus.DECLARING)
        self.assertIsNone(rnd.scene_id)

    def test_override_denied_without_scene(self):
        """Override without an active scene → denied."""
        char, _sheet, _account = _create_pc_with_account("Leo", location=self.room)
        action = StartRoundAction()
        result = action.run(char, mode=SceneRoundMode.STRICT)
        self.assertFalse(result.success)
        self.assertIn("scene", result.message.lower())

    def test_override_denied_for_non_owner(self):
        """Override for a PC who is not a scene owner → denied."""
        char, _sheet, _account = _create_pc_with_account("Mia", location=self.room)
        # Scene exists but Mia is not an owner
        SceneFactory(location=self.room, is_active=True)
        action = StartRoundAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertFalse(result.success)

    def test_override_applied_for_owner(self):
        """Override by a scene owner → round created with the requested mode, scene linked."""
        char, _sheet, account = _create_pc_with_account("Nora", location=self.room)
        scene = SceneFactory(location=self.room, is_active=True)
        SceneOwnerParticipationFactory(scene=scene, account=account)
        action = StartRoundAction()
        result = action.run(char, mode=SceneRoundMode.STRICT, advance_quorum_pct=80)
        self.assertTrue(result.success)
        rnd = SceneRound.objects.get(room=self.room)
        self.assertEqual(rnd.mode, SceneRoundMode.STRICT)
        self.assertEqual(rnd.advance_quorum_pct, 80)
        self.assertEqual(rnd.scene_id, scene.pk)

    def test_override_applied_for_staff_account(self):
        """A staff account can pass overrides — round created with correct mode."""
        char, _sheet, account = _create_pc_with_account("Petra", location=self.room)
        account.is_staff = True
        account.save()
        scene = SceneFactory(location=self.room, is_active=True)
        action = StartRoundAction()
        result = action.run(char, mode=SceneRoundMode.OPEN)
        self.assertTrue(result.success)
        rnd = SceneRound.objects.get(room=self.room)
        self.assertEqual(rnd.mode, SceneRoundMode.OPEN)
        self.assertEqual(rnd.scene_id, scene.pk)

    def test_no_override_defaults_from_config(self):
        """No override → config defaults copied, scene not linked."""
        from world.scenes.models import get_scene_round_defaults_config

        char, _sheet, _account = _create_pc_with_account("Owen", location=self.room)
        cfg = get_scene_round_defaults_config()
        action = StartRoundAction()
        action.run(char)
        rnd = SceneRound.objects.get(room=self.room)
        self.assertEqual(rnd.mode, cfg.default_mode)
        self.assertEqual(rnd.advance_quorum_pct, cfg.advance_quorum_pct)
        self.assertEqual(rnd.max_actions_per_round, cfg.max_actions_per_round)
        self.assertEqual(rnd.per_target_repeat_lock, cfg.per_target_repeat_lock)
        self.assertIsNone(rnd.scene_id)

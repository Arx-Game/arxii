"""E2E telnet journey: scene start → strict mode → guard → force-resolve → finish (#1445).

Drives the full nine-step journey through CmdScene → actions → services,
asserting both DB state and caller messages at each step.

SQLite-compatible: no CHALLENGE/Postgres-only queries touched.

DbHolder trap: all Evennia ObjectDB instances live in setUp, not setUpTestData.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.scene import CmdScene
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus, SceneRoundMode
from world.scenes.models import (
    SceneActionDeclaration,
    SceneParticipation,
    SceneRound,
    SceneRoundParticipant,
)

# Patch broadcast_scene_message at the module finish_scene_full imports it from.
_BROADCAST_PATH = "world.scenes.scene_admin_services.broadcast_scene_message"


def _create_pc_with_account(db_key: str, location=None):
    """Create a PC character with a live roster tenure (non-None active_account).

    Returns (character, account).
    Mirrors the helper in world/scenes/tests/test_scene_admin_services.py.
    """
    kwargs = {"db_key": db_key}
    if location is not None:
        kwargs["location"] = location
    char = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character", **kwargs)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    return char, account


def _run_scene_cmd(caller, args: str) -> list[str]:
    """Invoke CmdScene with the given args string; return all messages sent to caller."""
    caller.msg = MagicMock()
    cmd = CmdScene()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"scene {args}"
    cmd.func()
    return [str(call.args[0]) for call in caller.msg.call_args_list if call.args]


class SceneRoundJourneyTest(TestCase):
    """Nine-step E2E telnet journey for the scene-round mode-gate feature (#1445)."""

    def setUp(self) -> None:
        # DbHolder trap: build all Evennia objects in setUp, never setUpTestData.
        self.room = ObjectDBFactory(
            db_key="JourneyRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        # Owner AND co-owner are both in the room when scene start runs → both become co-owners.
        self.owner, self.owner_account = _create_pc_with_account("JOwner", location=self.room)
        self.coowner, self.coowner_account = _create_pc_with_account("JCoOwner", location=self.room)
        # Latecomer is NOT in the room during scene start; moved in after.
        # They will be a non-owner participant for permission-denial tests.
        self.latecomer, self.latecomer_account = _create_pc_with_account("JLatecomer")

    # ------------------------------------------------------------------
    # Step 1: owner runs `scene start` → scene active, owner is co-owner.
    # ------------------------------------------------------------------

    def test_step_01_scene_start(self) -> None:
        with patch(_BROADCAST_PATH):
            msgs = _run_scene_cmd(self.owner, "start")

        self.assertIn("scene begins", " ".join(msgs).lower())

        from world.scenes.models import Scene

        scene = Scene.objects.filter(location=self.room, is_active=True).first()
        self.assertIsNotNone(scene, "An active scene should exist after 'scene start'")

        # Owner was in the room at start → becomes a co-owner.
        self.assertTrue(
            SceneParticipation.objects.filter(
                scene=scene, account=self.owner_account, is_owner=True
            ).exists(),
            "Owner should be a co-owner",
        )
        # Co-owner was also in the room at start → becomes a co-owner too (key co-ownership design).
        self.assertTrue(
            SceneParticipation.objects.filter(
                scene=scene, account=self.coowner_account, is_owner=True
            ).exists(),
            "Second PC present at scene start should also be a co-owner",
        )

    # ------------------------------------------------------------------
    # Full nine-step journey in one test method.
    # ------------------------------------------------------------------

    def test_full_nine_step_journey(self) -> None:
        """Run all nine steps in sequence; assert DB state + messages at each step."""

        # ---- Step 1: owner scene start --------------------------------
        with patch(_BROADCAST_PATH):
            msgs = _run_scene_cmd(self.owner, "start")

        self.assertIn("scene begins", " ".join(msgs).lower())

        from world.scenes.models import Scene

        scene = Scene.objects.filter(location=self.room, is_active=True).first()
        self.assertIsNotNone(scene)
        # Owner was in the room at start → co-owner.
        self.assertTrue(
            SceneParticipation.objects.filter(
                scene=scene, account=self.owner_account, is_owner=True
            ).exists(),
            "Owner should be a co-owner",
        )
        # Second PC (co-owner) was also in the room at start → co-owner too
        # (key co-ownership design point).
        self.assertTrue(
            SceneParticipation.objects.filter(
                scene=scene, account=self.coowner_account, is_owner=True
            ).exists(),
            "Second PC present at scene start should also be a co-owner",
        )
        # Latecomer was NOT in the room → no participation row yet.
        self.assertFalse(
            SceneParticipation.objects.filter(scene=scene, account=self.latecomer_account).exists(),
            "Latecomer (not present at start) should have no participation row",
        )

        # ---- Step 2: get an active round ------------------------------
        # StartRoundAction is invoked directly here because CmdScene has no round-*start*
        # subcommand — its `round` subcommand only sets mode on an existing round.
        # Using StartRoundAction is intentional, not a bypass of the telnet layer.
        from actions.definitions.rounds import StartRoundAction

        result = StartRoundAction().run(actor=self.owner)
        self.assertTrue(result.success, f"StartRoundAction failed: {result.message}")

        rnd = SceneRound.objects.filter(
            room=self.room, status__in=[RoundStatus.DECLARING, RoundStatus.BETWEEN_ROUNDS]
        ).first()
        self.assertIsNotNone(rnd, "An active SceneRound should exist after StartRoundAction")

        # ---- Step 3: owner scene round strict -------------------------
        msgs = _run_scene_cmd(self.owner, "round strict")
        rnd.refresh_from_db()
        self.assertEqual(
            rnd.mode,
            SceneRoundMode.STRICT,
            f"Round mode should be STRICT; got {rnd.mode}. Messages: {msgs}",
        )

        # ---- Step 4: simulate a pending (non-immediate) declaration ---
        # We create the row directly — the guard only checks for
        # SceneActionDeclaration(is_immediate=False) rows on this round.
        # Using owner's participant row (created by StartRoundAction).
        # Use (or create) the owner's participant row for the pending declaration.
        participant, _ = SceneRoundParticipant.objects.get_or_create(
            scene_round=rnd,
            character_sheet=self.owner.sheet_data,
        )

        pending_decl = SceneActionDeclaration.objects.create(
            scene_round=rnd,
            round_number=rnd.round_number,
            participant=participant,
            is_immediate=False,
            is_pass=True,  # minimal: a deferred pass is enough to trigger the guard
        )

        # ---- Step 5: owner scene round pose_order → REFUSED ----------
        msgs = _run_scene_cmd(self.owner, "round pose_order")
        rnd.refresh_from_db()

        # The guard message is the exact service text from round_services.set_scene_round_mode:
        # "Resolve the current declarations first (force-resolve), then change the mode."
        full_text = " ".join(msgs).lower()
        self.assertIn(
            "force-resolve",
            full_text,
            f"Expected force-resolve guard message; got: {msgs}",
        )
        # Mode must still be STRICT.
        self.assertEqual(
            rnd.mode,
            SceneRoundMode.STRICT,
            "Mode must remain STRICT after guard refusal",
        )

        # ---- Step 6: force-resolve → pending declaration cleared ------
        from actions.definitions.rounds import ForceResolveRoundAction

        resolve_result = ForceResolveRoundAction().run(actor=self.owner)
        self.assertTrue(
            resolve_result.success, f"ForceResolveRoundAction failed: {resolve_result.message}"
        )

        # The round has been resolved; round_number is advanced (BETWEEN_ROUNDS → DECLARING
        # via resolve_scene_round → start_scene_round). Pending declarations for the OLD
        # round_number are deleted.
        self.assertFalse(
            SceneActionDeclaration.objects.filter(pk=pending_decl.pk).exists(),
            "Pending declaration should be deleted after force-resolve",
        )

        # ---- Step 7: owner scene round pose_order → SUCCEEDS ---------
        # After force-resolve, the round may have advanced to a new row.  Re-fetch the
        # genuinely-active round rather than asserting on the possibly-stale `rnd` object.
        from actions.definitions.rounds import _active_round_for_room

        msgs = _run_scene_cmd(self.owner, "round pose_order")
        active_rnd = _active_round_for_room(self.room)
        self.assertIsNotNone(active_rnd, "An active round should still exist after step 7")
        self.assertEqual(
            active_rnd.mode,
            SceneRoundMode.POSE_ORDER,
            f"Mode should be POSE_ORDER after successful change; got {active_rnd.mode}."
            f" Messages: {msgs}",
        )

        # ---- Step 8: non-owner latecomer tries scene round open → REFUSED ----
        # Latecomer arrives AFTER scene started so they are not a co-owner.
        # Persist their location so caller.location is non-None when the action runs.
        self.latecomer.location = self.room
        self.latecomer.save()
        msgs_second = _run_scene_cmd(self.latecomer, "round open")
        active_rnd_after_8 = _active_round_for_room(self.room)
        self.assertIsNotNone(
            active_rnd_after_8, "Active round should survive the non-owner attempt"
        )
        # Mode must not change.
        self.assertEqual(
            active_rnd_after_8.mode,
            SceneRoundMode.POSE_ORDER,
            "Mode should still be POSE_ORDER after non-owner attempt",
        )
        # Denial message must NOT indicate a missing room or missing scene (those would mean
        # the test environment is broken, not that the permission path was exercised).
        denial_text = " ".join(msgs_second).lower()
        self.assertNotIn(
            "not in a room",
            denial_text,
            "Latecomer must have a room location; 'not in a room' means location was not saved",
        )
        self.assertNotIn(
            "no active scene",
            denial_text,
            "'no active scene' indicates wrong path — permission gate should fire first",
        )
        # The refusal must be the permission-denial message from SetRoundModeAction.
        self.assertIn(
            "only the scene",
            denial_text,
            f"Expected permission-denial message for non-owner; got: {msgs_second}",
        )

        # ---- Step 9: owner scene finish → scene.is_active == False ----
        with patch(_BROADCAST_PATH):
            msgs = _run_scene_cmd(self.owner, "finish")

        scene.refresh_from_db()
        self.assertFalse(scene.is_active, "Scene should be inactive after 'scene finish'")
        # The exact success message from FinishSceneAction.execute():
        # "The scene comes to a close."
        self.assertIn(
            "the scene comes to a close",
            " ".join(msgs).lower(),
            f"Expected finish success message; got: {msgs}",
        )

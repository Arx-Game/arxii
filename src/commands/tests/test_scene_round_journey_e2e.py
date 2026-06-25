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
        # Owner is in the room when scene start runs → becomes co-owner.
        self.owner, self.owner_account = _create_pc_with_account("JOwner", location=self.room)
        # Outsider is NOT in the room during scene start; moved in after.
        # They will be a non-owner participant for permission-denial tests.
        self.outsider, self.outsider_account = _create_pc_with_account("JOutsider")

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
        # Outsider was NOT in the room → no participation row yet.
        self.assertFalse(
            SceneParticipation.objects.filter(scene=scene, account=self.outsider_account).exists(),
            "Outsider (not present at start) should have no participation row",
        )

        # ---- Step 2: get an active round ------------------------------
        # Create a DECLARING SceneRound directly (StartRoundAction requires a
        # CharacterSheet which owner has; using the action path to stay on the
        # action seam).
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

        # The guard message should mention force-resolve.
        full_text = " ".join(msgs).lower()
        self.assertIn(
            "force",
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
        # After resolve, a new round with a higher round_number is in DECLARING.
        rnd.refresh_from_db()
        msgs = _run_scene_cmd(self.owner, "round pose_order")
        rnd.refresh_from_db()
        self.assertEqual(
            rnd.mode,
            SceneRoundMode.POSE_ORDER,
            f"Mode should be POSE_ORDER after successful change; got {rnd.mode}. Messages: {msgs}",
        )

        # ---- Step 8: non-owner outsider tries scene round open → REFUSED ----
        # Move outsider into the room so they have a location; they are still not a co-owner.
        self.outsider.location = self.room
        msgs_second = _run_scene_cmd(self.outsider, "round open")
        rnd.refresh_from_db()
        # Mode must not change.
        self.assertEqual(
            rnd.mode,
            SceneRoundMode.POSE_ORDER,
            "Mode should still be POSE_ORDER after non-owner attempt",
        )
        # Caller receives a permission-denial message.
        denial_text = " ".join(msgs_second).lower()
        self.assertTrue(
            any(
                kw in denial_text
                for kw in ("owner", "gm", "only", "permission", "cannot", "can't", "may not")
            ),
            f"Expected permission-denial message for non-owner; got: {msgs_second}",
        )

        # ---- Step 9: owner scene finish → scene.is_active == False ----
        with patch(_BROADCAST_PATH):
            msgs = _run_scene_cmd(self.owner, "finish")

        scene.refresh_from_db()
        self.assertFalse(scene.is_active, "Scene should be inactive after 'scene finish'")
        self.assertIn("close", " ".join(msgs).lower())

"""Telnet E2E: endorsement journey — poses / endorse pose+entry+style (#1340).

Proves that ``CmdPoses`` + ``CmdEndorse`` reach the same endorsement services
the web viewsets use (via the shared Actions).

Two characters:
- ``endorser`` — in the room, has an account with SceneParticipation
- ``endorsee`` — in the room, has a pose + entry pose in the active scene,
  has claimed the test resonance

Pattern: mock only ``character.msg``; drive real commands + real services.
Uses ``setUp`` (not ``setUpTestData``) for ObjectDB-bearing fixtures:
setUpTestData deepcopy machinery cannot copy DbHolder/SharedMemoryModel
instances (copy.Error in CI shard runs — see project memory).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.endorse import CmdEndorse, CmdPoses
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import PoseEndorsement, SceneEntryEndorsement
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, InteractionVisibility, PoseKind
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)


def _make_char_in_room(room: ObjectDB) -> ObjectDB:
    char = CharacterFactory()
    char.location = room
    char.save()
    return char


def _wire_account(sheet):
    """Attach a RosterTenure so account_for_sheet() returns a non-None account."""
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return tenure.player_data.account


class EndorsementJourneyE2ETests(TestCase):
    """CmdPoses + CmdEndorse drive the real endorsement services end-to-end.

    Golden path:
    1. ``poses <endorsee>``              → lists the pose with its #1 position
    2. ``endorse pose <endorsee> resonance=<R>``         → preview (no DB row)
    3. ``endorse pose <endorsee> resonance=<R> confirm`` → creates PoseEndorsement
    4. ``endorse entry <endorsee> resonance=<R>``        → creates SceneEntryEndorsement
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        self.room = ObjectDB.objects.create(
            db_key="EndorseTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        # --- Endorser ---
        self.endorser_char = _make_char_in_room(self.room)
        self.endorser_sheet = CharacterSheetFactory(character=self.endorser_char)
        self.endorser_account = _wire_account(self.endorser_sheet)
        SceneParticipationFactory(scene=self.scene, account=self.endorser_account)

        # --- Endorsee ---
        self.endorsee_char = _make_char_in_room(self.room)
        self.endorsee_sheet = CharacterSheetFactory(character=self.endorsee_char)
        self.endorsee_account = _wire_account(self.endorsee_sheet)
        SceneParticipationFactory(scene=self.scene, account=self.endorsee_account)

        # Resonance claimed by endorsee
        self.resonance = ResonanceFactory(name="TestEmbers")
        CharacterResonanceFactory(character_sheet=self.endorsee_sheet, resonance=self.resonance)

        # A standard pose by endorsee in the scene
        self.pose = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

        # An entry pose (PoseKind.ENTRY) by endorsee in the scene
        self.entry_pose = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
            pose_kind=PoseKind.ENTRY,
        )

        self.endorser_char.msg = MagicMock()

    # ------------------------------------------------------------------

    def _run_cmd(self, cls, args: str) -> MagicMock:
        """Run a command with the endorser as caller; return the msg mock."""
        cmd = cls()
        cmd.caller = self.endorser_char
        cmd.args = args
        cmd.raw_string = f"{cls.key} {args}"
        cmd.func()
        return self.endorser_char.msg

    def test_poses_lists_endorseable_pose(self) -> None:
        """``poses <endorsee>`` shows the standard pose with its position number."""
        endorsee_name = self.endorsee_char.name
        msg_mock = self._run_cmd(CmdPoses, endorsee_name)
        last_call = msg_mock.call_args_list[-1]
        output = last_call[0][0] if last_call[0] else ""
        self.assertIn("#1", output)
        self.assertIn(self.pose.content[:20], output)

    def test_endorse_pose_preview_no_db_row(self) -> None:
        """``endorse pose <char> resonance=<R>`` shows preview; no PoseEndorsement written."""
        endorsee_name = self.endorsee_char.name
        self._run_cmd(CmdEndorse, f"pose {endorsee_name} resonance={self.resonance.name}")
        self.assertEqual(PoseEndorsement.objects.count(), 0)
        last_output = self.endorser_char.msg.call_args_list[-1][0][0]
        self.assertIn("confirm", last_output.lower())

    def test_endorse_pose_confirm_creates_row(self) -> None:
        """``endorse pose <char> resonance=<R> confirm`` creates a PoseEndorsement."""
        endorsee_name = self.endorsee_char.name
        self._run_cmd(
            CmdEndorse,
            f"pose {endorsee_name} resonance={self.resonance.name} confirm",
        )
        self.assertEqual(PoseEndorsement.objects.count(), 1)
        endorsement = PoseEndorsement.objects.get()
        self.assertEqual(endorsement.endorser_sheet, self.endorser_sheet)
        self.assertEqual(endorsement.endorsee_sheet, self.endorsee_sheet)
        self.assertEqual(endorsement.interaction, self.pose)
        self.assertEqual(endorsement.resonance, self.resonance)
        self.assertIsNone(endorsement.settled_at)  # unsettled at creation

    def test_endorse_pose_n_selector(self) -> None:
        """``endorse pose <char> #2 resonance=<R> confirm`` targets the second pose."""
        # pose=1, entry_pose=2 (created after self.pose)
        endorsee_name = self.endorsee_char.name
        self._run_cmd(
            CmdEndorse,
            f"pose {endorsee_name} #2 resonance={self.resonance.name} confirm",
        )
        self.assertEqual(PoseEndorsement.objects.count(), 1)
        endorsement = PoseEndorsement.objects.get()
        self.assertEqual(endorsement.interaction, self.entry_pose)

    def test_endorse_entry_creates_scene_entry_endorsement(self) -> None:
        """``endorse entry <char> resonance=<R>`` creates a SceneEntryEndorsement."""
        endorsee_name = self.endorsee_char.name
        self._run_cmd(
            CmdEndorse,
            f"entry {endorsee_name} resonance={self.resonance.name}",
        )
        self.assertEqual(SceneEntryEndorsement.objects.count(), 1)
        endorsement = SceneEntryEndorsement.objects.get()
        self.assertEqual(endorsement.endorser_sheet, self.endorser_sheet)
        self.assertEqual(endorsement.endorsee_sheet, self.endorsee_sheet)
        self.assertEqual(endorsement.scene, self.scene)

    def test_endorse_duplicate_pose_shows_error(self) -> None:
        """A second ``confirm`` for the same pose shows an error, not an exception."""
        endorsee_name = self.endorsee_char.name
        args = f"pose {endorsee_name} resonance={self.resonance.name} confirm"
        self._run_cmd(CmdEndorse, args)
        self._run_cmd(CmdEndorse, args)  # second attempt
        # Only one endorsement; second attempt sent an error message
        self.assertEqual(PoseEndorsement.objects.count(), 1)
        # CmdEndorse.func() calls self.msg(str(err)) for CommandError — check positional args
        all_calls = self.endorser_char.msg.call_args_list
        all_output = " ".join(str(c[0][0]) for c in all_calls if c[0])
        self.assertIn("already endorsed", all_output.lower())

    def test_poses_no_active_scene_shows_error(self) -> None:
        """``poses`` outside an active scene sends a CommandError message."""
        # Move both characters to a room with no active scene so search succeeds
        # but _get_active_scene returns None.
        empty_room = ObjectDB.objects.create(
            db_key="EmptyRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.endorser_char.location = empty_room
        self.endorser_char.save()
        self.endorsee_char.location = empty_room
        self.endorsee_char.save()
        self.endorser_char.msg.reset_mock()
        cmd = CmdPoses()
        cmd.caller = self.endorser_char
        cmd.args = self.endorsee_char.name
        cmd.raw_string = "poses ..."
        cmd.func()
        all_output = " ".join(str(c[0][0]) for c in self.endorser_char.msg.call_args_list if c[0])
        self.assertIn("no active scene", all_output.lower())

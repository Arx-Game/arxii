"""Tests for BlockContactFlag wiring into communication actions (#2088).

The coded block stops the exact blocked pair; a blocked player reaching the blocker via
*another identity* — through a directed say, whisper, pose, or page — is circumvention.
Not code-prevented (anti-derivation), but flagged for staff review.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from actions.definitions.communication import PoseAction, SayAction, WhisperAction
from commands.evennia_overrides.communication import CmdPage
from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block, BlockContactFlag


class CommunicationContactFlagTests(TestCase):
    """Each communication vector should fire a BlockContactFlag when a blocked player
    contacts the blocker via another identity."""

    def _make_side(self, name: str):
        """Create an account + rostered character with a primary persona + an alt persona."""
        account = AccountFactory(username=name)
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        character = CharacterFactory(db_key=name)
        entry = RosterEntryFactory(character_sheet__character=character)
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        sheet = entry.character_sheet
        primary = sheet.primary_persona
        alt = PersonaFactory(character_sheet=sheet, name=f"{name} Alt")
        # Characters need msg for the action's send_message/record_interaction.
        character.msg = MagicMock()
        character.location = None
        return account, player_data, character, sheet, primary, alt

    def setUp(self) -> None:
        # The blocker side — the person who did the blocking.
        (
            self.blocker_acct,
            self.blocker_pd,
            self.blocker_char,
            self.blocker_sheet,
            self.blocker_face,
            _,
        ) = self._make_side("Blocker")

        # The blocked side — the person who was blocked. Has an alt identity.
        (
            self.blocked_acct,
            self.blocked_pd,
            self.blocked_char,
            self.blocked_sheet,
            self.blocked_face,
            self.blocked_alt,
        ) = self._make_side("Blocked")

        # The blocker blocked the blocked player's main face.
        Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.blocked_pd,
            blocker_persona=self.blocker_face,
            blocked_persona=self.blocked_face,
        )

    def _patch_interaction_recording(self):
        """Patch out the DB-writing interaction recorders (they need a real scene/room)."""
        import actions.definitions.communication as comm_mod

        original_record = comm_mod.record_interaction
        original_whisper = comm_mod.record_whisper_interaction
        original_msg_location = comm_mod.message_location
        original_send_message = comm_mod.send_message
        comm_mod.record_interaction = MagicMock()
        comm_mod.record_whisper_interaction = MagicMock()
        comm_mod.message_location = MagicMock()
        comm_mod.send_message = MagicMock()
        return original_record, original_whisper, original_msg_location, original_send_message

    def _restore_interaction_recording(self, originals):
        import actions.definitions.communication as comm_mod

        (
            comm_mod.record_interaction,
            comm_mod.record_whisper_interaction,
            comm_mod.message_location,
            comm_mod.send_message,
        ) = originals

    # --- Whisper ---

    def test_whisper_from_blocked_alt_fires_flag(self) -> None:
        """A blocked player whispering the blocker via their alt fires a flag."""
        # The blocked player uses their alt to whisper the blocker.
        originals = self._patch_interaction_recording()
        try:
            WhisperAction().execute(
                actor=self.blocked_char,
                context=None,
                target=self.blocker_char,
                text="psst",
            )
        finally:
            self._restore_interaction_recording(originals)

        flag = BlockContactFlag.objects.filter(
            blocked_account_id=self.blocked_acct.pk,
            blocker_account_id=self.blocker_acct.pk,
        ).first()
        assert flag is not None, "Expected a BlockContactFlag for the whisper"

    def test_whisper_when_no_block_produces_no_flag(self) -> None:
        """A whisper between non-blocked pairs produces no flag."""
        _, _, stranger_char, _, _, _ = self._make_side("Stranger")
        originals = self._patch_interaction_recording()
        try:
            WhisperAction().execute(
                actor=stranger_char,
                context=None,
                target=self.blocker_char,
                text="hello",
            )
        finally:
            self._restore_interaction_recording(originals)

        assert BlockContactFlag.objects.count() == 0

    # --- Directed Say ---

    def test_directed_say_from_blocked_alt_fires_flag(self) -> None:
        """A blocked player using a directed say at the blocker fires a flag."""
        originals = self._patch_interaction_recording()
        try:
            SayAction().execute(
                actor=self.blocked_char,
                context=None,
                text="hi",
                targets=[self.blocker_char],
            )
        finally:
            self._restore_interaction_recording(originals)

        assert BlockContactFlag.objects.filter(blocked_account_id=self.blocked_acct.pk).exists()

    def test_room_wide_say_produces_no_flag(self) -> None:
        """A room-wide say (no explicit targets) does not fire a flag."""
        originals = self._patch_interaction_recording()
        try:
            SayAction().execute(
                actor=self.blocked_char,
                context=None,
                text="hi everyone",
                targets=[],
            )
        finally:
            self._restore_interaction_recording(originals)

        assert BlockContactFlag.objects.count() == 0

    # --- Directed Pose ---

    def test_directed_pose_from_blocked_alt_fires_flag(self) -> None:
        """A blocked player using a directed pose at the blocker fires a flag."""
        originals = self._patch_interaction_recording()
        try:
            PoseAction().execute(
                actor=self.blocked_char,
                context=None,
                text="waves at Blocker",
                targets=[self.blocker_char],
            )
        finally:
            self._restore_interaction_recording(originals)

        assert BlockContactFlag.objects.filter(blocked_account_id=self.blocked_acct.pk).exists()

    def test_room_wide_pose_produces_no_flag(self) -> None:
        """A room-wide pose (no explicit targets) does not fire a flag."""
        originals = self._patch_interaction_recording()
        try:
            PoseAction().execute(
                actor=self.blocked_char,
                context=None,
                text="waves",
                targets=[],
            )
        finally:
            self._restore_interaction_recording(originals)

        assert BlockContactFlag.objects.count() == 0

    # --- Dedup ---

    def test_repeated_contact_dedupes_to_one_flag(self) -> None:
        """Multiple contacts in the same scene-less context dedupe to one flag."""
        originals = self._patch_interaction_recording()
        try:
            for _ in range(3):
                WhisperAction().execute(
                    actor=self.blocked_char,
                    context=None,
                    target=self.blocker_char,
                    text="psst",
                )
        finally:
            self._restore_interaction_recording(originals)

        assert (
            BlockContactFlag.objects.filter(
                blocked_account_id=self.blocked_acct.pk,
                blocker_account_id=self.blocker_acct.pk,
            ).count()
            == 1
        )


class PageContactFlagTests(TestCase):
    """Page is OOC (no scene); a blocked player paging the blocker fires a flag."""

    def _make_side(self, name: str):
        account = AccountFactory(username=name)
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        character = CharacterFactory(db_key=name)
        entry = RosterEntryFactory(character_sheet__character=character)
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        sheet = entry.character_sheet
        character.msg = MagicMock()
        return account, player_data, character, sheet

    def setUp(self) -> None:
        self.blocker_acct, self.blocker_pd, self.blocker_char, self.blocker_sheet = self._make_side(
            "Blocker"
        )
        self.blocked_acct, self.blocked_pd, self.blocked_char, self.blocked_sheet = self._make_side(
            "Blocked"
        )

        # The blocker blocked the blocked player.
        Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.blocked_pd,
            blocker_persona=self.blocker_sheet.primary_persona,
            blocked_persona=self.blocked_sheet.primary_persona,
        )

    def _run_page(self, sender_char, target_char) -> None:
        """Invoke CmdPage.func with the sender's puppet set."""
        from unittest.mock import patch

        with patch(
            "commands.evennia_overrides.communication.search.object_search",
            return_value=[target_char],
        ):
            cmd = CmdPage()
            cmd.caller = self.blocked_acct
            cmd.session = MagicMock(puppet=sender_char)
            cmd.args = f"{target_char.db_key}=hello"
            cmd.func()

    def test_page_from_blocked_player_fires_flag(self) -> None:
        """A blocked player paging the blocker fires a flag (scene=None)."""
        self._run_page(self.blocked_char, self.blocker_char)

        flag = BlockContactFlag.objects.filter(
            blocked_account_id=self.blocked_acct.pk,
            blocker_account_id=self.blocker_acct.pk,
        ).first()
        assert flag is not None, "Expected a BlockContactFlag for the page"
        assert flag.scene_id is None, "Page is OOC; scene should be None"

    def test_page_when_no_block_produces_no_flag(self) -> None:
        """A page between non-blocked pairs produces no flag."""
        _, _, stranger_char, _ = self._make_side("Stranger")
        self._run_page(stranger_char, self.blocker_char)

        assert BlockContactFlag.objects.count() == 0

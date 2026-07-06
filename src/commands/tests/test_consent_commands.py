"""Tests for the telnet consent-initiate commands (#1337).

``CmdIntimidate`` is the worked example of ``ConsentRequestCommand``: a thin
telnet shell that resolves the caller's active scene + persona and the named
target's persona, then opens a PENDING ``SceneActionRequest`` via the SAME
``create_action_request`` service the web viewset calls. These tests build a
scene with both characters present (mirroring the consent viewset's persona
wiring) and assert the row lands in PENDING with the right personas.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.consent import CmdAccept, CmdDeny, CmdIntimidate, ConsentRequestCommand
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneActionRequestFactory, SceneFactory


class CmdIntimidateTests(TestCase):
    """Initiator runs ``intimidate <target>``; a PENDING request is created."""

    def setUp(self) -> None:
        # Evennia ObjectDB fixtures must be built in setUp, not setUpTestData:
        # the idmapper's DbHolder is un-deepcopyable, so the classmethod
        # snapshot machinery raises copy.Error (the DbHolder setUpTestData trap).
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.initiator_char = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_char = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        # CharacterSheet is the source of truth; primary_persona is the face.
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.initiator_persona = self.initiator_sheet.primary_persona
        self.target_persona = self.target_sheet.primary_persona
        # The active scene is resolved off the caller's location.
        self.scene = SceneFactory(is_active=True, location=self.room)
        # Bust the per-location active-scene cache (SharedMemory identity map).
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

    def _run(self, caller: object, args: str) -> CmdIntimidate:
        cmd = CmdIntimidate()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"intimidate {args}"
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    def test_intimidate_creates_pending_request(self) -> None:
        cmd = self._run(self.initiator_char, self.target_char.key)

        req = SceneActionRequest.objects.get(initiator_persona=self.initiator_persona)
        self.assertEqual(req.status, ActionRequestStatus.PENDING)
        self.assertEqual(req.target_persona, self.target_persona)
        self.assertEqual(req.action_key, "intimidate")
        self.assertEqual(req.scene, self.scene)
        cmd.caller.msg.assert_called()

    def test_no_args_reports_error_and_creates_nothing(self) -> None:
        cmd = self._run(self.initiator_char, "")

        self.assertFalse(SceneActionRequest.objects.exists())
        cmd.caller.msg.assert_called()

    def test_no_active_scene_reports_error(self) -> None:
        loner = ObjectDBFactory(
            db_key="Cleo",
            db_typeclass_path="typeclasses.characters.Character",
        )
        target = ObjectDBFactory(
            db_key="Dax",
            db_typeclass_path="typeclasses.characters.Character",
            location=loner.location,
        )
        CharacterSheetFactory(character=loner)
        CharacterSheetFactory(character=target)

        cmd = self._run(loner, target.key)

        self.assertFalse(SceneActionRequest.objects.exists())
        cmd.caller.msg.assert_called()

    def test_unknown_target_reports_error(self) -> None:
        cmd = self._run(self.initiator_char, "Nobody")

        self.assertFalse(SceneActionRequest.objects.exists())
        cmd.caller.msg.assert_called()

    def test_action_key_class_attr_drives_request(self) -> None:
        """The base reads ``action_key`` from the subclass — no hardcoding."""
        self.assertEqual(CmdIntimidate.action_key, "intimidate")
        self.assertTrue(issubclass(CmdIntimidate, ConsentRequestCommand))


class RespondCommandTests(TestCase):
    """Defender runs ``accept`` / ``deny``; the pending request is resolved.

    These exercise the thin shell's two jobs — resolving the caller's pending
    ``SceneActionRequest`` and forwarding the right ``ConsentDecision`` to
    ``respond_to_action_request`` (the SAME service the consent viewset calls).
    The deny path lands DENIED via the real service; the accept path's full
    resolution pipeline is the service's own concern (covered in scenes tests),
    so here we assert the command calls the service with ACCEPT.
    """

    def setUp(self) -> None:
        # DbHolder trap: Evennia ObjectDB fixtures must be built in setUp.
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.initiator_char = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_char = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.initiator_persona = self.initiator_sheet.primary_persona
        self.target_persona = self.target_sheet.primary_persona
        self.scene = SceneFactory(is_active=True, location=self.room)

    def _make_pending(self) -> SceneActionRequest:
        return SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            status=ActionRequestStatus.PENDING,
        )

    def _run(self, cmd_cls: type, caller: object, args: str = "") -> object:
        cmd = cmd_cls()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"{cmd_cls.key} {args}".strip()
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    def test_deny_marks_request_denied(self) -> None:
        req = self._make_pending()

        cmd = self._run(CmdDeny, self.target_char)

        req.refresh_from_db()
        self.assertEqual(req.status, ActionRequestStatus.DENIED)
        cmd.caller.msg.assert_called()

    def test_accept_forwards_accept_decision_for_pending_request(self) -> None:
        req = self._make_pending()

        with patch("commands.consent.respond_to_action_request") as respond:
            cmd = self._run(CmdAccept, self.target_char)

        respond.assert_called_once()
        kwargs = respond.call_args.kwargs
        self.assertEqual(kwargs["action_request"], req)
        self.assertEqual(kwargs["decision"], ConsentDecision.ACCEPT)
        cmd.caller.msg.assert_called()

    def test_accept_by_id_arg_resolves_that_request(self) -> None:
        req = self._make_pending()

        with patch("commands.consent.respond_to_action_request") as respond:
            self._run(CmdAccept, self.target_char, args=str(req.pk))

        self.assertEqual(respond.call_args.kwargs["action_request"], req)

    def test_no_pending_request_reports_cleanly(self) -> None:
        with patch("commands.consent.respond_to_action_request") as respond:
            cmd = self._run(CmdAccept, self.target_char)

        respond.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_respond_uses_most_recent_pending_for_caller(self) -> None:
        self._make_pending()
        newest = self._make_pending()

        with patch("commands.consent.respond_to_action_request") as respond:
            self._run(CmdAccept, self.target_char)

        self.assertEqual(respond.call_args.kwargs["action_request"], newest)

    def _run_with_switches(self, cmd_cls: type, caller: object, switches: list[str]) -> object:
        cmd = cmd_cls()
        cmd.caller = caller
        cmd.args = ""
        cmd.switches = switches
        cmd.raw_string = f"{cmd_cls.key}/{'/'.join(switches)}"
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    def test_accept_difficulty_switch_forwards_grade(self) -> None:
        """`accept/hard` forwards difficulty='hard' to the service (#1698)."""
        self._make_pending()
        with patch("commands.consent.respond_to_action_request") as respond:
            self._run_with_switches(CmdAccept, self.target_char, ["hard"])
        self.assertEqual(respond.call_args.kwargs["difficulty"], "hard")

    def test_deny_blacklist_switch_forwards_flag(self) -> None:
        """`deny/blacklist` forwards blacklist_actor=True to the service (#1698)."""
        self._make_pending()
        with patch("commands.consent.respond_to_action_request") as respond:
            self._run_with_switches(CmdDeny, self.target_char, ["blacklist"])
        self.assertTrue(respond.call_args.kwargs["blacklist_actor"])

    def test_accept_does_not_blacklist(self) -> None:
        """The blacklist switch is DENY-only — accept never sets the flag."""
        self._make_pending()
        with patch("commands.consent.respond_to_action_request") as respond:
            self._run_with_switches(CmdAccept, self.target_char, ["blacklist"])
        self.assertFalse(respond.call_args.kwargs["blacklist_actor"])


class AllSocialCommandsRegisteredTests(TestCase):
    """Every social-action singleton maps to a ConsentRequestCommand subclass."""

    def test_all_social_keys_have_commands(self) -> None:
        from commands.consent import (
            CmdDeceive,
            CmdEntrance,
            CmdFlirt,
            CmdPerform,
            CmdPersuade,
            CmdRestoreSense,
        )

        expected = {
            "intimidate": CmdIntimidate,
            "persuade": CmdPersuade,
            "deceive": CmdDeceive,
            "flirt": CmdFlirt,
            "perform": CmdPerform,
            "entrance": CmdEntrance,
            "restore_sense": CmdRestoreSense,
        }
        for action_key, cls in expected.items():
            with self.subTest(action_key=action_key):
                self.assertEqual(cls.action_key, action_key)
                self.assertTrue(issubclass(cls, ConsentRequestCommand))

    def test_ritual_command_has_no_perform_alias(self) -> None:
        from commands.ritual import CmdRitual

        self.assertNotIn("perform", getattr(CmdRitual, "aliases", []))  # noqa: GETATTR_LITERAL


class PullParsingOnConsentCommandsTests(TestCase):
    """``ConsentRequestCommand`` parses ``pull=`` tokens via ``PullParsingMixin`` (#1919).

    Verifies that pull keywords are stripped from the raw args before
    target-name resolution, and that ``beseech=`` is discarded (combat-only).
    """

    def test_extract_pull_keywords_strips_tokens(self) -> None:
        from commands.pull_parsing import PullParsingMixin

        remainder, pull_val, resonance_val, tier, beseech = PullParsingMixin._extract_pull_keywords(
            "Bob pull=My Thread resonance=Fire tier=2"
        )
        self.assertEqual(remainder, "Bob")
        self.assertEqual(pull_val, "My Thread")
        self.assertEqual(resonance_val, "Fire")
        self.assertEqual(tier, 2)
        self.assertEqual(beseech, 0)

    def test_extract_pull_keywords_discards_beseech(self) -> None:
        from commands.pull_parsing import PullParsingMixin

        remainder, pull_val, _resonance, _tier, beseech = PullParsingMixin._extract_pull_keywords(
            "Bob pull=Thread resonance=Fire beseech=5"
        )
        self.assertEqual(remainder, "Bob")
        self.assertEqual(pull_val, "Thread")
        # beseech is extracted (so it doesn't contaminate the target name) but
        # will be discarded by ConsentRequestCommand (always passes beseech_bonus=0).
        self.assertEqual(beseech, 5)

    def test_extract_pull_keywords_no_pull_tokens(self) -> None:
        from commands.pull_parsing import PullParsingMixin

        remainder, pull_val, _resonance, _tier, _beseech = PullParsingMixin._extract_pull_keywords(
            "Bob"
        )
        self.assertEqual(remainder, "Bob")
        self.assertIsNone(pull_val)

    def test_consent_command_inherits_pull_parsing_mixin(self) -> None:
        from commands.consent import ConsentRequestCommand
        from commands.pull_parsing import PullParsingMixin

        self.assertTrue(issubclass(ConsentRequestCommand, PullParsingMixin))

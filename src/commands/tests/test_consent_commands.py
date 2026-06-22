"""Tests for the telnet consent-initiate commands (#1337).

``CmdIntimidate`` is the worked example of ``ConsentRequestCommand``: a thin
telnet shell that resolves the caller's active scene + persona and the named
target's persona, then opens a PENDING ``SceneActionRequest`` via the SAME
``create_action_request`` service the web viewset calls. These tests build a
scene with both characters present (mirroring the consent viewset's persona
wiring) and assert the row lands in PENDING with the right personas.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.consent import CmdIntimidate, ConsentRequestCommand
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory


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

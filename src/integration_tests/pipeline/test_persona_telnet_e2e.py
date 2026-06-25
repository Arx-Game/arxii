"""Telnet E2E: persona switching end-to-end journey (#1347).

Covers three scenarios:
  1. ``persona`` (bare list) renders both personas with the active marker, then
     ``persona Alt Face`` switches via the full telnet path and DB state reflects it.
  2. Web-seam parity: ``dispatch_player_action`` (REGISTRY, ``set_active_persona``)
     reaches identical DB state — proves telnet + web converge on one Action.
  3. A foreign persona (from another character's sheet) is rejected via telnet and
     leaves the active persona unchanged.

setUp uses plain ``TestCase`` (not EvenniaTest) + factories, mirroring
``test_combat_cast_telnet_e2e.py``. ``idmapper_models.flush_cache()`` is called in
setUp to prevent PK-recycling flakiness from prior tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from commands.persona import CmdPersona
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.services import active_persona_for_sheet


def _cmd(character, args=""):
    """Build a ``CmdPersona`` instance wired to *character* with *args*."""
    cmd = CmdPersona()
    cmd.caller = character
    cmd.args = args
    cmd.raw_string = f"persona {args}".strip()
    cmd.cmdname = "persona"
    return cmd


class PersonaTelnetE2ETests(TestCase):
    """Full persona-switching journey from the telnet command.

    Uses setUp (not setUpTestData) for ObjectDB-backed objects: Django's
    setUpTestData deepcopy machinery cannot copy DbHolder / SharedMemoryModel
    instances (would raise copy.Error in CI shard runs — see project memory).
    """

    def setUp(self) -> None:
        # Flush SharedMemoryModel identity-map cache to prevent PK recycling
        # from a prior test leaking stale instances (see project memory).
        idmapper_models.flush_cache()

        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        self.alt = PersonaFactory(
            character_sheet=self.sheet,
            persona_type=PersonaType.ESTABLISHED,
            name="Alt Face",
        )

    def test_telnet_list_then_switch(self) -> None:
        """Bare ``persona`` lists both names + active marker; ``persona Alt Face`` switches."""
        # Step 1: bare listing — both personas visible, active marker present.
        _cmd(self.character).func()

        sent = "\n".join(str(call.args[0]) for call in self.character.msg.call_args_list)
        primary_name = self.sheet.primary_persona.name
        self.assertIn(primary_name, sent, "primary persona should appear in listing")
        self.assertIn("Alt Face", sent, "alt persona should appear in listing")
        self.assertIn(" ◄ active", sent, "active marker should appear in listing")

        self.character.msg.reset_mock()

        # Step 2: switch to alt via telnet.
        _cmd(self.character, "Alt Face").func()

        self.sheet.refresh_from_db()
        self.assertEqual(
            active_persona_for_sheet(self.sheet),
            self.alt,
            "active persona should be 'Alt Face' after switch",
        )
        self.assertEqual(
            self.sheet.active_persona_id,
            self.alt.pk,
            "active_persona_id should match alt pk",
        )

    def test_web_telnet_parity(self) -> None:
        """dispatch_player_action (web seam) reaches the same DB state as telnet.

        1. Switch to alt via telnet.
        2. Revert to primary via the web seam (dispatch_player_action REGISTRY).
        3. Assert DB state reverted — both surfaces mutate through one Action.
        """
        # Step 1: switch to alt via telnet.
        _cmd(self.character, "Alt Face").func()
        self.sheet.refresh_from_db()
        self.assertEqual(
            self.sheet.active_persona_id,
            self.alt.pk,
            "telnet switch to alt should have been applied",
        )

        # Step 2: revert to primary via web seam.
        primary = self.sheet.primary_persona
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="set_active_persona")
        result = dispatch_player_action(self.character, ref, {"persona_id": primary.pk})

        # Step 3: assert DB reverted to primary.
        self.sheet.refresh_from_db()
        self.assertTrue(result.detail.success, "web dispatch should succeed")
        self.assertEqual(
            self.sheet.active_persona_id,
            primary.pk,
            "active persona should be primary after web-seam revert",
        )

    def test_foreign_persona_rejected_via_telnet(self) -> None:
        """A persona from another sheet is rejected; active persona is unchanged.

        ``CmdPersona.func()`` sets ``self._name`` then calls ``super().func()``
        (``DispatchCommand.func()``), which catches ``CommandError`` from
        ``resolve_action_args()`` and sends the message to the caller via
        ``self.msg()`` — no exception propagates to the caller.  This test
        exercises the full real telnet path rather than calling
        ``resolve_action_args()`` directly.
        """
        other_sheet = CharacterSheetFactory()
        foreign_name = other_sheet.primary_persona.name

        primary_pk = self.sheet.primary_persona.pk

        cmd = _cmd(self.character, foreign_name)
        # Full real telnet path — func() must NOT raise; DispatchCommand.func()
        # catches CommandError and routes it to self.msg().
        cmd.func()

        # Caller must have been messaged with the error.
        self.assertTrue(
            self.character.msg.called,
            "msg should have been called with an error after foreign-name rejection",
        )
        sent = " ".join(
            str(call.args[0]) for call in self.character.msg.call_args_list if call.args
        )
        self.assertIn(
            foreign_name,
            sent,
            "error message should mention the unrecognised persona name",
        )

        # DB state unchanged: active persona pk is still the primary's pk.
        self.sheet.refresh_from_db()
        self.assertEqual(
            active_persona_for_sheet(self.sheet).pk,
            primary_pk,
            "active persona pk must be unchanged after rejected switch",
        )

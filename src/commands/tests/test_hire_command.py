"""Tests for the telnet ``hire`` command (#1493)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.npc_services import (
    end_npc_interaction,
    resolve_npc_offer,
    start_npc_interaction,
)
from commands.hire import CmdHire
from evennia_extensions.factories import RoomProfileFactory
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.npc_services.models import NPCRole
from world.scenes.models import Persona


def _make_cmd(args: str) -> CmdHire:
    cmd = CmdHire()
    cmd.caller = MagicMock()
    cmd.caller.session = MagicMock()
    cmd.caller.session.ndb = MagicMock(
        npc_interaction=None,
    )
    cmd.args = args
    cmd.raw_string = f"hire {args}".strip()
    cmd.cmdname = "hire"
    return cmd


class CmdHireRoutingTests(TestCase):
    def test_bare_hire_with_no_session_prints_no_interaction(self):
        cmd = _make_cmd("")
        cmd.func()
        cmd.caller.msg.assert_called_once()
        self.assertIn("No interaction", cmd.caller.msg.call_args.args[0])

    def test_start_subverb_dispatches_start_action(self):
        cmd = _make_cmd("blacksmith")
        role = MagicMock()
        role.pk = 1
        role.name = "blacksmith"
        qs = MagicMock()
        qs.filter.return_value.filter.return_value.first.return_value = role
        result = MagicMock(
            success=True,
            data={"session": MagicMock(role=MagicMock(pk=1, name="blacksmith"))},
        )
        with patch.object(NPCRole, "objects", qs):
            with patch.object(start_npc_interaction, "run", return_value=result) as run:
                with patch.object(cmd, "_show_offers"):
                    cmd.func()
        run.assert_called_once()
        run.assert_called_with(actor=cmd.caller, role_id=1, npc_persona_id=None)

    def test_start_with_persona_clause_dispatches_start_action(self):
        cmd = _make_cmd("blacksmith as Gerald")
        role = MagicMock()
        role.pk = 1
        role.name = "blacksmith"
        qs = MagicMock()
        qs.filter.return_value.filter.return_value.first.return_value = role
        npc_persona = MagicMock(spec=Persona, pk=42)
        cmd.caller.search.return_value = npc_persona
        result = MagicMock(
            success=True,
            data={"session": MagicMock(role=MagicMock(pk=1, name="blacksmith"))},
        )
        with patch.object(NPCRole, "objects", qs):
            with patch.object(start_npc_interaction, "run", return_value=result) as run:
                with patch.object(cmd, "_show_offers"):
                    cmd.func()
        cmd.caller.search.assert_called_once_with("Gerald")
        run.assert_called_once()
        run.assert_called_with(actor=cmd.caller, role_id=1, npc_persona_id=42)

    def test_hire_prefers_co_located_functionary(self):
        """`hire <name>` resolves a Functionary standing in the caller's room (#1766)."""
        profile = RoomProfileFactory()
        functionary = FunctionaryFactory(
            role=NPCRoleFactory(name="Barkeep"), room=profile, name_override="Old Marta"
        )
        cmd = _make_cmd("Old Marta")
        cmd.caller.location = profile.objectdb  # a real room ObjectDB
        result = MagicMock(success=True, data={"session": MagicMock(role=functionary.role)})
        with patch.object(start_npc_interaction, "run", return_value=result) as run:
            with patch.object(cmd, "_show_offers"):
                cmd.func()
        run.assert_called_once_with(
            actor=cmd.caller, role_id=functionary.role.pk, npc_persona_id=None
        )
        # Greeting uses the placement's display name.
        self.assertIn("Old Marta", cmd.caller.msg.call_args.args[0])

    def test_offer_subverb_dispatches_resolve_action(self):
        session = MagicMock(closed=True)
        cmd = _make_cmd("offer 7")
        cmd.caller.session.ndb.npc_interaction = session
        result = MagicMock(
            success=True,
            data={"session": session, "last_result_message": "Done"},
        )
        with patch.object(resolve_npc_offer, "run", return_value=result) as run:
            cmd.func()
        run.assert_called_once()

    def test_end_subverb_dispatches_end_action(self):
        session = MagicMock(closed=False)
        cmd = _make_cmd("end")
        cmd.caller.session.ndb.npc_interaction = session
        result = MagicMock(success=True, data={"session": session})
        with patch.object(end_npc_interaction, "run", return_value=result) as run:
            cmd.func()
        run.assert_called_once()

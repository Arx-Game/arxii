"""Unit + integration tests for ``CmdStage`` — the ``stage <subverb>`` namespace (#2503).

Mirrors ``test_defenses.py``'s shape: parsing/ref/kwargs unit tests with a mocked
caller, plus a full ``func()`` dispatch test with a mocked
``dispatch_player_action``. ``StageCommandEndToEndTests`` additionally drives
the real dispatcher (no mocking) against real fixtures, proving the telnet
command reaches the same ``StagePropAction`` seam as a direct ``action.run()``
call (per the task-5 brief's "telnet command drives the same action" bullet).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.exceptions import CommandError
from commands.gm_props import _SUBVERBS, CmdStage
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemTemplateFactory, ItemTemplatePropertyFactory
from world.items.models import ItemInstance
from world.mechanics.factories import PropertyFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory

_DISPATCH = "commands.command.dispatch_player_action"


def _make_cmd(args: str) -> CmdStage:
    cmd = CmdStage()
    cmd.caller = MagicMock()
    cmd.caller.location = MagicMock()
    cmd.args = args
    cmd.raw_string = f"stage {args}"
    cmd.cmdname = "stage"
    return cmd


class StageCommandParsingTests(TestCase):
    def test_subverb_map_covers_two_ops(self) -> None:
        self.assertEqual(set(_SUBVERBS), {"prop", "property"})

    def test_unknown_subverb_messages_and_does_not_dispatch(self) -> None:
        cmd = _make_cmd("frobnicate")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called()

    def test_bare_stage_shows_usage(self) -> None:
        cmd = _make_cmd("")
        with patch(_DISPATCH) as dispatch:
            cmd.func()
        dispatch.assert_not_called()
        cmd.caller.msg.assert_called_once()
        self.assertIn("Usage:", cmd.caller.msg.call_args.args[0])


class StageCommandRefTests(TestCase):
    def test_prop_ref(self) -> None:
        cmd = _make_cmd("prop Improv Torch")
        cmd._subverb = "prop"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.backend, ActionBackend.REGISTRY)
        self.assertEqual(ref.registry_key, "stage_prop")

    def test_property_ref(self) -> None:
        cmd = _make_cmd("property dark")
        cmd._subverb = "property"
        ref = cmd.resolve_action_ref()
        self.assertEqual(ref.registry_key, "stage_property")


class StageCommandKwargsTests(TestCase):
    def test_prop_resolves_template_name(self) -> None:
        cmd = _make_cmd("prop Improv Torch")
        cmd._subverb = "prop"
        cmd._rest = "Improv Torch"
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"item_template": "Improv Torch"})

    def test_prop_missing_name_raises(self) -> None:
        cmd = _make_cmd("prop")
        cmd._subverb = "prop"
        cmd._rest = ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_property_without_target(self) -> None:
        cmd = _make_cmd("property dark")
        cmd._subverb = "property"
        cmd._rest = "dark"
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs, {"property": "dark"})

    def test_property_with_target(self) -> None:
        cmd = _make_cmd("property sturdy = A Table")
        cmd._subverb = "property"
        cmd._rest = "sturdy = A Table"
        target = MagicMock()
        cmd.search_or_raise = MagicMock(return_value=target)
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["property"], "sturdy")
        self.assertEqual(kwargs["target"], target)
        cmd.search_or_raise.assert_called_once_with("A Table")

    def test_property_missing_name_raises(self) -> None:
        cmd = _make_cmd("property")
        cmd._subverb = "property"
        cmd._rest = ""
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()


class StageCommandDispatchTests(TestCase):
    """Full func() dispatch — mocked dispatch_player_action, asserts kwargs."""

    def test_prop_dispatches_through_func(self) -> None:
        cmd = _make_cmd("prop Improv Torch")
        result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="You conjure a torch into being."),
        )
        with patch(_DISPATCH, return_value=result) as dispatch:
            cmd.func()

        dispatch.assert_called_once()
        _, ref, kwargs = dispatch.call_args.args
        self.assertEqual(ref.registry_key, "stage_prop")
        self.assertEqual(kwargs["item_template"], "Improv Torch")


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    RosterTenureFactory(roster_entry=entry, player_data__account=account, end_date=None)
    return char, entry.character_sheet


class StageCommandEndToEndTests(TestCase):
    """Real dispatch (no mocking) — the telnet command reaches StagePropAction."""

    def setUp(self) -> None:
        self.room = _make_room("StageCmdRoom")
        self.gm_account = AccountFactory(username="stagecmd_gm", is_staff=True)
        self.gm_actor, _ = _make_actor_with_account("stagecmd_gm_actor", self.room, self.gm_account)

        self.scene = SceneFactory(location=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        self.template = ItemTemplateFactory(name="Command Torch")
        self.prop_flammable = PropertyFactory(name="cmd_flammable")
        ItemTemplatePropertyFactory(item_template=self.template, property=self.prop_flammable)

    def test_stage_prop_command_creates_object_in_room(self) -> None:
        cmd = CmdStage()
        cmd.caller = self.gm_actor
        cmd.args = "prop Command Torch"
        cmd.raw_string = "stage prop Command Torch"
        cmd.cmdname = "stage"
        cmd.msg = MagicMock()

        cmd.func()

        instance = ItemInstance.objects.get(template=self.template)
        self.assertIsNotNone(instance.game_object)
        self.assertEqual(instance.game_object.location, self.room)

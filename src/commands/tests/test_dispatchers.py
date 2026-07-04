"""Tests for command → action delegation.

These tests verify that commands correctly parse telnet input and
delegate to their action instances.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.items import EquipAction, TakeOutAction
from actions.definitions.movement import GetAction
from actions.definitions.outfits import ApplyOutfitAction, UndressAction
from actions.definitions.perception import LookAction, LookAtItemAction
from actions.types import ActionResult
from commands.evennia_overrides.communication import CmdPose, CmdSay, CmdWhisper
from commands.evennia_overrides.items import CmdUndress, CmdWear
from commands.evennia_overrides.movement import CmdDrop, CmdGet, CmdGive, CmdHome
from commands.evennia_overrides.perception import CmdInventory, CmdLook
from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
)
from world.roster.factories import RosterEntryFactory


def _make_cmd(cls, caller, args="", obj=None):
    """Create a command instance with caller and args set."""
    cmd = cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd.key} {args}"
    cmd.obj = obj
    cmd.cmdname = cmd.key
    return cmd


class CmdLookTests(TestCase):
    def test_look_at_room(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdLook, caller, args="")
        result = ActionResult(success=True, message="A room")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=room)
        caller.msg.assert_called_with("A room")

    def test_look_at_object(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(db_key="Sword", location=room)
        caller.search = MagicMock(return_value=target)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdLook, caller, args=" Sword")
        result = ActionResult(success=True, message="A sword")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=target)

    def test_look_at_missing_object(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.search = MagicMock(return_value=None)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdLook, caller, args=" missing")
        cmd.func()
        assert caller.msg.call_count >= 1


class CmdLookParserTests(TestCase):
    """Tests for the drilled-form parser on CmdLook."""

    def _make_caller(self, key: str = "ParseAlice"):
        room = ObjectDBFactory(
            db_key=f"ParseRoom_{key}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key=key,
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        return room, caller

    def test_plain_target_uses_look_action(self) -> None:
        room, caller = self._make_caller("PlainAlice")
        target = ObjectDBFactory(db_key="ParseSword", location=room)
        caller.search = MagicMock(return_value=target)
        cmd = _make_cmd(CmdLook, caller, args=" ParseSword")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAction)
        self.assertEqual(kwargs, {"target": target})

    def test_possessive_form_dispatches_look_at_item_action(self) -> None:
        room, caller = self._make_caller("PossAlice")
        bob = ObjectDBFactory(
            db_key="PossBob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.search = MagicMock(return_value=bob)
        cmd = _make_cmd(CmdLook, caller, args=" PossBob's hat")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAtItemAction)
        self.assertEqual(kwargs, {"owner_id": bob.pk, "item_name": "hat"})
        # Search was for the owner name only.
        self.assertEqual(caller.search.call_args_list[0].args[0], "PossBob")

    def test_on_form_dispatches_look_at_item_action(self) -> None:
        room, caller = self._make_caller("OnAlice")
        bob = ObjectDBFactory(
            db_key="OnBob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.search = MagicMock(return_value=bob)
        cmd = _make_cmd(CmdLook, caller, args=" hat on OnBob")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAtItemAction)
        self.assertEqual(kwargs, {"owner_id": bob.pk, "item_name": "hat"})
        self.assertEqual(caller.search.call_args_list[0].args[0], "OnBob")

    def test_in_form_dispatches_look_at_item_action(self) -> None:
        room, caller = self._make_caller("InAlice")
        pouch = ObjectDBFactory(db_key="InPouch", location=room)
        caller.search = MagicMock(return_value=pouch)
        cmd = _make_cmd(CmdLook, caller, args=" coin in InPouch")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAtItemAction)
        self.assertEqual(
            kwargs,
            {"container_id": pouch.pk, "item_name": "coin"},
        )
        self.assertEqual(caller.search.call_args_list[0].args[0], "InPouch")

    def test_possessive_unknown_owner_raises_command_error(self) -> None:
        _room, caller = self._make_caller("GhostAlice")
        caller.search = MagicMock(return_value=None)
        cmd = _make_cmd(CmdLook, caller, args=" ghost's hat")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_apostrophe_object_name_falls_through_to_plain_search(
        self,
    ) -> None:
        """An object literally named ``L'Aurelia's notebook`` should be
        findable when no character ``L'Aurelia`` is present. The
        possessive regex matches (owner=``L'Aurelia``, item=``notebook``),
        owner search fails, parser falls through to plain search.
        """
        room, caller = self._make_caller("ApostAlice")
        notebook = ObjectDBFactory(
            db_key="L'Aurelia's notebook",
            location=room,
        )

        def fake_search(name, *, quiet=False, **_kwargs):
            if name == "L'Aurelia":
                return [] if quiet else None
            if name == "L'Aurelia's notebook":
                return notebook
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search)
        cmd = _make_cmd(CmdLook, caller, args=" L'Aurelia's notebook")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAction)
        self.assertEqual(kwargs, {"target": notebook})

    def test_in_form_unfindable_container_falls_through_to_plain_search(
        self,
    ) -> None:
        """``look bob in armor`` when ``armor`` isn't in the room should
        fall through to a plain search for ``bob in armor`` so the
        intent (look at bob) still works if such an object exists.
        """
        room, caller = self._make_caller("InFallAlice")
        target = ObjectDBFactory(db_key="bob in armor", location=room)

        def fake_search(name, *, quiet=False, **_kwargs):
            if name == "armor":
                return [] if quiet else None
            if name == "bob in armor":
                return target
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search)
        cmd = _make_cmd(CmdLook, caller, args=" bob in armor")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAction)
        self.assertEqual(kwargs, {"target": target})

    def test_possessive_falls_through_when_named_object_exists(self) -> None:
        """An object literally named ``bob's hat`` should be findable
        when no character ``bob`` is present. The possessive regex
        matches first, owner search fails, parser falls through to
        plain search and finds the object.
        """
        room, caller = self._make_caller("HatAlice")
        hat = ObjectDBFactory(db_key="bob's hat", location=room)

        def fake_search(name, *, quiet=False, **_kwargs):
            if name == "bob":
                return [] if quiet else None
            if name == "bob's hat":
                return hat
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search)
        cmd = _make_cmd(CmdLook, caller, args=" bob's hat")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAction)
        self.assertEqual(kwargs, {"target": hat})


class CmdLookParserConcealmentTests(TestCase):
    """#1225 review gap — the drilled owner/container dispatch resolves names via
    Evennia's default (concealment-unaware) ``caller.search``. A concealed-and-
    undetected owner/container must fall through to plain search exactly like a
    nonexistent one, so the two are indistinguishable to the player.
    """

    def _make_caller(self, key: str = "ConcealAlice"):
        room = ObjectDBFactory(
            db_key=f"ConcealRoom_{key}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        roster = RosterEntryFactory()
        caller = roster.character_sheet.character
        caller.location = room
        return room, caller, roster.character_sheet

    def test_possessive_form_falls_through_when_owner_concealed_and_undetected(
        self,
    ) -> None:
        room, caller, _actor_sheet = self._make_caller("ConcealPossAlice")
        shade = ObjectDBFactory(
            db_key="ConcealShade",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=shade, condition=tmpl)

        def fake_search(name, *, quiet=False, **_kwargs):
            if name == "ConcealShade":
                return [shade] if quiet else shade
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search)
        cmd = _make_cmd(CmdLook, caller, args=" ConcealShade's hat")
        # Same failure mode as an unknown owner (test_possessive_unknown_owner_
        # raises_command_error) — falls all the way through to plain search,
        # which also misses, raising the generic not-found error.
        with self.assertRaises(CommandError) as concealed_ctx:
            cmd.resolve_action_args()

        # Strengthened per #1225 final review: assert exact message equality
        # against a genuinely nonexistent owner, not just "raises some error"
        # (mirrors LookActionConcealmentTests's rigor) — the two probes must be
        # byte-identical so a concealed owner is indistinguishable from one
        # that was never there.
        def fake_search_absent(_name, *, quiet=False, **_kwargs):
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search_absent)
        absent_cmd = _make_cmd(CmdLook, caller, args=" ConcealShade's hat")
        with self.assertRaises(CommandError) as absent_ctx:
            absent_cmd.resolve_action_args()

        self.assertEqual(str(concealed_ctx.exception), str(absent_ctx.exception))

    def test_possessive_form_dispatches_when_owner_detected(self) -> None:
        room, caller, actor_sheet = self._make_caller("ConcealDetectAlice")
        shade = ObjectDBFactory(
            db_key="ConcealDetectShade",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=shade, condition=tmpl)
        register_detection(actor_sheet, shade)

        def fake_search(name, *, quiet=False, **_kwargs):
            if name == "ConcealDetectShade":
                return [shade] if quiet else shade
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search)
        cmd = _make_cmd(CmdLook, caller, args=" ConcealDetectShade's hat")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, LookAtItemAction)
        self.assertEqual(kwargs, {"owner_id": shade.pk, "item_name": "hat"})

    def test_in_form_falls_through_when_container_concealed_and_undetected(
        self,
    ) -> None:
        room, caller, _actor_sheet = self._make_caller("ConcealContainerAlice")
        chest = ObjectDBFactory(db_key="ConcealChest", location=room)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=chest, condition=tmpl)

        def fake_search(name, *, quiet=False, **_kwargs):
            if name == "ConcealChest":
                return [chest] if quiet else chest
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search)
        cmd = _make_cmd(CmdLook, caller, args=" coin in ConcealChest")
        with self.assertRaises(CommandError) as concealed_ctx:
            cmd.resolve_action_args()

        # Strengthened per #1225 final review: assert exact message equality
        # against a genuinely nonexistent container (mirrors
        # LookActionConcealmentTests's rigor) — byte-identical, so a concealed
        # container is indistinguishable from one that was never there.
        def fake_search_absent(_name, *, quiet=False, **_kwargs):
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search_absent)
        absent_cmd = _make_cmd(CmdLook, caller, args=" coin in ConcealChest")
        with self.assertRaises(CommandError) as absent_ctx:
            absent_cmd.resolve_action_args()

        self.assertEqual(str(concealed_ctx.exception), str(absent_ctx.exception))


class CmdLookMessageParityTests(TestCase):
    """#1225 final review — the plain-look concealment-gate failure must be
    byte-identical to a genuinely nonexistent probe, exercised through the real
    ``CmdLook`` dispatch path (``resolve_action_args`` -> ``action.run()`` ->
    ``CmdLook._execute``'s message rewrite), NOT a direct ``LookAction().run()``
    call with a pre-resolved target (which bypasses name resolution entirely and
    can't observe this asymmetry — see ``LookActionConcealmentTests`` in
    ``actions/tests/test_actions.py`` for that narrower, still-valid check).

    ``LookAction.execute()`` builds its concealment-gate failure message from the
    resolved object's canonical ``target.key`` — a name the player never typed
    when their probe was a prefix or a different case. ``CmdLook._execute``
    rewrites that message from the caller's own raw ``self.args`` so it matches
    the genuinely-not-found message byte-for-byte.
    """

    def _make_caller(self, key: str = "MsgParityAlice"):
        room = ObjectDBFactory(
            db_key=f"MsgParityRoom_{key}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        roster = RosterEntryFactory()
        caller = roster.character_sheet.character
        caller.location = room
        caller.msg = MagicMock()
        return room, caller

    def test_prefix_case_variant_probe_matches_nonexistent_probe(self) -> None:
        room, caller = self._make_caller()
        shade = ObjectDBFactory(
            db_key="Umbrastalker",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        tmpl = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=shade, condition=tmpl)

        # A lowercase prefix of the concealed character's key — the kind of
        # probe Evennia's default (prefix-matching, case-insensitive)
        # ``search()`` resolves to a real object; the mock stands in for that
        # real resolution (matching this file's existing convention of
        # mocking ``caller.search`` rather than exercising Evennia's search
        # internals directly).
        probe = "umbrastalk"

        def fake_search(name, *, quiet=False, **_kwargs):
            if name.lower() == probe:
                return [shade] if quiet else shade
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search)
        cmd = _make_cmd(CmdLook, caller, args=f" {probe}")
        cmd.func()
        # First call, not the last: the base ArxCommand.func()'s CommandError
        # handler (hit by the genuinely-absent case below) sends the text via
        # self.msg(str(err)) and THEN a second, kwargs-only self.msg(command_error=...)
        # call with no positional args — grabbing the last call (.call_args)
        # would hit that second, argless call instead of the message text.
        concealed_message = caller.msg.call_args_list[0][0][0]

        # Same probe text, but nothing resolves at all — the genuinely-absent case.
        caller.msg.reset_mock()

        def fake_search_absent(_name, *, quiet=False, **_kwargs):
            return [] if quiet else None

        caller.search = MagicMock(side_effect=fake_search_absent)
        absent_cmd = _make_cmd(CmdLook, caller, args=f" {probe}")
        absent_cmd.func()
        absent_message = caller.msg.call_args_list[0][0][0]

        assert concealed_message == absent_message == f"Could not find '{probe}'."


class CmdInventoryTests(TestCase):
    def test_inventory_delegates_to_action(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdInventory, caller)
        result = ActionResult(success=True, message="You are not carrying anything.")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller)


class CmdSayTests(TestCase):
    def test_say_delegates_text(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdSay, caller, args=" hello")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, text="hello")

    def test_say_empty_text_errors(self):
        caller = ObjectDBFactory(db_key="Alice")
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdSay, caller, args="")
        cmd.func()
        assert caller.msg.call_count >= 1


class CmdPoseTests(TestCase):
    def test_pose_delegates_text(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdPose, caller, args=" stretches.")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, text="stretches.")


class CmdWhisperTests(TestCase):
    def test_whisper_parses_target_and_text(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(db_key="Bob", location=room)
        caller.search = MagicMock(return_value=target)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdWhisper, caller, args=" Bob=secret")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=target, text="secret")


class CmdGetTests(TestCase):
    def test_get_resolves_target(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=room)
        caller.search = MagicMock(return_value=item)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Sword")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=item)
        # Plain ``get <item>`` should keep using GetAction.
        assert isinstance(cmd.action, GetAction)

    def test_get_from_container_dispatches_take_out(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        chest = ObjectDBFactory(db_key="Chest", location=room)
        ring = ObjectDBFactory(db_key="Ring", location=chest)
        caller.search = MagicMock(side_effect=[chest, ring])
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Ring from Chest")
        # Patch TakeOutAction.run so the test doesn't run the action body.
        with patch.object(
            TakeOutAction,
            "run",
            return_value=ActionResult(success=True),
        ) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=ring)
        assert isinstance(cmd.action, TakeOutAction)
        # Verify search was called for container, then for item-in-container.
        assert caller.search.call_args_list[0].args[0] == "Chest"
        assert caller.search.call_args_list[1].args[0] == "Ring"
        assert caller.search.call_args_list[1].kwargs.get("location") == chest

    def test_take_alias_from_container_dispatches_take_out(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        chest = ObjectDBFactory(db_key="Chest", location=room)
        ring = ObjectDBFactory(db_key="Ring", location=chest)
        caller.search = MagicMock(side_effect=[chest, ring])
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Ring from Chest")
        # The ``take`` alias resolves to the same CmdGet class — verify by
        # forcing cmdname to the alias.
        cmd.cmdname = "take"
        with patch.object(
            TakeOutAction,
            "run",
            return_value=ActionResult(success=True),
        ) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=ring)
        assert isinstance(cmd.action, TakeOutAction)

    def test_get_from_missing_container_errors(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.search = MagicMock(return_value=None)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGet, caller, args=" Ring from Chest")
        cmd.func()
        assert caller.msg.call_count >= 1


class CmdDropTests(TestCase):
    def test_drop_resolves_from_inventory(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=caller)
        caller.search = MagicMock(return_value=item)
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdDrop, caller, args=" Sword")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=item)


class CmdGiveTests(TestCase):
    def test_give_parses_item_and_recipient(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        item = ObjectDBFactory(db_key="Sword", location=caller)
        recipient = ObjectDBFactory(db_key="Bob", location=room)
        caller.search = MagicMock(side_effect=[item, recipient])
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdGive, caller, args=" Sword to Bob")
        with patch.object(cmd.action, "run", return_value=ActionResult(success=True)) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller, target=item, recipient=recipient)


class CmdHomeTests(TestCase):
    def test_home_delegates(self):
        room = ObjectDBFactory(
            db_key="Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdHome, caller)
        result = ActionResult(success=True, message="You go home.")
        with patch.object(cmd.action, "run", return_value=result) as mock_run:
            cmd.func()
            mock_run.assert_called_once_with(actor=caller)

    def test_home_set_requires_standing(self):
        # home/set on a room you have no owner/tenant standing in is refused (#1514).
        room = ObjectDBFactory(
            db_key="HomeRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="Homeless",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        caller.msg = MagicMock()
        cmd = _make_cmd(CmdHome, caller)
        cmd.switches = [CmdHome.SET_SWITCH]
        cmd.func()
        sent = " ".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)
        assert "own or rent" in sent


class CmdUndressTests(TestCase):
    def test_undress_resolves_with_no_args(self) -> None:
        room = ObjectDBFactory(
            db_key="UndressRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        caller = ObjectDBFactory(
            db_key="UndressAlice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        cmd = _make_cmd(CmdUndress, caller, args="")
        self.assertEqual(cmd.resolve_action_args(), {})
        self.assertIsInstance(cmd.action, UndressAction)


class CmdWearTests(TestCase):
    def _make_character(self, key: str):
        room = ObjectDBFactory(
            db_key=f"WearRoom_{key}",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        character = ObjectDBFactory(
            db_key=f"WearChar_{key}",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        sheet = CharacterSheetFactory(character=character)
        return room, character, sheet

    def test_wear_outfit_name_dispatches_apply_outfit_action(self) -> None:
        """Typing 'wear outfit Court Attire' switches dispatch to ApplyOutfitAction."""
        room, character, sheet = self._make_character("apply")
        wardrobe_template = ItemTemplateFactory(
            name="WearTestWardrobe",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="WearTestWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
            location=room,
        )
        wardrobe = ItemInstanceFactory(template=wardrobe_template, game_object=wardrobe_obj)
        outfit = OutfitFactory(
            character_sheet=sheet,
            wardrobe=wardrobe,
            name="Court Attire",
        )

        cmd = _make_cmd(CmdWear, character, args=f"outfit {outfit.name}")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, ApplyOutfitAction)
        self.assertEqual(kwargs, {"outfit_id": outfit.pk})

    def test_wear_outfit_name_case_insensitive(self) -> None:
        """The 'outfit' prefix and outfit name match case-insensitively."""
        room, character, sheet = self._make_character("case")
        wardrobe_template = ItemTemplateFactory(
            name="CaseWardrobeTpl",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="CaseWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
            location=room,
        )
        wardrobe = ItemInstanceFactory(template=wardrobe_template, game_object=wardrobe_obj)
        outfit = OutfitFactory(
            character_sheet=sheet,
            wardrobe=wardrobe,
            name="Court Attire",
        )

        cmd = _make_cmd(CmdWear, character, args="OUTFIT court attire")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, ApplyOutfitAction)
        self.assertEqual(kwargs, {"outfit_id": outfit.pk})

    def test_wear_outfit_unknown_name_raises_command_error(self) -> None:
        _room, character, _sheet = self._make_character("unknown")
        cmd = _make_cmd(CmdWear, character, args="outfit DoesNotExist")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_wear_item_unchanged(self) -> None:
        """Plain 'wear <item>' still routes to EquipAction."""
        _room, character, _sheet = self._make_character("plain")
        item_obj = ObjectDBFactory(db_key="shirt", location=character)
        character.search = MagicMock(return_value=item_obj)

        cmd = _make_cmd(CmdWear, character, args="shirt")
        kwargs = cmd.resolve_action_args()
        self.assertIsInstance(cmd.action, EquipAction)
        self.assertEqual(kwargs, {"target": item_obj})

    def test_wear_empty_args_raises(self) -> None:
        _room, character, _sheet = self._make_character("empty")
        cmd = _make_cmd(CmdWear, character, args="")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

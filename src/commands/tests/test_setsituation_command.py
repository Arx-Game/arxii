"""setsituation command (#1895) — parse telnet text into SetSituationAction kwargs.

``setsituation find <term>`` (#2127) is covered separately in
``SetSituationFindTests`` below -- it routes to ``FindSituationAction``
instead of ``resolve_action_args()``/``SetSituationAction``.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.default_cmdsets import CharacterCmdSet
from commands.exceptions import CommandError
from commands.setsituation import CmdSetSituation
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, SituationKindFactory
from world.mechanics.factories import SituationTemplateFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class SetSituationParseTests(TestCase):
    def _parse(self, args: str) -> dict:
        cmd = CmdSetSituation()
        cmd.args = args
        return cmd.resolve_action_args()

    def test_name_resolves_to_template_id(self) -> None:
        template = SituationTemplateFactory(name="The Sealed Passage")
        assert self._parse("The Sealed Passage") == {
            "situation_template_id": template.pk,
        }

    def test_id_resolves_to_template_id(self) -> None:
        template = SituationTemplateFactory(name="Ambush Point")
        assert self._parse(str(template.pk)) == {
            "situation_template_id": template.pk,
        }

    def test_missing_args_raises(self) -> None:
        with self.assertRaises(CommandError):
            self._parse("")

    def test_unknown_name_raises(self) -> None:
        with self.assertRaises(CommandError):
            self._parse("No Such Situation")


class CmdSetSituationCmdsetRegistrationTests(TestCase):
    def test_setsituation_command_registered(self) -> None:
        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("setsituation", keys)


def _room(*, db_key: str = "SetSituationFindRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _gm_in_room(room: object, level: str, *, db_key: str) -> object:
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    GMProfileFactory(account=tenure.player_data.account, level=level)
    char.db_account = tenure.player_data.account
    char.msg = MagicMock()
    return char


def _run_cmd(caller: object, args: str) -> list[str]:
    cmd = CmdSetSituation()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"setsituation {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class SetSituationFindTests(TestCase):
    """``setsituation find <term>`` (#2127) -- routes to FindSituationAction."""

    def setUp(self) -> None:
        self.room = _room()
        self.gm_actor = _gm_in_room(self.room, GMLevel.STARTING, db_key="FindGM")

    def test_find_by_template_name(self) -> None:
        template = SituationTemplateFactory(name="The Sunken Archive")
        messages = _run_cmd(self.gm_actor, "find Sunken")
        self.assertTrue(any(template.name in m for m in messages))

    def test_find_by_kind_name(self) -> None:
        SituationKindFactory(name="Chase", minimum_gm_level=GMLevel.STARTING)
        messages = _run_cmd(self.gm_actor, "find Chase")
        self.assertTrue(any("Kind: Chase" in m for m in messages))

    def test_bare_find_lists_catalog(self) -> None:
        template = SituationTemplateFactory(name="Bare Find Template")
        messages = _run_cmd(self.gm_actor, "find")
        self.assertTrue(any(template.name in m for m in messages))

    def test_find_never_instantiates_a_situation(self) -> None:
        from world.mechanics.models import SituationInstance

        SituationTemplateFactory(name="Never Instantiated")
        _run_cmd(self.gm_actor, "find Never")
        self.assertEqual(SituationInstance.objects.count(), 0)

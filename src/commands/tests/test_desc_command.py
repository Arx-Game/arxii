"""Staff ``desc`` writes the description ``look`` reads (#4329).

Evennia's stock ``desc`` set the ``desc`` Attribute, which nothing renders, and
still answered "The description was set on ...". The override sends a room's,
an object's or an exit's text to ``ObjectDisplayData.permanent_description`` and
a character's to its sheet, through the versioned seam.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from commands.default_cmdsets import CharacterCmdSet
from commands.evennia_overrides.builder import CmdDesc, _desc_load, _desc_save
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import ProfileTextVersion


def _permanent_description(obj) -> str:
    display = ObjectDisplayData.objects.filter(object=obj).first()
    return display.permanent_description if display else ""


class DescCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDBFactory(db_key="DescRoom", db_typeclass_path="typeclasses.rooms.Room")
        # Admin passes the default `edit:perm(Admin)` lock. (A superuser's bypass is
        # cached when a session puppets, which a test character never does.)
        cls.staff_account = AccountFactory(username="desc_staff")
        cls.staff_account.permissions.add("Admin")
        cls.staffer = CharacterFactory(db_key="DescStaffer", location=cls.room)
        cls.staffer.db_account = cls.staff_account
        cls.staffer.save()
        cls.player_account = AccountFactory(username="desc_player")
        cls.player = CharacterFactory(db_key="DescPlayer", location=cls.room)
        cls.player.db_account = cls.player_account
        cls.player.save()
        cls.sheet = CharacterSheetFactory(character=cls.player)
        cls.rock = ObjectDBFactory(db_key="DescRock", location=cls.room)

    def _run(self, caller, args: str) -> list[str]:
        cmd = CmdDesc()
        cmd.caller = caller
        cmd.account = caller.account
        cmd.cmdstring = "desc"
        cmd.args = args
        cmd.raw_string = f"desc {args}"
        messages: list[str] = []

        def record(*a, **kw):
            messages.append(a[0] if a else kw.get("text"))

        # The objects are shared across tests through the identity map, so the
        # caller's msg is patched for this call only, never assigned.
        with (
            patch.object(caller, "msg", side_effect=record),
            patch.object(cmd, "msg", side_effect=record),
        ):
            cmd.parse()
            cmd.func()
        return messages

    def test_bare_desc_sets_the_room_look_reads(self):
        messages = self._run(self.staffer, "A grey hall with no windows.")

        assert _permanent_description(self.room) == "A grey hall with no windows."
        state = SceneDataManagerFactory().initialize_state_for_object(self.room)
        assert state.description == "A grey hall with no windows."
        assert self.room.attributes.get("desc") is None
        assert messages == ["The description was set on DescRoom."]

    def test_named_object_gets_its_own_description(self):
        self._run(self.staffer, "DescRock = A rock worn smooth by the river.")

        state = SceneDataManagerFactory().initialize_state_for_object(self.rock)
        assert state.description == "A rock worn smooth by the river."

    def test_telnet_markup_becomes_real_line_breaks(self):
        self._run(self.staffer, "DescRock = First line.%rSecond line.")

        assert _permanent_description(self.rock) == "First line.\nSecond line."

    def test_character_description_goes_to_the_sheet_with_history(self):
        self.sheet.additional_desc = "Tall, with ink-stained fingers."
        self.sheet.save(update_fields=["additional_desc"])

        self._run(self.staffer, "DescPlayer = Tall, with a scar through one brow.")

        self.sheet.refresh_from_db()
        assert self.sheet.additional_desc == "Tall, with a scar through one brow."
        assert _permanent_description(self.player) == ""
        versions = ProfileTextVersion.objects.filter(profile=self.sheet.true_profile).order_by("pk")
        assert [v.text for v in versions] == [
            "Tall, with ink-stained fingers.",
            "Tall, with a scar through one brow.",
        ]
        assert versions.last().edited_by == self.staff_account

    def test_without_permission_nothing_is_written(self):
        messages = self._run(self.player, "DescRock = Mine now.")

        assert _permanent_description(self.rock) == ""
        assert messages == ["You don't have permission to edit the description of DescRock."]

    def test_line_editor_loads_and_saves_the_same_store(self):
        self.staffer.db.evmenu_target = self.rock
        _desc_save(self.staffer, "Edited in the line editor.")

        assert _permanent_description(self.rock) == "Edited in the line editor."
        assert _desc_load(self.staffer) == "Edited in the line editor."

    def test_character_cmdset_carries_this_desc(self):
        matches = [cmd for cmd in CharacterCmdSet().commands if cmd.key == "@desc"]

        assert len(matches) == 1
        assert isinstance(matches[0], CmdDesc)

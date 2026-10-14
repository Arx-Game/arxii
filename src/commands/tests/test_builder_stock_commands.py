"""Staff ``@name``, ``@sethome`` and ``@set .../desc`` write the stores Arx reads (#4338).

Evennia's stock commands each wrote only Evennia's own store (the key, ``home``, the
``desc`` Attribute) and reported success, while ``look``, ``where``, the inventory and
the sheet read somewhere else. The overrides send each write through the service
that owns it; ``@spawn`` and ``@copy`` are gone.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from commands.default_cmdsets import CharacterCmdSet
from commands.evennia_overrides.builder import CmdName, CmdSetAttribute, CmdSetHome
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from evennia_extensions.models import ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.services import _room_display_name
from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.materialize import materialize_item_game_object_in_room
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership, LocationTenancy
from world.locations.services import assign_room_tenant


def _run(command_class, caller, cmdstring: str, args: str) -> list[str]:
    """Parse and run one command as ``caller``; return what it sent back."""
    cmd = command_class()
    cmd.caller = caller
    cmd.account = caller.account
    cmd.cmdstring = cmdstring
    cmd.args = args
    cmd.raw_string = f"{cmdstring} {args}"
    messages: list[str] = []

    def record(*a, **kw):
        messages.append(a[0] if a else kw.get("text"))

    # The objects are shared across tests through the identity map, so msg is
    # patched for this call only, never assigned.
    with (
        patch.object(caller, "msg", side_effect=record),
        patch.object(cmd, "msg", side_effect=record),
    ):
        cmd.parse()
        cmd.func()
    return messages


def _live(obj) -> ObjectDB:
    """The instance the game holds for ``obj``, which a command's search returns and changes."""
    return ObjectDB.objects.get(pk=obj.pk)


def _look_name(obj, looker) -> str:
    """The name ``look`` and the room listing show for ``obj``."""
    return SceneDataManagerFactory().initialize_state_for_object(obj).get_display_name(looker)


class _StaffFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.area = AreaFactory(level=AreaLevel.BUILDING)
        cls.room = RoomProfileFactory(area=cls.area).objectdb
        cls.room.key = "Old Hall"
        # Admin passes the default `control`/`edit` locks. (A superuser's bypass is
        # cached when a session puppets, which a test character never does.)
        cls.staff_account = AccountFactory(username="stock_staff")
        cls.staff_account.permissions.add("Admin")
        cls.staffer = CharacterFactory(db_key="StockStaffer", location=cls.room)
        cls.staffer.db_account = cls.staff_account
        cls.staffer.save()
        cls.player = CharacterFactory(db_key="Oldname", location=cls.room)
        cls.sheet = CharacterSheetFactory(character=cls.player)
        cls.rock = ObjectDBFactory(db_key="StockRock", location=cls.room)

    def setUp(self):
        # Each test reads a copy of the class's objects, while the commands find and
        # change the identity-mapped instance, which keeps a rename or a new home
        # past the previous test's rollback. Reload that instance from the database.
        for obj in (self.room, self.player, self.rock):
            _live(obj).refresh_from_db()


class NameCommandTests(_StaffFixture):
    def test_a_room_rename_reaches_look_and_the_area_path(self):
        ObjectDisplayData.objects.update_or_create(object=self.room, defaults={"longname": ""})

        messages = _run(CmdName, self.staffer, "@name", "here = Lantern Hall")

        self.room.refresh_from_db()
        assert self.room.db_key == "Lantern Hall"
        assert ObjectDisplayData.objects.get(object=self.room).longname == "Lantern Hall"
        assert _room_display_name(self.room) == "Lantern Hall"
        assert messages == ["Object's name changed to 'Lantern Hall'."]

    def test_a_character_rename_moves_the_persona_name_too(self):
        _run(CmdName, self.staffer, "@name", "Oldname = Newname")

        self.sheet.primary_persona.refresh_from_db()
        assert _live(self.player).key == "Newname"
        assert self.sheet.primary_persona.name == "Newname"

    def test_an_item_rename_reaches_look_and_the_inventory(self):
        template = ItemTemplateFactory(name="Plain cup")
        instance = ItemInstanceFactory(template=template)
        cup = materialize_item_game_object_in_room(instance, self.room)

        _run(CmdName, self.staffer, "@name", "Plain cup = Heron cup")

        instance.refresh_from_db()
        assert instance.custom_name == "Heron cup"
        assert instance.display_name == "Heron cup"
        assert _look_name(cup, self.staffer) == "Heron cup"

    def test_a_companion_rename_moves_its_own_name_too(self):
        """``Companion.name`` is what the companion panels show; ``look`` reads the key."""
        companion = CompanionFactory(owner=self.sheet, name="Old Hound")
        hound = ObjectDBFactory(
            db_key="Old Hound",
            db_typeclass_path="typeclasses.companions.CompanionObject",
            location=self.room,
        )
        companion.objectdb = hound
        companion.save(update_fields=["objectdb"])

        _run(CmdName, self.staffer, "@name", "Old Hound = Ember")

        companion.refresh_from_db()
        assert companion.name == "Ember"
        assert _live(hound).key == "Ember"

    def test_any_other_object_keeps_its_longname_in_step(self):
        ObjectDisplayData.objects.update_or_create(
            object=self.rock, defaults={"longname": "A stock rock"}
        )

        _run(CmdName, self.staffer, "@name", "StockRock = Riverstone;stone")

        assert _live(self.rock).key == "Riverstone"
        assert ObjectDisplayData.objects.get(object=self.rock).longname == "Riverstone"
        assert "stone" in _live(self.rock).aliases.all()

    def test_without_permission_nothing_changes(self):
        player_account = AccountFactory(username="stock_player")
        self.player.db_account = player_account
        self.player.save()

        messages = _run(CmdName, self.player, "@name", "StockRock = Mine")

        assert _live(self.rock).key == "StockRock"
        assert messages == ["You don't have the right to edit StockRock."]


class SetHomeCommandTests(_StaffFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.owner = CharacterSheetFactory(character=CharacterFactory()).primary_persona
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=cls.area,
            holder_type=HolderType.PERSONA,
            holder_persona=cls.owner,
        )

    def test_a_character_home_is_their_residence_everywhere(self):
        persona = self.sheet.primary_persona
        assign_room_tenant(persona=self.owner, room=self.room, tenant_persona=persona)

        messages = _run(CmdSetHome, self.staffer, "@sethome", "Oldname = here")

        self.sheet.refresh_from_db()
        assert _live(self.player).home == self.room
        assert self.sheet.current_residence == self.room.room_profile
        assert LocationTenancy.objects.get(tenant_persona=persona).is_primary_home
        assert messages == [f"Oldname's home is now Old Hall, as {persona.name}."]

    def test_a_character_with_no_standing_keeps_their_home(self):
        old_home = _live(self.player).home

        messages = _run(CmdSetHome, self.staffer, "@sethome", "Oldname = here")

        assert _live(self.player).home == old_home
        assert not LocationTenancy.objects.filter(
            tenant_persona=self.sheet.primary_persona
        ).exists()
        assert messages[0].startswith("Oldname's home was not changed: ")

    def test_any_other_object_keeps_evennias_home(self):
        _run(CmdSetHome, self.staffer, "@sethome", "StockRock = here")

        assert _live(self.rock).home == self.room


class SetDescriptionTests(_StaffFixture):
    def _description(self, obj) -> str:
        return SceneDataManagerFactory().initialize_state_for_object(obj).description

    def test_set_desc_writes_what_look_shows(self):
        messages = _run(CmdSetAttribute, self.staffer, "@set", "StockRock/desc = A river rock.")

        assert self._description(self.rock) == "A river rock."
        assert self.rock.attributes.get("desc") is None
        assert messages == ["Set the description of StockRock."]

    def test_a_description_is_stored_as_typed(self):
        """Evennia reads a value as a Python literal; prose keeps its quotes and gets no warning."""
        messages = _run(CmdSetAttribute, self.staffer, "@set", 'StockRock/desc = "Mine," it says.')

        assert self._description(self.rock) == '"Mine," it says.'
        assert messages == ["Set the description of StockRock."]

    def test_a_characters_desc_goes_to_the_sheet(self):
        _run(CmdSetAttribute, self.staffer, "@set", "Oldname/desc = Tall and grey-eyed.")

        self.sheet.refresh_from_db()
        assert self.sheet.additional_desc == "Tall and grey-eyed."
        assert self.player.attributes.get("desc") is None

    def test_viewing_and_clearing_use_the_same_store(self):
        _run(CmdSetAttribute, self.staffer, "@set", "StockRock/desc = A river rock.")

        viewed = _run(CmdSetAttribute, self.staffer, "@set", "StockRock/desc")
        cleared = _run(CmdSetAttribute, self.staffer, "@set", "StockRock/desc =")

        assert viewed == ["Description of StockRock: A river rock."]
        assert cleared == ["Cleared the description of StockRock."]
        assert ObjectDisplayData.objects.get(object=self.rock).permanent_description == ""

    def test_other_attributes_stay_evennia_attributes(self):
        _run(CmdSetAttribute, self.staffer, "@set", "StockRock/weight = 12")

        assert self.rock.attributes.get("weight") == 12

    def test_desc_among_several_attributes_is_refused_not_parsed(self):
        """Evennia's multi-attribute flow reads the value as Python; a description is text."""
        messages = _run(CmdSetAttribute, self.staffer, "@set", 'StockRock/desc/weight = "Hi"')

        assert messages == ["Set desc on its own: set <obj>/desc = <text>"]
        assert self._description(self.rock) != "Hi"
        assert self.rock.attributes.get("weight") is None

    def test_set_edit_desc_opens_the_description_editor(self):
        # A fresh staffer: the editor adds a persistent cmdset to its caller,
        # which must not ride the identity map into other tests.
        editor_staffer = CharacterFactory(db_key="StockEditor", location=self.room)
        editor_staffer.db_account = self.staff_account
        editor_staffer.save()
        _run(CmdSetAttribute, self.staffer, "@set", "StockRock/desc = A river rock.")

        _run(CmdSetAttribute, editor_staffer, "@set", "/edit StockRock/desc")

        editor = editor_staffer.ndb._eveditor
        assert editor.get_buffer() == "A river rock."
        editor.update_buffer("A split rock.")
        with patch.object(editor_staffer, "msg"):
            editor.save_buffer()
        assert self._description(self.rock) == "A split rock."


class StockBuilderCmdsetTests(TestCase):
    def test_the_rewired_commands_are_ours(self):
        commands = {cmd.key: cmd for cmd in CharacterCmdSet().commands}

        assert isinstance(commands["@name"], CmdName)
        assert isinstance(commands["@sethome"], CmdSetHome)
        assert isinstance(commands["@set"], CmdSetAttribute)

    def test_spawn_and_copy_are_gone(self):
        keys = {cmd.key for cmd in CharacterCmdSet().commands}

        assert "@spawn" not in keys
        assert "@copy" not in keys

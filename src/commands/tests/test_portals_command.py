"""Tests for CmdPortalAnchor (#2222)."""

from unittest.mock import patch

from django.test import TestCase

from commands.portals import CmdPortalAnchor
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.models import CharacterPurse
from world.locations.factories import LocationTenancyFactory
from world.magic.factories import PortalAnchorKindFactory
from world.magic.models import PortalAnchor


class CmdPortalAnchorInstallParseTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_key="MirrorRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.room_profile = RoomProfileFactory(objectdb=self.room)
        self.caller = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.caller)
        self.persona = self.sheet.primary_persona
        LocationTenancyFactory(room_profile=self.room_profile, tenant_persona=self.persona)
        CharacterPurse.objects.create(character_sheet=self.sheet, balance=10_000)
        self.kind = PortalAnchorKindFactory(name="Mirror")

    def _make_cmd(self, args, switches):
        cmd = CmdPortalAnchor()
        cmd.caller = self.caller
        cmd.args = args
        cmd.switches = switches
        cmd.raw_string = f"portal/{switches[0]} {args}"
        return cmd

    def test_install_parses_kind_equals_name_and_dispatches(self):
        cmd = self._make_cmd("Mirror=a tall silvered mirror", ["install"])

        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()

        assert mock_msg.called
        message = mock_msg.call_args[0][0]
        assert "install" in message.lower()
        anchor = PortalAnchor.objects.active().get(room_profile=self.room_profile, kind=self.kind)
        assert anchor.name == "a tall silvered mirror"

    def test_install_missing_equals_raises_usage_error(self):
        cmd = self._make_cmd("Mirror", ["install"])

        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()

        assert mock_msg.called
        assert "usage" in mock_msg.call_args[0][0].lower()
        assert not PortalAnchor.objects.active().filter(room_profile=self.room_profile).exists()

"""Telnet +grievance command tests (#1429) — thin over register_secret_grievance."""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.social.grievance import CmdGrievance
from evennia_extensions.factories import AccountFactory
from world.relationships.factories import GrievanceOptionFactory
from world.relationships.models import CharacterRelationship
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.secrets.factories import SecretFactory, SecretVictimFactory
from world.secrets.services import grant_secret_knowledge


class GrievanceCommandTests(TestCase):
    def setUp(self) -> None:
        self.entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=self.entry, player_data=PlayerDataFactory(account=AccountFactory())
        )
        self.caller = self.entry.character_sheet.character
        self.caller.msg = MagicMock()
        self.secret = SecretFactory(content="You poisoned my sister.")
        SecretVictimFactory(
            secret=self.secret,
            organization=None,
            persona=self.entry.character_sheet.primary_persona,
        )
        grant_secret_knowledge(roster_entry=self.entry, secret=self.secret)
        self.option = GrievanceOptionFactory(label="Furious Revelation")

    def _run(self, args: str = "") -> str:
        cmd = CmdGrievance()
        cmd.caller = self.caller
        cmd.args = args
        cmd.switches = []
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.caller.msg.call_args_list if c.args)

    def test_menu_lists_the_grievable_secret_and_options(self) -> None:
        out = self._run("")
        assert "You poisoned my sister." in out
        assert "Furious Revelation" in out

    def test_registering_by_name_applies_the_grievance(self) -> None:
        self._run(f"{self.secret.pk} = Furious Revelation")
        assert CharacterRelationship.objects.filter(
            source=self.entry.character_sheet, target=self.secret.subject_sheet
        ).exists()

    def test_registering_against_a_non_grievable_secret_is_refused(self) -> None:
        other = SecretFactory()  # not a secret this caller is a victim of
        out = self._run(f"{other.pk} = Furious Revelation")
        assert "not a secret you may answer" in out

"""Telnet ``sheet/<section>`` dispatch (#1334+) — the secrets section.

The sheet is the hub; ``sheet/secret`` is the first section, mirroring the web Secrets tab. Your
own secrets show in full; ``sheet/secret <character>`` shows the ones you've learned about them.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.account.sheet import CmdSheet
from world.roster.factories import RosterEntryFactory
from world.secrets.factories import SecretFactory
from world.secrets.services import grant_secret_knowledge


class SheetSecretSectionTests(TestCase):
    def setUp(self) -> None:
        self.viewer_entry = RosterEntryFactory()
        self.viewer_sheet = self.viewer_entry.character_sheet
        self.caller = MagicMock()
        self.caller.is_staff = False
        self.caller.puppet = self.viewer_sheet.character

    def _run(self, args: str = "", switches: list[str] | None = None) -> str:
        cmd = CmdSheet()
        cmd.caller = self.caller
        cmd.args = args
        cmd.switches = switches if switches is not None else ["secret"]
        cmd.func()
        return self.caller.msg.call_args[0][0] if self.caller.msg.called else ""

    def test_secret_section_shows_your_own_secrets(self) -> None:
        SecretFactory(subject_sheet=self.viewer_sheet, content="I am the masked thief.")
        assert "I am the masked thief." in self._run("")

    def test_secret_section_shows_what_you_know_about_another(self) -> None:
        bob_entry = RosterEntryFactory()
        secret = SecretFactory(subject_sheet=bob_entry.character_sheet, content="Bob is a spy.")
        grant_secret_knowledge(roster_entry=self.viewer_entry, secret=secret)
        self.caller.search.return_value = bob_entry.character_sheet.character

        assert "Bob is a spy." in self._run(args="Bob")

    def test_secret_section_without_an_active_character(self) -> None:
        self.caller.puppet = None
        assert "no active character" in self._run("").lower()

    def test_renown_section_shows_fame_and_prestige(self) -> None:
        out = self._run("", switches=["renown"])
        assert "Renown" in out
        assert "Fame:" in out
        assert "Prestige:" in out

    def test_renown_section_lists_society_standing(self) -> None:
        from world.societies.factories import SocietyReputationFactory

        SocietyReputationFactory(
            persona=self.viewer_sheet.primary_persona, society__name="The Compact", value=600
        )
        assert "The Compact" in self._run("", switches=["renown"])

    def test_relationships_section_lists_your_relationships(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.relationships.constants import TrackSign
        from world.relationships.factories import (
            CharacterRelationshipFactory,
            RelationshipTrackFactory,
            RelationshipTrackProgressFactory,
        )

        target = CharacterSheetFactory(character__db_key="Brennan")
        relationship = CharacterRelationshipFactory(source=self.viewer_sheet, target=target)
        RelationshipTrackProgressFactory(
            relationship=relationship,
            track=RelationshipTrackFactory(sign=TrackSign.POSITIVE),
            developed_points=50,
        )
        out = self._run("", switches=["relationship"])
        assert "Brennan" in out
        assert "warm" in out

    def test_relationships_section_empty(self) -> None:
        assert "no relationships" in self._run("", switches=["relationship"]).lower()

    def test_standing_section_lists_org_memberships_and_reputation(self) -> None:
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
            OrganizationReputationFactory,
        )

        persona = self.viewer_sheet.primary_persona
        OrganizationMembershipFactory(
            organization=OrganizationFactory(name="The Wardens"), persona=persona, rank=2
        )
        OrganizationReputationFactory(
            organization=OrganizationFactory(name="The Guild"), persona=persona, value=600
        )
        out = self._run("", switches=["standing"])
        assert "The Wardens" in out
        assert "The Guild" in out
        assert "Honored" in out

    def test_standing_section_empty(self) -> None:
        assert "no organizational standing" in self._run("", switches=["standing"]).lower()

    def test_covenant_section_lists_your_covenant(self) -> None:
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )

        CharacterCovenantRoleFactory(
            character_sheet=self.viewer_sheet,
            covenant=CovenantFactory(name="The Ashen Circle"),
            covenant_role=CovenantRoleFactory(name="Vanguard"),
        )
        out = self._run("", switches=["covenant"])
        assert "The Ashen Circle" in out
        assert "Vanguard" in out

    def test_covenant_section_empty(self) -> None:
        assert "no covenant" in self._run("", switches=["covenant"]).lower()

    def test_titles_section_lists_earned_titles(self) -> None:
        from world.achievements.factories import RewardDefinitionFactory
        from world.achievements.models import CharacterTitle

        reward = RewardDefinitionFactory(name="Hot Flex But Okay")
        CharacterTitle.objects.create(character_sheet=self.viewer_sheet, reward=reward)
        out = self._run("", switches=["titles"])
        assert "Hot Flex But Okay" in out

    def test_titles_section_empty(self) -> None:
        assert "no titles" in self._run("", switches=["titles"]).lower()

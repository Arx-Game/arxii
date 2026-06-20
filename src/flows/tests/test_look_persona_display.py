"""Look / room-contents identity rendering through the persona resolver (#1109).

`CharacterState.get_display_name(looker=...)` is the funnel for telnet room contents, telnet
look-at, and the web room-state list. A character renders as their presented persona, resolved
per viewer: own faces / named-public faces by real name, discovered anonymous faces as the
reveal, undiscovered anonymous faces as a composed sdesc.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.models import Gender
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaDiscoveryFactory, PersonaFactory


def _gender(key):
    return Gender.objects.get_or_create(key=key, defaults={"display_name": key.title()})[0]


class LookPersonaDisplayTests(TestCase):
    def setUp(self) -> None:
        self.context = MagicMock()

    def _played(self, account, *, fake_active=False, gender_key="male"):
        """A tenure'd character; optionally presenting an anonymous mask as its active face."""
        from evennia_extensions.models import PlayerData

        roster_entry = RosterEntryFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        sheet = roster_entry.character_sheet
        sheet.gender = _gender(gender_key)
        character = sheet.character
        character.db_account = account
        character.save()
        if fake_active:
            mask = PersonaFactory(character_sheet=sheet, is_fake_name=True, name="stag mask")
            sheet.active_persona = mask
        sheet.save()
        return character, sheet

    def _state(self, character):
        from flows.object_states.character_state import CharacterState

        return CharacterState(character, context=self.context)

    def test_non_owner_sees_a_masked_character_as_an_sdesc(self) -> None:
        target, _sheet = self._played(AccountFactory(), fake_active=True, gender_key="male")
        looker, _ = self._played(AccountFactory())

        name = self._state(target).get_display_name(looker=self._state(looker))
        assert name == "a man wearing a stag mask"

    def test_owner_account_is_never_restricted_from_their_own_masked_face(self) -> None:
        owner = AccountFactory()
        target, _sheet = self._played(owner, fake_active=True)
        # A second character on the SAME account looking — owns the face, sees it real.
        looker, _ = self._played(owner)

        name = self._state(target).get_display_name(looker=self._state(looker))
        assert name == "stag mask"

    def test_looking_at_your_own_masked_self_shows_the_real_face(self) -> None:
        owner = AccountFactory()
        target, _sheet = self._played(owner, fake_active=True)

        target_state = self._state(target)
        assert target_state.get_display_name(looker=target_state) == "stag mask"

    def test_a_viewer_who_discovered_the_link_sees_the_reveal(self) -> None:
        target, sheet = self._played(AccountFactory(), fake_active=True)
        looker, looker_sheet = self._played(AccountFactory())
        PersonaDiscoveryFactory(
            persona=sheet.active_persona,
            linked_to=sheet.primary_persona,
            discovered_by=looker_sheet,
        )

        name = self._state(target).get_display_name(looker=self._state(looker))
        assert name == f"{sheet.primary_persona.name} (as stag mask)"

    def test_a_normal_unmasked_character_renders_their_name(self) -> None:
        target, sheet = self._played(AccountFactory(), fake_active=False)
        looker, _ = self._played(AccountFactory())

        name = self._state(target).get_display_name(looker=self._state(looker))
        # A named (non-fake) primary persona renders by name, never an sdesc.
        assert "wearing a" not in name
        assert name == sheet.primary_persona.name

    def test_no_sheet_character_falls_back_to_default_name(self) -> None:
        from evennia_extensions.factories import CharacterFactory

        bare = CharacterFactory(db_key="Bare NPC")  # no CharacterSheet
        looker, _ = self._played(AccountFactory())
        assert self._state(bare).get_display_name(looker=self._state(looker)) == "Bare NPC"

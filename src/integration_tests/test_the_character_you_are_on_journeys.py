"""Journeys for the reveal rule's viewer (#4413): what a mask shows is decided for the one
character doing the looking. A player with two characters, where only Maud unmasked Ysmay
(or only Maud's eyes read the mask), meets a stranger while on Hobb, in ``look``, in the
scene feed and on the sheet, and the reveal again on Maud. Staff see through everything."""

from __future__ import annotations

from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import PlayerData
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import DISGUISE_SIGHT_CATEGORY_NAME
from world.mechanics.test_helpers import grant_lever
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry
from world.scenes.factories import PersonaDiscoveryFactory
from world.scenes.models import Persona, Scene

STRANGER = "a person wearing a Stag Mask"
REVEALED = "Stag Mask (Ysmay)"


class TheCharacterYouAreOn(JourneyCase):
    """One player plays Hobb and Maud; Ysmay masks; only Maud can tell who is under it."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.maud = self._second_character_of(self.hobb, "Maud")
        self.player = self.account_of(self.hobb)
        self.telnet(self.ysmay, "persona mask Stag Mask")
        self.telnet(self.ysmay, "scene start")
        self.scene = Scene.objects.active_for_room(self.lantern).first()
        self.telnet(self.ysmay, "pose keeps to the shadows.")
        self.mask = Persona.objects.get(character_sheet=self.ysmay.sheet_data, name="Stag Mask")

    def _second_character_of(self, sibling, name: str):
        """Another character on ``sibling``'s account, standing in the same room, not taken up."""
        character = CharacterFactory(db_key=name, location=sibling.location)
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        player_data = PlayerData.objects.get(account=self.account_of(sibling))
        RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
        character.db_account = player_data.account
        character.save()
        return character

    def _take_up(self, character) -> None:
        """The player switches to ``character``: the web now reads as them (#3412)."""
        player_data = PlayerData.objects.get(account=self.account_of(character))
        set_selected_entry(player_data, character.sheet_data.roster_entry)

    def _meets(self, viewer) -> tuple[str, str, str]:
        """How ``viewer`` meets Ysmay's face: in ``look``, in the scene feed, on her sheet."""
        self._take_up(viewer)
        told = strip_ansi(self.telnet(viewer, "look"))
        look = REVEALED if REVEALED in told else STRANGER if STRANGER in told else told
        client = self.api(self.account_of(viewer))
        feed = client.get(f"/api/interactions/?scene={self.scene.pk}")
        self.assertEqual(feed.status_code, 200, feed.content)
        rows = feed.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        feed_name = next(
            row["persona"]["name"] for row in rows if row["persona"]["id"] == self.mask.pk
        )
        sheet = client.get(f"/api/character-sheets/{self.ysmay.pk}/")
        self.assertEqual(sheet.status_code, 200, sheet.content)
        return look, feed_name, sheet.data["identity"]["name"]

    def test_a_discovery_is_the_discoverers_not_the_accounts(self) -> None:
        PersonaDiscoveryFactory(
            persona=self.mask,
            linked_to=self.ysmay.sheet_data.primary_persona,
            discovered_by=self.maud.sheet_data,
        )
        self.assertEqual(self._meets(self.hobb), (STRANGER, STRANGER, STRANGER))
        self.assertEqual(self._meets(self.maud), (REVEALED, REVEALED, REVEALED))
        # And back on Hobb the player is reminded Hobb does not know.
        self.assertEqual(self._meets(self.hobb), (STRANGER, STRANGER, STRANGER))

    def test_keen_eyes_belong_to_the_one_character(self) -> None:
        grant_lever(self.maud.sheet_data, DISGUISE_SIGHT_CATEGORY_NAME, "mundane", 1)
        self.assertEqual(self._meets(self.hobb), (STRANGER, STRANGER, STRANGER))
        self.assertEqual(self._meets(self.maud), (REVEALED, REVEALED, REVEALED))

    def test_staff_see_through_on_whichever_character(self) -> None:
        self.player.is_staff = True
        self.player.save(update_fields=["is_staff"])
        self.assertEqual(self._meets(self.hobb), (REVEALED, REVEALED, REVEALED))

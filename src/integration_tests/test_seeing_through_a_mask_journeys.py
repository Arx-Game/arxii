"""Journeys for sight through a mask (#4396): a character whose distinction pierces one kind
of disguise reads the name under it in ``look`` and on the sheet, while the other kind, and
everyone without the sight, still meets a stranger."""

from __future__ import annotations

from evennia.utils.ansi import strip_ansi

from integration_tests.harness import JourneyCase
from world.forms.factories import CharacterFormFactory
from world.forms.models import FormType
from world.mechanics.constants import DISGUISE_SIGHT_CATEGORY_NAME
from world.mechanics.test_helpers import grant_lever
from world.scenes.models import PersonaDiscovery
from world.scenes.services import create_mask


class SeeingThroughAMask(JourneyCase):
    """Ysmay masks; Hobb's keen eyes read a plain mask, Maud's warded eyes a glamour."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.maud = self.make_player("Maud", room=self.lantern)
        self.wat = self.make_player("Wat", room=self.lantern)
        grant_lever(self.hobb.sheet_data, DISGUISE_SIGHT_CATEGORY_NAME, "mundane", 1)
        grant_lever(self.maud.sheet_data, DISGUISE_SIGHT_CATEGORY_NAME, "magical", 1)

    def _sheet_name_seen_by(self, viewer) -> str:
        response = self.api(self.account_of(viewer)).get(f"/api/character-sheets/{self.ysmay.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["identity"]["name"]

    def test_keen_eyes_read_a_plain_mask_and_the_sheet_agrees(self) -> None:
        self.telnet(self.ysmay, "persona mask Stag Mask")

        told = strip_ansi(self.telnet(self.hobb, "look"))
        self.assertIn("Stag Mask (Ysmay)", told)
        told = strip_ansi(self.telnet(self.wat, "look"))
        self.assertIn("wearing a Stag Mask", told)
        self.assertNotIn("Ysmay", told)

        self.assertEqual(self._sheet_name_seen_by(self.hobb), "Stag Mask (Ysmay)")
        self.assertEqual(self._sheet_name_seen_by(self.wat), "a person wearing a Stag Mask")
        # Sight is live, not learned: none of those reads wrote a discovery row.
        self.assertEqual(PersonaDiscovery.objects.count(), 0)

    def test_a_glamour_needs_the_other_sight(self) -> None:
        glamour = CharacterFormFactory(character=self.ysmay.sheet_data, form_type=FormType.DISGUISE)
        create_mask(
            self.ysmay.sheet_data, name="Glamour", disguise_form=glamour, disguise_kind="magical"
        )

        told = strip_ansi(self.telnet(self.hobb, "look"))
        self.assertIn("wearing a Glamour", told)
        self.assertNotIn("Ysmay", told)
        told = strip_ansi(self.telnet(self.maud, "look"))
        self.assertIn("Glamour (Ysmay)", told)

        self.assertEqual(self._sheet_name_seen_by(self.hobb), "a person wearing a Glamour")
        self.assertEqual(self._sheet_name_seen_by(self.maud), "Glamour (Ysmay)")
        self.assertEqual(PersonaDiscovery.objects.count(), 0)

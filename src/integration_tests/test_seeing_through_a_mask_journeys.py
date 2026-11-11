"""Journeys for sight through a mask (#4396): a character whose distinction pierces one kind
of disguise reads the name under it in ``look`` and on the sheet, while the other kind, and
everyone without the sight, still meets a stranger."""

from __future__ import annotations

from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.areas.positioning.factories import ObjectPositionFactory, PositionFactory
from world.forms.factories import CharacterFormFactory
from world.forms.models import FormType
from world.mechanics.constants import DISGUISE_SIGHT_CATEGORY_NAME
from world.mechanics.test_helpers import grant_lever
from world.scenes.factories import SceneParticipationFactory
from world.scenes.models import Persona, PersonaDiscovery, Scene
from world.scenes.services import create_mask, record_persona_discovery


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


class AMaskInTheScenesPersonaList(JourneyCase):
    """Ysmay poses barefaced, then masks and poses again; the scene's persona list ties the
    mask to her only for Ysmay, staff and Hobb, who has uncovered it in play (#4888)."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.wat = self.make_player("Wat", room=self.lantern)
        ObjectPositionFactory(
            objectdb=self.ysmay, position=PositionFactory(room=self.lantern, name="Hearth")
        )
        self.telnet(self.ysmay, "scene start")
        self.telnet(self.ysmay, "pose warms her hands.")
        self.telnet(self.wat, "pose nods.")
        self.telnet(self.ysmay, "persona mask Stag Mask")
        self.telnet(self.ysmay, "pose watches the door.")
        self.scene = Scene.objects.get()
        self.mask = Persona.objects.get(name="Stag Mask")
        self.face = self.ysmay.sheet_data.primary_persona

    def _scene_personas(self, account) -> dict[str, dict]:
        response = self.api(account).get(f"/api/scenes/{self.scene.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.positions = {
            row["persona_id"]: row["position"] for row in response.data["persona_positions"]
        }
        return {row["name"]: row for row in response.data["personas"]}

    def _listed(self, account, query: str) -> dict[str, dict]:
        response = self.api(account).get(f"/api/personas/?{query}")
        self.assertEqual(response.status_code, 200, response.content)
        return {row["name"]: row for row in response.data["results"]}

    def test_a_stranger_sees_the_mask_with_nothing_tying_it_to_her(self) -> None:
        wat = self.account_of(self.wat)
        personas = self._scene_personas(wat)
        self.assertIsNone(personas["Stag Mask"]["character_sheet"])
        self.assertIsNone(personas["Stag Mask"]["roster_entry"])
        # Her barefaced face is unchanged, and so is Wat's own.
        self.assertEqual(personas["Ysmay"]["character_sheet"], self.ysmay.pk)
        self.assertEqual(personas["Ysmay"]["roster_entry"]["name"], "Ysmay")
        self.assertEqual(personas["Wat"]["character_sheet"], self.wat.pk)
        # She stands at the hearth as the mask; her own face stands nowhere beside it.
        self.assertEqual(self.positions[self.mask.pk]["name"], "Hearth")
        self.assertIsNone(self.positions[self.face.pk])

        listed = self._listed(wat, f"scene={self.scene.pk}")
        self.assertIsNone(listed["Stag Mask"]["character_sheet"])
        self.assertEqual(listed["Ysmay"]["character_sheet"], self.ysmay.pk)
        # Asking for her faces by character does not hand him the mask.
        self.assertEqual(set(self._listed(wat, f"character_sheet={self.ysmay.pk}")), {"Ysmay"})
        self.assertEqual(set(self._listed(wat, f"character={self.ysmay.pk}")), {"Ysmay"})

    def test_she_staff_and_the_one_who_uncovered_it_see_the_link(self) -> None:
        staff = AccountFactory(is_staff=True)
        record_persona_discovery(self.mask, self.face, self.hobb.sheet_data)
        for account in (self.account_of(self.ysmay), staff, self.account_of(self.hobb)):
            with self.subTest(account=account.username):
                personas = self._scene_personas(account)
                self.assertEqual(personas["Stag Mask"]["character_sheet"], self.ysmay.pk)
                self.assertEqual(personas["Stag Mask"]["roster_entry"]["name"], "Ysmay")
                listed = self._listed(account, f"scene={self.scene.pk}")
                self.assertEqual(listed["Stag Mask"]["character_sheet"], self.ysmay.pk)
        # Her own faces by character include the mask, for her and for staff.
        for account in (self.account_of(self.ysmay), staff):
            with self.subTest(account=account.username):
                listed = self._listed(account, f"character_sheet={self.ysmay.pk}")
                self.assertEqual(set(listed), {"Ysmay", "Stag Mask"})

    def test_the_scenes_gm_sees_the_link(self) -> None:
        gm = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=gm, is_gm=True)
        personas = self._scene_personas(gm)
        self.assertEqual(personas["Stag Mask"]["character_sheet"], self.ysmay.pk)

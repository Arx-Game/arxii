"""Journeys behind the GM's NPC form (#4418): place an NPC in a scene, save a template,
pick what works on an NPC, and set how its name shows titles."""

from __future__ import annotations

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory, seed_default_gm_level_caps
from world.npc_services.models import PersonalityTrait
from world.roster.models import RosterEntry
from world.roster.services.npc_lending import answer_loan, offer_npc
from world.scenes.factories import SceneFactory, SceneParticipationFactory

CAST_LIST = "/api/scenes/{}/cast-list/"
NPCS = "/api/roster/npcs/"
TRAITS = "/api/npc-services/personality-traits/"


class TheNpcFormsBackend(JourneyCase):
    """Ravenna, a JUNIOR GM in her study, runs the siege at Low Gate; Ilsa is a Guide."""

    def setUp(self) -> None:
        super().setUp()
        seed_default_gm_level_caps()
        self.gate = self.make_room("Low Gate")
        self.study = self.make_room("Ravenna's Study")
        self.ravenna = self.make_player("Ravenna", room=self.study)
        self.gm = self.account_of(self.ravenna)
        GMProfileFactory(account=self.gm, level=GMLevel.JUNIOR)
        self.ilsa = self.make_player("Ilsa", room=self.gate)
        self.guide = self.account_of(self.ilsa)
        GuideProfileFactory(account=self.guide)
        self.scene = SceneFactory(room=self.gate, name="The Siege at Low Gate")
        SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True, is_owner=True)

    def _mint(self, name: str, **extra) -> RosterEntry:
        minted = self.web(self.ravenna, "mint_story_npc", name=name, description="Grey.", **extra)
        self.assertTrue(minted.detail.success, minted.detail.message)
        return RosterEntry.objects.get(pk=minted.detail.data["roster_entry_id"])

    def _place(self, character, entry: RosterEntry):
        return self.web(
            character, "place_npc_in_scene", roster_entry_id=entry.pk, scene_id=self.scene.pk
        )

    def _cast_names(self) -> list[str]:
        response = self.api(self.gm).get(CAST_LIST.format(self.scene.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [row["name"] for row in response.json()]

    def test_a_minted_npc_placed_in_the_scene_joins_the_cast(self) -> None:
        vael = self._mint("Captain Vael")
        self.assertNotIn("Captain Vael", self._cast_names())
        placed = self._place(self.ravenna, vael)
        self.assertTrue(placed.detail.success, placed.detail.message)
        self.assertEqual(vael.character_sheet.character.location, self.gate)
        self.assertIn("Captain Vael", self._cast_names())

    def test_placing_is_refused_for_others_lent_npcs_and_non_npcs(self) -> None:
        vael = self._mint("Captain Vael")
        vael_char = vael.character_sheet.character
        start = vael_char.location

        # A second GM runs the scene too, but Vael is not theirs.
        osk = self.make_player("Osk", room=self.study)
        GMProfileFactory(account=self.account_of(osk), level=GMLevel.JUNIOR)
        SceneParticipationFactory(scene=self.scene, account=self.account_of(osk), is_gm=True)
        mine = self._place(osk, vael).detail
        self.assertFalse(mine.success)
        self.assertEqual(mine.message, "That NPC isn't yours to place.")

        # Lent to Ilsa, Vael stands where she plays him.
        loan = offer_npc(entry=vael, guide=self.guide, scene=self.scene, by=self.gm)
        answer_loan(loan=loan, accept=True, by=self.guide)
        lent = self._place(self.ravenna, vael).detail
        self.assertFalse(lent.success)
        self.assertEqual(lent.message, "That NPC is lent to someone else right now.")

        # Ilsa is a player character, not a story NPC.
        ilsa_entry = self.ilsa.sheet_data.roster_entry
        pc = self._place(self.ravenna, ilsa_entry).detail
        self.assertFalse(pc.success)
        self.assertEqual(pc.message, "Only a story NPC can be placed in a scene.")

        vael_char.refresh_from_db()
        self.assertEqual(vael_char.location, start)
        self.assertNotIn("Captain Vael", self._cast_names())

    def test_an_at_cap_gm_still_saves_a_template(self) -> None:
        self._mint("Captain Vael")
        self._mint("Sergeant Rook")
        refused = self.web(self.ravenna, "mint_story_npc", name="Corporal Brann", description="")
        self.assertFalse(refused.detail.success)

        template = self._mint("Watch Officer", as_template="true")
        self.assertTrue(template.story_npc_settings.is_template)
        self.assertIsNone(template.current_tenure)

    def test_gms_and_guides_list_active_traits(self) -> None:
        persuasion = CheckTypeFactory(name="Persuasion")
        PersonalityTrait.objects.create(
            name="Loves flattery", description="Warms to praise.", eased_check=persuasion
        )
        PersonalityTrait.objects.create(name="Hates bells", description="Flavor.")
        PersonalityTrait.objects.create(name="Retired trait", is_active=False)

        response = self.api(self.guide).get(TRAITS)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rows = response.json()["results"]
        self.assertEqual(
            rows,
            [
                {
                    "id": rows[0]["id"],
                    "name": "Hates bells",
                    "description": "Flavor.",
                    "eased_check": None,
                },
                {
                    "id": rows[1]["id"],
                    "name": "Loves flattery",
                    "description": "Warms to praise.",
                    "eased_check": "Persuasion",
                },
            ],
        )
        searched = self.api(self.gm).get(TRAITS, {"name": "flatter"}).json()["results"]
        self.assertEqual([row["name"] for row in searched], ["Loves flattery"])

        player = self.make_player("Ysmay", room=self.gate)
        refused = self.api(self.account_of(player)).get(TRAITS)
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)

    def test_the_owner_sets_how_titles_trail_the_npcs_name(self) -> None:
        vael = self._mint("Captain Vael")
        url = f"{NPCS}{vael.pk}/"
        patched = self.api(self.gm).patch(url, {"title": "primary"}, format="json")
        self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)
        self.assertEqual(patched.json()["title"], "primary")
        persona = vael.character_sheet.primary_persona
        persona.refresh_from_db()
        self.assertEqual(persona.title_suffix, "primary")

        refused = self.api(self.guide).patch(url, {"title": "all"}, format="json")
        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
        persona.refresh_from_db()
        self.assertEqual(persona.title_suffix, "primary")

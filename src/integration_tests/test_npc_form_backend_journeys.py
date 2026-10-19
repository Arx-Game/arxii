"""Journeys behind the GM's NPC form (#4418): place an NPC in a scene, save a template,
and pick what works on an NPC."""

from __future__ import annotations

from functools import partial
from unittest.mock import Mock, patch

import evennia
from evennia.server.serversession import ServerSession
from rest_framework import status

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory, seed_default_gm_level_caps
from world.npc_services.models import PersonalityTrait
from world.roster.factories import (
    NPCPresetSkillLineFactory,
    NPCPresetTraitLineFactory,
    NPCStatlinePresetFactory,
)
from world.roster.models import RosterEntry
from world.roster.services.npc_lending import answer_loan, offer_npc
from world.roster.services.npc_placement import NOT_YOURS_MESSAGE
from world.scenes.factories import SceneFactory, SceneParticipationFactory

CAST_LIST = "/api/scenes/{}/cast-list/"
NPCS = "/api/roster/npcs/"
TRAITS = "/api/npc-services/personality-traits/"
PRESETS = "/api/roster/npc-presets/"


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

    def test_the_form_lists_stat_blocks_with_their_lines(self) -> None:
        # #4418 bug 7: the list was a 500, so the form's Stat block picker was empty.
        guard = NPCStatlinePresetFactory(name="Gate guard", description="A spear and a shield.")
        strength = NPCPresetTraitLineFactory(preset=guard, display_value=3)
        brawl = NPCPresetSkillLineFactory(preset=guard, value=25)

        response = self.api(self.gm).get(PRESETS)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(
            response.json()["results"],
            [
                {
                    "id": guard.pk,
                    "name": "Gate guard",
                    "description": "A spear and a shield.",
                    "trait_lines": [{"trait_name": strength.trait.name, "display_value": 3}],
                    "skill_lines": [{"skill_name": brawl.skill.name, "value": 25}],
                }
            ],
        )

    # -- placing, more cases --------------------------------------------------

    def _signed_in(self, character, sessid: int) -> ServerSession:
        """A telnet session signed in as ``character``'s account; lines typed as
        ``character`` arrive on it (the harness's ``telnet`` passes no session)."""
        handler = evennia.SESSION_HANDLER
        for name in ("data_out", "disconnect"):
            patcher = patch.object(handler, name, Mock())
            patcher.start()
            self.addCleanup(patcher.stop)
        dummy = ServerSession()
        dummy.init_session("telnet", ("localhost", "testmode"), handler)
        dummy.sessid = sessid
        handler.portal_connect(dummy.get_sync_data())
        session = handler.session_from_sessid(sessid)
        self.addCleanup(handler.pop, sessid, None)
        handler.login(session, self.account_of(character), testmode=True)
        character.execute_cmd = partial(type(character).execute_cmd, character, session=session)
        self.addCleanup(character.__dict__.pop, "execute_cmd", None)
        return session

    def test_placing_an_npc_its_owner_is_playing_moves_the_puppet(self) -> None:
        vael = self._mint("Captain Vael")
        vael_char = vael.character_sheet.character
        session = self._signed_in(self.ravenna, sessid=16201)
        told = self.telnet(self.ravenna, "@ic Captain Vael")
        self.assertIn("Now controlling Captain Vael.", told)
        self.assertIs(session.puppet, vael_char)
        self.watch(vael_char)

        placed = self._place(self.ravenna, vael)
        self.assertTrue(placed.detail.success, placed.detail.message)
        self.assertEqual(vael_char.location, self.gate)
        # The move sent the puppet a room-state frame for Low Gate.
        frames = [
            kwargs["room_state"][1]
            for _args, kwargs in self.mailbox(vael_char).calls
            if "room_state" in kwargs
        ]
        self.assertTrue(frames)
        self.assertEqual(frames[-1]["room"]["name"], "Low Gate")

    def test_a_template_ended_scene_or_unknown_npc_is_refused(self) -> None:
        template = self._mint("Watch Officer", as_template=True)
        refused = self._place(self.ravenna, template).detail
        self.assertFalse(refused.success)
        self.assertEqual(refused.message, "A template can't be placed in a scene.")

        unknown = self.web(
            self.ravenna, "place_npc_in_scene", roster_entry_id=999999, scene_id=self.scene.pk
        ).detail
        self.assertFalse(unknown.success)
        self.assertEqual(unknown.message, "No such NPC.")

        vael = self._mint("Captain Vael")
        self.scene.finish_scene()
        ended = self._place(self.ravenna, vael).detail
        self.assertFalse(ended.success)
        self.assertEqual(ended.message, "That scene has ended.")

    def test_staff_place_anyones_npc(self) -> None:
        vael = self._mint("Captain Vael")
        warden = self.make_player("Warden", room=self.study)
        staff = self.account_of(warden)
        staff.is_staff = True
        staff.save()
        placed = self._place(warden, vael)
        self.assertTrue(placed.detail.success, placed.detail.message)
        self.assertNotEqual(placed.detail.message, NOT_YOURS_MESSAGE)
        self.assertIn("Captain Vael", self._cast_names())

    # -- the NPC detail shows what the NPC already has ------------------------

    def test_the_detail_lists_copied_preferences_and_authored_regard(self) -> None:
        flattery = PersonalityTrait.objects.create(name="Loves flattery")
        bells = PersonalityTrait.objects.create(name="Hates bells")
        rook = self._mint("Sergeant Rook")
        vael = self._mint("Captain Vael")
        client = self.api(self.gm)
        prefs = client.put(
            f"{NPCS}{rook.pk}/preferences/",
            {
                "preferences": [
                    {"trait": flattery.pk, "valence": "likes"},
                    {"trait": bells.pk, "valence": "dislikes"},
                ]
            },
            format="json",
        )
        self.assertEqual(prefs.status_code, status.HTTP_200_OK, prefs.data)
        copied = client.post(
            f"{NPCS}{vael.pk}/copy-section/",
            {"source_entry": rook.pk, "section": "preferences"},
            format="json",
        )
        self.assertEqual(copied.status_code, status.HTTP_200_OK, copied.data)
        ysmay = self.make_player("Ysmay", room=self.gate)
        ysmay_persona = ysmay.sheet_data.primary_persona
        regard = client.put(
            f"{NPCS}{vael.pk}/regard/",
            {
                "target_type": "persona",
                "target_id": ysmay_persona.pk,
                "value": 20,
                "reason": "Held the gate.",
            },
            format="json",
        )
        self.assertEqual(regard.status_code, status.HTTP_200_OK, regard.data)

        detail = client.get(f"{NPCS}{vael.pk}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        body = detail.json()
        self.assertEqual(
            body["preferences"],
            [
                {"trait_id": bells.pk, "trait_name": "Hates bells", "valence": "dislikes"},
                {"trait_id": flattery.pk, "trait_name": "Loves flattery", "valence": "likes"},
            ],
        )
        self.assertEqual(
            body["regard"],
            [
                {
                    "target_type": "persona",
                    "target_id": ysmay_persona.pk,
                    "target_name": "Ysmay",
                    "value": 20,
                    "reason": "Held the gate.",
                }
            ],
        )
        self.assertNotIn(self.account_of(ysmay).username, detail.content.decode())

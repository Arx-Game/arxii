"""API tests for the read-only NPCAsset endpoint (#1872, #3561)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase
from rest_framework.test import APIClient

from world.assets.factories import NPCAssetFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.stories.factories import StoryFactory, StoryParticipationFactory


class NPCAssetViewSetTests(EvenniaTestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        # RosterEntryFactory doesn't auto-create a tenure — first_tenure needs
        # an explicit player_number=1 RosterTenure to resolve.
        self.tenure = RosterTenureFactory(roster_entry=self.entry, player_number=1)
        self.account = self.tenure.player_data.account
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_list_scoped_to_own_persona(self) -> None:
        mine = NPCAssetFactory(promoter_persona=self.sheet.primary_persona)
        NPCAssetFactory()  # someone else's — must not appear
        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [mine.pk])

    def test_unauthenticated_rejected(self) -> None:
        # DRF returns 403, not 401, here: SessionAuthentication is the only
        # authenticator configured (REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES)
        # and its authenticate_header() returns None, so there's no
        # WWW-Authenticate challenge to trigger a 401 — matches
        # world.companions.tests.test_views's identical test_unauthenticated_is_denied.
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, 403)

    def test_staff_sees_every_asset(self) -> None:
        self.account.is_staff = True
        self.account.save()
        NPCAssetFactory(promoter_persona=self.sheet.primary_persona)
        elsewhere = NPCAssetFactory()

        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(elsewhere.pk, ids)

    def test_non_gm_name_search_still_scoped_to_own_persona(self) -> None:
        mine = NPCAssetFactory(promoter_persona=self.sheet.primary_persona)
        NPCAssetFactory()  # someone else's, matching name search too

        response = self.client.get(f"/api/assets/?name={mine.asset_persona.name}")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [mine.pk])

    def test_lead_gm_sees_asset_of_a_participant_in_their_led_story(self) -> None:
        """#3561 (review fix) - a non-staff GM's search scope is assets
        promoted by a character participating in a story that GM LEADS
        (Story.primary_table.gm == this GM's profile), not every asset in
        the game.
        """
        gm_profile = GMProfileFactory(account=self.account)
        table = GMTableFactory(gm=gm_profile)
        story = StoryFactory(primary_table=table)
        participant_sheet = CharacterSheetFactory()
        StoryParticipationFactory(story=story, character=participant_sheet)

        theirs = NPCAssetFactory(
            promoter_persona=participant_sheet.primary_persona,
            asset_persona=PersonaFactory(name="Quiet Informant"),
        )

        response = self.client.get("/api/assets/?name=quiet")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [theirs.pk])

    def test_lead_gm_does_not_see_asset_of_a_participant_in_another_story(self) -> None:
        """The privacy leak this test replaces: a GM who leads story S must
        not see an asset of a character who participates only in story T.
        """
        gm_profile = GMProfileFactory(account=self.account)
        table = GMTableFactory(gm=gm_profile)
        StoryFactory(primary_table=table)  # the story this GM leads - no participants

        other_story = StoryFactory()  # a story this GM does NOT lead
        other_sheet = CharacterSheetFactory()
        StoryParticipationFactory(story=other_story, character=other_sheet)
        NPCAssetFactory(
            promoter_persona=other_sheet.primary_persona,
            asset_persona=PersonaFactory(name="Loud Bruiser"),
        )

        response = self.client.get("/api/assets/?name=loud")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_junior_gm_who_leads_no_story_sees_only_own_assets(self) -> None:
        GMProfileFactory(account=self.account, level=GMLevel.JUNIOR)
        mine = NPCAssetFactory(promoter_persona=self.sheet.primary_persona)

        other_sheet = CharacterSheetFactory()
        other_story = StoryFactory()
        StoryParticipationFactory(story=other_story, character=other_sheet)
        NPCAssetFactory(promoter_persona=other_sheet.primary_persona)  # not led, not mine

        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [mine.pk])

"""The crown's player surfaces (#4061 slice 2): actions, the telnet command, the read API."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from actions.definitions.crown import CallCrownVoteAction, CastCrownVoteAction
from evennia_extensions.models import PlayerData
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.services import active_persona_for_sheet
from world.societies.constants import CrownBidStatus
from world.societies.crown import call_crown_vote
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.services import swear_fealty
from world.societies.membership_services import ensure_default_rank_ladder
from world.societies.models import CrownBid, CrownVote
from world.societies.seeds import seed_crime_vote_weights
from world.societies.turf_services import apply_turf_push


def _org(name):
    org = OrganizationFactory(name=name)
    ensure_default_rank_ladder(org)
    return org


class CrownSurfaceFixture(TestCase):
    def setUp(self):
        seed_crime_vote_weights()
        self.city = AreaFactory(level=AreaLevel.BARONY, name="Luxen")
        self.wards = [AreaFactory(level=AreaLevel.WARD, parent=self.city) for _ in range(3)]
        self.buns = _org("Dread Buns")
        self.lesser = _org("Gutter Kings")
        self.hands = _org("Sable Hands")
        apply_turf_push(self.buns, self.wards[0], 60)
        apply_turf_push(self.lesser, self.wards[1], 60)
        swear_fealty(vassal=self.lesser, liege=self.buns, tithe_pct=0)
        apply_turf_push(self.hands, self.wards[2], 60)
        self.account = AccountDB.objects.create_user("bob", "bob@example.com", "pw-123456")
        self.sheet = CharacterSheetFactory()
        # The seat sits on the sheet's active persona: what the actions resolve.
        self.bob = active_persona_for_sheet(self.sheet)
        OrganizationMembershipFactory(organization=self.buns, persona=self.bob, rank=1)
        self.character = self.sheet.character
        self.character.db_account = self.account
        self.character.save()
        entry = RosterEntryFactory(character_sheet=self.sheet)
        PlayerData.objects.create(account=self.account, selected_entry=entry)


class CrownActionTests(CrownSurfaceFixture):
    def test_a_crimelord_with_the_majority_calls_the_vote(self):
        result = CallCrownVoteAction().run(
            self.character, organization_id=self.buns.pk, city_id=self.city.pk
        )
        self.assertTrue(result.success, result.message)
        bid = CrownBid.objects.get(city=self.city)
        self.assertEqual(bid.bidder, self.buns)
        self.assertEqual(bid.called_by, self.bob)

    def test_only_the_organizations_leadership_may_call(self):
        nobody = CharacterSheetFactory()
        associate = active_persona_for_sheet(nobody)
        OrganizationMembershipFactory(organization=self.buns, persona=associate, rank=5)
        result = CallCrownVoteAction().run(
            nobody.character, organization_id=self.buns.pk, city_id=self.city.pk
        )
        self.assertFalse(result.success)
        self.assertFalse(CrownBid.objects.exists())

    def test_casting_records_the_vote_at_the_actors_weight(self):
        bid = call_crown_vote(self.buns, self.city, self.bob)
        result = CastCrownVoteAction().run(self.character, bid_id=bid.pk, in_favor=True)
        self.assertTrue(result.success, result.message)
        vote = CrownVote.objects.get(bid=bid, character_sheet=self.sheet)
        self.assertEqual((vote.weight, vote.in_favor, vote.persona), (20, True, self.bob))


class CrownApiTests(CrownSurfaceFixture):
    def _get(self, account=None):
        client = APIClient()
        client.force_authenticate(account or self.account)
        res = client.get(f"/api/societies/crown/{self.city.pk}/")
        assert res.status_code == 200, res.content
        return res.json()

    def test_the_read_shows_the_crown_the_open_bid_and_only_your_own_vote(self):
        data = self._get()
        self.assertIsNone(data["crown"])
        self.assertIsNone(data["bid"])
        self.assertTrue(data["may_call"])

        bid = call_crown_vote(self.buns, self.city, self.bob)
        CastCrownVoteAction().run(self.character, bid_id=bid.pk, in_favor=True)
        data = self._get()
        self.assertEqual(data["bid"]["bidder"], "Dread Buns")
        self.assertEqual(data["bid"]["status"], CrownBidStatus.OPEN)
        self.assertEqual(data["your_vote"], {"in_favor": True, "weight": 20})
        self.assertNotIn("weight_for", data["bid"])

    def test_the_tally_shows_once_the_bid_is_closed(self):
        bid = call_crown_vote(self.buns, self.city, self.bob)
        bid.status = CrownBidStatus.PASSED
        bid.weight_for, bid.weight_against = 23, 20
        bid.save(update_fields=["status", "weight_for", "weight_against"])
        data = self._get()
        self.assertIsNone(data["bid"])
        self.assertEqual(data["last_bid"]["weight_for"], 23)

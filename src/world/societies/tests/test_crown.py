"""Crime tiers, the weighted underworld vote and the crown (#4061 slice 1)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory
from world.societies.constants import CrimeTier, CrownBidStatus
from world.societies.crown import (
    CROWN_TITHE_PCT,
    call_crown_vote,
    cast_crown_vote,
    close_crown_bids,
    crime_tier,
    criminal_wards,
    may_call_vote,
    vote_weight,
)
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import FealtyEdge
from world.societies.houses.services import swear_fealty
from world.societies.membership_services import ensure_default_rank_ladder
from world.societies.models import Crown, CrownVote, Turf
from world.societies.seeds import seed_crime_vote_weights
from world.societies.turf_services import apply_turf_push


def _org(name):
    org = OrganizationFactory(name=name)
    ensure_default_rank_ladder(org)
    return org


def _member(org, tier, sheet=None):
    persona = PersonaFactory(character_sheet=sheet or CharacterSheetFactory())
    OrganizationMembershipFactory(organization=org, persona=persona, rank=tier)
    return persona


class CrimeTierTests(TestCase):
    def test_tier_is_the_highest_rung_the_org_itself_holds(self):
        ward = AreaFactory(level=AreaLevel.WARD)
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=ward)
        corner = RoomProfileFactory(area=neighborhood, is_outdoor=True)
        family, gang, crew = _org("Dread Buns"), _org("Ashfingers"), _org("Corner")
        nobody = _org("Nobody")
        apply_turf_push(family, ward, 40)
        apply_turf_push(gang, neighborhood, 40)
        apply_turf_push(crew, corner, 40)

        self.assertEqual(crime_tier(family), CrimeTier.FAMILY)
        self.assertEqual(crime_tier(gang), CrimeTier.GANG)
        self.assertEqual(crime_tier(crew), CrimeTier.CREW)
        self.assertIsNone(crime_tier(nobody))


class CityFixture(TestCase):
    """Luxen: four wards, three criminal, one lawful. The Dread Buns hold one ward, a
    smaller family sworn to them holds another, the Sable Hands hold the third; the
    Ashfingers are the Buns' sworn gang on a neighborhood."""

    def setUp(self):
        seed_crime_vote_weights()
        self.city = AreaFactory(level=AreaLevel.CITY)
        self.wards = [AreaFactory(level=AreaLevel.WARD, parent=self.city) for _ in range(4)]
        self.buns = _org("Dread Buns")
        self.lesser = _org("Gutter Kings")
        self.gang = _org("Ashfingers")
        self.hands = _org("Sable Hands")
        apply_turf_push(self.buns, self.wards[0], 60)
        apply_turf_push(self.lesser, self.wards[1], 60)
        swear_fealty(vassal=self.lesser, liege=self.buns, tithe_pct=0)
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=self.wards[0])
        apply_turf_push(self.gang, neighborhood, 60)
        swear_fealty(vassal=self.gang, liege=self.buns, tithe_pct=0)
        apply_turf_push(self.hands, self.wards[2], 60)
        self.bob = _member(self.buns, 1)


class CallingTheVoteTests(CityFixture):
    def test_criminal_wards_exclude_the_lawful_one(self):
        self.assertEqual(len(criminal_wards(self.city)), 3)

    def test_a_majority_of_criminal_wards_counting_vassals_may_call(self):
        self.assertTrue(may_call_vote(self.buns, self.city))  # 2 of 3, one via a vassal
        self.assertFalse(may_call_vote(self.hands, self.city))  # 1 of 3
        self.assertFalse(may_call_vote(self.lesser, self.city))  # its own ward alone

    def test_calling_opens_one_bid_that_closes_a_real_month_later(self):
        bid = call_crown_vote(self.buns, self.city, self.bob)
        self.assertEqual(bid.status, CrownBidStatus.OPEN)
        self.assertAlmostEqual((bid.closes_at - bid.opened_at).days, 30, delta=1)
        with self.assertRaises(ValueError):
            call_crown_vote(self.buns, self.city, self.bob)


class VoteWeightTests(CityFixture):
    def test_weights_follow_the_highest_seat_personally_held(self):
        self.assertEqual(vote_weight(self.bob.character_sheet), 20)
        princess = _member(self.buns, 2)
        self.assertEqual(vote_weight(princess.character_sheet), 3)
        boss = _member(self.gang, 1)
        _member(self.buns, 4, sheet=boss.character_sheet)  # an associate seat adds nothing
        self.assertEqual(vote_weight(boss.character_sheet), 5)
        associate = _member(self.buns, 5)
        self.assertEqual(vote_weight(associate.character_sheet), 0)
        outsider = CharacterSheetFactory()
        self.assertEqual(vote_weight(outsider), 0)


class TallyAndRecognitionTests(CityFixture):
    def _close(self, bid):
        bid.closes_at = timezone.now() - timedelta(minutes=1)
        bid.save(update_fields=["closes_at"])
        close_crown_bids()
        bid.refresh_from_db()
        return bid

    def test_votes_are_weighted_recast_replaces_and_zero_weight_may_not_vote(self):
        bid = call_crown_vote(self.buns, self.city, self.bob)
        princess = _member(self.buns, 2)
        cast_crown_vote(bid, self.bob.character_sheet, self.bob, in_favor=True)
        cast_crown_vote(bid, princess.character_sheet, princess, in_favor=False)
        cast_crown_vote(bid, princess.character_sheet, princess, in_favor=True)

        self.assertEqual(CrownVote.objects.filter(bid=bid).count(), 2)
        self.assertEqual(sum(v.weight for v in CrownVote.objects.filter(bid=bid)), 23)
        associate = _member(self.buns, 5)
        with self.assertRaises(ValueError):
            cast_crown_vote(bid, associate.character_sheet, associate, in_favor=True)

    def test_a_passed_bid_crowns_the_family_and_makes_the_others_its_vassals(self):
        bid = call_crown_vote(self.buns, self.city, self.bob)
        cast_crown_vote(bid, self.bob.character_sheet, self.bob, in_favor=True)
        princess = _member(self.buns, 2)
        cast_crown_vote(bid, princess.character_sheet, princess, in_favor=True)
        hands_head = _member(self.hands, 1)
        cast_crown_vote(bid, hands_head.character_sheet, hands_head, in_favor=False)
        close_crown_bids()  # not yet due: nothing happens
        self.assertFalse(Crown.objects.exists())

        bid = self._close(bid)

        self.assertEqual(bid.status, CrownBidStatus.PASSED)
        self.assertEqual((bid.weight_for, bid.weight_against), (23, 20))
        crown = Crown.objects.get(city=self.city, deposed_at__isnull=True)
        self.assertEqual(crown.organization, self.buns)
        self.assertEqual(crime_tier(self.buns), CrimeTier.EMPIRE)
        self.assertEqual(Turf.objects.get(area=self.city).controlling_org, self.buns)
        edge = FealtyEdge.objects.get(vassal=self.hands)
        self.assertEqual(edge.liege, self.buns)
        self.assertEqual(edge.obligation.percent, CROWN_TITHE_PCT)
        # Those already sworn keep their liege; the crown's cut reaches them through it.
        self.assertEqual(FealtyEdge.objects.get(vassal=self.gang).liege, self.buns)
        self.assertEqual(FealtyEdge.objects.get(vassal=self.lesser).liege, self.buns)

    def test_a_tie_or_a_no_fails(self):
        bid = call_crown_vote(self.buns, self.city, self.bob)
        cast_crown_vote(bid, self.bob.character_sheet, self.bob, in_favor=False)
        bid = self._close(bid)
        self.assertEqual(bid.status, CrownBidStatus.FAILED)
        self.assertFalse(Crown.objects.exists())

    def test_a_new_majority_ousts_the_sitting_crown(self):
        bid = call_crown_vote(self.buns, self.city, self.bob)
        cast_crown_vote(bid, self.bob.character_sheet, self.bob, in_favor=True)
        self._close(bid)
        # The Sable Hands flip the lawful ward and take the Buns' own ward: 3 of 4.
        apply_turf_push(self.hands, self.wards[3], 60)
        apply_turf_push(self.hands, self.wards[0], 100)
        self.assertTrue(may_call_vote(self.hands, self.city))
        hands_head = _member(self.hands, 1)
        bid2 = call_crown_vote(self.hands, self.city, hands_head)
        cast_crown_vote(bid2, hands_head.character_sheet, hands_head, in_favor=True)

        self._close(bid2)

        old = Crown.objects.get(organization=self.buns)
        self.assertIsNotNone(old.deposed_at)
        new = Crown.objects.get(city=self.city, deposed_at__isnull=True)
        self.assertEqual(new.organization, self.hands)
        self.assertEqual(FealtyEdge.objects.get(vassal=self.buns).liege, self.hands)
        self.assertEqual(Turf.objects.get(area=self.city).controlling_org, self.hands)

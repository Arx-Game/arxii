"""Accusation counter-clues (#1825) — the investigable trail every accusation leaves.

``create_accusation_counter_clue`` plants a RESEARCH-resolution SECRET clue in the
region's social hubs, with ``detect_difficulty`` seeded from the accuser's roll (a smear's
Gossip roll; a frame's project quality) — the "cost to mint ↔ difficulty to disprove" dial.
"""

from django.test import TestCase, tag

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.models import Clue, RoomClue
from world.clues.services import create_accusation_counter_clue
from world.secrets.factories import SecretFactory


@tag("postgres")  # hub-in-region resolution walks the AreaClosure materialized view
class AccusationCounterClueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region = AreaFactory(level=AreaLevel.REGION)
        cls.hub_one = RoomProfileFactory(area=cls.region, is_social_hub=True)
        cls.hub_two = RoomProfileFactory(area=cls.region, is_social_hub=True)
        cls.not_a_hub = RoomProfileFactory(area=cls.region, is_social_hub=False)
        cls.other_region_hub = RoomProfileFactory(
            area=AreaFactory(level=AreaLevel.REGION), is_social_hub=True
        )
        cls.secret = SecretFactory()

    def test_creates_a_research_secret_clue_in_region_hubs(self):
        clue = create_accusation_counter_clue(self.secret, region=self.region, difficulty=15)
        assert clue.target_kind == ClueTargetKind.SECRET
        assert clue.target_secret == self.secret
        assert clue.resolution_mode == ClueResolution.RESEARCH
        placements = RoomClue.objects.filter(clue=clue)
        placed_profiles = {placement.room_profile for placement in placements}
        assert placed_profiles == {self.hub_one, self.hub_two}
        assert all(placement.detect_difficulty == 15 for placement in placements)

    def test_ignores_non_hubs_and_other_regions(self):
        clue = create_accusation_counter_clue(self.secret, region=self.region, difficulty=10)
        placed = RoomClue.objects.filter(clue=clue).values_list("room_profile_id", flat=True)
        assert self.not_a_hub.pk not in placed
        assert self.other_region_hub.pk not in placed

    def test_idempotent_per_secret(self):
        first = create_accusation_counter_clue(self.secret, region=self.region, difficulty=10)
        second = create_accusation_counter_clue(self.secret, region=self.region, difficulty=99)
        assert first.pk == second.pk
        assert Clue.objects.filter(target_secret=self.secret).count() == 1
        # Existing placements keep their original difficulty (no silent re-difficulty).
        placements = RoomClue.objects.filter(clue=first)
        assert all(placement.detect_difficulty == 10 for placement in placements)

    def test_hub_cap_limits_placements(self):
        for _ in range(5):
            RoomProfileFactory(area=self.region, is_social_hub=True)
        clue = create_accusation_counter_clue(self.secret, region=self.region, difficulty=10)
        # PLACEHOLDER cap of 3 hubs.
        assert RoomClue.objects.filter(clue=clue).count() == 3

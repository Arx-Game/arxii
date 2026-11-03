"""A title's station (seated, titular, potential), its charter and the claims on it
(#4983 slice 1, #4984): the model rules, before the services that write them."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_creation.factories import RealmFactory
from world.societies.houses.almanach import plant_rung
from world.societies.houses.constants import TitleStation, TitleTier
from world.societies.houses.models import CharteredFief


class TitleStationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Luxen")
        cls.kingdom = plant_rung(realm=cls.realm, tier=TitleTier.KINGDOM, name="Luxen")
        cls.duchy = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Brittany", parent_title=cls.kingdom
        )

    def test_a_titular_or_crown_title_is_never_claimable(self) -> None:
        self.kingdom.is_claimable = True
        with self.assertRaises(ValidationError):
            self.kingdom.full_clean()
        self.duchy.station = TitleStation.TITULAR
        self.duchy.is_claimable = True
        with self.assertRaises(ValidationError):
            self.duchy.full_clean()
        self.duchy.is_claimable = False
        self.duchy.full_clean()
        self.duchy.station = TitleStation.SEATED
        self.duchy.is_claimable = True
        self.duchy.full_clean()

    def test_a_charter_names_lower_tiers_in_its_realm(self) -> None:
        other_realm = RealmFactory(name="Inferna")
        far_duchy = plant_rung(realm=other_realm, tier=TitleTier.DUCHY, name="Piropa")
        old_kingdom = plant_rung(realm=self.realm, tier=TitleTier.KINGDOM, name="Old Luxen")
        # a duchy chartered by two kingdoms is fine
        CharteredFief(title=self.kingdom, fief=self.duchy).full_clean()
        CharteredFief(title=old_kingdom, fief=self.duchy, basis="Before the revolt").full_clean()
        # at or above the title's tier: no
        with self.assertRaises(ValidationError):
            CharteredFief(title=self.duchy, fief=self.kingdom).full_clean()
        with self.assertRaises(ValidationError):
            CharteredFief(title=self.kingdom, fief=old_kingdom).full_clean()
        # another realm: only an empire's charter reaches that far
        with self.assertRaises(ValidationError):
            CharteredFief(title=self.kingdom, fief=far_duchy).full_clean()
        empire = plant_rung(realm=self.realm, tier=TitleTier.EMPIRE, name="The Chimeric Empire")
        CharteredFief(title=empire, fief=far_duchy).full_clean()

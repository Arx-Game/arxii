"""Tier 3 rites as ceremonies and the favored-facet offering bonus (#3777)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.ceremonies import OpenCeremonyAction
from evennia_extensions.factories import RoomProfileFactory
from world.ceremonies.constants import CeremonyTypeKey
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.models import CeremonyConfig, CeremonyOffering
from world.ceremonies.services import (
    CEREMONY_CHECK_TYPE_NAME,
    CeremonyError,
    finish_ceremony,
    open_ceremony,
    record_offering,
)
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemFacetFactory, ItemInstanceFactory
from world.magic.constants import GainSource
from world.magic.models.grant import ResonanceGrant
from world.roster.factories import grant_test_tenure
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import BeingResonanceTier, RiteTier
from world.worship.factories import (
    BeingFacetFactory,
    RiteKindFactory,
    WorshipFeastDayFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
)
from world.worship.models import DevotionStanding, WorshipDeclaration, WorshipRitePerformance


class RiteCeremonyTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.rite_type = CeremonyTypeFactory(key=CeremonyTypeKey.RITE, name="Rite")
        cls.blessing_type = CeremonyTypeFactory(key=CeremonyTypeKey.BLESSING, name="Blessing")
        cls.being = WorshippedBeingFactory()
        cls.location = RoomProfileFactory()
        cls.persona = PersonaFactory()
        cls.sheet = cls.persona.character_sheet
        grant_test_tenure(cls.sheet)
        WorshipDeclaration.objects.create(character_sheet=cls.sheet, public_being=cls.being)
        cls.ordeal = WorshipRiteFactory(
            being=cls.being,
            kind=RiteKindFactory(name="Ordeal", tier=RiteTier.PERILOUS),
            name="The Walk of Ash",
        )
        cls.ordeal.resonance.tier = BeingResonanceTier.ASSOCIATED
        cls.ordeal.resonance.save(update_fields=["tier"])
        cls.vigil = WorshipRiteFactory(
            being=cls.being, kind=RiteKindFactory(name="Vigil", tier=RiteTier.DEVOTIONAL)
        )
        cls.rites_check = CheckTypeFactory(name=CEREMONY_CHECK_TYPE_NAME)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        WorshipRiteTierAwardFactory(
            tier=RiteTier.PERILOUS, outcome_tier=cls.success, resonance_amount=12, favor_amount=9
        )

    def _open(self, rite=None, type_key=CeremonyTypeKey.RITE, being=None):
        return open_ceremony(
            officiant_persona=self.persona,
            type_key=type_key,
            honoree_sheets=[],
            location_profile=self.location,
            being=being,
            worship_rite=rite,
        )


class OpenRiteCeremonyTests(RiteCeremonyTestBase):
    def test_a_rite_ceremony_carries_its_tier_three_rite(self) -> None:
        ceremony = self._open(self.ordeal)
        self.assertEqual(ceremony.worship_rite, self.ordeal)
        self.assertEqual(ceremony.being, self.being)

    def test_a_rite_ceremony_needs_a_rite(self) -> None:
        with self.assertRaises(CeremonyError):
            self._open(None)

    def test_a_scene_act_rite_is_not_a_ceremony(self) -> None:
        with self.assertRaises(CeremonyError):
            self._open(self.vigil)

    def test_another_beings_rite_is_refused(self) -> None:
        other = WorshipRiteFactory(kind=self.ordeal.kind)
        with self.assertRaises(CeremonyError):
            self._open(other)

    def test_an_inactive_rite_is_refused(self) -> None:
        self.ordeal.is_active = False
        self.ordeal.save(update_fields=["is_active"])
        with self.assertRaises(CeremonyError):
            self._open(self.ordeal)

    def test_other_ceremony_types_carry_no_rite(self) -> None:
        with self.assertRaises(CeremonyError):
            self._open(self.ordeal, type_key=CeremonyTypeKey.BLESSING)

    def test_the_action_resolves_the_rite_by_name(self) -> None:
        self.sheet.character.db_location = self.location.objectdb
        self.sheet.character.save(update_fields=["db_location"])

        result = OpenCeremonyAction().run(
            actor=self.sheet.character,
            type_key=CeremonyTypeKey.RITE,
            honoree_names=[],
            rite_name="the walk of ash",
        )

        self.assertTrue(result.success, result.message)
        self.assertIn("The Walk of Ash", result.message)


class FinishRiteCeremonyTests(RiteCeremonyTestBase):
    def test_finish_pays_the_tier_three_award_off_the_rites_roll(self) -> None:
        ceremony = self._open(self.ordeal)

        with force_check_outcome(self.success):
            finish_ceremony(ceremony=ceremony)

        performance = WorshipRitePerformance.objects.get(character_sheet=self.sheet)
        self.assertEqual(performance.rite, self.ordeal)
        self.assertEqual(performance.ceremony, ceremony)
        self.assertEqual(performance.outcome_tier, self.success)
        self.assertEqual(performance.resonance_granted, 12)
        self.assertEqual(performance.favor_granted, 9)
        grant = ResonanceGrant.objects.get(source=GainSource.WORSHIP_RITE)
        self.assertEqual(grant.source_worship_rite_performance, performance)
        config = CeremonyConfig.objects.get()
        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        self.assertEqual(standing.favor, config.devotion_officiant + 9)

    def test_a_second_rite_ceremony_the_same_week_pays_resonance_but_no_favor(self) -> None:
        with force_check_outcome(self.success):
            finish_ceremony(ceremony=self._open(self.ordeal))
        with force_check_outcome(self.success):
            finish_ceremony(ceremony=self._open(self.ordeal))

        second = WorshipRitePerformance.objects.order_by("-pk").first()
        self.assertEqual(second.resonance_granted, 12)
        self.assertEqual(second.favor_granted, 0)

    def test_a_missing_award_row_stops_the_finish_before_any_honor(self) -> None:
        from world.ceremonies.constants import CeremonyStatus
        from world.societies.models import LegendEntry

        botch = CheckOutcomeFactory(name="Critical Failure", success_level=-2)
        ceremony = self._open(self.ordeal)

        with force_check_outcome(botch), self.assertRaises(CeremonyError):
            finish_ceremony(ceremony=ceremony)

        ceremony.refresh_from_db()
        self.assertEqual(ceremony.status, CeremonyStatus.OPEN)
        self.assertFalse(LegendEntry.objects.exists())
        self.assertFalse(DevotionStanding.objects.filter(character_sheet=self.sheet).exists())

    def test_a_plain_ceremony_pays_no_rite_award(self) -> None:
        ceremony = self._open(None, type_key=CeremonyTypeKey.BLESSING)

        with force_check_outcome(self.success):
            finish_ceremony(ceremony=ceremony)

        self.assertFalse(WorshipRitePerformance.objects.exists())

    def test_feast_day_doubles_the_ceremony_award_too(self) -> None:
        from unittest.mock import patch

        WorshipFeastDayFactory(being=self.being, ic_month=1, ic_day=1)
        ceremony = self._open(self.ordeal)

        with (
            patch("world.worship.rite_services.is_feast_day_today", return_value=True),
            force_check_outcome(self.success),
        ):
            finish_ceremony(ceremony=ceremony)

        performance = WorshipRitePerformance.objects.get(character_sheet=self.sheet)
        self.assertEqual(performance.resonance_granted, 24)


class FavoredOfferingTests(RiteCeremonyTestBase):
    def _funeral_less_ceremony(self):
        return self._open(None, type_key=CeremonyTypeKey.BLESSING)

    def test_an_item_with_a_favored_facet_is_credited_at_the_multiplier(self) -> None:
        config = CeremonyConfig.objects.first() or CeremonyConfig.objects.create()
        config.offering_favored_facet_multiplier_percent = 300
        config.save(update_fields=["offering_favored_facet_multiplier_percent"])
        favored = BeingFacetFactory(being=self.being)
        plain = ItemInstanceFactory(template__value=10)
        blessed = ItemInstanceFactory(template__value=10)
        ItemFacetFactory(item_instance=blessed, facet=favored.facet)
        ItemFacetFactory(item_instance=plain)  # some other facet the being does not favor
        ceremony = self._funeral_less_ceremony()

        record_offering(ceremony=ceremony, item_instances=[plain, blessed])

        by_name = {o.item_name: o for o in CeremonyOffering.objects.filter(ceremony=ceremony)}
        plain_grant = by_name[str(plain)].worship_grant
        blessed_grant = by_name[str(blessed)].worship_grant
        self.assertEqual(plain_grant.amount, 10 * config.offering_resonance_per_value)
        self.assertEqual(blessed_grant.amount, 3 * 10 * config.offering_resonance_per_value)
        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        self.assertEqual(standing.favor, config.devotion_per_offering * (1 + 3))

    def test_a_being_that_favors_nothing_credits_every_item_plainly(self) -> None:
        item = ItemInstanceFactory(template__value=10)
        ItemFacetFactory(item_instance=item)
        ceremony = self._funeral_less_ceremony()
        config = CeremonyConfig.objects.first() or CeremonyConfig.objects.create()

        record_offering(ceremony=ceremony, item_instances=[item])

        offering = CeremonyOffering.objects.get(ceremony=ceremony)
        self.assertEqual(offering.worship_grant.amount, 10 * config.offering_resonance_per_value)

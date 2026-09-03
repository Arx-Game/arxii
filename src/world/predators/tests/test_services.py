"""Predator ecology tests (#3093): the slow ladder, counterplay, Afflictions.

Area-dependent tests run on the CI parity tier (local parity DBs lack the
areas closure table — pre-existing). Deterministic rng stubs everywhere.
"""

import random

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.predators.constants import (
    DORMANCY_FLOOR,
    ROBBERY_SKIM_PCT,
    STAGE_WEEKS,
    MenaceStage,
)
from world.predators.factories import PredatorBandFactory
from world.predators.models import AfflictionSign, MenaceEvent, PredatorBand
from world.predators.services import (
    select_prey,
    strike_band,
    weekly_affliction_tick,
    weekly_menace_tick,
)
from world.roster.constants import NOBLE_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory, KinspersonFactory, UnionFactory
from world.roster.models import FamilyMembership, UnionKind
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import (
    CrisisOrigin,
    CrisisResolution,
    DomainCrisisSeverity,
)
from world.societies.houses.models import DomainCrisis, DomainCrisisType, HouseStature
from world.societies.houses.services import create_domain


class _NoSpawnRandom(random.Random):
    """rng whose random() is 1.0 (no spawns/spreads) — keeps ticks deterministic."""

    def random(self):
        return 1.0


def _make_landed(name: str, perceived: int, realm=None):
    family = FamilyFactory(name=name, kind=FamilyKindFactory(name=NOBLE_KIND_NAME))
    org = OrganizationFactory(name=f"House {name}", family=family)
    area = AreaFactory(realm=realm)
    create_domain(area=area, name=f"{name} Vale", owner_org=org)
    HouseStature.objects.create(organization=org, perceived_total=perceived, true_total=perceived)
    return org


class PreySelectionTests(TestCase):
    def test_weakest_perceived_org_is_chosen(self):
        strong = _make_landed("Strong", 10_000)
        weak = _make_landed("Weak", 100)
        band = PredatorBandFactory()
        self.assertEqual(select_prey(band), weak)
        self.assertNotEqual(select_prey(band), strong)

    def test_regional_peace_excludes_consort_holders(self):
        from world.realms.models import Realm
        from world.roster.constants import MembershipBasis

        band = PredatorBandFactory()
        # Give the band's region a realm so peace can key on it.
        realm = Realm.objects.create(name="Inferna Test")
        band.home_region.realm = realm
        band.home_region.save(update_fields=["realm"])
        shielded = _make_landed("Shielded", 50, realm=realm)
        exposed = _make_landed("Exposed", 60, realm=realm)
        consort_kind = UnionKind.objects.create(
            name="Consort of Inferna Test",
            realm=realm,
            stature_share_pct=50,
            requires_landed_title=True,
        )
        princess = KinspersonFactory(name="Princess", family=shielded.family)
        FamilyMembership.objects.create(
            kinsperson=princess,
            family=shielded.family,
            basis=MembershipBasis.BORN,
            started_at="2020-01-01T00:00:00Z",
        )
        consort = KinspersonFactory(name="Consort")
        UnionFactory(kind=consort_kind, members=[princess, consort])
        self.assertEqual(select_prey(band), exposed)


class MenaceLadderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prey = _make_landed("Prey", 100)

    def _band(self, **kwargs):
        return PredatorBandFactory(prey=self.prey, **kwargs)

    def test_band_advances_only_after_unanswered_weeks(self):
        band = self._band()
        weeks = STAGE_WEEKS[MenaceStage.RUMORS]
        rng = _NoSpawnRandom()
        for _ in range(weeks - 1):
            weekly_menace_tick(rng=rng)
        band.refresh_from_db()
        self.assertEqual(band.stage, MenaceStage.RUMORS)
        weekly_menace_tick(rng=rng)
        band.refresh_from_db()
        self.assertEqual(band.stage, MenaceStage.LAWLESSNESS)
        self.assertTrue(
            MenaceEvent.objects.filter(band=band, stage=MenaceStage.LAWLESSNESS).exists()
        )

    def test_full_ladder_takes_ten_weeks_to_raids(self):
        band = self._band()
        rng = _NoSpawnRandom()
        weeks_to_raids = sum(
            STAGE_WEEKS[s]
            for s in (MenaceStage.RUMORS, MenaceStage.LAWLESSNESS, MenaceStage.ROBBERY)
        )
        for _ in range(weeks_to_raids):
            weekly_menace_tick(rng=rng)
        band.refresh_from_db()
        self.assertEqual(band.stage, MenaceStage.RAIDS)
        # The first raid lands on the FOLLOWING tick — stage effects run before
        # advancement, so even the jump to open raiding is announced a week out.
        weekly_menace_tick(rng=rng)
        # An attributed, public raid crisis now stands on the prey's domain.
        crisis = DomainCrisis.objects.get(aggressor_band=band)
        self.assertEqual(crisis.origin, CrisisOrigin.PREDATOR)
        self.assertIsNone(crisis.surfaces_at)
        self.assertEqual(crisis.severity, DomainCrisisSeverity.CRISIS)

    def test_lawlessness_ticks_unrest_and_robbery_skims(self):
        from world.currency.models import OrgIncomeStream

        band = self._band(stage=MenaceStage.ROBBERY)
        stream = OrgIncomeStream.objects.create(
            organization=self.prey,
            name="Test Farms",
            kind="domain_tax",
            gross_amount=1_000,
            uncollected_pool=1_000,
        )
        domain = self.prey.domains.first()
        unrest_before = domain.unrest
        weekly_menace_tick(rng=_NoSpawnRandom())
        domain.refresh_from_db()
        stream.refresh_from_db()
        band.refresh_from_db()
        self.assertGreater(domain.unrest, unrest_before)
        expected_cut = 1_000 * ROBBERY_SKIM_PCT // 100
        self.assertEqual(stream.uncollected_pool, 1_000 - expected_cut)
        self.assertEqual(band.loot_stash, expected_cut)

    def test_strike_knocks_down_and_dormancy_below_floor(self):
        band = self._band(stage=MenaceStage.RAIDS, strength=DORMANCY_FLOOR + 20)
        strike_band(band, strength_burn=25)
        band.refresh_from_db()
        self.assertEqual(band.stage, MenaceStage.ROBBERY)
        self.assertIsNotNone(band.dormant_until)
        self.assertFalse(band.is_active)

    def test_strike_to_zero_disbands(self):
        band = self._band(strength=10)
        strike_band(band, strength_burn=25)
        band.refresh_from_db()
        self.assertIsNotNone(band.disbanded_at)

    def test_resolving_attributed_raid_answers_the_band(self):
        from world.societies.houses.crisis_services import resolve_crisis

        band = self._band(stage=MenaceStage.RAIDS)
        weekly_menace_tick(rng=_NoSpawnRandom())
        crisis = DomainCrisis.objects.get(aggressor_band=band)
        strength_before = PredatorBand.objects.get(pk=band.pk).strength
        resolve_crisis(crisis, resolution=CrisisResolution.MISSION_COMPLETED)
        band.refresh_from_db()
        self.assertLess(band.strength, strength_before)
        self.assertNotEqual(band.stage, MenaceStage.RAIDS)


class AfflictionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = _make_landed("Blightward", 500)
        cls.affliction = DomainCrisisType.objects.create(
            name="Walking Blight",
            default_severity=DomainCrisisSeverity.CATASTROPHE,
            ignores_stature=True,
            affliction_spreads=True,
        )

    def test_sign_converts_to_outbreak_next_tick(self):
        domain = self.org.domains.first()
        sign = AfflictionSign.objects.create(domain=domain, crisis_type=self.affliction)
        result = weekly_affliction_tick(rng=_NoSpawnRandom())
        self.assertEqual(result["outbreaks"], 1)
        sign.refresh_from_db()
        self.assertIsNotNone(sign.converted_at)
        crisis = DomainCrisis.objects.get(domain=domain)
        self.assertEqual(crisis.origin, CrisisOrigin.AFFLICTION)
        self.assertEqual(crisis.severity, DomainCrisisSeverity.CATASTROPHE)

    def test_unresolved_outbreak_spreads_one_hop(self):
        class _AlwaysSpread(_NoSpawnRandom):
            def random(self):
                return 0.0

        from world.realms.models import Realm

        realm = Realm.objects.create(name="Blightrealm")
        domain_a = self.org.domains.first()
        domain_a.area.realm = realm
        domain_a.area.save(update_fields=["realm"])
        neighbor_org = _make_landed("Neighbor", 500, realm=realm)
        AfflictionSign.objects.create(domain=domain_a, crisis_type=self.affliction)
        weekly_affliction_tick(rng=_NoSpawnRandom())  # convert to outbreak
        # _AlwaysSpread would also mint signs everywhere; count only spreads.
        result = weekly_affliction_tick(rng=_AlwaysSpread())
        self.assertGreaterEqual(result["spread"], 1)
        self.assertTrue(
            DomainCrisis.objects.filter(
                domain__owner_org=neighbor_org, crisis_type=self.affliction
            ).exists()
        )


class WeeklyTickSmokeTests(TestCase):
    def test_tick_with_no_bands_is_quiet(self):
        result = weekly_menace_tick(rng=_NoSpawnRandom())
        self.assertEqual(result, {"spawned": 0, "advanced": 0, "pressured": 0})

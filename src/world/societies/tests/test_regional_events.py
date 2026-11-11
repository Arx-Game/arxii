"""Regional events (#5069 slice 4, #5080): a disaster over an area is one row the
formula and the map both read. Opening it rebases the land beneath and cuts its
capacity while it lasts; closing it rebases again and the land recovers by formula;
an awake house inside gets a crisis to judge, a dormant one takes only the ambient hit."""

from datetime import timedelta
import math

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.areas.constants import AreaLevel
from world.character_creation.factories import RealmFactory
from world.game_clock.factories import GameClockFactory
from world.roster.factories import FamilyFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import plant_rung, rung_area_for_title
from world.societies.houses.constants import CrisisOrigin, TitleTier
from world.societies.houses.demography import population_now
from world.societies.houses.models import (
    Domain,
    DomainCrisis,
    DomainCrisisType,
    DominionConfig,
    RegionalEvent,
    RegionalEventKind,
)
from world.societies.houses.regional_events import (
    active_capacity_multipliers,
    close_regional_event,
    open_regional_event,
)
from world.societies.models import Organization

YEAR = timedelta(days=360)


class RegionalEventTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Inferna")
        cls.crown = OrganizationFactory(name="Piropa", family=FamilyFactory(name="Piropa"))
        cls.kingdom = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=cls.crown
        )
        cls.duchy = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Caldera", parent_title=cls.kingdom
        )
        cls.duke = OrganizationFactory(name="House Vampa", family=FamilyFactory(name="Vampa"))
        cls.vampa_county = plant_rung(
            realm=cls.realm,
            tier=TitleTier.COUNTY,
            name="Vampa",
            parent_title=cls.duchy,
            held_by=cls.duke,
        )
        cls.elsewhere = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Saltreach", parent_title=cls.kingdom
        )
        cls.crisis_type = DomainCrisisType.objects.create(
            name="Blight", description="The crops fail.", automated=False
        )
        cls.blight = RegionalEventKind.objects.create(
            name="Blight",
            description="A blight on the fields.",
            capacity_cut_pct=50,
            prosperity_delta=-20,
            unrest_delta=15,
            crisis_type=cls.crisis_type,
        )

    def setUp(self):
        dials = DominionConfig.load()
        dials.population_rate_pct_per_month = 10
        dials.save()
        # every holding's base is written at the clock's anchor, so the clock never
        # has to read a moment before its own epoch
        self.now = timezone.now()
        GameClockFactory(anchor_real_time=self.now, time_ratio=1.0)
        for domain in Domain.objects.filter(area__realm=self.realm):
            domain.population = 1000
            domain.population_capacity = 1000
            domain.population_rebased_at = self.now
            domain.prosperity = 50
            domain.unrest = 10
            domain.save(
                update_fields=[
                    "population",
                    "population_capacity",
                    "population_rebased_at",
                    "prosperity",
                    "unrest",
                ]
            )

    def _county_domain(self) -> Domain:
        return Domain.objects.get(pk=rung_area_for_title(self.vampa_county).pk)

    def test_opening_an_event_cuts_capacity_under_it_and_rebases_the_land(self):
        now = self.now
        event = open_regional_event(
            kind=self.blight,
            area=rung_area_for_title(self.duchy),
            note="The fields blacken.",
            now=now,
        )

        county = self._county_domain()
        self.assertEqual(county.population_rebased_at, now)
        self.assertEqual(county.prosperity, 30)
        self.assertEqual(county.unrest, 25)
        multipliers = active_capacity_multipliers(now=now)
        self.assertAlmostEqual(multipliers[county.area_id], 0.5)
        # the people fall toward the cut capacity: a year at ten percent a month
        later = now + YEAR
        self.assertEqual(population_now(county, at=later), round(500 + 500 * math.exp(-1.2)))
        # land outside the footprint is untouched
        saltreach_county = Domain.objects.filter(
            area__parent=rung_area_for_title(self.elsewhere)
        ).first()
        self.assertEqual(saltreach_county.prosperity, 50)
        self.assertEqual(population_now(saltreach_county, at=later), 1000)
        self.assertTrue(event.is_active)

    def test_an_awake_house_inside_gets_a_crisis_and_a_dormant_one_does_not(self):
        Organization.objects.filter(pk=self.crown.pk).update_with_reason(
            dormant_since=timezone.now(), reason="test: the crown sleeps"
        )
        Organization.flush_cached_instance(Organization.objects.get(pk=self.crown.pk))

        open_regional_event(kind=self.blight, area=rung_area_for_title(self.kingdom))

        duke_crises = DomainCrisis.objects.filter(domain__owner_org=self.duke)
        self.assertEqual(duke_crises.count(), 1)
        self.assertEqual(duke_crises.get().origin, CrisisOrigin.REGIONAL)
        self.assertEqual(duke_crises.get().crisis_type, self.crisis_type)
        self.assertFalse(DomainCrisis.objects.filter(domain__owner_org=self.crown).exists())

    def test_closing_an_event_restores_capacity_and_the_land_recovers(self):
        now = self.now
        event = open_regional_event(kind=self.blight, area=rung_area_for_title(self.duchy), now=now)
        midway = now + YEAR

        close_regional_event(event, now=midway)

        county = self._county_domain()
        self.assertEqual(county.population_rebased_at, midway)
        hurt = round(500 + 500 * math.exp(-1.2))
        self.assertEqual(county.population, hurt, "rebased to the figure the cut left")
        self.assertEqual(county.prosperity, 50)
        self.assertEqual(county.unrest, 10)
        self.assertEqual(active_capacity_multipliers(now=midway), {})
        # a year on, the people climb back toward the full capacity
        self.assertEqual(
            population_now(county, at=midway + YEAR),
            round(1000 - (1000 - hurt) * math.exp(-1.2)),
        )
        event.refresh_from_db()
        self.assertFalse(event.is_active)
        self.assertEqual(RegionalEvent.objects.filter(ended_at__isnull=True).count(), 0)

    def test_two_events_over_the_same_land_compound(self):
        famine = RegionalEventKind.objects.create(name="Famine", capacity_cut_pct=20)
        area = rung_area_for_title(self.duchy)
        open_regional_event(kind=self.blight, area=area)
        open_regional_event(kind=famine, area=area, severity_pct=50)

        county = self._county_domain()
        self.assertAlmostEqual(active_capacity_multipliers()[county.area_id], 0.5 * 0.9)

    def test_a_barony_area_event_touches_only_that_seat(self):
        barony = plant_rung(
            realm=self.realm,
            tier=TitleTier.BARONY,
            name="Cinder Gate",
            parent_title=self.vampa_county,
        )
        open_regional_event(kind=self.blight, area=rung_area_for_title(barony))

        multipliers = active_capacity_multipliers()
        self.assertIn(rung_area_for_title(barony).pk, multipliers)
        self.assertNotIn(self._county_domain().area_id, multipliers)


class RegionalEventAdminTests(TestCase):
    """Staff open and close an event from the admin too (#5080): the add form goes
    through ``open_regional_event`` so the land beneath is rebased, and a changelist
    action closes."""

    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Inferna")
        cls.crown = OrganizationFactory(name="Piropa", family=FamilyFactory(name="Piropa"))
        cls.kingdom = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=cls.crown
        )
        cls.blight = RegionalEventKind.objects.create(name="Blight", capacity_cut_pct=50)
        cls.superuser = AccountFactory(username="eventstaff", is_staff=True, is_superuser=True)

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_the_pages_render(self):
        for url in (
            reverse("admin:arxii_regionaleventkind_changelist"),
            reverse("admin:arxii_regionalevent_changelist"),
            reverse("admin:arxii_regionalevent_add"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_adding_opens_through_the_service_and_the_action_closes(self):
        area = rung_area_for_title(self.kingdom)
        before = timezone.now()
        response = self.client.post(
            reverse("admin:arxii_regionalevent_add"),
            {"kind": self.blight.pk, "area": area.pk, "severity_pct": 70, "note": "GM only"},
        )
        self.assertEqual(response.status_code, 302, response.content[:2000])
        event = RegionalEvent.objects.get()
        self.assertEqual(event.severity_pct, 70)
        self.assertEqual(event.opened_by_id, self.superuser.pk)
        county = Domain.objects.filter(area__realm=self.realm, area__level=AreaLevel.COUNTY).first()
        self.assertIsNotNone(county)
        self.assertGreaterEqual(county.population_rebased_at, before, "rebased at open")

        response = self.client.post(
            reverse("admin:arxii_regionalevent_changelist"),
            {"action": "close_events", "_selected_action": [event.pk]},
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertFalse(event.is_active)

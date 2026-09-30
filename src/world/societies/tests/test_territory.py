"""Territory (#4060 slice 1): turf at every rung, land units, territory streams."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.currency.constants import TERRITORY_BASE_PER_UNIT, IncomeStreamKind
from world.currency.models import OrgIncomeStream
from world.currency.services import accrue_income_stream
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import area_stat_total
from world.societies.constants import ControlKind
from world.societies.factories import OrganizationFactory
from world.societies.houses.services import create_domain
from world.societies.models import Turf
from world.societies.territory import ensure_territory_streams, territory_units
from world.societies.turf_services import apply_turf_push


def _room(area, *, outdoor=True):
    return RoomProfileFactory(area=area, is_outdoor=outdoor)


class TurfSiteTests(TestCase):
    def test_turf_may_sit_on_a_ward(self):
        ward = AreaFactory(level=AreaLevel.WARD)
        family = OrganizationFactory(name="Dread Buns")

        turf = apply_turf_push(family, ward, 40)

        self.assertEqual(turf.area, ward)
        self.assertEqual(turf.grip, 40)

    def test_turf_may_sit_on_an_outdoor_room(self):
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        corner = _room(neighborhood)
        crew = OrganizationFactory(name="Saltside Crew")

        turf = apply_turf_push(crew, corner, 30)

        self.assertEqual(turf.room_profile, corner)
        self.assertIsNone(turf.area)

    def test_turf_refuses_an_indoor_room(self):
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        cellar = _room(neighborhood, outdoor=False)

        with self.assertRaises(ValidationError):
            Turf(room_profile=cellar).full_clean()

    def test_turf_refuses_a_county_and_needs_exactly_one_site(self):
        # A barony is the city rung since #4085, so turf may sit on it; a county is above turf.
        county = AreaFactory(level=AreaLevel.COUNTY)
        with self.assertRaises(ValidationError):
            Turf(area=county).full_clean()

        ward = AreaFactory(level=AreaLevel.WARD)
        with self.assertRaises(ValidationError):
            Turf(area=ward, room_profile=_room(ward)).full_clean()
        with self.assertRaises(ValidationError):
            Turf().full_clean()


class LandUnitTests(TestCase):
    """Units are outdoor rooms under the site, minus rooms a lower rung of the same kind holds."""

    def setUp(self):
        self.city = AreaFactory(level=AreaLevel.BARONY)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=self.ward)
        self.corner = _room(self.neighborhood)
        _room(self.neighborhood)
        self.square = _room(self.ward)
        _room(self.ward, outdoor=False)

    def test_units_count_outdoor_rooms_only(self):
        self.assertEqual(territory_units(self.ward, ControlKind.CRIMINAL), 3)
        self.assertEqual(territory_units(self.corner, ControlKind.CRIMINAL), 1)

    def test_a_lower_rung_of_the_same_kind_takes_its_rooms_out(self):
        gang = OrganizationFactory(name="Ashfingers")
        apply_turf_push(gang, self.neighborhood, 50)

        self.assertEqual(territory_units(self.ward, ControlKind.CRIMINAL), 1)
        # A crew on one corner of the gang's neighborhood takes that room from the gang.
        apply_turf_push(OrganizationFactory(name="Corner Crew"), self.corner, 20)
        self.assertEqual(territory_units(self.neighborhood, ControlKind.CRIMINAL), 1)

    def test_the_other_kind_of_control_does_not_reduce_units(self):
        apply_turf_push(OrganizationFactory(name="Ashfingers"), self.neighborhood, 50)
        mayor = OrganizationFactory(name="Office of the Lord Mayor")
        create_domain(area=self.city, name="Luxen", owner_org=mayor)

        self.assertEqual(territory_units(self.city, ControlKind.LEGITIMATE), 3)

        baron = OrganizationFactory(name="House Orisant")
        create_domain(area=self.ward, name="Orisant Ward", owner_org=baron)
        self.assertEqual(territory_units(self.city, ControlKind.LEGITIMATE), 0)
        self.assertEqual(territory_units(self.ward, ControlKind.LEGITIMATE), 3)


class CrimeCompositionTests(TestCase):
    def test_room_turf_writes_a_room_modifier_and_leaves_the_area_total_alone(self):
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        corner = _room(neighborhood)
        apply_turf_push(OrganizationFactory(name="Corner Crew"), corner, 30)

        row = LocationValueModifier.objects.get(
            parent_type=LocationParentType.ROOM, room_profile=corner, stat_key=StatKey.CRIME
        )
        self.assertEqual(row.value, 15)
        self.assertEqual(area_stat_total(neighborhood, StatKey.CRIME), 0)

    def test_ward_turf_rolls_down_to_its_neighborhoods(self):
        ward = AreaFactory(level=AreaLevel.WARD)
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=ward)
        apply_turf_push(OrganizationFactory(name="Dread Buns"), ward, 40)
        apply_turf_push(OrganizationFactory(name="Ashfingers"), neighborhood, 20)

        self.assertEqual(area_stat_total(neighborhood, StatKey.CRIME), 20 + 10)


class TerritoryStreamTests(TestCase):
    def setUp(self):
        self.ward = AreaFactory(level=AreaLevel.WARD)
        self.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=self.ward)
        _room(self.neighborhood)
        _room(self.neighborhood)
        self.gang = OrganizationFactory(name="Ashfingers")

    def test_turf_gets_one_territory_stream_that_accrues_by_grip(self):
        turf = apply_turf_push(self.gang, self.neighborhood, 50)

        ensure_territory_streams()
        ensure_territory_streams()

        turf.refresh_from_db()
        stream = turf.income_stream
        self.assertIsNotNone(stream)
        self.assertEqual(stream.kind, IncomeStreamKind.TERRITORY)
        self.assertEqual(stream.organization, self.gang)
        self.assertEqual(OrgIncomeStream.objects.filter(kind=IncomeStreamKind.TERRITORY).count(), 1)
        accrue_income_stream(stream)
        stream.refresh_from_db()
        self.assertEqual(stream.uncollected_pool, 2 * TERRITORY_BASE_PER_UNIT * 50 // 100)
        self.assertEqual(stream.gross_amount, 2 * TERRITORY_BASE_PER_UNIT * 50 // 100)

    def test_a_domain_gets_a_territory_stream_that_accrues_by_prosperity(self):
        baron = OrganizationFactory(name="House Orisant")
        domain = create_domain(area=self.ward, name="Orisant Ward", owner_org=baron)
        domain.prosperity = 100
        domain.save(update_fields=["prosperity"])

        ensure_territory_streams()

        domain.refresh_from_db()
        stream = domain.territory_stream
        self.assertEqual(stream.organization, baron)
        accrue_income_stream(stream)
        stream.refresh_from_db()
        self.assertEqual(stream.uncollected_pool, 2 * TERRITORY_BASE_PER_UNIT * 2)

    def test_a_flip_retargets_the_territory_stream(self):
        turf = apply_turf_push(self.gang, self.neighborhood, 30)
        ensure_territory_streams()
        rival = OrganizationFactory(name="Rival Gang")

        apply_turf_push(rival, self.neighborhood, 60)

        turf.refresh_from_db()
        self.assertEqual(turf.controlling_org, rival)
        self.assertEqual(turf.income_stream.organization, rival)

    def test_contested_ground_has_no_stream(self):
        Turf.objects.create(area=self.neighborhood)

        ensure_territory_streams()

        self.assertFalse(OrgIncomeStream.objects.filter(kind=IncomeStreamKind.TERRITORY).exists())

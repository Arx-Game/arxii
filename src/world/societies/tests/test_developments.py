"""Developments (#4060 slice 2): holdings gain a site, units, a level and a standing."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.agriculture.models import CropType, FieldDetails
from world.agriculture.seeds import ensure_field_kind
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.currency.constants import TERRITORY_BASE_PER_UNIT
from world.currency.services import accrue_income_stream
from world.room_features.factories import RoomFeatureInstanceFactory
from world.societies.constants import ControlKind
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import HoldingSiteKind
from world.societies.houses.factories import HoldingKindFactory
from world.societies.houses.services import (
    HousesServiceError,
    add_holding,
    create_domain,
    site_holding,
)
from world.societies.territory import ensure_domain_stream, territory_gross, territory_units


def _room(area, *, outdoor=True):
    return RoomProfileFactory(area=area, is_outdoor=outdoor)


class HoldingSiteTests(TestCase):
    def setUp(self):
        self.ward = AreaFactory(level=AreaLevel.WARD)
        self.elsewhere = AreaFactory(level=AreaLevel.WARD)
        self.baron = OrganizationFactory(name="House Orisant")
        self.domain = create_domain(area=self.ward, name="Orisant Ward", owner_org=self.baron)
        self.field_row = _room(self.ward)
        self.commons = _room(self.ward)
        self.land_kind = HoldingKindFactory(
            name="Pasture", site_kind=HoldingSiteKind.LAND, units_required=1, base_gross=500
        )

    def test_a_land_holding_needs_an_outdoor_room_under_the_domain(self):
        holding = add_holding(domain=self.domain, kind=self.land_kind, room_profile=self.commons)
        self.assertEqual(holding.room_profile, self.commons)

        with self.assertRaises(HousesServiceError):
            add_holding(domain=self.domain, kind=self.land_kind, room_profile=_room(self.elsewhere))
        with self.assertRaises(HousesServiceError):
            add_holding(
                domain=self.domain,
                kind=self.land_kind,
                room_profile=_room(self.ward, outdoor=False),
            )
        with self.assertRaises(HousesServiceError):
            add_holding(domain=self.domain, kind=self.land_kind)

    def test_land_holdings_use_up_the_domains_units(self):
        big = HoldingKindFactory(name="Estate", site_kind=HoldingSiteKind.LAND, units_required=2)
        add_holding(domain=self.domain, kind=big, room_profile=self.field_row)

        with self.assertRaises(HousesServiceError):
            add_holding(domain=self.domain, kind=self.land_kind, room_profile=self.commons)

    def test_occupied_units_come_out_of_the_territory_gross(self):
        stream = ensure_domain_stream(self.domain)
        self.assertEqual(territory_units(self.ward, ControlKind.LEGITIMATE), 2)
        self.assertEqual(territory_gross(stream), 2 * TERRITORY_BASE_PER_UNIT)

        add_holding(domain=self.domain, kind=self.land_kind, room_profile=self.commons)

        self.assertEqual(territory_gross(stream), 1 * TERRITORY_BASE_PER_UNIT)

    def test_a_farm_needs_a_field_in_the_domain(self):
        farm_kind = HoldingKindFactory(
            name="Farm", site_kind=HoldingSiteKind.LAND, requires_field=True, units_required=1
        )
        wheat = CropType.objects.create(name="Wheat", base_production=10)
        field = FieldDetails.objects.create(
            feature_instance=RoomFeatureInstanceFactory(
                feature_kind=ensure_field_kind(), room_profile=self.field_row
            ),
            crop_type=wheat,
        )
        far_field = FieldDetails.objects.create(
            feature_instance=RoomFeatureInstanceFactory(
                feature_kind=ensure_field_kind(), room_profile=_room(self.elsewhere)
            ),
            crop_type=wheat,
        )

        holding = add_holding(domain=self.domain, kind=farm_kind, field=field)

        self.assertEqual(holding.field, field)
        self.assertEqual(holding.room_profile, self.field_row)
        with self.assertRaises(HousesServiceError):
            add_holding(domain=self.domain, kind=farm_kind, field=far_field)
        with self.assertRaises(HousesServiceError):
            add_holding(domain=self.domain, kind=farm_kind, room_profile=self.commons)

    def test_a_building_holding_needs_a_building_under_the_domain_and_takes_no_units(self):
        inn_kind = HoldingKindFactory(
            name="Inn", site_kind=HoldingSiteKind.BUILDING, units_required=0
        )
        inn = BuildingFactory(area=AreaFactory(level=AreaLevel.BUILDING, parent=self.ward))
        elsewhere_inn = BuildingFactory(
            area=AreaFactory(level=AreaLevel.BUILDING, parent=self.elsewhere)
        )

        holding = add_holding(domain=self.domain, kind=inn_kind, building=inn)

        self.assertEqual(holding.building, inn)
        self.assertEqual(
            territory_gross(ensure_domain_stream(self.domain)), 2 * TERRITORY_BASE_PER_UNIT
        )
        with self.assertRaises(HousesServiceError):
            add_holding(domain=self.domain, kind=inn_kind, building=elsewhere_inn)

    def test_an_unsited_holding_of_a_sited_kind_can_be_placed_later(self):
        holding = add_holding(domain=self.domain, kind=self.land_kind, unsited=True)
        self.assertIsNone(holding.room_profile)

        site_holding(holding, room_profile=self.commons)

        holding.refresh_from_db()
        self.assertEqual(holding.room_profile, self.commons)


class HoldingYieldTests(TestCase):
    def setUp(self):
        self.ward = AreaFactory(level=AreaLevel.WARD)
        self.domain = create_domain(
            area=self.ward, name="Orisant Ward", owner_org=OrganizationFactory(name="Orisant")
        )
        self.kind = HoldingKindFactory(name="Tollhouse", base_gross=1000)

    def test_defaults_yield_the_base(self):
        holding = add_holding(domain=self.domain, kind=self.kind)
        accrue_income_stream(holding.income_stream)
        holding.income_stream.refresh_from_db()
        self.assertEqual(holding.income_stream.uncollected_pool, 1000)

    def test_level_and_standing_scale_the_yield(self):
        holding = add_holding(domain=self.domain, kind=self.kind)
        holding.level = 2
        holding.standing = 100
        holding.save(update_fields=["level", "standing"])

        accrue_income_stream(holding.income_stream)

        holding.income_stream.refresh_from_db()
        self.assertEqual(holding.income_stream.uncollected_pool, 4000)

    def test_an_unsited_holding_of_a_sited_kind_yields_nothing_until_placed(self):
        land = HoldingKindFactory(name="Pasture", site_kind=HoldingSiteKind.LAND, base_gross=500)
        holding = add_holding(domain=self.domain, kind=land, unsited=True)

        accrue_income_stream(holding.income_stream)

        holding.income_stream.refresh_from_db()
        self.assertEqual(holding.income_stream.uncollected_pool, 0)

"""felt_sun_exposure component tests with real fixtures (#2846). SQLite tier —
nothing here fires apply_condition/remove_condition (the PG-only DISTINCT ON path)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.game_clock.constants import TimePhase
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.items.models import GarmentMitigation
from world.locations.constants import StatKey
from world.species.sun_constants import (
    BASE_SUN_DAWN_DUSK,
    BASE_SUN_DAY,
    CLOTHING_COVERAGE_CAP,
    SUN_MITIGATION_TARGET_NAME,
)
from world.species.sun_exposure import felt_sun_exposure


def _day_phase():
    return patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.DAY)


class FeltSunExposureBaseTest(TestCase):
    """Base sunlight gating: outdoor flag, enclosure, IC phase."""

    def setUp(self):
        self.profile = RoomProfileFactory(is_outdoor=True)
        self.room = self.profile.objectdb
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_outdoor_day_full_base(self):
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.base, BASE_SUN_DAY)
        self.assertEqual(exposure.residual, BASE_SUN_DAY)

    def test_dawn_dusk_reduced_base(self):
        for phase in (TimePhase.DAWN, TimePhase.DUSK):
            with patch("world.species.sun_exposure.get_ic_phase", return_value=phase):
                exposure = felt_sun_exposure(self.character, self.room)
            self.assertEqual(exposure.base, BASE_SUN_DAWN_DUSK)

    def test_night_zero(self):
        with patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.NIGHT):
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.residual, 0)

    def test_indoor_zero(self):
        indoor = RoomProfileFactory(is_outdoor=False)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, indoor.objectdb)
        self.assertEqual(exposure.residual, 0)

    def test_roofed_outdoor_zero(self):
        """An authored ROOFED enclosure (covered veranda) blocks direct sun."""
        self.profile.enclosure = RoomEnclosure.ROOFED
        self.profile.save(update_fields=["enclosure"])
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.residual, 0)

    def test_walled_default_outdoor_still_sunny(self):
        """The unauthored WALLED default on an outdoor room does NOT block sun."""
        self.assertEqual(self.profile.enclosure, RoomEnclosure.WALLED)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.base, BASE_SUN_DAY)

    def test_no_room_zero(self):
        with _day_phase():
            exposure = felt_sun_exposure(self.character, None)
        self.assertEqual(exposure.residual, 0)


class FeltSunExposureShadeTest(TestCase):
    """Graded shade from the radiant cascade (#1744) and position shelter (#1756)."""

    def setUp(self):
        self.profile = RoomProfileFactory(is_outdoor=True)
        self.room = self.profile.objectdb
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.db_location = self.room
        self.character.save(update_fields=["db_location"])

    def test_room_shade_is_graded_not_boolean(self):
        from world.conditions.factories import ensure_radiant_damage_type
        from world.locations.constants import KeyType
        from world.locations.models import LocationValueOverride

        LocationValueOverride.objects.create(
            parent_type="room",
            room_profile=self.profile,
            key_type=KeyType.DAMAGE_TYPE,
            damage_type=ensure_radiant_damage_type(),
            value=4,
        )
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.shade, 4)
        self.assertEqual(exposure.residual, BASE_SUN_DAY - 4)

    def test_position_shelter_adds_to_room_shade(self):
        from world.areas.positioning.models import PositionShelter
        from world.areas.positioning.services import (
            add_blueprint_position,
            create_blueprint,
            instantiate_blueprint,
            place_in_position,
        )
        from world.conditions.factories import ensure_radiant_damage_type

        bp = create_blueprint("Courtyard")
        add_blueprint_position(bp, "Tent")
        tent_pos = instantiate_blueprint(bp, self.room)[0]
        PositionShelter.objects.create(
            position=tent_pos,
            damage_type=ensure_radiant_damage_type(),
            value=100,
        )
        place_in_position(self.character, tent_pos)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.residual, 0)
        self.assertEqual(exposure.shade_only_residual, 0)


class FeltSunExposureClothingTest(TestCase):
    """Coverage from non-revealing garments; authored + resonance-imbued SUN rows."""

    def setUp(self):
        self.profile = RoomProfileFactory(is_outdoor=True)
        self.room = self.profile.objectdb
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def _equip(self, template, region, layer=EquipmentLayer.BASE):
        EquippedItemFactory(
            character=self.sheet,
            item_instance=ItemInstanceFactory(template=template),
            body_region=region,
            equipment_layer=layer,
        )
        self.character.equipped_items.invalidate()

    def test_nude_zero_clothing_protection(self):
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.coverage, 0)
        self.assertEqual(exposure.authored_sun, 0)

    def test_nonrevealing_garment_covers_its_regions(self):
        tunic = ItemTemplateFactory(is_revealing=False)
        self._equip(tunic, BodyRegion.TORSO)
        self._equip(ItemTemplateFactory(is_revealing=False), BodyRegion.LEFT_ARM)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.coverage, 2)

    def test_revealing_garment_gives_no_coverage(self):
        sheer = ItemTemplateFactory(is_revealing=True)
        self._equip(sheer, BodyRegion.TORSO)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.coverage, 0)

    def test_coverage_caps(self):
        regions = [
            BodyRegion.HEAD,
            BodyRegion.FACE,
            BodyRegion.NECK,
            BodyRegion.SHOULDERS,
            BodyRegion.TORSO,
            BodyRegion.BACK,
            BodyRegion.LEFT_ARM,
            BodyRegion.RIGHT_ARM,
            BodyRegion.LEFT_LEG,
            BodyRegion.RIGHT_LEG,
        ]
        for region in regions:
            self._equip(ItemTemplateFactory(is_revealing=False), region)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.coverage, CLOTHING_COVERAGE_CAP)

    def test_jewelry_regions_give_no_coverage(self):
        ring = ItemTemplateFactory(is_revealing=False)
        self._equip(ring, BodyRegion.LEFT_FINGER, EquipmentLayer.ACCESSORY)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.coverage, 0)

    def test_parasol_authored_sun_value_counts_from_hand_slot(self):
        parasol = ItemTemplateFactory(is_revealing=True)
        GarmentMitigation.objects.create(item_template=parasol, stat_key=StatKey.SUN, value=5)
        self._equip(parasol, BodyRegion.LEFT_HAND, EquipmentLayer.ACCESSORY)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.authored_sun, 5)
        self.assertEqual(exposure.resonance_sun, 0)

    def test_resonance_imbued_sun_rows_tracked_separately(self):
        """The sun-flex breakdown (#2377): resonance-imbued protection is its own field."""
        from world.magic.factories import ResonanceFactory

        wrap = ItemTemplateFactory(is_revealing=True)
        GarmentMitigation.objects.create(
            item_template=wrap,
            stat_key=StatKey.SUN,
            value=9,
            resonance=ResonanceFactory(),
        )
        self._equip(wrap, BodyRegion.TORSO)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.resonance_sun, 9)
        self.assertEqual(exposure.authored_sun, 0)
        self.assertEqual(exposure.coverage, 0)
        self.assertEqual(exposure.residual, BASE_SUN_DAY - 9)

    def test_other_axis_mitigation_ignored(self):
        coat = ItemTemplateFactory(is_revealing=True)
        GarmentMitigation.objects.create(item_template=coat, stat_key=StatKey.COLD, value=50)
        self._equip(coat, BodyRegion.TORSO)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.authored_sun, 0)


class FeltSunExposureMagicTest(TestCase):
    """sun_mitigation ModifierTarget lane (content-repo-owned; absent target reads 0)."""

    def setUp(self):
        self.profile = RoomProfileFactory(is_outdoor=True)
        self.room = self.profile.objectdb
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_absent_target_reads_zero(self):
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.magic, 0)

    def test_modifier_total_reduces_residual(self):
        from world.mechanics.factories import (
            CharacterModifierFactory,
            ModifierTargetFactory,
        )

        target = ModifierTargetFactory(name=SUN_MITIGATION_TARGET_NAME)
        CharacterModifierFactory(character=self.sheet, target=target, value=4)
        with _day_phase():
            exposure = felt_sun_exposure(self.character, self.room)
        self.assertEqual(exposure.magic, 4)
        self.assertEqual(exposure.residual, BASE_SUN_DAY - 4)

"""Catering by container (#2869): flagged vessels, tagged provisions, souvenirs.

SQLite tier. Nothing is consumed here — every assertion is about tags on
items that are still real and still in the world.
"""

from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from world.character_sheets.factories import CharacterSheetFactory
from world.events.constants import EventStatus
from world.events.models import CateringRole, EventCatering, EventHost
from world.events.services import (
    _award_catering_prestige,
    _catering_score,
    catering_history,
    designate_catering_container,
    tag_catered_provision,
)
from world.events.types import EventError
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory


def _instance(sheet, *, key, container=False, consumable=False, quality=None):
    obj = create_object("typeclasses.objects.Object", key=key, nohome=True)
    template = ItemTemplateFactory(
        name=key,
        is_container=container,
        is_consumable=consumable,
        max_charges=1 if consumable else 0,
    )
    return ItemInstanceFactory(
        template=template,
        holder_character_sheet=sheet,
        game_object=obj,
        quality_tier=quality,
    )


class CateringContainerTest(TestCase):
    def setUp(self):
        from world.events.factories import EventFactory

        self.event = EventFactory(status=EventStatus.ACTIVE)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.amphora = _instance(self.sheet, key="amphora", container=True)

    def test_flagging_a_vessel_records_it_without_consuming_it(self):
        from world.items.models import ItemInstance

        row = designate_catering_container(self.event, self.character, self.amphora)
        self.assertEqual(row.role, CateringRole.CONTAINER)
        self.assertTrue(ItemInstance.objects.filter(pk=self.amphora.pk).exists())

    def test_only_containers_can_be_flagged(self):
        loaf = _instance(self.sheet, key="loaf", consumable=True)
        with self.assertRaises(EventError):
            designate_catering_container(self.event, self.character, loaf)

    def test_flagging_twice_is_idempotent(self):
        designate_catering_container(self.event, self.character, self.amphora)
        designate_catering_container(self.event, self.character, self.amphora)
        self.assertEqual(EventCatering.objects.filter(item_instance=self.amphora).count(), 1)

    def test_finished_events_refuse_new_vessels(self):
        self.event.status = EventStatus.COMPLETED
        self.event.save(update_fields=["status"])
        with self.assertRaises(EventError):
            designate_catering_container(self.event, self.character, self.amphora)


class ProvisionTaggingTest(TestCase):
    def setUp(self):
        from world.events.factories import EventFactory

        self.event = EventFactory(status=EventStatus.ACTIVE)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.amphora = _instance(self.sheet, key="amphora", container=True)
        designate_catering_container(self.event, self.character, self.amphora)

    def test_consumable_in_a_flagged_vessel_tags(self):
        wine = _instance(self.sheet, key="wine", consumable=True)
        row = tag_catered_provision(wine, self.amphora, self.character)
        self.assertIsNotNone(row)
        self.assertEqual(row.role, CateringRole.PROVISION)
        self.assertEqual(row.event, self.event)

    def test_non_consumables_are_just_storage(self):
        knife = _instance(self.sheet, key="knife")
        self.assertIsNone(tag_catered_provision(knife, self.amphora, self.character))

    def test_unflagged_vessels_tag_nothing(self):
        crate = _instance(self.sheet, key="crate", container=True)
        wine = _instance(self.sheet, key="wine", consumable=True)
        self.assertIsNone(tag_catered_provision(wine, crate, self.character))

    def test_the_tag_survives_taking_the_food_back_out(self):
        """Setting it out was the contribution — removing it never untags."""
        wine = _instance(self.sheet, key="wine", consumable=True)
        tag_catered_provision(wine, self.amphora, self.character)
        wine.contained_in = None
        wine.save(update_fields=["contained_in"])
        self.assertEqual(_catering_score(self.event), 1)

    def test_shuffling_in_and_out_cannot_farm_prestige(self):
        wine = _instance(self.sheet, key="wine", consumable=True)
        for _ in range(5):
            tag_catered_provision(wine, self.amphora, self.character)
        self.assertEqual(
            EventCatering.objects.filter(event=self.event, role=CateringRole.PROVISION).count(),
            1,
        )


class CateringPrestigeTest(TestCase):
    def setUp(self):
        from world.events.factories import EventFactory

        self.event = EventFactory(status=EventStatus.ACTIVE)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.amphora = _instance(self.sheet, key="amphora", container=True)
        designate_catering_container(self.event, self.character, self.amphora)

    def test_score_reads_live_quality(self):
        from world.items.factories import QualityTierFactory

        fine = QualityTierFactory(name="Fine", stat_multiplier="1.25")
        master = QualityTierFactory(name="Masterwork", stat_multiplier="1.60")
        tag_catered_provision(
            _instance(self.sheet, key="wine", consumable=True, quality=fine),
            self.amphora,
            self.character,
        )
        tag_catered_provision(
            _instance(self.sheet, key="roast", consumable=True, quality=master),
            self.amphora,
            self.character,
        )
        self.assertEqual(_catering_score(self.event), round(1.25 + 1.60))

    def test_vessels_do_not_count_toward_the_spread(self):
        """Flagging ten empty tables earns nothing — the food is the gift."""
        for i in range(3):
            table = _instance(self.sheet, key=f"table{i}", container=True)
            designate_catering_container(self.event, self.character, table)
        self.assertEqual(_catering_score(self.event), 0)

    def test_completion_mints_the_host_deed(self):
        from world.items.factories import QualityTierFactory

        host_persona = CharacterSheetFactory().primary_persona
        EventHost.objects.create(event=self.event, persona=host_persona, is_primary=True)
        master = QualityTierFactory(name="Masterwork", stat_multiplier="1.60")
        for key in ("wine", "roast"):
            tag_catered_provision(
                _instance(self.sheet, key=key, consumable=True, quality=master),
                self.amphora,
                self.character,
            )
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_catering_prestige(self.event)
        deed.assert_called_once()
        self.assertEqual(deed.call_args.args[0], host_persona)


class CateringSouvenirTest(TestCase):
    def test_an_item_remembers_every_event_it_served(self):
        from world.events.factories import EventFactory

        sheet = CharacterSheetFactory()
        character = sheet.character
        amphora = _instance(sheet, key="amphora", container=True)
        first = EventFactory(status=EventStatus.ACTIVE, name="Big Bob's Nameday")
        second = EventFactory(status=EventStatus.ACTIVE, name="The Harvest Ball")
        designate_catering_container(first, character, amphora)
        designate_catering_container(second, character, amphora)
        names = {row.event.name for row in catering_history(amphora)}
        self.assertEqual(names, {"Big Bob's Nameday", "The Harvest Ball"})

    def test_examine_renders_the_souvenir_line(self):
        from typeclasses.mixins import _maybe_render_catering_history
        from world.events.factories import EventFactory

        sheet = CharacterSheetFactory()
        amphora = _instance(sheet, key="amphora", container=True)
        event = EventFactory(status=EventStatus.ACTIVE, name="Big Bob's Example Event")
        designate_catering_container(event, sheet.character, amphora)
        line = _maybe_render_catering_history(amphora.game_object)
        self.assertIsNotNone(line)
        self.assertIn("used for catering at Big Bob's Example Event", line)

    def test_untouched_items_render_nothing(self):
        from typeclasses.mixins import _maybe_render_catering_history

        sheet = CharacterSheetFactory()
        plain = _instance(sheet, key="rock")
        self.assertIsNone(_maybe_render_catering_history(plain.game_object))

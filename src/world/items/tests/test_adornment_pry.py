"""Tests for risky adornment prying (Build 0b slice 6)."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.action_points.factories import ActionPointPoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.exceptions import CraftingCostUnaffordable
from world.items.factories import (
    GemGradeFactory,
    GemInstanceDetailsFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.items.gems.constants import GemAxis
from world.items.gems.models import Adornment
from world.items.gems.services import adorn_item, pry_adornment
from world.items.models import ItemInstance
from world.items.services.pricing import appraise
from world.traits.factories import CheckOutcomeFactory


def _gem(value=100):
    """A gem ItemInstance worth exactly ``value`` (all grades ×1.0)."""
    inst = ItemInstanceFactory(template=ItemTemplateFactory(value=value))
    GemInstanceDetailsFactory(
        item_instance=inst,
        size_grade=GemGradeFactory(axis=GemAxis.SIZE, multiplier=Decimal("1.0")),
        purity_grade=GemGradeFactory(axis=GemAxis.PURITY, multiplier=Decimal("1.0")),
        cut_grade=GemGradeFactory(axis=GemAxis.CUT, multiplier=Decimal("1.0")),
    )
    inst.refresh_from_db()
    return inst


class PryAdornmentTests(TestCase):
    def setUp(self):
        self.character = CharacterFactory()
        self.pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200)
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory()
        self.host = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Scepter", value=50, adornment_capacity=3),
            lore_value=0,
        )

    def _adorn(self, worth=100):
        gem = _gem(value=worth)
        adornment = adorn_item(host_instance=self.host, gem_instance=gem)
        self.host.refresh_from_db()
        return adornment, gem

    def test_success_frees_the_gem_and_drops_host_worth(self):
        adornment, gem = self._adorn(worth=100)
        self.assertEqual(appraise(self.host), 50 + 100)  # base + adorned worth
        with force_check_outcome(CheckOutcomeFactory(name="PryOk", success_level=2)):
            result = pry_adornment(
                adornment=adornment,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
                check_type=self.check_type,
                ap_cost=5,
            )
        self.assertFalse(result.shattered)
        self.assertEqual(result.freed_gem, gem)
        gem.refresh_from_db()
        self.assertEqual(gem.holder_character_sheet_id, self.sheet.pk)  # back in inventory
        self.assertFalse(Adornment.objects.filter(pk=adornment.pk).exists())
        self.host.refresh_from_db()
        self.assertEqual(appraise(self.host), 50)  # worth dropped back to base

    def test_botch_shatters_the_gem(self):
        adornment, gem = self._adorn(worth=100)
        gem_pk = gem.pk
        with force_check_outcome(CheckOutcomeFactory(name="PryBotch", success_level=-1)):
            result = pry_adornment(
                adornment=adornment,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
                check_type=self.check_type,
                ap_cost=5,
            )
        self.assertTrue(result.shattered)
        self.assertIsNone(result.freed_gem)
        self.assertFalse(ItemInstance.objects.filter(pk=gem_pk).exists())  # destroyed
        self.assertFalse(Adornment.objects.filter(pk=adornment.pk).exists())
        self.host.refresh_from_db()
        self.assertEqual(appraise(self.host), 50)  # worth dropped either way

    def test_ap_spent_on_the_attempt(self):
        adornment, _ = self._adorn()
        with force_check_outcome(CheckOutcomeFactory(name="PryAp", success_level=1)):
            pry_adornment(
                adornment=adornment,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
                check_type=self.check_type,
                ap_cost=5,
            )
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 195)

    def test_unaffordable_ap_raises(self):
        adornment, _ = self._adorn()
        self.pool.current = 2
        self.pool.save(update_fields=["current"])
        with self.assertRaises(CraftingCostUnaffordable):
            pry_adornment(
                adornment=adornment,
                crafter_character=self.character,
                crafter_character_sheet=self.sheet,
                check_type=self.check_type,
                ap_cost=5,
            )

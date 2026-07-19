"""Tests for gem adornment (Build 0b slice 2)."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.items.exceptions import (
    AdornmentCapacityExceeded,
    GemAlreadyAdorned,
    NotAGem,
)
from world.items.factories import (
    GemGradeFactory,
    GemInstanceDetailsFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
)
from world.items.gems.constants import GemAxis
from world.items.gems.models import Adornment
from world.items.gems.services import adorn_item, adorned_materials
from world.items.services.pricing import appraise


def _make_gem(value=100, size="2.0", purity="2.0", cut="1.0"):
    """A gem ItemInstance worth ``value × size × purity × cut``."""
    tmpl = ItemTemplateFactory(value=value)
    inst = ItemInstanceFactory(template=tmpl)
    GemInstanceDetailsFactory(
        item_instance=inst,
        size_grade=GemGradeFactory(axis=GemAxis.SIZE, multiplier=Decimal(size)),
        purity_grade=GemGradeFactory(axis=GemAxis.PURITY, multiplier=Decimal(purity)),
        cut_grade=GemGradeFactory(axis=GemAxis.CUT, multiplier=Decimal(cut)),
    )
    inst.refresh_from_db()
    return inst


class AdornItemTests(TestCase):
    def _host(self, capacity=3, value=50):
        tmpl = ItemTemplateFactory(name="Scepter", value=value, adornment_capacity=capacity)
        return ItemInstanceFactory(template=tmpl, lore_value=0)

    def test_adorn_creates_record_and_raises_host_worth(self):
        host = self._host(value=50)
        gem = _make_gem(value=100, size="2.0", purity="2.0", cut="1.0")  # worth 400
        adornment = adorn_item(host_instance=host, gem_instance=gem, narration="the pommel stone")

        self.assertEqual(adornment.host_instance, host)
        self.assertIn(adornment, host.adornments.all())
        host.refresh_from_db()
        # host worth = base 50 (no tier) + adorned gem worth 400
        self.assertEqual(appraise(host), 450)

    def test_adorn_embeds_the_gem(self):
        host = self._host()
        gem = _make_gem()
        adorn_item(host_instance=host, gem_instance=gem)
        gem.refresh_from_db()
        self.assertIsNone(gem.holder_character_sheet_id)  # no longer carried
        self.assertEqual(gem.adorned_on.host_instance, host)

    def test_non_gem_rejected(self):
        host = self._host()
        plain = ItemInstanceFactory()  # not a gem
        with self.assertRaises(NotAGem):
            adorn_item(host_instance=host, gem_instance=plain)

    def test_gem_already_adorned_rejected(self):
        host = self._host()
        gem = _make_gem()
        adorn_item(host_instance=host, gem_instance=gem)
        other_host = self._host()
        with self.assertRaises(GemAlreadyAdorned):
            adorn_item(host_instance=other_host, gem_instance=gem)

    def test_capacity_gate(self):
        host = self._host(capacity=1)
        adorn_item(host_instance=host, gem_instance=_make_gem())
        with self.assertRaises(AdornmentCapacityExceeded):
            adorn_item(host_instance=host, gem_instance=_make_gem())

    def test_capacity_zero_rejects_all(self):
        host = self._host(capacity=0)
        with self.assertRaises(AdornmentCapacityExceeded):
            adorn_item(host_instance=host, gem_instance=_make_gem())


class AdornedMaterialsSeamTests(TestCase):
    def test_seam_lists_gem_types_on_the_piece(self):
        host = ItemInstanceFactory(template=ItemTemplateFactory(name="Crown", adornment_capacity=5))
        ruby = _make_gem()
        sapphire = _make_gem()
        adorn_item(host_instance=host, gem_instance=ruby)
        adorn_item(host_instance=host, gem_instance=sapphire)
        templates = adorned_materials(host)
        self.assertCountEqual(templates, [ruby.template, sapphire.template])
        # magic-readable: the piece carries the ruby's template
        self.assertTrue(host.adornments.filter(gem_instance__template=ruby.template).exists())

    def test_no_adornments_empty_seam(self):
        host = ItemInstanceFactory()
        self.assertEqual(adorned_materials(host), [])
        self.assertFalse(Adornment.objects.filter(host_instance=host).exists())

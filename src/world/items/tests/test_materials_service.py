"""Tests for world.items.services.materials — shared material-consumption helper.

Covers:
- gather_consumable_pks: sufficient supply returns the expected PKs (no raise)
- gather_consumable_pks: insufficient quantity raises InsufficientMaterials with
  structured requirement + provided_qty attrs
- gather_consumable_pks: min_quality_tier filtering excludes low-tier instances
- consume_pks: deletes exactly the requested PKs; other rows are untouched
"""

from django.test import TestCase

from world.items.exceptions import InsufficientMaterials
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, QualityTierFactory
from world.items.models import ItemInstance
from world.items.services.materials import consume_pks, gather_consumable_pks, meets_quality_tier

# ---------------------------------------------------------------------------
# Minimal duck-typed requirement for tests
# ---------------------------------------------------------------------------


class _Req:
    """Duck-typed stand-in for RitualComponentRequirement / CraftingMaterialRequirement."""

    def __init__(self, item_template, quantity, min_quality_tier=None):
        self.item_template = item_template
        self.item_template_id = item_template.pk
        self.quantity = quantity
        self.min_quality_tier = min_quality_tier
        self.min_quality_tier_id = min_quality_tier.pk if min_quality_tier is not None else None


# ---------------------------------------------------------------------------
# meets_quality_tier
# ---------------------------------------------------------------------------


class MeetsQualityTierTests(TestCase):
    """Unit tests for meets_quality_tier predicate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.low_tier = QualityTierFactory(name="Low", sort_order=10)
        cls.high_tier = QualityTierFactory(name="High", sort_order=20)
        cls.template = ItemTemplateFactory()
        cls.inst_low = ItemInstanceFactory(template=cls.template, quality_tier=cls.low_tier)
        cls.inst_high = ItemInstanceFactory(template=cls.template, quality_tier=cls.high_tier)
        cls.inst_no_tier = ItemInstanceFactory(template=cls.template, quality_tier=None)

    def test_no_minimum_always_passes(self) -> None:
        """When min_quality_tier_id is None any instance qualifies."""
        req = _Req(self.template, 1, min_quality_tier=None)
        self.assertTrue(meets_quality_tier(self.inst_no_tier, req))
        self.assertTrue(meets_quality_tier(self.inst_low, req))
        self.assertTrue(meets_quality_tier(self.inst_high, req))

    def test_instance_without_tier_fails_when_minimum_set(self) -> None:
        """An instance with no quality_tier is excluded when a minimum is required."""
        req = _Req(self.template, 1, min_quality_tier=self.low_tier)
        self.assertFalse(meets_quality_tier(self.inst_no_tier, req))

    def test_equal_sort_order_passes(self) -> None:
        """An instance at exactly the minimum sort_order satisfies the requirement."""
        req = _Req(self.template, 1, min_quality_tier=self.low_tier)
        self.assertTrue(meets_quality_tier(self.inst_low, req))

    def test_higher_sort_order_passes(self) -> None:
        req = _Req(self.template, 1, min_quality_tier=self.low_tier)
        self.assertTrue(meets_quality_tier(self.inst_high, req))

    def test_lower_sort_order_fails(self) -> None:
        req = _Req(self.template, 1, min_quality_tier=self.high_tier)
        self.assertFalse(meets_quality_tier(self.inst_low, req))


# ---------------------------------------------------------------------------
# gather_consumable_pks — sufficient supply
# ---------------------------------------------------------------------------


class GatherConsumablePksSufficientTests(TestCase):
    """gather_consumable_pks returns PKs without raising when supply is adequate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ItemTemplateFactory()
        cls.inst1 = ItemInstanceFactory(template=cls.template, quantity=2)
        cls.inst2 = ItemInstanceFactory(template=cls.template, quantity=3)

    def test_single_requirement_single_instance(self) -> None:
        """One requirement, one instance with sufficient qty — returns that PK."""
        req = _Req(self.template, 2)
        pks = gather_consumable_pks(available=[self.inst1], requirements=[req])
        self.assertIn(self.inst1.pk, pks)

    def test_single_requirement_multiple_instances(self) -> None:
        """Requirement satisfied across multiple instances — all needed PKs returned."""
        req = _Req(self.template, 4)
        pks = gather_consumable_pks(available=[self.inst1, self.inst2], requirements=[req])
        # Both instances needed (qty 2+3=5 >= 4); at minimum inst1 + inst2 appear.
        self.assertIn(self.inst1.pk, pks)
        self.assertIn(self.inst2.pk, pks)

    def test_greedy_prune_stops_early(self) -> None:
        """Greedy logic stops adding PKs once the running qty is satisfied."""
        # inst2 alone (qty=3) satisfies requirement=3; inst1 should NOT be needed.
        req = _Req(self.template, 3)
        pks = gather_consumable_pks(available=[self.inst2], requirements=[req])
        self.assertIn(self.inst2.pk, pks)
        self.assertNotIn(self.inst1.pk, pks)

    def test_empty_requirements_returns_empty(self) -> None:
        """No requirements → empty pk list, no error."""
        pks = gather_consumable_pks(available=[self.inst1], requirements=[])
        self.assertEqual(pks, [])

    def test_no_double_count_across_requirements(self) -> None:
        """The same instance PK cannot be allocated to two requirements simultaneously."""
        template_a = ItemTemplateFactory()
        template_b = ItemTemplateFactory()
        inst_a = ItemInstanceFactory(template=template_a, quantity=1)
        inst_b = ItemInstanceFactory(template=template_b, quantity=1)
        req_a = _Req(template_a, 1)
        req_b = _Req(template_b, 1)
        pks = gather_consumable_pks(available=[inst_a, inst_b], requirements=[req_a, req_b])
        self.assertIn(inst_a.pk, pks)
        self.assertIn(inst_b.pk, pks)
        # No duplicates.
        self.assertEqual(len(pks), len(set(pks)))


# ---------------------------------------------------------------------------
# gather_consumable_pks — insufficient quantity
# ---------------------------------------------------------------------------


class GatherConsumablePksInsufficientTests(TestCase):
    """gather_consumable_pks raises InsufficientMaterials when supply is inadequate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ItemTemplateFactory()
        cls.inst = ItemInstanceFactory(template=cls.template, quantity=1)

    def test_no_supply_raises(self) -> None:
        """Zero available items → InsufficientMaterials with provided_qty=0."""
        req = _Req(self.template, 1)
        with self.assertRaises(InsufficientMaterials) as ctx:
            gather_consumable_pks(available=[], requirements=[req])
        exc = ctx.exception
        self.assertEqual(exc.provided_qty, 0)
        self.assertIs(exc.requirement, req)

    def test_partial_supply_raises(self) -> None:
        """qty=1 for requirement=3 → InsufficientMaterials."""
        req = _Req(self.template, 3)
        with self.assertRaises(InsufficientMaterials) as ctx:
            gather_consumable_pks(available=[self.inst], requirements=[req])
        exc = ctx.exception
        self.assertEqual(exc.provided_qty, 1)

    def test_wrong_template_raises(self) -> None:
        """Instance with non-matching template doesn't count."""
        other_template = ItemTemplateFactory()
        req = _Req(other_template, 1)
        with self.assertRaises(InsufficientMaterials):
            gather_consumable_pks(available=[self.inst], requirements=[req])

    def test_insufficient_materials_has_user_message(self) -> None:
        """InsufficientMaterials carries a non-empty user_message."""
        req = _Req(self.template, 3)
        with self.assertRaises(InsufficientMaterials) as ctx:
            gather_consumable_pks(available=[self.inst], requirements=[req])
        self.assertTrue(ctx.exception.user_message)


# ---------------------------------------------------------------------------
# gather_consumable_pks — min_quality_tier filtering
# ---------------------------------------------------------------------------


class GatherConsumablePksQualityFilterTests(TestCase):
    """Low-tier instances are excluded when min_quality_tier is set."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.low = QualityTierFactory(name="Low QT", sort_order=10)
        cls.high = QualityTierFactory(name="High QT", sort_order=20)
        cls.template = ItemTemplateFactory()
        cls.low_inst = ItemInstanceFactory(template=cls.template, quality_tier=cls.low)
        cls.high_inst = ItemInstanceFactory(template=cls.template, quality_tier=cls.high)

    def test_low_tier_excluded_from_count(self) -> None:
        """Low-tier instance doesn't satisfy a high-tier requirement."""
        req = _Req(self.template, 1, min_quality_tier=self.high)
        # Only low_inst is available — insufficient because it doesn't meet the tier.
        with self.assertRaises(InsufficientMaterials) as ctx:
            gather_consumable_pks(available=[self.low_inst], requirements=[req])
        exc = ctx.exception
        self.assertEqual(exc.provided_qty, 0)

    def test_high_tier_satisfies_low_requirement(self) -> None:
        """High-tier instance satisfies a low min_quality_tier."""
        req = _Req(self.template, 1, min_quality_tier=self.low)
        pks = gather_consumable_pks(available=[self.high_inst], requirements=[req])
        self.assertIn(self.high_inst.pk, pks)

    def test_mixed_only_high_tier_selected(self) -> None:
        """With both tiers available, only high-tier instance is selected for a high req."""
        req = _Req(self.template, 1, min_quality_tier=self.high)
        pks = gather_consumable_pks(available=[self.low_inst, self.high_inst], requirements=[req])
        self.assertIn(self.high_inst.pk, pks)
        self.assertNotIn(self.low_inst.pk, pks)


# ---------------------------------------------------------------------------
# consume_pks
# ---------------------------------------------------------------------------


class ConsumePksTests(TestCase):
    """consume_pks deletes exactly the given PKs and leaves others untouched."""

    def test_deletes_targeted_pks(self) -> None:
        """PKs passed to consume_pks are deleted from the DB."""
        template = ItemTemplateFactory()
        inst = ItemInstanceFactory(template=template)
        consume_pks([inst.pk])
        self.assertFalse(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_leaves_other_pks_intact(self) -> None:
        """ItemInstance rows NOT in the PK list are unaffected."""
        template = ItemTemplateFactory()
        to_delete = ItemInstanceFactory(template=template)
        to_keep = ItemInstanceFactory(template=template)
        consume_pks([to_delete.pk])
        self.assertTrue(ItemInstance.objects.filter(pk=to_keep.pk).exists())

    def test_empty_pk_list_is_noop(self) -> None:
        """An empty PK list does not raise and does not delete any rows."""
        template = ItemTemplateFactory()
        inst = ItemInstanceFactory(template=template)
        consume_pks([])
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())

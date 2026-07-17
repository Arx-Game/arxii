"""Tests for world.items.services.materials — shared material-consumption helper.

Covers:
- gather_consumable_pks: sufficient supply returns the expected allocations (no raise)
- gather_consumable_pks: insufficient quantity raises InsufficientMaterials with
  structured requirement + provided_qty attrs
- gather_consumable_pks: min_quality_tier filtering excludes low-tier instances
- consume_materials: partial consume decrements quantity; full consume deletes row;
  split across stacks decrements each correctly
"""

from django.test import TestCase

from world.items.exceptions import InsufficientMaterials
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, QualityTierFactory
from world.items.models import ItemInstance
from world.items.services.materials import (
    consume_materials,
    gather_consumable_pks,
    meets_quality_tier,
)

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
    """gather_consumable_pks returns allocations without raising when supply is adequate."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ItemTemplateFactory()
        cls.inst1 = ItemInstanceFactory(template=cls.template, quantity=2)
        cls.inst2 = ItemInstanceFactory(template=cls.template, quantity=3)

    def test_single_requirement_single_instance(self) -> None:
        """One requirement, one instance with sufficient qty — returns that instance."""
        req = _Req(self.template, 2)
        allocations = gather_consumable_pks(available=[self.inst1], requirements=[req])
        self.assertEqual(allocations, [(self.inst1, 2)])

    def test_single_requirement_multiple_instances(self) -> None:
        """Requirement satisfied across multiple instances — all needed allocations returned."""
        req = _Req(self.template, 4)
        allocations = gather_consumable_pks(available=[self.inst1, self.inst2], requirements=[req])
        # Both instances needed (qty 2+3=5 >= 4); inst1 fully consumed, inst2 partially.
        self.assertEqual(allocations, [(self.inst1, 2), (self.inst2, 2)])

    def test_greedy_prune_stops_early(self) -> None:
        """Greedy logic stops adding allocations once the running qty is satisfied."""
        # inst2 alone (qty=3) satisfies requirement=3; inst1 should NOT be needed.
        req = _Req(self.template, 3)
        allocations = gather_consumable_pks(available=[self.inst2], requirements=[req])
        self.assertEqual(allocations, [(self.inst2, 3)])

    def test_partial_consume_takes_only_what_is_needed(self) -> None:
        """Requirement of 1 against a stack of 5 returns amount=1, not 5."""
        inst = ItemInstanceFactory(template=self.template, quantity=5)
        req = _Req(self.template, 1)
        allocations = gather_consumable_pks(available=[inst], requirements=[req])
        self.assertEqual(allocations, [(inst, 1)])

    def test_empty_requirements_returns_empty(self) -> None:
        """No requirements → empty allocations list, no error."""
        allocations = gather_consumable_pks(available=[self.inst1], requirements=[])
        self.assertEqual(allocations, [])

    def test_no_double_count_across_requirements(self) -> None:
        """The same instance cannot be allocated to two requirements simultaneously."""
        template_a = ItemTemplateFactory()
        template_b = ItemTemplateFactory()
        inst_a = ItemInstanceFactory(template=template_a, quantity=1)
        inst_b = ItemInstanceFactory(template=template_b, quantity=1)
        req_a = _Req(template_a, 1)
        req_b = _Req(template_b, 1)
        allocations = gather_consumable_pks(available=[inst_a, inst_b], requirements=[req_a, req_b])
        pks = [inst.pk for inst, _ in allocations]
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
        allocations = gather_consumable_pks(available=[self.high_inst], requirements=[req])
        self.assertEqual(allocations, [(self.high_inst, 1)])

    def test_mixed_only_high_tier_selected(self) -> None:
        """With both tiers available, only high-tier instance is selected for a high req."""
        req = _Req(self.template, 1, min_quality_tier=self.high)
        allocations = gather_consumable_pks(
            available=[self.low_inst, self.high_inst], requirements=[req]
        )
        self.assertEqual(allocations, [(self.high_inst, 1)])


# ---------------------------------------------------------------------------
# consume_materials
# ---------------------------------------------------------------------------


class ConsumeMaterialsTests(TestCase):
    """consume_materials decrements partial stacks and deletes depleted ones."""

    def test_partial_consume_decrements_quantity(self) -> None:
        """Consuming 1 from a stack of 5 leaves quantity=4; row survives."""
        template = ItemTemplateFactory()
        inst = ItemInstanceFactory(template=template, quantity=5)
        consume_materials([(inst, 1)])
        inst.refresh_from_db()
        self.assertEqual(inst.quantity, 4)
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_full_consume_deletes_row(self) -> None:
        """Consuming the full quantity deletes the row."""
        template = ItemTemplateFactory()
        inst = ItemInstanceFactory(template=template, quantity=5)
        consume_materials([(inst, 5)])
        self.assertFalse(ItemInstance.objects.filter(pk=inst.pk).exists())

    def test_split_across_stacks(self) -> None:
        """A requirement split across two stacks: first depleted, second survives."""
        template = ItemTemplateFactory()
        inst1 = ItemInstanceFactory(template=template, quantity=5)
        inst2 = ItemInstanceFactory(template=template, quantity=3)
        consume_materials([(inst1, 5), (inst2, 2)])
        self.assertFalse(ItemInstance.objects.filter(pk=inst1.pk).exists())
        inst2.refresh_from_db()
        self.assertEqual(inst2.quantity, 1)

    def test_leaves_other_instances_intact(self) -> None:
        """Instances NOT in the allocations list are unaffected."""
        template = ItemTemplateFactory()
        to_consume = ItemInstanceFactory(template=template, quantity=3)
        to_keep = ItemInstanceFactory(template=template, quantity=2)
        consume_materials([(to_consume, 3)])
        self.assertFalse(ItemInstance.objects.filter(pk=to_consume.pk).exists())
        self.assertTrue(ItemInstance.objects.filter(pk=to_keep.pk).exists())
        to_keep.refresh_from_db()
        self.assertEqual(to_keep.quantity, 2)

    def test_empty_allocations_is_noop(self) -> None:
        """An empty allocations list does not raise and does not modify any rows."""
        template = ItemTemplateFactory()
        inst = ItemInstanceFactory(template=template, quantity=1)
        consume_materials([])
        self.assertTrue(ItemInstance.objects.filter(pk=inst.pk).exists())
        inst.refresh_from_db()
        self.assertEqual(inst.quantity, 1)

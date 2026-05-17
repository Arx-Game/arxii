"""Tests for ConsequencePool and ConsequencePoolEntry models."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.services import get_effective_consequences
from actions.types import WeightedConsequence
from world.checks.factories import ConsequenceFactory
from world.traits.factories import CheckOutcomeFactory


class ConsequencePoolModelTests(TestCase):
    """Test ConsequencePool model validation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.parent_pool = ConsequencePoolFactory(name="Parent Pool")
        cls.child_pool = ConsequencePoolFactory(name="Child Pool", parent=cls.parent_pool)

    def test_pool_creation(self) -> None:
        pool = ConsequencePoolFactory(name="Test Pool")
        assert pool.name == "Test Pool"
        assert pool.parent is None

    def test_child_pool_with_parent(self) -> None:
        assert self.child_pool.parent == self.parent_pool

    def test_grandchild_rejected(self) -> None:
        grandchild = ConsequencePoolFactory.build(name="Grandchild", parent=self.child_pool)
        with self.assertRaises(ValidationError):
            grandchild.full_clean()

    def test_self_parent_rejected(self) -> None:
        pool = ConsequencePoolFactory()
        pool.parent = pool
        with self.assertRaises(ValidationError):
            pool.full_clean()

    def test_str(self) -> None:
        assert str(self.parent_pool) == "Parent Pool"


class ConsequencePoolEntryModelTests(TestCase):
    """Test ConsequencePoolEntry model validation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.parent_pool = ConsequencePoolFactory(name="Parent")
        cls.child_pool = ConsequencePoolFactory(name="Child", parent=cls.parent_pool)
        cls.consequence = ConsequenceFactory()

    def test_entry_creation(self) -> None:
        entry = ConsequencePoolEntryFactory(pool=self.parent_pool, consequence=self.consequence)
        assert entry.pool == self.parent_pool
        assert entry.weight_override is None
        assert entry.is_excluded is False

    def test_weight_override(self) -> None:
        entry = ConsequencePoolEntryFactory(
            pool=self.parent_pool,
            consequence=self.consequence,
            weight_override=10,
        )
        assert entry.weight_override == 10

    def test_exclusion_on_parent_rejected(self) -> None:
        entry = ConsequencePoolEntryFactory.build(
            pool=self.parent_pool,
            consequence=self.consequence,
            is_excluded=True,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_exclusion_on_child_allowed(self) -> None:
        entry = ConsequencePoolEntryFactory(
            pool=self.child_pool,
            consequence=self.consequence,
            is_excluded=True,
        )
        assert entry.is_excluded is True

    def test_unique_constraint(self) -> None:
        ConsequencePoolEntryFactory(pool=self.parent_pool, consequence=self.consequence)
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ConsequencePoolEntryFactory(pool=self.parent_pool, consequence=self.consequence)


class GetEffectiveConsequencesTests(TestCase):
    """Test pool inheritance resolution."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome_tier = CheckOutcomeFactory()
        cls.parent_pool = ConsequencePoolFactory(name="Parent")
        cls.c1 = ConsequenceFactory(outcome_tier=cls.outcome_tier, label="C1", weight=10)
        cls.c2 = ConsequenceFactory(outcome_tier=cls.outcome_tier, label="C2", weight=20)
        cls.c3 = ConsequenceFactory(outcome_tier=cls.outcome_tier, label="C3", weight=30)
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.c1)
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.c2)

    def test_simple_pool_no_parent(self) -> None:
        result = get_effective_consequences(self.parent_pool)
        assert len(result) == 2
        labels = {wc.label for wc in result}
        assert labels == {"C1", "C2"}

    def test_default_weight_from_consequence(self) -> None:
        result = get_effective_consequences(self.parent_pool)
        c1_entry = next(wc for wc in result if wc.label == "C1")
        assert c1_entry.weight == 10

    def test_weight_override_on_entry(self) -> None:
        pool = ConsequencePoolFactory(name="Override Pool")
        ConsequencePoolEntryFactory(pool=pool, consequence=self.c1, weight_override=99)
        result = get_effective_consequences(pool)
        assert result[0].weight == 99

    def test_child_inherits_parent(self) -> None:
        child = ConsequencePoolFactory(name="Child", parent=self.parent_pool)
        result = get_effective_consequences(child)
        assert len(result) == 2
        labels = {wc.label for wc in result}
        assert labels == {"C1", "C2"}

    def test_child_adds_consequence(self) -> None:
        child = ConsequencePoolFactory(name="Child Add", parent=self.parent_pool)
        ConsequencePoolEntryFactory(pool=child, consequence=self.c3)
        result = get_effective_consequences(child)
        assert len(result) == 3
        labels = {wc.label for wc in result}
        assert labels == {"C1", "C2", "C3"}

    def test_child_excludes_parent_consequence(self) -> None:
        child = ConsequencePoolFactory(name="Child Excl", parent=self.parent_pool)
        ConsequencePoolEntryFactory(pool=child, consequence=self.c1, is_excluded=True)
        result = get_effective_consequences(child)
        assert len(result) == 1
        assert result[0].label == "C2"

    def test_child_overrides_parent_weight(self) -> None:
        child = ConsequencePoolFactory(name="Child Weight", parent=self.parent_pool)
        ConsequencePoolEntryFactory(pool=child, consequence=self.c1, weight_override=50)
        result = get_effective_consequences(child)
        c1_entry = next(wc for wc in result if wc.label == "C1")
        assert c1_entry.weight == 50

    def test_empty_pool_returns_empty_list(self) -> None:
        pool = ConsequencePoolFactory(name="Empty")
        result = get_effective_consequences(pool)
        assert result == []

    def test_child_excludes_all_returns_empty(self) -> None:
        child = ConsequencePoolFactory(name="Child Empty", parent=self.parent_pool)
        ConsequencePoolEntryFactory(pool=child, consequence=self.c1, is_excluded=True)
        ConsequencePoolEntryFactory(pool=child, consequence=self.c2, is_excluded=True)
        result = get_effective_consequences(child)
        assert result == []

    def test_character_loss_forwarded(self) -> None:
        loss_c = ConsequenceFactory(
            outcome_tier=self.outcome_tier,
            label="Death",
            weight=1,
            character_loss=True,
        )
        pool = ConsequencePoolFactory(name="Loss Pool")
        ConsequencePoolEntryFactory(pool=pool, consequence=loss_c)
        result = get_effective_consequences(pool)
        assert result[0].character_loss is True


class CachedConsequencesTests(TestCase):
    """Test ConsequencePool.cached_consequences property.

    cached_consequences returns a flat list of WeightedConsequence objects
    resolved across single-depth inheritance: parent entries merged with child
    entries, honoring exclusion and child overrides. Elements expose .outcome_tier,
    .weight, .label, and .character_loss — the interface required by select_consequence().
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcome_tier = CheckOutcomeFactory()
        cls.parent_pool = ConsequencePoolFactory(name="CP Parent")
        cls.c_parent = ConsequenceFactory(
            outcome_tier=cls.outcome_tier, label="CP_ParentOnly", weight=5
        )
        cls.c_shared = ConsequenceFactory(
            outcome_tier=cls.outcome_tier, label="CP_Shared", weight=10
        )
        cls.c_child_only = ConsequenceFactory(
            outcome_tier=cls.outcome_tier, label="CP_ChildOnly", weight=15
        )
        # Parent pool has two entries: c_parent and c_shared
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.c_parent)
        ConsequencePoolEntryFactory(pool=cls.parent_pool, consequence=cls.c_shared)

        cls.child_pool = ConsequencePoolFactory(name="CP Child", parent=cls.parent_pool)
        # Child adds c_child_only and also has c_shared (override)
        ConsequencePoolEntryFactory(pool=cls.child_pool, consequence=cls.c_child_only)
        ConsequencePoolEntryFactory(
            pool=cls.child_pool, consequence=cls.c_shared, weight_override=99
        )

    def test_child_cached_consequences_includes_parent_entries(self) -> None:
        """child.cached_consequences includes all three consequences."""
        result = self.child_pool.cached_consequences
        labels = {wc.label for wc in result}
        assert "CP_ParentOnly" in labels
        assert "CP_Shared" in labels
        assert "CP_ChildOnly" in labels

    def test_child_cached_consequences_returns_three_entries(self) -> None:
        """child.cached_consequences returns exactly three entries."""
        result = self.child_pool.cached_consequences
        assert len(result) == 3

    def test_returns_weighted_consequence_instances(self) -> None:
        """Each element is a WeightedConsequence with outcome_tier and weight."""
        result = self.child_pool.cached_consequences
        for item in result:
            assert isinstance(item, WeightedConsequence)
            assert item.outcome_tier is not None
            assert isinstance(item.weight, int)

    def test_default_weight_from_consequence(self) -> None:
        """Weight comes from the Consequence when no override is set."""
        result = self.parent_pool.cached_consequences
        parent_only = next(wc for wc in result if wc.label == "CP_ParentOnly")
        assert parent_only.weight == 5

    def test_weight_override_reflected_in_weight(self) -> None:
        """When child overrides weight, .weight reflects the override value."""
        result = self.child_pool.cached_consequences
        shared = next(wc for wc in result if wc.label == "CP_Shared")
        assert shared.weight == 99

    def test_excluded_entry_omitted(self) -> None:
        """An excluded entry is not returned."""
        c_excl = ConsequenceFactory(outcome_tier=self.outcome_tier, label="CP_Excluded", weight=1)
        parent = ConsequencePoolFactory(name="CP Excl Parent")
        ConsequencePoolEntryFactory(pool=parent, consequence=c_excl)
        child = ConsequencePoolFactory(name="CP Excl Child", parent=parent)
        ConsequencePoolEntryFactory(pool=child, consequence=c_excl, is_excluded=True)
        result = child.cached_consequences
        labels = {wc.label for wc in result}
        assert "CP_Excluded" not in labels

    def test_child_entry_overrides_parent_appears_once(self) -> None:
        """A child entry for the same consequence appears exactly once (no duplicate)."""
        result = self.child_pool.cached_consequences
        shared = [wc for wc in result if wc.label == "CP_Shared"]
        assert len(shared) == 1

    def test_parent_only_pool_returns_own_consequences(self) -> None:
        """A pool without a parent returns its own WeightedConsequences."""
        result = self.parent_pool.cached_consequences
        labels = {wc.label for wc in result}
        assert "CP_ParentOnly" in labels
        assert "CP_Shared" in labels
        assert len(result) == 2
        assert all(isinstance(wc, WeightedConsequence) for wc in result)

    def test_returns_list(self) -> None:
        """cached_consequences returns a list (not a queryset)."""
        result = self.child_pool.cached_consequences
        assert isinstance(result, list)

    def test_child_relist_no_override_uses_parent_consequence_weight(self) -> None:
        """Child entry with weight_override=None re-lists parent consequence at base weight.

        A child pool may include a consequence that also exists on its parent without
        specifying a weight_override. In that case the effective weight must equal the
        consequence's own .weight field (not zero or None).
        """
        c_relist = ConsequenceFactory(outcome_tier=self.outcome_tier, label="CP_Relist", weight=42)
        parent = ConsequencePoolFactory(name="CP Relist Parent")
        ConsequencePoolEntryFactory(pool=parent, consequence=c_relist)
        child = ConsequencePoolFactory(name="CP Relist Child", parent=parent)
        # Re-list with no weight_override — should inherit consequence's base weight
        ConsequencePoolEntryFactory(pool=child, consequence=c_relist, weight_override=None)
        result = child.cached_consequences
        relist_entry = next(wc for wc in result if wc.label == "CP_Relist")
        assert relist_entry.weight == 42

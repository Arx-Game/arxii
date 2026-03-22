"""Tests for ConsequencePool and ConsequencePoolEntry models."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.factories import ConsequenceFactory


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

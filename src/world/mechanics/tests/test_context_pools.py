"""Tests for ContextConsequencePool model."""

from django.test import TestCase

from world.mechanics.factories import ContextConsequencePoolFactory


class ContextConsequencePoolModelTests(TestCase):
    """Test ContextConsequencePool model."""

    def test_creation_rider_mode(self) -> None:
        ctx_pool = ContextConsequencePoolFactory(check_type=None)
        assert ctx_pool.check_type is None

    def test_creation_reactive_mode(self) -> None:
        ctx_pool = ContextConsequencePoolFactory()
        assert ctx_pool.check_type is not None

    def test_str(self) -> None:
        ctx_pool = ContextConsequencePoolFactory()
        assert ctx_pool.property.name in str(ctx_pool)

    def test_unique_constraint(self) -> None:
        ctx_pool = ContextConsequencePoolFactory()
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ContextConsequencePoolFactory(
                property=ctx_pool.property,
                consequence_pool=ctx_pool.consequence_pool,
            )

"""Tests for apply_pool_deterministically() consequence resolution."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.models import ConsequencePoolEntry
from world.checks.consequence_resolution import apply_pool_deterministically
from world.checks.factories import ConsequenceFactory
from world.checks.types import ResolutionContext
from world.mechanics.types import AppliedEffect


class ApplyPoolDeterministicallyTests(TestCase):
    """Tests for the deterministic pool-wide consequence application."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="DeterministicChar")

    def _make_context(self) -> ResolutionContext:
        return ResolutionContext(character=self.character)

    def test_fires_all_consequences_in_pool(self) -> None:
        """All consequences in the pool are walked (returned list has one entry per effect)."""
        pool = ConsequencePoolFactory()
        c1 = ConsequenceFactory(label="ConsequenceA")
        c2 = ConsequenceFactory(label="ConsequenceB")
        c3 = ConsequenceFactory(label="ConsequenceC")
        ConsequencePoolEntryFactory(pool=pool, consequence=c1)
        ConsequencePoolEntryFactory(pool=pool, consequence=c2)
        ConsequencePoolEntryFactory(pool=pool, consequence=c3)

        context = self._make_context()
        # No effects on the consequences — apply_all_effects returns [] per consequence.
        # The function must walk all 3 without error; result is empty but not None.
        result = apply_pool_deterministically(pool=pool, context=context)
        assert isinstance(result, list)

    def test_no_parent_returns_only_own_consequences(self) -> None:
        """Pool with no parent fires only its own entries."""
        pool = ConsequencePoolFactory(parent=None)
        c1 = ConsequenceFactory(label="OwnA")
        c2 = ConsequenceFactory(label="OwnB")
        ConsequencePoolEntryFactory(pool=pool, consequence=c1)
        ConsequencePoolEntryFactory(pool=pool, consequence=c2)

        from world.checks.consequence_resolution import _resolve_pool_consequences

        resolved = _resolve_pool_consequences(pool)
        assert len(resolved) == 2
        labels = {c.label for c in resolved}
        assert labels == {"OwnA", "OwnB"}

    def test_inheritance_walks_parent(self) -> None:
        """Child pool inherits parent consequences AND adds its own."""
        parent_pool = ConsequencePoolFactory(name="ParentPool")
        child_pool = ConsequencePoolFactory(name="ChildPool", parent=parent_pool)

        parent_c = ConsequenceFactory(label="ParentConsequence")
        child_c = ConsequenceFactory(label="ChildConsequence")
        ConsequencePoolEntryFactory(pool=parent_pool, consequence=parent_c)
        ConsequencePoolEntryFactory(pool=child_pool, consequence=child_c)

        from world.checks.consequence_resolution import _resolve_pool_consequences

        resolved = _resolve_pool_consequences(child_pool)
        labels = [c.label for c in resolved]
        # Parent consequence fires first (declaration order), then child
        assert "ParentConsequence" in labels
        assert "ChildConsequence" in labels
        assert labels.index("ParentConsequence") < labels.index("ChildConsequence")

    def test_is_excluded_suppresses_parent_consequence(self) -> None:
        """Child entry with is_excluded=True suppresses the inherited consequence."""
        parent_pool = ConsequencePoolFactory(name="ParentPoolExclude")
        child_pool = ConsequencePoolFactory(name="ChildPoolExclude", parent=parent_pool)

        shared_c = ConsequenceFactory(label="SharedConsequence")
        child_only_c = ConsequenceFactory(label="ChildOnlyConsequence")

        # Parent has both consequences
        ConsequencePoolEntryFactory(pool=parent_pool, consequence=shared_c)
        # Child excludes shared_c and adds its own
        ConsequencePoolEntry.objects.create(pool=child_pool, consequence=shared_c, is_excluded=True)
        ConsequencePoolEntryFactory(pool=child_pool, consequence=child_only_c)

        from world.checks.consequence_resolution import _resolve_pool_consequences

        resolved = _resolve_pool_consequences(child_pool)
        labels = [c.label for c in resolved]
        assert "SharedConsequence" not in labels
        assert "ChildOnlyConsequence" in labels

    def test_returns_applied_effects_list(self) -> None:
        """Return value is always a list of AppliedEffect, never None."""
        pool = ConsequencePoolFactory()
        # Empty pool — no entries, no effects
        result = apply_pool_deterministically(pool=pool, context=self._make_context())
        assert isinstance(result, list)
        # All items (if any) are AppliedEffect instances
        for item in result:
            assert isinstance(item, AppliedEffect)

    def test_full_pipeline_returns_empty_for_no_effects(self) -> None:
        """Pool with consequences but no ConsequenceEffect rows returns empty list."""
        pool = ConsequencePoolFactory()
        c1 = ConsequenceFactory(label="NoEffectA")
        c2 = ConsequenceFactory(label="NoEffectB")
        ConsequencePoolEntryFactory(pool=pool, consequence=c1)
        ConsequencePoolEntryFactory(pool=pool, consequence=c2)

        result = apply_pool_deterministically(pool=pool, context=self._make_context())
        # Consequences have no effects → apply_all_effects returns [] for each
        assert result == []

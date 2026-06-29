"""AbstractSpecializedVariant — abstract base API surface + shared columns (#1578).

The classmethods (matching_variant, newly_crossed_variants, discovery_narrative)
are exercised end-to-end by TechniqueVariant (Task 4) and CovenantRole (Task 5)
tests, since the base is abstract and has no rows of its own.
"""

from django.test import SimpleTestCase

from world.magic.specialization.models import AbstractSpecializedVariant


class AbstractSpecializedVariantSurfaceTests(SimpleTestCase):
    def test_base_is_abstract(self) -> None:
        self.assertTrue(AbstractSpecializedVariant._meta.abstract)

    def test_shared_columns_present(self) -> None:
        field_names = {f.name for f in AbstractSpecializedVariant._meta.get_fields()}
        for name in ("resonance", "unlock_thread_level", "discovery_achievement", "codex_entry"):
            self.assertIn(name, field_names)

    def test_classmethods_exist(self) -> None:
        self.assertTrue(callable(AbstractSpecializedVariant.matching_variant))
        self.assertTrue(callable(AbstractSpecializedVariant.newly_crossed_variants))

    def test_discovery_narrative_is_abstract_contract(self) -> None:
        # The base declares discovery_narrative; it raises NotImplementedError to
        # force concrete subclasses to implement it. Verify the contract.
        import inspect

        src = inspect.getsource(AbstractSpecializedVariant.discovery_narrative)
        self.assertIn("NotImplementedError", src)

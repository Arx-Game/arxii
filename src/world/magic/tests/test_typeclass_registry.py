"""Tests for `_typeclass_path_in_registry` helper.

A general utility for checking whether an Evennia typeclass path (or any of
its MRO ancestors) is present in a registry. It must:
- Return True on exact path match.
- Return True when any base class in the MRO is in the registry
  (so registering a base typeclass admits all subclasses).
- Return False when the registry is empty.
"""

from django.test import SimpleTestCase

from world.magic.services import _typeclass_path_in_registry


class TypeclassRegistryTests(SimpleTestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(
            _typeclass_path_in_registry(
                "typeclasses.objects.Object",
                ("typeclasses.objects.Object",),
            ),
        )

    def test_empty_registry_rejects_everything(self) -> None:
        self.assertFalse(
            _typeclass_path_in_registry(
                "typeclasses.objects.Object",
                (),
            ),
        )

    def test_subclass_admitted_via_mro(self) -> None:
        """If a base typeclass is registered, a subclass should pass."""
        # typeclasses.characters.Character extends Evennia's DefaultObject via DefaultCharacter.
        self.assertTrue(
            _typeclass_path_in_registry(
                "typeclasses.characters.Character",
                ("evennia.objects.objects.DefaultObject",),
            ),
        )

    def test_unrelated_path_not_admitted(self) -> None:
        self.assertFalse(
            _typeclass_path_in_registry(
                "typeclasses.objects.Object",
                ("evennia.scripts.scripts.DefaultScript",),
            ),
        )

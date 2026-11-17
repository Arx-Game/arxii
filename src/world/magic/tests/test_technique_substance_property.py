"""A major gift's substance property rides every technique of the gift (#5125).

The property is read at call time through ``effect_property_ids_by_technique`` and stored
nowhere, so staff cannot untick it and a substance's property change reaches every technique
at once. These are unit tests: they are pure reads of the marks table and the gift lineage.
"""

from django.test import TestCase

from world.combat.clash import _technique_effect_property_ids
from world.magic.constants import GiftKind
from world.magic.factories import GiftFactory, SubstanceFactory, TechniqueFactory
from world.magic.services.technique_marks import effect_property_ids_by_technique
from world.mechanics.factories import PropertyFactory


class TechniqueSubstancePropertyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.shadow = PropertyFactory(name="shadow-carried")
        cls.teleport = PropertyFactory(name="teleport-stored")
        substance = SubstanceFactory(name="shadow-substance", property=cls.shadow)
        cls.gift = GiftFactory(name="Umbra", substance=substance)
        cls.child = GiftFactory(name="Umbra kin", parent=cls.gift)
        cls.minor = GiftFactory(name="Odd job", kind=GiftKind.MINOR, parent=cls.gift)
        cls.technique = TechniqueFactory(name="Veil", gift=cls.gift)
        cls.child_technique = TechniqueFactory(name="Veil kin", gift=cls.child)
        cls.minor_technique = TechniqueFactory(name="Odd veil", gift=cls.minor)

    def marks(self, technique) -> frozenset[int]:
        return effect_property_ids_by_technique([technique.pk])[technique.pk]

    def test_every_technique_of_a_major_gift_carries_its_substance_property(self) -> None:
        self.technique.properties.set([self.teleport])

        self.assertEqual(self.marks(self.technique), {self.shadow.pk, self.teleport.pk})
        self.assertFalse(self.technique.properties.filter(pk=self.shadow.pk).exists())

    def test_child_gift_technique_carries_parent_substance_property(self) -> None:
        self.assertEqual(self.marks(self.child_technique), {self.shadow.pk})

    def test_minor_gift_technique_carries_none(self) -> None:
        self.assertEqual(self.marks(self.minor_technique), frozenset())

    def test_unticking_in_admin_cannot_remove_it(self) -> None:
        self.technique.properties.set([self.shadow])

        self.technique.properties.set([])  # what an admin save with the box cleared writes

        self.assertEqual(self.marks(self.technique), {self.shadow.pk})

    def test_has_property_and_clash_marks_agree(self) -> None:
        self.assertTrue(self.technique.has_property("shadow-carried"))
        self.assertFalse(self.technique.has_property("teleport-stored"))
        self.assertEqual(_technique_effect_property_ids(self.technique), {self.shadow.pk})
        self.assertFalse(self.minor_technique.has_property("shadow-carried"))
        self.assertEqual(_technique_effect_property_ids(self.minor_technique), frozenset())

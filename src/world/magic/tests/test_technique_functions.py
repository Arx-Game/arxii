"""Tests for TechniqueFunction (constants) + TechniqueFunctionTag (#2443).

Layer 2 of the vow-power model: a code-defined vocabulary of fine-grained
technique job labels, plus a content-authored sidecar model linking
techniques to those labels.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
from world.magic.models.techniques import TechniqueFunctionTag


class TechniqueFunctionTagModelTests(TestCase):
    def test_str_uses_technique_name_and_function_display(self) -> None:
        tag = TechniqueFunctionTagFactory(
            technique__name="Ember Lash",
            function=TechniqueFunction.WEAKEN,
        )
        self.assertEqual(str(tag), "Ember Lash: Weaken")

    def test_multiple_tags_per_technique(self) -> None:
        """A technique may carry several function labels (a damage+weaken cast)."""
        technique = TechniqueFactory(name="Cinder Rend")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        TechniqueFunctionTagFactory(
            technique=technique, function=TechniqueFunction.DAMAGE_BUFF_SELF
        )

        self.assertEqual(technique.function_tags.count(), 2)
        functions = set(technique.function_tags.values_list("function", flat=True))
        self.assertEqual(functions, {TechniqueFunction.WEAKEN, TechniqueFunction.DAMAGE_BUFF_SELF})

    def test_unique_function_per_technique(self) -> None:
        """The same function cannot be attached twice to the same technique."""
        technique = TechniqueFactory(name="Doubled Ward")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.BARRIER)

        with self.assertRaises(IntegrityError), transaction.atomic():
            TechniqueFunctionTag.objects.create(
                technique=technique, function=TechniqueFunction.BARRIER
            )

    def test_same_function_allowed_on_different_techniques(self) -> None:
        """Uniqueness is scoped per-technique, not global."""
        first = TechniqueFactory(name="Ward One")
        second = TechniqueFactory(name="Ward Two")
        TechniqueFunctionTagFactory(technique=first, function=TechniqueFunction.BARRIER)
        TechniqueFunctionTagFactory(technique=second, function=TechniqueFunction.BARRIER)

        self.assertEqual(
            TechniqueFunctionTag.objects.filter(function=TechniqueFunction.BARRIER).count(), 2
        )

    def test_cascade_deletes_with_technique(self) -> None:
        technique = TechniqueFactory(name="Fading Charm")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.CHARM)

        technique.delete()

        self.assertEqual(TechniqueFunctionTag.objects.count(), 0)

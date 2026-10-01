"""Schema-level guarantees for personalizing a held technique (#4099)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.classes.services import is_crossing_level
from world.magic.constants import CREATION_PERSONALIZATION_MAX_LEVEL, RestrictionKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    PriceFactory,
    RestrictionFactory,
    SignatureMotifBonusFactory,
    TechniqueFactory,
    TechniqueVariantFactory,
)
from world.magic.models import CharacterTechnique, Restriction
from world.magic.serializers import TechniqueSerializer
from world.magic.services.technique_builder import _restriction_bonus_total
from world.magic.types.technique_builder import TechniqueDesignInput


class CreationLevelCeilingTests(TestCase):
    def test_ceiling_sits_just_below_the_first_crossing(self) -> None:
        for level in range(1, CREATION_PERSONALIZATION_MAX_LEVEL + 1):
            self.assertFalse(is_crossing_level(level))
        self.assertTrue(is_crossing_level(CREATION_PERSONALIZATION_MAX_LEVEL + 1))


class HoldCleanTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.design = RestrictionFactory(kind=RestrictionKind.DESIGN)
        cls.price = PriceFactory()

    def test_design_restriction_is_not_a_price(self) -> None:
        hold = CharacterTechniqueFactory()
        hold.price = self.design
        with self.assertRaises(ValidationError):
            hold.full_clean()

    def test_price_kind_restriction_is_accepted(self) -> None:
        hold = CharacterTechniqueFactory()
        hold.price = self.price
        hold.full_clean()

    def test_early_form_must_be_a_form_of_the_held_technique(self) -> None:
        hold = CharacterTechniqueFactory()
        hold.early_form = TechniqueVariantFactory(unlock_thread_level=1)
        with self.assertRaises(ValidationError):
            hold.full_clean()

    def test_display_name_prefers_the_players_name(self) -> None:
        hold = CharacterTechniqueFactory(technique=TechniqueFactory(name="Scorch Lash"))
        self.assertEqual(hold.display_name, "Scorch Lash")
        hold.custom_name = "Winterbite"
        self.assertEqual(hold.display_name, "Winterbite")


class PersonalizationConstraintTests(TestCase):
    def test_database_refuses_a_dash_in_a_custom_name(self) -> None:
        hold = CharacterTechniqueFactory()
        hold.custom_name = "Winter—bite"
        with self.assertRaises(IntegrityError), transaction.atomic():
            hold.save(update_fields=["custom_name"])
        CharacterTechnique.flush_instance_cache()

    def test_flourish_cost_needs_a_level_below_the_first_crossing(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            SignatureMotifBonusFactory(min_crossing_level=3, creation_point_cost=2)

    def test_design_restriction_cannot_carry_a_creation_cost(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            RestrictionFactory(kind=RestrictionKind.DESIGN, creation_point_cost=1)

    def test_purchasable_form_sits_at_level_one_or_two(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            TechniqueVariantFactory(unlock_thread_level=0, creation_point_cost=3)


class DesignSideGuardTests(TestCase):
    """A price never reaches a technique design (Review Focus 4)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.design = RestrictionFactory(kind=RestrictionKind.DESIGN, power_bonus=10)
        cls.price = PriceFactory(power_bonus=4)
        cls.technique = TechniqueFactory()

    def test_builder_ignores_price_rows(self) -> None:
        design = TechniqueDesignInput(
            name="x",
            description="",
            gift_id=self.technique.gift_id,
            effect_type_id=self.technique.effect_type_id,
            action_category="attack",
            tier=1,
            intensity=1,
            control=1,
            anima_cost=1,
            level=1,
            restriction_ids=(self.design.pk, self.price.pk),
        )
        self.assertEqual(_restriction_bonus_total(design), 10)

    def test_technique_serializer_rejects_a_price(self) -> None:
        serializer = TechniqueSerializer(
            instance=self.technique, data={"restriction_ids": [self.price.pk]}, partial=True
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("restriction_ids", serializer.errors)
        self.assertEqual(Restriction.objects.filter(pk=self.price.pk).count(), 1)

"""Model validation tests for AmbientEmoteLine + AmbientEmoteCondition (#2471 v2)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.distinctions.factories import DistinctionFactory
from world.locations.constants import LocationParentType
from world.magic.factories import ResonanceFactory
from world.narrative.constants import ConditionConnector, ConditionType
from world.narrative.models import AmbientEmoteCondition, AmbientEmoteLine
from world.societies.constants import FameTier
from world.societies.factories import SocietyFactory
from world.species.factories import SpeciesFactory


class AmbientEmoteLineTests(TestCase):
    def test_room_parent_requires_room_profile(self) -> None:
        line = AmbientEmoteLine(parent_type=LocationParentType.ROOM, arriver_body="A shadow.")
        with self.assertRaises(ValidationError):
            line.save()

    def test_area_parent_requires_area(self) -> None:
        line = AmbientEmoteLine(parent_type=LocationParentType.AREA, arriver_body="A scent.")
        with self.assertRaises(ValidationError):
            line.save()

    def test_requires_at_least_one_body(self) -> None:
        profile = RoomProfileFactory()
        line = AmbientEmoteLine(parent_type=LocationParentType.ROOM, room_profile=profile)
        with self.assertRaises(ValidationError):
            line.save()

    def test_valid_line_with_area_saves(self) -> None:
        area = AreaFactory()
        line = AmbientEmoteLine(
            parent_type=LocationParentType.AREA, area=area, arriver_body="A hush lies here."
        )
        line.save()
        self.assertIsNotNone(line.pk)

    def test_discriminator_and_body_errors_both_reported(self) -> None:
        line = AmbientEmoteLine(parent_type=LocationParentType.ROOM)
        with self.assertRaises(ValidationError) as ctx:
            line.save()
        message_dict = ctx.exception.message_dict
        self.assertIn("room_profile", message_dict)
        self.assertIn("arriver_body", message_dict)


class AmbientEmoteConditionTests(TestCase):
    def setUp(self) -> None:
        profile = RoomProfileFactory()
        self.line = AmbientEmoteLine.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=profile,
            bystander_body="A murmur runs through the room.",
        )

    def test_species_requires_species(self) -> None:
        condition = AmbientEmoteCondition(line=self.line, condition_type=ConditionType.SPECIES)
        with self.assertRaises(ValidationError):
            condition.save()

    def test_species_with_species_saves(self) -> None:
        species = SpeciesFactory()
        condition = AmbientEmoteCondition(
            line=self.line, condition_type=ConditionType.SPECIES, species=species
        )
        condition.save()
        self.assertIsNotNone(condition.pk)

    def test_resonance_min_requires_resonance_and_minimum(self) -> None:
        resonance = ResonanceFactory()
        condition = AmbientEmoteCondition(
            line=self.line, condition_type=ConditionType.RESONANCE_MIN, resonance=resonance
        )
        with self.assertRaises(ValidationError):
            condition.save()

    def test_resonance_min_with_both_saves(self) -> None:
        resonance = ResonanceFactory()
        condition = AmbientEmoteCondition(
            line=self.line,
            condition_type=ConditionType.RESONANCE_MIN,
            resonance=resonance,
            minimum_value=50,
        )
        condition.save()
        self.assertIsNotNone(condition.pk)

    def test_distinction_requires_distinction(self) -> None:
        condition = AmbientEmoteCondition(line=self.line, condition_type=ConditionType.DISTINCTION)
        with self.assertRaises(ValidationError):
            condition.save()

    def test_distinction_with_distinction_saves(self) -> None:
        distinction = DistinctionFactory()
        condition = AmbientEmoteCondition(
            line=self.line, condition_type=ConditionType.DISTINCTION, distinction=distinction
        )
        condition.save()
        self.assertIsNotNone(condition.pk)

    def test_renown_min_requires_min_fame_tier(self) -> None:
        condition = AmbientEmoteCondition(line=self.line, condition_type=ConditionType.RENOWN_MIN)
        with self.assertRaises(ValidationError):
            condition.save()

    def test_renown_min_with_tier_and_optional_society_saves(self) -> None:
        society = SocietyFactory()
        condition = AmbientEmoteCondition(
            line=self.line,
            condition_type=ConditionType.RENOWN_MIN,
            min_fame_tier=FameTier.CELEBRITY,
            perceiving_society=society,
        )
        condition.save()
        self.assertIsNotNone(condition.pk)

    def test_multiple_conditions_on_one_line_with_or_connector(self) -> None:
        self.line.condition_connector = ConditionConnector.OR
        self.line.save(update_fields=["condition_connector"])
        species_a = SpeciesFactory()
        species_b = SpeciesFactory()
        AmbientEmoteCondition.objects.create(
            line=self.line, condition_type=ConditionType.SPECIES, species=species_a
        )
        AmbientEmoteCondition.objects.create(
            line=self.line, condition_type=ConditionType.SPECIES, species=species_b
        )
        self.assertEqual(self.line.conditions.count(), 2)


class AmbientEmoteLineFactoryTests(TestCase):
    def test_factory_produces_valid_saved_instance(self) -> None:
        from world.narrative.factories import AmbientEmoteLineFactory

        line = AmbientEmoteLineFactory()
        self.assertIsNotNone(line.pk)

    def test_condition_factory_produces_valid_saved_instance(self) -> None:
        from world.narrative.factories import AmbientEmoteConditionFactory

        condition = AmbientEmoteConditionFactory()
        self.assertIsNotNone(condition.pk)
        self.assertEqual(condition.condition_type, ConditionType.SPECIES)

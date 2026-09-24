"""Secret-victim grievances (#1429).

When a wronged character learns who harmed them, they choose a preset swing (or a custom value)
and ``register_grievance`` adds it as Conflict on their own (one-sided) side of the tie (#3957).
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.factories import GrievanceOptionFactory
from world.relationships.models import CharacterRelationship
from world.relationships.services import register_grievance


class RegisterGrievanceTests(TestCase):
    def setUp(self) -> None:
        self.victim = CharacterSheetFactory()
        self.perpetrator = CharacterSheetFactory()

    def test_preset_grievance_adds_conflict_to_the_victims_side(self) -> None:
        option = GrievanceOptionFactory(label="Unforgivable Betrayal", conflict_points=2000)

        side = register_grievance(source=self.victim, target=self.perpetrator, option=option)

        self.assertEqual(side.conflict, 2000)
        relationship = CharacterRelationship.objects.get(
            source=self.victim, target=self.perpetrator
        )
        self.assertEqual(relationship.conflict, 2000)
        # One-sided: no row is created for the perpetrator.
        self.assertFalse(
            CharacterRelationship.objects.filter(
                source=self.perpetrator, target=self.victim
            ).exists()
        )

    def test_custom_grievance_uses_provided_points(self) -> None:
        side = register_grievance(source=self.victim, target=self.perpetrator, custom_points=123)

        self.assertEqual(side.conflict, 123)

    def test_requires_an_option_or_custom_points(self) -> None:
        with self.assertRaises(ValidationError):
            register_grievance(source=self.victim, target=self.perpetrator)

    def test_rejects_both_option_and_custom_points(self) -> None:
        option = GrievanceOptionFactory(label="Slight", conflict_points=50)
        with self.assertRaises(ValidationError):
            register_grievance(
                source=self.victim, target=self.perpetrator, option=option, custom_points=10
            )

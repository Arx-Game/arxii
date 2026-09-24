"""Tests for ambient relationship bumps (#1699): model constraints + service (#3957)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import BUMP_POINTS, BumpValence
from world.relationships.exceptions import AlreadyAcknowledgedError
from world.relationships.factories import CharacterRelationshipFactory, RelationshipBumpFactory
from world.relationships.models import CharacterRelationship, RelationshipBump
from world.relationships.services import apply_relationship_bump
from world.scenes.factories import InteractionFactory


class RelationshipBumpModelTests(TestCase):
    """Model-level constraints for RelationshipBump."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.relationship = CharacterRelationshipFactory()
        cls.interaction = InteractionFactory()

    def test_duplicate_bump_per_interaction_rejected(self) -> None:
        RelationshipBumpFactory(relationship=self.relationship, interaction=self.interaction)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            RelationshipBumpFactory(
                relationship=self.relationship,
                interaction=self.interaction,
                valence=BumpValence.NEGATIVE,
            )

    def test_same_interaction_bumpable_by_other_relationship(self) -> None:
        RelationshipBumpFactory(relationship=self.relationship, interaction=self.interaction)
        other = CharacterRelationshipFactory()
        bump = RelationshipBumpFactory(relationship=other, interaction=self.interaction)
        self.assertEqual(RelationshipBump.objects.filter(interaction=self.interaction).count(), 2)
        self.assertEqual(bump.timestamp, self.interaction.timestamp)


class ApplyRelationshipBumpTests(TestCase):
    """Service-level behavior of apply_relationship_bump (#3957: gauges, not tracks)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.source = CharacterSheetFactory()
        cls.target = CharacterSheetFactory()
        cls.interaction = InteractionFactory()

    def test_positive_bump_adds_affection(self) -> None:
        bump = apply_relationship_bump(
            source=self.source,
            target=self.target,
            interaction=self.interaction,
            valence=1,
        )
        self.assertEqual(bump.valence, BumpValence.POSITIVE)
        relationship = CharacterRelationship.objects.get(source=self.source, target=self.target)
        self.assertEqual(relationship.affection, BUMP_POINTS)
        self.assertEqual(relationship.conflict, 0)

    def test_negative_bump_adds_conflict(self) -> None:
        apply_relationship_bump(
            source=self.source,
            target=self.target,
            interaction=self.interaction,
            valence=-1,
        )
        relationship = CharacterRelationship.objects.get(source=self.source, target=self.target)
        self.assertEqual(relationship.conflict, BUMP_POINTS)
        self.assertEqual(relationship.affection, 0)

    def test_duplicate_raises_and_applies_no_points(self) -> None:
        apply_relationship_bump(
            source=self.source, target=self.target, interaction=self.interaction, valence=1
        )
        with self.assertRaises(AlreadyAcknowledgedError):
            apply_relationship_bump(
                source=self.source, target=self.target, interaction=self.interaction, valence=1
            )
        relationship = CharacterRelationship.objects.get(source=self.source, target=self.target)
        self.assertEqual(relationship.affection, BUMP_POINTS)
        self.assertEqual(RelationshipBump.objects.filter(relationship=relationship).count(), 1)

    def test_opposite_valence_on_same_interaction_still_deduped(self) -> None:
        apply_relationship_bump(
            source=self.source, target=self.target, interaction=self.interaction, valence=1
        )
        with self.assertRaises(AlreadyAcknowledgedError):
            apply_relationship_bump(
                source=self.source, target=self.target, interaction=self.interaction, valence=-1
            )

    def test_self_target_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            apply_relationship_bump(
                source=self.source, target=self.source, interaction=self.interaction, valence=1
            )

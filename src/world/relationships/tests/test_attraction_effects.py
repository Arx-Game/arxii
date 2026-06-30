"""Flirt/Seduction write-side: add_relationship_condition + the SET_RELATIONSHIP_CONDITION effect,
plus the engine's union of temporary conditions (#1697)."""

from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, ModifierSourceKind
from world.checks.types import ResolutionContext
from world.mechanics.effect_handlers import _set_relationship_condition
from world.mechanics.factories import CharacterModifierFactory
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipConditionFactory,
)
from world.relationships.models import (
    CharacterRelationship,
    TemporaryRelationshipCondition,
)
from world.relationships.services import (
    add_relationship_condition,
    relationship_gated_contributions,
)


class AddRelationshipConditionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.source = CharacterSheetFactory()  # becomes attracted
        cls.target = CharacterSheetFactory()  # the attractive one
        cls.attracted = RelationshipConditionFactory(name="Attracted To")
        cls.very = RelationshipConditionFactory(name="Very Attracted")

    def test_permanent_goes_on_the_m2m(self) -> None:
        add_relationship_condition(source=self.source, target=self.target, condition=self.attracted)
        rel = CharacterRelationship.objects.get(source=self.source, target=self.target)
        self.assertIn(self.attracted, list(rel.conditions.all()))
        self.assertFalse(TemporaryRelationshipCondition.objects.exists())

    def test_temporary_creates_an_expiring_row(self) -> None:
        add_relationship_condition(
            source=self.source,
            target=self.target,
            condition=self.very,
            duration=timedelta(hours=2),
        )
        rel = CharacterRelationship.objects.get(source=self.source, target=self.target)
        temp = TemporaryRelationshipCondition.objects.get(relationship=rel, condition=self.very)
        self.assertGreater(temp.expires_at, timezone.now())
        # Not on the permanent M2M.
        self.assertNotIn(self.very, list(rel.conditions.all()))

    def test_temporary_reup_refreshes_in_place(self) -> None:
        add_relationship_condition(
            source=self.source, target=self.target, condition=self.very, duration=timedelta(hours=1)
        )
        # Capture the VALUE (not the cached instance — SharedMemoryModel returns the same object).
        first_expiry = TemporaryRelationshipCondition.objects.get(condition=self.very).expires_at
        add_relationship_condition(
            source=self.source, target=self.target, condition=self.very, duration=timedelta(hours=5)
        )
        # update_or_create on (relationship, condition) → still one row, later expiry.
        self.assertEqual(
            TemporaryRelationshipCondition.objects.filter(condition=self.very).count(), 1
        )
        refreshed_expiry = TemporaryRelationshipCondition.objects.get(
            condition=self.very
        ).expires_at
        self.assertGreater(refreshed_expiry, first_expiry)


class SetRelationshipConditionEffectTests(TestCase):
    """The handler makes the effect's TARGET attracted to the actor (source=target→actor)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.actor_sheet = CharacterSheetFactory()  # the attractive one (context.character)
        cls.target_sheet = CharacterSheetFactory()  # becomes attracted (context.target)
        cls.condition = RelationshipConditionFactory(name="Attracted To")

    def _effect(self, duration=None):
        return SimpleNamespace(
            target=EffectTarget.TARGET,
            relationship_condition=self.condition,
            relationship_condition_duration=duration,
        )

    def _context(self):
        return ResolutionContext(
            character=self.actor_sheet.character, target=self.target_sheet.character
        )

    def test_handler_makes_target_attracted_to_actor(self) -> None:
        result = _set_relationship_condition(self._effect(), self._context())
        self.assertTrue(result.applied)
        # Directed: source=target (the smitten one), target=actor (the attractive one).
        rel = CharacterRelationship.objects.get(source=self.target_sheet, target=self.actor_sheet)
        self.assertIn(self.condition, list(rel.conditions.all()))

    def test_handler_temporary_duration_creates_temp_row(self) -> None:
        result = _set_relationship_condition(self._effect(timedelta(hours=3)), self._context())
        self.assertTrue(result.applied)
        self.assertTrue(
            TemporaryRelationshipCondition.objects.filter(condition=self.condition).exists()
        )

    def test_handler_skips_self_target(self) -> None:
        ctx = ResolutionContext(
            character=self.actor_sheet.character, target=self.actor_sheet.character
        )
        result = _set_relationship_condition(self._effect(), ctx)
        self.assertFalse(result.applied)
        self.assertEqual(result.skip_reason, "self_target")


class TemporaryConditionEngineUnionTests(TestCase):
    """The allure engine unions ACTIVE temporary conditions; expired ones are ignored (#1697)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.perceiver = CharacterSheetFactory()  # attracted
        cls.perceived = CharacterSheetFactory()  # has allure
        cls.modifier = CharacterModifierFactory(character=cls.perceived, value=10)
        cls.allure = cls.modifier.target
        cls.very = RelationshipConditionFactory(name="Very Attracted")
        cls.very.gates_modifiers.add(cls.allure)
        cls.rel = CharacterRelationshipFactory(
            source=cls.perceiver, target=cls.perceived, is_active=True
        )

    def test_active_temporary_condition_is_counted(self) -> None:
        TemporaryRelationshipCondition.objects.create(
            relationship=self.rel,
            condition=self.very,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        contribs = relationship_gated_contributions(
            perceiver=self.perceiver, perceived=self.perceived
        )
        self.assertEqual(len(contribs), 1)
        self.assertEqual(contribs[0].value, 10)
        self.assertEqual(contribs[0].source_kind, ModifierSourceKind.RELATIONSHIP)

    def test_expired_temporary_condition_is_ignored(self) -> None:
        TemporaryRelationshipCondition.objects.create(
            relationship=self.rel,
            condition=self.very,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        contribs = relationship_gated_contributions(
            perceiver=self.perceiver, perceived=self.perceived
        )
        self.assertEqual(contribs, [])


class ClearVeryAttractedTests(TestCase):
    """The scene-end early clear drops Very Attracted for the scene's participants (#1697)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.outsider = CharacterSheetFactory()
        cls.very = RelationshipConditionFactory(name="Very Attracted")

    def _very_attracted(self, source, target):
        rel = CharacterRelationshipFactory(source=source, target=target, is_active=True)
        return TemporaryRelationshipCondition.objects.create(
            relationship=rel, condition=self.very, expires_at=timezone.now() + timedelta(hours=16)
        )

    def test_clears_rows_touching_a_participant(self) -> None:
        from world.relationships.services import clear_very_attracted

        self._very_attracted(self.a, self.b)  # A very attracted to B (both participants)
        clear_very_attracted({self.a, self.b})
        self.assertFalse(TemporaryRelationshipCondition.objects.exists())

    def test_leaves_unrelated_rows(self) -> None:
        from world.relationships.services import clear_very_attracted

        kept = self._very_attracted(self.outsider, self.a)  # touches outsider (not cleared set)...
        # ...but A IS in the set, so source-or-target match clears it. Use a fully-outside pair:
        kept.delete()
        outside = CharacterSheetFactory()
        kept = self._very_attracted(self.outsider, outside)
        clear_very_attracted({self.a, self.b})
        self.assertTrue(TemporaryRelationshipCondition.objects.filter(pk=kept.pk).exists())

"""Tests for companion-as-mate evaluator bridges (#2666)."""

from django.test import TestCase

from world.covenants.perks.context import SituationContext, SituationParams
from world.covenants.perks.evaluators import SITUATION_EVALUATORS


class ResolveCompanionOwnerCharacterTests(TestCase):
    """_resolve_companion_owner_character bridges companion ObjectDB to owner."""

    def test_returns_none_for_non_companion_objectdb(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.perks.evaluators import _resolve_companion_owner_character

        sheet = CharacterSheetFactory()
        # A real PC character is not a companion objectdb.
        result = _resolve_companion_owner_character(sheet.character)
        self.assertIsNone(result)

    def test_returns_owner_for_companion_objectdb(self):
        from evennia.utils.create import create_object

        from typeclasses.companions import CompanionObject
        from world.character_sheets.factories import CharacterSheetFactory
        from world.companions.factories import CompanionArchetypeFactory
        from world.companions.models import Companion
        from world.covenants.perks.evaluators import _resolve_companion_owner_character
        from world.magic.factories import GiftFactory

        sheet = CharacterSheetFactory()
        archetype = CompanionArchetypeFactory()
        obj = create_object(CompanionObject, key="TestPet", nohome=True)
        Companion.objects.create(
            owner=sheet,
            archetype=archetype,
            granting_gift=GiftFactory(),
            name="TestPet",
            objectdb=obj,
        )

        result = _resolve_companion_owner_character(obj)
        self.assertEqual(result, sheet.character)

    def test_returns_none_for_none_input(self):
        from world.covenants.perks.evaluators import _resolve_companion_owner_character

        result = _resolve_companion_owner_character(None)
        self.assertIsNone(result)


class ProvenanceEvaluatorFalsePathTests(TestCase):
    """Companion bridge doesn't break existing False-path behavior."""

    def _ctx(self, **overrides):
        defaults = {
            "holder": None,
            "subject": None,
            "target": None,
            "resolution": None,
        }
        defaults.update(overrides)
        return SituationContext(**defaults)

    def test_target_swayed_by_ally_no_context(self):
        result = SITUATION_EVALUATORS["target_swayed_by_ally"](self._ctx(), SituationParams())
        self.assertFalse(result)

    def test_shielded_by_ally_no_target(self):
        result = SITUATION_EVALUATORS["shielded_by_ally"](self._ctx(), SituationParams())
        self.assertFalse(result)


class LockEvaluatorFalsePathTests(TestCase):
    """Companion bridge doesn't break lock evaluators' False-path behavior."""

    def _ctx(self, **overrides):
        defaults = {
            "holder": None,
            "subject": None,
            "target": None,
            "resolution": None,
        }
        defaults.update(overrides)
        return SituationContext(**defaults)

    def test_enemy_held_by_ally_no_context(self):
        result = SITUATION_EVALUATORS["enemy_held_by_ally"](self._ctx(), SituationParams())
        self.assertFalse(result)

    def test_barrier_contested_no_context(self):
        result = SITUATION_EVALUATORS["barrier_contested"](self._ctx(), SituationParams())
        self.assertFalse(result)
